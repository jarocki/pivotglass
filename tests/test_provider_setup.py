"""Tests for agent/provider_setup.py — interactive provider/model wizard.

# @mock-exempt: httpx.get is an external HTTP boundary (provider list-models
# endpoints). All provider HTTP calls are mocked via unittest.mock.patch so
# tests run hermetically without live API keys or network access.

Production sequence tested here:
  ProviderSpec registry → list_models() → _build_model_string() → wizard flow

@decision DEC-TEST-PROVIDER-SETUP-001
@title Mock httpx.get at the HTTP boundary for hermetic provider tests
@status accepted
@rationale The provider wizard's sole external I/O is httpx.get calls to
           list-models endpoints. Mocking at this boundary lets us exercise:
           (1) all provider-specific JSON parsing paths, (2) auth header
           construction, (3) ProviderAuthError on 401/403, (4) ProviderConnectionError
           on network failure, (5) the full wizard flow with mocked Rich prompts.
           We do NOT mock internal functions — the production dispatch path is
           exercised end-to-end up to the HTTP boundary.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from adversary_pursuit.agent.provider_setup import (
    PROVIDER_BY_ID,
    PROVIDERS,
    ProviderAuthError,
    ProviderConnectionError,
    _build_model_string,
    list_models,
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
        result = _build_model_string(
            PROVIDER_BY_ID["anthropic"], "claude-3-5-sonnet-20241022"
        )
        assert result == "claude-3-5-sonnet-20241022"

    def test_openai_bare_model_id(self):
        """OpenAI prefix is empty — litellm accepts bare model IDs."""
        result = _build_model_string(PROVIDER_BY_ID["openai"], "gpt-4o")
        assert result == "gpt-4o"

    def test_openrouter_prefixed(self):
        result = _build_model_string(
            PROVIDER_BY_ID["openrouter"], "anthropic/claude-3.5-sonnet"
        )
        assert result == "openrouter/anthropic/claude-3.5-sonnet"

    def test_google_prefixed(self):
        result = _build_model_string(
            PROVIDER_BY_ID["google"], "models/gemini-2.0-flash-exp"
        )
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
        with patch(
            "httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)
        ) as mock_get:
            list_models(PROVIDER_BY_ID["anthropic"], "sk-ant-test-key")
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["headers"]["x-api-key"] == "sk-ant-test-key"

    def test_sends_anthropic_version_header(self):
        with patch(
            "httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)
        ) as mock_get:
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
        with patch(
            "httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)
        ) as mock_get:
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
        with patch(
            "httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)
        ) as mock_get:
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
        with patch(
            "httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)
        ) as mock_get:
            list_models(PROVIDER_BY_ID["google"], "AIza-test-key")
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["key"] == "AIza-test-key"

    def test_no_auth_header_sent(self):
        with patch(
            "httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)
        ) as mock_get:
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
        with patch(
            "httpx.get", return_value=_mock_response(200, self._RESPONSE_JSON)
        ) as mock_get:
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
        assert "connect" in str(exc_info.value).lower() or "Anthropic" in str(
            exc_info.value
        )

    def test_timeout_raises_provider_connection_error(self):
        with patch(
            "httpx.get",
            side_effect=httpx.TimeoutException("timed out", request=MagicMock()),
        ):
            with pytest.raises(ProviderConnectionError):
                list_models(PROVIDER_BY_ID["ollama"], None)

    def test_generic_request_error_raises_provider_connection_error(self):
        with patch(
            "httpx.get", side_effect=httpx.RequestError("generic", request=MagicMock())
        ):
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

    def _run_wizard_with_inputs(
        self,
        tmp_path: Path,
        provider_choice: int,
        api_key: str,
        model_choice: int,
        http_json: dict,
        http_status: int = 200,
    ) -> tuple[str, ConfigManager]:
        """Helper: run wizard with mocked console input and HTTP."""
        from adversary_pursuit.agent.provider_setup import run_provider_wizard

        config_mgr = make_config_mgr(tmp_path)

        # Sequence of console.input() calls: provider choice, api_key, model choice
        input_side_effects = [str(provider_choice), api_key, str(model_choice)]

        with (
            patch("httpx.get", return_value=_mock_response(http_status, http_json)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=input_side_effects,
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

        # Ollama only needs 2 inputs: provider choice + model choice (no key)
        input_side_effects = ["5", "1"]

        with (
            patch("httpx.get", return_value=_mock_response(200, ollama_response)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=input_side_effects,
            ),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.status"
            ) as mock_status,
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

        input_side_effects = ["4", "AIza-test-key", "1"]  # provider 4 = Google

        with (
            patch("httpx.get", return_value=_mock_response(200, google_response)),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.input",
                side_effect=input_side_effects,
            ),
            patch(
                "adversary_pursuit.agent.provider_setup.Console.status"
            ) as mock_status,
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
            patch(
                "adversary_pursuit.agent.provider_setup.Console.status"
            ) as mock_status,
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
            patch(
                "adversary_pursuit.agent.provider_setup.Console.status"
            ) as mock_status,
            patch("adversary_pursuit.agent.provider_setup.Console.print"),
        ):
            mock_status.return_value.__enter__ = MagicMock(return_value=None)
            mock_status.return_value.__exit__ = MagicMock(return_value=False)
            with pytest.raises(SystemExit):
                run_provider_wizard(config_mgr)


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
        import stat

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
