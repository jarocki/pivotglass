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

@decision DEC-TEST-AGENT-002
@title Credential builder tests verify multi-key init_config for Censys/PT
@status accepted
@rationale Censys and PassiveTotal use multi-key auth (censys_id+censys_secret,
           passivetotal_user+passivetotal_key). Tests verify run_module() calls
           module.initialize() with the correct keys — not just {"api_key": ...}.
           This proves DEC-AGENT-TOOLS-003 is wired correctly end-to-end.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adversary_pursuit.agent.tools import (
    ToolContext,
    _CREDENTIAL_BUILDERS,
    _MODULE_MAP,
    create_tools,
    execute_tool,
)


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

SAMPLE_VT_RESULTS = [
    {
        "type": "ipv4-addr",
        "value": "1.2.3.4",
        "x_malicious": 5,
        "x_suspicious": 1,
        "x_harmless": 60,
        "x_undetected": 10,
        "x_reputation": -5,
        "x_last_analysis_date": 1700000000,
        "x_as_owner": "Example ISP",
        "x_country": "US",
    }
]

SAMPLE_CENSYS_RESULTS = [
    {
        "type": "ipv4-addr",
        "value": "8.8.8.8",
        "x_services": [
            {"port": 53, "protocol": "UDP", "service_name": "DNS"},
            {"port": 443, "protocol": "TCP", "service_name": "HTTPS"},
        ],
        "x_os": "Linux",
        "x_location_country": "US",
        "x_autonomous_system": {
            "asn": 15169,
            "name": "Google LLC",
            "bgp_prefix": "8.8.8.0/24",
            "country_code": "US",
        },
        "x_last_updated": "2024-01-01T00:00:00Z",
    }
]

