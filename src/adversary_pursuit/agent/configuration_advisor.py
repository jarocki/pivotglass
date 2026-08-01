"""Periodic, local, character-voiced configuration guidance.

The advisor never calls a model or provider.  It observes only masked local
configuration state, selects one actionable suggestion deterministically, and
labels the result as character narration rather than evidence.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Callable

from adversary_pursuit.agent.model_control import ModelControl
from adversary_pursuit.gamification.modes import display_mode_name


@dataclass(frozen=True)
class ConfigurationAdvisory:
    """One bounded, non-modal configuration suggestion."""

    character: str
    character_name: str
    message: str
    action: str
    category: str = "configuration"
    content_class: str = "narration"
    evidence: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_VOICE: dict[str, tuple[str, ...]] = {
    "default": (
        "{issue} Recommended next action: {action}.",
        "Configuration check: {issue} Use {action} when you are ready.",
    ),
    "sensei": (
        "Chuck Norris does not fear configuration drift. Configuration drift fears "
        "the command `{action}`. {issue}",
        "{issue} Chuck Norris calls that a warm-up. Run `{action}`.",
    ),
    "the_computer": (
        "I am completely operational, unlike this setting. {issue} I suggest "
        "`{action}`. Calmly.",
        "{issue} This is entirely fixable, Dave. Use `{action}`.",
    ),
    "full_troll": (
        "{issue} Bold configuration strategy. 🙄 Try `{action}` before blaming the API.",
        "Tiny snag: {issue} Even the documentation would recommend `{action}`.",
    ),
    "detective": (
        "{issue} The smallest inconsistency is often the decisive clue. Apply "
        "`{action}`.",
        "Elementary configuration hygiene: {issue} Our next move is `{action}`.",
    ),
    "the_sprawl": (
        "{issue} The console glow says the route is cold. Jack in with `{action}`.",
        "{issue} Somewhere beyond the ICE, an endpoint is waiting. Try `{action}`.",
    ),
    "m4tr1x": (
        "{issue} The system is showing you the door. Follow it with `{action}`.",
        "{issue} There is a difference between knowing the path and running "
        "`{action}`.",
    ),
}


class ConfigurationAdvisor:
    """Throttle and render configuration suggestions without stealing focus."""

    def __init__(
        self,
        control: ModelControl,
        *,
        interval_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.control = control
        self.interval_seconds = max(1.0, float(interval_seconds))
        self._clock = clock
        self._next_due = 0.0
        self._sequence = 0

    def poll(
        self, character: str, *, force: bool = False
    ) -> ConfigurationAdvisory | None:
        """Return a due advisory, or ``None`` when disabled/not yet due."""
        if not self.control.config_mgr.is_configuration_advisor_enabled():
            return None
        now = self._clock()
        if not force and now < self._next_due:
            return None
        self._next_due = now + self.interval_seconds

        repair = self.control.repair_plan()
        action = repair["actions"][0]
        issue = str(action["summary"])
        command = str(action["command"])
        templates = _VOICE.get(character, _VOICE["default"])
        template = templates[self._sequence % len(templates)]
        self._sequence += 1
        return ConfigurationAdvisory(
            character=character,
            character_name=display_mode_name(character),
            message=template.format(issue=issue, action=command),
            action=command,
        )
