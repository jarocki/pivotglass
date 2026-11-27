"""Which module answers which indicator type for automated pivots.

``DEFAULT_SUBSCRIPTIONS`` maps a module path to the STIX types it is asked
about when a pivot run (``modules/pivoting/run.py``, DEC-PIVOT-RUN-001)
expands an indicator. It is keyed by module path because that is what the
evidence path (``ToolContext.run_module``) executes, so a module added here
joins pivot runs and autopivot with no other change. The dossier's capability
extractor (``dossier/slot_inference.py``, DEC-M2-DOSSIER-003) reads the same
map as its registry of supported modules.

This module is the map's only home. Until v1.5.0 it lived in
``core/event_bus.py`` beside the auto-pivot cascade; that cascade was retired
(DEC-PIVOT-AUTOPIVOT-001) and the map moved here with its last consumer.
"""

from __future__ import annotations

DEFAULT_SUBSCRIPTIONS: dict[str, list[str]] = {
    "osint/abuseipdb": ["ipv4-addr"],
    "osint/shodan_ip": ["ipv4-addr"],
    "osint/whois_lookup": ["domain-name"],
    "cti/otx": ["ipv4-addr", "domain-name"],
    "osint/hibp": ["email-addr"],
    "osint/urlscan": ["url"],
    "osint/greynoise": ["ipv4-addr"],
    # F61 keyless hunters
    "cti/urlhaus": ["domain-name", "ipv4-addr", "url"],
    "cti/threatfox": ["ipv4-addr", "domain-name", "url", "file"],
    "cti/malwarebazaar": ["file"],
    "osint/crtsh": ["domain-name"],
    # Keyless context sources. Mnemonic passive DNS is deliberately absent: its
    # public tier allows 10 requests per minute, which a pivot run would exhaust.
    "osint/shodan_internetdb": ["ipv4-addr", "ipv6-addr"],
    "osint/sans_isc": ["ipv4-addr"],
    "osint/rdap": ["domain-name"],
    "osint/dns_doh": ["domain-name"],
    "osint/ip_asn": ["ipv4-addr", "ipv6-addr"],
    "cti/hashlookup": ["file"],
    # Keyless vulnerability sources (#58). CVEs reach them as ``vulnerability`` objects
    # emitted by host scanners (InternetDB, Shodan host). NVD is rate limited to
    # 5 requests per 30 s, enforced by its own limiter, so a run queues rather than fails.
    "cti/cisa_kev": ["vulnerability"],
    "cti/first_epss": ["vulnerability"],
    "cti/nvd_cve": ["vulnerability"],
}
