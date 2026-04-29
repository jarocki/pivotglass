"""asyncio event bus for auto-pivoting (SpiderFoot pattern).

When a module discovers artifacts, the event bus can auto-trigger relevant
modules on the new indicators.

@decision DEC-EVENTBUS-001
@title Pub/sub event bus with depth-limited cascading and module whitelist
@status accepted
@rationale SpiderFoot's proven pattern: discovered artifacts trigger subscribed
           modules automatically. Depth limit prevents infinite recursion.
           Module whitelist gives per-workspace control over which modules auto-fire.

@decision DEC-EVENTBUS-002
@title EventBus is disabled by default — opt-in via autopivot command
@status accepted
@rationale Auto-pivoting can consume API quotas rapidly. Disabled by default
           protects free-tier users. Analysts enable it explicitly when ready.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class PivotEvent:
    """An event representing a discovered indicator."""
    stix_type: str
    value: str
    source_module: str
    depth: int = 0


@dataclass
class PivotConfig:
    """Configuration for auto-pivoting."""
    enabled: bool = False
    max_depth: int = 2
    module_whitelist: list[str] = field(default_factory=list)


# Default subscriptions: which modules trigger on which STIX types
DEFAULT_SUBSCRIPTIONS: dict[str, list[str]] = {
    "osint/abuseipdb": ["ipv4-addr"],
    "osint/shodan_ip": ["ipv4-addr"],
    "osint/dns_resolve": ["domain-name"],
    "osint/whois_lookup": ["domain-name"],
    "cti/otx": ["ipv4-addr", "domain-name"],
    "osint/hibp": ["email-addr"],
    "osint/urlscan": ["url"],
}


class EventBus:
    """Pub/sub event bus for auto-pivoting."""

    def __init__(self, config: PivotConfig | None = None) -> None:
        self.config = config or PivotConfig()
        self._subscribers: dict[str, list[Callable]] = {}
        self._event_history: list[PivotEvent] = []

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

    async def publish(self, event: PivotEvent) -> list[dict]:
        """Publish an event and trigger all subscribed callbacks.

        Returns aggregated results from all triggered modules.
        Respects depth limit, enabled flag, and module whitelist.
        """
        if not self.config.enabled:
            return []

        if event.depth >= self.config.max_depth:
            logger.debug("Max pivot depth %d reached, stopping", self.config.max_depth)
            return []

        self._event_history.append(event)
        all_results: list[dict] = []

        for callback in self._subscribers.get(event.stix_type, []):
            try:
                results = await callback(event)
                if results:
                    all_results.extend(results)
            except Exception as exc:
                logger.warning("Auto-pivot callback failed: %s", exc)

        return all_results

    async def process_results(
        self, results: list[dict], source_module: str, depth: int = 0
    ) -> list[dict]:
        """Process module results and auto-pivot on new indicators."""
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
                )
                new_results = await self.publish(event)
                pivot_results.extend(new_results)
        return pivot_results

    def register_module_subscriptions(
        self, module_name: str, stix_types: list[str], hunt_callback: Callable
    ) -> None:
        """Register a module to auto-trigger on specific STIX types."""
        if (
            self.config.module_whitelist
            and module_name not in self.config.module_whitelist
        ):
            return
        for stype in stix_types:
            self.subscribe(stype, hunt_callback)

    def get_history(self) -> list[PivotEvent]:
        """Return event history."""
        return list(self._event_history)

    def clear_history(self) -> None:
        """Clear event history."""
        self._event_history.clear()

    @property
    def subscriber_count(self) -> int:
        """Total number of subscriptions across all types."""
        return sum(len(cbs) for cbs in self._subscribers.values())
