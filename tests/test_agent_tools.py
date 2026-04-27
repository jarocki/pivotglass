"""Tests for the agent tool layer (Issue #25 — smolagents integration).

# @mock-exempt: httpx.AsyncClient is an external HTTP boundary for module calls.
# The tool layer tests focus on the dispatch logic and ToolContext wiring,
# mocking the module's hunt() at the asyncio boundary — not internal logic.

Production sequence: ToolContext(tmp dirs) -> create_tools() -> execute_tool()
The LLM is NOT tested here — that's a separate concern requiring litellm mocks.
This test file validates the tool dispatch layer works correctly before any
LLM integration.

@decision DEC-TEST-AGENT-001
@title Mock module.hunt() at the asyncio boundary for hermetic tool tests
@status accepted
@rationale The tool tests must run without live API keys. Rather than mocking
           httpx, we mock hunt() directly on the instantiated module — this is
           the boundary between the tool layer and the module layer. It tests
           that ToolContext.run_module() correctly: (1) looks up the module,
           (2) initializes it, (3) calls hunt(), (4) stores in workspace,
           (5) scores, (6) formats summary. All business logic in the tool
           layer is exercised; the module's network layer is bypassed.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.agent.tools import (
    ToolContext,
    create_tools,
    execute_tool,
    _workspace_summary,
    _search_workspace,
)
from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.core.workspace import WorkspaceManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_ctx(tmp_path):
    """ToolContext with temp config + workspace dirs (no disk side-effects)."""
    config_dir = tmp_path / "config"
    workspace_dir = tmp_path / "workspaces"
    config_dir.mkdir()
    workspace_dir.mkdir()
    ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
    # Initialize default workspace so tests don't hit missing-workspace errors
    ctx.workspace_mgr.create("default")
    ctx.workspace_mgr.switch("default")
    return ctx


SAMPLE_IP_RESULTS = [
    {"type": "ipv4-addr", "value": "1.2.3.4"},
    {"type": "domain-name", "value": "evil.example.com"},
]

SAMPLE_DOMAIN_RESULTS = [
    {"type": "domain-name", "value": "example.com"},
    {"type": "ipv4-addr", "value": "93.184.216.34"},
]


# ---------------------------------------------------------------------------
# ToolContext initialization
# ---------------------------------------------------------------------------

class TestToolContextInit:
    """ToolContext initializes cleanly with temp directories."""

    def test_init_with_tmp_dirs(self, tmp_path):
        """ToolContext can be created with tmp config and workspace dirs."""
        ctx = ToolContext(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        assert ctx.config_mgr is not None
        assert ctx.config is not None
        assert ctx.workspace_mgr is not None
        assert ctx.plugin_mgr is not None
        assert ctx.scoring is not None

    def test_plugins_loaded(self, tmp_ctx):
        """Plugin manager loads built-in modules after ToolContext init."""
        modules = tmp_ctx.plugin_mgr.list_modules()
        module_names = [m["name"] for m in modules]
        assert "osint/dns_resolve" in module_names
        assert "osint/whois_lookup" in module_names
        assert "osint/abuseipdb" in module_names
        assert "osint/shodan_ip" in module_names
        assert "osint/hibp" in module_names
        assert "cti/otx" in module_names
        assert "osint/urlscan" in module_names

    def test_config_loaded(self, tmp_ctx):
        """Config loads with defaults when no config file exists."""
        assert tmp_ctx.config is not None
        assert tmp_ctx.config.general is not None
        assert tmp_ctx.config.api_keys is not None


# ---------------------------------------------------------------------------
# create_tools — tool definition schema
# ---------------------------------------------------------------------------

class TestCreateTools:
    """create_tools returns correct OpenAI function-calling definitions."""

    def test_returns_list(self, tmp_ctx):
        """create_tools returns a list."""
        tools = create_tools(tmp_ctx)
        assert isinstance(tools, list)

    def test_returns_nine_tools(self, tmp_ctx):
        """create_tools returns exactly 9 tool definitions."""
        tools = create_tools(tmp_ctx)
        assert len(tools) == 9

    def test_all_tools_have_type_function(self, tmp_ctx):
        """All tool definitions have type='function'."""
        tools = create_tools(tmp_ctx)
        for tool in tools:
            assert tool["type"] == "function", f"Tool missing type=function: {tool}"

    def test_all_tools_have_function_block(self, tmp_ctx):
        """All tool definitions have a 'function' block with name and description."""
        tools = create_tools(tmp_ctx)
        for tool in tools:
            fn = tool["function"]
            assert "name" in fn, f"Missing name in tool: {tool}"
            assert "description" in fn, f"Missing description in tool: {tool}"
            assert isinstance(fn["description"], str)
            assert len(fn["description"]) > 0

    def test_all_tools_have_parameters(self, tmp_ctx):
        """All tool definitions have a parameters block."""
        tools = create_tools(tmp_ctx)
        for tool in tools:
            fn = tool["function"]
            assert "parameters" in fn, f"Missing parameters in tool: {fn['name']}"
            params = fn["parameters"]
            assert params["type"] == "object", f"Parameters type must be 'object': {fn['name']}"

    def test_expected_tool_names(self, tmp_ctx):
        """create_tools includes all expected tool names."""
        tools = create_tools(tmp_ctx)
        names = {t["function"]["name"] for t in tools}
        expected = {
            "dns_resolve",
            "whois_lookup",
            "check_ip_reputation",
            "shodan_host_lookup",
            "check_breaches",
            "otx_threat_intel",
            "scan_url",
            "get_workspace_summary",
            "search_workspace",
        }
        assert names == expected

    def test_dns_resolve_has_required_domain(self, tmp_ctx):
        """dns_resolve tool has 'domain' as a required parameter."""
        tools = create_tools(tmp_ctx)
        dns_tool = next(t for t in tools if t["function"]["name"] == "dns_resolve")
        params = dns_tool["function"]["parameters"]
        assert "domain" in params["properties"]
        assert "domain" in params["required"]

    def test_check_ip_reputation_has_required_ip(self, tmp_ctx):
        """check_ip_reputation tool has 'ip_address' as required."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "check_ip_reputation")
        params = tool["function"]["parameters"]
        assert "ip_address" in params["properties"]
        assert "ip_address" in params["required"]

    def test_workspace_tools_have_no_required_params(self, tmp_ctx):
        """get_workspace_summary takes no required parameters."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "get_workspace_summary")
        params = tool["function"]["parameters"]
        # Empty properties or no required
        assert "required" not in params or len(params.get("required", [])) == 0

    def test_openai_compatible_schema(self, tmp_ctx):
        """Tool schema is JSON-serializable (OpenAI-compatible)."""
        tools = create_tools(tmp_ctx)
        # Should not raise
        serialized = json.dumps(tools)
        roundtripped = json.loads(serialized)
        assert len(roundtripped) == 9


# ---------------------------------------------------------------------------
# execute_tool — dispatch to correct modules
# ---------------------------------------------------------------------------

class TestExecuteToolDispatch:
    """execute_tool dispatches to the correct module and returns string results."""

    def _make_mock_module(self, results):
        """Create a mock PursuitModule that returns given results from hunt()."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def test_unknown_tool_returns_error(self, tmp_ctx):
        """execute_tool returns an error string for unknown tool names."""
        result = execute_tool(tmp_ctx, "nonexistent_tool", {})
        assert "Unknown tool" in result
        assert "nonexistent_tool" in result

    def test_dns_resolve_dispatches_to_dns_module(self, tmp_ctx):
        """execute_tool('dns_resolve') runs the osint/dns_resolve module."""
        mock_mod = self._make_mock_module(SAMPLE_DOMAIN_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            result = execute_tool(tmp_ctx, "dns_resolve", {"domain": "example.com"})
            assert isinstance(result, str)
            assert "Found" in result
            # Verify get_module was called with correct path
            mock_get.assert_called_once_with("osint/dns_resolve")

    def test_whois_lookup_dispatches(self, tmp_ctx):
        """execute_tool('whois_lookup') runs the osint/whois_lookup module."""
        mock_mod = self._make_mock_module(SAMPLE_DOMAIN_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            result = execute_tool(tmp_ctx, "whois_lookup", {"target": "example.com"})
            assert isinstance(result, str)
            mock_get.assert_called_once_with("osint/whois_lookup")

    def test_check_ip_reputation_dispatches(self, tmp_ctx):
        """execute_tool('check_ip_reputation') runs abuseipdb module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            result = execute_tool(tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"})
            assert isinstance(result, str)
            mock_get.assert_called_once_with("osint/abuseipdb")

    def test_shodan_host_lookup_dispatches(self, tmp_ctx):
        """execute_tool('shodan_host_lookup') runs osint/shodan_ip module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            result = execute_tool(tmp_ctx, "shodan_host_lookup", {"ip_address": "1.2.3.4"})
            assert isinstance(result, str)
            mock_get.assert_called_once_with("osint/shodan_ip")

    def test_check_breaches_dispatches(self, tmp_ctx):
        """execute_tool('check_breaches') runs osint/hibp module."""
        mock_mod = self._make_mock_module([{"type": "email-addr", "value": "user@example.com"}])
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            result = execute_tool(tmp_ctx, "check_breaches", {"email": "user@example.com"})
            assert isinstance(result, str)
            mock_get.assert_called_once_with("osint/hibp")

    def test_otx_threat_intel_dispatches(self, tmp_ctx):
        """execute_tool('otx_threat_intel') runs cti/otx module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            result = execute_tool(tmp_ctx, "otx_threat_intel", {"target": "1.2.3.4"})
            assert isinstance(result, str)
            mock_get.assert_called_once_with("cti/otx")

    def test_scan_url_dispatches(self, tmp_ctx):
        """execute_tool('scan_url') runs osint/urlscan module."""
        mock_mod = self._make_mock_module([{"type": "url", "value": "http://evil.example.com"}])
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            result = execute_tool(tmp_ctx, "scan_url", {"url": "http://evil.example.com"})
            assert isinstance(result, str)
            mock_get.assert_called_once_with("osint/urlscan")

    def test_module_not_found_returns_error(self, tmp_ctx):
        """execute_tool returns error string when module not found."""
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=None):
            result = execute_tool(tmp_ctx, "dns_resolve", {"domain": "example.com"})
        assert "Error" in result

    def test_module_exception_returns_error(self, tmp_ctx):
        """execute_tool returns error string when module raises exception."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(side_effect=RuntimeError("Network error"))
        mock_mod.initialize = MagicMock()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = execute_tool(tmp_ctx, "dns_resolve", {"domain": "example.com"})
        assert "Error" in result


# ---------------------------------------------------------------------------
# execute_tool — workspace tools
# ---------------------------------------------------------------------------

class TestWorkspaceTools:
    """execute_tool handles get_workspace_summary and search_workspace."""

    def test_get_workspace_summary_returns_string(self, tmp_ctx):
        """execute_tool('get_workspace_summary', {}) returns a string."""
        result = execute_tool(tmp_ctx, "get_workspace_summary", {})
        assert isinstance(result, str)
        assert "Workspace" in result or "workspace" in result.lower()

    def test_get_workspace_summary_includes_counts(self, tmp_ctx):
        """Workspace summary includes total indicators and score."""
        result = execute_tool(tmp_ctx, "get_workspace_summary", {})
        assert "indicators" in result.lower() or "Total" in result

    def test_search_workspace_empty_returns_message(self, tmp_ctx):
        """search_workspace on empty workspace returns 'no objects' message."""
        result = execute_tool(tmp_ctx, "search_workspace", {})
        assert isinstance(result, str)
        # Empty workspace should indicate no results found
        assert "No" in result or "0" in result or "no" in result.lower()

    def test_search_workspace_with_type_filter(self, tmp_ctx):
        """search_workspace with type_filter filters by STIX type."""
        result = execute_tool(tmp_ctx, "search_workspace", {"type_filter": "ipv4-addr"})
        assert isinstance(result, str)

    def test_search_workspace_after_storing_objects(self, tmp_ctx):
        """search_workspace returns stored objects after a module run."""
        # Store some objects directly
        from adversary_pursuit.models.stix import dict_to_stix
        objects = [{"type": "ipv4-addr", "value": "1.2.3.4"}]
        tmp_ctx.workspace_mgr.store_stix_objects(objects, "test/module", "1.2.3.4")

        result = execute_tool(tmp_ctx, "search_workspace", {"type_filter": "ipv4-addr"})
        assert "1.2.3.4" in result or "Found 1" in result


# ---------------------------------------------------------------------------
# run_module — stores results and triggers scoring
# ---------------------------------------------------------------------------

class TestRunModule:
    """ToolContext.run_module stores results in workspace and scores them."""

    def _make_mock_module(self, results):
        """Create a mock PursuitModule."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def test_run_module_stores_stix_objects(self, tmp_ctx):
        """run_module stores STIX objects in the workspace."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/dns_resolve", "example.com", {})

        assert "results" in result
        assert "summary" in result
        assert result["total_points"] >= 0

        # Verify objects are in workspace
        objects = tmp_ctx.workspace_mgr.get_stix_objects()
        assert len(objects) >= 1

    def test_run_module_triggers_scoring(self, tmp_ctx):
        """run_module awards points for new STIX indicators."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        # IP and domain should score
        assert result["total_points"] > 0
        assert len(result["score_events"]) > 0

    def test_run_module_returns_summary_string(self, tmp_ctx):
        """run_module returns a non-empty summary string."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/dns_resolve", "example.com", {})

        assert isinstance(result["summary"], str)
        assert "Found" in result["summary"]

    def test_run_module_unknown_path_returns_error(self, tmp_ctx):
        """run_module returns error dict for unknown module paths."""
        result = tmp_ctx.run_module("osint/nonexistent_module", "target", {})
        assert "error" in result

    def test_run_module_logs_module_run(self, tmp_ctx):
        """run_module creates a module run record in the workspace."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        runs = tmp_ctx.workspace_mgr.get_module_runs()
        assert len(runs) == 1
        assert runs[0]["module_name"] == "osint/abuseipdb"
        assert runs[0]["target"] == "1.2.3.4"

    def test_run_module_scores_stored_in_workspace(self, tmp_ctx):
        """run_module score events are stored in workspace database."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/dns_resolve", "example.com", {})

        total = tmp_ctx.workspace_mgr.get_total_score()
        assert total > 0

    def test_run_module_passes_options_to_hunt(self, tmp_ctx):
        """run_module passes options dict to module.hunt()."""
        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {"MAX_AGE": "30"})

        mock_mod.hunt.assert_called_once_with("1.2.3.4", {"MAX_AGE": "30"})

    def test_run_module_initializes_with_api_key(self, tmp_ctx):
        """run_module calls module.initialize() with api_key from config."""
        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        mock_mod.initialize.assert_called_once()
        call_args = mock_mod.initialize.call_args[0][0]
        assert "api_key" in call_args


