"""Unit tests for core/pivot_policy.py — PivotPolicy three-gate engine.

@decision DEC-60-TEST-PIVOT-POLICY-001
@title 28 unit tests covering every gate rule; no mocks for internal logic
@status accepted
@rationale PivotPolicy is the sole gate authority (DEC-60-PIVOT-POLICY-001).
           Tests must exercise every gate rule directly, not through the EventBus,
           so failures are pinpointed to the gate not the bus wiring.  No mocks
           are used for PivotPolicy internals — real rule evaluation is the
           production path.  User-list tests write real temp files so the
           file-loading path is exercised end-to-end.

Coverage matrix (28 tests):
  Gate 1 — IOC value filter:
    RFC1918 IPv4 private addresses (10.x, 172.16.x, 192.168.x)
    Loopback IPv4 (127.x)
    Loopback IPv6 (::1)
    Link-local IPv4 (169.254.x)
    Link-local IPv6 (fe80::)
    RFC6761 special-use domain exact match
    RFC6761 special-use domain TLD match (.local, .test, .invalid)
    Top-1k static-deny domain exact match
    Public IP passes gate 1
    Public domain passes gate 1
    User-deny overrides user-allow
    User-allow short-circuits static deny
    Missing user files silently empty
  Gate 2 — Confidence:
    Score above threshold passes
    Score below threshold skips
    Score at threshold passes (boundary)
    Score one below threshold skips (boundary)
    Missing score OPTIMISTIC (default) passes
    Missing score PESSIMISTIC (registry entry) skips
    Non-numeric score OPTIMISTIC pass
  Gate 3 — Budget:
    Per-cascade budget exhaustion skips on N+1
    Per-session budget exhaustion skips on N+1
    Dry-run counters not incremented
    reset_cascade_budget resets per-cascade counter
    reset_session_budget resets both counters
  Gate ordering:
    IOC-value rejection short-circuits before confidence
    Confidence rejection short-circuits before budget
  Decision log / dry_run:
    build_log_entry produces all 7 required keys
    build_log_entry skip entry values correct
    build_log_entry allow entry values correct
"""

from __future__ import annotations

from adversary_pursuit.core.config import AutoPivotPolicyConfig
from adversary_pursuit.core.pivot_policy import PivotPolicy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_policy(
    *,
    confidence_threshold: int = 75,
    max_per_cascade: int = 5,
    max_per_session: int = 50,
    allowlist_path: str | None = "/dev/null",
    denylist_path: str | None = "/dev/null",
) -> PivotPolicy:
    """Build a PivotPolicy with controlled config.

    allowlist_path and denylist_path default to /dev/null so tests don't
    read ~/.ap/ files.
    """
    cfg = AutoPivotPolicyConfig(
        confidence_threshold=confidence_threshold,
        max_per_cascade=max_per_cascade,
        max_per_session=max_per_session,
        allowlist_path=allowlist_path,
        denylist_path=denylist_path,
    )
    return PivotPolicy(cfg)


