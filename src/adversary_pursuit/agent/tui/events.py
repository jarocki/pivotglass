"""Typed event bus for the TUI layer.

Provides typed dataclass events and a thread-safe EventBus that decouples
TUI producers (battery runs, agent runner, yield command handler) from TUI
consumers (LivePane, scrollback renderer, future status surfaces).

@decision DEC-TUI-EVENTS-001
@title Typed dataclass events; single EventBus per TuiApplication session
@status accepted
@rationale Using typed dataclasses instead of string-keyed dicts gives
           callers import-time safety and editors autocomplete. A single
           EventBus instance per session wires all producers and consumers
           without introducing a global registry. Thread-safety is achieved
           via threading.Lock so battery threads and the PTK app thread can
           both publish without races.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


@dataclass
class TargetChanged:
    """Fired when the analyst sets or changes the investigation target.

    Parameters
    ----------
    target:
        The raw target string (e.g. "evil.example.com").
    target_type:
        STIX SCO type string auto-detected from target, or
        "unrecognized-type" when detection fails.
    """

    target: str
    target_type: str  # "domain-name", "ipv4-addr", "url", "file", "email-addr", "unrecognized-type"


@dataclass
class HypothesisChanged:
    """Fired when the analyst updates the working hypothesis.

    Parameters
    ----------
    text:
        Free-text hypothesis string.
    """

    text: str


@dataclass
class BatteryStarted:
    """Fired when a Battery begins executing.

    Parameters
    ----------
    battery_name:
        Canonical battery name (e.g. "identity_battery").
    tools:
        Ordered tuple of tool names to be executed.
    target_slots:
        Tuple of DossierSlotName.value strings this battery targets.
        Multi-slot batteries (e.g. reputation covers ttps + capability)
        emit all covered slot names so the live pane can display them.
    reason:
        Human-readable reason why this battery was dispatched.
    """

    battery_name: str
    tools: tuple[str, ...]
    target_slots: tuple[str, ...]  # tuple of DossierSlotName.value strings
    reason: str


@dataclass
class BatteryToolStarted:
    """Fired immediately before a tool is called inside a battery run.

    Parameters
    ----------
    battery_name:
        Parent battery name.
    tool_name:
        Name of the tool about to execute.
    """

    battery_name: str
    tool_name: str


@dataclass
class BatteryToolFinished:
    """Fired immediately after a tool completes inside a battery run.

    Parameters
    ----------
    battery_name:
        Parent battery name.
    tool_name:
        Name of the tool that finished.
    success:
        True when the tool returned without error; False on exception.
    """

    battery_name: str
    tool_name: str
    success: bool


@dataclass
class BatteryFinished:
    """Fired when a Battery has fully completed (all tools run or halted).

    Parameters
    ----------
    battery_name:
        The battery that finished.
    success:
        True when the battery ran to completion without being stopped.
    """

    battery_name: str
    success: bool


@dataclass
class SlotTransition:
    """Fired when a dossier slot changes status (e.g. empty → partial).

    Parameters
    ----------
    slot_name:
        DossierSlotName.value string.
    old_status:
        SlotStatus.value before the transition.
    new_status:
        SlotStatus.value after the transition.
    """

    slot_name: str  # DossierSlotName.value
    old_status: str  # SlotStatus.value
    new_status: str  # SlotStatus.value


@dataclass
class YieldReceived:
    """Fired when the analyst submits a yield command.

    Parameters
    ----------
    primitive:
        One of "stop", "focus", "add", "skip".
    argument:
        The argument token for focus/add/skip; None for stop.
    """

    primitive: str  # "stop", "focus", "add", "skip"
    argument: str | None  # for focus/add/skip


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

_Handler = Callable[[Any], None]


class EventBus:
    """Thread-safe publish/subscribe event bus for TUI events.

    A single instance is created by TuiApplication and shared with all
    producers and consumers in the session. Handlers are called synchronously
    in the publishing thread, so handlers must be fast and non-blocking.

    Usage
    -----
    bus = EventBus()
    bus.subscribe(BatteryStarted, lambda e: print(e.battery_name))
    bus.publish(BatteryStarted(name="identity_battery", tools=(...), ...))
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        # Maps event class -> list of handler callables
        self._handlers: dict[type, list[_Handler]] = {}

    def subscribe(self, event_type: type, handler: _Handler) -> None:
        """Register a handler for the given event type.

        Parameters
        ----------
        event_type:
            The dataclass event class to listen for.
        handler:
            Callable that accepts one argument (the event instance).
            Called synchronously when an event of this type is published.
        """
        with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        """Publish an event to all registered handlers.

        Handlers are called in registration order, synchronously in the
        calling thread. Exceptions in individual handlers are swallowed so
        one bad handler does not prevent others from receiving the event.

        Parameters
        ----------
        event:
            An event dataclass instance.
        """
        with self._lock:
            handlers = list(self._handlers.get(type(event), []))
        for handler in handlers:
            try:
                handler(event)
            except Exception:  # noqa: BLE001
                pass  # handler errors must never block the publishing thread
