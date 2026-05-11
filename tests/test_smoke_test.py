"""Tests for scripts/smoke_test.py helper logic.

# @mock-exempt: The exit-code semantics tests (TestExitCodeSemantics) patch
# internal module runner functions and _check_workspace_persistence. These
# patches are necessary to exercise main()'s pass/fail/skip counting and exit
# code without making real network calls (external HTTP APIs) or real SQLite
# I/O. All patched callees are themselves tested independently with real
# implementations. The mocks here represent the "all external boundaries
# already tested elsewhere" pattern described in DEC-TEST-OTX-001 and
# DEC-TEST-CENSYS-001. The mask_secret, SKIP-semantics, and _resolve_keys
# tests use NO mocks — they exercise real code directly.

Tests cover:
- mask_secret() helper: normal, short, and empty inputs
- Module-iteration logic: SKIP when key not configured
- Pass/fail exit code semantics
- _resolve_keys: reads from env/config, no hardcoded values

@decision DEC-TEST-SMOKE-001
@title Import smoke_test via importlib to avoid scripts/ not being a package
@status accepted
@rationale scripts/smoke_test.py is not inside a Python package (no __init__.py).
           importlib.util.spec_from_file_location is the correct mechanism for
           importing a module by absolute file path without adding scripts/ to
           sys.path permanently, which could interfere with other imports.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import smoke_test module via importlib (not a package, so direct import)
# ---------------------------------------------------------------------------

_SMOKE_SCRIPT = Path(__file__).parent.parent / "scripts" / "smoke_test.py"


def _load_smoke_module():
    """Load scripts/smoke_test.py as a module object."""
    spec = importlib.util.spec_from_file_location("smoke_test", _SMOKE_SCRIPT)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def smoke():
    """Module-scoped fixture: load scripts/smoke_test.py once per test session."""
    return _load_smoke_module()


# ---------------------------------------------------------------------------
# mask_secret() tests — pure Python, no mocks
# ---------------------------------------------------------------------------


class TestMaskSecret:
    """Unit tests for the mask_secret() helper function."""

    def test_mask_secret_normal_input(self, smoke):
        """Normal secret: first 4 chars + '...' + last 3 chars."""
        result = smoke.mask_secret("sk-ant-12345abcXYZ")
        assert result == "sk-a...XYZ"

    def test_mask_secret_exactly_8_chars(self, smoke):
        """8-character string: first 4 + '...' + last 3."""
        result = smoke.mask_secret("abcdefgh")
        assert result == "abcd...fgh"

    def test_mask_secret_short_input(self, smoke):
        """Short string (< 8 chars) returns '***' to prevent leaking any portion."""
        assert smoke.mask_secret("short") == "***"
        assert smoke.mask_secret("abc") == "***"
        assert smoke.mask_secret("a") == "***"

    def test_mask_secret_exactly_7_chars(self, smoke):
        """7-character string (< 8) returns '***'."""
        assert smoke.mask_secret("1234567") == "***"

    def test_mask_secret_empty(self, smoke):
        """Empty string returns empty string."""
        assert smoke.mask_secret("") == ""

    def test_mask_secret_long_key(self, smoke):
        """Long API key: only first 4 and last 3 chars are visible."""
        key = "prefix-middle-suffix-xyz"
        result = smoke.mask_secret(key)
        assert result.startswith("pref")
        assert result.endswith("xyz")
        assert "..." in result
        # The middle portion is hidden
        assert len(result) < len(key)

    def test_mask_secret_does_not_expose_middle(self, smoke):
        """The masked output must not contain any character from the middle of the key."""
        key = "HEADMIDDLETAIL"
        result = smoke.mask_secret(key)
        # 'HEAD' is the first 4; 'AIL' is the last 3; 'MIDDLET' must not appear
        assert "MIDDLET" not in result
        assert "IDDLE" not in result


# ---------------------------------------------------------------------------
# SKIP semantics: modules skip when key not configured — no mocks, real logic
# ---------------------------------------------------------------------------


class TestSkipWhenNoKey:
    """Modules with unconfigured keys should return SKIP, not FAIL.

    These tests call the real _run_* functions with empty key dicts. The
    functions short-circuit before any network call when a key is missing,
    so no HTTP mock is needed.
    """

    def test_shodan_skips_without_key(self, smoke):
        """_run_shodan returns SKIP when the shodan key is empty."""
        keys = {"shodan": ("", "")}
        status, msg, count = smoke._run_shodan("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP
        assert count == 0

    def test_censys_skips_without_id(self, smoke):
        """_run_censys returns SKIP when censys_id is missing."""
        keys = {"censys_id": ("", ""), "censys_secret": ("mysecret", "env")}
        status, msg, count = smoke._run_censys("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP

    def test_censys_skips_without_secret(self, smoke):
        """_run_censys returns SKIP when censys_secret is missing."""
        keys = {"censys_id": ("myid", "env"), "censys_secret": ("", "")}
        status, msg, count = smoke._run_censys("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP

    def test_censys_skips_when_both_missing(self, smoke):
        """_run_censys returns SKIP when both censys_id and censys_secret are missing."""
        keys = {"censys_id": ("", ""), "censys_secret": ("", "")}
        status, msg, count = smoke._run_censys("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP

    def test_abuseipdb_skips_without_key(self, smoke):
        """_run_abuseipdb returns SKIP when the key is empty."""
        keys = {"abuseipdb": ("", "")}
        status, msg, count = smoke._run_abuseipdb("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP

    def test_urlscan_skips_without_key(self, smoke):
        """_run_urlscan returns SKIP when the key is empty."""
        keys = {"urlscan": ("", "")}
        status, msg, count = smoke._run_urlscan("https://example.com", keys, verbose=False)
        assert status == smoke.SKIP

    def test_hibp_skips_without_key(self, smoke):
        """_run_hibp returns SKIP when the key is empty."""
        keys = {"hibp": ("", "")}
        status, msg, count = smoke._run_hibp("test@example.com", keys, verbose=False)
        assert status == smoke.SKIP

    def test_virustotal_skips_without_key(self, smoke):
        """_run_virustotal returns SKIP when the key is empty."""
        keys = {"virustotal": ("", "")}
        status, msg, count = smoke._run_virustotal("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP

    def test_otx_skips_without_key(self, smoke):
        """_run_otx returns SKIP when the key is empty."""
        keys = {"otx": ("", "")}
        status, msg, count = smoke._run_otx("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP

    def test_passivetotal_skips_without_user(self, smoke):
        """_run_passivetotal returns SKIP when user is missing."""
        keys = {"passivetotal_user": ("", ""), "passivetotal_key": ("mykey", "env")}
        status, msg, count = smoke._run_passivetotal("google.com", keys, verbose=False)
        assert status == smoke.SKIP

    def test_passivetotal_skips_without_key(self, smoke):
        """_run_passivetotal returns SKIP when key is missing."""
        keys = {
            "passivetotal_user": ("user@example.com", "env"),
            "passivetotal_key": ("", ""),
        }
        status, msg, count = smoke._run_passivetotal("google.com", keys, verbose=False)
        assert status == smoke.SKIP


# ---------------------------------------------------------------------------
# Exit code semantics
# @mock-exempt: patches _run_dns_resolve, _run_whois_lookup, and
# _check_workspace_persistence to exercise main()'s counting + exit code
# logic without real network I/O (external HTTP boundaries) or filesystem I/O.
# The real implementations of those functions are tested in their own classes.
# ---------------------------------------------------------------------------


class TestExitCodeSemantics:
    """main() returns 0 when all pass/skip, 1 when any fail."""

    def _empty_keys(self, smoke):
        """Return an all-empty keys dict so all key-gated modules SKIP."""
        return {
            k: ("", "")
            for k in [
                "shodan",
                "censys_id",
                "censys_secret",
                "abuseipdb",
                "urlscan",
                "hibp",
                "virustotal",
                "otx",
                "passivetotal_user",
                "passivetotal_key",
            ]
        }

    def test_exit_0_when_all_pass_or_skip(self, smoke):
        """main() exits 0 when all modules pass or skip and workspace check passes."""
        with (
            patch.object(smoke, "_resolve_keys", return_value=self._empty_keys(smoke)),
            patch.object(smoke, "_run_dns_resolve", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_whois_lookup", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_check_workspace_persistence", return_value=(smoke.PASS, "")),
            patch.object(smoke, "_load_config_toml", return_value={}),
            patch("sys.argv", ["smoke_test.py", "--quiet"]),
        ):
            code = smoke.main()
        assert code == 0

    def test_exit_1_when_workspace_fails(self, smoke):
        """main() exits 1 when workspace persistence check fails."""
        with (
            patch.object(smoke, "_resolve_keys", return_value=self._empty_keys(smoke)),
            patch.object(smoke, "_run_dns_resolve", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_whois_lookup", return_value=(smoke.PASS, "", 1)),
            patch.object(
                smoke,
                "_check_workspace_persistence",
                return_value=(smoke.FAIL, "UnboundExecutionError"),
            ),
            patch.object(smoke, "_load_config_toml", return_value={}),
            patch("sys.argv", ["smoke_test.py", "--quiet"]),
        ):
            code = smoke.main()
        assert code == 1

    def test_exit_1_when_module_fails(self, smoke):
        """main() exits 1 when at least one module fails."""
        with (
            patch.object(smoke, "_resolve_keys", return_value=self._empty_keys(smoke)),
            patch.object(smoke, "_run_dns_resolve", return_value=(smoke.FAIL, "DNS error", 0)),
            patch.object(smoke, "_run_whois_lookup", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_check_workspace_persistence", return_value=(smoke.PASS, "")),
            patch.object(smoke, "_load_config_toml", return_value={}),
            patch("sys.argv", ["smoke_test.py", "--quiet"]),
        ):
            code = smoke.main()
        assert code == 1

    def test_exit_0_when_all_skip(self, smoke):
        """main() exits 0 when all modules skip (no keys configured) and workspace passes."""
        with (
            patch.object(smoke, "_resolve_keys", return_value=self._empty_keys(smoke)),
            patch.object(smoke, "_run_dns_resolve", return_value=(smoke.SKIP, "no key", 0)),
            patch.object(smoke, "_run_whois_lookup", return_value=(smoke.SKIP, "no key", 0)),
            patch.object(smoke, "_check_workspace_persistence", return_value=(smoke.PASS, "")),
            patch.object(smoke, "_load_config_toml", return_value={}),
            patch("sys.argv", ["smoke_test.py", "--quiet"]),
        ):
            code = smoke.main()
        assert code == 0


# ---------------------------------------------------------------------------
# _resolve_keys: reads from env/config, never hardcoded — no mocks needed
# ---------------------------------------------------------------------------


class TestResolveKeys:
    """_resolve_keys reads from env/config, never hardcoded.

    These tests manipulate real environment variables and call _resolve_keys()
    directly with real in-memory config dicts. No mocks are needed.
    """

    # Env vars used by _resolve_keys for the shodan key
    _SHODAN_ENV_VARS = ["SHODAN_API_KEY", "AP_SHODAN_API_KEY"]

    def _clear_shodan_env(self) -> dict:
        """Save and clear all Shodan env vars. Returns saved values."""
        return {k: os.environ.pop(k, None) for k in self._SHODAN_ENV_VARS}

    def _restore_env(self, saved: dict) -> None:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    def test_resolve_keys_returns_empty_when_no_env_or_config(self, smoke):
        """When neither env vars nor config provides a key, value is empty string."""
        all_env_vars = [
            "SHODAN_API_KEY",
            "AP_SHODAN_API_KEY",
            "CENSYS_API_ID",
            "AP_CENSYS_ID",
            "CENSYS_ID",
            "CENSYS_API_SECRET",
            "AP_CENSYS_SECRET",
            "CENSYS_SECRET",
            "ABUSEIPDB_API_KEY",
            "AP_ABUSEIPDB_API_KEY",
            "URLSCAN_API_KEY",
            "AP_URLSCAN_API_KEY",
            "HIBP_API_KEY",
            "AP_HIBP_API_KEY",
            "VIRUSTOTAL_API_KEY",
            "AP_VIRUSTOTAL_API_KEY",
            "VT_API_KEY",
            "OTX_API_KEY",
            "AP_OTX_API_KEY",
            "AP_PASSIVETOTAL_USER",
            "PT_USERNAME",
            "AP_PASSIVETOTAL_KEY",
            "PT_API_KEY",
        ]
        saved = {k: os.environ.pop(k, None) for k in all_env_vars}
        try:
            keys = smoke._resolve_keys({})
            for name, (val, _src) in keys.items():
                assert val == "", f"Expected empty value for {name} with no config/env, got {val!r}"
        finally:
            self._restore_env(saved)

    def test_resolve_keys_reads_from_env(self, smoke):
        """_resolve_keys picks up SHODAN_API_KEY from environment."""
        saved = self._clear_shodan_env()
        try:
            os.environ["SHODAN_API_KEY"] = "test-shodan-key-from-env"
            keys = smoke._resolve_keys({})
            val, src = keys.get("shodan", ("", ""))
            assert val == "test-shodan-key-from-env"
            assert src == "env"
        finally:
            os.environ.pop("SHODAN_API_KEY", None)
            self._restore_env(saved)

    def test_resolve_keys_config_takes_precedence_over_env(self, smoke):
        """Config value takes precedence over env var for the same key."""
        saved = self._clear_shodan_env()
        try:
            os.environ["SHODAN_API_KEY"] = "env-key"
            config = {"api_keys": {"shodan_api_key": "config-key"}}
            keys = smoke._resolve_keys(config)
            val, src = keys.get("shodan", ("", ""))
            assert val == "config-key"
            assert src == "config"
        finally:
            os.environ.pop("SHODAN_API_KEY", None)
            self._restore_env(saved)
