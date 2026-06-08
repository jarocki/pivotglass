"""Tests for Issue #19: Event Bus (Auto-Pivot).

@decision DEC-TEST-EVENTBUS-001
@title Tests cover pub/sub, policy-gated publishing, whitelist, and process_results
@status accepted
@rationale The event bus is safety-critical (policy gate prevents quota-bomb,
           whitelist prevents API quota burn). Every safety mechanism must be
           tested.  Post-F60: max_depth is removed; PivotPolicy is the sole gate
           authority (DEC-60-PIVOT-POLICY-001, DEC-60-PIVOT-POLICY-006).
           TestPolicyAuthority verifies that max_depth is absent from PivotConfig
           and that publish() contains no inline gate logic beyond the enabled
           short-circuit and the policy call.

# @mock-exempt: AsyncMock callbacks simulate external module hunt() boundaries
# (real Shodan/OTX/DNS HTTP calls). Policy gate tests are the target; external
# service I/O is correctly mocked per CLAUDE.md §5.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock

import pytest

from adversary_pursuit.core.config import AutoPivotPolicyConfig
from adversary_pursuit.core.event_bus import (
    DEFAULT_SUBSCRIPTIONS,
    EventBus,
    PivotConfig,
    PivotEvent,
)
from adversary_pursuit.core.pivot_policy import PivotPolicy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus():
    """EventBus with policy that allows all public IPs (permissive config)."""
    cfg = AutoPivotPolicyConfig(
        max_per_cascade=100,
        max_per_session=10000,
        allowlist_path="/dev/null",
        denylist_path="/dev/null",
    )
    return EventBus(PivotConfig(enabled=True, policy=cfg))


@pytest.fixture
def disabled_bus():
    return EventBus(PivotConfig(enabled=False))


# ---------------------------------------------------------------------------
# PivotEvent
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PivotConfig
# ---------------------------------------------------------------------------


class TestPivotConfig:
    def test_defaults(self):
        c = PivotConfig()
        assert c.enabled is False
        assert c.module_whitelist == []

    def test_no_max_depth_field(self):
        """PivotConfig must not have a max_depth field (DEC-60-PIVOT-POLICY-006)."""
        c = PivotConfig()
        assert not hasattr(c, "max_depth"), (
            "max_depth was removed in F60 — flow control belongs to PivotPolicy budgets"
        )

    def test_policy_field_is_auto_pivot_policy_config(self):
        """PivotConfig.policy is an AutoPivotPolicyConfig instance (DEC-60-PIVOT-POLICY-001)."""
        c = PivotConfig()
        assert isinstance(c.policy, AutoPivotPolicyConfig)


# ---------------------------------------------------------------------------
# Policy Authority — DEC-60-PIVOT-POLICY-001
# ---------------------------------------------------------------------------


class TestPolicyAuthority:
    def test_event_bus_has_policy_attribute(self):
        """EventBus must carry a _policy PivotPolicy instance (DEC-60-PIVOT-POLICY-001)."""
        cfg = AutoPivotPolicyConfig(allowlist_path="/dev/null", denylist_path="/dev/null")
        b = EventBus(config=PivotConfig(enabled=True, policy=cfg))
        assert hasattr(b, "_policy")
        assert isinstance(b._policy, PivotPolicy)

    def test_publish_source_has_no_inline_depth_gate(self):
        """publish() source must not contain inline depth-gate logic (DEC-60-PIVOT-POLICY-006).

        Inspect the source of EventBus.publish to confirm max_depth is absent.
        This test will fail if an implementer re-introduces the pre-F60 depth
        check inline in publish(), which would create two gate authorities.
        """
        source = inspect.getsource(EventBus.publish)
        assert "max_depth" not in source, (
            "max_depth found inline in EventBus.publish — "
            "flow control must live in PivotPolicy (DEC-60-PIVOT-POLICY-006)"
        )

    def test_rfc1918_ip_blocked_by_policy_not_depth(self):
        """RFC1918 IP is skipped by PivotPolicy gate 1 (ioc_value), not by depth."""
        cfg = AutoPivotPolicyConfig(allowlist_path="/dev/null", denylist_path="/dev/null")
        b = EventBus(config=PivotConfig(enabled=True, policy=cfg))
        cb = AsyncMock(return_value=[])
        cb._module_path = "osint/abuseipdb"
        b.subscribe("ipv4-addr", cb)

        event = PivotEvent("ipv4-addr", "10.0.0.1", "test", depth=0)
        asyncio.run(b.publish(event))

        cb.assert_not_called()  # policy gate rejected it

    def test_clear_history_also_resets_policy_budget(self):
        """clear_history() resets policy session budget via PivotPolicy.reset_session_budget()."""
        cfg = AutoPivotPolicyConfig(
            max_per_cascade=2,
            max_per_session=2,
            allowlist_path="/dev/null",
            denylist_path="/dev/null",
        )
        b = EventBus(config=PivotConfig(enabled=True, policy=cfg))
        cb = AsyncMock(return_value=[])
        cb._module_path = "osint/abuseipdb"
        b.subscribe("ipv4-addr", cb)

        # Exhaust budget
        for _ in range(2):
            asyncio.run(b.publish(PivotEvent("ipv4-addr", "8.8.8.8", "test", depth=0)))
        # Budget exhausted — this should be skipped
        asyncio.run(b.publish(PivotEvent("ipv4-addr", "8.8.8.8", "test", depth=0)))
        assert cb.call_count == 2

        # Reset
        b.clear_history()
        assert b._policy._session_count == 0

        # Budget restored — callback should fire again
        asyncio.run(b.publish(PivotEvent("ipv4-addr", "8.8.8.8", "test", depth=0)))
        assert cb.call_count == 3


# ---------------------------------------------------------------------------
# Subscribe / Unsubscribe
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------


class TestPublish:
    def test_publish_triggers_callback(self, bus):
        cb = AsyncMock(return_value=[{"type": "domain-name", "value": "evil.com"}])
        cb._module_path = "test"
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

    def test_publish_records_history(self, bus):
        bus.subscribe("ipv4-addr", AsyncMock(return_value=[]))
        event = PivotEvent("ipv4-addr", "1.2.3.4", "test")
        asyncio.run(bus.publish(event))
        assert len(bus.get_history()) == 1

    def test_publish_callback_error_continues(self, bus):
        bad_cb = AsyncMock(side_effect=Exception("boom"))
        bad_cb._module_path = "bad"
        good_cb = AsyncMock(return_value=[{"type": "ok"}])
        good_cb._module_path = "good"
        bus.subscribe("ipv4-addr", bad_cb)
        bus.subscribe("ipv4-addr", good_cb)
        event = PivotEvent("ipv4-addr", "1.2.3.4", "test")
        results = asyncio.run(bus.publish(event))
        assert len(results) == 1

    def test_publish_no_subscribers(self, bus):
        event = PivotEvent("email-addr", "x@y.com", "test")
        results = asyncio.run(bus.publish(event))
        assert results == []


# ---------------------------------------------------------------------------
# ProcessResults
# ---------------------------------------------------------------------------


class TestProcessResults:
    def test_process_creates_events(self, bus):
        cb = AsyncMock(return_value=[])
        cb._module_path = "osint/dns_resolve"
        bus.subscribe("ipv4-addr", cb)
        results = [{"type": "ipv4-addr", "value": "1.2.3.4"}]
        asyncio.run(bus.process_results(results, "osint/dns_resolve"))
        assert cb.call_count == 1

    def test_process_increments_depth(self, bus):
        cb = AsyncMock(return_value=[])
        cb._module_path = "osint/dns_resolve"
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


# ---------------------------------------------------------------------------
# Module Registration
# ---------------------------------------------------------------------------


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

    def test_register_tags_callback_with_module_path(self, bus):
        """register_module_subscriptions tags callback with _module_path for policy lookup."""
        cb = AsyncMock()
        bus.register_module_subscriptions("osint/abuseipdb", ["ipv4-addr"], cb)
        assert cb._module_path == "osint/abuseipdb"


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class TestHistory:
    def test_empty_history(self, bus):
        assert bus.get_history() == []

    def test_clear_history(self, bus):
        bus.subscribe("ipv4-addr", AsyncMock(return_value=[]))
        asyncio.run(bus.publish(PivotEvent("ipv4-addr", "1.2.3.4", "test")))
        bus.clear_history()
        assert bus.get_history() == []

    def test_clear_history_also_clears_decision_log(self, bus):
        """clear_history() clears the decision log too."""
        cb = AsyncMock(return_value=[])
        cb._module_path = "test"
        bus.subscribe("ipv4-addr", cb)
        asyncio.run(bus.publish(PivotEvent("ipv4-addr", "1.2.3.4", "test")))
        assert len(bus.get_decision_log()) > 0
        bus.clear_history()
        assert bus.get_decision_log() == []


# ---------------------------------------------------------------------------
# Default Subscriptions
# ---------------------------------------------------------------------------


class TestDefaultSubscriptions:
    def test_default_subscriptions_has_modules(self):
        assert len(DEFAULT_SUBSCRIPTIONS) >= 7

    def test_abuseipdb_subscribes_to_ipv4(self):
        assert "ipv4-addr" in DEFAULT_SUBSCRIPTIONS["osint/abuseipdb"]

    def test_hibp_subscribes_to_email(self):
        assert "email-addr" in DEFAULT_SUBSCRIPTIONS["osint/hibp"]

    def test_urlscan_subscribes_to_url(self):
        assert "url" in DEFAULT_SUBSCRIPTIONS["osint/urlscan"]


# ---------------------------------------------------------------------------
# M-6 regression: process_results ranker kwarg is optional (F60 compat)
# ---------------------------------------------------------------------------


class TestProcessResultsRankerKwargOptional:
    """Regression: new ranker kwarg must be optional and must not shift positional signature."""

    def test_process_results_no_ranker_kwarg_is_f60_identical(self, bus):
        """process_results called with pre-M-6 positional signature is byte-identical to F60."""
        fired = []

        async def _cb(event):
            fired.append(event.value)
            return []

        _cb._module_path = "test/ipv4"
        bus.subscribe("ipv4-addr", _cb)

        results = [
            {"type": "ipv4-addr", "value": "5.5.5.5"},
            {"type": "ipv4-addr", "value": "6.6.6.6"},
        ]
        # Pre-M-6 positional call: no ranker kwarg, no keyword arguments at all
        asyncio.run(bus.process_results(results, "test/mod", 0))
        assert fired == ["5.5.5.5", "6.6.6.6"]

    def test_process_results_ranker_none_kwarg_is_f60_identical(self, bus):
        """Explicit ranker=None is byte-identical to the pre-M-6 call."""
        fired = []

        async def _cb(event):
            fired.append(event.value)
            return []

        _cb._module_path = "test/ipv4"
        bus.subscribe("ipv4-addr", _cb)

        results = [
            {"type": "ipv4-addr", "value": "7.7.7.7"},
            {"type": "ipv4-addr", "value": "8.8.8.8"},
        ]
        asyncio.run(bus.process_results(results, "test/mod", ranker=None))
        assert fired == ["7.7.7.7", "8.8.8.8"]
