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
# Key resolution helpers — read from config/env, never hardcoded
# ---------------------------------------------------------------------------


def _env(*names: str) -> str:
    """Return the first non-empty value from the given environment variable names."""
    for name in names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


def _load_config_toml() -> dict[str, Any]:
    """Load ~/.ap/config.toml and return its contents as a dict.

    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    config_path = Path.home() / ".ap" / "config.toml"
    if not config_path.exists():
        return {}
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return {}
    try:
        with open(config_path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _resolve_keys(config: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Resolve all module API keys from config + env.

    Returns a mapping of logical key name -> (value, source) where source is
    one of "config", "env", or "". Empty value means not configured.

    NEVER returns hardcoded key values — all values come from runtime sources.
    """
    api_keys = config.get("api_keys", {})

    def from_config(key: str) -> str:
        return str(api_keys.get(key, "")).strip()

    results: dict[str, tuple[str, str]] = {}

    def resolve(logical: str, config_key: str, *env_names: str) -> None:
        val = from_config(config_key)
        if val:
            results[logical] = (val, "config")
            return
        val = _env(*env_names)
        if val:
            results[logical] = (val, "env")
            return
        results[logical] = ("", "")

    resolve("shodan", "shodan_api_key", "SHODAN_API_KEY", "AP_SHODAN_API_KEY")
    resolve("censys_id", "censys_id", "CENSYS_API_ID", "AP_CENSYS_ID", "CENSYS_ID")
    resolve(
        "censys_secret",
        "censys_secret",
        "CENSYS_API_SECRET",
        "AP_CENSYS_SECRET",
        "CENSYS_SECRET",
    )
    resolve("abuseipdb", "abuseipdb_api_key", "ABUSEIPDB_API_KEY", "AP_ABUSEIPDB_API_KEY")
    resolve("urlscan", "urlscan_api_key", "URLSCAN_API_KEY", "AP_URLSCAN_API_KEY")
    resolve("hibp", "hibp_api_key", "HIBP_API_KEY", "AP_HIBP_API_KEY")
    resolve(
        "virustotal",
        "virustotal_api_key",
        "VIRUSTOTAL_API_KEY",
        "AP_VIRUSTOTAL_API_KEY",
        "VT_API_KEY",
    )
    resolve("otx", "otx_api_key", "OTX_API_KEY", "AP_OTX_API_KEY")
    resolve(
        "passivetotal_user",
        "passivetotal_user",
        "AP_PASSIVETOTAL_USER",
        "PT_USERNAME",
    )
    resolve(
        "passivetotal_key",
        "passivetotal_key",
        "AP_PASSIVETOTAL_KEY",
        "PT_API_KEY",
    )

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
    cid, _ = keys.get("censys_id", ("", ""))
    csec, _ = keys.get("censys_secret", ("", ""))
    if not cid or not csec:
        return SKIP, "no API key configured", 0
    try:
        from adversary_pursuit.core.plugin_mgr import PluginManager

        mgr = PluginManager()
        mgr.load_plugins()
        mod = mgr.get_module("osint/censys_host")
        if mod is None:
            return FAIL, "module not found", 0
        mod.initialize({"censys_id": cid, "censys_secret": csec})
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
    """Print masked key detection summary."""
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

    # Load runtime config (never hardcoded)
    config = _load_config_toml()
    config_path = Path.home() / ".ap" / "config.toml"

    if not args.quiet:
        print("Config sources:")
        print(f"  ~/.ap/config.toml: {'found' if config_path.exists() else 'NOT FOUND'}")

    keys = _resolve_keys(config)
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
