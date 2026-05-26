"""asyncio event bus for auto-pivoting (SpiderFoot pattern).

When a module discovers artifacts, the event bus can auto-trigger relevant
modules on the new indicators.  The ``PivotPolicy`` module is the SOLE gate
authority: before invoking any subscribed callback ``EventBus.publish`` calls
``PivotPolicy.evaluate`` and only proceeds on ``verdict=="allow"``.

@decision DEC-EVENTBUS-001
@title Pub/sub event bus with policy-gated cascading and module whitelist
@status accepted
@rationale SpiderFoot's proven pattern: discovered artifacts trigger subscribed
           modules automatically.  The pre-F60 depth limit (max_depth=2) is
           replaced by per-cascade + per-session budgets owned by PivotPolicy
           (DEC-60-PIVOT-POLICY-006).  Module whitelist gives per-workspace
           control over which modules auto-fire; this is orthogonal to policy —
           whitelist selects candidate modules, policy decides whether a candidate
           fires for a given SCO.

@decision DEC-EVENTBUS-002
@title EventBus is disabled by default — opt-in via autopivot command
@status accepted
@rationale Auto-pivoting can consume API quotas rapidly.  Disabled by default
           protects free-tier users.  Analysts enable it explicitly when ready.

@decision DEC-60-PIVOT-POLICY-001
@title PivotPolicy.evaluate is the sole gate authority; no inline gate logic in publish
@status accepted
@rationale EventBus.publish contains exactly one enabled short-circuit and one
           policy call.  All IOC-value, confidence, and budget logic lives in
           PivotPolicy.evaluate.  This is enforced by tests
           (test_event_bus.py::TestPolicyAuthority).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from adversary_pursuit.core.config import AutoPivotPolicyConfig
from adversary_pursuit.core.pivot_policy import DecisionLogEntry, PivotPolicy

logger = logging.getLogger(__name__)


@dataclass
class PivotEvent:
    """An event representing a discovered indicator."""

    stix_type: str
    value: str
    source_module: str
    depth: int = 0
    sco_id: str = ""
    sco_attrs: dict = field(default_factory=dict)


@dataclass
class PivotConfig:
    """Configuration for auto-pivoting.

    ``max_depth`` has been REMOVED in F60 (DEC-60-PIVOT-POLICY-006).  Flow
    control is now owned by per-cascade and per-session budgets in
    ``PivotPolicy`` (via ``AutoPivotPolicyConfig``).

    Fields
    ------
    enabled:
        Master on/off switch.  When False, publish() returns [] immediately.
    module_whitelist:
        Modules that may be cascade-triggered.  Empty list means ALL modules
        are candidates.  Orthogonal to PivotPolicy: whitelist controls which
        modules are candidates; policy decides whether a candidate fires for
        a given SCO value.
    policy:
        AutoPivotPolicyConfig instance.  PivotPolicy is constructed once per
        EventBus from this submodel (DEC-60-PIVOT-POLICY-CONFIG-001).
    """

    enabled: bool = False
    module_whitelist: list[str] = field(default_factory=list)
    policy: AutoPivotPolicyConfig = field(default_factory=AutoPivotPolicyConfig)


# Default subscriptions: which modules trigger on which STIX types
DEFAULT_SUBSCRIPTIONS: dict[str, list[str]] = {
    "osint/abuseipdb": ["ipv4-addr"],
    "osint/shodan_ip": ["ipv4-addr"],
    "osint/dns_resolve": ["domain-name"],
    "osint/whois_lookup": ["domain-name"],
    "cti/otx": ["ipv4-addr", "domain-name"],
    "osint/hibp": ["email-addr"],
    "osint/urlscan": ["url"],
    "osint/greynoise": ["ipv4-addr"],
}


class EventBus:
    """Pub/sub event bus for auto-pivoting.

    ``PivotPolicy`` is the sole gate authority (DEC-60-PIVOT-POLICY-001).
    ``publish()`` calls ``policy.evaluate()`` for each candidate callback
    before invoking it.  No inline IOC-value, confidence, or budget logic
    lives in this class.
    """

    def __init__(self, config: PivotConfig | None = None) -> None:
        self.config = config or PivotConfig()
        self._subscribers: dict[str, list[Callable]] = {}
        self._event_history: list[PivotEvent] = []
        self._policy: PivotPolicy = PivotPolicy(self.config.policy)
        self._decision_log: list[DecisionLogEntry] = []

    def subscribe(self, stix_type: str, callback: Callable) -> None:
        """Subscribe a callback to events of a given STIX type."""
        if stix_type not in self._subscribers:
            self._subscribers[stix_type] = []
        self._subscribers[stix_type].append(callback)

    def unsubscribe(self, stix_type: str, callback: Callable) -> None:
        """Remove a subscription."""
        if stix_type in self._subscribers:
            self._subscribers[stix_type] = [
                cb for cb in self._subscribers[stix_type] if cb is not callback
            ]

    async def publish(
        self,
        event: PivotEvent,
        *,
        dry_run: bool = False,
    ) -> list[dict]:
        """Publish an event and trigger policy-approved subscribed callbacks.

        Respects the enabled flag.  For each candidate callback (subscriber),
        calls ``PivotPolicy.evaluate`` — the sole gate authority.  Only
        callbacks whose decision is ``verdict=="allow"`` are invoked.
        Decision log entries are appended for every evaluation, allow or skip.

        Parameters
        ----------
        event:
            The PivotEvent to publish.
        dry_run:
            When True, evaluate policy gates but do NOT invoke callbacks and
            do NOT increment budget counters.  Returns ``[]``; decision log
            still populated.

        Returns
        -------
        list[dict]
            Aggregated results from all policy-approved callbacks (empty on
            dry-run or when no callbacks pass the policy gates).
        """
        if not self.config.enabled:
            return []

        self._event_history.append(event)
        all_results: list[dict] = []

        for callback in self._subscribers.get(event.stix_type, []):
            # Derive candidate_module name from callback closure attribute if present
            candidate_module: str = getattr(callback, "_module_path", repr(callback))

            decision = self._policy.evaluate(
                sco_type=event.stix_type,
                value=event.value,
                source_module=event.source_module,
                candidate_module=candidate_module,
                sco_attrs=event.sco_attrs,
                depth=event.depth,
                dry_run=dry_run,
                sco_id=event.sco_id,
            )

            entry = self._policy.build_log_entry(
                sco_id=event.sco_id,
                value=event.value,
                candidate_module=candidate_module,
                decision=decision,
                depth=event.depth,
            )
            self._decision_log.append(entry)

            if decision.verdict == "skip":
                logger.debug(
                    "pivot_policy: skip %r for %r via %r — %s [gate=%s]",
                    event.value,
                    event.stix_type,
                    candidate_module,
                    decision.reason,
                    decision.gate,
                )
                continue

            if dry_run:
                continue

            try:
                results = await callback(event)
                if results:
                    all_results.extend(results)
            except Exception as exc:
                logger.warning("Auto-pivot callback failed: %s", exc)

        return all_results

    async def process_results(
        self,
        results: list[dict],
        source_module: str,
        depth: int = 0,
        *,
        dry_run: bool = False,
    ) -> list[dict]:
        """Process module results and auto-pivot on new indicators.

        Resets the per-cascade budget counter at the start of each call
        (DEC-60-PIVOT-POLICY-006) so that each source SCO gets a fresh
        per-cascade budget window.

        Parameters
        ----------
        results:
            Raw hunt() output list.  Each entry may have ``type``, ``value``,
            ``id``, and arbitrary attribute keys.
        source_module:
            Module that produced the results (used for policy gate evaluation).
        depth:
            Cascade depth passed to PivotEvents constructed here.
        dry_run:
            When True, passes dry_run through to publish() — evaluates policy
            but does not invoke callbacks.
        """
        self._policy.reset_cascade_budget()

        pivot_results: list[dict] = []
        for result in results:
            stix_type = result.get("type", "")
            value = result.get("value", "")
            if stix_type and value:
                event = PivotEvent(
                    stix_type=stix_type,
                    value=value,
                    source_module=source_module,
                    depth=depth + 1,
                    sco_id=result.get("id", ""),
                    sco_attrs={k: v for k, v in result.items() if k not in ("type", "value", "id")},
                )
                new_results = await self.publish(event, dry_run=dry_run)
                pivot_results.extend(new_results)
        return pivot_results

    def register_module_subscriptions(
        self, module_name: str, stix_types: list[str], hunt_callback: Callable
    ) -> None:
        """Register a module to auto-trigger on specific STIX types.

        The callback is tagged with ``_module_path`` so ``publish`` can
        extract the module name for policy evaluation without a secondary
        lookup.
        """
        if self.config.module_whitelist and module_name not in self.config.module_whitelist:
            return
        # Tag callback with the module path for policy candidate_module lookup
        hunt_callback._module_path = module_name  # type: ignore[attr-defined]
        for stype in stix_types:
            self.subscribe(stype, hunt_callback)

    def get_history(self) -> list[PivotEvent]:
        """Return event history."""
        return list(self._event_history)

    def get_decision_log(self) -> list[DecisionLogEntry]:
        """Return the full policy decision log."""
        return list(self._decision_log)

    def clear_history(self) -> None:
        """Clear event history, decision log, and reset session budget."""
        self._event_history.clear()
        self._decision_log.clear()
        self._policy.reset_session_budget()

    @property
    def subscriber_count(self) -> int:
        """Total number of subscriptions across all types."""
        return sum(len(cbs) for cbs in self._subscribers.values())
