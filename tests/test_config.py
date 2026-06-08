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
# Environment variable override via get_api_key()
# ---------------------------------------------------------------------------
# NOTE (DEC-CONFIG-003): load() no longer applies env vars to the Config object.
# Env var resolution happens exclusively in get_api_key() at query time.
# These tests call get_api_key() to exercise the 3-layer precedence chain.


class TestEnvVarOverride:
    def test_shodan_ap_env_resolves_via_get_api_key(self, tmp_path, monkeypatch):
        """AP_SHODAN_API_KEY resolves via get_api_key() when no config is set."""
        monkeypatch.setenv("AP_SHODAN_API_KEY", "env-key")
        monkeypatch.delenv("SHODAN_API_KEY", raising=False)
        assert make_manager(tmp_path).get_api_key("shodan") == "env-key"

    def test_virustotal_legacy_ap_env_resolves(self, tmp_path, monkeypatch):
        """Legacy AP_VT_API_KEY resolves via get_api_key() when no config is set."""
        monkeypatch.setenv("AP_VT_API_KEY", "vt-env")
        monkeypatch.delenv("AP_VIRUSTOTAL_API_KEY", raising=False)
        monkeypatch.delenv("VIRUSTOTAL_API_KEY", raising=False)
        assert make_manager(tmp_path).get_api_key("virustotal") == "vt-env"

    def test_abuseipdb_ap_env_resolves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_ABUSEIPDB_API_KEY", "abuse-env")
        monkeypatch.delenv("ABUSEIPDB_API_KEY", raising=False)
        assert make_manager(tmp_path).get_api_key("abuseipdb") == "abuse-env"

    def test_censys_id_ap_env_resolves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_CENSYS_ID", "censys-id-env")
        monkeypatch.delenv("AP_CENSYS_API_ID", raising=False)
        monkeypatch.delenv("CENSYS_API_ID", raising=False)
        assert make_manager(tmp_path).get_api_key("censys_id") == "censys-id-env"

    def test_censys_secret_ap_env_resolves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_CENSYS_SECRET", "censys-secret-env")
        monkeypatch.delenv("AP_CENSYS_API_SECRET", raising=False)
        monkeypatch.delenv("CENSYS_API_SECRET", raising=False)
        assert make_manager(tmp_path).get_api_key("censys_secret") == "censys-secret-env"

    def test_urlscan_ap_env_resolves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_URLSCAN_API_KEY", "urlscan-env")
        monkeypatch.delenv("URLSCAN_API_KEY", raising=False)
        assert make_manager(tmp_path).get_api_key("urlscan") == "urlscan-env"

    def test_hibp_ap_env_resolves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_HIBP_API_KEY", "hibp-env")
        monkeypatch.delenv("HIBP_API_KEY", raising=False)
        assert make_manager(tmp_path).get_api_key("hibp") == "hibp-env"

    def test_otx_ap_env_resolves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_OTX_API_KEY", "otx-env")
        monkeypatch.delenv("OTX_API_KEY", raising=False)
        assert make_manager(tmp_path).get_api_key("otx") == "otx-env"

    def test_passivetotal_user_ap_env_resolves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_PASSIVETOTAL_USER", "pt-user-env")
        monkeypatch.delenv("AP_PT_USER", raising=False)
        monkeypatch.delenv("PT_USERNAME", raising=False)
        assert make_manager(tmp_path).get_api_key("passivetotal_user") == "pt-user-env"

    def test_passivetotal_key_ap_env_resolves(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AP_PASSIVETOTAL_KEY", "pt-key-env")
        monkeypatch.delenv("AP_PT_API_KEY", raising=False)
        monkeypatch.delenv("PT_API_KEY", raising=False)
        assert make_manager(tmp_path).get_api_key("passivetotal_key") == "pt-key-env"

    def test_load_does_not_apply_env_to_config_object(self, tmp_path, monkeypatch):
        """load() returns raw config — env vars are NOT applied (DEC-CONFIG-003).

        Setting AP_SHODAN_API_KEY must NOT mutate cfg.api_keys.shodan returned
        by load(). The config object always reflects only what is on disk.
        """
        monkeypatch.setenv("AP_SHODAN_API_KEY", "env-key")
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        # Disk has no shodan key — load() must return the default empty string,
        # not the env var value.
        assert cfg.api_keys.shodan == ""

    def test_env_absent_returns_file_value(self, tmp_path, monkeypatch):
        """When env var is not set, get_api_key() returns the file value."""
        monkeypatch.delenv("AP_SHODAN_API_KEY", raising=False)
        monkeypatch.delenv("SHODAN_API_KEY", raising=False)
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "file-only"
        mgr.save(cfg)
        assert mgr.get_api_key("shodan") == "file-only"


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

    def test_config_wins_over_env_var(self, tmp_path, monkeypatch):
        """Config-stored value takes precedence over env var (DEC-AGENT-CONFIG-KEY-RESOLUTION-001).

        The old (wrong) behaviour allowed AP_SHODAN_API_KEY to silently
        override a wizard-saved config value. The correct precedence is:
        config.toml > AP_<SERVICE>_API_KEY > <SERVICE>_API_KEY > None.
        """
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "config-value"
        mgr.save(cfg)

        monkeypatch.setenv("AP_SHODAN_API_KEY", "env-value")
        # Config wins — "config-value" must be returned, not "env-value"
        assert mgr.get_api_key("shodan") == "config-value"

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
    def test_invalid_auto_pivot_depth_rejected(self):
        """auto_pivot_depth must be a positive integer."""
        from pydantic import ValidationError

        from adversary_pursuit.core.config import GeneralConfig

        with pytest.raises(ValidationError):
            GeneralConfig(auto_pivot_depth=-1)

    def test_invalid_theme_rejected(self):
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


# ---------------------------------------------------------------------------
# Agent provider/model fields — DEC-AGENT-CONFIG-PROVIDER-001
# ---------------------------------------------------------------------------


class TestAgentProviderFields:
    """Tests for agent_provider, agent_model, and provider API key helpers."""

    def test_defaults_are_none(self, tmp_path):
        mgr = make_manager(tmp_path)
        assert mgr.get_agent_provider() is None
        assert mgr.get_agent_model() is None

    def test_set_agent_selection_persists(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.set_agent_selection("anthropic", "claude-3-5-sonnet-20241022")
        assert mgr.get_agent_provider() == "anthropic"
        assert mgr.get_agent_model() == "claude-3-5-sonnet-20241022"

    def test_set_agent_selection_round_trip(self, tmp_path):
        """Write via one ConfigManager, read back via a fresh one."""
        mgr = make_manager(tmp_path)
        mgr.set_agent_selection("openai", "gpt-4o")

        mgr2 = make_manager(tmp_path)
        assert mgr2.get_agent_provider() == "openai"
        assert mgr2.get_agent_model() == "gpt-4o"

    def test_set_provider_api_key_anthropic(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.set_provider_api_key("anthropic", "sk-ant-test-key")
        assert mgr.get_provider_api_key("anthropic") == "sk-ant-test-key"

    def test_set_provider_api_key_openai(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.set_provider_api_key("openai", "sk-openai-key")
        assert mgr.get_provider_api_key("openai") == "sk-openai-key"

    def test_set_provider_api_key_openrouter(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.set_provider_api_key("openrouter", "sk-or-key")
        assert mgr.get_provider_api_key("openrouter") == "sk-or-key"

    def test_set_provider_api_key_google(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.set_provider_api_key("google", "AIza-google-key")
        assert mgr.get_provider_api_key("google") == "AIza-google-key"

    def test_get_provider_api_key_returns_none_for_ollama(self, tmp_path):
        """Ollama has no API key — get_provider_api_key('ollama') is always None."""
        mgr = make_manager(tmp_path)
        assert mgr.get_provider_api_key("ollama") is None

    def test_set_provider_api_key_unknown_raises(self, tmp_path):
        mgr = make_manager(tmp_path)
        with pytest.raises(ValueError, match="Unknown provider"):
            mgr.set_provider_api_key("unknown_provider_xyz", "some-key")

    def test_get_provider_api_key_unknown_returns_none(self, tmp_path):
        mgr = make_manager(tmp_path)
        assert mgr.get_provider_api_key("unknown_provider_xyz") is None

    def test_provider_key_round_trip(self, tmp_path):
        """Write key via one manager, read back via a fresh one."""
        mgr = make_manager(tmp_path)
        mgr.set_provider_api_key("anthropic", "sk-ant-persist-test")

        mgr2 = make_manager(tmp_path)
        assert mgr2.get_provider_api_key("anthropic") == "sk-ant-persist-test"

    def test_provider_key_file_is_0600(self, tmp_path):
        """Config file retains 0600 permissions after writing provider key."""
        import stat

        mgr = make_manager(tmp_path)
        mgr.set_provider_api_key("openai", "sk-openai-test")
        config_path = tmp_path / "config.toml"
        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0600, got {oct(mode)}"

    def test_full_provider_setup_round_trip(self, tmp_path):
        """Compound test: set provider + model + key; read all back."""
        import stat

        mgr = make_manager(tmp_path)
        mgr.set_agent_selection("openrouter", "openrouter/anthropic/claude-3.5-sonnet")
        mgr.set_provider_api_key("openrouter", "sk-or-compound-test")

        mgr2 = make_manager(tmp_path)
        assert mgr2.get_agent_provider() == "openrouter"
        assert mgr2.get_agent_model() == "openrouter/anthropic/claude-3.5-sonnet"
        assert mgr2.get_provider_api_key("openrouter") == "sk-or-compound-test"

        config_path = tmp_path / "config.toml"
        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600

    def test_agent_model_default_none_in_general_config(self, tmp_path):
        """GeneralConfig defaults agent_provider and agent_model to None."""
        from adversary_pursuit.core.config import GeneralConfig

        g = GeneralConfig()
        assert g.agent_provider is None
        assert g.agent_model is None

    def test_api_keys_config_has_agent_fields(self, tmp_path):
        """ApiKeysConfig has agent_anthropic, agent_openai, etc. defaulting to None."""
        from adversary_pursuit.core.config import ApiKeysConfig

        k = ApiKeysConfig()
        assert k.agent_anthropic is None
        assert k.agent_openai is None
        assert k.agent_openrouter is None
        assert k.agent_google is None


# ---------------------------------------------------------------------------
# 3-layer precedence chain — DEC-AGENT-CONFIG-KEY-RESOLUTION-001
# ---------------------------------------------------------------------------


class TestThreeLayerPrecedence:
    """Verify the full config > AP_env > vendor_env > None chain for get_api_key()."""

    def test_config_wins_over_both_env_layers(self, tmp_path, monkeypatch):
        """Config-stored value beats AP_* env and vendor env simultaneously."""
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.shodan = "config-stored"
        mgr.save(cfg)

        monkeypatch.setenv("AP_SHODAN_API_KEY", "ap-env")
        monkeypatch.setenv("SHODAN_API_KEY", "vendor-env")

        assert mgr.get_api_key("shodan") == "config-stored"

    def test_ap_prefixed_env_wins_over_vendor_env(self, tmp_path, monkeypatch):
        """AP_<SERVICE>_API_KEY beats the vendor-convention env var."""
        monkeypatch.setenv("AP_SHODAN_API_KEY", "ap_val")
        monkeypatch.setenv("SHODAN_API_KEY", "vendor_val")

        assert make_manager(tmp_path).get_api_key("shodan") == "ap_val"

    def test_vendor_env_used_when_no_config_no_ap_prefix(self, tmp_path, monkeypatch):
        """Vendor env var (SHODAN_API_KEY) is the last non-None layer."""
        monkeypatch.delenv("AP_SHODAN_API_KEY", raising=False)
        monkeypatch.setenv("SHODAN_API_KEY", "vendor_only")

        assert make_manager(tmp_path).get_api_key("shodan") == "vendor_only"

    def test_returns_none_when_all_layers_empty(self, tmp_path, monkeypatch):
        """None is returned when config, AP_ env, and vendor env are all absent."""
        monkeypatch.delenv("AP_SHODAN_API_KEY", raising=False)
        monkeypatch.delenv("SHODAN_API_KEY", raising=False)

        result = make_manager(tmp_path).get_api_key("shodan")
        assert result is None

    def test_censys_id_and_secret_resolve_independently(self, tmp_path, monkeypatch):
        """censys_id and censys_secret can each come from different layers."""
        # id from config, secret from env
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.censys_id = "stored-id"
        mgr.save(cfg)

        monkeypatch.delenv("AP_CENSYS_ID", raising=False)
        monkeypatch.delenv("AP_CENSYS_API_ID", raising=False)
        monkeypatch.delenv("CENSYS_API_ID", raising=False)
        monkeypatch.setenv("AP_CENSYS_SECRET", "env-secret")
        monkeypatch.delenv("AP_CENSYS_API_SECRET", raising=False)
        monkeypatch.delenv("CENSYS_API_SECRET", raising=False)

        assert mgr.get_api_key("censys_id") == "stored-id"
        assert mgr.get_api_key("censys_secret") == "env-secret"

    def test_passivetotal_user_and_key_resolve_independently(self, tmp_path, monkeypatch):
        """passivetotal_user and passivetotal_key can each come from different layers."""
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.passivetotal_user = "stored-user"
        mgr.save(cfg)

        monkeypatch.delenv("AP_PASSIVETOTAL_USER", raising=False)
        monkeypatch.delenv("AP_PT_USER", raising=False)
        monkeypatch.delenv("PT_USERNAME", raising=False)
        monkeypatch.setenv("AP_PASSIVETOTAL_KEY", "env-key")
        monkeypatch.delenv("AP_PT_API_KEY", raising=False)
        monkeypatch.delenv("PT_API_KEY", raising=False)

        assert mgr.get_api_key("passivetotal_user") == "stored-user"
        assert mgr.get_api_key("passivetotal_key") == "env-key"

    def test_get_provider_api_key_anthropic_3_layer_chain(self, tmp_path, monkeypatch):
        """Provider key: stored config wins over both env layers."""
        mgr = make_manager(tmp_path)
        mgr.set_provider_api_key("anthropic", "sk-ant-stored")

        monkeypatch.setenv("AP_ANTHROPIC_API_KEY", "ap-env-val")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "vendor-env-val")

        # Layer 1 (stored config) wins
        assert mgr.get_provider_api_key("anthropic") == "sk-ant-stored"

    @pytest.mark.parametrize(
        "provider_id,ap_var,ap_value,vendor_var,vendor_value",
        [
            ("anthropic", "AP_ANTHROPIC_API_KEY", "ap-ant-key", "ANTHROPIC_API_KEY", "ant-vendor"),
            ("openai", "AP_OPENAI_API_KEY", "ap-oai-key", "OPENAI_API_KEY", "oai-vendor"),
            ("openrouter", "AP_OPENROUTER_API_KEY", "ap-or-key", "OPENROUTER_API_KEY", "or-vendor"),
            ("google", "AP_GOOGLE_API_KEY", "ap-gg-key", "GOOGLE_API_KEY", "gg-vendor"),
        ],
    )
    def test_get_provider_api_key_uses_ap_env_when_no_config(
        self,
        tmp_path,
        monkeypatch,
        provider_id,
        ap_var,
        ap_value,
        vendor_var,
        vendor_value,
    ):
        """Layer 2 (AP_<PROVIDER>_API_KEY) is honoured when no config is stored.

        Regression guard for the bug where get_provider_api_key() only read the
        stored config field and silently returned None when no wizard config existed,
        even if the user had AP_ANTHROPIC_API_KEY (or equivalent) set in their shell.
        """
        mgr = make_manager(tmp_path)
        # No stored config — both env layers should be reachable
        monkeypatch.setenv(ap_var, ap_value)
        monkeypatch.setenv(vendor_var, vendor_value)

        # AP_* layer wins over vendor layer
        assert mgr.get_provider_api_key(provider_id) == ap_value

    @pytest.mark.parametrize(
        "provider_id,ap_var,vendor_var,vendor_value",
        [
            ("anthropic", "AP_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", "ant-vendor-only"),
            ("openai", "AP_OPENAI_API_KEY", "OPENAI_API_KEY", "oai-vendor-only"),
            ("openrouter", "AP_OPENROUTER_API_KEY", "OPENROUTER_API_KEY", "or-vendor-only"),
            ("google", "AP_GOOGLE_API_KEY", "GOOGLE_API_KEY", "gg-vendor-only"),
        ],
    )
    def test_get_provider_api_key_uses_vendor_env_when_no_config_no_ap(
        self,
        tmp_path,
        monkeypatch,
        provider_id,
        ap_var,
        vendor_var,
        vendor_value,
    ):
        """Layer 3 (vendor env var) is honoured when no config and no AP_ env var.

        Ensures that ANTHROPIC_API_KEY (and equivalents) already exported in the
        user's shell are picked up without requiring AP_* duplication.
        """
        mgr = make_manager(tmp_path)
        # No stored config; AP_ var absent; vendor var present
        monkeypatch.delenv(ap_var, raising=False)
        monkeypatch.setenv(vendor_var, vendor_value)

        assert mgr.get_provider_api_key(provider_id) == vendor_value

    def test_load_does_not_mutate_api_keys_from_env(self, tmp_path, monkeypatch):
        """load() does not inject env var values into the Config object (DEC-CONFIG-003).

        This is the DEC-CONFIG-003 regression guard: the old behaviour ran env-var
        substitution inside load() which silently inverted the precedence. load()
        must return exactly what is on disk — no env-var mutation.
        """
        monkeypatch.setenv("AP_SHODAN_API_KEY", "injected-by-env")
        monkeypatch.setenv("AP_VIRUSTOTAL_API_KEY", "vt-injected")

        mgr = make_manager(tmp_path)
        cfg = mgr.load()

        # Disk has no values — load() must return the defaults, not env values
        assert cfg.api_keys.shodan == ""
        assert cfg.api_keys.virustotal == ""

    def test_vendor_env_var_names_are_honoured(self, tmp_path, monkeypatch):
        """Spot-check: vendor env vars with non-obvious names work correctly."""
        # Censys uses CENSYS_API_ID / CENSYS_API_SECRET (not CENSYS_ID_API_KEY)
        monkeypatch.delenv("AP_CENSYS_ID", raising=False)
        monkeypatch.delenv("AP_CENSYS_API_ID", raising=False)
        monkeypatch.setenv("CENSYS_API_ID", "censys-vendor-id")

        monkeypatch.delenv("AP_PASSIVETOTAL_USER", raising=False)
        monkeypatch.delenv("AP_PT_USER", raising=False)
        monkeypatch.setenv("PT_USERNAME", "pt-vendor-user")

        mgr = make_manager(tmp_path)
        assert mgr.get_api_key("censys_id") == "censys-vendor-id"
        assert mgr.get_api_key("passivetotal_user") == "pt-vendor-user"


# ---------------------------------------------------------------------------
# censys_pat — new field + 3-layer chain (resolves #45, DEC-CONFIG-CENSYS-PAT-001)
# ---------------------------------------------------------------------------


class TestCensysPat:
    """Tests for the censys_pat field and get_censys_pat() helper."""

    def test_ApiKeysConfig_has_censys_pat_field(self, tmp_path):
        """ApiKeysConfig includes censys_pat as a nullable field."""
        from adversary_pursuit.core.config import ApiKeysConfig

        cfg = ApiKeysConfig()
        assert hasattr(cfg, "censys_pat")
        assert cfg.censys_pat is None

    def test_ApiKeysConfig_round_trip_includes_censys_pat(self, tmp_path):
        """censys_pat persists correctly through a config.toml round-trip."""
        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.censys_pat = "test-pat-value"
        mgr.save(cfg)

        mgr2 = make_manager(tmp_path)
        cfg2 = mgr2.load()
        assert cfg2.api_keys.censys_pat == "test-pat-value"

    def test_get_censys_pat_returns_none_when_not_configured(self, tmp_path, monkeypatch):
        """get_censys_pat() returns None when no config, AP env, or vendor env is set."""
        monkeypatch.delenv("AP_CENSYS_PAT", raising=False)
        monkeypatch.delenv("CENSYS_PAT", raising=False)
        mgr = make_manager(tmp_path)
        assert mgr.get_censys_pat() is None

    def test_get_censys_pat_layer1_config_value(self, tmp_path, monkeypatch):
        """Layer 1: stored config value takes highest precedence."""
        monkeypatch.setenv("AP_CENSYS_PAT", "env-pat-layer2")
        monkeypatch.setenv("CENSYS_PAT", "env-pat-layer3")

        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.api_keys.censys_pat = "config-pat-layer1"
        mgr.save(cfg)

        # Config layer wins over both env layers
        assert mgr.get_censys_pat() == "config-pat-layer1"

    def test_get_censys_pat_layer2_ap_env_var(self, tmp_path, monkeypatch):
        """Layer 2: AP_CENSYS_PAT env var used when config has no value."""
        monkeypatch.setenv("AP_CENSYS_PAT", "ap-env-pat")
        monkeypatch.delenv("CENSYS_PAT", raising=False)

        mgr = make_manager(tmp_path)
        assert mgr.get_censys_pat() == "ap-env-pat"

    def test_get_censys_pat_layer3_vendor_env_var(self, tmp_path, monkeypatch):
        """Layer 3: CENSYS_PAT vendor env var used as final fallback."""
        monkeypatch.delenv("AP_CENSYS_PAT", raising=False)
        monkeypatch.setenv("CENSYS_PAT", "vendor-env-pat")

        mgr = make_manager(tmp_path)
        assert mgr.get_censys_pat() == "vendor-env-pat"

    def test_get_censys_pat_3_layer_chain_precedence(self, tmp_path, monkeypatch):
        """Full 3-layer chain: config > AP_CENSYS_PAT > CENSYS_PAT."""
        # Start with only vendor env — should return it
        monkeypatch.delenv("AP_CENSYS_PAT", raising=False)
        monkeypatch.setenv("CENSYS_PAT", "vendor-only")
        mgr = make_manager(tmp_path)
        assert mgr.get_censys_pat() == "vendor-only"

        # Add AP env — should win over vendor
        monkeypatch.setenv("AP_CENSYS_PAT", "ap-env-wins")
        assert mgr.get_censys_pat() == "ap-env-wins"

        # Add config value — should win over both env layers
        cfg = mgr.load()
        cfg.api_keys.censys_pat = "config-wins"
        mgr.save(cfg)
        assert mgr.get_censys_pat() == "config-wins"


# ---------------------------------------------------------------------------
# GreyNoise API key — TOML round-trip and env-var resolution
# ---------------------------------------------------------------------------


class TestGreyNoiseApiKey:
    """ApiKeysConfig.greynoise field persists and resolves via the 3-layer chain.

    Tests mirror the shodan/abuseipdb patterns so all module keys have symmetric
    coverage. The env var names follow the convention declared in config.py:
      AP_GREYNOISE_API_KEY (layer 2) and GREYNOISE_API_KEY (layer 3).
    """

    def test_greynoise_api_key_resolution_from_toml(self, tmp_path):
        """Config-stored greynoise key is returned by get_api_key('greynoise').

        Writes the key via ConfigManager.set(), then reads it back via get_api_key()
        to confirm the TOML round-trip (layer 1 of the 3-layer precedence chain).
        """
        mgr = make_manager(tmp_path)
        mgr.set("api_keys.greynoise", "gn-config-key")
        assert mgr.get_api_key("greynoise") == "gn-config-key"

    def test_greynoise_api_key_resolution_from_env(self, tmp_path, monkeypatch):
        """AP_GREYNOISE_API_KEY env var resolves via get_api_key() when no config is set.

        This exercises layer 2 of the 3-layer precedence chain (AP_<SERVICE>_API_KEY).
        No key is written to the TOML file so the env var must be the winning source.
        """
        monkeypatch.setenv("AP_GREYNOISE_API_KEY", "gn-env-key")
        monkeypatch.delenv("GREYNOISE_API_KEY", raising=False)
        assert make_manager(tmp_path).get_api_key("greynoise") == "gn-env-key"

    def test_greynoise_default_is_empty_string(self, tmp_path, monkeypatch):
        """ApiKeysConfig.greynoise defaults to '' when no config file and no env var."""
        monkeypatch.delenv("AP_GREYNOISE_API_KEY", raising=False)
        monkeypatch.delenv("GREYNOISE_API_KEY", raising=False)
        cfg = make_manager(tmp_path).load()
        assert cfg.api_keys.greynoise == ""

    def test_greynoise_config_wins_over_env(self, tmp_path, monkeypatch):
        """Stored config beats AP_GREYNOISE_API_KEY env var (layer 1 > layer 2)."""
        mgr = make_manager(tmp_path)
        mgr.set("api_keys.greynoise", "gn-stored")
        monkeypatch.setenv("AP_GREYNOISE_API_KEY", "gn-env-value")
        assert mgr.get_api_key("greynoise") == "gn-stored"

    def test_greynoise_vendor_env_var_resolves(self, tmp_path, monkeypatch):
        """GREYNOISE_API_KEY vendor env var is the layer-3 fallback."""
        monkeypatch.delenv("AP_GREYNOISE_API_KEY", raising=False)
        monkeypatch.setenv("GREYNOISE_API_KEY", "gn-vendor-key")
        assert make_manager(tmp_path).get_api_key("greynoise") == "gn-vendor-key"


# ---------------------------------------------------------------------------
# M-6: AutoPivotPolicyConfig.dossier_aware_ranking (DEC-M6-PIVOT-008)
# ---------------------------------------------------------------------------


class TestDossierAwareRankingConfig:
    """M-6 tests for AutoPivotPolicyConfig.dossier_aware_ranking field."""

    def test_dossier_aware_ranking_defaults_to_true(self, tmp_path):
        """AutoPivotPolicyConfig.dossier_aware_ranking defaults to True (M-6 ON by default)."""
        from adversary_pursuit.core.config import AutoPivotPolicyConfig

        cfg = AutoPivotPolicyConfig()
        assert cfg.dossier_aware_ranking is True

    def test_dossier_aware_ranking_false_roundtrip(self, tmp_path):
        """TOML round-trip: writing dossier_aware_ranking=false and reading back preserves it."""
        import tomllib

        from adversary_pursuit.core.config import AutoPivotPolicyConfig

        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        cfg.general.auto_pivot_policy = AutoPivotPolicyConfig(dossier_aware_ranking=False)
        mgr.save(cfg)

        # Re-load from disk
        with (tmp_path / "config.toml").open("rb") as fh:
            raw = tomllib.load(fh)
        assert raw["general"]["auto_pivot_policy"]["dossier_aware_ranking"] is False

        # Full round-trip via ConfigManager.load()
        reloaded = mgr.load()
        assert reloaded.general.auto_pivot_policy.dossier_aware_ranking is False

    def test_backward_compat_missing_field_deserializes_to_true(self, tmp_path):
        """A config TOML that omits dossier_aware_ranking deserializes with default True."""
        import tomli_w

        # Write a config that has auto_pivot_policy but no dossier_aware_ranking key
        toml_dict = {
            "general": {
                "auto_pivot_policy": {
                    "confidence_threshold": 80,
                    "max_per_cascade": 3,
                    # dossier_aware_ranking intentionally absent
                }
            },
            "api_keys": {},
        }
        config_file = tmp_path / "config.toml"
        config_file.write_bytes(tomli_w.dumps(toml_dict).encode())
        config_file.chmod(0o600)

        mgr = make_manager(tmp_path)
        cfg = mgr.load()
        # Pydantic default kicks in for the missing field
        assert cfg.general.auto_pivot_policy.dossier_aware_ranking is True
