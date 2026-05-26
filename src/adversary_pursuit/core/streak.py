"""ISO-week streak tracking for Adversary Pursuit.

StreakManager is the sole authority for ~/.ap/streak.json (or a test-injected
path). It tracks daily hunt streaks in the style of Duolingo: consecutive days
build a streak; one freeze per ISO week bridges a single missed day.

Schema (streak.json):
    {
        "current_streak": int,
        "longest_streak": int,
        "last_hunt_date": "YYYY-MM-DD" | null,
        "freezes_used_this_week": int,
        "freeze_limit_per_week": int,
        "last_iso_week": [iso_year, iso_week] | null
    }

@decision DEC-62-STREAK-001
@title StreakManager as sole authority for streak.json; path injectable for tests
@status accepted
@rationale A single module owns all reads and writes to streak.json so there is
           never a second authority that could diverge. The path is an __init__
           parameter so tests can write to tmp_path/streak.json without touching
           ~/.ap/streak.json. All writes are atomic via tempfile + os.replace to
           survive process crash between write and rename.

@decision DEC-62-STREAK-002
@title ISO-week anchoring for freeze reset, not calendar Monday-UTC
@status accepted
@rationale date.isocalendar() gives the ISO (year, week) pair which correctly
           handles year-boundary weeks (e.g. last days of Dec belong to W1 of
           next year). Using (iso_year, iso_week) as the reset key avoids the
           Monday-UTC approximation that breaks across year boundaries. The pair
           is stored as a two-element list in JSON for portability.

@decision DEC-62-STREAK-003
@title Duolingo-style 1 freeze per ISO week; gap of exactly 1 day consumes it
@status accepted
@rationale Gap of exactly 1 calendar day (delta.days == 2, meaning one calendar
           day was skipped) can be bridged by the freeze if freezes_used_this_week
           < freeze_limit_per_week. A gap of >= 2 missed days always breaks the
           streak even if a freeze is available — Duolingo semantics. The freeze
           limit resets when the ISO week changes between hunts.

@decision DEC-62-STREAK-004
@title Corruption → log WARNING, rename to .corrupt-<ts>, fresh state
@status accepted
@rationale A corrupted file must never crash the application. The corrupt file is
           renamed (not deleted) so the user can recover data manually if needed.
           A fresh zero-state is returned so the streak begins again cleanly.
           The WARNING log is visible at default log level so the analyst can
           investigate without it being an error that might propagate.

@decision DEC-62-STREAK-005
@title Clock-skew backward → clamp without mutation
@status accepted
@rationale If the system clock jumps backward (NTP correction, suspend/resume),
           processing the past date would incorrectly break the streak. Clamping
           (returning early without changing state) is the correct response:
           the hunt is acknowledged, the streak is unchanged, and the analyst is
           not penalised for a clock drift they did not cause.

@decision DEC-62-STREAK-006
@title format_banner_line() shared by banner.py and console.py preloop
@status accepted
@rationale A single method on StreakManager produces the streak display line so
           both render surfaces (agent boot banner and cmd2 preloop) show identical
           text. AP_NO_BANNER=1 suppression is the caller's responsibility —
           format_banner_line() always returns the correct string; callers that
           respect AP_NO_BANNER skip rendering it.

@decision DEC-62-STREAK-007
@title update() fires from APConsole._execute_hunt and ToolContext.run_module only
@status accepted
@rationale Modules must never call update() directly — they do not own the streak
           authority. The two wiring points (cmd2 console and agent tool path) are
           the only callers in production. This mirrors the badge and challenge
           check pattern: a single post-hunt hook that runs regardless of which
           module was used.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

#: Default path for the streak state file.
DEFAULT_STREAK_PATH: Path = Path.home() / ".ap" / "streak.json"

#: Number of freeze tokens allowed per ISO week.
_DEFAULT_FREEZE_LIMIT: int = 1


@dataclass
class StreakState:
    """In-memory representation of the streak JSON schema.

    All fields map 1:1 to JSON keys so serialisation is trivial.
    """

    current_streak: int = 0
    longest_streak: int = 0
    last_hunt_date: date | None = None
    freezes_used_this_week: int = 0
    freeze_limit_per_week: int = _DEFAULT_FREEZE_LIMIT
    last_iso_week: tuple[int, int] | None = None  # (iso_year, iso_week)


def _to_dict(state: StreakState) -> dict:
    """Serialise StreakState to a JSON-safe dict."""
    return {
        "current_streak": state.current_streak,
        "longest_streak": state.longest_streak,
        "last_hunt_date": state.last_hunt_date.isoformat() if state.last_hunt_date else None,
        "freezes_used_this_week": state.freezes_used_this_week,
        "freeze_limit_per_week": state.freeze_limit_per_week,
        "last_iso_week": list(state.last_iso_week) if state.last_iso_week else None,
    }


def _from_dict(data: dict) -> StreakState:
    """Deserialise a dict from JSON into a StreakState."""
    last_hunt_str = data.get("last_hunt_date")
    last_hunt: date | None = date.fromisoformat(last_hunt_str) if last_hunt_str else None

    raw_week = data.get("last_iso_week")
    last_iso_week: tuple[int, int] | None = (
        (int(raw_week[0]), int(raw_week[1])) if raw_week and len(raw_week) == 2 else None
    )

    return StreakState(
        current_streak=int(data.get("current_streak", 0)),
        longest_streak=int(data.get("longest_streak", 0)),
        last_hunt_date=last_hunt,
        freezes_used_this_week=int(data.get("freezes_used_this_week", 0)),
        freeze_limit_per_week=int(data.get("freeze_limit_per_week", _DEFAULT_FREEZE_LIMIT)),
        last_iso_week=last_iso_week,
    )


class StreakManager:
    """Manages the daily hunt streak.

    The StreakManager is the sole reader and writer of the streak JSON file.
    Construct with ``path=tmp_path / "streak.json"`` in tests to avoid touching
    the real user state.

    Usage
    -----
    mgr = StreakManager()          # uses DEFAULT_STREAK_PATH
    mgr.update(date.today())       # call after every successful hunt
    print(mgr.format_banner_line()) # for boot banner or preloop display
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialise and load existing state from disk.

        Parameters
        ----------
        path:
            Override the streak file path. Defaults to DEFAULT_STREAK_PATH.
            Tests pass tmp_path/streak.json to avoid touching real user data.
        """
        self._path: Path = path if path is not None else DEFAULT_STREAK_PATH
        self._state: StreakState = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> StreakState:
        """Return the current in-memory streak state (read-only view)."""
        return self._state

    def update(self, today: date) -> None:
        """Record a successful hunt on *today* and persist the updated state.

        Idempotent for the same calendar day — calling twice on the same date
        is a no-op. Clamps backward time without mutation.

        Parameters
        ----------
        today:
            The calendar date of the hunt. In production use ``date.today()``.
            Tests pass an explicit date to control the timeline.
        """
        s = self._state

        # Clock-skew backward: never process a date before the last hunt.
        # DEC-62-STREAK-005: clamp without mutation.
        if s.last_hunt_date is not None and today < s.last_hunt_date:
            logger.debug(
                "StreakManager.update: backward date %s < last_hunt %s — clamped",
                today,
                s.last_hunt_date,
            )
            return

        # Same-day idempotency: already recorded today.
        if s.last_hunt_date == today:
            return

        # Determine new ISO week and reset freeze counter when week rolls over.
        today_iso = today.isocalendar()[:2]  # (iso_year, iso_week)
        current_week = s.last_iso_week

        if current_week is not None and tuple(current_week) != tuple(today_iso):
            # New ISO week — reset freeze counter.
            s.freezes_used_this_week = 0
        s.last_iso_week = today_iso

        if s.last_hunt_date is None:
            # Very first hunt ever.
            s.current_streak = 1
            s.last_hunt_date = today
            s.longest_streak = max(s.longest_streak, s.current_streak)
            self._save(s)
            return

        gap_days = (today - s.last_hunt_date).days

        if gap_days == 1:
            # Consecutive day — streak grows.
            s.current_streak += 1
        elif gap_days == 2 and s.freezes_used_this_week < s.freeze_limit_per_week:
            # Exactly one missed day and a freeze is available — bridge it.
            # DEC-62-STREAK-003.
            s.freezes_used_this_week += 1
            s.current_streak += 1
        else:
            # Gap too large or no freeze available — streak breaks.
            s.current_streak = 1

        s.longest_streak = max(s.longest_streak, s.current_streak)
        s.last_hunt_date = today
        self._save(s)

    def format_banner_line(self) -> str:
        """Return a single display line suitable for the boot banner or preloop.

        Returns an empty string when current_streak == 0 so callers can
        suppress the line without special-casing.

        DEC-62-STREAK-006: shared by banner.render_boot_banner and
        APConsole.preloop. Callers that respect AP_NO_BANNER=1 skip
        rendering the returned string.

        Returns
        -------
        str
            e.g. ``"🔥 5-day streak! (best: 12)"`` or ``""`` for no streak.
        """
        s = self._state
        if s.current_streak == 0:
            return ""
        streak_word = "day" if s.current_streak == 1 else "days"
        return f"🔥 {s.current_streak}-{streak_word} streak! (best: {s.longest_streak})"

    # ------------------------------------------------------------------
    # Internal: load / save
    # ------------------------------------------------------------------

    def _load(self) -> StreakState:
        """Load and parse streak.json; return fresh state on any error.

        DEC-62-STREAK-004: corruption → rename to .corrupt-<ts>, fresh state.
        Missing file → fresh state (not an error).
        """
        if not self._path.exists():
            return StreakState()

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return _from_dict(data)
        except Exception as exc:  # noqa: BLE001
            # Corruption: rename and start fresh.
            ts = int(time.time())
            corrupt_path = self._path.parent / f"{self._path.name}.corrupt-{ts}"
            try:
                self._path.rename(corrupt_path)
                logger.warning(
                    "streak.json corrupted (%s); renamed to %s — starting fresh",
                    exc,
                    corrupt_path,
                )
            except Exception as rename_exc:  # noqa: BLE001
                logger.warning(
                    "streak.json corrupted (%s) and rename failed (%s) — starting fresh",
                    exc,
                    rename_exc,
                )
            return StreakState()

    def _save(self, state: StreakState) -> None:
        """Atomically write state to the streak JSON file.

        Uses tempfile in the same directory + os.replace for an atomic swap.
        This prevents a half-written file on process crash (DEC-62-STREAK-001).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = _to_dict(state)
        payload = json.dumps(data, indent=2)

        # Write to a temp file in the same directory so os.replace is atomic
        # (same filesystem). NamedTemporaryFile with delete=False so we can
        # close it before replacing (required on Windows; harmless on POSIX).
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_name, self._path)
        except Exception:
            # Best-effort cleanup of the temp file on write failure.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
