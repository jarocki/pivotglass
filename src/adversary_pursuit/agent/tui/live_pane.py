"""Fixed 6-row live status pane for the TUI.

Renders the bottom 6 rows of the terminal with real-time session state:
character identity, target, hypothesis, dossier strip, activity, and yield
hint. Subscribes to EventBus events and is polled by TuiApplication at the
character-specific refresh cadence.

@decision DEC-TUI-LIVE-PANE-001
@title exactly 6 rows always; character-driven refresh cadence
@status accepted
@rationale A fixed-height live pane means the scrollback window above it
           always gets exactly H-7 rows (6 pane rows + 1 input row). This
           makes layout deterministic and snapshot-testable without a real
           terminal. The refresh cadence table maps each character to an Hz
           value: characters with high-energy voices (full_troll=4 Hz) refresh
           faster; calm characters (hal9000=1 Hz, ninja=1 Hz) refresh slower.
           This is a design affordance — the pane itself does not animate text;
           it simply re-renders at the cadence so tool-queue updates are seen
           promptly.
"""

from __future__ import annotations

import threading
import time

from adversary_pursuit.agent.tui.events import (
    BatteryFinished,
    BatteryStarted,
    BatteryToolFinished,
    BatteryToolStarted,
    EventBus,
    HypothesisChanged,
    SlotTransition,
    TargetChanged,
    YieldReceived,
)
from adversary_pursuit.dossier.slot_glyphs import SLOT_ORDER, render_slot_strip

# ---------------------------------------------------------------------------
# Character refresh cadence table (DEC-TUI-LIVE-PANE-001)
# ---------------------------------------------------------------------------

_REFRESH_HZ: dict[str, float] = {
    "hal9000": 1.0,
    "ninja": 1.0,
    "default": 2.0,
    "sun_tzu": 2.0,
    "deckard": 2.0,
    "bruce_lee": 2.0,
    "bureaucrat": 2.0,
    "chuck_norris": 2.0,
    "bobby_hill": 2.0,
    "full_troll": 4.0,
}

_DEFAULT_HZ: float = 2.0

# Number of filled slots in the dossier
_TOTAL_SLOTS: int = len(SLOT_ORDER)

# Yield hint strings (idle vs active)
_YIELD_HINT_IDLE = "  yield: stop · focus <tool> · add <tool> · skip <tool>"
_YIELD_HINT_ACTIVE = "► yield: stop · focus <tool> · add <tool> · skip <tool>"

# Flash duration for first-battery discoverability nudge (seconds)
_FLASH_DURATION: float = 3.0


