"""Tests for agent/provider_setup.py — interactive provider/model wizard.

# @mock-exempt: httpx.get is an external HTTP boundary (provider list-models
# endpoints). All provider HTTP calls are mocked via unittest.mock.patch so
# tests run hermetically without live API keys or network access.
# Console.input/print/status wrap terminal I/O (external boundary).
# MagicMock is used only for the Rich Console context-manager protocol
# (status().__enter__) which has no real in-process equivalent.

Production sequence tested here:
  ProviderSpec registry → list_models() → _build_model_string() → wizard flow
  → save-destination prompt → _write_rc_with_marker() / stdout fallback

@decision DEC-TEST-PROVIDER-SETUP-001
@title Mock httpx.get at the HTTP boundary for hermetic provider tests
@status accepted
@rationale The provider wizard's sole external I/O is httpx.get calls to
           list-models endpoints. Mocking at this boundary lets us exercise:
           (1) all provider-specific JSON parsing paths, (2) auth header
           construction, (3) ProviderAuthError on 401/403, (4) ProviderConnectionError
           on network failure, (5) the full wizard flow with mocked Rich prompts,
           (6) dotfile export helpers (_detect_shell_rc, _compose_export_lines,
           _write_rc_with_marker) and all three save-destination wizard paths.
           We do NOT mock internal functions — the production dispatch path is
           exercised end-to-end up to the HTTP boundary.
"""

from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from adversary_pursuit.agent.provider_setup import (
    CTI_SERVICES,
    PROVIDER_BY_ID,
    PROVIDERS,
    ProviderAuthError,
    ProviderConnectionError,
    _build_model_string,
    _compose_cti_export_lines,
    _compose_export_lines,
    _detect_shell_rc,
    _validate_cti_key,
    _write_cti_rc_with_marker,
    _write_rc_with_marker,
    list_models,
    mask_secret,
    run_cti_credentials_wizard,
)
from adversary_pursuit.core.config import ConfigManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_config_mgr(tmp_path: Path) -> ConfigManager:
    """Return a ConfigManager wired to a temp directory (no real ~/.ap touch)."""
    return ConfigManager(config_dir=tmp_path)


def _mock_response(status_code: int, json_body: dict) -> MagicMock:
    """Return a mock httpx.Response with the given status and JSON body."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Provider registry sanity checks
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_five_providers_defined(self):
        assert len(PROVIDERS) == 5

    def test_provider_ids(self):
        ids = {p.id for p in PROVIDERS}
        assert ids == {"anthropic", "openai", "openrouter", "google", "ollama"}

    def test_all_have_display_name(self):
        for p in PROVIDERS:
            assert p.display_name, f"{p.id} missing display_name"

    def test_ollama_no_key_required(self):
        assert PROVIDER_BY_ID["ollama"].needs_api_key is False

    def test_all_others_require_key(self):
        for p in PROVIDERS:
            if p.id != "ollama":
                assert p.needs_api_key is True, f"{p.id} should require API key"

    def test_provider_by_id_lookup(self):
        assert PROVIDER_BY_ID["anthropic"].display_name == "Anthropic"
        assert PROVIDER_BY_ID["openai"].display_name == "OpenAI"
        assert PROVIDER_BY_ID["openrouter"].display_name == "OpenRouter"
        assert PROVIDER_BY_ID["google"].display_name == "Google (Gemini)"
        assert PROVIDER_BY_ID["ollama"].display_name == "Ollama (local)"


# ---------------------------------------------------------------------------
# _build_model_string
# ---------------------------------------------------------------------------


class TestBuildModelString:
    def test_anthropic_bare_model_id(self):
        """Anthropic prefix is empty — litellm accepts bare model IDs."""
        result = _build_model_string(PROVIDER_BY_ID["anthropic"], "claude-3-5-sonnet-20241022")
        assert result == "claude-3-5-sonnet-20241022"

    def test_openai_bare_model_id(self):
        """OpenAI prefix is empty — litellm accepts bare model IDs."""
        result = _build_model_string(PROVIDER_BY_ID["openai"], "gpt-4o")
        assert result == "gpt-4o"

    def test_openrouter_prefixed(self):
        result = _build_model_string(PROVIDER_BY_ID["openrouter"], "anthropic/claude-3.5-sonnet")
        assert result == "openrouter/anthropic/claude-3.5-sonnet"

    def test_google_prefixed(self):
        result = _build_model_string(PROVIDER_BY_ID["google"], "models/gemini-2.0-flash-exp")
        assert result == "gemini/models/gemini-2.0-flash-exp"

    def test_ollama_prefixed(self):
        result = _build_model_string(PROVIDER_BY_ID["ollama"], "qwen2.5:8b")
        assert result == "ollama/qwen2.5:8b"


# ---------------------------------------------------------------------------
# list_models — per-provider JSON parsing (mocked HTTP)
# ---------------------------------------------------------------------------


class TestListModelsAnthropic:
    """list_models correctly parses Anthropic's response shape."""

    _RESPONSE_JSON = {
        "data": [
            {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-haiku-20240307", "display_name": "Claude 3 Haiku"},
        ]
    }

    def test_returns_model_ids(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)):
            models = list_models(PROVIDER_BY_ID["anthropic"], "sk-ant-test")
        assert models == ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]

    def test_sends_api_key_header(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)) as mock_get:
            list_models(PROVIDER_BY_ID["anthropic"], "sk-ant-test-key")
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["x-api-key"] == "sk-ant-test-key"

    def test_sends_anthropic_version_header(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)) as mock_get:
            list_models(PROVIDER_BY_ID["anthropic"], "sk-ant-test-key")
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["anthropic-version"] == "2023-06-01"


class TestListModelsOpenAI:
    """list_models correctly parses OpenAI's response shape."""

    _RESPONSE_JSON = {
        "data": [
            {"id": "gpt-4o", "object": "model"},
            {"id": "gpt-4o-mini", "object": "model"},
            {"id": "gpt-3.5-turbo", "object": "model"},
        ]
    }

    def test_returns_model_ids(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)):
            models = list_models(PROVIDER_BY_ID["openai"], "sk-test")
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models

    def test_sends_bearer_token(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)) as mock_get:
            list_models(PROVIDER_BY_ID["openai"], "sk-test-key")
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key"


