"""Tests for Issue #19: Event Bus (Auto-Pivot).

@decision DEC-TEST-EVENTBUS-001
@title Tests cover pub/sub, depth limits, whitelist, and process_results
@status accepted
@rationale The event bus is safety-critical (depth limit prevents infinite
           recursion, whitelist prevents API quota burn). Every safety
           mechanism must be tested.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from adversary_pursuit.core.event_bus import (
    DEFAULT_SUBSCRIPTIONS,
    EventBus,
    PivotConfig,
    PivotEvent,
)


@pytest.fixture
def bus():
    return EventBus(PivotConfig(enabled=True, max_depth=3))


@pytest.fixture
def disabled_bus():
    return EventBus(PivotConfig(enabled=False))


class TestPivotEvent:
    def test_fields(self):
        e = PivotEvent("ipv4-addr", "1.2.3.4", "osint/dns_resolve", depth=1)
        assert e.stix_type == "ipv4-addr"
        assert e.value == "1.2.3.4"
        assert e.source_module == "osint/dns_resolve"
        assert e.depth == 1

    def test_default_depth(self):
        e = PivotEvent("domain-name", "evil.com", "osint/whois_lookup")
        assert e.depth == 0


class TestPivotConfig:
    def test_defaults(self):
        c = PivotConfig()
        assert c.enabled is False
        assert c.max_depth == 2
        assert c.module_whitelist == []


class TestSubscribeUnsubscribe:
    def test_subscribe_adds_callback(self, bus):
        cb = AsyncMock(return_value=[])
        bus.subscribe("ipv4-addr", cb)
        assert bus.subscriber_count == 1

    def test_unsubscribe_removes_callback(self, bus):
        cb = AsyncMock(return_value=[])
        bus.subscribe("ipv4-addr", cb)
        bus.unsubscribe("ipv4-addr", cb)
        assert bus.subscriber_count == 0

    def test_unsubscribe_nonexistent_type(self, bus):
        cb = AsyncMock(return_value=[])
        bus.unsubscribe("ipv4-addr", cb)  # no error

    def test_multiple_subscribers(self, bus):
        cb1 = AsyncMock(return_value=[])
        cb2 = AsyncMock(return_value=[])
        bus.subscribe("ipv4-addr", cb1)
        bus.subscribe("ipv4-addr", cb2)
        assert bus.subscriber_count == 2


class TestPublish:
    def test_publish_triggers_callback(self, bus):
        cb = AsyncMock(return_value=[{"type": "domain-name", "value": "evil.com"}])
        bus.subscribe("ipv4-addr", cb)
        event = PivotEvent("ipv4-addr", "1.2.3.4", "test", depth=0)
        results = asyncio.run(bus.publish(event))
        cb.assert_called_once_with(event)
        assert len(results) == 1

    def test_publish_disabled_returns_empty(self, disabled_bus):
        cb = AsyncMock(return_value=[{"type": "x"}])
        disabled_bus.subscribe("ipv4-addr", cb)
        event = PivotEvent("ipv4-addr", "1.2.3.4", "test")
        results = asyncio.run(disabled_bus.publish(event))
        assert results == []
        cb.assert_not_called()

    def test_publish_depth_limit(self, bus):
        cb = AsyncMock(return_value=[{"type": "x"}])
        bus.subscribe("ipv4-addr", cb)
        event = PivotEvent("ipv4-addr", "1.2.3.4", "test", depth=3)  # at max
        results = asyncio.run(bus.publish(event))
        assert results == []
        cb.assert_not_called()

    def test_publish_below_depth_limit(self, bus):
        cb = AsyncMock(return_value=[{"type": "x"}])
        bus.subscribe("ipv4-addr", cb)
        event = PivotEvent("ipv4-addr", "1.2.3.4", "test", depth=2)
        results = asyncio.run(bus.publish(event))
        assert len(results) == 1

    def test_publish_records_history(self, bus):
        bus.subscribe("ipv4-addr", AsyncMock(return_value=[]))
        event = PivotEvent("ipv4-addr", "1.2.3.4", "test")
        asyncio.run(bus.publish(event))
        assert len(bus.get_history()) == 1

    def test_publish_callback_error_continues(self, bus):
        bad_cb = AsyncMock(side_effect=Exception("boom"))
        good_cb = AsyncMock(return_value=[{"type": "ok"}])
        bus.subscribe("ipv4-addr", bad_cb)
        bus.subscribe("ipv4-addr", good_cb)
        event = PivotEvent("ipv4-addr", "1.2.3.4", "test")
        results = asyncio.run(bus.publish(event))
        assert len(results) == 1

    def test_publish_no_subscribers(self, bus):
        event = PivotEvent("email-addr", "x@y.com", "test")
        results = asyncio.run(bus.publish(event))
        assert results == []


class TestProcessResults:
    def test_process_creates_events(self, bus):
        cb = AsyncMock(return_value=[])
        bus.subscribe("ipv4-addr", cb)
        results = [{"type": "ipv4-addr", "value": "1.2.3.4"}]
        asyncio.run(bus.process_results(results, "osint/dns_resolve"))
        assert cb.call_count == 1

    def test_process_increments_depth(self, bus):
        cb = AsyncMock(return_value=[])
        bus.subscribe("ipv4-addr", cb)
        results = [{"type": "ipv4-addr", "value": "1.2.3.4"}]
        asyncio.run(bus.process_results(results, "test", depth=1))
        event = cb.call_args[0][0]
        assert event.depth == 2

    def test_process_skips_empty_type(self, bus):
        cb = AsyncMock(return_value=[])
        bus.subscribe("ipv4-addr", cb)
        results = [{"type": "", "value": "1.2.3.4"}]
        asyncio.run(bus.process_results(results, "test"))
        cb.assert_not_called()


class TestModuleRegistration:
    def test_register_adds_subscriptions(self, bus):
        cb = AsyncMock()
        bus.register_module_subscriptions("osint/abuseipdb", ["ipv4-addr"], cb)
        assert bus.subscriber_count == 1

    def test_whitelist_blocks_unregistered(self):
        bus = EventBus(PivotConfig(enabled=True, module_whitelist=["osint/abuseipdb"]))
        cb = AsyncMock()
        bus.register_module_subscriptions("cti/otx", ["ipv4-addr"], cb)
        assert bus.subscriber_count == 0

    def test_whitelist_allows_registered(self):
        bus = EventBus(PivotConfig(enabled=True, module_whitelist=["osint/abuseipdb"]))
        cb = AsyncMock()
        bus.register_module_subscriptions("osint/abuseipdb", ["ipv4-addr"], cb)
        assert bus.subscriber_count == 1

    def test_empty_whitelist_allows_all(self, bus):
        cb = AsyncMock()
        bus.register_module_subscriptions("anything", ["ipv4-addr", "domain-name"], cb)
        assert bus.subscriber_count == 2


class TestHistory:
    def test_empty_history(self, bus):
        assert bus.get_history() == []

    def test_clear_history(self, bus):
        bus.subscribe("ipv4-addr", AsyncMock(return_value=[]))
        asyncio.run(bus.publish(PivotEvent("ipv4-addr", "1.2.3.4", "test")))
        bus.clear_history()
        assert bus.get_history() == []


class TestDefaultSubscriptions:
    def test_default_subscriptions_has_modules(self):
        assert len(DEFAULT_SUBSCRIPTIONS) >= 7

    def test_abuseipdb_subscribes_to_ipv4(self):
        assert "ipv4-addr" in DEFAULT_SUBSCRIPTIONS["osint/abuseipdb"]

    def test_hibp_subscribes_to_email(self):
        assert "email-addr" in DEFAULT_SUBSCRIPTIONS["osint/hibp"]

    def test_urlscan_subscribes_to_url(self):
        assert "url" in DEFAULT_SUBSCRIPTIONS["osint/urlscan"]