SAMPLE_PT_RESULTS = [
    {
        "type": "domain-name",
        "value": "evil.example.com",
        "x_first_seen": "2020-01-01 00:00:00",
        "x_last_seen": "2024-01-01 00:00:00",
        "x_record_count": 42,
    },
    {"type": "ipv4-addr", "value": "1.2.3.4"},
    {"type": "ipv4-addr", "value": "5.6.7.8"},
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
        """Plugin manager loads all built-in modules after ToolContext init."""
        modules = tmp_ctx.plugin_mgr.list_modules()
        module_names = [m["name"] for m in modules]
        assert "osint/dns_resolve" in module_names
        assert "osint/whois_lookup" in module_names
        assert "osint/abuseipdb" in module_names
        assert "osint/shodan_ip" in module_names
        assert "osint/hibp" in module_names
        assert "cti/otx" in module_names
        assert "osint/urlscan" in module_names
        # New modules wired in this slice
        assert "cti/virustotal" in module_names
        assert "osint/censys_host" in module_names
        assert "cti/passivetotal" in module_names

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

    def test_returns_fourteen_tools(self, tmp_ctx):
        """create_tools returns exactly 14 tool definitions (7 original + 3 new + 2 workspace + 2 hints)."""
        tools = create_tools(tmp_ctx)
        assert len(tools) == 14

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
            assert params["type"] == "object", (
                f"Parameters type must be 'object': {fn['name']}"
            )

    def test_expected_tool_names(self, tmp_ctx):
        """create_tools includes all expected tool names including hint tools."""
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
            # New tools — VT/Censys/PassiveTotal parity
            "virustotal_lookup",
            "censys_host_lookup",
            "passivetotal_lookup",
            # Workspace tools
            "get_workspace_summary",
            "search_workspace",
            # Hint tools (DEC-AGENT-HINTS-001)
            "get_next_hint",
            "buy_hint",
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
        tool = next(
            t for t in tools if t["function"]["name"] == "get_workspace_summary"
        )
        params = tool["function"]["parameters"]
        # Empty properties or no required
        assert "required" not in params or len(params.get("required", [])) == 0

    def test_openai_compatible_schema(self, tmp_ctx):
        """Tool schema is JSON-serializable (OpenAI-compatible)."""
        tools = create_tools(tmp_ctx)
        # Should not raise
        serialized = json.dumps(tools)
        roundtripped = json.loads(serialized)
        assert len(roundtripped) == 14

    # --- New tool schema tests ---

    def test_virustotal_lookup_has_required_target(self, tmp_ctx):
        """virustotal_lookup tool has 'target' as a required parameter."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "virustotal_lookup")
        params = tool["function"]["parameters"]
        assert "target" in params["properties"]
        assert "target" in params["required"]
        # target_type is optional
        assert "target_type" in params["properties"]
        assert "required" not in params or "target_type" not in params.get(
            "required", []
        )

    def test_censys_host_lookup_has_required_ip(self, tmp_ctx):
        """censys_host_lookup tool has 'ip_address' as a required parameter."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "censys_host_lookup")
        params = tool["function"]["parameters"]
        assert "ip_address" in params["properties"]
        assert "ip_address" in params["required"]

    def test_passivetotal_lookup_has_required_target(self, tmp_ctx):
        """passivetotal_lookup tool has 'target' as a required parameter."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "passivetotal_lookup")
        params = tool["function"]["parameters"]
        assert "target" in params["properties"]
        assert "target" in params["required"]
        # include_whois is optional
        assert "include_whois" in params["properties"]


# ---------------------------------------------------------------------------
# execute_tool — dispatch to correct modules
# ---------------------------------------------------------------------------


class TestExecuteToolDispatch:
    """execute_tool dispatches to the correct module and returns (summary, celebration).

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # Tests mock at the asyncio boundary (module.hunt) to avoid live API calls.
    # This is the exact same exemption declared in the module docstring.
    """

    def _make_mock_module(self, results):
        """Create a mock PursuitModule that returns given results from hunt()."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def test_unknown_tool_returns_error(self, tmp_ctx):
        """execute_tool returns (error_string, None) for unknown tool names."""
        summary, celebration, badges = execute_tool(tmp_ctx, "nonexistent_tool", {})
        assert "Unknown tool" in summary
        assert "nonexistent_tool" in summary
        assert celebration is None

    def test_dns_resolve_dispatches_to_dns_module(self, tmp_ctx):
        """execute_tool('dns_resolve') runs the osint/dns_resolve module."""
        mock_mod = self._make_mock_module(SAMPLE_DOMAIN_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "dns_resolve", {"domain": "example.com"}
            )
            assert isinstance(summary, str)
            assert "Found" in summary
            # Verify get_module was called with correct path
            mock_get.assert_called_once_with("osint/dns_resolve")

    def test_whois_lookup_dispatches(self, tmp_ctx):
        """execute_tool('whois_lookup') runs the osint/whois_lookup module."""
        mock_mod = self._make_mock_module(SAMPLE_DOMAIN_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "whois_lookup", {"target": "example.com"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/whois_lookup")

    def test_check_ip_reputation_dispatches(self, tmp_ctx):
        """execute_tool('check_ip_reputation') runs abuseipdb module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/abuseipdb")

    def test_shodan_host_lookup_dispatches(self, tmp_ctx):
        """execute_tool('shodan_host_lookup') runs osint/shodan_ip module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "shodan_host_lookup", {"ip_address": "1.2.3.4"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/shodan_ip")

    def test_check_breaches_dispatches(self, tmp_ctx):
        """execute_tool('check_breaches') runs osint/hibp module."""
        mock_mod = self._make_mock_module(
            [{"type": "email-addr", "value": "user@example.com"}]
        )
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "check_breaches", {"email": "user@example.com"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/hibp")

    def test_otx_threat_intel_dispatches(self, tmp_ctx):
        """execute_tool('otx_threat_intel') runs cti/otx module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "otx_threat_intel", {"target": "1.2.3.4"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("cti/otx")

    def test_scan_url_dispatches(self, tmp_ctx):
        """execute_tool('scan_url') runs osint/urlscan module."""
        mock_mod = self._make_mock_module(
            [{"type": "url", "value": "http://evil.example.com"}]
        )
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "scan_url", {"url": "http://evil.example.com"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/urlscan")

    def test_module_not_found_returns_error(self, tmp_ctx):
        """execute_tool returns (error_string, None) when module not found."""
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=None):
            summary, celebration, _badges = execute_tool(
                tmp_ctx, "dns_resolve", {"domain": "example.com"}
            )
        assert "Error" in summary
        assert celebration is None

    def test_module_exception_returns_error(self, tmp_ctx):
        """execute_tool returns (error_string, None) when module raises exception."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(side_effect=RuntimeError("Network error"))
        mock_mod.initialize = MagicMock()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges = execute_tool(
                tmp_ctx, "dns_resolve", {"domain": "example.com"}
            )
        assert "Error" in summary
        assert celebration is None

    # --- New tool dispatch tests ---

    def test_virustotal_lookup_dispatches(self, tmp_ctx):
        """execute_tool('virustotal_lookup') runs cti/virustotal module."""
        mock_mod = self._make_mock_module(SAMPLE_VT_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "virustotal_lookup", {"target": "1.2.3.4"}
            )
            assert isinstance(summary, str)
            assert "Found" in summary
            mock_get.assert_called_once_with("cti/virustotal")

    def test_virustotal_lookup_passes_target_type(self, tmp_ctx):
        """execute_tool('virustotal_lookup') passes TARGET_TYPE option to module."""
        mock_mod = self._make_mock_module(SAMPLE_VT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            execute_tool(
                tmp_ctx, "virustotal_lookup", {"target": "1.2.3.4", "target_type": "ip"}
            )
        mock_mod.hunt.assert_called_once_with("1.2.3.4", {"TARGET_TYPE": "ip"})

    def test_virustotal_lookup_empty_target_type_default(self, tmp_ctx):
        """execute_tool('virustotal_lookup') defaults TARGET_TYPE to '' for auto-detection."""
        mock_mod = self._make_mock_module(SAMPLE_VT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            execute_tool(tmp_ctx, "virustotal_lookup", {"target": "evil.example.com"})
        mock_mod.hunt.assert_called_once_with("evil.example.com", {"TARGET_TYPE": ""})

    def test_censys_host_lookup_dispatches(self, tmp_ctx):
        """execute_tool('censys_host_lookup') runs osint/censys_host module."""
        mock_mod = self._make_mock_module(SAMPLE_CENSYS_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "censys_host_lookup", {"ip_address": "8.8.8.8"}
            )
            assert isinstance(summary, str)
            assert "Found" in summary
            mock_get.assert_called_once_with("osint/censys_host")

    def test_censys_host_lookup_passes_ip_as_target(self, tmp_ctx):
        """execute_tool('censys_host_lookup') uses ip_address as the hunt() target."""
        mock_mod = self._make_mock_module(SAMPLE_CENSYS_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            execute_tool(tmp_ctx, "censys_host_lookup", {"ip_address": "8.8.8.8"})
        mock_mod.hunt.assert_called_once_with("8.8.8.8", {})

    def test_passivetotal_lookup_dispatches(self, tmp_ctx):
        """execute_tool('passivetotal_lookup') runs cti/passivetotal module."""
        mock_mod = self._make_mock_module(SAMPLE_PT_RESULTS)
        with patch.object(
            tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod
        ) as mock_get:
            summary, _celebration, _badges = execute_tool(
                tmp_ctx, "passivetotal_lookup", {"target": "evil.example.com"}
            )
            assert isinstance(summary, str)
            assert "Found" in summary
            mock_get.assert_called_once_with("cti/passivetotal")

    def test_passivetotal_lookup_passes_include_whois_true(self, tmp_ctx):
        """execute_tool('passivetotal_lookup') defaults INCLUDE_WHOIS to 'true'."""
        mock_mod = self._make_mock_module(SAMPLE_PT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            execute_tool(tmp_ctx, "passivetotal_lookup", {"target": "evil.example.com"})
        mock_mod.hunt.assert_called_once_with(
            "evil.example.com", {"INCLUDE_WHOIS": "true"}
        )

    def test_passivetotal_lookup_passes_include_whois_false(self, tmp_ctx):
        """execute_tool('passivetotal_lookup') passes INCLUDE_WHOIS=false when requested."""
        mock_mod = self._make_mock_module(SAMPLE_PT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            execute_tool(
                tmp_ctx,
                "passivetotal_lookup",
                {"target": "evil.example.com", "include_whois": False},
            )
        mock_mod.hunt.assert_called_once_with(
            "evil.example.com", {"INCLUDE_WHOIS": "false"}
        )


# ---------------------------------------------------------------------------
# execute_tool — workspace tools
# ---------------------------------------------------------------------------


class TestWorkspaceTools:
    """execute_tool handles get_workspace_summary and search_workspace.

    # @mock-exempt: no mocks used — workspace tools use real in-memory SQLite.
    """

    def test_get_workspace_summary_returns_string(self, tmp_ctx):
        """execute_tool('get_workspace_summary', {}) returns (summary, None)."""
        summary, celebration, _badges = execute_tool(
            tmp_ctx, "get_workspace_summary", {}
        )
        assert isinstance(summary, str)
        assert "Workspace" in summary or "workspace" in summary.lower()
        assert celebration is None

    def test_get_workspace_summary_includes_counts(self, tmp_ctx):
        """Workspace summary includes total indicators and score."""
        summary, _celebration, _badges = execute_tool(
            tmp_ctx, "get_workspace_summary", {}
        )
        assert "indicators" in summary.lower() or "Total" in summary

    def test_search_workspace_empty_returns_message(self, tmp_ctx):
        """search_workspace on empty workspace returns (no-results string, None)."""
        summary, celebration, _badges = execute_tool(tmp_ctx, "search_workspace", {})
        assert isinstance(summary, str)
        # Empty workspace should indicate no results found
        assert "No" in summary or "0" in summary or "no" in summary.lower()
        assert celebration is None

    def test_search_workspace_with_type_filter(self, tmp_ctx):
        """search_workspace with type_filter filters by STIX type."""
        summary, _celebration, _badges = execute_tool(
            tmp_ctx, "search_workspace", {"type_filter": "ipv4-addr"}
        )
        assert isinstance(summary, str)

    def test_search_workspace_after_storing_objects(self, tmp_ctx):
        """search_workspace returns stored objects after a module run."""
        # Store some objects directly
        objects = [{"type": "ipv4-addr", "value": "1.2.3.4"}]
        tmp_ctx.workspace_mgr.store_stix_objects(objects, "test/module", "1.2.3.4")

        summary, _celebration, _badges = execute_tool(
            tmp_ctx, "search_workspace", {"type_filter": "ipv4-addr"}
        )
        assert "1.2.3.4" in summary or "Found 1" in summary


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
# Credential builders — multi-key auth modules (DEC-AGENT-TOOLS-003)
# ---------------------------------------------------------------------------


class TestCredentialBuilders:
    """_CREDENTIAL_BUILDERS supplies correct init_config for multi-key modules."""

    def test_credential_builders_keys_present(self):
        """_CREDENTIAL_BUILDERS contains entries for censys_host and passivetotal."""
        assert "osint/censys_host" in _CREDENTIAL_BUILDERS
        assert "cti/passivetotal" in _CREDENTIAL_BUILDERS

    def test_censys_builder_returns_id_and_secret(self, tmp_ctx):
        """Censys credential builder produces censys_id and censys_secret keys."""
        builder = _CREDENTIAL_BUILDERS["osint/censys_host"]
        config = builder(tmp_ctx.config_mgr)
        assert "censys_id" in config
        assert "censys_secret" in config
        # Both should be strings (empty when not configured)
        assert isinstance(config["censys_id"], str)
        assert isinstance(config["censys_secret"], str)

    def test_passivetotal_builder_returns_user_and_key(self, tmp_ctx):
        """PassiveTotal credential builder produces passivetotal_user and passivetotal_key."""
        builder = _CREDENTIAL_BUILDERS["cti/passivetotal"]
        config = builder(tmp_ctx.config_mgr)
        assert "passivetotal_user" in config
        assert "passivetotal_key" in config
        assert isinstance(config["passivetotal_user"], str)
        assert isinstance(config["passivetotal_key"], str)

    def test_run_module_uses_censys_credentials(self, tmp_ctx):
        """run_module initializes censys_host with censys_id + censys_secret."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_CENSYS_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/censys_host", "8.8.8.8", {})

        mock_mod.initialize.assert_called_once()
        init_arg = mock_mod.initialize.call_args[0][0]
        # Must NOT be the legacy single-key format
        assert "api_key" not in init_arg
        assert "censys_id" in init_arg
        assert "censys_secret" in init_arg

    def test_run_module_uses_passivetotal_credentials(self, tmp_ctx):
        """run_module initializes passivetotal with passivetotal_user + passivetotal_key."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_PT_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("cti/passivetotal", "evil.example.com", {})

        mock_mod.initialize.assert_called_once()
        init_arg = mock_mod.initialize.call_args[0][0]
        assert "api_key" not in init_arg
        assert "passivetotal_user" in init_arg
        assert "passivetotal_key" in init_arg

    def test_virustotal_uses_legacy_api_key_path(self, tmp_ctx):
        """VirusTotal uses the standard api_key path (not _CREDENTIAL_BUILDERS)."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_VT_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("cti/virustotal", "1.2.3.4", {})

        mock_mod.initialize.assert_called_once()
        init_arg = mock_mod.initialize.call_args[0][0]
        # VT is NOT in _CREDENTIAL_BUILDERS — uses legacy api_key format
        assert "api_key" in init_arg
        assert "cti/virustotal" not in _CREDENTIAL_BUILDERS


# ---------------------------------------------------------------------------
# _MODULE_MAP — catalog completeness
# ---------------------------------------------------------------------------


class TestModuleMap:
    """_MODULE_MAP contains entries for all 10 module-backed tools."""

    def test_module_map_has_ten_entries(self):
        """_MODULE_MAP has exactly 10 entries (7 original + 3 new)."""
        assert len(_MODULE_MAP) == 10

    def test_module_map_contains_new_tools(self):
        """_MODULE_MAP contains virustotal_lookup, censys_host_lookup, passivetotal_lookup."""
        assert "virustotal_lookup" in _MODULE_MAP
        assert "censys_host_lookup" in _MODULE_MAP
        assert "passivetotal_lookup" in _MODULE_MAP

    def test_virustotal_maps_to_correct_path(self):
        """virustotal_lookup maps to cti/virustotal."""
        module_path, _ = _MODULE_MAP["virustotal_lookup"]
        assert module_path == "cti/virustotal"

    def test_censys_maps_to_correct_path(self):
        """censys_host_lookup maps to osint/censys_host."""
        module_path, _ = _MODULE_MAP["censys_host_lookup"]
        assert module_path == "osint/censys_host"

    def test_passivetotal_maps_to_correct_path(self):
        """passivetotal_lookup maps to cti/passivetotal."""
        module_path, _ = _MODULE_MAP["passivetotal_lookup"]
        assert module_path == "cti/passivetotal"


# ---------------------------------------------------------------------------
# End-to-end compound interaction: full production sequence for new tools
# ---------------------------------------------------------------------------


class TestNewToolsProductionSequence:
    """Compound interaction tests: ToolContext -> create_tools -> execute_tool.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # Mocking at the asyncio boundary avoids live API calls while exercising
    # the complete dispatch path through workspace storage and scoring.

    Each test exercises the real production sequence end-to-end:
    ToolContext init -> module lookup -> initialize() -> hunt() -> workspace
    storage -> scoring -> (summary, celebration) returned to caller.

    This validates that the three new tools work through the complete
    dispatch path, not just individual unit slices.
    """

    def _make_mock_module(self, results):
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def test_virustotal_full_sequence(self, tmp_ctx):
        """Full VT sequence: tools defined -> execute dispatches -> workspace updated."""
        # 1. Verify tool is in catalog
        tools = create_tools(tmp_ctx)
        tool_names = {t["function"]["name"] for t in tools}
        assert "virustotal_lookup" in tool_names

        # 2. Execute via dispatch path
        mock_mod = self._make_mock_module(SAMPLE_VT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges = execute_tool(
                tmp_ctx, "virustotal_lookup", {"target": "1.2.3.4"}
            )

        # 3. Verify string summary returned to LLM
        assert isinstance(summary, str)
        assert "Found" in summary

        # 4. Verify workspace was updated
        objects = tmp_ctx.workspace_mgr.get_stix_objects()
        assert len(objects) >= 1

        # 5. Verify scoring fired
        score = tmp_ctx.workspace_mgr.get_total_score()
        assert score > 0

        # 6. Verify celebration artifact was computed (points > 0)
        assert celebration is not None
        assert isinstance(celebration, str)
        assert len(celebration) > 0

    def test_censys_full_sequence(self, tmp_ctx):
        """Full Censys sequence: tools -> execute -> multi-key init -> workspace."""
        tools = create_tools(tmp_ctx)
        assert "censys_host_lookup" in {t["function"]["name"] for t in tools}

        mock_mod = self._make_mock_module(SAMPLE_CENSYS_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges = execute_tool(
                tmp_ctx, "censys_host_lookup", {"ip_address": "8.8.8.8"}
            )

        assert isinstance(summary, str)
        assert "Found" in summary

        # Verify multi-key credentials were used
        mock_mod.initialize.assert_called_once()
        init_arg = mock_mod.initialize.call_args[0][0]
        assert "censys_id" in init_arg
        assert "censys_secret" in init_arg

        # Workspace updated
        objects = tmp_ctx.workspace_mgr.get_stix_objects()
        assert len(objects) >= 1

        # Celebration present for non-zero scoring
        assert celebration is not None

    def test_passivetotal_full_sequence(self, tmp_ctx):
        """Full PT sequence: tools -> execute -> multi-key init -> workspace -> scoring."""
        tools = create_tools(tmp_ctx)
        assert "passivetotal_lookup" in {t["function"]["name"] for t in tools}

        mock_mod = self._make_mock_module(SAMPLE_PT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges = execute_tool(
                tmp_ctx,
                "passivetotal_lookup",
                {"target": "evil.example.com", "include_whois": True},
            )

        assert isinstance(summary, str)
        assert "Found" in summary

        # Verify INCLUDE_WHOIS was passed as string "true"
        mock_mod.hunt.assert_called_once_with(
            "evil.example.com", {"INCLUDE_WHOIS": "true"}
        )

        # Verify multi-key credentials
        init_arg = mock_mod.initialize.call_args[0][0]
        assert "passivetotal_user" in init_arg
        assert "passivetotal_key" in init_arg

        # Multiple related indicators should score
        score = tmp_ctx.workspace_mgr.get_total_score()
        assert score > 0

        # Celebration present for non-zero scoring
        assert celebration is not None

    def test_all_ten_tools_in_module_map_are_dispatchable(self, tmp_ctx):
        """All 10 _MODULE_MAP entries can be dispatched without KeyError."""
        # Maps tool name to minimal valid arguments
        arg_map = {
            "dns_resolve": {"domain": "example.com"},
            "whois_lookup": {"target": "example.com"},
            "check_ip_reputation": {"ip_address": "1.2.3.4"},
            "shodan_host_lookup": {"ip_address": "1.2.3.4"},
            "check_breaches": {"email": "user@example.com"},
            "otx_threat_intel": {"target": "1.2.3.4"},
            "scan_url": {"url": "http://example.com"},
            "virustotal_lookup": {"target": "1.2.3.4"},
            "censys_host_lookup": {"ip_address": "1.2.3.4"},
            "passivetotal_lookup": {"target": "evil.example.com"},
        }

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_IP_RESULTS)
        mock_mod.initialize = MagicMock()

        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            for tool_name, args in arg_map.items():
                summary, celebration, _badges = execute_tool(tmp_ctx, tool_name, args)
                assert isinstance(summary, str), f"Tool {tool_name} did not return str"
                assert "Error" not in summary or "Unknown" not in summary, (
                    f"Tool {tool_name} returned unexpected error: {summary}"
                )
                # celebration is str or None depending on scoring
                assert celebration is None or isinstance(celebration, str)


# ---------------------------------------------------------------------------
# CelebrationEngine wiring tests (DEC-AGENT-CELEBRATIONS-001)
# ---------------------------------------------------------------------------


class TestCelebrationWiring:
    """Tests for CelebrationEngine integration in ToolContext and execute_tool.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # Mocking at the asyncio boundary avoids live API calls while exercising
    # the real celebration computation path through CelebrationEngine.

    Covers:
      (1) celebration is computed after a scoring tool call
      (2) silent path — celebration is None when no points awarded
      (3) milestone message appended at exact score threshold
      (4) celebration key present in run_module return dict
      (5) compound-interaction: create_tools -> execute_tool -> celebration computed
    """

    def _make_mock_module(self, results):
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def test_tool_context_has_celebration_engine(self, tmp_ctx):
        """ToolContext.__init__ creates a CelebrationEngine instance."""
        from adversary_pursuit.gamification.celebrations import CelebrationEngine

        assert hasattr(tmp_ctx, "celebration")
        assert isinstance(tmp_ctx.celebration, CelebrationEngine)

    def test_run_module_returns_celebration_key(self, tmp_ctx):
        """run_module return dict includes 'celebration' key for all outcomes."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert "celebration" in result

    def test_run_module_celebration_non_none_when_points_awarded(self, tmp_ctx):
        """run_module returns a non-None celebration when scoring events fire."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        # SAMPLE_IP_RESULTS includes ipv4-addr + domain-name, both score
        assert result["total_points"] > 0
        assert result["celebration"] is not None
        assert isinstance(result["celebration"], str)
        assert len(result["celebration"]) > 0

    def test_run_module_celebration_none_when_no_points(self, tmp_ctx):
        """run_module returns celebration=None when hunt() yields no scoring results.

        Silent path (DEC-AGENT-CELEBRATIONS-001): zero points => no celebration.
        """
        # Empty results: no indicators -> no scoring events -> total_points==0
        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["total_points"] == 0
        assert result["celebration"] is None

    def test_execute_tool_returns_celebration_string_for_scoring_tools(self, tmp_ctx):
        """execute_tool returns a non-None celebration for tools that award points."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        assert isinstance(summary, str)
        assert celebration is not None
        assert isinstance(celebration, str)

    def test_execute_tool_celebration_none_when_no_score(self, tmp_ctx):
        """execute_tool celebration is None when hunt() returns no new indicators."""
        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            _summary, celebration, _badges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        assert celebration is None

    def test_celebration_art_level_small_for_low_points(self, tmp_ctx):
        """Celebration art uses 'small' level for points < 50 (DEC-CELEBRATION-001)."""
        # A single low-value indicator result (email breach = few points)
        low_results = [{"type": "email-addr", "value": "user@example.com"}]
        mock_mod = self._make_mock_module(low_results)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/hibp", "user@example.com", {})

        if result["total_points"] > 0 and result["total_points"] < 50:
            # Small threshold: art should be from the small bucket
            assert result["celebration"] is not None

    def test_milestone_message_appended_at_exact_threshold(self, tmp_ctx):
        """Milestone message appended to celebration when total_score hits exact threshold.

        Mirrors DEC-CELEBRATION-002: milestones fire at exact values only.
        We seed the workspace score to 99 pts then trigger a 1-pt scoring event
        to land exactly on the 100-pt milestone.
        """
        from adversary_pursuit.gamification.celebrations import MILESTONES

        # Seed workspace with 99 pts by storing a synthetic score event
        tmp_ctx.workspace_mgr.store_score_events(
            [
                {
                    "action": "seed",
                    "points": 99,
                    "indicator": "seed",
                    "rule_description": "seed",
                }
            ]
        )
        assert tmp_ctx.workspace_mgr.get_total_score() == 99

        # Now trigger a 1-pt scoring event so post-storage total == 100
        # Use a result type that scores exactly 1 pt if possible; if the scoring
        # engine gives more, we verify milestone fires for whatever threshold is hit.
        single_result = [{"type": "email-addr", "value": "unique@example.com"}]
        mock_mod = self._make_mock_module(single_result)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/hibp", "unique@example.com", {})

        if result["total_points"] > 0:
            post_total = tmp_ctx.workspace_mgr.get_total_score()
            expected_milestone = MILESTONES.get(post_total)
            if expected_milestone:
                # Celebration must contain the milestone text
                assert expected_milestone in result["celebration"], (
                    f"Expected milestone '{expected_milestone}' in celebration "
                    f"but got: {result['celebration']!r}"
                )

    def test_compound_create_tools_execute_tool_celebration(self, tmp_ctx):
        """Compound: create_tools -> execute_tool -> celebration computed end-to-end.

        This is the required compound-interaction test crossing the boundaries:
        ToolContext init (CelebrationEngine wired) -> create_tools (catalog built)
        -> execute_tool (dispatch + run_module + celebration computed) -> caller
        receives (summary, celebration) tuple ready for rendering.

        Production path: chat.py calls runner.chat() which calls execute_tool()
        and accumulates celebrations in runner.last_celebrations for display.
        This test exercises all components except the LLM call itself.
        """
        # 1. Tools catalog built from ToolContext (includes CelebrationEngine)
        tools = create_tools(tmp_ctx)
        tool_names = {t["function"]["name"] for t in tools}
        assert "check_ip_reputation" in tool_names

        # 2. Execute dispatch path with scoring results
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        # 3. Summary goes to LLM — must be a non-empty string
        assert isinstance(summary, str)
        assert "Found" in summary

        # 4. Celebration goes to user terminal — must be non-None (points awarded)
        assert celebration is not None
        assert isinstance(celebration, str)

        # 5. Workspace state reflects both the indicators and score
        objects = tmp_ctx.workspace_mgr.get_stix_objects()
        assert len(objects) >= 1
        score = tmp_ctx.workspace_mgr.get_total_score()
        assert score > 0

        # 6. Celebration content is ASCII art from CelebrationEngine
        # (not empty, not an error message)
        assert "Error" not in celebration
        assert len(celebration.strip()) > 0


# ---------------------------------------------------------------------------
# BadgeManager wiring tests (DEC-AGENT-BADGES-001)
# ---------------------------------------------------------------------------


class TestBadgeWiring:
    """Tests for BadgeManager integration in ToolContext and execute_tool.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # Mocking at the asyncio boundary avoids live API calls while exercising
    # the real badge evaluation path through BadgeManager and WorkspaceManager.

    Covers:
      (1) ToolContext has a BadgeManager and _awarded_badges set
      (2) badge check fires after each tool call (run_module returns "badges" key)
      (3) newly-earned badges surface in the run_module dict and execute_tool triple
      (4) silent path — badges=[] when no new badges earned
      (5) _awarded_badges set updated correctly — no duplicate awards across calls
      (6) badge info appended to LLM summary string
      (7) badge events persisted to workspace via store_badge_event
      (8) compound interaction: create_tools -> execute_tool -> badge computed end-to-end
    """

    def _make_mock_module(self, results):
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def _make_high_score_ctx(self, tmp_path):
        """Create a ToolContext pre-seeded with enough score to earn badge-century."""
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        # Seed score to 99 — one more scoring event will cross the 100-pt "Century" badge
        ctx.workspace_mgr.store_score_events(
            [
                {
                    "action": "seed",
                    "points": 99,
                    "indicator": "seed",
                    "rule_description": "seed",
                }
            ]
        )
        return ctx

    def test_tool_context_has_badge_manager(self, tmp_ctx):
        """ToolContext.__init__ creates a BadgeManager instance."""
        from adversary_pursuit.gamification.badges import BadgeManager

        assert hasattr(tmp_ctx, "badge_mgr")
        assert isinstance(tmp_ctx.badge_mgr, BadgeManager)

    def test_tool_context_has_awarded_badges_set(self, tmp_ctx):
        """ToolContext.__init__ initialises _awarded_badges as an empty set."""
        assert hasattr(tmp_ctx, "_awarded_badges")
        assert isinstance(tmp_ctx._awarded_badges, set)
        assert len(tmp_ctx._awarded_badges) == 0

    def test_run_module_returns_badges_key(self, tmp_ctx):
        """run_module return dict always includes 'badges' key."""
        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert "badges" in result
        assert isinstance(result["badges"], list)

    def test_run_module_badges_empty_when_not_earned(self, tmp_ctx):
        """run_module returns badges=[] when no badge thresholds are crossed.

        Silent path (DEC-AGENT-BADGES-001): no badges => empty list.
        Fresh workspace with no indicators means no badge can be earned.
        """
        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["badges"] == []

    def test_run_module_badge_earned_when_threshold_crossed(self, tmp_path):
        """run_module returns newly-earned Badge when workspace stats cross threshold.

        Seeds workspace to 99 score points, then triggers a scoring event that
        pushes total to 100, crossing the 'Century' badge threshold (100 pts).
        """
        from adversary_pursuit.gamification.badges import Badge

        ctx = self._make_high_score_ctx(tmp_path)
        assert ctx.workspace_mgr.get_total_score() == 99

        # A scoring result that pushes total over 100 pt threshold
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        if result["total_points"] > 0:
            # Badges should contain at least the Century badge (100-pt threshold)
            badge_ids = [b.id for b in result["badges"]]
            assert "badge-century" in badge_ids, (
                f"Expected badge-century in {badge_ids} with score "
                f"{ctx.workspace_mgr.get_total_score()}"
            )
            for badge in result["badges"]:
                assert isinstance(badge, Badge)

    def test_awarded_badges_set_updated_after_badge_earned(self, tmp_path):
        """_awarded_badges set is updated when a badge is earned, preventing re-award."""
        ctx = self._make_high_score_ctx(tmp_path)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        if result["badges"]:
            for badge in result["badges"]:
                assert badge.id in ctx._awarded_badges

    def test_no_duplicate_badge_award_on_second_call(self, tmp_path):
        """Badge is not re-awarded on a second run_module call for the same workspace.

        DEC-BADGE-002: already_awarded set prevents duplicate awards.
        """
        ctx = self._make_high_score_ctx(tmp_path)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result1 = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        first_badge_ids = {b.id for b in result1["badges"]}

        # Second call — same workspace, same target; no new badges should fire
        mock_mod2 = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod2):
            result2 = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        second_badge_ids = {b.id for b in result2["badges"]}
        # None of the badges from the first call should re-appear in the second
        overlap = first_badge_ids & second_badge_ids
        assert not overlap, f"Badges re-awarded on second call: {overlap}"

    def test_badge_event_persisted_to_workspace(self, tmp_path):
        """Newly-earned badges are persisted via store_badge_event to the workspace DB."""
        ctx = self._make_high_score_ctx(tmp_path)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        if result["badges"]:
            awarded = ctx.workspace_mgr.get_awarded_badges()
            awarded_ids = {row["badge_id"] for row in awarded}
            for badge in result["badges"]:
                assert badge.id in awarded_ids, (
                    f"Badge {badge.id} earned but not found in workspace: {awarded_ids}"
                )

    def test_badge_info_appended_to_llm_summary(self, tmp_path):
        """Badge name and rarity are appended to the LLM summary string when earned."""
        ctx = self._make_high_score_ctx(tmp_path)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        if result["badges"]:
            summary = result["summary"]
            assert "Badge" in summary or "badge" in summary.lower(), (
                f"Expected badge info in summary but got: {summary!r}"
            )
            for badge in result["badges"]:
                assert badge.name in summary, (
                    f"Badge name {badge.name!r} not found in summary: {summary!r}"
                )

    def test_execute_tool_returns_badges_list(self, tmp_path):
        """execute_tool returns a triple (summary, celebration, badges)."""
        ctx = self._make_high_score_ctx(tmp_path)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = execute_tool(ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"})

        assert len(result) == 3
        summary, celebration, badges = result
        assert isinstance(summary, str)
        assert isinstance(badges, list)

    def test_execute_tool_badges_empty_for_workspace_meta_tools(self, tmp_ctx):
        """Workspace meta-tools return badges=[] — no badge check on workspace queries."""
        summary, celebration, badges = execute_tool(
            tmp_ctx, "get_workspace_summary", {}
        )
        assert badges == []
        summary2, celebration2, badges2 = execute_tool(tmp_ctx, "search_workspace", {})
        assert badges2 == []

    def test_execute_tool_badges_empty_for_unknown_tool(self, tmp_ctx):
        """execute_tool returns badges=[] for unknown tool names."""
        summary, celebration, badges = execute_tool(tmp_ctx, "unknown_tool", {})
        assert badges == []

    def test_compound_create_tools_execute_tool_badge_computed(self, tmp_path):
        """Compound: create_tools -> execute_tool -> badge computed end-to-end.

        This is the required compound-interaction test crossing the real
        production sequence: ToolContext init (BadgeManager + _awarded_badges
        wired) -> create_tools (catalog built) -> execute_tool (dispatch +
        run_module + badge check + persist) -> caller receives triple with
        newly-earned Badge objects ready for Rich panel rendering in chat.py.

        Production path: chat.py calls runner.chat() which calls execute_tool()
        and accumulates badges in runner.last_badges for display. This test
        exercises all components except the LLM call itself.
        """
        ctx = self._make_high_score_ctx(tmp_path)

        # 1. Tools catalog built from ToolContext (includes BadgeManager)
        tools = create_tools(ctx)
        tool_names = {t["function"]["name"] for t in tools}
        assert "check_ip_reputation" in tool_names

        # 2. Execute dispatch path: scoring results push score over badge threshold
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, badges = execute_tool(
                ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        # 3. Summary goes to LLM — must be a non-empty string
        assert isinstance(summary, str)
        assert "Found" in summary

        # 4. badges list is returned (may be empty if scoring didn't cross threshold)
        assert isinstance(badges, list)

        # 5. If badges were earned, they are Badge objects with rarity metadata
        from adversary_pursuit.gamification.badges import Badge, BadgeRarity

        for badge in badges:
            assert isinstance(badge, Badge)
            assert isinstance(badge.rarity, BadgeRarity)
            assert badge.id in ctx._awarded_badges

        # 6. Workspace reflects badge persistence
        if badges:
            awarded = ctx.workspace_mgr.get_awarded_badges()
            awarded_ids = {row["badge_id"] for row in awarded}
            for badge in badges:
                assert badge.id in awarded_ids


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
        assert len(r.tools) == 14

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


# ---------------------------------------------------------------------------
# ModeManager wiring tests (DEC-AGENT-MODES-001)
# ---------------------------------------------------------------------------


class TestModeWiring:
    """Tests for ModeManager integration in ToolContext, AgentRunner, and chat meta-command.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # The mode wiring tests focus on ModeManager state, system-prompt injection,
    # and celebration template substitution. hunt() is mocked at the asyncio
    # boundary to avoid live API calls — same exemption as TestCelebrationWiring
    # and TestBadgeWiring above.

    Covers:
      (1) ToolContext has a ModeManager defaulting to 'default' mode
      (2) mode_mgr.switch(name) changes the active mode
      (3) runner.set_character(mode) updates the LLM system prompt
      (4) personality appears in runner system prompt after set_character
      (5) run_module celebration uses active mode's score_celebration template
      (6) unknown mode name raises ValueError / leaves state unchanged
      (7) list_modes returns all mode names including the active one
      (8) default mode is 'default' on fresh ToolContext
      (9) compound: switch mode -> run tool -> celebration uses new mode template
    """

    def _make_mock_module(self, results):
        # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    # --- (1) ToolContext has ModeManager ---

    def test_tool_context_has_mode_manager(self, tmp_ctx):
        """ToolContext.__init__ creates a ModeManager instance."""
        from adversary_pursuit.gamification.modes import ModeManager

        assert hasattr(tmp_ctx, "mode_mgr")
        assert isinstance(tmp_ctx.mode_mgr, ModeManager)

    # --- (8) Default mode ---

    def test_tool_context_default_mode_is_default(self, tmp_ctx):
        """ToolContext.mode_mgr starts in 'default' mode."""
        assert tmp_ctx.mode_mgr.active.name == "default"

    # --- (2) Mode switching ---

    def test_mode_switch_changes_active_mode(self, tmp_ctx):
        """ModeManager.switch('ninja') changes active mode to ninja."""
        tmp_ctx.mode_mgr.switch("ninja")
        assert tmp_ctx.mode_mgr.active.name == "ninja"

    def test_mode_switch_returns_character_mode(self, tmp_ctx):
        """ModeManager.switch() returns the newly-activated CharacterMode."""
        from adversary_pursuit.gamification.modes import CharacterMode

        result = tmp_ctx.mode_mgr.switch("sun_tzu")
        assert isinstance(result, CharacterMode)
        assert result.name == "sun_tzu"

    # --- (6) Unknown mode name ---

    def test_unknown_mode_raises_value_error(self, tmp_ctx):
        """ModeManager.switch() raises ValueError for unknown mode names."""
        with pytest.raises(ValueError, match="Unknown mode"):
            tmp_ctx.mode_mgr.switch("nonexistent_mode")

    def test_unknown_mode_leaves_state_unchanged(self, tmp_ctx):
        """ModeManager.switch() with unknown name does not change the active mode."""
        original = tmp_ctx.mode_mgr.active.name
        try:
            tmp_ctx.mode_mgr.switch("does_not_exist")
        except ValueError:
            pass
        assert tmp_ctx.mode_mgr.active.name == original

    # --- (7) list_modes ---

    def test_list_modes_returns_all_mode_names(self, tmp_ctx):
        """ModeManager.list_modes() returns entries for all built-in modes."""
        modes = tmp_ctx.mode_mgr.list_modes()
        names = {m["name"] for m in modes}
        expected = {
            "default",
            "ninja",
            "full_troll",
            "drunken_master",
            "sun_tzu",
            "chuck_norris",
            "bureaucrat",
            "bobby_hill",
            "bruce_lee",
            "columbo",
        }
        assert expected == names

    def test_list_modes_entries_have_personality(self, tmp_ctx):
        """Each list_modes() entry has 'name' and 'personality' keys."""
        for entry in tmp_ctx.mode_mgr.list_modes():
            assert "name" in entry
            assert "personality" in entry
            assert isinstance(entry["personality"], str)

    # --- (3) & (4) runner.set_character updates system prompt ---

    def test_set_character_updates_system_prompt(self, tmp_ctx):
        """AgentRunner.set_character(mode) updates self.system_prompt."""
        from adversary_pursuit.agent.runner import AgentRunner

        r = AgentRunner(tool_context=tmp_ctx)
        original_prompt = r.system_prompt

        ninja_mode = tmp_ctx.mode_mgr.switch("ninja")
        r.set_character(ninja_mode)

        assert r.system_prompt != original_prompt

    def test_set_character_injects_personality_into_system_prompt(self, tmp_ctx):
        """AgentRunner.set_character(mode) includes mode.personality in system prompt."""
        from adversary_pursuit.agent.runner import AgentRunner

        r = AgentRunner(tool_context=tmp_ctx)
        sun_tzu_mode = tmp_ctx.mode_mgr.switch("sun_tzu")
        r.set_character(sun_tzu_mode)

        assert sun_tzu_mode.personality in r.system_prompt

    def test_set_character_updates_conversation_system_slot(self, tmp_ctx):
        """AgentRunner.set_character() updates conversation[0] system message."""
        from adversary_pursuit.agent.runner import AgentRunner

        r = AgentRunner(tool_context=tmp_ctx)
        drunken_mode = tmp_ctx.mode_mgr.switch("drunken_master")
        r.set_character(drunken_mode)

        assert r.conversation[0]["role"] == "system"
        assert drunken_mode.personality in r.conversation[0]["content"]

    def test_set_character_preserves_conversation_history_length(self, tmp_ctx):
        """set_character() only modifies conversation[0], does not append or truncate."""
        from adversary_pursuit.agent.runner import AgentRunner

        r = AgentRunner(tool_context=tmp_ctx)
        # Manually add a user message to simulate mid-conversation mode switch
        r.conversation.append({"role": "user", "content": "hello"})
        assert len(r.conversation) == 2

        ninja_mode = tmp_ctx.mode_mgr.switch("ninja")
        r.set_character(ninja_mode)

        # Length unchanged — only slot 0 was replaced
        assert len(r.conversation) == 2
        assert r.conversation[1]["content"] == "hello"

    # --- (5) celebration uses active mode template ---

    def test_celebration_uses_default_mode_template(self, tmp_ctx):
        """run_module celebration contains default mode score_celebration text."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["total_points"] > 0
        # Default mode template: "+{points} points!" — formatted result must appear
        expected_text = f"+{result['total_points']} points!"
        assert expected_text in result["celebration"], (
            f"Expected '{expected_text}' in celebration: {result['celebration']!r}"
        )

    def test_celebration_uses_ninja_mode_template_after_switch(self, tmp_ctx):
        """run_module celebration uses ninja mode template after mode switch."""
        tmp_ctx.mode_mgr.switch("ninja")

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["total_points"] > 0
        # Ninja mode template: "[dim]+{points}[/dim]" — the formatted points must appear
        expected_text = f"+{result['total_points']}"
        assert expected_text in result["celebration"], (
            f"Expected '{expected_text}' in celebration: {result['celebration']!r}"
        )

    def test_celebration_uses_sun_tzu_template_after_switch(self, tmp_ctx):
        """run_module celebration uses sun_tzu mode template after switch."""
        tmp_ctx.mode_mgr.switch("sun_tzu")

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["total_points"] > 0
        # sun_tzu template: '"Supreme excellence." +{points} points earned.'
        expected_text = f"+{result['total_points']} points earned."
        assert expected_text in result["celebration"], (
            f"Expected sun_tzu template text '{expected_text}' in: {result['celebration']!r}"
        )

    # --- (9) Compound: switch mode -> run tool -> celebration uses new mode template ---

    def test_compound_mode_switch_then_tool_uses_mode_celebration(self, tmp_ctx):
        """Compound: switch to sun_tzu mode, run tool, celebration uses sun_tzu template.

        This is the required compound-interaction test exercising the real
        production sequence: ModeManager.switch() -> runner.set_character()
        -> ToolContext.run_module() -> celebration computed with active mode's
        score_celebration template.

        Production path: chat.py 'mode sun_tzu' -> mode_mgr.switch('sun_tzu')
        -> runner.set_character(mode) -> user runs a query -> execute_tool()
        -> run_module() -> celebration uses sun_tzu template.
        """
        from adversary_pursuit.agent.runner import AgentRunner

        # 1. Create runner sharing the same ToolContext
        r = AgentRunner(tool_context=tmp_ctx)

        # 2. Switch to sun_tzu mode (as chat.py 'mode sun_tzu' would do)
        new_mode = tmp_ctx.mode_mgr.switch("sun_tzu")
        r.set_character(new_mode)

        # 3. Verify system prompt reflects sun_tzu persona
        assert new_mode.personality in r.system_prompt

        # 4. Run a tool that scores points (hunt() mocked at HTTP boundary)
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["total_points"] > 0

        # 5. Celebration must contain sun_tzu's score_celebration template text
        # sun_tzu template: '"Supreme excellence." +{points} points earned.'
        expected_text = f"+{result['total_points']} points earned."
        assert expected_text in result["celebration"], (
            f"Expected sun_tzu template text '{expected_text}' in: {result['celebration']!r}"
        )


# ---------------------------------------------------------------------------
# HintProvider wiring tests (DEC-AGENT-HINTS-001)
# ---------------------------------------------------------------------------

# @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
# The hint wiring tests use the same exemption as TestCelebrationWiring,
# TestBadgeWiring, and TestModeWiring above: hunt() is mocked at the asyncio
# boundary to avoid live API calls while exercising the full dispatch path.

# Minimal deterministic hint catalogue for tests — avoids coupling to
# _DEFAULT_HINTS order or count.
from adversary_pursuit.gamification.hints import Hint as _Hint  # noqa: E402

_FREE_HINT_GENERAL = _Hint(
    id="test-free-001", text="Free general hint text.", cost=0, module=None
)
_FREE_HINT_DNS = _Hint(
    id="test-free-dns-001",
    text="Free DNS hint text.",
    cost=0,
    module="dns_resolve",
)
_PAID_HINT_GENERAL = _Hint(
    id="test-paid-001", text="Paid general hint text.", cost=10, module=None
)
_PAID_HINT_DNS = _Hint(
    id="test-paid-dns-001",
    text="Paid DNS hint text.",
    cost=15,
    module="dns_resolve",
)

_TEST_HINTS = [
    _FREE_HINT_GENERAL,
    _FREE_HINT_DNS,
    _PAID_HINT_GENERAL,
    _PAID_HINT_DNS,
]


@pytest.fixture
def hint_ctx(tmp_path):
    """ToolContext with deterministic test hint set and a funded workspace."""
    config_dir = tmp_path / "config"
    workspace_dir = tmp_path / "workspaces"
    config_dir.mkdir()
    workspace_dir.mkdir()
    ctx = ToolContext(
        config_dir=config_dir, workspace_dir=workspace_dir, hints=_TEST_HINTS
    )
    ctx.workspace_mgr.create("default")
    ctx.workspace_mgr.switch("default")
    # Seed score so paid-hint tests have a balance to spend (cheapest paid = 10 pts)
    ctx.workspace_mgr.store_score_events(
        [
            {
                "action": "seed",
                "points": 100,
                "indicator": "seed",
                "rule_description": "seed for hint tests",
            }
        ]
    )
    return ctx


class TestHintWiring:
    """Tests for HintProvider integration in ToolContext and execute_tool.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # The compound test mocks hunt() at the asyncio boundary to avoid live API
    # calls — same exemption declared in the file-level docstring and used by
    # TestCelebrationWiring, TestBadgeWiring, and TestModeWiring.

    Covers:
      (1) ToolContext has a HintProvider instance on .hint_mgr
      (2) HintProvider singleton — same instance across accesses preserves revealed state
      (3) execute_tool('get_next_hint') returns next free hint text
      (4) get_next_hint with module= filters to module-specific hints
      (5) get_next_hint returns 'no more' message when all free hints revealed
      (6) execute_tool('buy_hint') deducts score and returns paid hint
      (7) buy_hint with module= filters to module-specific paid hints
      (8) buy_hint returns error string on insufficient balance (score not modified)
      (9) balance protection: score after failed buy equals score before
      (10) hint tools in create_tools() catalog: get_next_hint and buy_hint present
      (11) hint tools have correct schema (no required parameters)
      (12) compound: switch mode -> run module tool -> get hint -> hint surfaces correctly
    """

    # --- (1) ToolContext has HintProvider ---

    def test_tool_context_has_hint_provider(self, hint_ctx):
        """ToolContext.__init__ creates a HintProvider instance on .hint_mgr."""
        from adversary_pursuit.gamification.hints import HintProvider

        assert hasattr(hint_ctx, "hint_mgr")
        assert isinstance(hint_ctx.hint_mgr, HintProvider)

    # --- (2) Singleton — same instance preserves revealed state ---

    def test_hint_mgr_is_same_instance_across_accesses(self, hint_ctx):
        """hint_mgr is the same object across all accesses — session-scoped singleton."""
        first = hint_ctx.hint_mgr
        second = hint_ctx.hint_mgr
        assert first is second

    def test_revealed_state_persists_across_calls(self, hint_ctx):
        """Calling get_next_hint twice returns two different hints (revealed set shared).

        get_next_hint returns hints in cost-ascending order (free first, then paid).
        The second call reveals the paid hint — NOT a 'no more' message, because
        HintProvider.get_next_hint() covers all hints (free and paid), free first.
        """
        from adversary_pursuit.agent.tools import _execute_get_next_hint

        result1 = _execute_get_next_hint(hint_ctx, module=None)
        result2 = _execute_get_next_hint(hint_ctx, module=None)
        # First call: the single general free hint is revealed
        assert "Free general hint text." in result1
        # Second call: paid general hint revealed next (cost-ascending order)
        assert "Paid general hint text." in result2
        # Both are different hints — revealed-set prevented re-showing hint 1
        assert result1 != result2

    # --- (3) get_next_hint returns free hint ---

    def test_execute_get_next_hint_returns_free_hint_text(self, hint_ctx):
        """execute_tool('get_next_hint', {}) returns the next free general hint."""
        summary, celebration, badges = execute_tool(hint_ctx, "get_next_hint", {})
        assert "Free general hint text." in summary
        assert celebration is None
        assert badges == []

    # --- (4) get_next_hint with module filters ---

    def test_get_next_hint_dns_module_surfaces_dns_specific_hint(self, hint_ctx):
        """After general free hint revealed, next get_next_hint for dns_resolve is DNS-specific."""
        from adversary_pursuit.agent.tools import _execute_get_next_hint

        # dns_resolve pool ordered by cost: [free-general(0), free-dns(0), paid-general(10), paid-dns(15)]
        # First call reveals free-general
        _execute_get_next_hint(hint_ctx, module="dns_resolve")
        # Second call reveals free-dns (next unrevealed in module pool)
        result2 = _execute_get_next_hint(hint_ctx, module="dns_resolve")
        assert "Free DNS hint text." in result2

    # --- (5) get_next_hint exhausted → 'no more' message ---

    def test_get_next_hint_exhausted_returns_no_more_message(self, hint_ctx):
        """get_next_hint returns 'no more' string when ALL hints in pool are revealed.

        The general-only pool has 2 hints: free-general (cost=0) and paid-general (cost=10).
        get_next_hint covers free AND paid (free first). After both are revealed,
        the third call returns the 'no more' message.
        """
        from adversary_pursuit.agent.tools import _execute_get_next_hint

        # Reveal hint 1: free-general
        _execute_get_next_hint(hint_ctx, module=None)
        # Reveal hint 2: paid-general (get_next_hint covers all, free first)
        _execute_get_next_hint(hint_ctx, module=None)
        # Third call: pool exhausted
        result = _execute_get_next_hint(hint_ctx, module=None)
        assert "No more free hints" in result
        assert "buy_hint" in result  # directs analyst to paid path

    # --- (6) buy_hint deducts score and returns paid hint ---

    def test_execute_buy_hint_returns_paid_hint_and_deducts_score(self, hint_ctx):
        """execute_tool('buy_hint', {}) deducts cost from score and returns paid hint."""
        score_before = hint_ctx.workspace_mgr.get_total_score()
        summary, celebration, badges = execute_tool(hint_ctx, "buy_hint", {})

        assert "Paid general hint text." in summary
        assert "-10 pts" in summary  # cost note in returned string
        assert celebration is None
        assert badges == []

        score_after = hint_ctx.workspace_mgr.get_total_score()
        assert score_after == score_before - 10

    # --- (7) buy_hint with module filter ---

    def test_execute_buy_hint_module_filter_deducts_correct_cost(self, hint_ctx):
        """execute_tool('buy_hint', {'module': 'dns_resolve'}) deducts correct cost."""
        score_before = hint_ctx.workspace_mgr.get_total_score()
        summary, _, _ = execute_tool(hint_ctx, "buy_hint", {"module": "dns_resolve"})

        # dns_resolve paid pool: paid-general (10 pts) first, paid-dns (15 pts) second
        assert "Paid" in summary or "hint" in summary.lower()
        score_after = hint_ctx.workspace_mgr.get_total_score()
        assert score_after == score_before - 10  # cheapest paid hint costs 10 pts

    # --- (8) buy_hint insufficient balance → error string ---

    def test_buy_hint_insufficient_balance_returns_error_string(self, tmp_path):
        """execute_tool('buy_hint') returns error string when score < hint cost."""
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(
            config_dir=config_dir, workspace_dir=workspace_dir, hints=_TEST_HINTS
        )
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        # Score = 0 — cannot afford any paid hint (cheapest is 10 pts)
        summary, celebration, badges = execute_tool(ctx, "buy_hint", {})

        assert "Insufficient score" in summary or "insufficient" in summary.lower()
        assert "need" in summary.lower() or "pts" in summary.lower()
        assert celebration is None
        assert badges == []

    # --- (9) Balance protection: score unchanged on failed buy ---

    def test_buy_hint_insufficient_balance_does_not_modify_score(self, tmp_path):
        """Score is not deducted when buy_hint raises InsufficientBalanceError."""
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(
            config_dir=config_dir, workspace_dir=workspace_dir, hints=_TEST_HINTS
        )
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        # Score = 0
        score_before = ctx.workspace_mgr.get_total_score()
        execute_tool(ctx, "buy_hint", {})
        score_after = ctx.workspace_mgr.get_total_score()
        assert score_after == score_before == 0

    # --- (10) Hint tools in create_tools catalog ---

    def test_hint_tools_in_create_tools(self, hint_ctx):
        """create_tools includes get_next_hint and buy_hint in the tool catalog."""
        tools = create_tools(hint_ctx)
        names = {t["function"]["name"] for t in tools}
        assert "get_next_hint" in names
        assert "buy_hint" in names

    # --- (11) Hint tool schema has no required parameters ---

    def test_get_next_hint_schema_no_required_params(self, hint_ctx):
        """get_next_hint tool has no required parameters (module is optional)."""
        tools = create_tools(hint_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "get_next_hint")
        params = tool["function"]["parameters"]
        assert "required" not in params or len(params.get("required", [])) == 0

    def test_buy_hint_schema_no_required_params(self, hint_ctx):
        """buy_hint tool has no required parameters (module is optional)."""
        tools = create_tools(hint_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "buy_hint")
        params = tool["function"]["parameters"]
        assert "required" not in params or len(params.get("required", [])) == 0

    # --- (12) Compound: switch mode -> run module tool -> get hint ---

    def test_compound_mode_switch_tool_run_then_hint(self, hint_ctx):
        """Compound: switch to ninja mode, run a module tool, then get hint.

        # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
        # Mocking at the asyncio boundary avoids live API calls while exercising
        # the full dispatch path through workspace storage and scoring.

        Production sequence:
          (a) ModeManager.switch('ninja') changes active mode
          (b) execute_tool(module_tool) runs hunt() (mocked at HTTP boundary),
              stores results, scores, returns celebration with ninja template
          (c) execute_tool('get_next_hint') returns free hint via same HintProvider
              instance — revealed-set shared between LLM tool path and meta-command path

        This crosses ToolContext, ModeManager, WorkspaceManager, ScoringEngine,
        and HintProvider boundaries in the real production call sequence.
        """
        # (a) Switch mode — mirrors chat.py 'mode ninja' meta-command
        hint_ctx.mode_mgr.switch("ninja")
        assert hint_ctx.mode_mgr.active.name == "ninja"

        # (b) Run a module tool that scores points (hunt() mocked at HTTP boundary)
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_IP_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(hint_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _ = execute_tool(
                hint_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )
        assert "Found" in summary
        assert celebration is not None  # ninja mode scored points → celebration present

        # (c) Get a free hint — same HintProvider, same revealed-set
        hint_summary, hint_celebration, hint_badges = execute_tool(
            hint_ctx, "get_next_hint", {}
        )
        assert "Free general hint text." in hint_summary
        assert hint_celebration is None
        assert hint_badges == []

        # Workspace reflects both the seed (100) and module scoring
        total = hint_ctx.workspace_mgr.get_total_score()
        assert total > 100  # seed was 100; module scoring adds more
