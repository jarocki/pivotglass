"""Battery — deterministic ordered tool dispatch for the TUI.

A Battery is a frozen configuration object that groups a set of tools,
a target dossier slot, and a set of applicable target types. BatteryRun
executes a battery against a concrete target, firing typed events on the
shared EventBus and honouring yield commands received mid-flight.

@decision DEC-BATTERY-DISPATCH-001
@title deterministic dispatch, not LLM-driven
@status accepted
@rationale Batteries execute tools in a fixed, declared order. This makes
           the analyst's experience predictable (the same battery always
           runs the same tools in the same sequence) and makes the system
           testable without an LLM in the loop. The LLM is consulted for
           investigation strategy (what to pursue next), not for tool
           ordering inside an already-dispatched battery.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from adversary_pursuit.dossier.slots import DossierSlotName

# ---------------------------------------------------------------------------
# Battery configuration (frozen, shareable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Battery:
    """Immutable configuration object for a named tool battery.

    Parameters
    ----------
    name:
        Canonical battery identifier (e.g. "identity_battery").
    tools:
        Ordered tuple of tool names to execute.
    target_slot:
        The dossier slot this battery contributes to.
    applies_to:
        Tuple of STIX SCO type strings this battery is valid for.
        Used by dispatch_batteries() in battery_registry.py to filter.
    hypothesis_hint:
        Short description of what the battery is trying to establish.
        Shown in the live pane when the battery starts.
    """

    name: str
    tools: tuple[str, ...]
    target_slot: DossierSlotName
    applies_to: tuple[str, ...]  # target type strings
    hypothesis_hint: str


# ---------------------------------------------------------------------------
# BatteryRun — execution state for one run of a Battery
# ---------------------------------------------------------------------------


class BatteryRun:
    """Stateful execution of a Battery against a concrete target.

    One BatteryRun instance is created per battery dispatch. It holds the
    mutable pending-tool queue, a threading.Lock for yield-command safety,
    and references to the EventBus and tool executor.

    Parameters
    ----------
    battery:
        The Battery configuration to execute.
    bus:
        Session EventBus. BatteryStarted/ToolStarted/ToolFinished/Finished
        events are published here.
    tool_executor:
        Callable ``(tool_name: str, target: str) -> Any``. Called for each
        pending tool. Return value is ignored; exceptions are caught and
        reported via BatteryToolFinished(success=False).
    """

    def __init__(
        self,
        battery: Battery,
        bus,  # EventBus — avoid circular import; duck-typed
        tool_executor,  # Callable[[str, str], Any]
    ) -> None:
        self._battery = battery
        self._bus = bus
        self._tool_executor = tool_executor
        self._lock = threading.Lock()
        # Mutable pending queue — yield commands may reorder or prune this
        self._pending_tools: list[str] = list(battery.tools)
        self._stopped = False

    # ------------------------------------------------------------------
    # Public run interface
    # ------------------------------------------------------------------

    def run(self, target: str) -> None:
        """Execute the battery against *target*.

        Fires BatteryStarted, then iterates _pending_tools. For each tool:
        fires BatteryToolStarted, calls tool_executor, fires
        BatteryToolFinished. Fires BatteryFinished when the loop ends
        (either all tools ran or a "stop" yield halted execution).

        The pending queue is checked fresh at each iteration so that yield
        commands applied mid-run (via apply_yield) take effect immediately
        on the next tool.

        Parameters
        ----------
        target:
            The investigation target string (e.g. "evil.example.com").
        """
        from adversary_pursuit.agent.tui.events import (
            BatteryFinished,
            BatteryStarted,
            BatteryToolFinished,
            BatteryToolStarted,
        )

        self._bus.publish(
            BatteryStarted(
                battery_name=self._battery.name,
                tools=tuple(self._pending_tools),
                target_slot=self._battery.target_slot.value,
                reason=self._battery.hypothesis_hint,
            )
        )

        success = True
        while True:
            with self._lock:
                if self._stopped or not self._pending_tools:
                    if self._stopped:
                        success = False
                    break
                tool_name = self._pending_tools.pop(0)

            self._bus.publish(
                BatteryToolStarted(
                    battery_name=self._battery.name,
                    tool_name=tool_name,
                )
            )

            tool_success = True
            try:
                self._tool_executor(tool_name, target)
            except Exception:  # noqa: BLE001
                tool_success = False

            self._bus.publish(
                BatteryToolFinished(
                    battery_name=self._battery.name,
                    tool_name=tool_name,
                    success=tool_success,
                )
            )

        self._bus.publish(
            BatteryFinished(
                battery_name=self._battery.name,
                success=success,
            )
        )

    # ------------------------------------------------------------------
    # Yield command application
    # ------------------------------------------------------------------

    def apply_yield(self, cmd) -> None:  # cmd: YieldCommand
        """Apply a yield command to the pending tool queue.

        Thread-safe. May be called from the PTK input thread while run()
        is executing in the battery thread.

        Supported primitives:
        - "stop":  halt the battery after the current tool finishes.
        - "focus": move the named tool to the front of the pending queue.
                   If the tool is not pending, this is a no-op.
        - "add":   append the named tool to the end of the pending queue.
        - "skip":  remove the named tool from the pending queue.
                   If the tool is not pending, this is a no-op.

        Parameters
        ----------
        cmd:
            A YieldCommand instance (duck-typed to avoid circular import).
        """
        primitive = cmd.primitive
        argument = cmd.argument

        with self._lock:
            if primitive == "stop":
                self._stopped = True

            elif primitive == "focus" and argument is not None:
                if argument in self._pending_tools:
                    self._pending_tools.remove(argument)
                    self._pending_tools.insert(0, argument)

            elif primitive == "add" and argument is not None:
                self._pending_tools.append(argument)

            elif primitive == "skip" and argument is not None:
                if argument in self._pending_tools:
                    self._pending_tools.remove(argument)

    # ------------------------------------------------------------------
    # Accessors (for testing and live pane display)
    # ------------------------------------------------------------------

    @property
    def pending_tools(self) -> list[str]:
        """Return a snapshot of the current pending tool queue."""
        with self._lock:
            return list(self._pending_tools)

    @property
    def is_stopped(self) -> bool:
        """True when a "stop" yield has been applied."""
        with self._lock:
            return self._stopped

    @property
    def battery(self) -> Battery:
        """The Battery configuration being executed."""
        return self._battery
