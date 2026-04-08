"""Tests for ConfigManager — Issue #5.

@decision DEC-CONFIG-001
@title Test-first contract for ConfigManager
@status accepted
@rationale Tests define the public API contract before implementation.
           Using tmp_path fixture throughout ensures the real ~/.ap/ directory
           is never touched during testing. monkeypatch isolates env vars per test.

Tests cover:
- Loading config from TOML file
- Saving and loading round-trip
- Environment variable override (monkeypatch)
- Missing config file creates defaults
- Dotted key get/set
- File permissions 0600 after save
- get_api_key returns env var when set, config file value otherwise
- Invalid config values rejected by Pydantic
"""

import stat
from pathlib import Path

import pytest

from adversary_pursuit.core.config import Config, ConfigManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_manager(tmp_path: Path) -> ConfigManager:
    """Return a ConfigManager wired to a temp directory."""
    return ConfigManager(config_dir=tmp_path)


# ---------------------------------------------------------------------------
# Defaults when no config file exists
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_load_returns_config_without_file(self, tmp_path):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        assert isinstance(cfg, Config)

    def test_default_workspace(self, tmp_path):
        cfg = make_manager(tmp_path).load()
        assert cfg.general.default_workspace == "default"

    def test_default_theme(self, tmp_path):
        cfg = make_manager(tmp_path).load()
        assert cfg.general.theme == "dark"

    def test_default_auto_pivot(self, tmp_path):
        cfg = make_manager(tmp_path).load()
        assert cfg.general.auto_pivot is False

    def test_default_auto_pivot_depth(self, tmp_path):
        cfg = make_manager(tmp_path).load()
        assert cfg.general.auto_pivot_depth == 2

    def test_default_api_keys_empty(self, tmp_path):
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.shodan == ""
        assert cfg.api_keys.virustotal == ""
        assert cfg.api_keys.abuseipdb == ""


# ---------------------------------------------------------------------------
# Save / load round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_save_creates_file(self, tmp_path):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        mgr.save(cfg)
        assert (tmp_path / "config.toml").exists()

    def test_round_trip_api_key(self, tmp_path):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "my-shodan-key"
        mgr.save(cfg)

        cfg2 = mgr.load()
        assert cfg2.api_keys.shodan == "my-shodan-key"

    def test_round_trip_general_settings(self, tmp_path):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.general.theme = "light"
        cfg.general.auto_pivot = True
        cfg.general.auto_pivot_depth = 5
        mgr.save(cfg)

        cfg2 = mgr.load()
        assert cfg2.general.theme == "light"
        assert cfg2.general.auto_pivot is True
        assert cfg2.general.auto_pivot_depth == 5

    def test_round_trip_all_api_keys(self, tmp_path):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.virustotal = "vt-key"
        cfg.api_keys.censys_id = "censys-id"
        cfg.api_keys.censys_secret = "censys-secret"
        cfg.api_keys.urlscan = "urlscan-key"
        cfg.api_keys.abuseipdb = "abuse-key"
        cfg.api_keys.hibp = "hibp-key"
        cfg.api_keys.otx = "otx-key"
        cfg.api_keys.passivetotal_user = "pt-user"
        cfg.api_keys.passivetotal_key = "pt-key"
        mgr.save(cfg)

        cfg2 = mgr.load()
        assert cfg2.api_keys.virustotal == "vt-key"
        assert cfg2.api_keys.censys_id == "censys-id"
        assert cfg2.api_keys.censys_secret == "censys-secret"
        assert cfg2.api_keys.urlscan == "urlscan-key"
        assert cfg2.api_keys.abuseipdb == "abuse-key"
        assert cfg2.api_keys.hibp == "hibp-key"
        assert cfg2.api_keys.otx == "otx-key"
        assert cfg2.api_keys.passivetotal_user == "pt-user"
        assert cfg2.api_keys.passivetotal_key == "pt-key"


# ---------------------------------------------------------------------------
# File permissions
# ---------------------------------------------------------------------------

class TestFilePermissions:
    def test_config_file_is_0600(self, tmp_path):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        mgr.save(cfg)
        config_path = tmp_path / "config.toml"
        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0600, got {oct(mode)}"

    def test_permissions_preserved_on_resave(self, tmp_path):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        mgr.save(cfg)
        cfg.api_keys.shodan = "new-key"
        mgr.save(cfg)
        mode = stat.S_IMODE((tmp_path / "config.toml").stat().st_mode)
        assert mode == 0o600


# ---------------------------------------------------------------------------
# Dotted key get/set
# ---------------------------------------------------------------------------