class TestListModelsOpenRouter:
    """list_models correctly parses OpenRouter's response shape."""

    _RESPONSE_JSON = {
        "data": [
            {"id": "anthropic/claude-3.5-sonnet"},
            {"id": "openai/gpt-4o"},
            {"id": "google/gemini-2.0-flash"},
        ]
    }

    def test_returns_model_ids(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)):
            models = list_models(PROVIDER_BY_ID["openrouter"], "sk-or-test")
        assert "anthropic/claude-3.5-sonnet" in models
        assert "openai/gpt-4o" in models
        assert "google/gemini-2.0-flash" in models

    def test_sends_bearer_token(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)) as mock_get:
            list_models(PROVIDER_BY_ID["openrouter"], "sk-or-key")
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-or-key"


class TestListModelsGoogle:
    """list_models correctly parses Google's response shape (key in query string)."""

    _RESPONSE_JSON = {
        "models": [
            {"name": "models/gemini-2.0-flash-exp", "displayName": "Gemini 2.0 Flash"},
            {"name": "models/gemini-1.5-pro", "displayName": "Gemini 1.5 Pro"},
        ]
    }

    def test_returns_model_names(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)):
            models = list_models(PROVIDER_BY_ID["google"], "AIza-test-key")
        assert "models/gemini-2.0-flash-exp" in models
        assert "models/gemini-1.5-pro" in models

    def test_sends_key_as_query_param(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)) as mock_get:
            list_models(PROVIDER_BY_ID["google"], "AIza-test-key")
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["key"] == "AIza-test-key"

    def test_no_auth_header_sent(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)) as mock_get:
            list_models(PROVIDER_BY_ID["google"], "AIza-test-key")
        call_kwargs = mock_get.call_args[1]
        # No Authorization header — Google uses query param
        assert "Authorization" not in call_kwargs.get("headers", {})


