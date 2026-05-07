"""Configuration management for Adversary Pursuit.

Handles loading and saving TOML config from ~/.ap/config.toml, environment
variable overrides for API keys, Pydantic validation, and 0600 file permissions.

@decision DEC-CONFIG-002
@title tomllib (stdlib) for read, tomli_w for write; Pydantic for validation
@status accepted
@rationale tomllib is in the stdlib since Python 3.11 (project requires >=3.12),
           so no read-side dependency. tomli_w provides the write counterpart.
           Pydantic v2 is already a project dependency (used in models) — reusing
           it here gives us field validation and clean model construction without
           adding another library. A separate ApiKeysConfig model keeps the env-var
           override logic co-located with the fields it applies to.

@decision DEC-CONFIG-003
@title Environment variables applied at load time, not via BaseSettings
@status accepted
@rationale Pydantic BaseSettings performs env-var injection at model construction
           time and requires pydantic-settings as an extra install. Since we already
           need post-load mutation (dotted-key set), and because env vars only apply
           to api_keys (not general settings), a manual override step in ConfigManager.load()
           is simpler, more explicit, and avoids an additional dependency.

@decision DEC-AGENT-CONFIG-PROVIDER-001
@title Agent provider/model selection persisted in GeneralConfig + ApiKeysConfig
@status accepted
@rationale The interactive provider wizard needs to persist: (1) the chosen provider
           id ("anthropic", "openai", etc.), (2) the full litellm model string, and
           (3) the provider-specific API key. All three live in config.toml under
           existing sections (general and api_keys) rather than a new section to
           avoid changing the TOML schema shape for downstream consumers. Provider API
           keys are stored in ApiKeysConfig alongside existing service keys — they get
           the same 0600 file permission protection. get_provider_api_key() and
           set_provider_api_key() use a stable string-keyed lookup so new providers
           can be added to the registry without changing this module.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Default config directory (overridable in tests via ConfigManager.__init__)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_DIR = Path.home() / ".ap"

# ---------------------------------------------------------------------------
# Environment variable mapping: api_keys field name → env var name
# ---------------------------------------------------------------------------

_ENV_VAR_MAP: dict[str, str] = {
    "shodan": "AP_SHODAN_API_KEY",
    "virustotal": "AP_VT_API_KEY",
    "censys_id": "AP_CENSYS_API_ID",
    "censys_secret": "AP_CENSYS_API_SECRET",
    "urlscan": "AP_URLSCAN_API_KEY",
    "abuseipdb": "AP_ABUSEIPDB_API_KEY",
    "hibp": "AP_HIBP_API_KEY",
    "otx": "AP_OTX_API_KEY",
    "passivetotal_user": "AP_PT_USER",
    "passivetotal_key": "AP_PT_API_KEY",
}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class GeneralConfig(BaseModel):
    """General application settings."""

    default_workspace: str = "default"
    theme: Literal["dark", "light"] = "dark"
    auto_pivot: bool = False
    auto_pivot_depth: int = Field(default=2, ge=1)
    # Agent provider/model selection — set by the interactive wizard.
    # None means "not configured"; wizard will prompt on first chat launch.
    agent_provider: str | None = None
    agent_model: str | None = None

    @field_validator("auto_pivot_depth")
    @classmethod
    def depth_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("auto_pivot_depth must be >= 1")
        return v


class ApiKeysConfig(BaseModel):
    """API keys for supported intelligence services.

    Fields default to empty string (not configured).
    Environment variables override these at load time — see _ENV_VAR_MAP.
    Provider-specific keys for the agent wizard are also stored here so they
    receive the same 0600 file-permission protection as other service keys.
    """

    shodan: str = ""
    virustotal: str = ""
    censys_id: str = ""
    censys_secret: str = ""
    urlscan: str = ""
    abuseipdb: str = ""
    hibp: str = ""
    otx: str = ""
    passivetotal_user: str = ""
    passivetotal_key: str = ""
    # Agent provider API keys — keyed by provider id ("anthropic", "openai", etc.)
    # Stored as nullable so TOML round-trips cleanly when not yet set.
    agent_anthropic: str | None = None
    agent_openai: str | None = None
    agent_openrouter: str | None = None
    agent_google: str | None = None


class Config(BaseModel):
    """Top-level configuration model."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    api_keys: ApiKeysConfig = Field(default_factory=ApiKeysConfig)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for TOML serialisation.

        None values are excluded because tomli_w cannot serialise Python None.
        TOML has no null type; absent fields round-trip as their Pydantic default
        (None) when the key is not present in the file — this is the correct
        representation for "not yet configured" optional fields.
        """
        return {
            "general": {
                k: v for k, v in self.general.model_dump().items() if v is not None
            },
            "api_keys": {
                k: v for k, v in self.api_keys.model_dump().items() if v is not None
            },
        }


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------


class ConfigManager:
    """Loads, validates, and persists application configuration.

    Usage
    -----
    mgr = ConfigManager()          # uses ~/.ap/config.toml
    cfg = mgr.load()               # load (creates defaults if absent)
    cfg.api_keys.shodan = "key"
    mgr.save(cfg)                  # write back with 0600 permissions

    mgr.get("api_keys.shodan")     # dotted-key read
    mgr.set("general.theme", "light")  # dotted-key write + save

    mgr.get_api_key("shodan")      # env-var-first lookup
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        """Initialise with optional config directory override (for testing).

        Parameters
        ----------
        config_dir:
            Directory that contains config.toml.  Defaults to ~/.ap/.
            Pass ``tmp_path`` in tests to avoid touching the real user config.
        """
        self._config_dir: Path = (
            Path(config_dir) if config_dir is not None else _DEFAULT_CONFIG_DIR
        )
        self._config_path: Path = self._config_dir / "config.toml"
        self._cache: Config | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> Config:
        """Load config from file, applying environment variable overrides.

        If the config file does not exist, returns a Config with all defaults.
        Environment variables always take precedence over file values.
        The loaded config is cached so subsequent get() calls don't re-parse.
        """
        if self._config_path.exists():
            with self._config_path.open("rb") as fh:
                raw = tomllib.load(fh)
            general = GeneralConfig(**raw.get("general", {}))
            api_keys = ApiKeysConfig(**raw.get("api_keys", {}))
            cfg = Config(general=general, api_keys=api_keys)
        else:
            cfg = Config()

        # Apply environment variable overrides
        for field_name, env_var in _ENV_VAR_MAP.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                setattr(cfg.api_keys, field_name, env_value)

        self._cache = cfg
        return cfg

    def save(self, config: Config) -> None:
        """Save config to file with 0600 permissions (protects API keys).

        Creates the config directory if it does not exist.
        File is written atomically via a temporary file to avoid partial writes.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)

        toml_bytes = tomli_w.dumps(config.to_dict()).encode()

        # Write to a temp file first, then rename (atomic on POSIX)
        tmp_path = self._config_path.with_suffix(".toml.tmp")
        tmp_path.write_bytes(toml_bytes)
        tmp_path.chmod(0o600)
        tmp_path.rename(self._config_path)

        self._cache = config

    def get(self, key: str) -> Any:
        """Get a config value by dotted key (e.g. 'api_keys.shodan').

        Parameters
        ----------
        key:
            Dotted path of the form ``<section>.<field>`` where section is
            one of ``general`` or ``api_keys``.

        Raises
        ------
        KeyError:
            If the section or field does not exist.
        """
        cfg = self._cache if self._cache is not None else self.load()
        parts = key.split(".", 1)
        if len(parts) != 2:
            raise KeyError(f"Key must be of the form 'section.field', got: {key!r}")
        section, field = parts
        section_obj = getattr(cfg, section, _MISSING)
        if section_obj is _MISSING:
            raise KeyError(f"Unknown config section: {section!r}")
        value = getattr(section_obj, field, _MISSING)
        if value is _MISSING:
            raise KeyError(f"Unknown field {field!r} in section {section!r}")
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a config value by dotted key and persist to disk.

        Parameters
        ----------
        key:
            Dotted path of the form ``<section>.<field>``.
        value:
            New value to assign.  Pydantic validation runs on the enclosing
            model when saving.
        """
        cfg = self._cache if self._cache is not None else self.load()
        parts = key.split(".", 1)
        if len(parts) != 2:
            raise KeyError(f"Key must be of the form 'section.field', got: {key!r}")
        section, field = parts
        section_obj = getattr(cfg, section, _MISSING)
        if section_obj is _MISSING:
            raise KeyError(f"Unknown config section: {section!r}")
        if not hasattr(section_obj, field):
            raise KeyError(f"Unknown field {field!r} in section {section!r}")
        setattr(section_obj, field, value)
        self.save(cfg)

    def get_api_key(self, service: str) -> str | None:
        """Return the API key for *service*, with env var taking precedence.

        Checks the environment variable first (same mapping as _ENV_VAR_MAP),
        then falls back to the config file value.  Returns ``None`` if the
        service is unknown or the key is unset.

        Parameters
        ----------
        service:
            One of the field names in ApiKeysConfig (e.g. "shodan", "virustotal").
        """
        # Check env var first
        env_var = _ENV_VAR_MAP.get(service)
        if env_var:
            env_value = os.environ.get(env_var)
            if env_value is not None:
                return env_value

        # Fall back to config file value
        if service not in _ENV_VAR_MAP:
            return None

        cfg = self._cache if self._cache is not None else self.load()
        value = getattr(cfg.api_keys, service, None)
        # Return None for empty string (not configured)
        return value if value else None

    # ------------------------------------------------------------------
    # Agent provider/model helpers (DEC-AGENT-CONFIG-PROVIDER-001)
    # ------------------------------------------------------------------

    # Mapping from provider_id → ApiKeysConfig field name.
    # Kept here (not in provider_setup.py) so config.py stays self-contained
    # and can be imported without pulling in wizard dependencies.
    _PROVIDER_KEY_FIELD: dict[str, str] = {
        "anthropic": "agent_anthropic",
        "openai": "agent_openai",
        "openrouter": "agent_openrouter",
        "google": "agent_google",
    }

    def get_agent_provider(self) -> str | None:
        """Return the configured agent provider id, or None if not set."""
        cfg = self._cache if self._cache is not None else self.load()
        return cfg.general.agent_provider or None

    def get_agent_model(self) -> str | None:
        """Return the configured litellm model string, or None if not set."""
        cfg = self._cache if self._cache is not None else self.load()
        return cfg.general.agent_model or None

    def set_agent_selection(self, provider: str, model: str) -> None:
        """Persist provider id and litellm model string to config.

        Parameters
        ----------
        provider:
            Provider id string (e.g. "anthropic", "openai").
        model:
            Full litellm model string (e.g. "claude-3-5-sonnet-20241022",
            "openai/gpt-4o", "gemini/gemini-2.0-flash-exp").
        """
        cfg = self._cache if self._cache is not None else self.load()
        cfg.general.agent_provider = provider
        cfg.general.agent_model = model
        self.save(cfg)

    def get_provider_api_key(self, provider_id: str) -> str | None:
        """Return the stored API key for *provider_id*, or None.

        Parameters
        ----------
        provider_id:
            One of "anthropic", "openai", "openrouter", "google".
            Returns None immediately for "ollama" (no key needed).
        """
        field = self._PROVIDER_KEY_FIELD.get(provider_id)
        if field is None:
            return None
        cfg = self._cache if self._cache is not None else self.load()
        value = getattr(cfg.api_keys, field, None)
        return value if value else None

    def set_provider_api_key(self, provider_id: str, key: str) -> None:
        """Persist the API key for *provider_id*.

        Parameters
        ----------
        provider_id:
            One of "anthropic", "openai", "openrouter", "google".
        key:
            The API key string to persist.

        Raises
        ------
        ValueError:
            If provider_id is not in the known provider map.
        """
        field = self._PROVIDER_KEY_FIELD.get(provider_id)
        if field is None:
            raise ValueError(f"Unknown provider id: {provider_id!r}")
        cfg = self._cache if self._cache is not None else self.load()
        setattr(cfg.api_keys, field, key)
        self.save(cfg)


# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------


class _MissingType:
    """Sentinel for missing attribute lookups (avoids None ambiguity)."""

    def __repr__(self) -> str:
        return "<MISSING>"


_MISSING = _MissingType()
