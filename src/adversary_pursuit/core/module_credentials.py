"""Shared per-module credential resolver for the Adversary Pursuit toolkit.

This module is the single authority for building the ``init_config`` dict
passed to ``PursuitModule.initialize()`` from either the chat-agent path
(``agent/tools.py::run_module``) or the REPL hunt path
(``core/console.py::_initialize_module``).

@decision DEC-MODULE-CREDS-SHARED-001
@title Single authority for per-module credential resolution
@status accepted
@rationale Both the chat agent (agent/tools.py::run_module) and the REPL
    (core/console.py::_initialize_module) need the same per-module init dict.
    Sacred Practice 12 — single rendering authority. The agent path was correct
    (legacy); the REPL was passing wrong types since Phase 17R (AP #97 / AP #98).
    AP #97 introduced _initialize_module but still passed self.config_mgr directly
    to module.initialize(). That was still wrong because modules' base contract is:

        initialize(self, config: dict[str, Any])

    and every module calls self._config.get("api_key", "") inside initialize().
    ConfigManager.get() takes one arg and raises KeyError on miss; modules need
    dict.get(key, default). This module extracts the resolver that was already
    correct in the agent path and makes it a shared core authority.

    The upstream decisions that defined the resolver are preserved verbatim here
    as precedent:

    DEC-AGENT-SERVICE-NAME-MAP-001 — _SERVICE_NAMES map fixes module_path-tail
    != ConfigManager service-name mismatch. The legacy path derived the service
    name from the module path tail: "osint/shodan_ip" -> "shodan_ip". But
    ConfigManager.get_api_key() expects "shodan" (the field name in
    ApiKeysConfig), so Shodan keys were never resolved from config or env vars
    via the 3-layer chain. The fix is an explicit map from module_path to
    canonical service name. None signals that the module needs no API key
    (for example, whois_lookup). Modules absent from the map fall back to the
    path tail for forward-compat with future plugins. Multi-key modules (Censys,
    PassiveTotal) stay in CREDENTIAL_BUILDERS and are never looked up here.

    DEC-AGENT-TOOLS-003 — Per-module credential builders for multi-key auth
    modules. Most modules use a single api_key, but Censys requires censys_pat
    and PassiveTotal requires passivetotal_user + passivetotal_key.
    CREDENTIAL_BUILDERS maps module paths to callables that construct the full
    init_config dict from ConfigManager. Modules not in the map fall back to
    the legacy {"api_key": ...} pattern. This keeps resolve_module_credentials()
    generic while correctly threading multi-key credentials to modules that need
    them.

    Extracting the resolver into a shared core module forbids the two paths
    (agent and REPL) from diverging again.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Service-name map for single-key modules (DEC-AGENT-SERVICE-NAME-MAP-001)
# ---------------------------------------------------------------------------

SERVICE_NAMES: dict[str, str | None] = {
    "osint/shodan_ip": "shodan",
    "osint/abuseipdb": "abuseipdb",
    "osint/urlscan": "urlscan",
    "osint/hibp": "hibp",
    "cti/virustotal": "virustotal",
    "cti/otx": "otx",
    "osint/greynoise": "greynoise",
    "osint/whois_lookup": None,  # no key needed
    # F61 keyless modules — no API key needed (DEC-61-SCOPING-001)
    "cti/urlhaus": None,
    "cti/threatfox": None,
    "cti/malwarebazaar": None,
    "osint/crtsh": None,
}

# ---------------------------------------------------------------------------
# Credential builders for multi-key auth modules (DEC-AGENT-TOOLS-003)
# ---------------------------------------------------------------------------

# Maps module_path -> callable(ConfigManager) -> init_config dict.
# Only modules that require credentials beyond a single "api_key" field
# are listed here. resolve_module_credentials() falls back to {"api_key": ...}
# for all others.
CREDENTIAL_BUILDERS: dict[str, Any] = {
    "osint/censys_host": lambda cfg: {
        "censys_pat": cfg.get_censys_pat() or "",
    },
    "cti/passivetotal": lambda cfg: {
        "passivetotal_user": cfg.get_api_key("passivetotal_user") or "",
        "passivetotal_key": cfg.get_api_key("passivetotal_key") or "",
    },
}


def resolve_module_credentials(module_path: str, config_mgr: Any) -> dict:
    """Return the init_config dict for *module_path* using the canonical precedence.

    This is the single authority for credential resolution used by both
    ``run_module()`` in ``agent/tools.py`` and ``_initialize_module()`` in
    ``core/console.py`` (DEC-MODULE-CREDS-SHARED-001, DEC-AGENT-SERVICE-NAME-MAP-001,
    DEC-AGENT-TOOLS-003).

    Precedence:
    1. ``CREDENTIAL_BUILDERS``: multi-key modules (Censys, PassiveTotal).
    2. ``SERVICE_NAMES``: maps module_path to canonical service name for
       ``get_api_key()``. ``None`` means no API key needed (e.g. whois_lookup).
    3. Fallback: path tail used as service name (forward-compat with future plugins).

    Parameters
    ----------
    module_path:
        Canonical module path (e.g. "osint/shodan_ip", "cti/virustotal").
    config_mgr:
        ConfigManager instance to resolve keys from.

    Returns
    -------
    dict
        init_config dict ready for ``PursuitModule.initialize()``. Empty dict
        for key-free modules; ``{"api_key": ...}`` for standard single-key
        modules; multi-field dict for Censys/PassiveTotal.
    """
    credential_builder = CREDENTIAL_BUILDERS.get(module_path)
    if credential_builder is not None:
        return credential_builder(config_mgr)

    # Resolve canonical service name; fall back to path tail for unknown modules.
    service_name = SERVICE_NAMES.get(module_path, module_path.split("/")[-1])
    if service_name is None:
        # No key needed (e.g. whois_lookup)
        return {}

    api_key = config_mgr.get_api_key(service_name) or ""
    return {"api_key": api_key}