# ---------------------------------------------------------------------------
# AgentRunner import check (no litellm needed)
# ---------------------------------------------------------------------------

class TestAgentRunnerImport:
    """AgentRunner can be imported and raises clear error when litellm missing."""

    def test_agent_runner_importable(self):
        """AgentRunner module can be imported without litellm."""
        from adversary_pursuit.agent import runner
        assert hasattr(runner, "AgentRunner")

    def test_agent_runner_instantiable_with_ctx(self, tmp_ctx):
        """AgentRunner can be instantiated with a ToolContext."""
        from adversary_pursuit.agent.runner import AgentRunner
        r = AgentRunner(tool_context=tmp_ctx)
        assert r.ctx is tmp_ctx
        assert len(r.tools) == 9

    def test_agent_runner_has_conversation_history(self, tmp_ctx):
        """AgentRunner initializes with system prompt in conversation."""
        from adversary_pursuit.agent.runner import AgentRunner
        r = AgentRunner(tool_context=tmp_ctx)
        assert len(r.conversation) == 1
        assert r.conversation[0]["role"] == "system"

    def test_agent_runner_reset_clears_history(self, tmp_ctx):
        """AgentRunner.reset() clears conversation to just system prompt."""
        from adversary_pursuit.agent.runner import AgentRunner
        r = AgentRunner(tool_context=tmp_ctx)
        r.conversation.append({"role": "user", "content": "hello"})
        r.reset()
        assert len(r.conversation) == 1
        assert r.conversation[0]["role"] == "system"

    def test_chat_raises_without_litellm(self, tmp_ctx):
        """AgentRunner.chat() raises ImportError when litellm is not available."""
        from adversary_pursuit.agent.runner import AgentRunner, HAS_LITELLM
        if HAS_LITELLM:
            pytest.skip("litellm is installed — ImportError path not tested")
        r = AgentRunner(tool_context=tmp_ctx)
        with pytest.raises(ImportError, match="litellm"):
            r.chat("test message")
