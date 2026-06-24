"""Tests for core/module_credentials.py — shared per-module credential resolver.

Production sequence: resolve_module_credentials(module_path, config_mgr) is called
by both agent/tools.py::run_module (chat agent path) and core/console.py::_initialize_module
(REPL hunt path) to produce the init_config dict for PursuitModule.initialize().

@decision DEC-MODULE-CREDS-SHARED-001
@title Single authority for per-module credential resolution (test coverage)
@status accepted
@rationale Both the chat agent and the REPL call the same resolver. These tests verify
    the resolver's precedence logic: CREDENTIAL_BUILDERS first, then SERVICE_NAMES,
    then path-tail fallback. ConfigManager is mocked because it reads config files
    and env vars — an external I/O boundary. The resolver logic is exercised with real
    code; only the I/O boundary is replaced.

# @mock-exempt: ConfigManager reads config files and env vars — it is an external
#   I/O boundary. Mocking it keeps tests fast, deterministic, and network-free while
#   the resolver logic itself (SERVICE_NAMES, CREDENTIAL_BUILDERS, fallback) is
#   exercised with real code paths, not mocks.
"""

from __future__ import annotations

from unittest.mock import Mock  # @mock-exempt: ConfigManager is external I/O boundary

from adversary_pursuit.core.module_credentials import (
    CREDENTIAL_BUILDERS,
    SERVICE_NAMES,
    resolve_module_credentials,
)