class LivePane:
    """Fixed 6-row live status pane.

    Subscribes to all EventBus event types and maintains internal state
    that is rendered on demand via render(). TuiApplication polls render()
    at refresh_hz to update the prompt_toolkit layout.

    Parameters
    ----------
    bus:
        Session EventBus. LivePane registers handlers for all event types.
    mode_name:
        Initial character mode name (e.g. "default", "deckard").
    model_display:
        Model identifier string shown in row 1 (e.g. "opus 4.7").
    workspace_mgr:
        Optional WorkspaceManager for elapsed-time display. When None,
        workspace elapsed time shows "--:--".
    """

    def __init__(
        self,
        bus: EventBus,
        mode_name: str = "default",
        model_display: str = "",
        workspace_mgr=None,
    ) -> None:
        self._lock = threading.Lock()
        self._mode_name = mode_name
        self._model_display = model_display
        self._workspace_mgr = workspace_mgr
        self._session_start = time.monotonic()

        # State updated by event handlers
        self._target: str = "—"
        self._target_type: str = ""
        self._hypothesis: str = "—"
        self._dossier_state = None  # DossierState | None
        self._slots_filled: int = 0

        # Battery activity state
        self._battery_active: bool = False
        self._battery_name: str = ""
        self._current_tool: str = ""
        self._pending_tools: list[str] = []

        # Last yield command received
        self._last_yield: str = ""

        # Discoverability: flash hint on first battery
        self._first_battery_seen: bool = False
        self._flash_until: float = 0.0

        # Subscribe to all event types
        bus.subscribe(TargetChanged, self._on_target_changed)
        bus.subscribe(HypothesisChanged, self._on_hypothesis_changed)
        bus.subscribe(BatteryStarted, self._on_battery_started)
        bus.subscribe(BatteryToolStarted, self._on_battery_tool_started)
        bus.subscribe(BatteryToolFinished, self._on_battery_tool_finished)
        bus.subscribe(BatteryFinished, self._on_battery_finished)
        bus.subscribe(SlotTransition, self._on_slot_transition)
        bus.subscribe(YieldReceived, self._on_yield_received)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_target_changed(self, event: TargetChanged) -> None:
        with self._lock:
            self._target = event.target or "—"
            self._target_type = event.target_type

    def _on_hypothesis_changed(self, event: HypothesisChanged) -> None:
        with self._lock:
            self._hypothesis = event.text or "—"

    def _on_battery_started(self, event: BatteryStarted) -> None:
        with self._lock:
            self._battery_active = True
            self._battery_name = event.battery_name
            self._pending_tools = list(event.tools)
            self._current_tool = self._pending_tools[0] if self._pending_tools else ""
            if not self._first_battery_seen:
                self._first_battery_seen = True
                self._flash_until = time.monotonic() + _FLASH_DURATION

    def _on_battery_tool_started(self, event: BatteryToolStarted) -> None:
        with self._lock:
            self._current_tool = event.tool_name
            if event.tool_name in self._pending_tools:
                idx = self._pending_tools.index(event.tool_name)
                self._pending_tools = self._pending_tools[idx + 1 :]

    def _on_battery_tool_finished(self, event: BatteryToolFinished) -> None:
        # Current tool display cleared; next tool will be set by BatteryToolStarted
        with self._lock:
            self._current_tool = ""

    def _on_battery_finished(self, event: BatteryFinished) -> None:
        with self._lock:
            self._battery_active = False
            self._battery_name = ""
            self._current_tool = ""
            self._pending_tools = []

    def _on_slot_transition(self, event: SlotTransition) -> None:
        # Recount filled slots from the transition — we don't hold a full
        # DossierState here; callers may inject it via set_dossier_state().
        # For the slot counter we simply maintain an integer.
        with self._lock:
            from adversary_pursuit.dossier.slots import SlotStatus

            if event.new_status == SlotStatus.FILLED.value:
                self._slots_filled = min(self._slots_filled + 1, _TOTAL_SLOTS)
            elif event.old_status == SlotStatus.FILLED.value:
                self._slots_filled = max(self._slots_filled - 1, 0)

    def _on_yield_received(self, event: YieldReceived) -> None:
        with self._lock:
            if event.argument:
                self._last_yield = f"{event.primitive} {event.argument}"
            else:
                self._last_yield = event.primitive

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def set_character(self, mode_name: str) -> None:
        """Update the active character, which changes the refresh cadence.

        Parameters
        ----------
        mode_name:
            New character mode name.
        """
        with self._lock:
            self._mode_name = mode_name

    def set_dossier_state(self, dossier_state) -> None:
        """Inject an updated DossierState for strip rendering.

        Parameters
        ----------
        dossier_state:
            A DossierState instance from slot_inference.py, or None.
        """
        with self._lock:
            self._dossier_state = dossier_state
            if dossier_state is not None:
                from adversary_pursuit.dossier.slots import SlotStatus

                self._slots_filled = sum(
                    1 for s in dossier_state.slots.values() if s.status == SlotStatus.FILLED
                )

    @property
    def refresh_hz(self) -> float:
        """Refresh rate in Hz for the active character."""
        with self._lock:
            return _REFRESH_HZ.get(self._mode_name, _DEFAULT_HZ)

    def render(self) -> list[str]:
        """Render the live pane as exactly 6 plain-text lines.

        Returns
        -------
        list[str]
            Always exactly 6 elements. Used by TuiApplication and snapshot
            tests.
        """
        with self._lock:
            return self._render_locked()

    def _render_locked(self) -> list[str]:
        """Render while holding self._lock. Must not acquire the lock again."""
        mode = self._mode_name
        model = self._model_display or ""
        target = self._target
        hypothesis = self._hypothesis
        dossier_state = self._dossier_state
        slots_filled = self._slots_filled
        battery_active = self._battery_active
        battery_name = self._battery_name
        current_tool = self._current_tool
        pending_tools = list(self._pending_tools)
        now = time.monotonic()
        flash_active = battery_active and (now < self._flash_until)

        # Row 1: character + model + workspace elapsed
        elapsed = int(now - self._session_start)
        elapsed_str = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
        right_segment = f"{model} │ ws {elapsed_str}" if model else f"ws {elapsed_str}"
        left_segment = f"🕵 {mode}"
        # Pad to ~72 chars
        pad = max(1, 72 - len(left_segment) - len(right_segment))
        row1 = left_segment + " " * pad + right_segment

        # Row 2: target
        row2 = f"target: {target}"

        # Row 3: hypothesis
        row3 = f"hypothesis: {hypothesis}"

        # Row 4: dossier strip
        strip = render_slot_strip(dossier_state)
        slot_count = f"{slots_filled}/{_TOTAL_SLOTS} slots"
        pad4 = max(1, 72 - len("dossier: " + strip) - len(slot_count))
        row4 = f"dossier: {strip}" + " " * pad4 + slot_count

        # Row 5: activity — tool queue summary or idle phrase
        if battery_active and current_tool:
            remaining = len(pending_tools)
            if remaining:
                row5 = f"  {current_tool}  (+{remaining} queued)"
            else:
                row5 = f"  {current_tool}"
        elif battery_active and battery_name:
            row5 = f"  {battery_name} running…"
        else:
            row5 = "  idle"

        # Row 6: yield hint
        if battery_active or flash_active:
            row6 = _YIELD_HINT_ACTIVE
        else:
            row6 = _YIELD_HINT_IDLE

        return [row1, row2, row3, row4, row5, row6]
