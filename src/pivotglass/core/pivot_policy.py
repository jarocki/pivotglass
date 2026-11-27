"""Pivot policy engine: value filter, confidence gate, and request budget.

This module is the SOLE gate authority for automated pivots. Every
(indicator, module) pair a pivot run (``modules/pivoting/run.py``,
DEC-PIVOT-RUN-001) considers is decided by ``PivotPolicy.evaluate``; no caller
re-implements a gate. Autopivot is a pivot run (DEC-PIVOT-AUTOPIVOT-001), so it
is gated here too.

@decision DEC-60-PIVOT-POLICY-001
@title PivotPolicy.evaluate is the sole pivot gate authority (consulted by PivotRun)
@status accepted (amended v1.5.0: the consumer is PivotRun; the event bus is retired)
@rationale Single-source-of-truth (CLAUDE.md §12).  If gates lived inline in a caller
           AND in a policy module, two authorities would silently diverge: a future
           implementer adding a new gate would have to remember to update both paths.
           The architecture rule (CLAUDE.md "Encode authority, don't imply it") is
           satisfied by a single explicit authority.
           History: until v1.5.0 the consumer was ``EventBus.publish`` in
           ``core/event_bus.py`` and tests asserted publish held no inline gate
           conditionals. The cascade was retired in favour of PivotRun
           (DEC-PIVOT-AUTOPIVOT-001); PivotRun calls ``evaluate`` for every pair and
           tests assert its readiness check spends nothing and decides no value.

@decision DEC-PIVOT-SEED-001
@title Analyst-named seeds skip the popularity and confidence gates, never the reserved-value gate
@status accepted
@rationale An analyst who types ``pivot google.com`` has decided that indicator is
           worth asking about; the top-1k popularity rule exists to stop *automated*
           expansion from fanning out into the web's most common domains, and a
           typed seed carries no module confidence score to gate on. So
           ``evaluate(..., analyst_seed=True)`` does not apply the top-1k list or the
           confidence threshold, and records the allow as "analyst-named seed;
           popularity gate not applied". It still refuses private, loopback and
           link-local addresses and RFC 6761 special-use names (and the analyst's own
           denylist): third parties know nothing useful about them, and asking can
           leak internal addresses. The budget still applies. Children found from a
           seed, and autopivot's seeds (which are module results, not analyst input),
           pass every gate.

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
@status superseded by DEC-PIVOT-AUTOPIVOT-001
@rationale Original: explicit-kwarg threading over a global flag let tests run dry
           and non-dry side by side, and a seven-key DecisionLogEntry gave consumers
           a stable shape. v1.5.0: the preview is a plan-only PivotRun, which
           evaluates every gate against its own private budget and executes nothing;
           its ``decisions`` list (one entry per pair: value, depth, module, verdict,
           gate, reason) is the decision log. ``evaluate`` no longer takes
           ``dry_run`` and DecisionLogEntry/build_log_entry were removed with the bus.

@decision DEC-60-PIVOT-POLICY-006
@title max_depth REMOVED from PivotConfig; per-cascade + per-session budgets are the
       sole flow-control; auto_pivot_depth field retained in GeneralConfig for
       backward-compatible TOML round-trip only (not consulted by F60+ code)
@status accepted (amended v1.5.0)
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
           v1.5.0: the two counters are gone from PivotPolicy. A policy now carries
           one request budget, set by its pivot run. ``max_per_cascade`` sizes each
           autopivot run and ``max_per_session`` caps autopivot requests across a
           ToolContext session (DEC-PIVOT-AUTOPIVOT-001).

@decision DEC-60-PIVOT-POLICY-007
@title User allowlist / denylist paths default to ~/.pivotglass/pivot-allowlist.txt and
       ~/.pivotglass/pivot-denylist.txt; missing files are silently treated as empty
@status accepted
@rationale Config stores optional paths; None means "use default location".
           Silent empty-file fall-through means: (a) first-run works without the
           user creating files; (b) CI/CD environments without ~/.pivotglass/ don't fail.
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
from typing import Literal

from pivotglass.core.config import AutoPivotPolicyConfig

logger = logging.getLogger(__name__)

# The recorded reason when an analyst-named seed is allowed (DEC-PIVOT-SEED-001).
ANALYST_SEED_REASON = "analyst-named seed; popularity gate not applied"


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
        3. budget      — the owning pivot run's request budget.

    Parameters
    ----------
    policy_config:
        ``AutoPivotPolicyConfig`` instance read from ``GeneralConfig.auto_pivot_policy``
        (DEC-60-PIVOT-POLICY-CONFIG-001).  Loaded once on construction; not re-read.
    budget:
        Requests this policy may allow before the budget gate refuses. Each pivot
        run constructs its own policy with its own budget (DEC-PIVOT-RUN-001), so
        the counter is never shared or reset.

    Notes
    -----
    The class is stateless across calls except for the request counter, which
    ``evaluate`` increments on every allow.
    """

    def __init__(self, policy_config: AutoPivotPolicyConfig, *, budget: int) -> None:
        self._cfg = policy_config
        self._budget = budget
        self._static_deny_domains: frozenset[str] = frozenset()
        self._user_allow_domains: frozenset[str] = frozenset()
        self._user_deny_domains: frozenset[str] = frozenset()

        # Per-(source_module, sco_type) missing-confidence policy override.
        # Empty by default → OPTIMISTIC for all pairs (DEC-60-PIVOT-POLICY-004).
        self._missing_confidence_policy: dict[
            tuple[str, str], Literal["optimistic", "pessimistic"]
        ] = {}

        # Requests allowed so far (the budget gate's counter).
        self._allowed: int = 0

        self._load_static_rules()
        self._load_user_lists()

    # ------------------------------------------------------------------
    # Loader helpers
    # ------------------------------------------------------------------

    def _load_static_rules(self) -> None:
        """Load the bundled top-1k static deny-for-pivoting list.

        The file ships as ``src/pivotglass/data/pivot_allowlist_top1k.txt``.
        Any IOError falls through to an empty set so offline / restricted
        environments don't hard-fail (DEC-60-PIVOT-POLICY-007).
        """
        try:
            ref = resources.files("pivotglass.data").joinpath("pivot_allowlist_top1k.txt")
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

        Default paths: ``~/.pivotglass/pivot-allowlist.txt`` and ``~/.pivotglass/pivot-denylist.txt``.
        Missing files are silently treated as empty.
        """
        allow_path = (
            Path(self._cfg.allowlist_path)
            if self._cfg.allowlist_path
            else Path.home() / ".pivotglass" / "pivot-allowlist.txt"
        )
        deny_path = (
            Path(self._cfg.denylist_path)
            if self._cfg.denylist_path
            else Path.home() / ".pivotglass" / "pivot-denylist.txt"
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
    # Budget
    # ------------------------------------------------------------------

    @property
    def allowed_count(self) -> int:
        """Requests allowed so far (read-only view of the budget gate's counter)."""
        return self._allowed

    # ------------------------------------------------------------------
    # Gate implementations
    # ------------------------------------------------------------------

    def _evaluate_ioc_value(
        self, sco_type: str, value: str, *, popularity: bool = True
    ) -> PolicyDecision | None:
        """Gate 1: filter out indicators with no pivot value (DEC-60-PIVOT-POLICY-001).

        ``popularity=False`` leaves out the top-1k rule only (analyst-named seeds,
        DEC-PIVOT-SEED-001); reserved and private values are refused either way.

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
            if popularity and v in self._static_deny_domains:
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
        """Gate 3: the run's request budget (DEC-60-PIVOT-POLICY-006).

        Returns a SKIP PolicyDecision if the budget is spent, else None.
        Does NOT increment the counter — ``evaluate`` does that on ALLOW.
        """
        if self._allowed >= self._budget:
            return PolicyDecision(
                "skip", "budget", f"request budget exhausted: {self._allowed}/{self._budget}"
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
        sco_id: str = "",
        analyst_seed: bool = False,
    ) -> PolicyDecision:
        """Evaluate whether a candidate pivot should proceed.

        Gates are applied in strict order (DEC-60-PIVOT-POLICY-002).  The first
        SKIP result short-circuits evaluation; no later gates are consulted.
        On ALLOW, the request counter is incremented.

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
        sco_id:
            Optional SCO identifier (unused by the gates; kept for callers' logs).
        analyst_seed:
            ``True`` when the analyst typed this indicator as a pivot seed. The
            top-1k popularity rule and the confidence gate are not applied; the
            reserved/private-value rules and the budget are (DEC-PIVOT-SEED-001).

        Returns
        -------
        PolicyDecision
            verdict="allow" → caller may invoke the candidate_module callback.
            verdict="skip"  → caller must not invoke the callback.
        """
        attrs = sco_attrs or {}

        # Gate 0: a module's own output never re-triggers that module. Only the
        # vulnerability modules can hit this (their result type is their own
        # subscription), and re-asking NVD for the CVE it just answered would
        # spend its 5-per-30-second allowance for nothing (#58).
        if sco_type == "vulnerability" and source_module == candidate_module:
            return PolicyDecision("skip", "self_pivot", f"{candidate_module} produced this object")

        # Gate 1: IOC value (popularity rule only for indicators the analyst did not name)
        decision = self._evaluate_ioc_value(sco_type, value, popularity=not analyst_seed)
        if decision is not None:
            return decision

        # Gate 2: confidence (a typed seed carries no module score to gate on)
        if not analyst_seed:
            decision = self._evaluate_confidence(source_module, sco_type, attrs)
            if decision is not None:
                return decision

        # Gate 3: budget
        decision = self._evaluate_budget()
        if decision is not None:
            return decision

        self._allowed += 1
        if analyst_seed:
            return PolicyDecision("allow", "allow", ANALYST_SEED_REASON)
        return PolicyDecision("allow", "allow", "passed all gates")
