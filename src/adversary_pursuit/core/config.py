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
@title Environment variables applied at query time via get_api_key(), not at load time
@status accepted
@rationale Previously, env vars were applied at load() time, which silently overwrote
           config-stored values. The correct precedence (config wins over env) requires
           the lookup to happen at get_api_key() call time, not at load time. load()
           now returns the raw config values from disk without env mutation. This means
           the cached Config object always reflects what the user explicitly persisted,
           and get_api_key() implements the full 3-layer chain on each call.

@decision DEC-AGENT-CONFIG-KEY-RESOLUTION-001
@title API key resolution: config.toml > AP_<SERVICE>_API_KEY env > <SERVICE>_API_KEY env
@status accepted
@rationale The user-reported bug was that wizard-saved config values were silently
           overridden by env vars because load() stomped stored values with env values.
           The correct precedence, from highest to lowest:
             1. Explicit value in ~/.ap/config.toml (set by wizard or hand-edit).
                User's explicit persistent choice must always win — this is the
                "I configured this tool" assertion.
             2. AP_<SERVICE>_API_KEY — project-namespaced env var for per-session
                override without touching config. Takes precedence over vendor-default
                env var so operators can inject AP_SHODAN_API_KEY to override a
                shell-level SHODAN_API_KEY without editing the file.
             3. <SERVICE>_API_KEY — vendor-convention env var (SHODAN_API_KEY,
                ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.). Honoring vendor convention
                means users don't need to double-set keys they already have in .zshrc.
             4. None — the caller decides how to handle a missing key.
           This same precedence applies to CTI service keys and LLM provider keys.
           load() no longer mutates cfg.api_keys with env values — those overrides
           belonged to get_api_key(), not to load().

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
# Environment variable mappings for API key resolution
#
# Two layers of env var support (DEC-AGENT-CONFIG-KEY-RESOLUTION-001):
#   Layer 2: AP_<SERVICE>_API_KEY — project-namespaced, takes precedence over vendor.
#   Layer 3: <SERVICE>_API_KEY   — vendor convention (SHODAN_API_KEY, ANTHROPIC_API_KEY…)
#
# For services whose vendor env var name differs from <SERVICE>_API_KEY the
# canonical name is listed explicitly in _VENDOR_ENV_VAR_MAP.  When no entry
# exists the code falls back to f"{service.upper()}_API_KEY" automatically.
# ---------------------------------------------------------------------------

# Layer 2: AP-prefixed project env vars.  Checked after config, before vendor env.
_AP_ENV_VAR_MAP: dict[str, str] = {
    "shodan": "AP_SHODAN_API_KEY",
    "virustotal": "AP_VIRUSTOTAL_API_KEY",
    "censys_id": "AP_CENSYS_ID",
    "censys_secret": "AP_CENSYS_SECRET",
    "urlscan": "AP_URLSCAN_API_KEY",
    "abuseipdb": "AP_ABUSEIPDB_API_KEY",
    "hibp": "AP_HIBP_API_KEY",
    "otx": "AP_OTX_API_KEY",
    "passivetotal_user": "AP_PASSIVETOTAL_USER",
    "passivetotal_key": "AP_PASSIVETOTAL_KEY",
    # Provider keys — AP-prefixed form
    "agent_anthropic": "AP_ANTHROPIC_API_KEY",
    "agent_openai": "AP_OPENAI_API_KEY",
    "agent_openrouter": "AP_OPENROUTER_API_KEY",
    "agent_google": "AP_GOOGLE_API_KEY",
}

# Layer 3: Vendor-convention env vars.  Non-obvious names listed explicitly;
# the fallback for unlisted services is f"{service.upper()}_API_KEY".
_VENDOR_ENV_VAR_MAP: dict[str, str] = {
    "shodan": "SHODAN_API_KEY",
    "virustotal": "VIRUSTOTAL_API_KEY",
    "censys_id": "CENSYS_API_ID",
    "censys_secret": "CENSYS_API_SECRET",
    "urlscan": "URLSCAN_API_KEY",
    "abuseipdb": "ABUSEIPDB_API_KEY",
    "hibp": "HIBP_API_KEY",
    "otx": "OTX_API_KEY",
    "passivetotal_user": "PT_USERNAME",
    "passivetotal_key": "PT_API_KEY",
    # Provider keys — vendor/standard env var names
    "agent_anthropic": "ANTHROPIC_API_KEY",
    "agent_openai": "OPENAI_API_KEY",
    "agent_openrouter": "OPENROUTER_API_KEY",
    "agent_google": "GOOGLE_API_KEY",
}

