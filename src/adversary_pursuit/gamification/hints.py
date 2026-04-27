"""Hint System for Adversary Pursuit (Issue #18).

Provides contextual hints to help analysts when they're stuck. Hints are
divided into free (cost=0) and paid (cost=10-20 points). General hints
apply to all modules; module-specific hints apply to a loaded module.

@decision DEC-HINT-001
@title Hint cost is a score penalty, not a currency field
@status accepted
@rationale Analysts earn points through module runs. Hints consume points
           as an explicit trade-off: knowledge at the cost of score. The
           cost is applied by APConsole via WorkspaceManager.store_score_events()
           with a negative point value. HintProvider is stateless about the
           workspace — it only returns the cost to pay. The caller owns
           deduction and persistence. This mirrors DEC-BADGE-001 (pure data
           producers, stateless about persistence).

@decision DEC-HINT-002
@title Hints are revealed sequentially, tracked by ID set in HintProvider
@status accepted
@rationale Revealed hint IDs are tracked in HintProvider._revealed so the
           same hint is not shown twice. The HintProvider instance is held
           by APConsole (session-scoped), so revealed set resets on each new
           session. For v1, session-scoped tracking is sufficient; workspace
           persistence of revealed hints can be added in v2.

@decision DEC-HINT-003
@title get_next_hint returns free hints before paid hints
@status accepted
@rationale Ordering by cost ascending means analysts always see free hints
           first. Within the same cost tier, hints are presented in definition
           order. Module-specific hints are interleaved with general hints
           in cost order. This ensures the best UX: no accidental score penalty
           for hints the analyst could have gotten for free.

@decision DEC-HINT-004
@title Module-specific hints use module base name (not full path)
@status accepted
@rationale Modules are loaded by path (e.g. "osint/dns_resolve") but hints
           are keyed by base name (e.g. "dns_resolve"). APConsole strips the
           prefix when calling HintProvider methods. This keeps hint definitions
           readable and independent of the module namespace layout, which may
           change in v2 when additional module types are added.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hint:
    """A single contextual hint.

    Parameters
    ----------
    id:
        Unique identifier (e.g. "hint-general-001"). Stable across sessions.
    text:
        Human-readable hint text shown to the analyst.
    cost:
        Point cost to reveal. 0 = free. Paid hints are 10-20 points.
    module:
        Module base name this hint applies to (e.g. "dns_resolve"), or None
        for general hints that apply to all modules.
    """

    id: str
    text: str
    cost: int
    module: str | None


@dataclass
class HintResult:
    """The result of revealing a hint.

    Parameters
    ----------
    hint:
        The Hint that was revealed.
    cost_paid:
        Points that should be deducted from the analyst's score.
        Matches hint.cost for paid hints; 0 for free hints.
    """

    hint: Hint
    cost_paid: int


class InsufficientBalanceError(Exception):
    """Raised when the analyst cannot afford a paid hint.

    Contains ``required`` and ``available`` attributes so the caller can
    display a helpful error message.
    """

    def __init__(self, required: int, available: int) -> None:
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient score: need {required} pts but have {available} pts"
        )


# ---------------------------------------------------------------------------
# Default hint catalogue
# ---------------------------------------------------------------------------

_DEFAULT_HINTS: list[Hint] = [
    # -----------------------------------------------------------------------
    # General — free (cost=0)
    # -----------------------------------------------------------------------
    Hint(
        id="hint-general-001",
        text=(
            "Start with the most specific indicator you have — an IP or domain is "
            "better than a URL as a pivot point."
        ),
        cost=0,
        module=None,
    ),
    Hint(
        id="hint-general-002",
        text=(
            "Look for patterns in timestamps. Adversaries often register domains "
            "or spin up infrastructure in tight time windows."
        ),
        cost=0,
        module=None,
    ),
    Hint(
        id="hint-general-003",
        text=(
            "Adversaries reuse infrastructure. If you find a hosting provider or "
            "ASN, check for other IPs/domains on the same range."
        ),
        cost=0,
        module=None,
    ),
    Hint(
        id="hint-general-004",
        text=(
            "Use 'use' to load a module, 'set TARGET <indicator>' to set the target, "
            "and 'run' to execute. 'back' returns to the main context."
        ),
        cost=0,
        module=None,
    ),
    Hint(
        id="hint-general-005",
        text=(
            "Type 'search <keyword>' to find relevant modules. "
            "Try keywords like 'ip', 'domain', 'email', or 'whois'."
        ),
        cost=0,
        module=None,
    ),
    # -----------------------------------------------------------------------
    # General — paid (cost=10-20)
    # -----------------------------------------------------------------------
    Hint(
        id="hint-general-paid-001",
        text=(
            "Pivot from an IP to its hosting provider using Shodan or AbuseIPDB. "
            "Provider ASN can reveal related infrastructure clusters."
        ),
        cost=10,
        module=None,
    ),
    Hint(
        id="hint-general-paid-002",
        text=(
            "Check certificate transparency logs (crt.sh) for domains issued "
            "from the same organization — adversaries often reuse cert subjects."
        ),
        cost=10,
        module=None,
    ),
    Hint(
        id="hint-general-paid-003",
        text=(
            "WHOIS registrant email addresses are often reused across adversary "
            "infrastructure. A pivot on the email can reveal entire campaigns."
        ),
        cost=15,
        module=None,
    ),
    Hint(
        id="hint-general-paid-004",
        text=(
            "Passive DNS records show what domains have resolved to an IP over time. "
            "Combine PassiveTotal or OTX passive DNS with current active DNS to find "
            "infrastructure that has been rotated but not fully cleaned up."
        ),
        cost=20,
        module=None,
    ),
    # -----------------------------------------------------------------------
    # dns_resolve — free
    # -----------------------------------------------------------------------
    Hint(
        id="hint-dns-001",
        text=(
            "dns_resolve performs A, AAAA, MX, NS, TXT, and PTR lookups. "
            "Check NS records — adversaries sometimes use custom nameservers "
            "across multiple domains."
        ),
        cost=0,
        module="dns_resolve",
    ),
    Hint(
        id="hint-dns-002",
        text=(
            "TXT records often contain SPF, DKIM, and verification tokens that "
            "can link domains to known services or leak infrastructure details."
        ),
        cost=0,
        module="dns_resolve",
    ),
    # dns_resolve — paid
    Hint(
        id="hint-dns-paid-001",
        text=(
            "Check for wildcard DNS entries (* records). Adversaries use wildcard "
            "DNS for phishing kits so any subdomain resolves to the same landing page."
        ),
        cost=10,
        module="dns_resolve",
    ),
    Hint(
        id="hint-dns-paid-002",
        text=(
            "MX records point to mail servers. If the MX and A record point to "
            "different IPs, the mail infrastructure may be hosted separately — "
            "a useful pivot to hosting providers."
        ),
        cost=15,
        module="dns_resolve",
    ),
    # -----------------------------------------------------------------------
    # whois_lookup — free
    # -----------------------------------------------------------------------
    Hint(
        id="hint-whois-001",
        text=(
            "whois_lookup returns registrant details, registrar, and creation/expiry dates. "
            "Fresh registrations (< 30 days) are a strong signal of newly-staged infrastructure."
        ),
        cost=0,
        module="whois_lookup",
    ),
    Hint(
        id="hint-whois-002",
        text=(
            "Privacy-protected WHOIS (e.g. WhoisGuard, PrivacyProtect) still reveals "
            "the registrar and registration date. The registrar alone can be a useful "
            "clustering attribute."
        ),
        cost=0,
        module="whois_lookup",
    ),
    # whois_lookup — paid
    Hint(
        id="hint-whois-paid-001",
        text=(
            "Registrant name and organization fields are often fabricated but follow "
            "patterns. Try searching for the registrant email across other WHOIS databases "
            "to find related domains registered by the same threat actor."
        ),
        cost=10,
        module="whois_lookup",
    ),
    Hint(
        id="hint-whois-paid-002",
        text=(
            "Check the registrar's abuse desk if the domain is actively used for "
            "phishing or C2. The registrar's abuse contact is in the WHOIS output."
        ),
        cost=15,
        module="whois_lookup",
    ),
    # -----------------------------------------------------------------------
    # abuseipdb — free
    # -----------------------------------------------------------------------
    Hint(
        id="hint-abuseipdb-001",
        text=(
            "AbuseIPDB's confidence score is a percentage: 100% means all reporters "
            "agree the IP is malicious. Scores above 80% warrant immediate investigation."
        ),
        cost=0,
        module="abuseipdb",
    ),
    Hint(
        id="hint-abuseipdb-002",
        text=(
            "AbuseIPDB reports include abuse categories (port scan, brute force, DDoS, etc). "
            "A mix of categories can indicate a compromised host used for multiple purposes."
        ),
        cost=0,
        module="abuseipdb",
    ),
    # abuseipdb — paid
    Hint(
        id="hint-abuseipdb-paid-001",
        text=(
            "Cross-reference AbuseIPDB reports with Shodan banners on the same IP. "
            "An IP with open RDP (3389) and high abuse score is almost certainly a brute-force "
            "source or active C2."
        ),
        cost=10,
        module="abuseipdb",
    ),
    Hint(
        id="hint-abuseipdb-paid-002",
        text=(
            "Filter report comments for keywords like 'C2', 'cobalt strike', 'metasploit'. "
            "Community reporters sometimes embed IOCs in comments that aren't in the "
            "structured fields."
        ),
        cost=15,
        module="abuseipdb",
    ),
    # -----------------------------------------------------------------------
    # shodan_ip — free
    # -----------------------------------------------------------------------
    Hint(
        id="hint-shodan-001",
        text=(
            "Shodan's banner data includes HTTP response headers. Check the Server: header "
            "for fingerprinting — specific server software versions can tie infrastructure "
            "to known adversary tooling."
        ),
        cost=0,
        module="shodan_ip",
    ),
    Hint(
        id="hint-shodan-002",
        text=(
            "Shodan returns historical data via the /shodan/host/{ip}/summary endpoint. "
            "Review open ports over time to see when new services appeared or disappeared."
        ),
        cost=0,
        module="shodan_ip",
    ),
    # shodan_ip — paid
    Hint(
        id="hint-shodan-paid-001",
        text=(
            "Cobalt Strike team servers often expose port 50050 or use self-signed certs "
            "with the subject 'Major Cobalt Strike'. Shodan facets can enumerate all matching "
            "IPs globally."
        ),
        cost=10,
        module="shodan_ip",
    ),
    Hint(
        id="hint-shodan-paid-002",
        text=(
            "Use Shodan's 'ssl.cert.subject.cn' filter to find all IPs using a certificate "
            "with the same Common Name as the one on your target. Certificate reuse is a "
            "strong pivot for adversary infrastructure clustering."
        ),
        cost=20,
        module="shodan_ip",
    ),
    # -----------------------------------------------------------------------
    # hibp (HaveIBeenPwned) — free
    # -----------------------------------------------------------------------
    Hint(
        id="hint-hibp-001",
        text=(
            "HaveIBeenPwned checks if an email address appeared in known data breaches. "
            "Compromised credentials are frequently used in initial access — a hit here "
            "warrants a credential reset."
        ),
        cost=0,
        module="hibp",
    ),
    Hint(
        id="hint-hibp-002",
        text=(
            "HIBP tracks paste sites (Pastebin, etc.) where credentials are leaked. "
            "The 'pastes' endpoint can surface fresh leaks not yet in breach compilations."
        ),
        cost=0,
        module="hibp",
    ),
    # hibp — paid
    Hint(
        id="hint-hibp-paid-001",
        text=(
            "A domain that appears in HIBP breach data (corporate email format in breaches) "
            "indicates employees were exposed. Cross-reference with LinkedIn to identify "
            "which employees likely had their credentials leaked."
        ),
        cost=10,
        module="hibp",
    ),
    Hint(
        id="hint-hibp-paid-002",
        text=(
            "HIBP breach dates help establish an adversary timeline. If a breach happened "
            "before a C2 domain registration, the breached credentials may have been used "
            "for initial access — correlate the dates."
        ),
        cost=15,
        module="hibp",
    ),
    # -----------------------------------------------------------------------
    # otx (AlienVault OTX) — free
    # -----------------------------------------------------------------------
    Hint(
        id="hint-otx-001",
        text=(
            "OTX pulses aggregate multiple IOCs from threat reports. Check which pulses "
            "reference your indicator — the pulse title often names the threat actor or campaign."
        ),
        cost=0,
        module="otx",
    ),
    Hint(
        id="hint-otx-002",
        text=(
            "OTX provides passive DNS, URL lists, file hashes, and malware samples linked "
            "to an indicator. The 'general' section shows a reputation score and pulse count."
        ),
        cost=0,
        module="otx",
    ),
    # otx — paid
    Hint(
        id="hint-otx-paid-001",
        text=(
            "OTX pulse tags often include MITRE ATT&CK technique IDs. Extract these tags "
            "and map them to your STIX objects — this bootstraps TTP coverage for your report."
        ),
        cost=10,
        module="otx",
    ),
    Hint(
        id="hint-otx-paid-002",
        text=(
            "OTX's 'adversary' field on a pulse names known threat actors. If a pulse "
            "references your target IP/domain and has an adversary name, that's a direct "
            "attribution link — worth significant points."
        ),
        cost=20,
        module="otx",
    ),
    # -----------------------------------------------------------------------
    # urlscan — free
    # -----------------------------------------------------------------------
    Hint(
        id="hint-urlscan-001",
        text=(
            "URLScan.io takes a screenshot and records all HTTP requests made by a page. "
            "Outbound requests in the scan reveal CDN, analytics, and C2 callback domains."
        ),
        cost=0,
        module="urlscan",
    ),
    Hint(
        id="hint-urlscan-002",
        text=(
            "URLScan returns DOM content, page title, and detected technologies. "
            "Technology fingerprints (e.g. specific JS frameworks) can cluster phishing "
            "kits across multiple domains."
        ),
        cost=0,
        module="urlscan",
    ),
    # urlscan — paid
    Hint(
        id="hint-urlscan-paid-001",
        text=(
            "URLScan's 'similar' endpoint finds pages with similar DOM structure or "
            "resources. Phishing kits are often deployed unchanged across many domains — "
            "finding one unlocks a cluster."
        ),
        cost=10,
        module="urlscan",
    ),
    Hint(
        id="hint-urlscan-paid-002",
        text=(
            "Check the URLScan result's 'verdicts' field — community and automated verdicts "
            "tag scans as 'malicious', 'phishing', or 'benign'. A malicious verdict from "
            "multiple engines is strong confirming evidence."
        ),
        cost=15,
        module="urlscan",
    ),
]


# ---------------------------------------------------------------------------
# HintProvider
# ---------------------------------------------------------------------------


class HintProvider:
    """Manages hint delivery for the active session.

    Tracks revealed hints in memory (session-scoped). Free hints are always
    available without cost. Paid hints require a score balance check — the
    caller (APConsole) is responsible for deducting and persisting the cost
    via WorkspaceManager.store_score_events() with a negative points entry.

    Usage::

        provider = HintProvider()

        # Get the next unrevealed hint (free first)
        result = provider.get_next_hint(module="dns_resolve")

        # Get all free hints at once
        free = provider.get_free_hints(module="dns_resolve")

        # Buy a paid hint (raises InsufficientBalanceError if can't afford)
        result = provider.buy_hint(current_score=score)
        # Caller deducts: store_score_events([{"action": "hint", "points": -result.cost_paid, ...}])

    See DEC-HINT-001 through DEC-HINT-004 for design rationale.
    """

    def __init__(self, hints: list[Hint] | None = None) -> None:
        """Initialise with optional custom hint list (defaults to _DEFAULT_HINTS).

        Parameters
        ----------
        hints:
            Override the default hints. Pass None to use the built-in catalogue.
            Useful for tests that need isolated, deterministic hint sets.
        """
        self._all_hints: list[Hint] = hints if hints is not None else _DEFAULT_HINTS
        self._revealed: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_free_hints(self, module: str | None = None) -> list[Hint]:
        """Return all free (cost=0) hints for the given module context.

        Returns general free hints plus any module-specific free hints for
        the provided module name. Already-revealed hints are included — this
        method returns the full free catalogue regardless of session state.

        Parameters
        ----------
        module:
            Module base name (e.g. "dns_resolve") to include module-specific
            hints. Pass None to return only general free hints.

        Returns
        -------
        list[Hint]
            All free hints applicable to the context, in definition order.
        """
        return [
            h for h in self._all_hints
            if h.cost == 0 and (h.module is None or h.module == module)
        ]

    def get_module_hints(self, module: str) -> list[Hint]:
        """Return all hints (free and paid) applicable to a module.

        Combines general hints (module=None) with module-specific hints,
        ordered by cost ascending (free first).

        Parameters
        ----------
        module:
            Module base name (e.g. "abuseipdb").

        Returns
        -------
        list[Hint]
            All applicable hints, ordered by cost ascending.
        """
        applicable = [
            h for h in self._all_hints
            if h.module is None or h.module == module
        ]
        return sorted(applicable, key=lambda h: h.cost)

    def get_next_hint(self, module: str | None = None) -> HintResult | None:
        """Return the next unrevealed hint, free hints first.

        Selects from general hints and module-specific hints (if module
        provided). Orders by cost ascending so free hints always come before
        paid hints. Returns None when all applicable hints have been revealed.

        The revealed state is updated in-place — calling get_next_hint()
        twice returns two different hints.

        Parameters
        ----------
        module:
            Module base name to include module-specific hints.

        Returns
        -------
        HintResult | None
            The next hint result, or None if all hints are revealed.
        """
        if module:
            applicable = self.get_module_hints(module)
        else:
            applicable = sorted(
                [h for h in self._all_hints if h.module is None],
                key=lambda h: h.cost,
            )
        for hint in applicable:
            if hint.id not in self._revealed:
                self._revealed.add(hint.id)
                return HintResult(hint=hint, cost_paid=0)
        return None

    def buy_hint(self, current_score: int, module: str | None = None) -> HintResult | None:
        """Reveal the next unrevealed paid hint, checking balance first.

        Raises InsufficientBalanceError if the analyst cannot afford the next
        paid hint. Returns None if no unrevealed paid hints remain.

        The cost is NOT deducted here — the caller (APConsole) must store
        a negative score event via WorkspaceManager. See DEC-HINT-001.

        Parameters
        ----------
        current_score:
            The analyst's current score (from WorkspaceManager.get_total_score()).
        module:
            Module base name to include module-specific paid hints.

        Returns
        -------
        HintResult | None
            The paid hint result (cost_paid > 0), or None if no paid hints remain.

        Raises
        ------
        InsufficientBalanceError
            When the next paid hint's cost exceeds current_score.
        """
        if module:
            candidate_pool = self.get_module_hints(module)
        else:
            candidate_pool = sorted(
                [h for h in self._all_hints if h.module is None],
                key=lambda h: h.cost,
            )

        applicable_paid = [
            h for h in candidate_pool
            if h.cost > 0 and h.id not in self._revealed
        ]

        if not applicable_paid:
            return None

        next_hint = applicable_paid[0]
        if current_score < next_hint.cost:
            raise InsufficientBalanceError(
                required=next_hint.cost,
                available=current_score,
            )

        self._revealed.add(next_hint.id)
        return HintResult(hint=next_hint, cost_paid=next_hint.cost)