class TestResolveModuleCredentials:
    """Unit tests for resolve_module_credentials() precedence logic."""

    def test_keyless_module_returns_empty_dict(self):
        """dns_resolve, whois_lookup, and F61 modules return {} — no API key needed."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        assert resolve_module_credentials("osint/dns_resolve", cfg) == {}
        assert resolve_module_credentials("osint/whois_lookup", cfg) == {}
        assert resolve_module_credentials("osint/crtsh", cfg) == {}
        assert resolve_module_credentials("cti/threatfox", cfg) == {}
        assert resolve_module_credentials("cti/urlhaus", cfg) == {}
        assert resolve_module_credentials("cti/malwarebazaar", cfg) == {}
        # ConfigManager must not be called for key-free modules
        cfg.get_api_key.assert_not_called()

    def test_single_key_module_returns_api_key_dict(self):
        """virustotal returns {"api_key": <value>} via the SERVICE_NAMES map."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_api_key.return_value = "secret-vt-key"
        result = resolve_module_credentials("cti/virustotal", cfg)
        assert result == {"api_key": "secret-vt-key"}
        cfg.get_api_key.assert_called_with("virustotal")

    def test_single_key_module_no_key_returns_empty_string(self):
        """When get_api_key returns None, api_key is coerced to empty string."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_api_key.return_value = None
        result = resolve_module_credentials("osint/abuseipdb", cfg)
        assert result == {"api_key": ""}

    def test_shodan_uses_canonical_service_name(self):
        """osint/shodan_ip maps to 'shodan' not 'shodan_ip' — path-tail would be wrong."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_api_key.return_value = "shodan-key"
        result = resolve_module_credentials("osint/shodan_ip", cfg)
        assert result == {"api_key": "shodan-key"}
        cfg.get_api_key.assert_called_with("shodan")

    def test_censys_uses_credential_builder(self):
        """censys_host uses CREDENTIAL_BUILDERS — multi-key auth."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_censys_pat.return_value = "censys-pat-value"
        result = resolve_module_credentials("osint/censys_host", cfg)
        assert result == {"censys_pat": "censys-pat-value"}

    def test_censys_no_pat_returns_empty_string(self):
        """When get_censys_pat returns None, censys_pat is coerced to empty string."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_censys_pat.return_value = None
        result = resolve_module_credentials("osint/censys_host", cfg)
        assert result == {"censys_pat": ""}

    def test_passivetotal_uses_credential_builder(self):
        """passivetotal uses CREDENTIAL_BUILDERS — multi-key auth."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_api_key.side_effect = lambda key: {
            "passivetotal_user": "pt-user",
            "passivetotal_key": "pt-key",
        }.get(key)
        result = resolve_module_credentials("cti/passivetotal", cfg)
        assert result == {"passivetotal_user": "pt-user", "passivetotal_key": "pt-key"}

    def test_unknown_module_path_falls_back_to_path_tail(self):
        """A module not in SERVICE_NAMES or CREDENTIAL_BUILDERS uses the path tail."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_api_key.return_value = "fake-key"
        result = resolve_module_credentials("custom/myservice", cfg)
        assert result == {"api_key": "fake-key"}
        cfg.get_api_key.assert_called_with("myservice")

    def test_unknown_module_no_key_falls_back_to_empty(self):
        """Path-tail fallback: if get_api_key returns None, api_key is ''."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_api_key.return_value = None
        result = resolve_module_credentials("custom/unknownplugin", cfg)
        assert result == {"api_key": ""}

    def test_result_is_plain_dict(self):
        """resolve_module_credentials always returns a plain dict (not ConfigManager)."""
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_api_key.return_value = "key"
        result = resolve_module_credentials("cti/virustotal", cfg)
        assert isinstance(result, dict)

    def test_dict_get_with_default_works(self):
        """The returned dict supports .get('api_key', '') without raising.

        This is the exact access pattern modules use inside initialize():
            self._config.get("api_key", "")
        ConfigManager.get() raises KeyError on miss; the dict must support 2-arg get.
        This test guards against AP #97 / AP #98 regression class.
        """
        # @mock-exempt: ConfigManager is external I/O boundary
        cfg = Mock()
        cfg.get_api_key.return_value = "vt-key"
        result = resolve_module_credentials("cti/virustotal", cfg)
        # Real modules call this exact pattern:
        assert result.get("api_key", "") == "vt-key"
        # Unknown key with default must not raise:
        assert result.get("nonexistent_key", "fallback") == "fallback"


class TestServiceNamesMapping:
    """Spot-checks on the SERVICE_NAMES registry."""

    def test_known_modules_are_mapped(self):
        """Key modules have correct canonical service names."""
        assert SERVICE_NAMES["cti/virustotal"] == "virustotal"
        # Critical: path tail "shodan_ip" != canonical "shodan"
        assert SERVICE_NAMES["osint/shodan_ip"] == "shodan"
        assert SERVICE_NAMES["osint/abuseipdb"] == "abuseipdb"
        assert SERVICE_NAMES["osint/urlscan"] == "urlscan"
        assert SERVICE_NAMES["cti/otx"] == "otx"

    def test_keyless_modules_map_to_none(self):
        """Keyless modules are mapped to None."""
        assert SERVICE_NAMES["osint/dns_resolve"] is None
        assert SERVICE_NAMES["osint/whois_lookup"] is None
        assert SERVICE_NAMES["cti/urlhaus"] is None
        assert SERVICE_NAMES["cti/threatfox"] is None
        assert SERVICE_NAMES["cti/malwarebazaar"] is None
        assert SERVICE_NAMES["osint/crtsh"] is None


class TestCredentialBuilders:
    """Spot-checks on the CREDENTIAL_BUILDERS registry."""

    def test_censys_and_passivetotal_are_registered(self):
        """Multi-key modules must be present."""
        assert "osint/censys_host" in CREDENTIAL_BUILDERS
        assert "cti/passivetotal" in CREDENTIAL_BUILDERS

    def test_virustotal_not_in_credential_builders(self):
        """Single-key modules use the SERVICE_NAMES path, not CREDENTIAL_BUILDERS."""
        assert "cti/virustotal" not in CREDENTIAL_BUILDERS

    def test_dns_resolve_not_in_credential_builders(self):
        """Keyless modules are not in CREDENTIAL_BUILDERS."""
        assert "osint/dns_resolve" not in CREDENTIAL_BUILDERS