class TestDottedKeys:
    def test_get_api_key_dotted(self, tmp_path):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "shodankey"
        mgr.save(cfg)
        assert mgr.get("api_keys.shodan") == "shodankey"

    def test_get_general_setting(self, tmp_path):
        mgr = make_manager(tmp_path)
        assert mgr.get("general.theme") == "dark"

    def test_set_saves_value(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.set("api_keys.virustotal", "vt-123")
        assert mgr.get("api_keys.virustotal") == "vt-123"

    def test_set_persists_across_reload(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.set("general.theme", "light")

        mgr2 = make_manager(tmp_path)
        assert mgr2.get("general.theme") == "light"

    def test_get_nonexistent_key_raises(self, tmp_path):
        mgr = make_manager(tmp_path)
        with pytest.raises((KeyError, AttributeError, ValueError)):
            mgr.get("nonexistent.key")


# ---------------------------------------------------------------------------
# Environment variable override
# ---------------------------------------------------------------------------

class TestEnvVarOverride:
    def test_shodan_env_overrides_file(self, tmp_path, monkeypatch):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "file-key"
        mgr.save(cfg)

        monkeypatch.setenv("AP_SHODAN_API_KEY", "env-key")
        cfg2 = mgr.load()
        assert cfg2.api_keys.shodan == "env-key"

    def test_virustotal_env_overrides_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_VT_API_KEY", "vt-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.virustotal == "vt-env"

    def test_abuseipdb_env_overrides(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_ABUSEIPDB_API_KEY", "abuse-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.abuseipdb == "abuse-env"

    def test_censys_id_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_CENSYS_API_ID", "censys-id-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.censys_id == "censys-id-env"

    def test_censys_secret_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_CENSYS_API_SECRET", "censys-secret-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.censys_secret == "censys-secret-env"

    def test_urlscan_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_URLSCAN_API_KEY", "urlscan-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.urlscan == "urlscan-env"

    def test_hibp_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_HIBP_API_KEY", "hibp-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.hibp == "hibp-env"

    def test_otx_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_OTX_API_KEY", "otx-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.otx == "otx-env"

    def test_passivetotal_user_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_PT_USER", "pt-user-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.passivetotal_user == "pt-user-env"

    def test_passivetotal_key_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_PT_API_KEY", "pt-key-env")
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.passivetotal_key == "pt-key-env"

    def test_env_absent_returns_file_value(self, tmp_path, monkeypatch):
        """When env var is not set, the file value should be used."""
        monkeypatch.delenv("AP_SHODAN_API_KEY", raising=False)
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "file-only"
        mgr.save(cfg)
        cfg2 = mgr.load()
        assert cfg2.api_keys.shodan == "file-only"


# ---------------------------------------------------------------------------
# get_api_key method
# ---------------------------------------------------------------------------

class TestGetApiKey:
    def test_returns_none_when_not_set(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AP_SHODAN_API_KEY", raising=False)
        mgr = make_manager(tmp_path)
        result = mgr.get_api_key("shodan")
        assert result is None or result == ""

    def test_returns_env_var_value(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_SHODAN_API_KEY", "env-shodan")
        mgr = make_manager(tmp_path)
        assert mgr.get_api_key("shodan") == "env-shodan"

    def test_env_takes_precedence_over_config(self, tmp_path, monkeypatch):
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "config-value"
        mgr.save(cfg)

        monkeypatch.setenv("AP_SHODAN_API_KEY", "env-value")
        assert mgr.get_api_key("shodan") == "env-value"

    def test_falls_back_to_config_when_env_absent(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AP_SHODAN_API_KEY", raising=False)
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "config-shodan"
        mgr.save(cfg)
        assert mgr.get_api_key("shodan") == "config-shodan"

    def test_virustotal_via_get_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_VT_API_KEY", "vt-via-env")
        assert make_manager(tmp_path).get_api_key("virustotal") == "vt-via-env"

    def test_abuseipdb_via_get_api_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_ABUSEIPDB_API_KEY", "abuse-via-env")
        assert make_manager(tmp_path).get_api_key("abuseipdb") == "abuse-via-env"

    def test_unknown_service_returns_none(self, tmp_path):
        mgr = make_manager(tmp_path)
        result = mgr.get_api_key("nonexistent_service_xyz")
        assert result is None


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------

class TestPydanticValidation:
    def test_invalid_auto_pivot_depth_rejected(self, tmp_path):
        """auto_pivot_depth must be a positive integer."""
        from pydantic import ValidationError
        from adversary_pursuit.core.config import GeneralConfig
        with pytest.raises(ValidationError):
            GeneralConfig(auto_pivot_depth=-1)

    def test_invalid_theme_rejected(self, tmp_path):
        """theme must be 'dark' or 'light'."""
        from pydantic import ValidationError
        from adversary_pursuit.core.config import GeneralConfig
        with pytest.raises(ValidationError):
            GeneralConfig(theme="neon-rainbow")


# ---------------------------------------------------------------------------
# Config directory creation
# ---------------------------------------------------------------------------

class TestDirCreation:
    def test_creates_config_dir_on_save(self, tmp_path):
        config_dir = tmp_path / "nested" / "ap"
        mgr = ConfigManager(config_dir=config_dir)
        cfg = mgr.load()
        mgr.save(cfg)
        assert config_dir.exists()
        assert (config_dir / "config.toml").exists()