def eval_ip(
    policy: PivotPolicy,
    value: str,
    sco_type: str = "ipv4-addr",
    source_module: str = "osint/abuseipdb",
    candidate_module: str = "osint/shodan_ip",
    sco_attrs: dict | None = None,
    depth: int = 0,
    dry_run: bool = False,
):
    return policy.evaluate(
        sco_type=sco_type,
        value=value,
        source_module=source_module,
        candidate_module=candidate_module,
        sco_attrs=sco_attrs,
        depth=depth,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Gate 1: IOC value filter — IP addresses
# ---------------------------------------------------------------------------


class TestGate1IPv4RFC1918:
    def test_10_block_skipped(self):
        p = make_policy()
        d = eval_ip(p, "10.0.0.1")
        assert d.verdict == "skip"
        assert d.gate == "ioc_value"
        assert "RFC1918" in d.reason

    def test_172_16_block_skipped(self):
        p = make_policy()
        d = eval_ip(p, "172.16.0.5")
        assert d.verdict == "skip"
        assert "RFC1918" in d.reason

    def test_192_168_block_skipped(self):
        p = make_policy()
        d = eval_ip(p, "192.168.1.100")
        assert d.verdict == "skip"
        assert "RFC1918" in d.reason

    def test_loopback_127_skipped(self):
        p = make_policy()
        d = eval_ip(p, "127.0.0.1")
        assert d.verdict == "skip"
        assert "loopback" in d.reason

    def test_loopback_ipv6_skipped(self):
        p = make_policy()
        d = eval_ip(p, "::1", sco_type="ipv6-addr")
        assert d.verdict == "skip"
        assert "loopback" in d.reason

    def test_link_local_169_254_skipped(self):
        p = make_policy()
        d = eval_ip(p, "169.254.0.1")
        assert d.verdict == "skip"
        assert "link-local" in d.reason

    def test_link_local_ipv6_fe80_skipped(self):
        p = make_policy()
        d = eval_ip(p, "fe80::1", sco_type="ipv6-addr")
        assert d.verdict == "skip"
        assert "link-local" in d.reason

    def test_public_ip_passes(self):
        p = make_policy()
        d = eval_ip(p, "1.2.3.4")
        assert d.verdict == "allow"


# ---------------------------------------------------------------------------
# Gate 1: IOC value filter — domains
# ---------------------------------------------------------------------------


class TestGate1Domains:
    def test_localhost_exact_skipped(self):
        p = make_policy()
        d = eval_ip(p, "localhost", sco_type="domain-name")
        assert d.verdict == "skip"
        assert d.gate == "ioc_value"

    def test_rfc6761_local_tld_skipped(self):
        p = make_policy()
        d = eval_ip(p, "mydevice.local", sco_type="domain-name")
        assert d.verdict == "skip"

    def test_rfc6761_test_tld_skipped(self):
        p = make_policy()
        d = eval_ip(p, "foo.test", sco_type="domain-name")
        assert d.verdict == "skip"

    def test_rfc6761_invalid_tld_skipped(self):
        p = make_policy()
        d = eval_ip(p, "host.invalid", sco_type="domain-name")
        assert d.verdict == "skip"

    def test_top1k_google_skipped(self):
        p = make_policy()
        d = eval_ip(p, "google.com", sco_type="domain-name")
        assert d.verdict == "skip"
        assert "top-1k" in d.reason

    def test_top1k_youtube_skipped(self):
        p = make_policy()
        d = eval_ip(p, "youtube.com", sco_type="domain-name")
        assert d.verdict == "skip"

    def test_unknown_domain_passes(self):
        p = make_policy()
        d = eval_ip(p, "evil-c2-domain.xyz", sco_type="domain-name")
        assert d.verdict == "allow"


# ---------------------------------------------------------------------------
# Gate 1: User allow / deny lists
# ---------------------------------------------------------------------------


class TestGate1UserLists:
    def test_user_deny_overrides_user_allow(self, tmp_path):
        """User deny list overrides user allow list (highest precedence)."""
        deny_file = tmp_path / "deny.txt"
        allow_file = tmp_path / "allow.txt"
        deny_file.write_text("1.2.3.4\n")
        allow_file.write_text("1.2.3.4\n")
        cfg = AutoPivotPolicyConfig(
            allowlist_path=str(allow_file),
            denylist_path=str(deny_file),
        )
        p = PivotPolicy(cfg)
        d = p.evaluate("ipv4-addr", "1.2.3.4", "m", "n")
        assert d.verdict == "skip"
        assert "user-deny" in d.reason

    def test_user_allow_overrides_static_deny(self, tmp_path):
        """User allow list permits an otherwise-top-1k-blocked domain."""
        allow_file = tmp_path / "allow.txt"
        deny_file = tmp_path / "deny.txt"
        allow_file.write_text("google.com\n")
        deny_file.write_text("")
        cfg = AutoPivotPolicyConfig(
            allowlist_path=str(allow_file),
            denylist_path=str(deny_file),
        )
        p = PivotPolicy(cfg)
        d = p.evaluate("domain-name", "google.com", "m", "n")
        assert d.verdict == "allow"

    def test_missing_user_files_treated_as_empty(self):
        """Non-existent user list files silently treated as empty."""
        cfg = AutoPivotPolicyConfig(
            allowlist_path="/nonexistent/allow.txt",
            denylist_path="/nonexistent/deny.txt",
        )
        p = PivotPolicy(cfg)
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
        assert d.verdict == "allow"


# ---------------------------------------------------------------------------
# Gate 2: Confidence
# ---------------------------------------------------------------------------


class TestGate2Confidence:
    def test_score_above_threshold_passes(self):
        p = make_policy(confidence_threshold=75)
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n", sco_attrs={"x_abuse_confidence_score": 80})
        assert d.verdict == "allow"

    def test_score_at_threshold_passes(self):
        p = make_policy(confidence_threshold=75)
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n", sco_attrs={"x_abuse_confidence_score": 75})
        assert d.verdict == "allow"

    def test_score_below_threshold_skips(self):
        p = make_policy(confidence_threshold=75)
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n", sco_attrs={"x_abuse_confidence_score": 50})
        assert d.verdict == "skip"
        assert d.gate == "confidence"
        assert "50" in d.reason

    def test_score_one_below_threshold_skips(self):
        p = make_policy(confidence_threshold=75)
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n", sco_attrs={"x_abuse_confidence_score": 74})
        assert d.verdict == "skip"

    def test_missing_score_optimistic_default(self):
        """Missing x_abuse_confidence_score -> OPTIMISTIC -> passes (DEC-60-PIVOT-POLICY-004)."""
        p = make_policy()
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n", sco_attrs={})
        assert d.verdict == "allow"

    def test_missing_score_pessimistic_registry(self):
        """Pessimistic registry entry skips when score is absent."""
        p = make_policy()
        p._missing_confidence_policy[("osint/abuseipdb", "ipv4-addr")] = "pessimistic"
        d = p.evaluate("ipv4-addr", "8.8.8.8", "osint/abuseipdb", "n", sco_attrs={})
        assert d.verdict == "skip"
        assert d.gate == "confidence"
        assert "pessimistic" in d.reason

    def test_non_numeric_score_optimistic(self):
        """Non-numeric score value -> optimistic pass (bad data must not block)."""
        p = make_policy()
        d = p.evaluate(
            "ipv4-addr",
            "8.8.8.8",
            "m",
            "n",
            sco_attrs={"x_abuse_confidence_score": "not-a-number"},
        )
        assert d.verdict == "allow"


# ---------------------------------------------------------------------------
# Gate 3: Budget
# ---------------------------------------------------------------------------


class TestGate3Budget:
    def test_per_cascade_budget_exhausted_skips(self):
        """The (max_per_cascade + 1)th call in one cascade is skipped."""
        p = make_policy(max_per_cascade=3, max_per_session=100)
        for _ in range(3):
            d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
            assert d.verdict == "allow"
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
        assert d.verdict == "skip"
        assert d.gate == "budget"
        assert "per-cascade" in d.reason

    def test_per_session_budget_exhausted_skips(self):
        """The (max_per_session + 1)th call across resets is skipped."""
        p = make_policy(max_per_cascade=100, max_per_session=3)
        for _ in range(3):
            d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
            assert d.verdict == "allow"
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
        assert d.verdict == "skip"
        assert d.gate == "budget"
        assert "per-session" in d.reason

    def test_dry_run_does_not_increment_counters(self):
        """dry_run=True: policy evaluated but counters not incremented."""
        p = make_policy(max_per_cascade=3, max_per_session=100)
        for _ in range(10):
            d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n", dry_run=True)
            assert d.verdict == "allow"
        assert p._cascade_count == 0
        assert p._session_count == 0

    def test_reset_cascade_budget(self):
        """reset_cascade_budget resets per-cascade counter to 0, preserves session."""
        p = make_policy(max_per_cascade=2, max_per_session=100)
        p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
        p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
        assert p._cascade_count == 2
        p.reset_cascade_budget()
        assert p._cascade_count == 0
        assert p._session_count == 2  # preserved

    def test_reset_session_budget(self):
        """reset_session_budget resets both cascade and session counters."""
        p = make_policy(max_per_cascade=10, max_per_session=100)
        for _ in range(5):
            p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
        assert p._cascade_count == 5
        assert p._session_count == 5
        p.reset_session_budget()
        assert p._cascade_count == 0
        assert p._session_count == 0


# ---------------------------------------------------------------------------
# Gate ordering — short-circuit semantics
# ---------------------------------------------------------------------------


class TestGateOrdering:
    def test_ioc_value_short_circuits_confidence(self):
        """RFC1918 IP rejected at gate 1; confidence gate never consulted."""
        p = make_policy(confidence_threshold=0)  # would pass confidence if reached
        d = p.evaluate(
            "ipv4-addr",
            "192.168.1.1",
            "m",
            "n",
            sco_attrs={"x_abuse_confidence_score": 100},
        )
        assert d.verdict == "skip"
        assert d.gate == "ioc_value"

    def test_confidence_short_circuits_budget(self):
        """Low-confidence result rejected at gate 2; budget counter not charged."""
        p = make_policy(confidence_threshold=75, max_per_cascade=5)
        d = p.evaluate(
            "ipv4-addr",
            "8.8.8.8",
            "m",
            "n",
            sco_attrs={"x_abuse_confidence_score": 10},
        )
        assert d.verdict == "skip"
        assert d.gate == "confidence"
        assert p._cascade_count == 0


# ---------------------------------------------------------------------------
# Decision log shape and build_log_entry
# ---------------------------------------------------------------------------


class TestDecisionLog:
    def test_build_log_entry_has_all_seven_keys(self):
        """DecisionLogEntry TypedDict has all 7 required keys (DEC-60-PIVOT-POLICY-005)."""
        p = make_policy()
        d = p.evaluate("ipv4-addr", "8.8.8.8", "osint/urlscan", "osint/shodan_ip")
        entry = p.build_log_entry(
            sco_id="indicator--1234",
            value="8.8.8.8",
            candidate_module="osint/shodan_ip",
            decision=d,
            depth=1,
        )
        required_keys = {
            "source_sco_id",
            "source_sco_value",
            "candidate_module",
            "gate",
            "verdict",
            "reason",
            "depth",
        }
        assert set(entry.keys()) == required_keys

    def test_build_log_entry_skip_values_correct(self):
        """Log entry for skipped RFC1918 IP captures correct verdict and gate."""
        p = make_policy()
        d = p.evaluate("ipv4-addr", "10.0.0.1", "m", "n")
        entry = p.build_log_entry("id-1", "10.0.0.1", "n", d, depth=0)
        assert entry["verdict"] == "skip"
        assert entry["gate"] == "ioc_value"
        assert entry["source_sco_value"] == "10.0.0.1"
        assert entry["depth"] == 0

    def test_build_log_entry_allow_values_correct(self):
        """Log entry for an allowed public IP captures correct verdict."""
        p = make_policy()
        d = p.evaluate("ipv4-addr", "8.8.8.8", "m", "n")
        entry = p.build_log_entry("id-2", "8.8.8.8", "n", d, depth=2)
        assert entry["verdict"] == "allow"
        assert entry["gate"] == "allow"
        assert entry["depth"] == 2
