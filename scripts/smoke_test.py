"""Adversary Pursuit dummy-user smoke test.

Reads API keys from runtime sources ONLY — never hardcoded here:
  1. ~/.ap/config.toml  (via adversary_pursuit.core.config.ConfigManager)
  2. AP_* environment variables (project-namespaced)
  3. Vendor-convention environment variables (SHODAN_API_KEY, OTX_API_KEY, etc.)

NEVER commit API key values to this file or any file in the repo.

Usage
-----
    uv run python scripts/smoke_test.py
    uv run python scripts/smoke_test.py --quiet     # summary only
    uv run python scripts/smoke_test.py --verbose   # full tracebacks
    uv run python scripts/smoke_test.py --target 1.2.3.4

Exit codes
----------
    0  — all modules passed or skipped (no failures)
    1  — at least one module failed

@decision DEC-SMOKE-001
@title Smoke script reads keys from runtime config only; never hardcodes secrets
@status accepted
@rationale The script is committed to the repo. Hardcoding any API key would
           expose it in git history permanently. Instead, the script delegates
           key lookup to ConfigManager (which reads ~/.ap/config.toml and env
           vars) so the committed file contains zero secrets.

@decision DEC-SMOKE-002
@title SKIP vs FAIL: modules with unconfigured keys are SKIP, not FAIL
@status accepted
@rationale A missing key means the user hasn't set up that integration, not that
           the module is broken. Treating missing keys as SKIP lets the script
           give a useful pass/fail signal for the integrations that ARE configured.
           Only actual runtime errors (HTTP errors, exceptions, wrong output shape)
           count as FAIL.

@decision DEC-SMOKE-003
@title Key lookup delegates entirely to ConfigManager; no duplicate field-name logic
@status accepted
@rationale The prior _resolve_keys() helper read config.toml directly with
           WRONG field names (e.g. "shodan_api_key" instead of the real
           ApiKeysConfig field "shodan"). This caused "no API key configured"
           false-positives even when the user had valid keys in config.toml.
           Delegating to ConfigManager.get_api_key() / get_censys_pat() gives
           the correct 3-layer chain (config > AP_* env > vendor env) automatically
           and keeps this file free of field-name duplication that can drift.

@decision DEC-SMOKE-004
@title Source layer identified via Option B: raw model attribute check + env probe
@status accepted
@rationale Identifying which layer supplied a key ("config", "AP env", "vendor env")
           for diagnostic display requires per-layer probing. ConfigManager does not
           expose a get_api_key_with_source() method (adding one would require
           touching the forbidden src/ scope). Option B: the smoke test probes each
           layer directly using the already-loaded config model's attribute + os.environ
           lookups that mirror ConfigManager's precedence logic. This is a read-only
           diagnostic path only — the actual key VALUE always comes from ConfigManager.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Secret masking helper
# ---------------------------------------------------------------------------


def mask_secret(s: str) -> str:
    """Mask a secret string for safe display in output.

    Returns the first 4 characters + '...' + last 3 characters.
    For strings shorter than 8 characters, returns '***' to prevent leaking
    any meaningful portion of a short secret.

    Parameters
    ----------
    s:
        The secret string to mask.

    Returns
    -------
    str
        Masked representation safe for logging. Empty string returns empty string.

    Examples
    --------
    >>> mask_secret("sk-ant-12345abcXYZ")
    'sk-a...XYZ'
    >>> mask_secret("short")
    '***'
    >>> mask_secret("")
    ''
    """
    if not s:
        return ""
    if len(s) < 8:
        return "***"
    return f"{s[:4]}...{s[-3:]}"


# ---------------------------------------------------------------------------
# Key resolution helpers — delegate to ConfigManager, never duplicate field logic
# ---------------------------------------------------------------------------

# AP-prefixed env var names for each service (mirrors ConfigManager._AP_ENV_VAR_MAP).
# Used only for source-layer reporting in _source_for(); the actual value always
# comes from ConfigManager.get_api_key() / get_censys_pat().
_AP_ENV_NAMES: dict[str, str] = {
    "shodan": "AP_SHODAN_API_KEY",
    "virustotal": "AP_VIRUSTOTAL_API_KEY",
    "urlscan": "AP_URLSCAN_API_KEY",
    "abuseipdb": "AP_ABUSEIPDB_API_KEY",
    "hibp": "AP_HIBP_API_KEY",
    "otx": "AP_OTX_API_KEY",
    "censys_pat": "AP_CENSYS_PAT",
    "passivetotal_user": "AP_PASSIVETOTAL_USER",
    "passivetotal_key": "AP_PASSIVETOTAL_KEY",
}

# Vendor-convention env var names for each service (mirrors ConfigManager._VENDOR_ENV_VAR_MAP).
# Used only for source-layer reporting.
_VENDOR_ENV_NAMES: dict[str, str] = {
    "shodan": "SHODAN_API_KEY",
    "virustotal": "VIRUSTOTAL_API_KEY",
    "urlscan": "URLSCAN_API_KEY",
    "abuseipdb": "ABUSEIPDB_API_KEY",
    "hibp": "HIBP_API_KEY",
    "otx": "OTX_API_KEY",
    "censys_pat": "CENSYS_PAT",
    "passivetotal_user": "PT_USERNAME",
    "passivetotal_key": "PT_API_KEY",
}


def _source_for(
    cm: Any,
    service_id: str,
    value: str | None,
) -> str:
    """Return which config layer supplied the value for *service_id*.

    This is a DIAGNOSTIC-ONLY helper (DEC-SMOKE-004). It probes the same
    three layers that ConfigManager.get_api_key() checks, in the same order,
    to determine WHERE the value came from so the user can see e.g.
    "(config)" vs "(AP env)" vs "(vendor env)" next to each detected key.

    The actual key VALUE is not re-derived here — it is passed in as *value*
    (already resolved by ConfigManager) so there is no duplication of key
    resolution logic, only source attribution.

    Parameters
    ----------
    cm:
        A loaded ConfigManager instance.
    service_id:
        ApiKeysConfig field name (e.g. "shodan", "censys_pat").
    value:
        The resolved key value from ConfigManager.get_api_key() or
        get_censys_pat(). None/empty means "not configured" — returns "".

    Returns
    -------
    str
        One of "config", "AP env", "vendor env", or "" (not configured).
    """
    if not value:
        return ""

    # Layer 1: stored in config.toml — check the model attribute directly.
    # cm.config is the loaded Config object; we probe api_keys.<service_id>.
    try:
        cfg = cm._cache  # already loaded; safe to access the cache directly
        if cfg is not None:
            stored = getattr(cfg.api_keys, service_id, None)
            if stored:
                return "config"
    except AttributeError:
        pass

    # Layer 2: AP-prefixed env var
    ap_var = _AP_ENV_NAMES.get(service_id)
    if ap_var and os.environ.get(ap_var):
        return "AP env"

    # Layer 3: vendor-convention env var
    vendor_var = _VENDOR_ENV_NAMES.get(service_id)
    if vendor_var and os.environ.get(vendor_var):
        return "vendor env"

    # Fallback: value exists but source is unclear (e.g. legacy AP_* alias)
    return "env"


def _resolve_keys(cm: Any) -> dict[str, tuple[str, str]]:
    """Resolve all module API keys via ConfigManager and annotate each with its source layer.

    Returns a mapping of logical key name -> (value, source) where source is one of
    "config", "AP env", "vendor env", "env", or "". Empty value means not configured.

    Delegates ALL key lookup to ConfigManager so field names are always correct
    (DEC-SMOKE-003). Source attribution uses _source_for() (DEC-SMOKE-004).

    NEVER returns hardcoded key values — all values come from ConfigManager.
    """
    results: dict[str, tuple[str, str]] = {}

    def _add(logical: str, value: str | None) -> None:
        val = value or ""
        src = _source_for(cm, logical, val) if val else ""
        results[logical] = (val, src)

    _add("shodan", cm.get_api_key("shodan"))
    _add("virustotal", cm.get_api_key("virustotal"))
    _add("urlscan", cm.get_api_key("urlscan"))
    _add("abuseipdb", cm.get_api_key("abuseipdb"))
    _add("hibp", cm.get_api_key("hibp"))
    _add("otx", cm.get_api_key("otx"))
    _add("censys_pat", cm.get_censys_pat())
    _add("passivetotal_user", cm.get_api_key("passivetotal_user"))
    _add("passivetotal_key", cm.get_api_key("passivetotal_key"))

    return results


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


# ---------------------------------------------------------------------------
# Module runners
# ---------------------------------------------------------------------------


async def _run_module(mod, target: str, options: dict) -> list[dict]:
    """Call mod.hunt() and return its result list."""
    return await mod.hunt(target, options)


def _run_dns_resolve(target: str, verbose: bool) -> tuple[str, str, int]:
    """Run osint/dns_resolve — no key required."""
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/dns_resolve")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_whois_lookup(target: str, verbose: bool) -> tuple[str, str, int]:
    """Run osint/whois_lookup — no key required."""
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/whois_lookup")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_shodan(target: str, keys: dict, verbose: bool) -> tuple[str, str, int]:
    val, _ = keys.get("shodan", ("", ""))
    if not val:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/shodan_ip")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"api_key": val})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_censys(target: str, keys: dict, verbose: bool) -> tuple[str, str, int]:
    """Run osint/censys_host using the Censys Platform PAT (censys_pat).

    The legacy censys_id/censys_secret check has been removed; this now uses
    the Platform PAT as the sole auth mechanism (DEC-CONFIG-CENSYS-PAT-001).
    Missing PAT → SKIP (not FAIL — the migration error message belongs in the
    module, not here).
    """
    pat, _ = keys.get("censys_pat", ("", ""))
    if not pat:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/censys_host")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"censys_pat": pat})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_abuseipdb(target: str, keys: dict, verbose: bool) -> tuple[str, str, int]:
    val, _ = keys.get("abuseipdb", ("", ""))
    if not val:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/abuseipdb")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"api_key": val})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_urlscan(target: str, keys: dict, verbose: bool) -> tuple[str, str, int]:
    val, _ = keys.get("urlscan", ("", ""))
    if not val:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/urlscan")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"api_key": val})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_hibp(target: str, keys: dict, verbose: bool) -> tuple[str, str, int]:
    val, _ = keys.get("hibp", ("", ""))
    if not val:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/hibp")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"api_key": val})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_virustotal(target: str, keys: dict, verbose: bool) -> tuple[str, str, int]:
    val, _ = keys.get("virustotal", ("", ""))
    if not val:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/virustotal")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"api_key": val})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_otx(target: str, keys: dict, verbose: bool) -> tuple[str, str, int]:
    val, _ = keys.get("otx", ("", ""))
    if not val:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/otx")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"api_key": val})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _run_passivetotal(target: str, keys: dict, verbose: bool) -> tuple[str, str, int]:
    user, _ = keys.get("passivetotal_user", ("", ""))
    key, _ = keys.get("passivetotal_key", ("", ""))
    if not user or not key:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("cti/passivetotal")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"passivetotal_user": user, "passivetotal_key": key})
        results = asyncio.run(_run_module(mod, target, {}))
        return PASS, "", len(results)
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose), 0


def _fmt_exc(exc: Exception, verbose: bool) -> str:
    """Format an exception for output. Full traceback in verbose mode."""
    if verbose:
        return traceback.format_exc().strip()
    return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Workspace persistence check
# ---------------------------------------------------------------------------


def _check_workspace_persistence(
    stored_objects: list[dict], tmp_dir: Path, verbose: bool
) -> tuple[str, str]:
    """Verify the workspace can store and retrieve objects without UnboundExecutionError.

    This is the regression check for Bug 1. Uses a fresh WorkspaceManager with
    tmp_dir to avoid touching ~/.ap/workspaces/.
    """
    from sqlalchemy.exc import UnboundExecutionError

    try:
        from adversary_pursuit.core.workspace import WorkspaceManager

        wm = WorkspaceManager(workspace_dir=tmp_dir)
        # Deliberately do NOT call create() or switch() — same as production path
        objects = [
            {"type": "ipv4-addr", "value": "8.8.8.8"},
            {"type": "domain-name", "value": "google.com"},
        ]
        count = wm.store_stix_objects(
            objects,
            module_name="smoke_test/workspace_check",
            target="8.8.8.8",
        )
        retrieved = wm.get_stix_objects()
        if count != 2 or len(retrieved) != 2:
            return FAIL, f"expected 2 objects, got count={count} retrieved={len(retrieved)}"
        return PASS, ""
    except UnboundExecutionError as exc:
        return FAIL, f"UnboundExecutionError — workspace bind bug not fixed: {exc}"
    except Exception as exc:
        return FAIL, _fmt_exc(exc, verbose)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _print_key_summary(keys: dict, quiet: bool) -> None:
    """Print masked key detection summary showing source layer for each key."""
    if quiet:
        return
    configured = []
    for name, (val, src) in keys.items():
        if val:
            configured.append(f"    {name}={mask_secret(val)} ({src})")
    if configured:
        print("  CTI keys detected:")
        for line in configured:
            print(line)
    else:
        print("  CTI keys detected: none")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Adversary Pursuit dummy-user smoke test.\n"
            "Reads API keys from ~/.ap/config.toml and environment variables.\n"
            "NEVER hardcodes secrets — see DEC-SMOKE-001."
        )
    )
    parser.add_argument(
        "--target",
        default=None,
        help=(
            "Override default IP target (default: 8.8.8.8). "
            "Domain-based modules always use google.com."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all output except the final summary.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full tracebacks for failures.",
    )
    args = parser.parse_args()

    ip_target = args.target or "8.8.8.8"
    domain_target = "google.com"
    email_target = "test@example.com"
    url_target = "https://example.com"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not args.quiet:
        print(f"\nap dummy-user smoke test  ({now})")
        print("=" * 60)
        print()

    # Load runtime config via ConfigManager (never raw toml read + wrong field names).
    # ConfigManager.get_api_key() implements the correct 3-layer chain:
    #   config.toml > AP_<SERVICE>_API_KEY env > <SERVICE>_API_KEY env.
    # (DEC-SMOKE-003)
    from adversary_pursuit.core.config import ConfigManager

    cm = ConfigManager()
    cm.load()
    config_path = Path.home() / ".ap" / "config.toml"

    if not args.quiet:
        print("Config sources:")
        print(f"  ~/.ap/config.toml: {'found' if config_path.exists() else 'NOT FOUND'}")

    keys = _resolve_keys(cm)
    _print_key_summary(keys, args.quiet)

    if not args.quiet:
        print()
        print("Module tests:")

    # Module definitions: (display_name, runner_fn, target)
    module_runs = [
        ("osint/dns_resolve", lambda: _run_dns_resolve(domain_target, args.verbose), domain_target),
        (
            "osint/whois_lookup",
            lambda: _run_whois_lookup(domain_target, args.verbose),
            domain_target,
        ),
        ("osint/shodan_ip", lambda: _run_shodan(ip_target, keys, args.verbose), ip_target),
        ("osint/censys_host", lambda: _run_censys(ip_target, keys, args.verbose), ip_target),
        ("osint/abuseipdb", lambda: _run_abuseipdb(ip_target, keys, args.verbose), ip_target),
        ("osint/urlscan", lambda: _run_urlscan(url_target, keys, args.verbose), url_target),
        ("osint/hibp", lambda: _run_hibp(email_target, keys, args.verbose), email_target),
        ("cti/virustotal", lambda: _run_virustotal(ip_target, keys, args.verbose), ip_target),
        ("cti/otx", lambda: _run_otx(ip_target, keys, args.verbose), ip_target),
        (
            "cti/passivetotal",
            lambda: _run_passivetotal(domain_target, keys, args.verbose),
            domain_target,
        ),
    ]

    pass_count = 0
    fail_count = 0
    skip_count = 0
    results: list[tuple[str, str, str, str, int]] = []

    for module_name, runner, target in module_runs:
        status, error, indicator_count = runner()
        results.append((status, module_name, target, error, indicator_count))
        if status == PASS:
            pass_count += 1
        elif status == FAIL:
            fail_count += 1
        else:
            skip_count += 1

        if not args.quiet:
            indicator_str = f"→ {indicator_count} indicator{'s' if indicator_count != 1 else ''}"
            if status == PASS:
                line = f"  [PASS] {module_name:<28} {target:<20} {indicator_str}"
            elif status == SKIP:
                line = f"  [SKIP] {module_name:<28} {target:<20} → {error}"
            else:
                short_err = error.split("\n")[0][:60] if error else "unknown error"
                line = f"  [FAIL] {module_name:<28} {target:<20} → {short_err}"
            print(line)

    # Workspace persistence regression check (Bug 1)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_status, ws_error = _check_workspace_persistence([], Path(tmp_dir), args.verbose)

    if not args.quiet:
        print()
        print("Workspace persistence:")
        if ws_status == PASS:
            print("  [PASS] Workspace bind error not reproduced")
        else:
            print(f"  [FAIL] {ws_error}")

    if ws_status == FAIL:
        fail_count += 1

    if not args.quiet:
        print()
        print(f"Summary: {pass_count} pass / {fail_count} fail / {skip_count} skip")
        exit_code = 1 if fail_count > 0 else 0
        print(f"Exit code: {exit_code}{' (any failure)' if exit_code else ' (all pass/skip)'}")
        print()
    else:
        exit_code = 1 if fail_count > 0 else 0
        print(
            f"ap smoke test: {pass_count} pass / {fail_count} fail / {skip_count} skip"
            f" — exit {exit_code}"
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
