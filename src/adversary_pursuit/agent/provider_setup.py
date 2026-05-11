"""Interactive provider/model setup wizard for the AP agent.

Prompts the user to choose an LLM provider, enter their API key, verify it
by listing available models, and persist the selection to ~/.ap/config.toml.

@decision DEC-AGENT-PROVIDER-SETUP-001
@title Interactive UX wizard replaces silent AP_MODEL env-var-only flow
@status accepted
@rationale On first launch of 'ap chat' when no provider is configured the user
           would previously hit a connection error from the Ollama default with
           no guidance. The wizard provides: (1) curated provider list so users
           don't need to know litellm model strings, (2) immediate key validation
           via the provider's list-models endpoint so bad keys are caught before
           any LLM call, (3) model listing so the user picks from what they
           actually have access to, (4) secure persistence at chmod 0600 so keys
           survive session boundaries. Precedence is preserved: explicit model=
           arg > AP_MODEL env > config.toml > wizard. The wizard is re-runnable
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
from typing import TYPE_CHECKING

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from adversary_pursuit.core.config import ConfigManager

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
        "gemini" → "gemini/gemini-2.0-flash-exp".  Empty string for providers
        where litellm accepts bare model IDs (Anthropic, OpenAI).
    list_models_url:
        Full URL for the provider's list-models endpoint.
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
    list_models_url: str
    auth_header: str
    auth_format: str
    key_in_query: bool
    needs_api_key: bool
    models_json_path: str
    model_id_field: str


PROVIDERS: list[ProviderSpec] = [
    ProviderSpec(
        id="anthropic",
        display_name="Anthropic",
        litellm_prefix="",
        list_models_url="https://api.anthropic.com/v1/models",
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
        list_models_url="https://api.openai.com/v1/models",
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
        list_models_url="https://openrouter.ai/api/v1/models",
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
        list_models_url="https://generativelanguage.googleapis.com/v1beta/models",
        auth_header="",
        auth_format="",
        key_in_query=True,
        needs_api_key=True,
        models_json_path="models",
        model_id_field="name",
    ),
    ProviderSpec(
        id="ollama",
        display_name="Ollama (local)",
        litellm_prefix="ollama",
        list_models_url="http://localhost:11434/api/tags",
        auth_header="",
        auth_format="",
        key_in_query=False,
        needs_api_key=False,
        models_json_path="models",
        model_id_field="name",
    ),
]

# Lookup by id for O(1) access
PROVIDER_BY_ID: dict[str, ProviderSpec] = {p.id: p for p in PROVIDERS}

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
_RC_MARKER_BEGIN = "# >>> ap chat wizard exports — managed by ap; edit at your own risk"
_RC_MARKER_END = "# <<< ap chat wizard exports"

# Map from provider id to the vendor-convention env var name for the API key.
# These names match the entries in core/config._VENDOR_ENV_VAR_MAP so that
# shells configured via this wizard need no additional ap-specific variables.
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
    >>> _build_model_string(PROVIDER_BY_ID["anthropic"], "claude-3-5-sonnet-20241022")
    'claude-3-5-sonnet-20241022'
    >>> _build_model_string(PROVIDER_BY_ID["google"], "models/gemini-2.0-flash-exp")
    'gemini/models/gemini-2.0-flash-exp'
    >>> _build_model_string(PROVIDER_BY_ID["ollama"], "qwen2.5:8b")
    'ollama/qwen2.5:8b'
    """
    if provider.litellm_prefix:
        return f"{provider.litellm_prefix}/{model_id}"
    return model_id


def list_models(provider: ProviderSpec, api_key: str | None) -> list[str]:
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
        response = httpx.get(
            provider.list_models_url,
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
        "claude-3-5-sonnet-20241022", "gemini/gemini-2.0-flash-exp").
        This string can be passed directly to ``AgentRunner(model=...)``.
    """
    console = Console()

    console.print(
        "\n[bold cyan]Provider Setup Wizard[/bold cyan]\n"
        "Let's configure your LLM provider for [bold]ap chat[/bold].\n"
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
    dest_table.add_row("1", "~/.ap/config.toml only (already saved)")
    dest_table.add_row(
        "2",
        f"~/.ap/config.toml + append export line(s) to {rc_label}",
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