# Backward-compat alias: old AP_VT_API_KEY and AP_PT_* names still honoured.
# These are checked as additional AP-layer fallbacks in get_api_key().
_LEGACY_AP_ENV_VAR_MAP: dict[str, list[str]] = {
    "virustotal": ["AP_VT_API_KEY"],
    "censys_id": ["AP_CENSYS_API_ID"],
    "censys_secret": ["AP_CENSYS_API_SECRET"],
    "passivetotal_user": ["AP_PT_USER"],
    "passivetotal_key": ["AP_PT_API_KEY"],
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
    # REPL editing mode for prompt_toolkit — "vi" or "emacs".
    # None means "not configured"; defaults to "vi" at runtime.
    editing_mode: str | None = None

    @field_validator("auto_pivot_depth")
    @classmethod
    def depth_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("auto_pivot_depth must be >= 1")
        return v


class ApiKeysConfig(BaseModel):
    """API keys for supported intelligence services.

    Fields default to empty string (not configured).
    Environment variables are resolved at query time via get_api_key() and
    get_provider_api_key(), NOT at load time. See _AP_ENV_VAR_MAP and
    _VENDOR_ENV_VAR_MAP for the env var name lookup tables. Precedence is:
    stored value > AP_<SERVICE>_API_KEY > <SERVICE>_API_KEY > None.
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
            "general": {k: v for k, v in self.general.model_dump().items() if v is not None},
            "api_keys": {k: v for k, v in self.api_keys.model_dump().items() if v is not None},
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
        self._config_dir: Path = Path(config_dir) if config_dir is not None else _DEFAULT_CONFIG_DIR
        self._config_path: Path = self._config_dir / "config.toml"
        self._cache: Config | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> Config:
        """Load config from file and cache it.

        If the config file does not exist, returns a Config with all defaults.
        The loaded config is cached so subsequent get() calls don't re-parse.

        NOTE: Environment variable resolution is intentionally NOT applied here.
        Use get_api_key() to resolve a key with the full 3-layer precedence:
          config.toml > AP_<SERVICE>_API_KEY env > <SERVICE>_API_KEY env.
        Applying env overrides at load time would invert that precedence (env
        would silently win over config), breaking the documented contract
        (DEC-AGENT-CONFIG-KEY-RESOLUTION-001).
        """
        if self._config_path.exists():
            with self._config_path.open("rb") as fh:
                raw = tomllib.load(fh)
            general = GeneralConfig(**raw.get("general", {}))
            api_keys = ApiKeysConfig(**raw.get("api_keys", {}))
            cfg = Config(general=general, api_keys=api_keys)
        else:
            cfg = Config()

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
        """Return the API key for *service* using the documented 3-layer precedence.

        Precedence (highest → lowest) per DEC-AGENT-CONFIG-KEY-RESOLUTION-001:
          1. Stored config value (~/.ap/config.toml, written by wizard or hand).
             User's explicit persistent choice wins — this is the "I configured
             this tool" assertion.
          2. AP_<SERVICE>_API_KEY env var — project-namespaced per-session override.
             Also checks legacy AP_* variant names (e.g. AP_VT_API_KEY for VT).
          3. <SERVICE>_API_KEY env var — vendor convention (SHODAN_API_KEY, etc.).
             Honoured so users don't need to double-set keys they already export.
          4. None — key not configured; caller decides how to handle.

        Parameters
        ----------
        service:
            Field name in ApiKeysConfig (e.g. "shodan", "virustotal",
            "censys_id", "censys_secret", "passivetotal_user", "passivetotal_key").
            Unknown service names fall through to None at layer 4.
        """
        # Layer 1: config-stored value (highest precedence)
        cfg = self._cache if self._cache is not None else self.load()
        stored = getattr(cfg.api_keys, service, None)
        if stored:  # empty-string counts as "not set"
            return stored

        # Layer 2: AP-prefixed project env var
        ap_var = _AP_ENV_VAR_MAP.get(service)
        if ap_var:
            val = os.environ.get(ap_var)
            if val:
                return val
        # Also check legacy AP_* names (e.g. AP_VT_API_KEY, AP_PT_USER)
        for legacy_var in _LEGACY_AP_ENV_VAR_MAP.get(service, []):
            val = os.environ.get(legacy_var)
            if val:
                return val

        # Layer 3: vendor-convention env var
        vendor_var = _VENDOR_ENV_VAR_MAP.get(service)
        if vendor_var:
            val = os.environ.get(vendor_var)
            if val:
                return val

        return None

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

    def get_editing_mode(self) -> str:
        """Return the configured REPL editing mode, defaulting to ``"vi"``.

        Checks the ``AP_EDITING_MODE`` environment variable first (values:
        ``"vi"`` or ``"emacs"``), then falls back to the config field, then
        to ``"vi"`` as the hard default.

        Returns
        -------
        str
            ``"vi"`` or ``"emacs"``.
        """
        env_mode = os.environ.get("AP_EDITING_MODE", "").lower()
        if env_mode in ("vi", "emacs"):
            return env_mode
        cfg = self._cache if self._cache is not None else self.load()
        stored = cfg.general.editing_mode
        if stored and stored.lower() in ("vi", "emacs"):
            return stored.lower()
        return "vi"

    def set_editing_mode(self, mode: str) -> None:
        """Persist the REPL editing mode to config.

        Parameters
        ----------
        mode:
            ``"vi"`` or ``"emacs"``.

        Raises
        ------
        ValueError:
            If *mode* is not one of the recognised values.
        """
        if mode.lower() not in ("vi", "emacs"):
            raise ValueError(f"editing_mode must be 'vi' or 'emacs', got {mode!r}")
        cfg = self._cache if self._cache is not None else self.load()
        cfg.general.editing_mode = mode.lower()
        self.save(cfg)

    def get_provider_api_key(self, provider_id: str) -> str | None:
        """Return the API key for *provider_id* using the 3-layer precedence.

        Precedence (highest → lowest) per DEC-AGENT-CONFIG-KEY-RESOLUTION-001:
          1. Stored config value (config.toml field, e.g. agent_anthropic).
          2. AP_<PROVIDER>_API_KEY env var (e.g. AP_ANTHROPIC_API_KEY).
          3. <PROVIDER>_API_KEY vendor convention (e.g. ANTHROPIC_API_KEY).
          4. None — key not configured.

        The env-layer lookup delegates to get_api_key() using the canonical
        service name "agent_<provider_id>" which maps to the correct AP_ and
        vendor env var entries in _AP_ENV_VAR_MAP / _VENDOR_ENV_VAR_MAP.

        Parameters
        ----------
        provider_id:
            One of "anthropic", "openai", "openrouter", "google".
            Returns None immediately for "ollama" (no key needed) and for
            any unknown provider id.
        """
        field = self._PROVIDER_KEY_FIELD.get(provider_id)
        if field is None:
            return None

        # Layer 1: stored config value (highest precedence)
        cfg = self._cache if self._cache is not None else self.load()
        value = getattr(cfg.api_keys, field, None)
        if value:
            return value

        # Layers 2 + 3: env vars via the shared 3-layer resolver.
        # The service name "agent_<provider_id>" is the key used in
        # _AP_ENV_VAR_MAP and _VENDOR_ENV_VAR_MAP for provider keys.
        # We skip layer 1 here (config already checked above) by passing
        # a synthetic service name that has no ApiKeysConfig field — the
        # stored-value lookup in get_api_key() returns falsy for unknown
        # fields, so the env layers fire correctly.
        return self.get_api_key(f"agent_{provider_id.lower()}")

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
