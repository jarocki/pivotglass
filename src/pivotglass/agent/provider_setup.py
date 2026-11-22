"""Interactive provider/model setup wizard for the Pivotglass agent.

Prompts the user to choose an LLM provider, enter their API key, verify it
by listing available models, and persist the selection to ~/.pivotglass/config.toml.

@decision DEC-AGENT-PROVIDER-SETUP-001
@title Interactive UX wizard replaces silent PIVOTGLASS_MODEL env-var-only flow
@status accepted
@rationale On first launch of 'pivotglass chat' when no provider is configured the user
           would previously hit a connection error from the Ollama default with
           no guidance. The wizard provides: (1) curated provider list so users
           don't need to know litellm model strings, (2) immediate key validation
           via the provider's list-models endpoint so bad keys are caught before
           any LLM call, (3) model listing so the user picks from what they
           actually have access to, (4) secure persistence at chmod 0600 so keys
           survive session boundaries. Precedence is preserved: explicit model=
           arg > PIVOTGLASS_MODEL env > config.toml > wizard. The wizard is re-runnable
           via the 'model select' chat meta-command. The provider registry is a
           frozen-dataclass list so adding a new provider is a one-line change;
           the rest of the wizard is generic. httpx is a core project dependency
           (pyproject.toml) so no optional-dep guard is needed here.

@decision DEC-AGENT-WIZARD-DOTFILE-001
@title Wizard optionally appends export lines to shell rc with idempotent marker
@status accepted
@rationale User request: the wizard should bootstrap env-var dotfiles on first
           run, not just config.toml. Three save destinations let users choose:
           (1) config.toml only (existing default, always written), (2) config.toml
           plus shell rc append (idempotent marker block prevents duplicate exports
           on re-runs; block is REPLACED rather than duplicated when the wizard
           runs a second time with a different key), (3) stdout-only (user copies
           export lines themselves). Vendor env var names (ANTHROPIC_API_KEY, etc.)
           are preferred so existing shells work out of the box without any
           additional configuration. Shell auto-detected via $SHELL env var so
           zsh users get ~/.zshrc without being asked; fish uses set -x syntax.
           Unknown shells fall back to stdout with a warning rather than writing
           to an unrecognised file. File permissions are preserved across the
           replace-in-place operation.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pivotglass.core.service_endpoints import SERVICE_BASE_URLS

if TYPE_CHECKING:
    from pivotglass.core.config import ConfigManager

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSpec:
    """Immutable descriptor for one LLM provider.

    Attributes
    ----------
    id:
        Internal provider identifier used as the litellm prefix and as the
        key stored in config.toml under general.agent_provider.
    display_name:
        Human-readable name shown in the wizard UI.
    litellm_prefix:
        Prefix used when building the full litellm model string, e.g.
        "gemini" → "gemini/gemini-3.5-flash-lite".  Empty string for providers
        where litellm accepts bare model IDs (Anthropic, OpenAI).
    default_base_url:
        API base URL used when the analyst has not set an override. Request and
        model-list URLs derive from the effective base (DEC-ENDPOINTS-001).
    models_path:
        List-models path relative to the base URL.
    auth_header:
        HTTP header name for the API key.  Empty string means no auth header
        (Ollama local, or Google which uses a query-param instead).
    auth_format:
        Format template for the header value, e.g. "Bearer {key}".
        Empty string when no header auth is used.
    key_in_query:
        True when the API key is passed as a ``key`` query parameter rather
        than an HTTP header (Google Generative Language API).
    needs_api_key:
        False for Ollama (local daemon, no auth required).
    models_json_path:
        Dot-separated path into the response JSON to reach the list of model
        objects, e.g. "data" → response["data"], "models" → response["models"].
    model_id_field:
        Field name on each model object that holds the model identifier string
        the user will see and select.
    """

    id: str
    display_name: str
    litellm_prefix: str
    default_base_url: str
    models_path: str
    auth_header: str
    auth_format: str
    key_in_query: bool
    needs_api_key: bool
    models_json_path: str
    model_id_field: str
    # True when the analyst must supply the base URL (Azure resource, generic gateway).
    requires_base_url: bool = False
    # One-line guidance shown beside the provider in Configuration.
    note: str = ""

    def base_url_for(self, override: str | None = None) -> str:
        return (override or self.default_base_url).rstrip("/")

    def models_url_for(self, override: str | None = None) -> str:
        """Model-list URL under the effective base (DEC-ENDPOINTS-001)."""
        return self.base_url_for(override) + self.models_path

    @property
    def list_models_url(self) -> str:
        return self.models_url_for()


PROVIDERS: list[ProviderSpec] = [
    # Order is the terminal wizard's menu numbering; append new providers at the end.
    ProviderSpec(
        id="anthropic",
        display_name="Anthropic",
        litellm_prefix="",
        default_base_url="https://api.anthropic.com",
        models_path="/v1/models",
        auth_header="x-api-key",
        auth_format="{key}",
        key_in_query=False,
        needs_api_key=True,
        models_json_path="data",
        model_id_field="id",
    ),
    ProviderSpec(
        id="openai",
        display_name="OpenAI",
        litellm_prefix="",
        default_base_url="https://api.openai.com/v1",
        models_path="/models",
        auth_header="Authorization",
        auth_format="Bearer {key}",
        key_in_query=False,
        needs_api_key=True,
        models_json_path="data",
        model_id_field="id",
    ),
    ProviderSpec(
        id="openrouter",
        display_name="OpenRouter",
        litellm_prefix="openrouter",
        default_base_url="https://openrouter.ai/api/v1",
        models_path="/models",
        auth_header="Authorization",
        auth_format="Bearer {key}",
        key_in_query=False,
        needs_api_key=True,
        models_json_path="data",
        model_id_field="id",
    ),
    ProviderSpec(
        id="google",
        display_name="Google (Gemini)",
        litellm_prefix="gemini",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        models_path="/models",
        auth_header="",
        auth_format="",
        key_in_query=True,
        needs_api_key=True,
        models_json_path="models",
        model_id_field="name",
        note="The free tier may use prompts for training; use a paid key for case data.",
    ),
    ProviderSpec(
        id="ollama",
        display_name="Ollama (local)",
        litellm_prefix="ollama",
        default_base_url="http://localhost:11434",
        models_path="/api/tags",
        auth_header="",
        auth_format="",
        key_in_query=False,
        needs_api_key=False,
        models_json_path="models",
        model_id_field="name",
    ),
    ProviderSpec(
        id="azure_openai",
        display_name="Azure OpenAI / AI Foundry",
        litellm_prefix="openai",
        default_base_url="",
        models_path="/models",
        auth_header="api-key",
        auth_format="{key}",
        key_in_query=False,
        needs_api_key=True,
        models_json_path="data",
        model_id_field="id",
        requires_base_url=True,
        note="Base URL is your resource's v1 endpoint, e.g. https://NAME.openai.azure.com/openai/v1",
    ),
    ProviderSpec(
        id="openai_compatible",
        display_name="OpenAI-compatible endpoint",
        litellm_prefix="openai",
        default_base_url="",
        models_path="/models",
        auth_header="Authorization",
        auth_format="Bearer {key}",
        key_in_query=False,
        needs_api_key=False,
        models_json_path="data",
        model_id_field="id",
        requires_base_url=True,
        note="Any gateway or provider with an OpenAI-style /v1 API (LiteLLM proxy, Mistral, Groq, Together, xAI).",
    ),
    ProviderSpec(
        id="local_openai",
        display_name="Local OpenAI-compatible (LM Studio, MLX, llama.cpp)",
        litellm_prefix="openai",
        default_base_url="http://localhost:1234/v1",
        models_path="/models",
        auth_header="",
        auth_format="",
        key_in_query=False,
        needs_api_key=False,
        models_json_path="data",
        model_id_field="id",
    ),
]

# Lookup by id for O(1) access
PROVIDER_BY_ID: dict[str, ProviderSpec] = {p.id: p for p in PROVIDERS}

# Built-in fallback when nothing is configured: local, so no case data leaves the machine.
# qwen3.5:9b fits 16 GB machines; qwen3.6:35b is the better choice on 32 GB+ (research,
# 2026-11-21, docs/plans/V1.4.0_ENRICHMENT_STORY_PLAN.md). qwen2.5:8b was never a real tag.
DEFAULT_LOCAL_MODEL = "ollama/qwen3.5:9b"


def provider_call_kwargs(config_mgr: Any, provider_id: str | None = None) -> dict[str, str]:
    """litellm credential and endpoint kwargs for the configured provider.

    One authority for every litellm call site: the stored key (which takes precedence
    over vendor environment variables) and, when the analyst set a gateway override or
    the provider has no fixed endpoint, ``api_base`` (DEC-ENDPOINTS-001).
    """
    if config_mgr is None:
        return {}
    selected = provider_id or config_mgr.get_agent_provider()
    if not selected:
        return {}
    kwargs: dict[str, str] = {}
    key = config_mgr.get_provider_api_key(selected)
    spec = PROVIDER_BY_ID.get(selected)
    if key:
        kwargs["api_key"] = key
    elif spec is not None and spec.litellm_prefix == "openai":
        # litellm's OpenAI client falls back to OPENAI_API_KEY when no key is given;
        # never let that key travel to a gateway or local server the analyst named.
        kwargs["api_key"] = "not-needed"
    override = config_mgr.get_endpoint_override(selected)
    if override or (spec is not None and spec.litellm_prefix == "openai" and spec.default_base_url):
        kwargs["api_base"] = (spec.base_url_for(override) if spec else override.rstrip("/"))
    return kwargs

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderAuthError(Exception):
    """Raised when the provider rejects the API key (HTTP 401 or 403)."""


class ProviderConnectionError(Exception):
    """Raised when the provider endpoint is unreachable or times out."""


# ---------------------------------------------------------------------------
# Dotfile export helpers
# ---------------------------------------------------------------------------

# Marker strings used to wrap the idempotent export block in shell rc files.
# These must be unique and stable — changing them breaks idempotency for users
# who already have a block from a previous wizard run.
_RC_MARKER_BEGIN = "# >>> pivotglass chat wizard exports — managed by pivotglass; edit at your own risk"
_RC_MARKER_END = "# <<< pivotglass chat wizard exports"

# Map from provider id to the vendor-convention env var name for the API key.
# These names match the entries in core/config._VENDOR_ENV_VAR_MAP so that
# shells configured via this wizard need no additional pivotglass-specific variables.
_PROVIDER_ENV_VAR: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def _detect_shell_rc() -> Path | None:
    """Return the rc file Path for the user's current shell, or None if unknown.

    Detection is based on the ``$SHELL`` environment variable only — we do not
    inspect running processes.  The mapping covers the three shells most likely
    to be encountered:

    * zsh  → ``~/.zshrc``
    * bash → ``~/.bashrc``
    * fish → ``~/.config/fish/config.fish``

    Any other shell returns ``None`` and the caller falls back to stdout.
    """
    shell = os.environ.get("SHELL", "")
    shell_name = Path(shell).name  # e.g. "zsh", "bash", "fish"
    if shell_name == "zsh":
        return Path.home() / ".zshrc"
    if shell_name == "bash":
        return Path.home() / ".bashrc"
    if shell_name == "fish":
        return Path.home() / ".config" / "fish" / "config.fish"
    return None


def _compose_export_lines(provider_id: str, api_key: str) -> list[str]:
    """Return the shell export line(s) for *provider_id* with *api_key*.

    Uses vendor-convention env var names (e.g. ``ANTHROPIC_API_KEY``) so
    existing shell sessions and third-party tools work without additional
    configuration.  Returns an empty list for providers that do not use an API
    key (e.g. Ollama) or for unrecognised provider IDs.
    """
    env_var = _PROVIDER_ENV_VAR.get(provider_id)
    if not env_var:
        return []
    return [f'export {env_var}="{api_key}"']


def _write_rc_with_marker(rc_path: Path, export_lines: list[str]) -> None:
    """Append or replace the wizard's export block in *rc_path* idempotently.

    The block is delimited by ``_RC_MARKER_BEGIN`` / ``_RC_MARKER_END`` lines.
    If the markers are already present the entire block (including markers) is
    replaced in place.  If they are absent the block is appended at the end of
    the file with a leading blank line.

    Original file permissions are preserved after the write.

    Parameters
    ----------
    rc_path:
        Absolute path to the shell rc file (``~/.zshrc``, ``~/.bashrc``, etc.).
        The file is created if it does not exist.
    export_lines:
        Lines to place between the begin and end markers, without newlines.
    """
    new_block = "\n".join([_RC_MARKER_BEGIN, *export_lines, _RC_MARKER_END])

    # Preserve original permissions; default 0o644 for new files
    original_mode: int | None = None
    if rc_path.exists():
        original_mode = stat.S_IMODE(rc_path.stat().st_mode)
        existing = rc_path.read_text(encoding="utf-8")
    else:
        existing = ""

    # Replace an existing marker block, or append a new one
    pattern = re.compile(
        r"\n?" + re.escape(_RC_MARKER_BEGIN) + r".*?" + re.escape(_RC_MARKER_END),
        re.DOTALL,
    )
    if pattern.search(existing):
        updated = pattern.sub("\n" + new_block, existing)
    else:
        # No existing block — append after a blank separator line
        separator = "\n" if existing.endswith("\n") else "\n\n"
        updated = existing + separator + new_block + "\n"

    rc_path.parent.mkdir(parents=True, exist_ok=True)
    rc_path.write_text(updated, encoding="utf-8")
    if original_mode is not None:
        os.chmod(rc_path, original_mode)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _build_model_string(provider: ProviderSpec, model_id: str) -> str:
    """Return the litellm model string for *model_id* under *provider*.

    For providers with an empty prefix (Anthropic, OpenAI) litellm accepts the
    bare model id.  For all others the prefix is prepended with a slash.

    Examples
    --------
    >>> _build_model_string(PROVIDER_BY_ID["anthropic"], "claude-sonnet-5-5")
    'claude-sonnet-5-5'
    >>> _build_model_string(PROVIDER_BY_ID["google"], "models/gemini-3.5-flash-lite")
    'gemini/models/gemini-3.5-flash-lite'
    >>> _build_model_string(PROVIDER_BY_ID["ollama"], "qwen3.5:9b")
    'ollama/qwen3.5:9b'
    """
    if provider.litellm_prefix:
        return f"{provider.litellm_prefix}/{model_id}"
    return model_id


def list_models(
    provider: ProviderSpec, api_key: str | None, base_url: str | None = None
) -> list[str]:
    """Call the provider's list-models endpoint and return model id strings.

    Parameters
    ----------
    provider:
        The ProviderSpec describing the endpoint and auth style.
    api_key:
        The user-supplied API key.  Ignored (and may be None) when
        ``provider.needs_api_key`` is False.

    Returns
    -------
    list[str]
        Ordered list of model id strings as returned by the provider.
        May be empty if the account has no models (e.g. no quota assigned).

    Raises
    ------
    ProviderAuthError
        On HTTP 401 or 403 — bad or expired API key.
    ProviderConnectionError
        On network failures, DNS errors, or connection timeouts.
    """
    headers: dict[str, str] = {}
    params: dict[str, str] = {}

    # Anthropic also requires an API version header
    if provider.id == "anthropic":
        headers["anthropic-version"] = "2023-06-01"

    if provider.auth_header and api_key:
        headers[provider.auth_header] = provider.auth_format.format(key=api_key)

    if provider.key_in_query and api_key:
        params["key"] = api_key

    try:
        models_url = provider.models_url_for(base_url)
        if not models_url.startswith(("http://", "https://")):
            raise ProviderConnectionError(
                f"{provider.display_name} needs a base URL. Set it in Configuration."
            )
        response = httpx.get(
            models_url,
            headers=headers,
            params=params,
            timeout=15.0,
        )
    except httpx.ConnectError as exc:
        raise ProviderConnectionError(f"Cannot connect to {provider.display_name}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ProviderConnectionError(
            f"Timeout connecting to {provider.display_name}: {exc}"
        ) from exc
    except httpx.RequestError as exc:
        raise ProviderConnectionError(f"Network error for {provider.display_name}: {exc}") from exc

    if response.status_code in (401, 403):
        raise ProviderAuthError(
            f"Invalid API key for {provider.display_name} (HTTP {response.status_code})"
        )

    response.raise_for_status()
    data = response.json()

    # Navigate the provider-specific JSON path to the model list
    model_objects: list = data.get(provider.models_json_path, [])
    return [obj[provider.model_id_field] for obj in model_objects if provider.model_id_field in obj]


# ---------------------------------------------------------------------------
# CTI service registry
# ---------------------------------------------------------------------------
# @decision DEC-AGENT-CTI-WIZARD-001
# @title CTI credential wizard as a post-LLM wizard step with per-service validate
# @status accepted
# @rationale The LLM setup wizard only configures the LLM provider. Users of the
#            Pivotglass agent also need CTI service credentials (Shodan,
#            VirusTotal, etc.). Adding a second wizard step after LLM setup keeps
#            the flow cohesive: user finishes LLM config, is immediately offered
#            CTI config. Each service has a single-shot validation call that proves
#            the key works before saving it. validate_method strings are an explicit enum to
#            keep _validate_cti_key() free of magic string guessing. The dotfile
#            export for CTI keys uses a separate marker block so LLM and CTI exports
#            don't collide on re-runs. Every keyed service is optional/skippable.
#
# @decision DEC-CTI-KEYLESS-SERVICES-001
# @title Keyless context sources live in CTI_SERVICES with no credential fields
# @status accepted
# @rationale Configuration's service list, enable/disable, base-URL overrides,
#            and the operational registry all key off CTI_SERVICES. A second
#            list for keyless sources would be a parallel authority, so keyless
#            sources are specs with empty config_keys (needs_credential False):
#            the wizard skips them, configuration reports credential_source
#            "not-required", and the test is a plain reachability request
#            (validate_method "none") against a public, non-case value.


@dataclass(frozen=True)
class CTIServiceSpec:
    """Immutable descriptor for one CTI intelligence service.

    Attributes
    ----------
    id:
        Internal service identifier; must match the ApiKeysConfig field name
        (or the first of config_keys for multi-key services).
    display_name:
        Human-readable name shown in the wizard UI.
    config_keys:
        List of ApiKeysConfig field names that store credentials for this service.
        Single-key services have one entry; Censys has two (PAT, org ID).
    prompt_labels:
        Labels shown when prompting the user for each credential in config_keys.
    validate_path:
        Path (and query) of the single-shot validation request, relative to the
        service's effective base URL (core/service_endpoints, DEC-ENDPOINTS-001),
        so a gateway override applies to the credential check as well.
    validate_method:
        Auth method to use when building the validation request:
          "query_param"    — key appended as ?key=<key>
          "bearer"         — Authorization: Bearer <key>
          "header_x_apikey"— x-apikey: <key>
          "header_key"     — Key: <key>  (AbuseIPDB, HIBP)
          "header_x_otx"   — X-OTX-API-KEY: <key>
          "header_api_key" — API-Key: <key>  (URLScan)
          "none"           — no credential (keyless context sources)
    validate_header_name:
        Header name for header_* methods. Empty string for others.
    docs_url:
        Where the user obtains an API key; shown in the wizard.
    """

    id: str
    display_name: str
    config_keys: list[str]
    prompt_labels: list[str]
    validate_path: str
    validate_method: str
    validate_header_name: str
    docs_url: str
    optional_config_keys: tuple[str, ...] = ()

    @property
    def default_base_url(self) -> str:
        return SERVICE_BASE_URLS[self.id]

    def validate_url_for(self, base_url: str | None = None) -> str:
        """Validation URL under *base_url* (an override), else the registry default."""
        return (base_url or self.default_base_url).rstrip("/") + self.validate_path

    @property
    def validate_url(self) -> str:
        return self.validate_url_for()

    @property
    def needs_credential(self) -> bool:
        """False for keyless context sources, which have no credential fields."""
        return bool(self.config_keys)


CTI_SERVICES: list[CTIServiceSpec] = [
    CTIServiceSpec(
        id="shodan",
        display_name="Shodan",
        config_keys=["shodan"],
        prompt_labels=["API Key"],
        validate_path="/api-info?key={key}",
        validate_method="query_param",
        validate_header_name="",
        docs_url="https://account.shodan.io",
    ),
    CTIServiceSpec(
        id="virustotal",
        display_name="VirusTotal",
        config_keys=["virustotal"],
        prompt_labels=["API Key"],
        validate_path="/ip_addresses/8.8.8.8",
        validate_method="header_x_apikey",
        validate_header_name="x-apikey",
        docs_url="https://www.virustotal.com/gui/my-apikey",
    ),
    CTIServiceSpec(
        id="abuseipdb",
        display_name="AbuseIPDB",
        config_keys=["abuseipdb"],
        prompt_labels=["API Key"],
        validate_path="/check?ipAddress=176.111.173.242",
        validate_method="header_key",
        validate_header_name="Key",
        docs_url="https://www.abuseipdb.com/account/api",
    ),
    CTIServiceSpec(
        id="hibp",
        display_name="HaveIBeenPwned",
        config_keys=["hibp"],
        prompt_labels=["API Key"],
        validate_path="/subscription/status",
        validate_method="header_key",
        validate_header_name="hibp-api-key",
        docs_url="https://haveibeenpwned.com/API/Key",
    ),
    CTIServiceSpec(
        id="otx",
        display_name="AlienVault OTX",
        config_keys=["otx"],
        prompt_labels=["API Key"],
        validate_path="/api/v1/user/me",
        validate_method="header_x_otx",
        validate_header_name="X-OTX-API-KEY",
        docs_url="https://otx.alienvault.com/settings",
    ),
    CTIServiceSpec(
        id="urlscan",
        display_name="URLScan",
        config_keys=["urlscan"],
        prompt_labels=["API Key"],
        validate_path="/api/v1/quotas",
        validate_method="header_api_key",
        validate_header_name="API-Key",
        docs_url="https://urlscan.io/user/profile/",
    ),
    CTIServiceSpec(
        id="censys_pat",
        display_name="Censys (Platform PAT)",
        config_keys=["censys_pat", "censys_org_id"],
        prompt_labels=["Personal Access Token", "Organization ID (optional for Free accounts)"],
        validate_path="/v3/global/asset/host/8.8.8.8",
        validate_method="bearer",
        validate_header_name="",
        docs_url="https://app.censys.io/user/tokens",
        optional_config_keys=("censys_org_id",),
    ),
    CTIServiceSpec(
        id="greynoise",
        display_name="GreyNoise",
        config_keys=["greynoise"],
        prompt_labels=["API Key"],
        # /ping checks the key itself; community/{ip} answers 404 for any IP GreyNoise
        # has not seen scanning (including 8.8.8.8), so it never proved the key.
        validate_path="/ping",
        validate_method="header_key",
        validate_header_name="key",
        docs_url="https://viz.greynoise.io/account/api-key",
    ),
    # Keyless context sources (#46, #45; DEC-CTI-KEYLESS-SERVICES-001): no
    # credential fields, so they appear in Configuration for enable/disable,
    # base-URL override, and a reachability test, and the wizard skips them.
    # The test queries a public, non-case value.
    CTIServiceSpec(
        id="mnemonic_pdns",
        display_name="Mnemonic passive DNS",
        config_keys=[],
        prompt_labels=[],
        validate_path="/pdns/v3/example.com?limit=1",
        validate_method="none",
        validate_header_name="",
        docs_url="https://docs.mnemonic.no/service-integration-guides/passivedns/docs/public/01-public_api.html",
    ),
    CTIServiceSpec(
        id="shodan_internetdb",
        display_name="Shodan InternetDB",
        config_keys=[],
        prompt_labels=[],
        validate_path="/8.8.8.8",
        validate_method="none",
        validate_header_name="",
        docs_url="https://internetdb.shodan.io/",
    ),
    CTIServiceSpec(
        id="sans_isc",
        display_name="SANS ISC",
        config_keys=[],
        prompt_labels=[],
        validate_path="/ip/8.8.8.8?json",
        validate_method="none",
        validate_header_name="",
        docs_url="https://isc.sans.edu/api/",
    ),
    CTIServiceSpec(
        id="rdap",
        display_name="RDAP",
        config_keys=[],
        prompt_labels=[],
        validate_path="/domain/example.com",
        validate_method="none",
        validate_header_name="",
        docs_url="https://about.rdap.org/",
    ),
    CTIServiceSpec(
        id="wayback",
        display_name="Wayback Machine",
        config_keys=[],
        prompt_labels=[],
        validate_path="/cdx/search/cdx?url=example.com&output=json&limit=1",
        validate_method="none",
        validate_header_name="",
        docs_url="https://archive.org/developers/wayback-cdx-server.html",
    ),
    CTIServiceSpec(
        id="hashlookup",
        display_name="CIRCL hashlookup",
        config_keys=[],
        prompt_labels=[],
        validate_path="/info",
        validate_method="none",
        validate_header_name="",
        docs_url="https://www.circl.lu/services/hashlookup/",
    ),
]

# Map from CTI service config_key to vendor env var for dotfile export.
# Keys match the ApiKeysConfig field names that store the credential.
_CTI_ENV_VAR: dict[str, str] = {
    "shodan": "SHODAN_API_KEY",
    "virustotal": "VIRUSTOTAL_API_KEY",
    "abuseipdb": "ABUSEIPDB_API_KEY",
    "hibp": "HIBP_API_KEY",
    "otx": "OTX_API_KEY",
    "urlscan": "URLSCAN_API_KEY",
    "censys_pat": "CENSYS_PAT",
    "censys_org_id": "CENSYS_ORG_ID",
    "greynoise": "GREYNOISE_API_KEY",
}

# Marker strings for the CTI dotfile export block — separate from the LLM block
# so that re-running either wizard only replaces its own section.
_CTI_RC_MARKER_BEGIN = "# >>> pivotglass cti wizard exports — managed by pivotglass; edit at your own risk"
_CTI_RC_MARKER_END = "# <<< pivotglass cti wizard exports"


def mask_secret(value: str, visible: int = 4) -> str:
    """Return *value* with all but the last *visible* characters replaced by *.

    Used to safely display existing credential values in the wizard without
    exposing the full secret.

    Parameters
    ----------
    value:
        The secret string to mask.
    visible:
        Number of trailing characters to reveal.  Defaults to 4.
    """
    if len(value) < visible:
        return "*" * len(value)
    if len(value) == visible:
        return value
    return "*" * (len(value) - visible) + value[-visible:]


def _compose_cti_export_lines(values: dict[str, str]) -> list[str]:
    """Return export lines for all non-empty CTI credential values.

    Parameters
    ----------
    values:
        Mapping from ApiKeysConfig field name (e.g. "shodan") to the key value.
        Empty or None values are skipped.
    """
    lines: list[str] = []
    for config_key, key_value in values.items():
        if not key_value:
            continue
        env_var = _CTI_ENV_VAR.get(config_key)
        if env_var:
            lines.append(f'export {env_var}="{key_value}"')
    return lines


def _write_cti_rc_with_marker(rc_path: "Path", export_lines: list[str]) -> None:
    """Write CTI export lines into *rc_path* using the CTI marker block.

    Uses the same idempotent replace-or-append logic as _write_rc_with_marker
    but with a different marker string so LLM and CTI sections coexist.
    """
    new_block = "\n".join([_CTI_RC_MARKER_BEGIN, *export_lines, _CTI_RC_MARKER_END])

    original_mode: int | None = None
    if rc_path.exists():
        import stat as _stat

        original_mode = _stat.S_IMODE(rc_path.stat().st_mode)
        existing = rc_path.read_text(encoding="utf-8")
    else:
        existing = ""

    pattern = re.compile(
        r"\n?" + re.escape(_CTI_RC_MARKER_BEGIN) + r".*?" + re.escape(_CTI_RC_MARKER_END),
        re.DOTALL,
    )
    if pattern.search(existing):
        updated = pattern.sub("\n" + new_block, existing)
    else:
        separator = "\n" if existing.endswith("\n") else "\n\n"
        updated = existing + separator + new_block + "\n"

    rc_path.parent.mkdir(parents=True, exist_ok=True)
    rc_path.write_text(updated, encoding="utf-8")
    if original_mode is not None:
        import os as _os

        _os.chmod(rc_path, original_mode)


def _validate_cti_key(
    spec: CTIServiceSpec, values: list[str], base_url: str | None = None
) -> tuple[bool, str]:
    """Make a single validation HTTP request and report success or failure.

    Parameters
    ----------
    spec:
        The CTIServiceSpec describing how to authenticate.
    values:
        List of credential strings in the same order as spec.config_keys.
        Single-key services have one value; Censys has [PAT, org ID].

    Returns
    -------
    tuple[bool, str]
        (success, message) where message is shown to the user.

    Notes
    -----
    Rate limits, timeouts, and network errors leave access unverified. Callers decide whether
    to store the credential independently of this one-shot test.
    """
    headers: dict[str, str] = {}
    url = spec.validate_url_for(base_url)
    key = values[0] if values else ""

    method = spec.validate_method
    if method == "query_param":
        url = url.format(key=key)
    elif method == "bearer":
        headers["Authorization"] = f"Bearer {key}"
        if spec.id == "censys_pat" and len(values) > 1 and values[1]:
            headers["X-Organization-ID"] = values[1]
    elif method in ("header_x_apikey", "header_key", "header_x_otx", "header_api_key"):
        headers[spec.validate_header_name] = key

    if spec.id == "hibp":
        headers["user-agent"] = "Pivotglass credential check"
    if not spec.needs_credential:
        # Keyless sources: SANS ISC asks for a descriptive User-Agent; no contact detail.
        from pivotglass.modules.keyless_http import USER_AGENT

        headers["User-Agent"] = USER_AGENT

    try:
        response = httpx.get(
            url, headers=headers,
            timeout=10.0, follow_redirects=True,
        )
    except httpx.TimeoutException:
        return False, "Validation timed out; access is unverified"
    except httpx.ConnectError:
        return False, "Network unreachable; access is unverified"
    except httpx.RequestError:
        return False, "Network error; access is unverified"

    if response.status_code == 429:
        return False, "Rate limited (HTTP 429); credential access is unverified"
    if response.status_code == 401:
        return False, "Authentication failed"
    if response.status_code == 403:
        return False, "Access forbidden (HTTP 403); check account permissions, plan, and organization"
    if response.status_code >= 400:
        return False, f"Unexpected status {response.status_code}"
    if not spec.needs_credential:
        return True, "Reachable; no credential is required"
    return True, "Validated successfully"


def _set_cti_credentials(
    config_mgr: "ConfigManager", config_keys: list[str], values: list[str]
) -> None:
    """Persist CTI credentials to config using dotted-key set().

    Parameters
    ----------
    config_mgr:
        ConfigManager instance to write to.
    config_keys:
        ApiKeysConfig field names (e.g. ["shodan"] or ["censys_pat", "censys_org_id"]).
    values:
        Corresponding credential strings.
    """
    for key, value in zip(config_keys, values):
        if value:
            config_mgr.set(f"api_keys.{key}", value)


def run_cti_credentials_wizard(
    config_mgr: "ConfigManager",
    console: "Console | None" = None,
) -> dict[str, bool]:
    """Walk the user through configuring CTI service credentials.

    Called after the LLM wizard step.  Iterates CTI_SERVICES in order,
    offering Skip / Configure for each.  If a key already exists in config,
    shows the masked value and asks Keep / Replace / Skip.

    Parameters
    ----------
    config_mgr:
        ConfigManager instance for credential persistence.
    console:
        Rich Console instance.  Created fresh if None (supports testing).

    Returns
    -------
    dict[str, bool]
        Mapping from service id → True if credentials were saved for that service.
    """
    if console is None:
        console = Console()

    configured: dict[str, bool] = {}
    # Track all newly-saved values for the dotfile export offer at the end
    saved_values: dict[str, str] = {}

    for spec in CTI_SERVICES:
        if not spec.needs_credential:
            continue  # keyless context sources have nothing to configure here
        # Check if any credential is already set for this service
        existing: list[str] = []
        for key in spec.config_keys:
            val = config_mgr.get_api_key(key) or ""
            existing.append(val)

        has_existing = any(v for v in existing)

        if has_existing:
            # Show masked existing value
            masked_display = ", ".join(
                f"{lbl}: {mask_secret(v)}" if v else f"{lbl}: (not set)"
                for lbl, v in zip(spec.prompt_labels, existing)
            )
            console.print(f"\n[cyan]{spec.display_name}[/cyan] — existing: {masked_display}")
            choice_raw = (
                console.input(
                    f"  [bold]{spec.display_name}[/bold]: Keep / Replace / Skip [K/r/s]: "
                )
                .strip()
                .lower()
            )
            if choice_raw in ("s", "skip"):
                configured[spec.id] = False
                continue
            if choice_raw not in ("r", "replace"):
                # Default is Keep
                configured[spec.id] = True
                # Count existing as still configured
                continue
        else:
            console.print(f"\n[cyan]{spec.display_name}[/cyan] — docs: [dim]{spec.docs_url}[/dim]")
            configure_raw = (
                console.input(f"  Configure {spec.display_name}? [y/N]: ").strip().lower()
            )
            if configure_raw != "y":
                configured[spec.id] = False
                continue

        # Prompt for credentials
        values: list[str] = []
        for label in spec.prompt_labels:
            val = console.input(f"  {label}: ", password=True).strip()
            values.append(val)

        if not any(values):
            console.print(
                f"  [yellow]No credentials entered for {spec.display_name} — skipping.[/yellow]"
            )
            configured[spec.id] = False
            continue

        # Validate
        console.print(f"  [dim]Validating {spec.display_name}…[/dim]")
        ok, msg = _validate_cti_key(spec, values)
        if ok:
            console.print(f"  [green]{msg}[/green]")
            _set_cti_credentials(config_mgr, spec.config_keys, values)
            configured[spec.id] = True
            for key, value in zip(spec.config_keys, values):
                if value:
                    saved_values[key] = value
        else:
            console.print(f"  [red]Validation failed:[/red] {msg}")
            keep_anyway = console.input("  Save anyway? [y/N]: ").strip().lower()
            if keep_anyway == "y":
                _set_cti_credentials(config_mgr, spec.config_keys, values)
                configured[spec.id] = True
                for key, value in zip(spec.config_keys, values):
                    if value:
                        saved_values[key] = value
            else:
                configured[spec.id] = False

    # Offer dotfile export for all newly-saved CTI credentials
    if saved_values:
        export_lines = _compose_cti_export_lines(saved_values)
        if export_lines:
            _prompt_cti_save_destination(console, export_lines)

    return configured


def _prompt_cti_save_destination(
    console: "Console",
    export_lines: list[str],
) -> None:
    """Prompt the user to optionally export CTI keys to shell rc.

    Mirrors _prompt_save_destination() for LLM keys but uses the CTI marker
    block so the two sections remain independent and idempotent separately.
    """
    rc_path = _detect_shell_rc()
    rc_label = str(rc_path) if rc_path else "~/.zshrc / ~/.bashrc"

    dest_table = Table(show_header=True, header_style="bold cyan", show_lines=False)
    dest_table.add_column("#", style="bold", width=3)
    dest_table.add_column("Save CTI credential destination", style="cyan")
    dest_table.add_row("1", "~/.pivotglass/config.toml only (already saved)")
    dest_table.add_row(
        "2",
        f"~/.pivotglass/config.toml + append CTI export line(s) to {rc_label}",
    )
    dest_table.add_row("3", "Print CTI export line(s) to stdout (I'll paste them myself)")
    console.print("\n[bold]Where would you like to also export these CTI credentials?[/bold]")
    console.print(dest_table)

    choice = _prompt_int(console, "Choose save destination [1-3]", 1, 3)

    if choice == 1:
        return

    if choice == 2:
        if rc_path is None:
            console.print(
                "[yellow]Unknown shell — cannot determine rc file. Falling back to stdout.[/yellow]"
            )
            _print_export_lines(console, export_lines)
            return
        _write_cti_rc_with_marker(rc_path, export_lines)
        console.print(
            f"\n[green]CTI export line(s) written to[/green] {rc_path}\n"
            "[dim]Restart your shell or run [bold]source "
            f"{rc_path}[/bold] to apply.[/dim]"
        )
        return

    # choice == 3
    _print_export_lines(console, export_lines)


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------


def run_provider_wizard(
    config_mgr: ConfigManager,
) -> str:
    """Run the full interactive provider/model setup wizard.

    Prompts the user for provider, API key, lists available models, asks the
    user to pick one, persists provider+model+key to config.toml, and
    optionally exports the API key to the user's shell rc file.

    Parameters
    ----------
    config_mgr:
        ConfigManager instance used to persist the selection.

    Returns
    -------
    str
        The full litellm model string the user selected (e.g.
        "claude-sonnet-5-5", "gemini/gemini-3.5-flash-lite").
        This string can be passed directly to ``AgentRunner(model=...)``.
    """
    console = Console()

    console.print(
        "\n[bold cyan]Provider Setup Wizard[/bold cyan]\n"
        "Let's configure your LLM provider for [bold]pivotglass chat[/bold].\n"
    )

    # --- Step 1: Choose provider ---
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="bold", width=3)
    table.add_column("Provider", style="cyan")
    table.add_column("Notes", style="dim")

    notes: dict[str, str] = {
        "anthropic": "Requires API key — api.anthropic.com",
        "openai": "Requires API key — api.openai.com",
        "openrouter": "Unified gateway; access 200+ models with one key",
        "google": "Requires API key — Gemini models",
        "ollama": "Local inference — no API key needed",
    }
    for i, p in enumerate(PROVIDERS, start=1):
        table.add_row(str(i), p.display_name, notes.get(p.id, ""))
    console.print(table)

    provider_idx = _prompt_int(
        console,
        f"Choose a provider [1-{len(PROVIDERS)}]",
        1,
        len(PROVIDERS),
    )
    provider = PROVIDERS[provider_idx - 1]
    console.print(f"\n[green]Selected:[/green] {provider.display_name}")

    # --- Step 2: Enter API key ---
    api_key: str | None = None
    if provider.needs_api_key:
        api_key = console.input(
            f"\nEnter your [bold]{provider.display_name}[/bold] API key: ",
            password=True,
        ).strip()
        if not api_key:
            console.print("[red]No key entered. Aborting setup.[/red]")
            raise SystemExit(1)

    # --- Step 3: Verify key + list models ---
    console.print("\n[dim]Verifying key and fetching available models…[/dim]")
    try:
        with console.status("[bold green]Contacting provider…[/bold green]"):
            models = list_models(provider, api_key)
    except ProviderAuthError as exc:
        console.print(f"\n[red]Authentication failed:[/red] {exc}")
        console.print(
            "[yellow]Check that your API key is correct and has the right permissions.[/yellow]"
        )
        raise SystemExit(1) from exc
    except ProviderConnectionError as exc:
        console.print(f"\n[red]Connection failed:[/red] {exc}")
        if provider.id == "ollama":
            console.print("[yellow]Is Ollama running? Start it with: ollama serve[/yellow]")
        raise SystemExit(1) from exc

    if not models:
        console.print(
            "[yellow]No models returned by the provider. "
            "Check your account has model access, then run 'model select' to retry.[/yellow]"
        )
        raise SystemExit(1)

    # --- Step 4: Display models ---
    console.print(f"\n[bold]Available models ({len(models)} found):[/bold]\n")
    model_table = Table(show_header=True, header_style="bold cyan")
    model_table.add_column("#", style="bold", width=4)
    model_table.add_column("Model ID", style="cyan")
    for i, m in enumerate(models, start=1):
        model_table.add_row(str(i), m)
    console.print(model_table)

    # --- Step 5: Pick a model ---
    model_idx = _prompt_int(
        console,
        f"Choose a model [1-{len(models)}]",
        1,
        len(models),
    )
    chosen_raw = models[model_idx - 1]
    chosen_model = _build_model_string(provider, chosen_raw)
    console.print(f"\n[green]Model:[/green] {chosen_model}")

    # --- Step 6: Persist to config.toml (always) ---
    if api_key:
        config_mgr.set_provider_api_key(provider.id, api_key)
    config_mgr.set_agent_selection(provider.id, chosen_model)

    # --- Step 7: Save destination prompt (only when there is an API key to export) ---
    if api_key:
        export_lines = _compose_export_lines(provider.id, api_key)
        if export_lines:
            _prompt_save_destination(console, provider.id, export_lines)

    # --- Step 8: Offer CTI credential setup ---
    cti_prompt = console.input("\nConfigure CTI service credentials too? (y/N) ").strip().lower()
    if cti_prompt == "y":
        run_cti_credentials_wizard(config_mgr, console=console)

    console.print(
        "\n[bold green]Setup complete![/bold green] "
        "Provider and model saved to config.\n"
        "Run [bold]model select[/bold] at any time to change your selection.\n"
    )
    return chosen_model


def _prompt_save_destination(
    console: Console,
    provider_id: str,
    export_lines: list[str],
) -> None:
    """Prompt the user for where to save the API key export lines.

    Called after config.toml has already been written (option 1 is always
    applied before this function is invoked).

    Options:
      1. config.toml only — already done, nothing extra needed.
      2. config.toml + append to shell rc file (auto-detected via $SHELL).
      3. Print export lines to stdout for the user to paste manually.

    Falls back to stdout (with a warning) when the user selects option 2 but
    the shell is not recognised.
    """
    rc_path = _detect_shell_rc()
    rc_label = str(rc_path) if rc_path else "~/.zshrc / ~/.bashrc"

    dest_table = Table(show_header=True, header_style="bold cyan", show_lines=False)
    dest_table.add_column("#", style="bold", width=3)
    dest_table.add_column("Save destination", style="cyan")
    dest_table.add_row("1", "~/.pivotglass/config.toml only (already saved)")
    dest_table.add_row(
        "2",
        f"~/.pivotglass/config.toml + append export line(s) to {rc_label}",
    )
    dest_table.add_row("3", "Print export line(s) to stdout (I'll paste them myself)")
    console.print("\n[bold]Where would you like to save these credentials?[/bold]")
    console.print(dest_table)

    choice = _prompt_int(console, "Choose save destination [1-3]", 1, 3)

    if choice == 1:
        # config.toml already written — nothing more to do
        return

    if choice == 2:
        if rc_path is None:
            console.print(
                "[yellow]Unknown shell — cannot determine rc file. Falling back to stdout.[/yellow]"
            )
            _print_export_lines(console, export_lines)
            return
        _write_rc_with_marker(rc_path, export_lines)
        console.print(
            f"\n[green]Export line(s) written to[/green] {rc_path}\n"
            "[dim]Restart your shell or run [bold]source "
            f"{rc_path}[/bold] to apply.[/dim]"
        )
        return

    # choice == 3
    _print_export_lines(console, export_lines)


def _print_export_lines(console: Console, export_lines: list[str]) -> None:
    """Render *export_lines* inside a Rich Panel for easy copying."""
    content = "\n".join(export_lines)
    console.print(
        Panel(
            f"[bold green]{content}[/bold green]",
            title="[bold]Paste into your shell rc file[/bold]",
            subtitle="[dim]e.g. ~/.zshrc  ~/.bashrc  ~/.config/fish/config.fish[/dim]",
            expand=False,
        )
    )


def _prompt_int(console: Console, prompt: str, lo: int, hi: int) -> int:
    """Prompt for an integer in [lo, hi], re-prompting on invalid input."""
    while True:
        raw = console.input(f"{prompt}: ").strip()
        try:
            value = int(raw)
            if lo <= value <= hi:
                return value
            console.print(f"[yellow]Please enter a number between {lo} and {hi}.[/yellow]")
        except ValueError:
            console.print(f"[yellow]Invalid input '{raw}'. Enter a number.[/yellow]")