class TestListModelsOllama:
    """list_models correctly parses Ollama's response shape (no auth)."""

    _RESPONSE_JSON = {
        "models": [
            {"name": "qwen2.5:8b", "modified_at": "2024-01-01T00:00:00Z"},
            {"name": "llama3.2:3b", "modified_at": "2024-01-01T00:00:00Z"},
        ]
    }

    def test_returns_model_names(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)):
            models = list_models(PROVIDER_BY_ID["ollama"], None)
        assert "qwen2.5:8b" in models
        assert "llama3.2:3b" in models

    def test_sends_no_auth_header(self):
        with patch("httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)) as mock_get:
            list_models(PROVIDER_BY_ID["ollama"], None)
        call_kwargs = mock_get.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert "Authorization" not in headers
        assert "x-api-key" not in headers


# ---------------------------------------------------------------------------
# list_models — error paths
# ---------------------------------------------------------------------------


class TestListModelsErrors:
    """list_models raises the correct exceptions on failure."""

    def test_401_raises_auth_error(self):
        resp = _mock_response(401, {"error": "invalid api key"})
        with patch("httpx.get", return_value=resp):
            with pytest.raises(ProviderAuthError) as exc_info:
                list_models(PROVIDER_BY_ID["anthropic"], "bad-key")
        assert "401" in str(exc_info.value)

    def test_403_raises_auth_error(self):
        resp = _mock_response(403, {"error": "forbidden"})
        with patch("httpx.get", return_value=resp):
            with pytest.raises(ProviderAuthError) as exc_info:
                list_models(PROVIDER_BY_ID["openai"], "bad-key")
        assert "403" in str(exc_info.value)

    def test_connect_error_raises_provider_connection_error(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("connection refused")):
            with pytest.raises(ProviderConnectionError) as exc_info:
                list_models(PROVIDER_BY_ID["anthropic"], "sk-ant-test")
        assert "connect" in str(exc_info.value).lower() or "Anthropic" in str(exc_info.value)

    def test_timeout_raises_provider_connection_error(self):
        with patch(
            "httpx.get",
            side_effect=httpx.TimeoutException("timed out", request=MagicMock()),
        ):
            with pytest.raises(ProviderConnectionError):
                list_models(PROVIDER_BY_ID["ollama"], None)

    def test_generic_request_error_raises_provider_connection_error(self):
        with patch("httpx.get", side_effect=httpx.RequestError("generic", request=MagicMock())):
            with pytest.raises(ProviderConnectionError):
                list_models(PROVIDER_BY_ID["openai"], "sk-test")

    def test_empty_model_list_returns_empty(self):
        """Provider that returns no models gives empty list (not an exception)."""
        with patch("httpx.get", return_value=_mock_response(200, {"data": []})):
            models = list_models(PROVIDER_BY_ID["openai"], "sk-test")
        assert models == []

    def test_missing_json_path_returns_empty(self):
        """If the expected JSON key is absent, returns empty (not crash)."""
        with patch("httpx.get", return_value=_mock_response(200, {})):
            models = list_models(PROVIDER_BY_ID["anthropic"], "sk-test")
        assert models == []


# ---------------------------------------------------------------------------
# Wizard flow — end-to-end with mocked HTTP + mocked console input
# ---------------------------------------------------------------------------


class TestWizardFlow:
    """End-to-end test: wizard prompts → HTTP → config persistence."""

    _ANTHROPIC_RESPONSE = {
        "data": [
            {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-haiku-20240307", "display_name": "Claude 3 Haiku"},
        ]
    }

    # @mock-exempt: Console.input/print/status and httpx.get are external I/O boundaries.
    # MagicMock is used only for the Rich Console context-manager protocol (status().__enter__)
    # which wraps terminal output and has no real in-process equivalent.
    def _run_wizard_with_inputs(
        self,
        tmp_path: Path,
        provider_choice: int,
        api_key: str,
        model_choice: int,
        http_json: dict,
        http_status: int = 200,
        save_destination: int = 1,
    ) -> tuple[str, ConfigManager]:
        """Helper: run wizard with mocked console input and HTTP.

        Parameters
        ----------
        save_destination:
            The save-destination choice (1=config only, 2=config+rc, 3=stdout).
            Defaults to 1 (config.toml only) for regression-safe behavior.
            Only injected as an input when the provider has an API key
            (Ollama skips the save-destination prompt entirely).
        """
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)

        # Sequence of console.input() calls:
        #   provider choice, api_key (if needed), model choice, save destination (if key)
        # Ollama (no key) does not reach the save-destination prompt.
        has_key = bool(api_key)
        inputs = [str(provider_choice)]
        if has_key:
            inputs.append(api_key)
        inputs.append(str(model_choice))
        if has_key:
            inputs.append(str(save_destination))
        # The CTI credentials prompt is always offered at the end of run_provider_wizard.
        # Existing wizard flow tests skip it by default.
        inputs.append("n")

        with (
            patch("httpx.get", return_value=_mock_response(http_status, http_json)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.status",
            ) as mock_status,
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            # Make status() usable as a context manager
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            result = run_provider_wizard(config_mgr)

        return result, config_mgr

    def test_wizard_anthropic_full_flow(self, tmp_path):
        """Full wizard: pick Anthropic (1), enter key, pick first model → persisted."""
        result, config_mgr = self._run_wizard_with_inputs(
            tmp_path,
            provider_choice=1,  # Anthropic
            api_key="sk-ant-test-key",
            model_choice=1,
            http_json=self._ANTHROPIC_RESPONSE,
        )
        assert result == "claude-3-5-sonnet-20241022"
        # Config persisted correctly
        assert config_mgr.get_agent_provider() == "anthropic"
        assert config_mgr.get_agent_model() == "claude-3-5-sonnet-20241022"
        assert config_mgr.get_provider_api_key("anthropic") == "sk-ant-test-key"

    def test_wizard_picks_second_model(self, tmp_path):
        """Wizard returns the second model when user selects index 2."""
        result, config_mgr = self._run_wizard_with_inputs(
            tmp_path,
            provider_choice=1,
            api_key="sk-ant-test",
            model_choice=2,
            http_json=self._ANTHROPIC_RESPONSE,
        )
        assert result == "claude-3-haiku-20240307"
        assert config_mgr.get_agent_model() == "claude-3-haiku-20240307"

    def test_wizard_ollama_skips_api_key(self, tmp_path):
        """Ollama wizard flow: no API key prompt (ollama = provider 5)."""
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)
        ollama_response = {"models": [{"name": "qwen2.5:8b"}, {"name": "llama3.2:3b"}]}

        # Ollama only needs 2 inputs: provider choice + model choice (no key, no save dest)
        input_side_effects = ["5", "1", "n"]

        with (
            patch("httpx.get", return_value=_mock_response(200, ollama_response)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=input_side_effects,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.status") as mock_status,
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            result = run_provider_wizard(config_mgr)

        assert result == "ollama/qwen2.5:8b"
        assert config_mgr.get_agent_model() == "ollama/qwen2.5:8b"
        # Ollama has no key to store
        assert config_mgr.get_provider_api_key("ollama") is None

    def test_wizard_google_stores_key_and_prefixes_model(self, tmp_path):
        """Google wizard: key stored, model string prefixed with 'gemini/'."""
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)
        google_response = {
            "models": [
                {"name": "models/gemini-2.0-flash-exp"},
                {"name": "models/gemini-1.5-pro"},
            ]
        }

        # @mock-exempt: httpx.get is external HTTP; Console is terminal I/O boundary
        # provider choice, api key, model choice, save destination (1=config only)
        input_side_effects = ["4", "AIza-test-key", "1", "1", "n"]  # provider 4 = Google

        with (
            patch("httpx.get", return_value=_mock_response(200, google_response)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=input_side_effects,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.status") as mock_status,
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            result = run_provider_wizard(config_mgr)

        assert result == "gemini/models/gemini-2.0-flash-exp"
        assert config_mgr.get_agent_provider() == "google"
        assert config_mgr.get_provider_api_key("google") == "AIza-test-key"

    def test_wizard_aborts_on_auth_error(self, tmp_path):
        """Wizard calls SystemExit when provider returns 401."""
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)

        with (
            patch("httpx.get", return_value=_mock_response(401, {"error": "bad key"})),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=["1", "bad-key"],
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.status") as mock_status,
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(SystemExit):
                run_provider_wizard(config_mgr)

    def test_wizard_aborts_on_empty_model_list(self, tmp_path):
        """Wizard calls SystemExit when provider returns empty model list."""
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)

        with (
            patch("httpx.get", return_value=_mock_response(200, {"data": []})),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=["1", "sk-ant-test"],
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.status") as mock_status,
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(SystemExit):
                run_provider_wizard(config_mgr)


# ---------------------------------------------------------------------------
# Dotfile export helpers — unit tests (no mocks; use tmp_path + monkeypatch)
# ---------------------------------------------------------------------------


class TestDotfileExport:
    """Tests for _detect_shell_rc, _compose_export_lines, _write_rc_with_marker,
    and the wizard save-destination flow.

    All tests are hermetic: shell detection uses monkeypatch on os.environ,
    file I/O uses tmp_path, and no network calls are made.
    """

    # ------------------------------------------------------------------
    # _detect_shell_rc
    # ------------------------------------------------------------------

    def test_detect_shell_rc_zsh(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/zsh")
        result = _detect_shell_rc()
        assert result == Path.home() / ".zshrc"

    def test_detect_shell_rc_bash(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/bash")
        result = _detect_shell_rc()
        assert result == Path.home() / ".bashrc"

    def test_detect_shell_rc_fish(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/usr/local/bin/fish")
        result = _detect_shell_rc()
        assert result == Path.home() / ".config" / "fish" / "config.fish"

    def test_detect_shell_rc_unknown(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/csh")
        result = _detect_shell_rc()
        assert result is None

    def test_detect_shell_rc_missing_env(self, monkeypatch):
        monkeypatch.delenv("SHELL", raising=False)
        result = _detect_shell_rc()
        assert result is None

    # ------------------------------------------------------------------
    # _compose_export_lines
    # ------------------------------------------------------------------

    def test_compose_export_lines_anthropic(self):
        lines = _compose_export_lines("anthropic", "sk-ant-abc123")
        assert lines == ['export ANTHROPIC_API_KEY="sk-ant-abc123"']

    def test_compose_export_lines_openai(self):
        lines = _compose_export_lines("openai", "sk-openai-test")
        assert lines == ['export OPENAI_API_KEY="sk-openai-test"']

    def test_compose_export_lines_openrouter(self):
        lines = _compose_export_lines("openrouter", "sk-or-test")
        assert lines == ['export OPENROUTER_API_KEY="sk-or-test"']

    def test_compose_export_lines_google(self):
        lines = _compose_export_lines("google", "AIza-test")
        assert lines == ['export GOOGLE_API_KEY="AIza-test"']

    def test_compose_export_lines_ollama_returns_empty(self):
        """Ollama has no API key so export lines should be empty."""
        lines = _compose_export_lines("ollama", "")
        assert lines == []

    def test_compose_export_lines_unknown_provider_returns_empty(self):
        lines = _compose_export_lines("unknown_provider", "some-key")
        assert lines == []

    # ------------------------------------------------------------------
    # _write_rc_with_marker — core idempotency logic (real file I/O)
    # ------------------------------------------------------------------

    def test_write_rc_with_marker_creates_block(self, tmp_path):
        """Empty rc file gets the marker block appended."""
        rc = tmp_path / ".zshrc"
        rc.write_text("", encoding="utf-8")

        _write_rc_with_marker(rc, ['export ANTHROPIC_API_KEY="sk-test"'])

        content = rc.read_text(encoding="utf-8")
        assert "# >>> ap chat wizard exports" in content
        assert 'export ANTHROPIC_API_KEY="sk-test"' in content
        assert "# <<< ap chat wizard exports" in content

    def test_write_rc_with_marker_appends_after_existing_content(self, tmp_path):
        """Existing rc lines are preserved above the marker block."""
        rc = tmp_path / ".bashrc"
        rc.write_text("export PATH=$HOME/bin:$PATH\n", encoding="utf-8")

        _write_rc_with_marker(rc, ['export OPENAI_API_KEY="sk-openai"'])

        content = rc.read_text(encoding="utf-8")
        # Existing content preserved
        assert "export PATH=$HOME/bin:$PATH" in content
        # New block present
        assert 'export OPENAI_API_KEY="sk-openai"' in content
        # Existing content appears before the marker
        assert content.index("export PATH") < content.index("# >>> ap chat wizard exports")

    def test_write_rc_with_marker_idempotent_same_key(self, tmp_path):
        """Running twice with the same key produces exactly one marker block."""
        rc = tmp_path / ".zshrc"
        rc.write_text("", encoding="utf-8")
        export = ['export ANTHROPIC_API_KEY="sk-ant-v1"']

        _write_rc_with_marker(rc, export)
        _write_rc_with_marker(rc, export)

        content = rc.read_text(encoding="utf-8")
        assert content.count("# >>> ap chat wizard exports") == 1
        assert content.count("# <<< ap chat wizard exports") == 1

    def test_write_rc_with_marker_replaces_existing_block(self, tmp_path):
        """Re-running with a new key replaces the old block; no duplication."""
        rc = tmp_path / ".zshrc"
        rc.write_text("# my existing config\n", encoding="utf-8")

        _write_rc_with_marker(rc, ['export ANTHROPIC_API_KEY="sk-ant-old"'])
        _write_rc_with_marker(rc, ['export ANTHROPIC_API_KEY="sk-ant-new"'])

        content = rc.read_text(encoding="utf-8")
        # Exactly one marker block
        assert content.count("# >>> ap chat wizard exports") == 1
        # Only the new key is present
        assert 'sk-ant-new"' in content
        assert "sk-ant-old" not in content
        # Surrounding user content preserved
        assert "# my existing config" in content

    def test_write_rc_preserves_permissions(self, tmp_path):
        """File permissions on the rc file are unchanged after write."""
        rc = tmp_path / ".zshrc"
        rc.write_text("", encoding="utf-8")
        rc.chmod(0o644)

        _write_rc_with_marker(rc, ['export ANTHROPIC_API_KEY="sk-test"'])

        mode = stat.S_IMODE(rc.stat().st_mode)
        assert mode == 0o644

    def test_write_rc_creates_file_if_not_exists(self, tmp_path):
        """If the rc file doesn't exist yet it is created."""
        rc = tmp_path / ".zshrc"
        assert not rc.exists()

        _write_rc_with_marker(rc, ['export OPENAI_API_KEY="sk-new"'])

        assert rc.exists()
        assert 'export OPENAI_API_KEY="sk-new"' in rc.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Wizard flow — save-destination paths (compound integration)
    #
    # Production sequence:
    #   1. Wizard collects provider/key/model from console.input()
    #   2. config.toml written (always)
    #   3. _prompt_save_destination() called when export_lines non-empty
    #   4. User picks destination → rc written / stdout printed / no-op
    # ------------------------------------------------------------------

    _ANTHROPIC_RESPONSE = {
        "data": [
            {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"},
        ]
    }

    def _run_wizard(
        self,
        tmp_path: Path,
        inputs: list[str],
        http_json: dict,
        rc_path: Path | None = None,
    ) -> tuple[str, "ConfigManager"]:
        """Run wizard end-to-end with controlled inputs and isolated config dir.

        Uses real file I/O for rc file tests (tmp_path). Console I/O and
        httpx.get are patched as external boundaries.
        # @mock-exempt: httpx.get is external HTTP; Console wraps terminal I/O
        """
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)

        with (
            patch("httpx.get", return_value=_mock_response(200, http_json)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.status") as mock_status,
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            if rc_path is not None:
                with patch(
                    "adversary_pursuit.agent.provider_setup._detect_shell_rc",
                    return_value=rc_path,
                ):
                    result = run_provider_wizard(config_mgr)
            else:
                result = run_provider_wizard(config_mgr)

        return result, config_mgr

    def test_wizard_save_option_1_config_only(self, tmp_path):
        """Option 1: config.toml written, rc file untouched."""
        rc = tmp_path / ".zshrc"
        rc.write_text("# existing\n", encoding="utf-8")

        # provider=1(anthropic), key, model=1, save=1
        inputs = ["1", "sk-ant-test", "1", "1", "n"]
        result, config_mgr = self._run_wizard(
            tmp_path, inputs, self._ANTHROPIC_RESPONSE, rc_path=rc
        )

        assert result == "claude-3-5-sonnet-20241022"
        assert config_mgr.get_provider_api_key("anthropic") == "sk-ant-test"
        # RC file unchanged — option 1 writes config only
        assert rc.read_text(encoding="utf-8") == "# existing\n"

    def test_wizard_save_option_2_config_plus_rc(self, tmp_path):
        """Option 2: both config.toml and rc file written."""
        rc = tmp_path / ".zshrc"
        rc.write_text("# existing zshrc\n", encoding="utf-8")

        # provider=1(anthropic), key, model=1, save=2
        inputs = ["1", "sk-ant-key", "1", "2", "n"]
        result, config_mgr = self._run_wizard(
            tmp_path, inputs, self._ANTHROPIC_RESPONSE, rc_path=rc
        )

        assert config_mgr.get_provider_api_key("anthropic") == "sk-ant-key"
        rc_content = rc.read_text(encoding="utf-8")
        assert "# >>> ap chat wizard exports" in rc_content
        assert 'export ANTHROPIC_API_KEY="sk-ant-key"' in rc_content
        assert "# existing zshrc" in rc_content

    def test_wizard_save_option_2_idempotent(self, tmp_path):
        """Running wizard twice with option 2 leaves exactly one marker block."""
        rc = tmp_path / ".zshrc"
        rc.write_text("", encoding="utf-8")

        for key in ["sk-ant-first", "sk-ant-second"]:
            inputs = ["1", key, "1", "2", "n"]
            self._run_wizard(tmp_path, inputs, self._ANTHROPIC_RESPONSE, rc_path=rc)

        content = rc.read_text(encoding="utf-8")
        assert content.count("# >>> ap chat wizard exports") == 1
        assert "sk-ant-first" not in content
        assert 'sk-ant-second"' in content

    def test_wizard_save_option_3_stdout_only(self, tmp_path):
        """Option 3: config.toml written, rc untouched, stdout receives export lines."""
        rc = tmp_path / ".zshrc"
        rc.write_text("# untouched\n", encoding="utf-8")

        printed_args: list = []

        def capture_print(*args, **kwargs):
            printed_args.extend(args)

        # @mock-exempt: httpx.get/Console are external I/O boundaries
        # provider=1(anthropic), key, model=1, save=3
        inputs = ["1", "sk-ant-stdout", "1", "3", "n"]
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)
        with (
            patch("httpx.get", return_value=_mock_response(200, self._ANTHROPIC_RESPONSE)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.status") as mock_status,
            patch(
                "adversary_pursuit.agent.provider_setup.Console.print",
                side_effect=capture_print,
            ),
            patch(
                "adversary_pursuit.agent.provider_setup._detect_shell_rc",
                return_value=rc,
            ),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            run_provider_wizard(config_mgr)

        # Config written
        assert config_mgr.get_provider_api_key("anthropic") == "sk-ant-stdout"
        # RC file untouched
        assert rc.read_text(encoding="utf-8") == "# untouched\n"
        # Panel with export lines was printed (Panel object in printed args)
        from rich.panel import Panel as RichPanel

        panel_args = [a for a in printed_args if isinstance(a, RichPanel)]
        assert panel_args, "Expected a Rich Panel to be printed for option 3"
        panel_text = str(panel_args[0].renderable)
        assert "ANTHROPIC_API_KEY" in panel_text

    def test_wizard_save_falls_back_to_stdout_when_shell_unknown(self, tmp_path, monkeypatch):
        """Option 2 + unknown shell → fallback to stdout with a warning."""
        monkeypatch.setenv("SHELL", "/bin/csh")

        printed_args: list = []

        def capture_print(*args, **kwargs):
            printed_args.extend(args)

        # @mock-exempt: httpx.get/Console are external I/O boundaries
        # provider=1(anthropic), key, model=1, save=2 (rc requested but shell unknown)
        inputs = ["1", "sk-ant-csh", "1", "2", "n"]
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)
        with (
            patch("httpx.get", return_value=_mock_response(200, self._ANTHROPIC_RESPONSE)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.status") as mock_status,
            patch(
                "adversary_pursuit.agent.provider_setup.Console.print",
                side_effect=capture_print,
            ),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            run_provider_wizard(config_mgr)

        # Config written despite shell fallback
        assert config_mgr.get_provider_api_key("anthropic") == "sk-ant-csh"
        # Panel printed as fallback
        from rich.panel import Panel as RichPanel

        panel_args = [a for a in printed_args if isinstance(a, RichPanel)]
        assert panel_args, "Expected a Rich Panel when falling back from unknown shell"


# ---------------------------------------------------------------------------
# Config persistence round-trip for provider fields
# (compound integration: wizard output → config.toml → load back → AgentRunner)
# ---------------------------------------------------------------------------


class TestProviderConfigRoundTrip:
    """Compound-interaction test: wizard persists → config reads back → runner uses it.

    This is the real production sequence:
      1. Wizard calls config_mgr.set_agent_selection() + set_provider_api_key()
      2. TOML written to disk at 0600
      3. New ConfigManager instance loads the TOML
      4. AgentRunner picks up the model from config layer
    """

    def test_full_round_trip_anthropic(self, tmp_path):
        config_mgr = make_config_mgr(tmp_path)
        # Simulate what wizard would do after user picks Anthropic + model
        config_mgr.set_provider_api_key("anthropic", "sk-ant-prod-key")
        config_mgr.set_agent_selection("anthropic", "claude-3-5-sonnet-20241022")

        # New ConfigManager reading same dir — simulates next session launch
        config_mgr2 = make_config_mgr(tmp_path)
        assert config_mgr2.get_agent_provider() == "anthropic"
        assert config_mgr2.get_agent_model() == "claude-3-5-sonnet-20241022"
        assert config_mgr2.get_provider_api_key("anthropic") == "sk-ant-prod-key"

        # Permissions preserved
        config_path = tmp_path / "config.toml"
        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600

    def test_runner_picks_up_config_model(self, tmp_path, monkeypatch):
        """AgentRunner uses config model when AP_MODEL env var is not set."""
        monkeypatch.delenv("AP_MODEL", raising=False)

        config_mgr = make_config_mgr(tmp_path)
        config_mgr.set_agent_selection("openai", "gpt-4o")

        # Import here to avoid circular at module level in test collection
        from adversary_pursuit.agent.runner import AgentRunner

        runner = AgentRunner(config_mgr=config_mgr)
        assert runner.model == "gpt-4o"

    def test_ap_model_env_overrides_config(self, tmp_path, monkeypatch):
        """AP_MODEL env var takes precedence over config.toml selection."""
        monkeypatch.setenv("AP_MODEL", "anthropic/claude-override")

        config_mgr = make_config_mgr(tmp_path)
        config_mgr.set_agent_selection("openai", "gpt-4o")

        from adversary_pursuit.agent.runner import AgentRunner

        runner = AgentRunner(config_mgr=config_mgr)
        assert runner.model == "anthropic/claude-override"

    def test_explicit_model_arg_overrides_all(self, tmp_path, monkeypatch):
        """Explicit model= arg beats AP_MODEL env and config."""
        monkeypatch.setenv("AP_MODEL", "from-env-model")

        config_mgr = make_config_mgr(tmp_path)
        config_mgr.set_agent_selection("openai", "gpt-4o")

        from adversary_pursuit.agent.runner import AgentRunner

        runner = AgentRunner(model="explicit-model", config_mgr=config_mgr)
        assert runner.model == "explicit-model"

    def test_default_model_when_nothing_configured(self, tmp_path, monkeypatch):
        """DEFAULT_MODEL is used when AP_MODEL unset and config has no model."""
        monkeypatch.delenv("AP_MODEL", raising=False)
        config_mgr = make_config_mgr(tmp_path)

        from adversary_pursuit.agent.runner import AgentRunner

        runner = AgentRunner(config_mgr=config_mgr)
        assert runner.model == AgentRunner.DEFAULT_MODEL


# ---------------------------------------------------------------------------
# CTI services registry
# ---------------------------------------------------------------------------


class TestCTIServicesRegistry:
    """CTI_SERVICES registry structure and completeness checks."""

    SERVICE_IDS = {
        "shodan", "virustotal", "abuseipdb", "hibp", "otx",
        "urlscan", "censys_pat", "passivetotal",
    }

    def test_eight_services_defined(self):
        assert len(CTI_SERVICES) == 8

    def test_all_expected_service_ids_present(self):
        ids = {s.id for s in CTI_SERVICES}
        assert ids == self.SERVICE_IDS

    def test_all_have_display_name(self):
        for s in CTI_SERVICES:
            assert s.display_name, f"{s.id} missing display_name"

    def test_all_have_validate_url(self):
        for s in CTI_SERVICES:
            assert s.validate_url, f"{s.id} missing validate_url"

    def test_all_have_docs_url(self):
        for s in CTI_SERVICES:
            assert s.docs_url, f"{s.id} missing docs_url"

    def test_all_have_config_keys(self):
        for s in CTI_SERVICES:
            assert s.config_keys, f"{s.id} missing config_keys"

    def test_all_have_prompt_labels_matching_config_keys(self):
        for s in CTI_SERVICES:
            assert len(s.prompt_labels) == len(s.config_keys), (
                f"{s.id}: prompt_labels count ({len(s.prompt_labels)}) "
                f"!= config_keys count ({len(s.config_keys)})"
            )

    def test_passivetotal_has_two_keys(self):
        pt = next(s for s in CTI_SERVICES if s.id == "passivetotal")
        assert pt.config_keys == ["passivetotal_user", "passivetotal_key"]

    def test_censys_uses_pat_not_legacy_id_secret(self):
        censys = next(s for s in CTI_SERVICES if s.id == "censys_pat")
        assert censys.config_keys == ["censys_pat"]
        assert "censys_id" not in censys.config_keys
        assert "censys_secret" not in censys.config_keys


# ---------------------------------------------------------------------------
# mask_secret
# ---------------------------------------------------------------------------


class TestMaskSecret:
    def test_masks_all_but_last_four(self):
        assert mask_secret("abcdefgh") == "****efgh"

    def test_short_string_fully_masked(self):
        assert mask_secret("ab") == "**"

    def test_exactly_four_chars(self):
        assert mask_secret("abcd") == "abcd"

    def test_custom_visible(self):
        assert mask_secret("abcdefgh", visible=2) == "******gh"


# ---------------------------------------------------------------------------
# _validate_cti_key — per-method auth dispatch + response handling
# ---------------------------------------------------------------------------


def _mock_httpx_response(status_code: int) -> MagicMock:
    """Return a mock httpx Response with the given status code."""
    resp = MagicMock()
    resp.status_code = status_code
    return resp


class TestValidateCTIKey:
    """_validate_cti_key returns (True, ...) on success and (False, ...) on failure."""

    def _spec(self, service_id: str) -> CTIServiceSpec:
        return next(s for s in CTI_SERVICES if s.id == service_id)

    # --- Shodan (query_param) ---
    def test_shodan_200_returns_true(self):
        spec = self._spec("shodan")
        with patch("httpx.get", return_value=_mock_httpx_response(200)):
            ok, msg = _validate_cti_key(spec, ["test-key"])
        assert ok is True

    def test_shodan_401_returns_false_auth_failed(self):
        spec = self._spec("shodan")
        with patch("httpx.get", return_value=_mock_httpx_response(401)):
            ok, msg = _validate_cti_key(spec, ["bad-key"])
        assert ok is False
        assert "Authentication failed" in msg

    def test_shodan_403_returns_false_auth_failed(self):
        spec = self._spec("shodan")
        with patch("httpx.get", return_value=_mock_httpx_response(403)):
            ok, msg = _validate_cti_key(spec, ["bad-key"])
        assert ok is False
        assert "Authentication failed" in msg

    def test_shodan_429_returns_true_rate_limited(self):
        spec = self._spec("shodan")
        with patch("httpx.get", return_value=_mock_httpx_response(429)):
            ok, msg = _validate_cti_key(spec, ["valid-key"])
        assert ok is True

    def test_shodan_network_error_returns_false(self):
        spec = self._spec("shodan")
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            ok, msg = _validate_cti_key(spec, ["test-key"])
        assert ok is False
        assert "Network unreachable" in msg

    def test_shodan_timeout_returns_true_saving_anyway(self):
        spec = self._spec("shodan")
        with patch(
            "httpx.get",
            side_effect=httpx.TimeoutException("timeout", request=MagicMock()),
        ):
            ok, msg = _validate_cti_key(spec, ["test-key"])
        assert ok is True
        assert "timed out" in msg.lower() or "saving anyway" in msg.lower()

    # --- VirusTotal (header_x_apikey) ---
    def test_virustotal_200_returns_true(self):
        spec = self._spec("virustotal")
        with patch("httpx.get", return_value=_mock_httpx_response(200)) as mock_get:
            ok, msg = _validate_cti_key(spec, ["vt-key"])
        assert ok is True
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["x-apikey"] == "vt-key"

    def test_virustotal_401_returns_false(self):
        spec = self._spec("virustotal")
        with patch("httpx.get", return_value=_mock_httpx_response(401)):
            ok, msg = _validate_cti_key(spec, ["bad-vt-key"])
        assert ok is False
        assert "Authentication failed" in msg

    # --- AbuseIPDB (header_key) ---
    def test_abuseipdb_200_returns_true(self):
        spec = self._spec("abuseipdb")
        with patch("httpx.get", return_value=_mock_httpx_response(200)) as mock_get:
            ok, msg = _validate_cti_key(spec, ["abuse-key"])
        assert ok is True
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["Key"] == "abuse-key"

    # --- HIBP (header_key with hibp-api-key header) ---
    def test_hibp_200_returns_true(self):
        spec = self._spec("hibp")
        with patch("httpx.get", return_value=_mock_httpx_response(200)) as mock_get:
            ok, msg = _validate_cti_key(spec, ["hibp-key"])
        assert ok is True
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["hibp-api-key"] == "hibp-key"

    # --- OTX (header_x_otx) ---
    def test_otx_200_returns_true(self):
        spec = self._spec("otx")
        with patch("httpx.get", return_value=_mock_httpx_response(200)) as mock_get:
            ok, msg = _validate_cti_key(spec, ["otx-key"])
        assert ok is True
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["X-OTX-API-KEY"] == "otx-key"

    # --- URLScan (header_api_key) ---
    def test_urlscan_200_returns_true(self):
        spec = self._spec("urlscan")
        with patch("httpx.get", return_value=_mock_httpx_response(200)) as mock_get:
            ok, msg = _validate_cti_key(spec, ["urlscan-key"])
        assert ok is True
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["API-Key"] == "urlscan-key"

    # --- Censys PAT (bearer) ---
    def test_censys_pat_200_returns_true(self):
        spec = self._spec("censys_pat")
        with patch("httpx.get", return_value=_mock_httpx_response(200)) as mock_get:
            ok, msg = _validate_cti_key(spec, ["pat-token"])
        assert ok is True
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer pat-token"

    # --- PassiveTotal (basic_auth) ---
    def test_passivetotal_200_returns_true(self):
        spec = self._spec("passivetotal")
        with patch("httpx.get", return_value=_mock_httpx_response(200)) as mock_get:
            ok, msg = _validate_cti_key(spec, ["user@example.com", "pt-api-key"])
        assert ok is True
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["auth"] == ("user@example.com", "pt-api-key")

    def test_passivetotal_401_returns_false(self):
        spec = self._spec("passivetotal")
        with patch("httpx.get", return_value=_mock_httpx_response(401)):
            ok, msg = _validate_cti_key(spec, ["bad-user", "bad-key"])
        assert ok is False
        assert "Authentication failed" in msg

    def test_generic_request_error_returns_false(self):
        spec = self._spec("shodan")
        with patch("httpx.get", side_effect=httpx.RequestError("err", request=MagicMock())):
            ok, msg = _validate_cti_key(spec, ["key"])
        assert ok is False
        assert "Network error" in msg

    def test_unexpected_status_returns_false(self):
        spec = self._spec("shodan")
        with patch("httpx.get", return_value=_mock_httpx_response(500)):
            ok, msg = _validate_cti_key(spec, ["key"])
        assert ok is False
        assert "500" in msg


# ---------------------------------------------------------------------------
# _compose_cti_export_lines + _write_cti_rc_with_marker
# ---------------------------------------------------------------------------


class TestCTIExportHelpers:
    def test_compose_cti_export_lines_single_key(self):
        lines = _compose_cti_export_lines({"shodan": "shdn-key"})
        assert lines == ['export SHODAN_API_KEY="shdn-key"']

    def test_compose_cti_export_lines_multiple_keys(self):
        lines = _compose_cti_export_lines({
            "shodan": "shdn-key",
            "virustotal": "vt-key",
        })
        assert 'export SHODAN_API_KEY="shdn-key"' in lines
        assert 'export VIRUSTOTAL_API_KEY="vt-key"' in lines

    def test_compose_cti_export_lines_skips_empty(self):
        lines = _compose_cti_export_lines({"shodan": "", "virustotal": "vt-key"})
        assert not any("SHODAN" in l for l in lines)
        assert 'export VIRUSTOTAL_API_KEY="vt-key"' in lines

    def test_compose_cti_export_lines_censys_pat(self):
        lines = _compose_cti_export_lines({"censys_pat": "my-pat"})
        assert lines == ['export CENSYS_PAT="my-pat"']

    def test_compose_cti_export_lines_passivetotal(self):
        lines = _compose_cti_export_lines({
            "passivetotal_user": "user@example.com",
            "passivetotal_key": "pt-key",
        })
        assert 'export PT_USERNAME="user@example.com"' in lines
        assert 'export PT_API_KEY="pt-key"' in lines

    def test_write_cti_rc_with_marker_creates_block(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# existing\n", encoding="utf-8")
        _write_cti_rc_with_marker(rc, ['export SHODAN_API_KEY="test"'])
        content = rc.read_text(encoding="utf-8")
        assert "# >>> ap cti wizard exports" in content
        assert 'export SHODAN_API_KEY="test"' in content
        assert "# existing" in content

    def test_write_cti_rc_with_marker_idempotent(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text("", encoding="utf-8")
        _write_cti_rc_with_marker(rc, ['export SHODAN_API_KEY="v1"'])
        _write_cti_rc_with_marker(rc, ['export SHODAN_API_KEY="v2"'])
        content = rc.read_text(encoding="utf-8")
        assert content.count("# >>> ap cti wizard exports") == 1
        assert "v1" not in content
        assert "v2" in content

    def test_cti_and_llm_markers_coexist(self, tmp_path):
        """CTI and LLM export blocks can coexist in the same rc file."""
        rc = tmp_path / ".zshrc"
        rc.write_text("", encoding="utf-8")
        _write_rc_with_marker(rc, ['export ANTHROPIC_API_KEY="ant-key"'])
        _write_cti_rc_with_marker(rc, ['export SHODAN_API_KEY="shdn-key"'])
        content = rc.read_text(encoding="utf-8")
        assert content.count("# >>> ap chat wizard exports") == 1
        assert content.count("# >>> ap cti wizard exports") == 1
        assert "ANTHROPIC_API_KEY" in content
        assert "SHODAN_API_KEY" in content


# ---------------------------------------------------------------------------
# run_cti_credentials_wizard — flow tests
# ---------------------------------------------------------------------------


def make_config_mgr_cti(tmp_path: Path) -> "ConfigManager":
    return ConfigManager(config_dir=tmp_path)


class TestRunCTICredentialsWizard:
    """Tests for run_cti_credentials_wizard() flow."""

    def test_no_returns_empty_configured(self, tmp_path):
        """User declines CTI setup for all services → empty configured dict."""
        # For all 8 services: user says "n" to configure prompt
        # run_cti_credentials_wizard iterates over services and shows
        # "Configure X? [y/N]:" for each; user replies "n" each time.
        # The wizard itself also has dotfile export prompt logic.
        config_mgr = make_config_mgr_cti(tmp_path)
        # "n" for each of the 8 services
        inputs = ["n"] * 8
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
            patch("adversary_pursuit.agent.provider_setup._validate_cti_key"),
        ):
            result = run_cti_credentials_wizard(config_mgr)
        assert all(v is False for v in result.values())

    def test_skip_each_service(self, tmp_path):
        """Explicit 's' (skip) for each service produces all-False result."""
        config_mgr = make_config_mgr_cti(tmp_path)
        inputs = ["s"] * 8
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            result = run_cti_credentials_wizard(config_mgr)
        assert all(v is False for v in result.values())

    def test_save_after_successful_validate(self, tmp_path):
        """Shodan key: user enters key, validation passes, key saved to config."""
        config_mgr = make_config_mgr_cti(tmp_path)
        # For Shodan (first service): "y" configure, enter key "shdn-test"
        # For all remaining 7 services: "n" skip
        inputs = ["y", "shdn-test"] + ["n"] * 7 + ["1"]  # save dest = 1
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
            patch(
                "adversary_pursuit.agent.provider_setup.httpx.get",
                return_value=_mock_httpx_response(200),
            ),
        ):
            result = run_cti_credentials_wizard(config_mgr)
        assert result.get("shodan") is True
        assert config_mgr.get_api_key("shodan") == "shdn-test"

    def test_mask_secret_used_for_existing_value(self, tmp_path):
        """When a service already has a key, it is shown masked in the prompt."""
        config_mgr = make_config_mgr_cti(tmp_path)
        # Pre-set Shodan key
        config_mgr.set("api_keys.shodan", "supersecretkey12345")

        printed_args: list = []

        def capture_print(*args, **kwargs):
            printed_args.extend(str(a) for a in args)

        # For Shodan: existing key shown, user picks "k" (keep)
        # For remaining 7: "n"
        inputs = ["k"] + ["n"] * 7
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.print",
                side_effect=capture_print,
            ),
        ):
            result = run_cti_credentials_wizard(config_mgr)
        # Masked value must appear in output, not the raw key
        all_output = " ".join(printed_args)
        assert "supersecretkey12345" not in all_output
        # Should see the masked tail
        assert mask_secret("supersecretkey12345") in all_output

    def test_existing_value_keep_default_preserves_config(self, tmp_path):
        """When user keeps existing value, it remains in config unchanged."""
        config_mgr = make_config_mgr_cti(tmp_path)
        config_mgr.set("api_keys.shodan", "existing-shodan-key")
        # "k" = keep for shodan, "n" for rest
        inputs = ["k"] + ["n"] * 7
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            result = run_cti_credentials_wizard(config_mgr)
        assert config_mgr.get_api_key("shodan") == "existing-shodan-key"
        assert result.get("shodan") is True

    def test_validation_failure_save_anyway_yes(self, tmp_path):
        """Validation fails but user elects to save anyway."""
        config_mgr = make_config_mgr_cti(tmp_path)
        # Shodan: configure, enter key, validation returns 401, save anyway=y
        # After validation failure + "save anyway=y": the wizard collects the key
        # and offers dotfile export (save_dest=1 = config only)
        inputs = ["y", "bad-key", "y"] + ["n"] * 7 + ["1"]
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
            patch(
                "adversary_pursuit.agent.provider_setup.httpx.get",
                return_value=_mock_httpx_response(401),
            ),
        ):
            result = run_cti_credentials_wizard(config_mgr)
        assert result.get("shodan") is True
        assert config_mgr.get_api_key("shodan") == "bad-key"

    def test_validation_failure_save_anyway_no(self, tmp_path):
        """Validation fails and user declines to save → service not configured."""
        config_mgr = make_config_mgr_cti(tmp_path)
        inputs = ["y", "bad-key", "n"] + ["n"] * 7
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
            patch(
                "adversary_pursuit.agent.provider_setup.httpx.get",
                return_value=_mock_httpx_response(401),
            ),
        ):
            result = run_cti_credentials_wizard(config_mgr)
        assert result.get("shodan") is False
        assert config_mgr.get_api_key("shodan") is None

    def test_multi_key_passivetotal_both_saved(self, tmp_path):
        """PassiveTotal: both username and API key are prompted and saved."""
        config_mgr = make_config_mgr_cti(tmp_path)
        # Skip all 7 services before passivetotal, configure passivetotal
        # Order: shodan, virustotal, abuseipdb, hibp, otx, urlscan, censys_pat, passivetotal
        inputs = ["n"] * 7 + ["y", "user@example.com", "pt-api-key"] + ["1"]
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
            patch(
                "adversary_pursuit.agent.provider_setup.httpx.get",
                return_value=_mock_httpx_response(200),
            ),
        ):
            result = run_cti_credentials_wizard(config_mgr)
        assert result.get("passivetotal") is True
        assert config_mgr.get_api_key("passivetotal_user") == "user@example.com"
        assert config_mgr.get_api_key("passivetotal_key") == "pt-api-key"

    def test_passivetotal_basic_auth_validation(self, tmp_path):
        """PassiveTotal validation uses basic_auth (username, password) args."""
        config_mgr = make_config_mgr_cti(tmp_path)
        inputs = ["n"] * 7 + ["y", "user@example.com", "pt-api-key"] + ["1"]
        with (
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
            patch(
                "adversary_pursuit.agent.provider_setup.httpx.get",
                return_value=_mock_httpx_response(200),
            ) as mock_get,
        ):
            run_cti_credentials_wizard(config_mgr)
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["auth"] == ("user@example.com", "pt-api-key")


# ---------------------------------------------------------------------------
# Compound integration: full wizard flow with CTI step
# ---------------------------------------------------------------------------


class TestWizardFlowWithCTI:
    """End-to-end test: LLM wizard → CTI wizard → config persistence."""

    _ANTHROPIC_RESPONSE = {
        "data": [
            {"id": "claude-3-5-sonnet-20241022", "display_name": "Claude 3.5 Sonnet"},
        ]
    }

    def test_full_wizard_with_cti_shodan_configured(self, tmp_path):
        """Production sequence: LLM wizard + CTI wizard → both persisted in config.

        This is the compound-interaction test exercising:
          LLM provider selection → key validation → model selection → config save
          → CTI offer → Shodan configure → validation → CTI save
        """
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)

        # LLM wizard inputs: provider=1 (Anthropic), key, model=1, save_dest=1
        # CTI wizard offer: y
        # Shodan: y configure, enter key
        # Remaining 7 CTI services: n skip
        # CTI dotfile export: 1 (config only)
        inputs = ["1", "sk-ant-key", "1", "1", "y", "y", "shdn-key"] + ["n"] * 7 + ["1"]

        # Both LLM and CTI validation use httpx.get; use side_effect to return
        # different responses. First call is the LLM list-models endpoint,
        # subsequent call is the Shodan validation endpoint.
        llm_response = _mock_response(200, self._ANTHROPIC_RESPONSE)
        cti_response = _mock_httpx_response(200)
        http_responses = [llm_response, cti_response]

        with (
            patch(
                "adversary_pursuit.agent.provider_setup.httpx.get",
                side_effect=http_responses,
            ),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=inputs,
            ),
            patch("adversary_pursuit.agent.provider_setup.Console.status") as mock_status,
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            result = run_provider_wizard(config_mgr)

        # LLM persisted
        assert result == "claude-3-5-sonnet-20241022"
        assert config_mgr.get_agent_provider() == "anthropic"
        assert config_mgr.get_provider_api_key("anthropic") == "sk-ant-key"
        # CTI persisted
        assert config_mgr.get_api_key("shodan") == "shdn-key"
