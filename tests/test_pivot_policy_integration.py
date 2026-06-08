"""Integration tests — quota-bomb scenario solved by PivotPolicy via EventBus.

@decision DEC-60-TEST-PIVOT-POLICY-INT-001
@title 5 integration tests reconstructing URLScan-fronted quota-bomb end-to-end
@status accepted
@rationale The quota-bomb bug (URLScan returning 15 CDN domains each triggering
           cascades) must be tested end-to-end through the real EventBus wiring
           path, not just via isolated PivotPolicy unit tests.  Mocked module
           callbacks are acceptable here because the external module I/O is not
           under test — the policy gate and budget enforcement are.  The five
           scenarios cover the full evaluation contract:
           (a) default config caps to ≤ max_per_cascade callbacks per source SCO;
           (b) total cascade ≤ max_per_session across a session;
           (c) dry-run produces full decision log with zero callback invocations;
           (d) pre-F60 baseline would fire all 15; post-F60 fires ≤ 5;
           (e) clear_history() resets session budget so a new source SCO gets
               fresh quota.

These tests exercise the compound production sequence:
    EventBus.process_results()
      -> PivotPolicy.evaluate() x N (once per result × subscriber)
      -> callback invocation (only on allow)
which is exactly the cascade path in tools.py run_module().

# @mock-exempt: Callbacks mock the external module hunt() boundary — real
# PursuitModule.hunt() calls make live network requests to Shodan/OTX/DNS.
# The integration under test is the EventBus + PivotPolicy gate wiring;
# the external service boundary is correctly mocked per CLAUDE.md §5.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from adversary_pursuit.core.config import AutoPivotPolicyConfig
from adversary_pursuit.core.event_bus import EventBus, PivotConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CDN_DOMAINS = [
    "cdn1.example-infra.net",
    "cdn2.example-infra.net",
    "cdn3.example-infra.net",
    "cdn4.example-infra.net",
    "cdn5.example-infra.net",
    "cdn6.example-infra.net",
    "cdn7.example-infra.net",
    "cdn8.example-infra.net",
    "cdn9.example-infra.net",
    "cdn10.example-infra.net",
    "cdn11.example-infra.net",
    "cdn12.example-infra.net",
    "cdn13.example-infra.net",
    "cdn14.example-infra.net",
    "cdn15.example-infra.net",
]

# Three subscriber modules for domain-name (models dns_resolve, whois_lookup, otx)
DOMAIN_MODULES = ["osint/dns_resolve", "osint/whois_lookup", "cti/otx"]


def make_bus(
    max_per_cascade: int = 5,
    max_per_session: int = 50,
    enabled: bool = True,
) -> tuple[EventBus, list[AsyncMock]]:
    """Return (bus, callbacks) with DOMAIN_MODULES subscribed for domain-name."""
    cfg = AutoPivotPolicyConfig(
        max_per_cascade=max_per_cascade,
        max_per_session=max_per_session,
        allowlist_path="/dev/null",
        denylist_path="/dev/null",
    )
    bus = EventBus(config=PivotConfig(enabled=enabled, policy=cfg))
    callbacks: list[AsyncMock] = []
    for mod in DOMAIN_MODULES:
        cb = AsyncMock(return_value=[])
        cb._module_path = mod  # tag for policy candidate_module lookup
        bus.subscribe("domain-name", cb)
        callbacks.append(cb)
    return bus, callbacks


def cdn_results() -> list[dict]:
    """Simulate URLScan returning 15 CDN domain results."""
    return [
        {"type": "domain-name", "value": d, "id": f"domain--{i}"} for i, d in enumerate(CDN_DOMAINS)
    ]


# ---------------------------------------------------------------------------
# Test (a): per-cascade budget caps callbacks for one source SCO
# ---------------------------------------------------------------------------


class TestPerCascadeBudget:
    def test_15_cdn_domains_capped_to_max_per_cascade(self):
        """URLScan 15-domain result fires ≤ max_per_cascade callbacks per module."""
        max_per_cascade = 5
        bus, callbacks = make_bus(max_per_cascade=max_per_cascade, max_per_session=1000)

        asyncio.run(bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0))

        # Each module should have been called at most max_per_cascade times
        for cb in callbacks:
            assert cb.call_count <= max_per_cascade, (
                f"Callback invoked {cb.call_count} times; expected ≤ {max_per_cascade}"
            )

    def test_total_callbacks_well_below_uncapped_45(self):
        """Post-F60 total invocations << 45 (15 CDN × 3 modules = uncapped baseline)."""
        bus, callbacks = make_bus(max_per_cascade=5, max_per_session=1000)

        asyncio.run(bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0))

        total = sum(cb.call_count for cb in callbacks)
        # With per-cascade=5 and 3 modules, max is 5×3=15, far below 45
        assert total <= 5 * len(DOMAIN_MODULES)
        # Sanity check that at least some callbacks fired (policy is not 0)
        assert total > 0


# ---------------------------------------------------------------------------
# Test (b): per-session budget caps total across cascades
# ---------------------------------------------------------------------------


class TestPerSessionBudget:
    def test_session_budget_limits_total_across_multiple_process_calls(self):
        """Total allowed callbacks across two process_results calls <= max_per_session."""
        max_per_session = 8
        bus, callbacks = make_bus(max_per_cascade=100, max_per_session=max_per_session)

        # First batch: 15 CDN domains
        asyncio.run(bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0))
        after_first = sum(cb.call_count for cb in callbacks)

        # Second batch: same 15 CDN domains again (different cascade, session accumulates)
        asyncio.run(bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0))
        after_second = sum(cb.call_count for cb in callbacks)

        assert after_second <= max_per_session, (
            f"Total session callbacks {after_second} exceeds max_per_session={max_per_session}"
        )
        # First batch alone should have used some quota
        assert after_first > 0


# ---------------------------------------------------------------------------
# Test (c): dry-run — full decision log, zero invocations
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_zero_callback_invocations(self):
        """dry_run=True: no callbacks invoked for any of 15 CDN domains."""
        bus, callbacks = make_bus(max_per_cascade=5, max_per_session=50)

        asyncio.run(
            bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0, dry_run=True)
        )

        for cb in callbacks:
            assert cb.call_count == 0

    def test_dry_run_produces_decision_log(self):
        """dry_run=True: decision log populated with entries for each candidate."""
        bus, _callbacks = make_bus(max_per_cascade=5, max_per_session=50)

        asyncio.run(
            bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0, dry_run=True)
        )

        log = bus.get_decision_log()
        # 15 CDN domains × 3 subscribers = 45 total decisions logged
        assert len(log) == len(CDN_DOMAINS) * len(DOMAIN_MODULES)

    def test_dry_run_log_has_correct_shape(self):
        """Each decision log entry has the 8 required keys (DEC-60-PIVOT-POLICY-005, DEC-M6-PIVOT-007).

        M-6 added 'dossier_weight' as the 8th key — always present in every entry,
        set to None when no ranker was supplied (pure F60 path).
        """
        bus, _callbacks = make_bus(max_per_cascade=5, max_per_session=50)

        asyncio.run(
            bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0, dry_run=True)
        )

        required_keys = {
            "source_sco_id",
            "source_sco_value",
            "candidate_module",
            "gate",
            "verdict",
            "reason",
            "depth",
            "dossier_weight",  # M-6 DEC-M6-PIVOT-007: always present; None when no ranker
        }
        log = bus.get_decision_log()
        assert log, "Decision log must be non-empty"
        for entry in log:
            assert set(entry.keys()) == required_keys, f"Missing keys in entry: {entry}"

    def test_dry_run_budget_counters_not_incremented(self):
        """dry_run=True: policy budget counters stay at 0 throughout."""
        bus, _callbacks = make_bus(max_per_cascade=5, max_per_session=50)

        asyncio.run(
            bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0, dry_run=True)
        )

        assert bus._policy._cascade_count == 0
        assert bus._policy._session_count == 0


# ---------------------------------------------------------------------------
# Test (e): session reset allows fresh quota for new cascades
# ---------------------------------------------------------------------------


class TestSessionReset:
    def test_clear_history_resets_session_quota(self):
        """After clear_history(), a new batch gets a fresh session budget."""
        max_per_session = 3
        bus, callbacks = make_bus(max_per_cascade=100, max_per_session=max_per_session)

        # First batch — exhausts session quota
        asyncio.run(bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0))
        first_total = sum(cb.call_count for cb in callbacks)
        assert first_total <= max_per_session

        # Reset session
        bus.clear_history()
        for cb in callbacks:
            cb.reset_mock()

        # Second batch — should get fresh quota
        asyncio.run(bus.process_results(cdn_results(), source_module="osint/urlscan", depth=0))
        second_total = sum(cb.call_count for cb in callbacks)
        # After reset, second batch should fire callbacks again (budget was replenished)
        assert second_total > 0
        assert second_total <= max_per_session
