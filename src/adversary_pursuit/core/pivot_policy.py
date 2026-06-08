"""Pivot policy engine — IOC filter, confidence gate, and per-cascade/session budgets.

This module is the SOLE gate authority for auto-pivot decisions in the event bus.
``PivotPolicy.evaluate`` is called by ``EventBus.publish`` before invoking any
subscribed callback.  No inline conditionals in ``publish`` may replicate the gate
logic: see DEC-60-PIVOT-POLICY-001.

@decision DEC-60-PIVOT-POLICY-001
@title PivotPolicy.evaluate is the sole gate authority consulted by EventBus.publish
@status accepted
@rationale Single-source-of-truth (CLAUDE.md §12).  If gates lived inline in publish
           AND in a policy module, two authorities would silently diverge: a future
           implementer adding a new gate would have to remember to update both paths.
           The architecture rule (CLAUDE.md "Encode authority, don't imply it") is
           satisfied by a single explicit authority.  Tests assert that publish
           contains no inline gate conditionals other than the enabled short-circuit
           and the policy call.

@decision DEC-60-PIVOT-POLICY-002
@title Three-gate ordering: ioc_value → confidence → budget (strict, short-circuit)
@status accepted
@rationale Cheapest and most definitive filter goes first.  IOC-value rejection
           (RFC1918, RFC6761, top-1k) is entirely local/offline and eliminates the
           largest class of low-value pivots before any I/O occurs.  Confidence
           rejection comes second — it's also offline (reads sco_attrs) but applies
           only when the IOC passed the value filter.  Budget is the most
           context-sensitive filter and goes last: it depends on mutable session
           state that is irrelevant if the indicator was already rejected by value
           or confidence.  Short-circuiting at each gate means budget counters are
           never charged for filtered-out indicators.

@decision DEC-60-PIVOT-POLICY-003
@title Bundled top-1k allowlist ships as data/pivot_allowlist_top1k.txt; source is
       Cloudflare Radar top-1k (snapshot date: 2026-05-01); top-1k chosen over
       top-10k for bundle-size tradeoff
@status accepted
@rationale Bundled data over network fetch: determinism (offline-correct), no
           first-run network dependency, no rate-limit risk during testing,
           version-controlled (reviewable in git).  Source: Cloudflare Radar
           publishes a free, redistribution-friendly top-1k.  Alexa's top-1k was
           retired in May 2022; using a current maintained source matters.
           Size choice: top-1k ~25 KB packed; top-10k ~250 KB and would denylist
           many medium-popularity sites with legitimate pivot value (niche CDNs,
           lesser-known infra).  Refreshed once per minor release via a separate
           maintenance slice (out-of-scope for F60).
           File SHA-256: computed at runtime in _load_static_rules.

@decision DEC-60-PIVOT-POLICY-004
@title Per-SCO-type missing-confidence policy: OPTIMISTIC by default (pass), user-
       overridable to PESSIMISTIC (skip) via _missing_confidence_policy registry
@status accepted
@rationale Many legitimate CTI feeds do not populate x_abuse_confidence_score on
           every object.  Rejecting on absence would cascade-filter almost every
           result from modules that don't score indicators.  OPTIMISTIC default
           preserves the pre-F60 behaviour (any pivot was allowed).  PESSIMISTIC
           is an opt-in override for analysts who want stricter confidence gating
           on specific (source_module, sco_type) combinations.  The registry is an
           empty dict by default: no overrides.  Tests assert that an empty registry
           results in OPTIMISTIC behaviour for all (source, sco_type) pairs.

@decision DEC-60-PIVOT-POLICY-005
@title Dry-run mode is a kwarg on evaluate() and process_results(); returned
       decision_log entries carry a typed DecisionLogEntry TypedDict
@status accepted
@rationale Explicit-kwarg threading over global flag: tests can run dry and
           non-dry side-by-side; agents that want to "preview" don't have to
           mutate global state.  The decision-log shape is the contract — seven
           required keys — so downstream consumers (agent LLM surfacing, future
           Rich-table renderers, future audit logs) have a stable structure.

@decision DEC-60-PIVOT-POLICY-006
@title max_depth REMOVED from PivotConfig; per-cascade + per-session budgets are the
       sole flow-control; auto_pivot_depth field retained in GeneralConfig for
       backward-compatible TOML round-trip only (not consulted by F60+ code)
@status accepted
@rationale max_depth=2 (the pre-F60 cascade stopper) was a blunt instrument that
           stopped cascade at depth 2 regardless of the number of pivots at each
           depth.  A URLScan result with 15 CDN domains could fire 15 callbacks at
           depth 1 alone, each firing up to 15 more at depth 2 — 225 API calls.
           Per-cascade budget (default 5) caps callbacks per single source SCO
           invocation; per-session budget (default 50) caps the session total.
           Two independent budgets are preferable to one depth limit because they
           address different failure modes: per-cascade prevents individual
           "exploding" SCOs; per-session prevents accumulated drift.  max_depth
           offered neither guarantee once a single SCO produced many indicators.

@decision DEC-60-PIVOT-POLICY-007
@title User allowlist / denylist paths default to ~/.ap/pivot-allowlist.txt and
       ~/.ap/pivot-denylist.txt; missing files are silently treated as empty
@status accepted
@rationale Config stores optional paths; None means "use default location".
           Silent empty-file fall-through means: (a) first-run works without the
           user creating files; (b) CI/CD environments without ~/.ap/ don't fail.
           Precedence order is: user_deny > user_allow > static_deny > static_allow
           > default_allow.  The static allow (top-1k) is a DENY for pivoting:
           "this domain is too popular to be useful as a pivot target" — so
           "static_allow" in the precedence chain refers to the allowlist of
           domains-that-are-blocked-from-pivoting, i.e. the top-1k list.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal, TypedDict

from adversary_pursuit.core.config import AutoPivotPolicyConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RFC-reserved IP ranges that are never useful pivot targets
# ---------------------------------------------------------------------------

# RFC 1918 private ranges (IPv4)
_RFC1918_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]

# RFC 6761 special-use domains (IANA special-use registry)
# https://www.iana.org/assignments/special-use-domain-names/
_RFC6761_DOMAINS: frozenset[str] = frozenset(
    [
        "localhost",
        "local",
        "example",
        "example.com",
        "example.net",
        "example.org",
        "invalid",
        "test",
        "internal",
    ]
)

# Loopback ranges (IPv4 + IPv6)
_LOOPBACK_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]

# Link-local ranges
_LINK_LOCAL_NETS = [
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


# ---------------------------------------------------------------------------
# Type definitions
# ---------------------------------------------------------------------------


class DecisionLogEntry(TypedDict, total=False):
    """Typed contract for a single pivot-policy decision record.

    Seven keys are required (source_sco_id, source_sco_value, candidate_module,
    gate, verdict, reason, depth).  One optional diagnostic field is added by M-6:

    dossier_weight (float | None):
        The slot-fill score computed by the M-6 dossier-aware ranker for this SCO,
        or None when the ranker was not supplied to process_results.  Populated by
        EventBus.publish after build_log_entry() returns the base entry.  Additive-
        optional: existing consumers that only read the seven required keys see no
        breaking change.  (DEC-M6-PIVOT-007)

    (DEC-60-PIVOT-POLICY-005)
    """

    # Required keys — always present
    source_sco_id: str
    source_sco_value: str
    candidate_module: str
    gate: str
    verdict: Literal["allow", "skip"]
    reason: str
    depth: int
    # Optional M-6 diagnostic field (DEC-M6-PIVOT-007)
    dossier_weight: float | None


@dataclass
class PolicyDecision:
    """Result of a single PivotPolicy.evaluate() call.

    ``verdict``  : "allow" if the pivot should proceed, "skip" if not.
    ``gate``     : which gate produced the decision ("ioc_value",
                   "confidence", "budget", or "allow").
    ``reason``   : human-readable rationale string.
    """

    verdict: Literal["allow", "skip"]
    gate: str
    reason: str


# ---------------------------------------------------------------------------
# PivotPolicy
# ---------------------------------------------------------------------------


class PivotPolicy:
    """Three-gate pivot policy engine.

    Gate order (DEC-60-PIVOT-POLICY-002):
        1. ioc_value   — RFC1918 / RFC6761 / loopback / link-local / top-1k check.
        2. confidence  — x_abuse_confidence_score threshold; missing-field policy.
        3. budget      — per-cascade + per-session counters.

    Parameters
    ----------
    policy_config:
        ``AutoPivotPolicyConfig`` instance read from ``GeneralConfig.auto_pivot_policy``
        (DEC-60-PIVOT-POLICY-CONFIG-001).  Loaded once on construction; not re-read.

    Notes
    -----
    The class is intentionally stateless across calls except for the mutable budget
    counters ``_cascade_count`` and ``_session_count``.  Session budget is reset by
    ``reset_session_budget()`` (called from ``EventBus.clear_history()``).  Cascade
    budget is reset by ``reset_cascade_budget()`` (called from
    ``EventBus.process_results()`` at the start of each source-SCO processing loop).
    """

    def __init__(self, policy_config: AutoPivotPolicyConfig) -> None:
        self._cfg = policy_config
        self._static_deny_domains: frozenset[str] = frozenset()
        self._user_allow_domains: frozenset[str] = frozenset()
        self._user_deny_domains: frozenset[str] = frozenset()

        # Per-(source_module, sco_type) missing-confidence policy override.
        # Empty by default → OPTIMISTIC for all pairs (DEC-60-PIVOT-POLICY-004).
        self._missing_confidence_policy: dict[
            tuple[str, str], Literal["optimistic", "pessimistic"]
        ] = {}

        # Mutable budget counters
        self._cascade_count: int = 0
        self._session_count: int = 0

        self._load_static_rules()
        self._load_user_lists()

    # ------------------------------------------------------------------
    # Loader helpers
    # ------------------------------------------------------------------

    def _load_static_rules(self) -> None:
        """Load the bundled top-1k static deny-for-pivoting list.

        The file ships as ``src/adversary_pursuit/data/pivot_allowlist_top1k.txt``.
        Any IOError falls through to an empty set so offline / restricted
        environments don't hard-fail (DEC-60-PIVOT-POLICY-007).
        """
        try:
            ref = resources.files("adversary_pursuit.data").joinpath("pivot_allowlist_top1k.txt")
            content = ref.read_text(encoding="utf-8")
            domains: list[str] = []
            sha_input_lines: list[str] = []
            for line in content.splitlines():
                stripped = line.strip().lower()
                if stripped and not stripped.startswith("#"):
                    domains.append(stripped)
                    sha_input_lines.append(stripped)
            self._static_deny_domains = frozenset(domains)
            # Record SHA-256 for provenance (DEC-60-PIVOT-POLICY-003)
            body = "\n".join(sha_input_lines).encode()
            self._static_list_sha256 = hashlib.sha256(body).hexdigest()
            logger.debug(
                "Loaded %d static-deny domains (SHA-256: %s)",
                len(self._static_deny_domains),
                self._static_list_sha256,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pivot_policy: could not load static deny list: %s", exc)
            self._static_deny_domains = frozenset()
            self._static_list_sha256 = ""

    def _load_user_lists(self) -> None:
        """Load user-supplied allow and deny lists (DEC-60-PIVOT-POLICY-007).

        Default paths: ``~/.ap/pivot-allowlist.txt`` and ``~/.ap/pivot-denylist.txt``.
        Missing files are silently treated as empty.
        """
        allow_path = (
            Path(self._cfg.allowlist_path)
            if self._cfg.allowlist_path
            else Path.home() / ".ap" / "pivot-allowlist.txt"
        )
        deny_path = (
            Path(self._cfg.denylist_path)
            if self._cfg.denylist_path
            else Path.home() / ".ap" / "pivot-denylist.txt"
        )
        self._user_allow_domains = self._read_list_file(allow_path, "user-allow")
        self._user_deny_domains = self._read_list_file(deny_path, "user-deny")

    @staticmethod
    def _read_list_file(path: Path, label: str) -> frozenset[str]:
        """Read a plain-text domain list; return frozenset (empty on any error)."""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            domains = frozenset(
                line.strip().lower()
                for line in lines
                if line.strip() and not line.strip().startswith("#")
            )
            logger.debug("Loaded %d %s domains from %s", len(domains), label, path)
            return domains
        except FileNotFoundError:
            return frozenset()
        except Exception as exc:  # noqa: BLE001
            logger.warning("pivot_policy: could not read %s list at %s: %s", label, path, exc)
            return frozenset()

    # ------------------------------------------------------------------
    # Budget management
    # ------------------------------------------------------------------

    def reset_cascade_budget(self) -> None:
        """Reset the per-cascade counter (called once per source SCO by EventBus)."""
        self._cascade_count = 0

    def reset_session_budget(self) -> None:
        """Reset both per-cascade and per-session counters (called by clear_history())."""
        self._cascade_count = 0
        self._session_count = 0

    # ------------------------------------------------------------------
    # Gate implementations
    # ------------------------------------------------------------------

    def _evaluate_ioc_value(self, sco_type: str, value: str) -> PolicyDecision | None:
        """Gate 1: filter out indicators with no pivot value (DEC-60-PIVOT-POLICY-001).

        Returns a SKIP PolicyDecision if the indicator should be filtered, else None.

        Precedence order (DEC-60-PIVOT-POLICY-007):
            user_deny > user_allow > static_deny > static_allow > default_allow

        Here:
            - user_deny (skip)        : value in user denylist
            - user_allow (continue)   : value in user allowlist → skip this gate → proceed
            - static_deny (skip)      : IPv4 RFC1918 / loopback / link-local, or top-1k domain
            - default_allow (continue): everything else passes
        """
        # Normalise for lookup
        v = value.strip().lower()

        # --- IP address checks ---
        if sco_type in ("ipv4-addr", "ipv6-addr"):
            try:
                addr = ipaddress.ip_address(v)
            except ValueError:
                pass  # not a valid IP — fall through to domain checks
            else:
                # User deny overrides all
                if v in self._user_deny_domains:
                    return PolicyDecision("skip", "ioc_value", f"user-deny: {v}")
                # User allow short-circuits static filters
                if v in self._user_allow_domains:
                    return None
                # RFC1918 private
                for net in _RFC1918_NETS:
                    if isinstance(addr, ipaddress.IPv4Address) and addr in net:
                        return PolicyDecision("skip", "ioc_value", f"RFC1918 private address: {v}")
                # Loopback
                for net in _LOOPBACK_NETS:
                    if addr in net:
                        return PolicyDecision("skip", "ioc_value", f"loopback address: {v}")
                # Link-local
                for net in _LINK_LOCAL_NETS:
                    if addr in net:
                        return PolicyDecision("skip", "ioc_value", f"link-local address: {v}")
                return None

        # --- Domain checks ---
        if sco_type == "domain-name":
            # User deny overrides all
            if v in self._user_deny_domains:
                return PolicyDecision("skip", "ioc_value", f"user-deny: {v}")
            # User allow short-circuits static filters
            if v in self._user_allow_domains:
                return None
            # RFC6761 special-use (exact match on TLD or full FQDN)
            if v in _RFC6761_DOMAINS or v.rstrip(".").split(".")[-1] in _RFC6761_DOMAINS:
                return PolicyDecision("skip", "ioc_value", f"RFC6761 special-use domain: {v}")
            # localhost (also matches localhost.* hostnames)
            if v == "localhost" or v.startswith("localhost."):
                return PolicyDecision("skip", "ioc_value", f"loopback hostname: {v}")
            # Static deny (top-1k popular domains)
            if v in self._static_deny_domains:
                return PolicyDecision("skip", "ioc_value", f"top-1k popular domain: {v}")
            return None

        # Other STIX types: user-level deny/allow only
        if v in self._user_deny_domains:
            return PolicyDecision("skip", "ioc_value", f"user-deny: {v}")
        if v in self._user_allow_domains:
            return None

        return None

    def _evaluate_confidence(
        self,
        source_module: str,
        sco_type: str,
        sco_attrs: dict,
    ) -> PolicyDecision | None:
        """Gate 2: confidence threshold filter (DEC-60-PIVOT-POLICY-004).

        Returns a SKIP PolicyDecision if the indicator fails confidence gating, else None.

        Behaviour when ``x_abuse_confidence_score`` is absent:
            - Consult ``_missing_confidence_policy[(source_module, sco_type)]``
            - Empty registry / key absent → OPTIMISTIC → passes (returns None)
            - Key present with "pessimistic" → SKIP
        """
        score = sco_attrs.get("x_abuse_confidence_score")
        if score is None:
            # Missing field: check per-(source, sco_type) policy
            policy = self._missing_confidence_policy.get((source_module, sco_type), "optimistic")
            if policy == "pessimistic":
                return PolicyDecision(
                    "skip",
                    "confidence",
                    f"missing x_abuse_confidence_score; pessimistic policy for "
                    f"({source_module!r}, {sco_type!r})",
                )
            return None  # optimistic: pass

        try:
            score_int = int(score)
        except (TypeError, ValueError):
            # Non-numeric score — treat as optimistic pass (don't reject on bad data)
            logger.debug(
                "pivot_policy: non-numeric x_abuse_confidence_score %r; passing (optimistic)",
                score,
            )
            return None

        if score_int < self._cfg.confidence_threshold:
            return PolicyDecision(
                "skip",
                "confidence",
                f"x_abuse_confidence_score {score_int} < threshold {self._cfg.confidence_threshold}",
            )
        return None

    def _evaluate_budget(self) -> PolicyDecision | None:
        """Gate 3: per-cascade and per-session budget check (DEC-60-PIVOT-POLICY-006).

        Returns a SKIP PolicyDecision if a budget is exhausted, else None.
        Does NOT increment counters — counters are incremented by the caller on ALLOW.
        """
        if self._cascade_count >= self._cfg.max_per_cascade:
            return PolicyDecision(
                "skip",
                "budget",
                f"per-cascade budget exhausted: {self._cascade_count}/{self._cfg.max_per_cascade}",
            )
        if self._session_count >= self._cfg.max_per_session:
            return PolicyDecision(
                "skip",
                "budget",
                f"per-session budget exhausted: {self._session_count}/{self._cfg.max_per_session}",
            )
        return None

    # ------------------------------------------------------------------
    # Public evaluation entry point
    # ------------------------------------------------------------------

    def evaluate(
        self,
        sco_type: str,
        value: str,
        source_module: str,
        candidate_module: str,
        sco_attrs: dict | None = None,
        depth: int = 0,
        *,
        dry_run: bool = False,
        sco_id: str = "",
    ) -> PolicyDecision:
        """Evaluate whether a candidate pivot should proceed.

        Gates are applied in strict order (DEC-60-PIVOT-POLICY-002).  The first
        SKIP result short-circuits evaluation; no later gates are consulted.
        On ALLOW, the per-cascade and per-session counters are incremented unless
        ``dry_run=True``.

        Parameters
        ----------
        sco_type:
            STIX SCO type, e.g. ``"ipv4-addr"``, ``"domain-name"``, ``"url"``.
        value:
            The string value of the SCO to evaluate (IP, domain, URL, etc.).
        source_module:
            Module that produced the SCO (e.g. ``"osint/urlscan"``).
        candidate_module:
            Module that would be triggered on this pivot (e.g. ``"osint/shodan_ip"``).
        sco_attrs:
            Optional dict of SCO attributes; used for ``x_abuse_confidence_score``
            lookup.  Defaults to ``{}``.
        depth:
            Cascade depth (0 = first level, used for the decision log).
        dry_run:
            If ``True``, evaluate all gates but do NOT increment counters.
        sco_id:
            Optional SCO identifier for the decision log entry.

        Returns
        -------
        PolicyDecision
            verdict="allow" → caller may invoke the candidate_module callback.
            verdict="skip"  → caller must not invoke the callback.
        """
        attrs = sco_attrs or {}

        # Gate 1: IOC value
        decision = self._evaluate_ioc_value(sco_type, value)
        if decision is not None:
            return decision

        # Gate 2: confidence
        decision = self._evaluate_confidence(source_module, sco_type, attrs)
        if decision is not None:
            return decision

        # Gate 3: budget
        decision = self._evaluate_budget()
        if decision is not None:
            return decision

        # ALLOW — increment counters (unless dry-run)
        if not dry_run:
            self._cascade_count += 1
            self._session_count += 1

        return PolicyDecision("allow", "allow", "passed all gates")

    def build_log_entry(
        self,
        sco_id: str,
        value: str,
        candidate_module: str,
        decision: PolicyDecision,
        depth: int,
    ) -> DecisionLogEntry:
        """Build a typed decision-log entry from a PolicyDecision.

        This factory keeps the DecisionLogEntry construction in one place so the
        key contract (DEC-60-PIVOT-POLICY-005) is enforced here, not scattered
        across callers.
        """
        return DecisionLogEntry(
            source_sco_id=sco_id,
            source_sco_value=value,
            candidate_module=candidate_module,
            gate=decision.gate,
            verdict=decision.verdict,
            reason=decision.reason,
            depth=depth,
        )
