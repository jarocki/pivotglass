"""Challenge system for Adversary Pursuit.

Challenges are intelligence requirements with verifiable completion conditions.
They can be loaded from YAML files or defined programmatically.

@decision DEC-CHALLENGE-001
@title workspace_data dict contract for check_completion
@status accepted
@rationale Challenge.check_completion receives a plain dict rather than a
           WorkspaceManager instance. This keeps Challenge dataclasses pure,
           database-free, and trivially testable. APConsole assembles the dict
           from WorkspaceManager before calling ChallengeManager.check_all().
           The dict contract has stable keys: stix_type_counts (dict[str, int]),
           modules_used (list[str]), total_score (int), total_indicators (int),
           elapsed_seconds (int | float, optional), indicators (list[dict], optional).
           This mirrors how ScoringEngine.score_results() receives a snapshot
           rather than a live DB connection — consistent pattern across gamification.

@decision DEC-CHALLENGE-002
@title In-memory challenge state (no persistence)
@status accepted
@rationale Challenge completion is session-scoped for v1. Persisting completed
           challenges to SQLite would require schema changes and migration logic.
           The gamification layer is intentionally stateless at the storage layer
           for v1: ChallengeManager holds state in memory, APConsole re-instantiates
           it on each session. This matches how ScoringEngine works (no state between
           sessions). Persistence can be added in v2 as a StorageBackend adapter.

@decision DEC-CHALLENGE-003
@title YAML file format: top-level "challenges" list key
@status accepted
@rationale Using {"challenges": [...]} instead of a bare list gives YAML files
           a named root key, making them extensible (future keys: metadata, version,
           author) without breaking the parser. ChallengeType enum values in YAML
           use lowercase strings ("standard", "pivoting", "discovery", "timed")
           matching the Enum.value attributes for simple string-to-enum conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import yaml


class ChallengeType(Enum):
    """Categories of challenges reflecting different intelligence hunting patterns."""
    STANDARD = "standard"     # Find a specific indicator
    PIVOTING = "pivoting"     # Multi-step transform chain
    DISCOVERY = "discovery"   # Identify a new tool/TTP/campaign
    TIMED = "timed"           # Complete within time limit


class ChallengeStatus(Enum):
    """Lifecycle state of a challenge."""
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


@dataclass
class Challenge:
    """A single intelligence challenge with a verifiable completion condition.

    Parameters
    ----------
    id:
        Unique identifier (e.g. "ch-001").
    name:
        Short display name shown in the challenges table.
    description:
        Full description of what the analyst must do.
    challenge_type:
        Category controlling display and eligibility (e.g. TIMED).
    points:
        Bonus points awarded upon first completion.
    verification:
        Dict describing how to verify completion. Supported types:
        - {"type": "indicator_count", "stix_type": "ipv4-addr"|None, "min_count": N}
        - {"type": "indicator_exists", "stix_type": "ipv4-addr", "value": "1.2.3.4"}
        - {"type": "module_used", "module_name": "osint/shodan_ip"}
        - {"type": "score_threshold", "min_score": 500}
        - {"type": "module_count", "min_count": 3}
    hints:
        Optional list of hints revealed progressively.
    time_limit_seconds:
        For TIMED challenges only: maximum elapsed seconds to complete.
        Compared against workspace_data["elapsed_seconds"] if present.
    status:
        Current lifecycle state. Starts ACTIVE.
    completed_at:
        UTC datetime when the challenge was first completed, or None.
    """

    id: str
    name: str
    description: str
    challenge_type: ChallengeType
    points: int
    verification: dict
    hints: list[str] = field(default_factory=list)
    time_limit_seconds: int | None = None
    status: ChallengeStatus = field(default=ChallengeStatus.ACTIVE)
    completed_at: datetime | None = None

    def check_completion(self, workspace_data: dict) -> bool:
        """Check if this challenge is satisfied by the current workspace state.

        For TIMED challenges with a ``time_limit_seconds``, the check fails if
        ``workspace_data["elapsed_seconds"]`` exceeds the limit (time expired
        before the goal was achieved).

        Parameters
        ----------
        workspace_data:
            Dict assembled by APConsole from WorkspaceManager. Expected keys:
            - stix_type_counts: dict[str, int]
            - modules_used: list[str]
            - total_score: int
            - total_indicators: int
            - elapsed_seconds: int | float (optional, used by TIMED)
            - indicators: list[dict] (optional, used by indicator_exists)

        Returns
        -------
        bool
            True if the challenge conditions are met, False otherwise.
        """
        # Timed guard: if time_limit_seconds is set and elapsed exceeds it, fail.
        if self.time_limit_seconds is not None:
            elapsed = workspace_data.get("elapsed_seconds")
            if elapsed is not None and elapsed > self.time_limit_seconds:
                return False

        v_type = self.verification.get("type", "")

        if v_type == "indicator_count":
            return self._check_indicator_count(workspace_data)
        elif v_type == "indicator_exists":
            return self._check_indicator_exists(workspace_data)
        elif v_type == "module_used":
            return self._check_module_used(workspace_data)
        elif v_type == "score_threshold":
            return self._check_score_threshold(workspace_data)
        elif v_type == "module_count":
            return self._check_module_count(workspace_data)

        # Unknown verification type: fail gracefully rather than raising.
        return False

    # ------------------------------------------------------------------
    # Private verification handlers
    # ------------------------------------------------------------------

    def _check_indicator_count(self, workspace_data: dict) -> bool:
        """Check min_count of STIX objects of stix_type (or all types if None)."""
        stix_type = self.verification.get("stix_type")
        min_count = self.verification.get("min_count", 1)

        if stix_type is None:
            # Count all indicators regardless of type
            actual = workspace_data.get("total_indicators", 0)
        else:
            counts = workspace_data.get("stix_type_counts", {})
            actual = counts.get(stix_type, 0)

        return actual >= min_count

    def _check_indicator_exists(self, workspace_data: dict) -> bool:
        """Check that a specific indicator value exists in the workspace."""
        stix_type = self.verification.get("stix_type")
        target_value = self.verification.get("value")
        indicators = workspace_data.get("indicators", [])

        for ind in indicators:
            if ind.get("type") == stix_type and ind.get("value") == target_value:
                return True
        return False

    def _check_module_used(self, workspace_data: dict) -> bool:
        """Check that a specific module was used in this workspace."""
        module_name = self.verification.get("module_name", "")
        modules_used = workspace_data.get("modules_used", [])
        return module_name in modules_used

    def _check_score_threshold(self, workspace_data: dict) -> bool:
        """Check that total workspace score meets the minimum."""
        min_score = self.verification.get("min_score", 0)
        total = workspace_data.get("total_score", 0)
        return total >= min_score

    def _check_module_count(self, workspace_data: dict) -> bool:
        """Check that at least min_count distinct modules have been used."""
        min_count = self.verification.get("min_count", 1)
        modules_used = workspace_data.get("modules_used", [])
        # Deduplicate: same module used N times counts as 1 distinct module.
        distinct = len(set(modules_used))
        return distinct >= min_count


class ChallengeManager:
    """Manages the lifecycle of all challenges for a session.

    Holds challenge state in memory (DEC-CHALLENGE-002). Challenges are loaded
    at init from built-in definitions. Additional challenges can be loaded from
    YAML files via load_from_yaml().

    Usage::

        mgr = ChallengeManager()
        workspace_data = {
            "stix_type_counts": {"ipv4-addr": 3},
            "modules_used": ["osint/whois_lookup"],
            "total_score": 150,
            "total_indicators": 3,
        }
        newly_completed = mgr.check_all(workspace_data)
        for ch in newly_completed:
            print(f"Challenge completed: {ch.name} (+{ch.points} pts)")
    """

    def __init__(self) -> None:
        self._challenges: dict[str, Challenge] = {}
        self._load_builtin_challenges()

    def _load_builtin_challenges(self) -> None:
        """Load the 5 starter challenges into memory."""
        starters = [
            Challenge(
                id="ch-001",
                name="First Blood",
                description="Discover your first IP address using any module",
                challenge_type=ChallengeType.STANDARD,
                points=50,
                verification={
                    "type": "indicator_count",
                    "stix_type": "ipv4-addr",
                    "min_count": 1,
                },
                hints=["Use PassiveTotal, VirusTotal, URLScan, or Censys enrichment"],
            ),
            Challenge(
                id="ch-002",
                name="Domain Hunter",
                description="Discover 5 unique domains",
                challenge_type=ChallengeType.STANDARD,
                points=150,
                verification={
                    "type": "indicator_count",
                    "stix_type": "domain-name",
                    "min_count": 5,
                },
                hints=["Use WHOIS plus passive-DNS or certificate intelligence"],
            ),
            Challenge(
                id="ch-003",
                name="The Pivot",
                description="Use at least 3 different modules in the same workspace",
                challenge_type=ChallengeType.PIVOTING,
                points=200,
                verification={"type": "module_count", "min_count": 3},
            ),
            Challenge(
                id="ch-004",
                name="Score Hunter",
                description="Reach a score of 500 points",
                challenge_type=ChallengeType.STANDARD,
                points=100,
                verification={"type": "score_threshold", "min_score": 500},
            ),
            Challenge(
                id="ch-005",
                name="Speed Run",
                description="Discover 10 indicators in under 5 minutes",
                challenge_type=ChallengeType.TIMED,
                points=300,
                verification={
                    "type": "indicator_count",
                    "stix_type": None,
                    "min_count": 10,
                },
                time_limit_seconds=300,
            ),
        ]
        for ch in starters:
            self._challenges[ch.id] = ch

    def load_from_yaml(self, path: str) -> int:
        """Load challenges from a YAML file.

        The YAML file must have a top-level "challenges" key containing a list
        of challenge dicts. Each dict must have: id, name, description,
        challenge_type, points, verification. Optional: hints, time_limit_seconds.

        Parameters
        ----------
        path:
            Absolute or relative path to the YAML file.

        Returns
        -------
        int
            Number of challenges successfully loaded.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        yaml.YAMLError
            If the file is not valid YAML.
        """
        with open(path) as f:
            data = yaml.safe_load(f)

        challenges_data = data.get("challenges", [])
        count = 0
        for raw in challenges_data:
            ch = self._parse_challenge_dict(raw)
            if ch is not None:
                self._challenges[ch.id] = ch
                count += 1
        return count

    def _parse_challenge_dict(self, raw: dict) -> Challenge | None:
        """Parse a raw dict into a Challenge dataclass.

        Returns None if required fields are missing.
        """
        try:
            type_str = raw.get("challenge_type", "standard")
            # Map lowercase string values to enum (DEC-CHALLENGE-003)
            challenge_type = ChallengeType(type_str)

            return Challenge(
                id=raw["id"],
                name=raw["name"],
                description=raw.get("description", ""),
                challenge_type=challenge_type,
                points=int(raw.get("points", 0)),
                verification=raw.get("verification", {}),
                hints=list(raw.get("hints", [])),
                time_limit_seconds=raw.get("time_limit_seconds"),
            )
        except (KeyError, ValueError):
            return None

    def get_active(self) -> list[Challenge]:
        """Return all challenges with ACTIVE status.

        Returns
        -------
        list[Challenge]
            Challenges that have not yet been completed or expired.
        """
        return [ch for ch in self._challenges.values() if ch.status == ChallengeStatus.ACTIVE]

    def check_all(self, workspace_data: dict) -> list[Challenge]:
        """Check all active challenges against the current workspace state.

        For each active challenge that passes check_completion(), marks it
        COMPLETED and records a completed_at timestamp.

        For TIMED challenges where elapsed_seconds exceeds time_limit_seconds
        and the challenge is not yet satisfied, marks it EXPIRED.

        Parameters
        ----------
        workspace_data:
            Dict assembled by APConsole. See Challenge.check_completion() for
            the full key contract (DEC-CHALLENGE-001).

        Returns
        -------
        list[Challenge]
            Challenges that were NEWLY completed in this call (status changed
            from ACTIVE to COMPLETED). Already-completed challenges are excluded.
        """
        newly_completed: list[Challenge] = []

        for ch in self.get_active():
            if ch.check_completion(workspace_data):
                ch.status = ChallengeStatus.COMPLETED
                ch.completed_at = datetime.now(tz=timezone.utc)
                newly_completed.append(ch)
            elif (
                ch.challenge_type == ChallengeType.TIMED
                and ch.time_limit_seconds is not None
            ):
                # Mark expired if time limit exceeded and not completed
                elapsed = workspace_data.get("elapsed_seconds")
                if elapsed is not None and elapsed > ch.time_limit_seconds:
                    ch.status = ChallengeStatus.EXPIRED

        return newly_completed

    def get_challenge(self, id: str) -> Challenge | None:
        """Get a challenge by its unique ID.

        Parameters
        ----------
        id:
            Challenge identifier (e.g. "ch-001").

        Returns
        -------
        Challenge | None
            The challenge, or None if not found.
        """
        return self._challenges.get(id)

    def list_challenges(self) -> list[dict]:
        """List all challenges with their current status as serializable dicts.

        Returns
        -------
        list[dict]
            Each dict has: id, name, description, challenge_type, points,
            status, completed_at (ISO string or None), hints.
        """
        result = []
        for ch in self._challenges.values():
            result.append({
                "id": ch.id,
                "name": ch.name,
                "description": ch.description,
                "challenge_type": ch.challenge_type.value,
                "points": ch.points,
                "status": ch.status.value,
                "completed_at": (
                    ch.completed_at.isoformat() if ch.completed_at is not None else None
                ),
                "hints": ch.hints,
                "time_limit_seconds": ch.time_limit_seconds,
            })
        return result
