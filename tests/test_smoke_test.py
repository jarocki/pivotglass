"""Tests for scripts/smoke_test.py helper logic.

# @mock-exempt: The exit-code semantics tests (TestExitCodeSemantics) patch
# internal module runner functions, _check_workspace_persistence, and
# ConfigManager to exercise main()'s pass/fail/skip counting and exit
# code without making real network calls (external HTTP APIs) or real SQLite
# I/O. All patched callees are themselves tested independently with real
# implementations. The mocks here represent the "all external boundaries
# already tested elsewhere" pattern described in DEC-TEST-OTX-001 and
# DEC-TEST-CENSYS-001.
# The TestAuthErrorClassification tests use AsyncMock on mod.hunt() — this IS
# the external HTTP boundary. The _run_* functions under test call asyncio.run()
# on mod.hunt(), which would make a live network request. Patching hunt() with
# AsyncMock that raises a specific exception exercises the exception-routing logic
# (AuthenticationError→SKIP, httpx errors→FAIL) without a real API call. The
# PluginManager.get_module() stub returns the mock module so plugin loading is
# bypassed. This is the canonical external-boundary mock pattern.
# The mask_secret, SKIP-semantics, and _resolve_keys tests use NO mocks —
# they exercise real code directly.

Tests cover:
- mask_secret() helper: normal, short, and empty inputs
- Module-iteration logic: SKIP when key not configured
- AuthenticationError classification: _run_* handlers return SKIP (not FAIL)
- HTTPStatusError / ReadTimeout classification: _run_* handlers return FAIL
- Pass/fail exit code semantics
- _resolve_keys: delegates to ConfigManager, reads from config/env, no hardcoded values
- _source_for: returns correct layer label ("config", "AP env", "vendor env")

@decision DEC-TEST-SMOKE-001
@title Import smoke_test via importlib to avoid scripts/ not being a package
@status accepted
@rationale scripts/smoke_test.py is not inside a Python package (no __init__.py).
           importlib.util.spec_from_file_location is the correct mechanism for
           importing a module by absolute file path without adding scripts/ to
           sys.path permanently, which could interfere with other imports.

@decision DEC-TEST-SMOKE-002
@title _resolve_keys tests use real ConfigManager instances backed by tmp_path config dirs
@status accepted
@rationale After DEC-SMOKE-003 (_resolve_keys delegates to ConfigManager), the
           tests must exercise a real ConfigManager to prove the correct field
           names are used. We construct ConfigManager(config_dir=tmp_dir) so
           tests never touch the user's real ~/.ap/config.toml, then call
           cm.load() and cm.save() to populate the in-memory cache with test
           values, which _resolve_keys() reads through the ConfigManager API.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest.mock import (  # @mock-exempt: hunt() is the external HTTP boundary; see module docstring
    AsyncMock,
    MagicMock,
    patch,
)

import httpx
import pytest

from adversary_pursuit.modules.base import AuthenticationError

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
# Helper: build a real ConfigManager pointed at a temp directory
# ---------------------------------------------------------------------------


def _make_cm(
    tmp_dir: str | Path,
    *,
    shodan: str = "",
    virustotal: str = "",
    urlscan: str = "",
    abuseipdb: str = "",
    hibp: str = "",
    otx: str = "",
    censys_pat: str | None = None,
    passivetotal_user: str = "",
    passivetotal_key: str = "",
) -> "ConfigManager":  # noqa: F821
    """Return a ConfigManager loaded from *tmp_dir* with the given api_keys pre-set.

    Uses ConfigManager's public API (load + field mutation + save) so the
    instance cache reflects the values and _resolve_keys() can query them
    through get_api_key() / get_censys_pat() without touching the real
    ~/.ap/config.toml.
    """
    from adversary_pursuit.core.config import ConfigManager

    cm = ConfigManager(config_dir=tmp_dir)
    cfg = cm.load()
    cfg.api_keys.shodan = shodan
    cfg.api_keys.virustotal = virustotal
    cfg.api_keys.urlscan = urlscan
    cfg.api_keys.abuseipdb = abuseipdb
    cfg.api_keys.hibp = hibp
    cfg.api_keys.otx = otx
    cfg.api_keys.censys_pat = censys_pat
    cfg.api_keys.passivetotal_user = passivetotal_user
    cfg.api_keys.passivetotal_key = passivetotal_key
    cm.save(cfg)
    # Re-load so the cache is fully populated from the file (same as production)
    cm.load()
    return cm


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

    def test_censys_skips_without_pat(self, smoke):
        """_run_censys returns SKIP when censys_pat is missing (new PAT-based check)."""
        keys = {"censys_pat": ("", "")}
        status, msg, count = smoke._run_censys("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP

    def test_censys_skips_when_pat_empty(self, smoke):
        """_run_censys returns SKIP when censys_pat tuple has empty value."""
        keys = {}  # no censys_pat key at all — same as missing
        status, msg, count = smoke._run_censys("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP

    def test_censys_does_not_use_legacy_id_secret(self, smoke):
        """_run_censys ignores censys_id / censys_secret — PAT is the only check.

        This is a regression guard: the old code used censys_id + censys_secret;
        providing them without censys_pat must still produce SKIP (not an attempt
        to call the module with legacy credentials).
        """
        keys = {
            "censys_id": ("some-id", "env"),
            "censys_secret": ("some-secret", "env"),
            "censys_pat": ("", ""),  # PAT absent
        }
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
# ConfigManager is patched via its constructor to avoid touching real config.
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
                "censys_pat",
                "abuseipdb",
                "urlscan",
                "hibp",
                "virustotal",
                "otx",
                "passivetotal_user",
                "passivetotal_key",
            ]
        }

    def _patch_cm(self, smoke, empty_keys):
        """Return a context manager that patches ConfigManager in the smoke module.

        Replaces ConfigManager() in the smoke module's namespace so main()
        receives a stub that returns empty keys via _resolve_keys.
        The stub has a .load() method (no-op) matching the real interface.
        """
        mock_cm = MagicMock()
        mock_cm.load.return_value = MagicMock()
        # ConfigManager class mock — constructor returns mock_cm instance
        mock_cm_class = MagicMock(return_value=mock_cm)
        return patch(
            "adversary_pursuit.core.config.ConfigManager",
            mock_cm_class,
        )

    def test_exit_0_when_all_pass_or_skip(self, smoke):
        """main() exits 0 when all modules pass or skip and workspace check passes.

        Patches all keyless runner functions (dns_resolve, whois_lookup, urlhaus,
        threatfox, malwarebazaar, crtsh) added in F61 so the test remains hermetic
        and doesn't require network access.
        """
        empty_keys = self._empty_keys(smoke)
        with (
            patch.object(smoke, "_resolve_keys", return_value=empty_keys),
            patch.object(smoke, "_run_dns_resolve", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_whois_lookup", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_urlhaus", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_threatfox", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_malwarebazaar", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_crtsh", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_check_workspace_persistence", return_value=(smoke.PASS, "")),
            patch("adversary_pursuit.core.config.ConfigManager"),
            patch("sys.argv", ["smoke_test.py", "--quiet"]),
        ):
            code = smoke.main()
        assert code == 0

    def test_exit_1_when_workspace_fails(self, smoke):
        """main() exits 1 when workspace persistence check fails."""
        empty_keys = self._empty_keys(smoke)
        with (
            patch.object(smoke, "_resolve_keys", return_value=empty_keys),
            patch.object(smoke, "_run_dns_resolve", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_whois_lookup", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_urlhaus", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_threatfox", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_malwarebazaar", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_crtsh", return_value=(smoke.PASS, "", 1)),
            patch.object(
                smoke,
                "_check_workspace_persistence",
                return_value=(smoke.FAIL, "UnboundExecutionError"),
            ),
            patch("adversary_pursuit.core.config.ConfigManager"),
            patch("sys.argv", ["smoke_test.py", "--quiet"]),
        ):
            code = smoke.main()
        assert code == 1

    def test_exit_1_when_module_fails(self, smoke):
        """main() exits 1 when at least one module fails."""
        empty_keys = self._empty_keys(smoke)
        with (
            patch.object(smoke, "_resolve_keys", return_value=empty_keys),
            patch.object(smoke, "_run_dns_resolve", return_value=(smoke.FAIL, "DNS error", 0)),
            patch.object(smoke, "_run_whois_lookup", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_urlhaus", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_threatfox", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_malwarebazaar", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_run_crtsh", return_value=(smoke.PASS, "", 1)),
            patch.object(smoke, "_check_workspace_persistence", return_value=(smoke.PASS, "")),
            patch("adversary_pursuit.core.config.ConfigManager"),
            patch("sys.argv", ["smoke_test.py", "--quiet"]),
        ):
            code = smoke.main()
        assert code == 1

    def test_exit_0_when_all_skip(self, smoke):
        """main() exits 0 when all modules skip (no keys configured) and workspace passes.

        Patches all keyless runner functions (dns_resolve, whois_lookup, urlhaus,
        threatfox, malwarebazaar, crtsh) added in F61 so the test remains hermetic
        and doesn't require network access.
        """
        empty_keys = self._empty_keys(smoke)
        with (
            patch.object(smoke, "_resolve_keys", return_value=empty_keys),
            patch.object(smoke, "_run_dns_resolve", return_value=(smoke.SKIP, "no key", 0)),
            patch.object(smoke, "_run_whois_lookup", return_value=(smoke.SKIP, "no key", 0)),
            patch.object(smoke, "_run_urlhaus", return_value=(smoke.SKIP, "no key", 0)),
            patch.object(smoke, "_run_threatfox", return_value=(smoke.SKIP, "no key", 0)),
            patch.object(smoke, "_run_malwarebazaar", return_value=(smoke.SKIP, "no key", 0)),
            patch.object(smoke, "_run_crtsh", return_value=(smoke.SKIP, "no key", 0)),
            patch.object(smoke, "_check_workspace_persistence", return_value=(smoke.PASS, "")),
            patch("adversary_pursuit.core.config.ConfigManager"),
            patch("sys.argv", ["smoke_test.py", "--quiet"]),
        ):
            code = smoke.main()
        assert code == 0


# ---------------------------------------------------------------------------
# _source_for: source layer attribution — no mocks, real ConfigManager
# ---------------------------------------------------------------------------


class TestSourceFor:
    """_source_for() returns the correct layer label for each resolution path.

    Uses real ConfigManager instances backed by a temporary directory
    (DEC-TEST-SMOKE-002) so these tests never touch the user's config.
    """

    def test_resolve_key_from_config_returns_source_layer(self, smoke):
        """When a key is stored in config.toml, _source_for returns 'config'."""
        with tempfile.TemporaryDirectory() as tmp:
            cm = _make_cm(tmp, shodan="test-shodan-key-32-chars-xxxxxxxxxx")
            src = smoke._source_for(cm, "shodan", "test-shodan-key-32-chars-xxxxxxxxxx")
        assert src == "config"

    def test_resolve_key_from_ap_env_returns_source_layer(self, smoke):
        """When key comes from AP_SHODAN_API_KEY env var, _source_for returns 'AP env'."""
        with tempfile.TemporaryDirectory() as tmp:
            cm = _make_cm(tmp, shodan="")  # no config value
            saved = os.environ.pop("AP_SHODAN_API_KEY", None)
            os.environ["AP_SHODAN_API_KEY"] = "env-shodan-key-from-ap"
            try:
                src = smoke._source_for(cm, "shodan", "env-shodan-key-from-ap")
            finally:
                os.environ.pop("AP_SHODAN_API_KEY", None)
                if saved is not None:
                    os.environ["AP_SHODAN_API_KEY"] = saved
        assert src == "AP env"

    def test_resolve_key_from_vendor_env_returns_source_layer(self, smoke):
        """When key comes from SHODAN_API_KEY vendor env var, _source_for returns 'vendor env'."""
        with tempfile.TemporaryDirectory() as tmp:
            cm = _make_cm(tmp, shodan="")  # no config value
            saved_ap = os.environ.pop("AP_SHODAN_API_KEY", None)
            saved_vendor = os.environ.pop("SHODAN_API_KEY", None)
            os.environ["SHODAN_API_KEY"] = "env-shodan-vendor-key"
            try:
                src = smoke._source_for(cm, "shodan", "env-shodan-vendor-key")
            finally:
                os.environ.pop("SHODAN_API_KEY", None)
                if saved_ap is not None:
                    os.environ["AP_SHODAN_API_KEY"] = saved_ap
                if saved_vendor is not None:
                    os.environ["SHODAN_API_KEY"] = saved_vendor
        assert src == "vendor env"

    def test_resolve_key_when_all_layers_empty_returns_empty(self, smoke):
        """_source_for returns '' when value is None/empty (key not configured)."""
        with tempfile.TemporaryDirectory() as tmp:
            cm = _make_cm(tmp, shodan="")
            saved_ap = os.environ.pop("AP_SHODAN_API_KEY", None)
            saved_vendor = os.environ.pop("SHODAN_API_KEY", None)
            try:
                src = smoke._source_for(cm, "shodan", None)
                src2 = smoke._source_for(cm, "shodan", "")
            finally:
                if saved_ap is not None:
                    os.environ["AP_SHODAN_API_KEY"] = saved_ap
                if saved_vendor is not None:
                    os.environ["SHODAN_API_KEY"] = saved_vendor
        assert src == ""
        assert src2 == ""


# ---------------------------------------------------------------------------
# _resolve_keys: delegates to ConfigManager — correct field names, correct values
# ---------------------------------------------------------------------------


class TestResolveKeys:
    """_resolve_keys delegates to ConfigManager, never duplicates field-name logic.

    These tests construct a real ConfigManager backed by a temporary directory
    (DEC-TEST-SMOKE-002) and populate it with known values so we can assert
    that _resolve_keys() calls ConfigManager.get_api_key() with the CORRECT
    field names (e.g. "shodan", not "shodan_api_key").
    """

    # Env vars that might bleed in and corrupt the vendor-env layer test
    _ALL_SHODAN_ENV = ["SHODAN_API_KEY", "AP_SHODAN_API_KEY"]

    def _isolate_shodan_env(self):
        """Remove Shodan env vars and return saved values."""
        return {k: os.environ.pop(k, None) for k in self._ALL_SHODAN_ENV}

    def _restore_env(self, saved: dict) -> None:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v

    def test_smoke_test_uses_config_manager_for_shodan_lookup(self, smoke):
        """_resolve_keys calls cm.get_api_key('shodan'), not 'shodan_api_key'.

        This is the direct regression test: the old code called
        _resolve_keys with "shodan_api_key" as the config dict key.
        The new code delegates to ConfigManager.get_api_key("shodan").
        """
        mock_cm = MagicMock()
        mock_cm.get_api_key.return_value = None
        mock_cm.get_censys_pat.return_value = None
        mock_cm._cache = None

        smoke._resolve_keys(mock_cm)

        # Must be called with "shodan" (the real ApiKeysConfig field), never "shodan_api_key"
        call_args_list = [call.args[0] for call in mock_cm.get_api_key.call_args_list]
        assert "shodan" in call_args_list, (
            f"Expected get_api_key('shodan') call, got: {call_args_list}"
        )
        assert "shodan_api_key" not in call_args_list, (
            "get_api_key called with wrong field name 'shodan_api_key'"
        )

    def test_smoke_test_picks_up_shodan_from_config_toml(self, smoke):
        """_resolve_keys returns the Shodan key when it's in config.toml (not SKIP).

        This is the end-to-end regression test: a user with [api_keys] shodan = '...'
        in config.toml must get a non-empty value from _resolve_keys so the module
        is NOT skipped.
        """
        saved = self._isolate_shodan_env()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                test_key = "test-shodan-key-32-chars-xxxxxxxxxx"
                cm = _make_cm(tmp, shodan=test_key)
                keys = smoke._resolve_keys(cm)

            val, src = keys.get("shodan", ("", ""))
            assert val == test_key, (
                f"Expected Shodan key from config.toml, got {val!r}. "
                "Bug: _resolve_keys may still be using wrong field name."
            )
            assert src == "config"
            # Verify the module would NOT be skipped
            status, _msg, _count = (
                smoke._run_shodan.__wrapped__("8.8.8.8", keys, False)
                if hasattr(smoke._run_shodan, "__wrapped__")
                else _assert_not_skipped(keys)
            )
        finally:
            self._restore_env(saved)

    def test_resolve_keys_returns_empty_when_no_env_or_config(self, smoke):
        """When neither env vars nor config provides a key, value is empty string."""
        all_env_vars = [
            "SHODAN_API_KEY",
            "AP_SHODAN_API_KEY",
            "CENSYS_PAT",
            "AP_CENSYS_PAT",
            "ABUSEIPDB_API_KEY",
            "AP_ABUSEIPDB_API_KEY",
            "URLSCAN_API_KEY",
            "AP_URLSCAN_API_KEY",
            "HIBP_API_KEY",
            "AP_HIBP_API_KEY",
            "VIRUSTOTAL_API_KEY",
            "AP_VIRUSTOTAL_API_KEY",
            "AP_VT_API_KEY",
            "VT_API_KEY",
            "OTX_API_KEY",
            "AP_OTX_API_KEY",
            "AP_PASSIVETOTAL_USER",
            "PT_USERNAME",
            "AP_PASSIVETOTAL_KEY",
            "PT_API_KEY",
            "GREYNOISE_API_KEY",
            "AP_GREYNOISE_API_KEY",
        ]
        saved = {k: os.environ.pop(k, None) for k in all_env_vars}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cm = _make_cm(tmp)  # all keys default to ""
                keys = smoke._resolve_keys(cm)

            for name, (val, _src) in keys.items():
                assert val == "", (
                    f"Expected empty value for {name!r} with no config/env, got {val!r}"
                )
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_resolve_keys_reads_from_vendor_env(self, smoke):
        """_resolve_keys picks up SHODAN_API_KEY from environment (vendor layer)."""
        saved = self._isolate_shodan_env()
        try:
            os.environ["SHODAN_API_KEY"] = "test-shodan-key-from-env"
            with tempfile.TemporaryDirectory() as tmp:
                cm = _make_cm(tmp, shodan="")  # no config value
                keys = smoke._resolve_keys(cm)

            val, src = keys.get("shodan", ("", ""))
            assert val == "test-shodan-key-from-env"
            # vendor env → source is "vendor env" (not "env" as in old code)
            assert src == "vendor env"
        finally:
            os.environ.pop("SHODAN_API_KEY", None)
            self._restore_env(saved)

    def test_resolve_keys_config_takes_precedence_over_env(self, smoke):
        """Config value takes precedence over env var for the same key."""
        saved = self._isolate_shodan_env()
        try:
            os.environ["SHODAN_API_KEY"] = "env-key-that-should-lose"
            with tempfile.TemporaryDirectory() as tmp:
                cm = _make_cm(tmp, shodan="config-key-wins-xxxxxxxxxxx")
                keys = smoke._resolve_keys(cm)

            val, src = keys.get("shodan", ("", ""))
            assert val == "config-key-wins-xxxxxxxxxxx"
            assert src == "config"
        finally:
            os.environ.pop("SHODAN_API_KEY", None)
            self._restore_env(saved)

    def test_resolve_keys_censys_uses_pat_field(self, smoke):
        """_resolve_keys returns censys_pat (not censys_id/censys_secret)."""
        with tempfile.TemporaryDirectory() as tmp:
            test_pat = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9-test-pat"
            cm = _make_cm(tmp, censys_pat=test_pat)
            keys = smoke._resolve_keys(cm)

        # New key name is "censys_pat", not "censys_id" or "censys_secret"
        assert "censys_pat" in keys, "Expected 'censys_pat' key in resolved keys"
        val, src = keys["censys_pat"]
        assert val == test_pat
        assert src == "config"
        # Legacy keys must NOT be present
        assert "censys_id" not in keys, "Legacy censys_id should not appear in resolved keys"
        assert "censys_secret" not in keys, "Legacy censys_secret should not appear"


# ---------------------------------------------------------------------------
# AuthenticationError classification: SKIP vs FAIL (closes backlog #48)
# @mock-exempt: mod.hunt() is the external HTTP boundary — it would make a
# live API call. AsyncMock patches the coroutine so we can inject specific
# exception types and verify the _run_* routing logic (AuthenticationError→SKIP,
# httpx errors→FAIL) without network I/O. PluginManager.get_module is patched
# only to return the mock module; all routing logic under test is real Python.
# ---------------------------------------------------------------------------


class TestAuthErrorClassification:
    """_run_* handlers classify AuthenticationError as SKIP and HTTP errors as FAIL.

    Production sequence: _run_shodan (and peers) call asyncio.run(_run_module(mod, ...))
    which calls mod.hunt(). These tests patch mod.hunt() with an AsyncMock that raises
    a controlled exception, then call the real _run_shodan/_run_censys functions to
    verify the try/except routing table is correct.
    """

    def _keys_with_shodan(self) -> dict:
        return {"shodan": ("fake-api-key-32-chars-xxxxxxxxxx", "config")}

    def _keys_with_censys(self) -> dict:
        return {"censys_pat": ("fake-censys-pat-token", "config")}

    def test_authentication_error_classified_as_skip(self, smoke):
        """AuthenticationError from hunt() → SKIP with 'auth: ...' message, count=0.

        This is the canonical DEC-SMOKE-005 test: a module that raises
        AuthenticationError must not produce FAIL (which would signal a broken
        module). The _run_shodan handler catches it and returns SKIP.
        """
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(side_effect=AuthenticationError("invalid token"))

        mock_mgr = MagicMock()
        mock_mgr.get_module.return_value = mock_mod

        with patch("adversary_pursuit.core.plugin_mgr.PluginManager", return_value=mock_mgr):
            status, msg, count = smoke._run_shodan("8.8.8.8", self._keys_with_shodan(), False)

        assert status == smoke.SKIP, f"Expected SKIP, got {status!r}"
        assert msg.startswith("auth:"), f"Expected 'auth: ...' message, got {msg!r}"
        assert count == 0

    def test_http_status_error_still_classified_as_fail(self, smoke):
        """httpx.HTTPStatusError from hunt() → FAIL (real HTTP error, not auth).

        An HTTP 500 from the upstream API is a real module failure — it must not
        be silently converted to SKIP. Only AuthenticationError gets SKIP treatment.
        """
        request = httpx.Request("GET", "https://api.shodan.io/shodan/host/8.8.8.8")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("500 Internal Server Error", request=request, response=response)

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(side_effect=exc)

        mock_mgr = MagicMock()
        mock_mgr.get_module.return_value = mock_mod

        with patch("adversary_pursuit.core.plugin_mgr.PluginManager", return_value=mock_mgr):
            status, msg, count = smoke._run_shodan("8.8.8.8", self._keys_with_shodan(), False)

        assert status == smoke.FAIL, f"Expected FAIL for HTTPStatusError, got {status!r}"
        assert count == 0

    def test_read_timeout_still_classified_as_fail(self, smoke):
        """httpx.ReadTimeout from hunt() → FAIL (network error, not auth).

        A timeout is a real operational failure. It must propagate to FAIL so
        the smoke test correctly signals an environment problem rather than
        silently skipping a broken module.
        """
        request = httpx.Request("GET", "https://api.shodan.io/shodan/host/8.8.8.8")
        exc = httpx.ReadTimeout("timed out reading response", request=request)

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(side_effect=exc)

        mock_mgr = MagicMock()
        mock_mgr.get_module.return_value = mock_mod

        with patch("adversary_pursuit.core.plugin_mgr.PluginManager", return_value=mock_mgr):
            status, msg, count = smoke._run_shodan("8.8.8.8", self._keys_with_shodan(), False)

        assert status == smoke.FAIL, f"Expected FAIL for ReadTimeout, got {status!r}"
        assert count == 0

    def test_censys_authentication_error_classified_as_skip(self, smoke):
        """AuthenticationError from censys hunt() → SKIP (not FAIL).

        Regression guard for the censys-specific handler added in DEC-SMOKE-005.
        Censys PAT rejected by the API raises AuthenticationError; the smoke test
        must return SKIP so a free-tier user with an invalid PAT sees [SKIP] not [FAIL].
        """
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(
            side_effect=AuthenticationError("PAT rejected — check https://app.censys.io")
        )

        mock_mgr = MagicMock()
        mock_mgr.get_module.return_value = mock_mod

        with patch("adversary_pursuit.core.plugin_mgr.PluginManager", return_value=mock_mgr):
            status, msg, count = smoke._run_censys("8.8.8.8", self._keys_with_censys(), False)

        assert status == smoke.SKIP, f"Expected SKIP for Censys AuthenticationError, got {status!r}"
        assert msg.startswith("auth:"), f"Expected 'auth: ...' message, got {msg!r}"
        assert count == 0


# ---------------------------------------------------------------------------
# Helper used by test_smoke_test_picks_up_shodan_from_config_toml
# ---------------------------------------------------------------------------


def _assert_not_skipped(keys: dict) -> tuple:
    """Verify shodan key is present; return a synthetic non-skip result."""
    val, _ = keys.get("shodan", ("", ""))
    assert val, "Shodan key is empty — module would be skipped"
    # Return a synthetic PASS-like tuple (we're not calling the real module here)
    return "PASS", "", 0


# ---------------------------------------------------------------------------
# GreyNoise _run_greynoise handler — SKIP, PASS, and FAIL classification
# ---------------------------------------------------------------------------

# @mock-exempt: mod.hunt() is an async external HTTP boundary (GreyNoise REST API).
# AsyncMock on hunt() exercises the AuthenticationError→SKIP, HTTPStatusError→FAIL
# routing table without a live network call — same exemption as TestAuthErrorClassification.


class TestGreyNoiseRunHandler:
    """_run_greynoise classifies AuthenticationError as SKIP and success as PASS.

    Production sequence: _run_greynoise calls asyncio.run(_run_module(mod, ...))
    which calls mod.hunt(). These tests patch mod.hunt() with AsyncMock that raises
    or returns a controlled value, then call the real _run_greynoise to verify the
    try/except routing table mirrors the DEC-SMOKE-005 contract.

    @decision DEC-TEST-SMOKE-GREYNOISE-001
    @title Mirror TestAuthErrorClassification pattern for GreyNoise handler
    @status accepted
    @rationale _run_greynoise follows the same AuthenticationError→SKIP,
               httpx.HTTPStatusError→FAIL, unhandled→FAIL contract as shodan/censys.
               Tests exercise that contract at the module boundary without live
               network calls, using AsyncMock on hunt() per DEC-TEST-SMOKE-002.
    """

    def _keys_with_greynoise(self) -> dict:
        return {"greynoise": ("fake-gn-api-key-32chars-xxxxx", "config")}

    def test_run_greynoise_skip_on_auth_error(self, smoke):
        """AuthenticationError from hunt() → SKIP with 'auth: ...' message, count=0.

        Exercises DEC-SMOKE-005 for the greynoise handler: a bad API key
        must produce SKIP, not FAIL, so users see [SKIP] not [FAIL] in smoke output.
        """
        mock_mod = MagicMock()  # @mock-exempt: PursuitModule with external hunt() boundary
        mock_mod.hunt = AsyncMock(
            side_effect=AuthenticationError("GreyNoise API key invalid/revoked.")
        )

        mock_mgr = MagicMock()
        mock_mgr.get_module.return_value = mock_mod

        with patch("adversary_pursuit.core.plugin_mgr.PluginManager", return_value=mock_mgr):
            status, msg, count = smoke._run_greynoise("8.8.8.8", self._keys_with_greynoise(), False)

        assert status == smoke.SKIP, f"Expected SKIP for AuthenticationError, got {status!r}"
        assert msg.startswith("auth:"), f"Expected 'auth: ...' prefix, got {msg!r}"
        assert count == 0

    def test_run_greynoise_pass_on_success(self, smoke):
        """A successful hunt() → PASS with result count > 0.

        The 200-response path (or 404→unknown stub) returns a list of SCOs.
        _run_greynoise must map this to PASS.
        """
        mock_mod = MagicMock()  # @mock-exempt: PursuitModule with external hunt() boundary
        mock_mod.hunt = AsyncMock(
            return_value=[
                {
                    "type": "ipv4-addr",
                    "value": "8.8.8.8",
                    "x_greynoise_classification": "benign",
                    "x_greynoise_noise": False,
                    "x_greynoise_riot": True,
                    "x_greynoise_name": "Google Public DNS",
                    "x_greynoise_last_seen": "2026-05-01",
                    "x_greynoise_link": "https://viz.greynoise.io/ip/8.8.8.8",
                }
            ]
        )

        mock_mgr = MagicMock()
        mock_mgr.get_module.return_value = mock_mod

        with patch("adversary_pursuit.core.plugin_mgr.PluginManager", return_value=mock_mgr):
            status, _msg, count = smoke._run_greynoise(
                "8.8.8.8", self._keys_with_greynoise(), False
            )

        assert status == smoke.PASS, f"Expected PASS for successful hunt(), got {status!r}"
        assert count == 1

    def test_run_greynoise_fail_on_unhandled_exception(self, smoke):
        """An unhandled exception from hunt() → FAIL, not SKIP.

        A network error or unexpected API response is a real failure. It must not
        be silently converted to SKIP — only AuthenticationError gets that treatment.
        """
        import httpx as httpx_mod

        request = httpx_mod.Request("GET", "https://api.greynoise.io/v3/community/8.8.8.8")
        response = httpx_mod.Response(500, request=request)
        exc = httpx_mod.HTTPStatusError(
            "500 Internal Server Error", request=request, response=response
        )

        mock_mod = MagicMock()  # @mock-exempt: PursuitModule with external hunt() boundary
        mock_mod.hunt = AsyncMock(side_effect=exc)

        mock_mgr = MagicMock()
        mock_mgr.get_module.return_value = mock_mod

        with patch("adversary_pursuit.core.plugin_mgr.PluginManager", return_value=mock_mgr):
            status, _msg, count = smoke._run_greynoise(
                "8.8.8.8", self._keys_with_greynoise(), False
            )

        assert status == smoke.FAIL, f"Expected FAIL for HTTPStatusError, got {status!r}"
        assert count == 0

    def test_run_greynoise_skip_when_no_key(self, smoke):
        """_run_greynoise returns SKIP immediately when the greynoise key is empty.

        No HTTP call is made — the handler short-circuits before any network access.
        No mocks needed: the function exits before touching the module layer.
        """
        keys: dict = {"greynoise": ("", "")}
        status, msg, count = smoke._run_greynoise("8.8.8.8", keys, verbose=False)
        assert status == smoke.SKIP
        assert count == 0
