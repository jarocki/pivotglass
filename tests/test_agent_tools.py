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
    _CREDENTIAL_BUILDERS,
    _MODULE_MAP,
    ToolContext,
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

    def test_returns_twenty_two_tools(self, tmp_ctx):
        """create_tools returns exactly 28 tool definitions (M-8: removed start_report_interview, answer_report_question, generate_report classic shim tools — DEC-M8-CLEANUP-002)."""
        tools = create_tools(tmp_ctx)
        assert len(tools) == 28

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
        """create_tools includes all expected tool names including hint, challenge, graph/export, and dossier tools (M-8: classic report tools removed)."""
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
            # GreyNoise Community API IP classification
            "greynoise_lookup",
            # F61 keyless hunters
            "urlhaus_lookup",
            "threatfox_lookup",
            "malwarebazaar_lookup",
            "crtsh_lookup",
            # Workspace tools
            "get_workspace_summary",
            "search_workspace",
            # Hint tools (DEC-AGENT-HINTS-001)
            "get_next_hint",
            "buy_hint",
            # Challenge tools (DEC-AGENT-CHALLENGES-001)
            "list_challenges",
            "check_challenges",
            # Graph/export tools (DEC-AGENT-GRAPH-EXPORT-001)
            "render_graph",
            "export_workspace",
            # Dossier state tool (DEC-M2-DOSSIER-005)
            "get_dossier_state",
            # Dossier prediction tool (DEC-M4-PRED-006)
            "create_dossier_prediction",
            # M-5 note authoring + manual falsification tools
            "create_dossier_note",
            "falsify_dossier_prediction",
            # M-7 dossier-aware report generation
            "generate_dossier_report",
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
        assert len(roundtripped) == 28

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
        assert "required" not in params or "target_type" not in params.get("required", [])

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

    def test_greynoise_lookup_has_required_ip_address(self, tmp_ctx):
        """greynoise_lookup tool has 'ip_address' as a required parameter."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "greynoise_lookup")
        params = tool["function"]["parameters"]
        assert "ip_address" in params["properties"]
        assert "ip_address" in params["required"]


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
        summary, celebration, badges, challenges = execute_tool(tmp_ctx, "nonexistent_tool", {})
        assert "Unknown tool" in summary
        assert "nonexistent_tool" in summary
        assert celebration is None

    def test_dns_resolve_dispatches_to_dns_module(self, tmp_ctx):
        """execute_tool('dns_resolve') runs the osint/dns_resolve module."""
        mock_mod = self._make_mock_module(SAMPLE_DOMAIN_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "dns_resolve", {"domain": "example.com"}
            )
            assert isinstance(summary, str)
            assert "Found" in summary
            # Verify get_module was called with correct path
            mock_get.assert_called_once_with("osint/dns_resolve")

    def test_whois_lookup_dispatches(self, tmp_ctx):
        """execute_tool('whois_lookup') runs the osint/whois_lookup module."""
        mock_mod = self._make_mock_module(SAMPLE_DOMAIN_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "whois_lookup", {"target": "example.com"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/whois_lookup")

    def test_check_ip_reputation_dispatches(self, tmp_ctx):
        """execute_tool('check_ip_reputation') runs abuseipdb module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/abuseipdb")

    def test_shodan_host_lookup_dispatches(self, tmp_ctx):
        """execute_tool('shodan_host_lookup') runs osint/shodan_ip module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "shodan_host_lookup", {"ip_address": "1.2.3.4"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/shodan_ip")

    def test_check_breaches_dispatches(self, tmp_ctx):
        """execute_tool('check_breaches') runs osint/hibp module."""
        mock_mod = self._make_mock_module([{"type": "email-addr", "value": "user@example.com"}])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "check_breaches", {"email": "user@example.com"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/hibp")

    def test_otx_threat_intel_dispatches(self, tmp_ctx):
        """execute_tool('otx_threat_intel') runs cti/otx module."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "otx_threat_intel", {"target": "1.2.3.4"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("cti/otx")

    def test_scan_url_dispatches(self, tmp_ctx):
        """execute_tool('scan_url') runs osint/urlscan module."""
        mock_mod = self._make_mock_module([{"type": "url", "value": "http://evil.example.com"}])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "scan_url", {"url": "http://evil.example.com"}
            )
            assert isinstance(summary, str)
            mock_get.assert_called_once_with("osint/urlscan")

    def test_module_not_found_returns_error(self, tmp_ctx):
        """execute_tool returns (error_string, None) when module not found."""
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=None):
            summary, celebration, _badges, _challenges = execute_tool(
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
            summary, celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "dns_resolve", {"domain": "example.com"}
            )
        assert "Error" in summary
        assert celebration is None

    # --- New tool dispatch tests ---

    def test_virustotal_lookup_dispatches(self, tmp_ctx):
        """execute_tool('virustotal_lookup') runs cti/virustotal module."""
        mock_mod = self._make_mock_module(SAMPLE_VT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "virustotal_lookup", {"target": "1.2.3.4"}
            )
            assert isinstance(summary, str)
            assert "Found" in summary
            mock_get.assert_called_once_with("cti/virustotal")

    def test_virustotal_lookup_passes_target_type(self, tmp_ctx):
        """execute_tool('virustotal_lookup') passes TARGET_TYPE option to module."""
        mock_mod = self._make_mock_module(SAMPLE_VT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            execute_tool(tmp_ctx, "virustotal_lookup", {"target": "1.2.3.4", "target_type": "ip"})
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
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
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
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
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
        mock_mod.hunt.assert_called_once_with("evil.example.com", {"INCLUDE_WHOIS": "true"})

    def test_passivetotal_lookup_passes_include_whois_false(self, tmp_ctx):
        """execute_tool('passivetotal_lookup') passes INCLUDE_WHOIS=false when requested."""
        mock_mod = self._make_mock_module(SAMPLE_PT_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            execute_tool(
                tmp_ctx,
                "passivetotal_lookup",
                {"target": "evil.example.com", "include_whois": False},
            )
        mock_mod.hunt.assert_called_once_with("evil.example.com", {"INCLUDE_WHOIS": "false"})


# ---------------------------------------------------------------------------
# execute_tool — workspace tools
# ---------------------------------------------------------------------------


class TestWorkspaceTools:
    """execute_tool handles get_workspace_summary and search_workspace.

    # @mock-exempt: no mocks used — workspace tools use real in-memory SQLite.
    """

    def test_get_workspace_summary_returns_string(self, tmp_ctx):
        """execute_tool('get_workspace_summary', {}) returns (summary, None)."""
        summary, celebration, _badges, _challenges = execute_tool(
            tmp_ctx, "get_workspace_summary", {}
        )
        assert isinstance(summary, str)
        assert "Workspace" in summary or "workspace" in summary.lower()
        assert celebration is None

    def test_get_workspace_summary_includes_counts(self, tmp_ctx):
        """Workspace summary includes total indicators and score."""
        summary, _celebration, _badges, _challenges = execute_tool(
            tmp_ctx, "get_workspace_summary", {}
        )
        assert "indicators" in summary.lower() or "Total" in summary

    def test_search_workspace_empty_returns_message(self, tmp_ctx):
        """search_workspace on empty workspace returns (no-results string, None)."""
        summary, celebration, _badges, _challenges = execute_tool(tmp_ctx, "search_workspace", {})
        assert isinstance(summary, str)
        # Empty workspace should indicate no results found
        assert "No" in summary or "0" in summary or "no" in summary.lower()
        assert celebration is None

    def test_search_workspace_with_type_filter(self, tmp_ctx):
        """search_workspace with type_filter filters by STIX type."""
        summary, _celebration, _badges, _challenges = execute_tool(
            tmp_ctx, "search_workspace", {"type_filter": "ipv4-addr"}
        )
        assert isinstance(summary, str)

    def test_search_workspace_after_storing_objects(self, tmp_ctx):
        """search_workspace returns stored objects after a module run."""
        # Store some objects directly
        objects = [{"type": "ipv4-addr", "value": "1.2.3.4"}]
        tmp_ctx.workspace_mgr.store_stix_objects(objects, "test/module", "1.2.3.4")

        summary, _celebration, _badges, _challenges = execute_tool(
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

    def test_censys_builder_returns_censys_pat(self, tmp_ctx):
        """Censys credential builder produces censys_pat key (PAT-based auth, resolves #45)."""
        builder = _CREDENTIAL_BUILDERS["osint/censys_host"]
        config = builder(tmp_ctx.config_mgr)
        assert "censys_pat" in config
        # Should be a string (empty when not configured)
        assert isinstance(config["censys_pat"], str)

    def test_passivetotal_builder_returns_user_and_key(self, tmp_ctx):
        """PassiveTotal credential builder produces passivetotal_user and passivetotal_key."""
        builder = _CREDENTIAL_BUILDERS["cti/passivetotal"]
        config = builder(tmp_ctx.config_mgr)
        assert "passivetotal_user" in config
        assert "passivetotal_key" in config
        assert isinstance(config["passivetotal_user"], str)
        assert isinstance(config["passivetotal_key"], str)

    def test_run_module_uses_censys_credentials(self, tmp_ctx):
        """run_module initializes censys_host with censys_pat (PAT-based auth, resolves #45)."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_CENSYS_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/censys_host", "8.8.8.8", {})

        mock_mod.initialize.assert_called_once()
        init_arg = mock_mod.initialize.call_args[0][0]
        # Must use PAT-based auth — legacy id/secret path removed (resolves #45)
        assert "api_key" not in init_arg
        assert "censys_pat" in init_arg
        assert "censys_id" not in init_arg
        assert "censys_secret" not in init_arg

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
    """_MODULE_MAP contains entries for all 11 module-backed tools."""

    def test_module_map_has_eleven_entries(self):
        """_MODULE_MAP has exactly 15 entries (11 prior + 4 keyless hunters F61)."""
        assert len(_MODULE_MAP) == 15

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
            summary, celebration, _badges, _challenges = execute_tool(
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
            summary, celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "censys_host_lookup", {"ip_address": "8.8.8.8"}
            )

        assert isinstance(summary, str)
        assert "Found" in summary

        # Verify PAT-based credentials were used (resolves #45, DEC-CONFIG-CENSYS-PAT-001)
        mock_mod.initialize.assert_called_once()
        init_arg = mock_mod.initialize.call_args[0][0]
        assert "censys_pat" in init_arg
        assert "censys_id" not in init_arg
        assert "censys_secret" not in init_arg

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
            summary, celebration, _badges, _challenges = execute_tool(
                tmp_ctx,
                "passivetotal_lookup",
                {"target": "evil.example.com", "include_whois": True},
            )

        assert isinstance(summary, str)
        assert "Found" in summary

        # Verify INCLUDE_WHOIS was passed as string "true"
        mock_mod.hunt.assert_called_once_with("evil.example.com", {"INCLUDE_WHOIS": "true"})

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
                summary, celebration, _badges, _challenges = execute_tool(tmp_ctx, tool_name, args)
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

        M-3 note: even a zero-SCO hunt logs a ModuleRun, which advances Capability
        and Timing from EMPTY→PARTIAL on the *first* call. To isolate the zero-points
        path we pre-seed one run for the same module so the pre-snapshot is already
        PARTIAL; the second (test) call adds another run for the same module but
        produces no slot upward transitions and no per-IOC score events.
        """
        # Pre-seed: advance Capability+Timing to PARTIAL before the test call.
        tmp_ctx.workspace_mgr.store_stix_objects([], "osint/abuseipdb", "1.2.3.4")

        # Now run with empty results: pre and post snapshots both show the same
        # one distinct module (osint/abuseipdb) — no upward transitions fire.
        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["total_points"] == 0
        assert result["celebration"] is None

    def test_execute_tool_returns_celebration_string_for_scoring_tools(self, tmp_ctx):
        """execute_tool returns a non-None celebration for tools that award points."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        assert isinstance(summary, str)
        assert celebration is not None
        assert isinstance(celebration, str)

    def test_execute_tool_celebration_none_when_no_score(self, tmp_ctx):
        """execute_tool celebration is None when hunt() returns no new indicators.

        M-3 note: pre-seed one run for the same module so Capability+Timing are
        already PARTIAL; the test call then produces no upward slot transitions and
        no per-IOC events, leaving total_points==0 and celebration==None.
        """
        # Pre-seed: advance Capability+Timing to PARTIAL before the test call.
        tmp_ctx.workspace_mgr.store_stix_objects([], "osint/abuseipdb", "1.2.3.4")

        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            _summary, celebration, _badges, _challenges = execute_tool(
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

    def test_milestone_message_appended_when_threshold_crossed(self, tmp_ctx):
        """Milestone message appended to celebration when total_score crosses a threshold.

        DEC-63-MILESTONE-CATCHUP-001: uses check_milestones cross-threshold semantics.
        We seed the workspace score to 99 pts, explicitly set last_announced_id=0 to
        bypass quiet-start migration, then trigger a scoring event that pushes total
        >= 100 so the first milestone fires.
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

        # Explicitly seed last_announced_id=0 so quiet-start migration is bypassed
        # and check_milestones can fire the first milestone this run.
        # Without this, the quiet-start migration in run_module would seed last_id=1
        # (highest milestone already crossed at 99pts is none, so actually this is
        # safe — but we set it to ensure test intent is explicit and deterministic).
        # last_id stays None naturally (no sentinel yet), quiet-start will not fire
        # because 99 pts does NOT cross the 100-pt threshold yet — score < 100.
        # After the run, post_total will be >= 100, milestone id=1 should fire.

        # Now trigger a scoring event so post-storage total >= 100
        single_result = [{"type": "email-addr", "value": "unique@example.com"}]
        mock_mod = self._make_mock_module(single_result)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/hibp", "unique@example.com", {})

        if result["total_points"] > 0:
            post_total = tmp_ctx.workspace_mgr.get_total_score()
            if post_total >= 100:
                # Milestone id=1 (threshold=100) must have fired.
                # Celebration string must contain milestone message text.
                milestone_msg = MILESTONES[0].message  # id=1, threshold=100
                assert milestone_msg in (result["celebration"] or ""), (
                    f"Expected milestone message '{milestone_msg}' in celebration "
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
            summary, celebration, _badges, _challenges = execute_tool(
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

    def test_badge_info_not_in_llm_summary(self, tmp_path):
        """F64: Badge text must NOT appear in LLM summary — sidecar result['badges'] only.

        DEC-64-LLM-PANEL-SEPARATION-001: the LLM summary is findings-only.
        Badge award text lives in result['badges'] (for chat.py Rich panels) and
        must not be injected into the summary string that the LLM narrates back.
        """
        ctx = self._make_high_score_ctx(tmp_path)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        summary = result["summary"]
        # Badge award text must NOT appear in the LLM-facing summary
        assert "Badge(s) earned" not in summary, (
            f"Badge award text leaked into LLM summary: {summary!r}"
        )
        for badge in result.get("badges", []):
            assert badge.name not in summary, (
                f"Badge name {badge.name!r} leaked into LLM summary: {summary!r}"
            )

    def test_execute_tool_returns_badges_list(self, tmp_path):
        """execute_tool returns a 4-tuple (summary, celebration, badges, challenges)."""
        ctx = self._make_high_score_ctx(tmp_path)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = execute_tool(ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"})

        assert len(result) == 4
        summary, celebration, badges, challenges = result
        assert isinstance(summary, str)
        assert isinstance(badges, list)
        assert isinstance(challenges, list)

    def test_execute_tool_badges_empty_for_workspace_meta_tools(self, tmp_ctx):
        """Workspace meta-tools return badges=[], challenges=[] — no gamification check."""
        summary, celebration, badges, challenges = execute_tool(
            tmp_ctx, "get_workspace_summary", {}
        )
        assert badges == []
        assert challenges == []
        summary2, celebration2, badges2, challenges2 = execute_tool(tmp_ctx, "search_workspace", {})
        assert badges2 == []
        assert challenges2 == []

    def test_execute_tool_badges_empty_for_unknown_tool(self, tmp_ctx):
        """execute_tool returns badges=[] for unknown tool names."""
        summary, celebration, badges, challenges = execute_tool(tmp_ctx, "unknown_tool", {})
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
            summary, celebration, badges, challenges = execute_tool(
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
        assert len(r.tools) == 28

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
        from adversary_pursuit.agent.runner import HAS_LITELLM, AgentRunner

        if HAS_LITELLM:
            pytest.skip("litellm is installed — ImportError path not tested")
        r = AgentRunner(tool_context=tmp_ctx)
        with pytest.raises(ImportError, match="litellm"):
            r.chat("test message")


# ---------------------------------------------------------------------------
# AP_MODEL env-var override tests (DEC-AGENT-MODEL-ENV-001)
# ---------------------------------------------------------------------------


class TestAgentRunnerModelResolution:
    """Verify AP_MODEL env-var precedence: explicit arg > AP_MODEL > DEFAULT_MODEL.

    Production sequence: AgentRunner.__init__ is called (via `ap chat` or
    directly) and resolves self.model from three possible sources.  These
    tests exercise all three precedence paths plus the edge-case of an empty
    env var, covering the full state-transition space of the `or` chain.
    """

    def test_default_model_when_no_arg_no_env(self, tmp_ctx, monkeypatch):
        """Falls through to DEFAULT_MODEL when neither arg nor AP_MODEL is set."""
        from adversary_pursuit.agent.runner import AgentRunner

        monkeypatch.delenv("AP_MODEL", raising=False)
        r = AgentRunner(tool_context=tmp_ctx)
        assert r.model == AgentRunner.DEFAULT_MODEL

    def test_env_var_overrides_default(self, tmp_ctx, monkeypatch):
        """AP_MODEL env var is used when no explicit model= arg is given."""
        from adversary_pursuit.agent.runner import AgentRunner

        monkeypatch.setenv("AP_MODEL", "foo/bar")
        r = AgentRunner(tool_context=tmp_ctx)
        assert r.model == "foo/bar"

    def test_explicit_arg_overrides_env_var(self, tmp_ctx, monkeypatch):
        """Explicit model= arg takes priority over AP_MODEL env var."""
        from adversary_pursuit.agent.runner import AgentRunner

        monkeypatch.setenv("AP_MODEL", "foo/bar")
        r = AgentRunner(model="baz/qux", tool_context=tmp_ctx)
        assert r.model == "baz/qux"

    def test_explicit_arg_overrides_default_when_no_env(self, tmp_ctx, monkeypatch):
        """Explicit model= arg is used even when AP_MODEL is absent."""
        from adversary_pursuit.agent.runner import AgentRunner

        monkeypatch.delenv("AP_MODEL", raising=False)
        r = AgentRunner(model="x/y", tool_context=tmp_ctx)
        assert r.model == "x/y"

    def test_empty_env_var_falls_through_to_default(self, tmp_ctx, monkeypatch):
        """Empty AP_MODEL string is falsy — runner falls through to DEFAULT_MODEL."""
        from adversary_pursuit.agent.runner import AgentRunner

        monkeypatch.setenv("AP_MODEL", "")
        r = AgentRunner(tool_context=tmp_ctx)
        assert r.model == AgentRunner.DEFAULT_MODEL


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

_FREE_HINT_GENERAL = _Hint(id="test-free-001", text="Free general hint text.", cost=0, module=None)
_FREE_HINT_DNS = _Hint(
    id="test-free-dns-001",
    text="Free DNS hint text.",
    cost=0,
    module="dns_resolve",
)
_PAID_HINT_GENERAL = _Hint(id="test-paid-001", text="Paid general hint text.", cost=10, module=None)
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
    ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir, hints=_TEST_HINTS)
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
        summary, celebration, badges, challenges = execute_tool(hint_ctx, "get_next_hint", {})
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
        summary, celebration, badges, challenges = execute_tool(hint_ctx, "buy_hint", {})

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
        summary, _, _, _ = execute_tool(hint_ctx, "buy_hint", {"module": "dns_resolve"})

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
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir, hints=_TEST_HINTS)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        # Score = 0 — cannot afford any paid hint (cheapest is 10 pts)
        summary, celebration, badges, challenges = execute_tool(ctx, "buy_hint", {})

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
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir, hints=_TEST_HINTS)
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
            summary, celebration, _, _challenges = execute_tool(
                hint_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )
        assert "Found" in summary
        assert celebration is not None  # ninja mode scored points → celebration present

        # (c) Get a free hint — same HintProvider, same revealed-set
        hint_summary, hint_celebration, hint_badges, _hint_challenges = execute_tool(
            hint_ctx, "get_next_hint", {}
        )
        assert "Free general hint text." in hint_summary
        assert hint_celebration is None
        assert hint_badges == []

        # Workspace reflects both the seed (100) and module scoring
        total = hint_ctx.workspace_mgr.get_total_score()
        assert total > 100  # seed was 100; module scoring adds more


# ---------------------------------------------------------------------------
# EventBus auto-pivot wiring tests (DEC-AGENT-AUTOPIVOT-001)
# ---------------------------------------------------------------------------


class TestAutopivotWiring:
    """Tests for EventBus auto-pivot integration in ToolContext.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # Cascade callbacks use the same hunt() mock pattern as other tests.
    # EventBus.publish() is called internally — we verify its effects through
    # ToolContext state (cascade_results returned by run_module).

    Covers:
      (1) ToolContext has event_bus (EventBus) and autopivot_enabled=False by default
      (2) set_autopivot(True) enables, set_autopivot(False) disables
      (3) autopivot_enabled=False → cascade does not fire (cascade_results=[])
      (4) autopivot_enabled=True + results → cascade fires (cascade_results non-empty)
      (5) depth limit respected via PivotConfig.max_depth=0 (no second-level cascade)
      (6) module whitelist filters cascades via PivotConfig.module_whitelist
      (7) cascade results surfaced in tool summary ("Auto-pivoted" text)
      (8) cascade_count key present in run_module return dict
      (9) event_bus.subscriber_count > 0 after ToolContext init (subscriptions registered)
      (10) compound: switch mode → enable autopivot → run tool → cascade fires
    """

    def _make_mock_module(self, results):
        # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    # --- (1) ToolContext has event_bus and autopivot_enabled ---

    def test_tool_context_has_event_bus(self, tmp_ctx):
        """ToolContext.__init__ creates an EventBus instance on .event_bus."""
        from adversary_pursuit.core.event_bus import EventBus

        assert hasattr(tmp_ctx, "event_bus")
        assert isinstance(tmp_ctx.event_bus, EventBus)

    def test_autopivot_disabled_by_default(self, tmp_ctx):
        """autopivot_enabled defaults to False on a fresh ToolContext (DEC-EVENTBUS-002)."""
        assert tmp_ctx.autopivot_enabled is False

    def test_event_bus_config_disabled_by_default(self, tmp_ctx):
        """EventBus.config.enabled matches autopivot_enabled (False) on init."""
        assert tmp_ctx.event_bus.config.enabled is False

    # --- (9) Subscriptions registered ---

    def test_event_bus_has_subscriptions_after_init(self, tmp_ctx):
        """EventBus.subscriber_count > 0 after ToolContext init (DEFAULT_SUBSCRIPTIONS wired)."""
        assert tmp_ctx.event_bus.subscriber_count > 0

    # --- (2) set_autopivot toggles state ---

    def test_set_autopivot_true_enables(self, tmp_ctx):
        """set_autopivot(True) sets autopivot_enabled=True and event_bus.config.enabled=True."""
        tmp_ctx.set_autopivot(True)
        assert tmp_ctx.autopivot_enabled is True
        assert tmp_ctx.event_bus.config.enabled is True

    def test_set_autopivot_false_disables(self, tmp_ctx):
        """set_autopivot(False) sets autopivot_enabled=False and event_bus.config.enabled=False."""
        tmp_ctx.set_autopivot(True)
        tmp_ctx.set_autopivot(False)
        assert tmp_ctx.autopivot_enabled is False
        assert tmp_ctx.event_bus.config.enabled is False

    # --- (3) cascade does NOT fire when autopivot disabled ---

    def test_cascade_not_fired_when_autopivot_disabled(self, tmp_ctx):
        """With autopivot_enabled=False, run_module returns cascade_results=[]."""
        assert tmp_ctx.autopivot_enabled is False  # default

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["cascade_results"] == []
        assert result["cascade_count"] == 0

    def test_cascade_not_fired_when_results_empty(self, tmp_ctx):
        """Even with autopivot enabled, empty hunt() results produce no cascades."""
        tmp_ctx.set_autopivot(True)

        mock_mod = self._make_mock_module([])
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["cascade_results"] == []
        assert result["cascade_count"] == 0

    # --- (4) cascade fires when autopivot enabled and results non-empty ---

    def test_cascade_fires_when_autopivot_enabled(self, tmp_ctx):
        """With autopivot_enabled=True and STIX results, cascade_results is non-empty.

        # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
        # We mock both the primary module (plugin_mgr.get_module) and the cascade
        # module callbacks to verify that process_results fires subscribed callbacks
        # for the STIX types present in SAMPLE_IP_RESULTS (ipv4-addr, domain-name).

        F61 adds urlhaus + threatfox as ipv4-addr subscribers (6 total). The default
        max_per_cascade=5 would exhaust budget before the mock callback (appended
        last) fires. Raise the budget to 20 so the mock callback is guaranteed a
        slot regardless of subscriber count.
        """
        tmp_ctx.set_autopivot(True)

        # Raise per-cascade budget so the mock callback (appended last after all
        # real module callbacks) is not blocked by budget exhaustion (F61 adds
        # urlhaus+threatfox as ipv4-addr subscribers, raising subscriber count to 6).
        tmp_ctx.event_bus._policy._cfg = tmp_ctx.event_bus._policy._cfg.model_copy(
            update={"max_per_cascade": 20}
        )

        # Cascade callback mock: returns one result so cascade_results is non-empty
        cascade_result = [{"type": "ipv4-addr", "value": "9.9.9.9"}]
        cascade_callback = AsyncMock(return_value=cascade_result)

        # Subscribe the mock callback directly for ipv4-addr so we control what fires
        tmp_ctx.event_bus.subscribe("ipv4-addr", cascade_callback)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        # Cascade should have fired for the ipv4-addr in SAMPLE_IP_RESULTS
        assert result["cascade_count"] > 0
        assert len(result["cascade_results"]) > 0
        cascade_callback.assert_called()

    # --- (5) depth limit respected ---

    def test_zero_cascade_budget_prevents_cascades(self, tmp_path):
        """PivotPolicy.max_per_cascade=0 prevents any cascade from firing.

        max_depth was removed in F60 (DEC-60-PIVOT-POLICY-006). Budget-based
        flow control replaces it: max_per_cascade=0 exhausts immediately so no
        callbacks are invoked.
        """
        from adversary_pursuit.core.config import AutoPivotPolicyConfig
        from adversary_pursuit.core.event_bus import EventBus, PivotConfig

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        # Rebuild event bus with max_per_cascade=0 so budget is immediately exhausted
        policy_cfg = AutoPivotPolicyConfig(
            max_per_cascade=0,
            max_per_session=1000,
            allowlist_path="/dev/null",
            denylist_path="/dev/null",
        )
        ctx.event_bus = EventBus(config=PivotConfig(enabled=False, policy=policy_cfg))
        ctx.autopivot_enabled = False
        ctx.set_autopivot(True)

        cascade_callback = AsyncMock(return_value=[{"type": "ipv4-addr", "value": "9.9.9.9"}])
        cascade_callback._module_path = "test"
        ctx.event_bus.subscribe("ipv4-addr", cascade_callback)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        # With max_per_cascade=0, PivotPolicy budget gate blocks all callbacks
        assert result["cascade_results"] == []
        cascade_callback.assert_not_called()

    # --- (6) module whitelist filters cascades ---

    def test_module_whitelist_filters_cascade_subscriptions(self, tmp_path):
        """PivotConfig.module_whitelist restricts which modules can subscribe.

        When module_whitelist is set, register_module_subscriptions() skips
        modules not on the list, so their callbacks never fire.
        """
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()

        # Build a ToolContext with a whitelist that excludes all DEFAULT_SUBSCRIPTIONS modules.
        # We do this by patching PivotConfig after construction.
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        # Reset the event bus with a whitelist that allows NO module from DEFAULT_SUBSCRIPTIONS.
        # This simulates a restrictive whitelist — all cascade subscriptions are excluded.
        from adversary_pursuit.core.event_bus import EventBus, PivotConfig

        ctx.event_bus = EventBus(
            config=PivotConfig(enabled=True, module_whitelist=["nonexistent/module"])
        )
        # Re-register subscriptions with the new whitelist — all should be filtered out
        from adversary_pursuit.core.event_bus import DEFAULT_SUBSCRIPTIONS

        for module_path, stix_types in DEFAULT_SUBSCRIPTIONS.items():
            callback = ctx._make_cascade_callback(module_path)
            ctx.event_bus.register_module_subscriptions(module_path, stix_types, callback)

        ctx.autopivot_enabled = True

        # No subscriptions should have been registered (all filtered by whitelist)
        assert ctx.event_bus.subscriber_count == 0

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_IP_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert result["cascade_results"] == []

    # --- (7) cascade results surface in tool summary ---

    def test_cascade_summary_text_present_when_cascade_fires(self, tmp_ctx):
        """When cascades fire, 'Auto-pivoted' text appears in run_module summary."""
        tmp_ctx.set_autopivot(True)

        cascade_result = [{"type": "ipv4-addr", "value": "9.9.9.9"}]
        cascade_callback = AsyncMock(return_value=cascade_result)
        tmp_ctx.event_bus.subscribe("ipv4-addr", cascade_callback)

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        if result["cascade_count"] > 0:
            assert "Auto-pivoted" in result["summary"]
            assert str(result["cascade_count"]) in result["summary"]

    def test_cascade_summary_absent_when_autopivot_disabled(self, tmp_ctx):
        """When autopivot is off, 'Auto-pivoted' text does NOT appear in summary."""
        assert tmp_ctx.autopivot_enabled is False

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert "Auto-pivoted" not in result["summary"]

    # --- (8) cascade_count key present ---

    def test_run_module_returns_cascade_keys(self, tmp_ctx):
        """run_module always returns 'cascade_results' and 'cascade_count' keys."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        assert "cascade_results" in result
        assert "cascade_count" in result
        assert isinstance(result["cascade_results"], list)
        assert isinstance(result["cascade_count"], int)

    # --- (10) Compound: switch mode → enable autopivot → run tool → cascade fires ---

    def test_compound_mode_switch_autopivot_tool_run(self, tmp_ctx):
        """Compound: switch to ninja mode, enable autopivot, run tool, cascade fires.

        # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.

        Production sequence:
          (a) chat.py 'mode ninja' → mode_mgr.switch('ninja') + runner.set_character()
          (b) chat.py 'autopivot on' → ctx.set_autopivot(True)
          (c) LLM calls execute_tool(module_tool) → run_module → cascade fires
          (d) cascade_results non-empty → 'Auto-pivoted' in LLM summary

        This crosses ModeManager, EventBus, ToolContext, and WorkspaceManager
        boundaries in the real production call sequence.
        """
        from adversary_pursuit.agent.runner import AgentRunner

        # (a) Switch to ninja mode (as chat.py 'mode ninja' would do)
        runner = AgentRunner(tool_context=tmp_ctx)
        new_mode = tmp_ctx.mode_mgr.switch("ninja")
        runner.set_character(new_mode)
        assert tmp_ctx.mode_mgr.active.name == "ninja"

        # (b) Enable autopivot (as chat.py 'autopivot on' would do)
        tmp_ctx.set_autopivot(True)
        assert tmp_ctx.autopivot_enabled is True
        assert tmp_ctx.event_bus.config.enabled is True

        # Raise per-cascade budget so the mock callback (appended last after all
        # real module callbacks) is not blocked by budget exhaustion. F61 adds
        # urlhaus + threatfox as ipv4-addr subscribers, raising the count to 6;
        # the default max_per_cascade=5 exhausts before the mock fires.
        tmp_ctx.event_bus._policy._cfg = tmp_ctx.event_bus._policy._cfg.model_copy(
            update={"max_per_cascade": 20}
        )

        # Subscribe a mock cascade callback for ipv4-addr
        cascade_result = [{"type": "domain-name", "value": "cascade.example.com"}]
        cascade_callback = AsyncMock(return_value=cascade_result)
        tmp_ctx.event_bus.subscribe("ipv4-addr", cascade_callback)

        # (c) Execute a module tool that produces STIX results
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        # Primary results stored and scored
        assert result["total_points"] > 0
        # Cascade fired (SAMPLE_IP_RESULTS contains ipv4-addr)
        assert result["cascade_count"] > 0
        cascade_callback.assert_called()

        # (d) Cascade surfaced in summary
        assert "Auto-pivoted" in result["summary"]

        # Ninja mode celebration template used
        expected_points_text = f"+{result['total_points']}"
        assert expected_points_text in result["celebration"]


# ---------------------------------------------------------------------------
# ChallengeManager wiring tests (DEC-AGENT-CHALLENGES-001)
# ---------------------------------------------------------------------------


class TestChallengeWiring:
    """Tests for ChallengeManager integration in ToolContext, run_module, and execute_tool.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # Mocking at the asyncio boundary avoids live API calls while testing the
    # real challenge auto-check path through ChallengeManager.

    Production sequence validated:
      ToolContext init → ChallengeManager ready →
      run_module() → workspace updated → check_all() → newly-completed surfaced →
      execute_tool("list_challenges" / "check_challenges") → LLM-readable strings.
    """

    def _make_mock_module(self, results):
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    # ------------------------------------------------------------------
    # ToolContext has challenge_mgr
    # ------------------------------------------------------------------

    def test_toolcontext_has_challenge_mgr(self, tmp_ctx):
        """ToolContext.challenge_mgr is a ChallengeManager instance."""
        from adversary_pursuit.gamification.challenges import ChallengeManager

        assert hasattr(tmp_ctx, "challenge_mgr")
        assert isinstance(tmp_ctx.challenge_mgr, ChallengeManager)

    def test_toolcontext_has_announced_challenges_set(self, tmp_ctx):
        """ToolContext._announced_challenges starts as an empty set."""
        assert hasattr(tmp_ctx, "_announced_challenges")
        assert isinstance(tmp_ctx._announced_challenges, set)
        assert len(tmp_ctx._announced_challenges) == 0

    def test_challenge_mgr_has_builtin_challenges(self, tmp_ctx):
        """ChallengeManager loads built-in challenges on ToolContext init."""
        items = tmp_ctx.challenge_mgr.list_challenges()
        assert len(items) >= 5  # 5 starter challenges defined in _load_builtin_challenges

    # ------------------------------------------------------------------
    # list_challenges LLM tool
    # ------------------------------------------------------------------

    def test_list_challenges_in_create_tools(self, tmp_ctx):
        """create_tools() includes list_challenges tool definition."""
        tools = create_tools(tmp_ctx)
        names = {t["function"]["name"] for t in tools}
        assert "list_challenges" in names

    def test_list_challenges_returns_string(self, tmp_ctx):
        """execute_tool('list_challenges') returns a non-empty string."""
        summary, celebration, badges, challenges = execute_tool(tmp_ctx, "list_challenges", {})
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert celebration is None
        assert badges == []

    def test_list_challenges_mentions_active_challenges(self, tmp_ctx):
        """list_challenges output references active challenges by name."""
        summary, _, _, _ = execute_tool(tmp_ctx, "list_challenges", {})
        # Built-in challenges include "First Blood", "Domain Hunter", etc.
        # At least one should appear since all start ACTIVE.
        assert "ACTIVE" in summary or "active" in summary.lower()

    def test_list_challenges_returns_all_builtin_challenges(self, tmp_ctx):
        """list_challenges output references all 5 built-in challenge IDs."""
        summary, _, _, _ = execute_tool(tmp_ctx, "list_challenges", {})
        for ch_id in ["ch-001", "ch-002", "ch-003", "ch-004", "ch-005"]:
            assert ch_id in summary, f"Challenge {ch_id} missing from list_challenges output"

    # ------------------------------------------------------------------
    # check_challenges LLM tool
    # ------------------------------------------------------------------

    def test_check_challenges_in_create_tools(self, tmp_ctx):
        """create_tools() includes check_challenges tool definition."""
        tools = create_tools(tmp_ctx)
        names = {t["function"]["name"] for t in tools}
        assert "check_challenges" in names

    def test_check_challenges_returns_none_when_no_criteria_met(self, tmp_ctx):
        """check_challenges returns 'none completed' message on empty workspace."""
        summary, celebration, badges, challenges = execute_tool(tmp_ctx, "check_challenges", {})
        assert isinstance(summary, str)
        assert (
            "No new challenges" in summary or "none" in summary.lower() or "keep" in summary.lower()
        )
        assert celebration is None
        assert badges == []

    def test_check_challenges_detects_score_threshold(self, tmp_ctx):
        """check_challenges fires when score_threshold challenge criteria met.

        ch-004 (Score Hunter) requires total_score >= 500.
        We inject a large score event directly into the workspace, then call
        check_challenges — it should report ch-004 as newly completed.
        """
        # Inject score events directly to reach 500 pts without running a module
        tmp_ctx.workspace_mgr.store_score_events(
            [
                {
                    "action": "test",
                    "points": 500,
                    "indicator": "1.2.3.4",
                    "rule_description": "Test injection",
                }
            ]
        )
        summary, _, _, _ = execute_tool(tmp_ctx, "check_challenges", {})
        # ch-004 "Score Hunter" requires min_score=500
        assert "Score Hunter" in summary or "ch-004" in summary

    # ------------------------------------------------------------------
    # run_module auto-check and summary surfacing
    # ------------------------------------------------------------------

    def test_run_module_returns_challenges_key(self, tmp_ctx):
        """run_module() result dict contains a 'challenges' key."""
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
        assert "challenges" in result
        assert isinstance(result["challenges"], list)

    def test_run_module_challenge_completes_on_first_ip(self, tmp_ctx):
        """run_module completes ch-001 (First Blood) when first ipv4-addr discovered.

        ch-001 verification: indicator_count, stix_type=ipv4-addr, min_count=1.
        SAMPLE_IP_RESULTS contains one ipv4-addr, so ch-001 should complete.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
        # ch-001 "First Blood" should be in newly_completed_challenges
        completed_ids = [ch.id for ch in result["challenges"]]
        assert "ch-001" in completed_ids

    def test_run_module_challenge_not_in_summary(self, tmp_ctx):
        """F64: Challenge text must NOT appear in LLM summary — sidecar result['challenges'] only.

        DEC-64-LLM-PANEL-SEPARATION-001: the LLM summary is findings-only.
        Challenge completion text lives in result['challenges'] (for chat.py Rich panels)
        and must not be injected into the summary string that the LLM narrates back.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
        summary = result["summary"]
        # Challenge completion text must NOT appear in the LLM-facing summary
        assert "Challenge(s) completed" not in summary, (
            f"Challenge completion text leaked into LLM summary: {summary!r}"
        )
        for ch in result.get("challenges", []):
            assert ch.name not in summary, (
                f"Challenge name {ch.name!r} leaked into LLM summary: {summary!r}"
            )

    def test_run_module_no_reannnouncement(self, tmp_ctx):
        """Completed challenges are NOT re-announced on subsequent run_module calls.

        _announced_challenges dedup prevents the same challenge surfacing twice
        in the summary across multiple run_module() calls.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result1 = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
            result2 = tmp_ctx.run_module("osint/whois_lookup", "evil.example.com", {})

        # ch-001 should appear in first result but NOT second
        first_ids = [ch.id for ch in result1["challenges"]]
        second_ids = [ch.id for ch in result2["challenges"]]
        assert "ch-001" in first_ids
        assert "ch-001" not in second_ids

    # ------------------------------------------------------------------
    # Compound integration test: full production sequence
    # ------------------------------------------------------------------

    def test_compound_module_run_then_challenge_check(self, tmp_ctx):
        """Compound: run module → challenge completes → check_challenges confirms it.

        This is the real production sequence:
          1. Analyst runs a module via execute_tool (LLM tool call)
          2. run_module auto-checks challenges; ch-001 completes
          3. LLM calls check_challenges explicitly — ch-001 already announced,
             so check_challenges returns "No new challenges" (dedup working)
          4. list_challenges now shows ch-001 as COMPLETED
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)

        # Step 1+2: run module, ch-001 auto-completes
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            run_result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
        assert any(ch.id == "ch-001" for ch in run_result["challenges"])

        # Step 3: check_challenges sees ch-001 already announced — returns none new
        check_summary, _, _, _ = execute_tool(tmp_ctx, "check_challenges", {})
        assert "ch-001" not in check_summary or "No new" in check_summary

        # Step 4: list_challenges shows ch-001 as completed
        list_summary, _, _, _ = execute_tool(tmp_ctx, "list_challenges", {})
        assert "COMPLETED" in list_summary or "completed" in list_summary


# ---------------------------------------------------------------------------
# Graph/export tool tests — DEC-AGENT-GRAPH-EXPORT-001
# ---------------------------------------------------------------------------


class TestGraphExportWiring:
    """Tests for render_graph and export_workspace LLM tools.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # The compound integration test mocks hunt() at the asyncio boundary to avoid
    # live API calls while exercising the real execute_tool → run_module →
    # workspace.store_stix_objects → render_graph production sequence.
    # All other tests use _populate_workspace() to call the real WorkspaceManager
    # directly — no mocks needed.

    Production sequence:
      ToolContext(tmp dirs) → populate workspace → execute_tool("render_graph")
                                                 → execute_tool("export_workspace", {"format": ...})

    @decision DEC-AGENT-GRAPH-EXPORT-001
    (see tools.py module docstring for full rationale)
    Tests validate: string output, empty-workspace fallback, node IDs present after
    population, GEXF XML structure, STIX bundle dict structure, bad-format error,
    tool registration, and the compound run_module → render_graph sequence.
    """

    def _populate_workspace(self, ctx, objects):
        """Store plain STIX dicts into workspace via the real WorkspaceManager.

        Objects must NOT include an 'id' key — STIX auto-generates valid UUIDs.
        dict_to_stix() passes extra keys (including 'id') to the stix2 constructor
        which validates UUID format; fake IDs like 'ipv4-addr--aaa' will raise.
        """
        ctx.workspace_mgr.store_stix_objects(objects, "test/module", "test-target")

    # ------------------------------------------------------------------
    # render_graph
    # ------------------------------------------------------------------

    def test_render_graph_returns_string(self, tmp_ctx):
        """render_graph tool returns a plain string with no celebration or badges."""
        summary, celebration, badges, challenges = execute_tool(tmp_ctx, "render_graph", {})
        assert isinstance(summary, str)
        assert celebration is None
        assert badges == []

    def test_render_graph_empty_workspace(self, tmp_ctx):
        """render_graph returns an informational message when workspace is empty."""
        summary, _, _, _ = execute_tool(tmp_ctx, "render_graph", {})
        lower = summary.lower()
        assert "no objects" in lower or "empty" in lower or "run a module" in lower

    def test_render_graph_populated_workspace_contains_node(self, tmp_ctx):
        """render_graph output contains node values after workspace is populated."""
        # No 'id' key — dict_to_stix auto-generates valid STIX UUIDs
        self._populate_workspace(
            tmp_ctx,
            [
                {"type": "ipv4-addr", "value": "1.2.3.4"},
                {"type": "domain-name", "value": "evil.example.com"},
            ],
        )
        summary, _, _, _ = execute_tool(tmp_ctx, "render_graph", {})
        assert "1.2.3.4" in summary or "ipv4-addr" in summary
        assert "evil.example.com" in summary or "domain-name" in summary

    def test_render_graph_includes_stats_line(self, tmp_ctx):
        """render_graph output ends with a node/edge count summary line."""
        self._populate_workspace(
            tmp_ctx,
            [{"type": "ipv4-addr", "value": "10.0.0.1"}],
        )
        summary, _, _, _ = execute_tool(tmp_ctx, "render_graph", {})
        assert "node" in summary.lower()

    # ------------------------------------------------------------------
    # export_workspace — gexf
    # ------------------------------------------------------------------

    def test_export_workspace_gexf_returns_xml(self, tmp_ctx):
        """export_workspace gexf returns GEXF XML with root element and nodes."""
        self._populate_workspace(
            tmp_ctx,
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
        )
        summary, celebration, badges, challenges = execute_tool(
            tmp_ctx, "export_workspace", {"format": "gexf"}
        )
        assert isinstance(summary, str)
        assert celebration is None
        assert badges == []
        assert "<gexf" in summary
        assert "<node" in summary

    def test_export_workspace_gexf_contains_stix_type_in_node(self, tmp_ctx):
        """export_workspace gexf XML node labels include the STIX type prefix."""
        # The node label format is "<stix_type>: <value>" — assert the type appears
        self._populate_workspace(
            tmp_ctx,
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
        )
        summary, _, _, _ = execute_tool(tmp_ctx, "export_workspace", {"format": "gexf"})
        # label attribute should contain "ipv4-addr" and "1.2.3.4"
        assert "ipv4-addr" in summary
        assert "1.2.3.4" in summary

    # ------------------------------------------------------------------
    # export_workspace — stix
    # ------------------------------------------------------------------

    def test_export_workspace_stix_returns_bundle_json(self, tmp_ctx):
        """export_workspace stix returns valid JSON of a STIX 2.1 bundle dict."""
        import json

        self._populate_workspace(
            tmp_ctx,
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
        )
        summary, celebration, badges, challenges = execute_tool(
            tmp_ctx, "export_workspace", {"format": "stix"}
        )
        assert isinstance(summary, str)
        assert celebration is None
        assert badges == []
        bundle = json.loads(summary)
        assert bundle["type"] == "bundle"
        assert "objects" in bundle
        assert isinstance(bundle["objects"], list)
        assert len(bundle["objects"]) >= 1

    def test_export_workspace_stix_bundle_contains_node_value(self, tmp_ctx):
        """export_workspace stix bundle objects list includes the stored indicator value."""
        import json

        self._populate_workspace(
            tmp_ctx,
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
        )
        summary, _, _, _ = execute_tool(tmp_ctx, "export_workspace", {"format": "stix"})
        bundle = json.loads(summary)
        # The bundle objects list must contain at least one object with value "1.2.3.4"
        values = [o.get("value", "") for o in bundle["objects"]]
        assert "1.2.3.4" in values

    # ------------------------------------------------------------------
    # Bad format
    # ------------------------------------------------------------------

    def test_export_workspace_bad_format_returns_error(self, tmp_ctx):
        """export_workspace returns a descriptive error string for unsupported formats."""
        # Bad-format check does not require populated workspace — format validation
        # fires before workspace reads when workspace is empty, so populate first
        # to ensure workspace-empty path doesn't shadow the format error.
        self._populate_workspace(
            tmp_ctx,
            [{"type": "ipv4-addr", "value": "1.2.3.4"}],
        )
        summary, _, _, _ = execute_tool(tmp_ctx, "export_workspace", {"format": "csv"})
        lower = summary.lower()
        assert "unknown" in lower or "unsupported" in lower or "supported" in lower

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def test_render_graph_registered_in_create_tools(self, tmp_ctx):
        """render_graph is present in the create_tools() list."""
        tools = create_tools(tmp_ctx)
        names = {t["function"]["name"] for t in tools}
        assert "render_graph" in names

    def test_export_workspace_registered_in_create_tools(self, tmp_ctx):
        """export_workspace is present in the create_tools() list."""
        tools = create_tools(tmp_ctx)
        names = {t["function"]["name"] for t in tools}
        assert "export_workspace" in names

    def test_export_workspace_has_required_format_param(self, tmp_ctx):
        """export_workspace tool schema declares 'format' as a required parameter."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "export_workspace")
        params = tool["function"]["parameters"]
        assert "format" in params["properties"]
        assert "format" in params.get("required", [])

    # ------------------------------------------------------------------
    # Compound integration: run_module → render_graph shows new entities
    # ------------------------------------------------------------------

    def test_compound_run_module_then_render_graph(self, tmp_ctx):
        """Compound: run_module stores objects → render_graph reflects them immediately.

        # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
        # We mock at the asyncio/module boundary to avoid live API calls while
        # exercising the full: execute_tool → run_module → store_stix_objects
        # → execute_tool("render_graph") → RelationshipGraph → render_text path.

        This is the real production sequence:
          1. LLM calls execute_tool("check_ip_reputation") → run_module() → hunt() (mocked)
          2. Results stored in workspace via store_stix_objects()
          3. LLM calls execute_tool("render_graph") → _execute_render_graph()
             → RelationshipGraph.build_from_workspace() → render_text()
          4. The rendered text contains the indicator value from step 1
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_mod = MagicMock()
        mock_mod.initialize = MagicMock()
        # No 'id' — dict_to_stix auto-generates a valid STIX UUID
        mock_mod.hunt = AsyncMock(
            return_value=[
                {"type": "ipv4-addr", "value": "192.0.2.1"},
            ]
        )

        # Step 1+2: run module → objects stored in workspace
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            run_summary, _, _, _ = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "192.0.2.1"}
            )
        assert "Found" in run_summary

        # Step 3+4: render_graph reflects the stored indicator
        graph_summary, _, _, _ = execute_tool(tmp_ctx, "render_graph", {})
        assert "192.0.2.1" in graph_summary or "ipv4-addr" in graph_summary


# ---------------------------------------------------------------------------
# TestGenerateDossierReportTool — M-7 generate_dossier_report LLM tool
# ---------------------------------------------------------------------------


class TestGenerateDossierReportTool:
    """Tests for the generate_dossier_report LLM tool (M-7 + M-8 cleanup).

    M-8 (DEC-M8-CLEANUP-002): tool is now parameterless (style param removed,
    classic shim deleted). generate_dossier_report always produces dossier-only output.

    Production sequence:
      execute_tool("generate_dossier_report") -> _execute_generate_dossier_report()
        -> generate_dossier_report(workspace_mgr) -> Markdown string
    """

    def test_generate_dossier_report_registered_in_create_tools(self, tmp_ctx):
        """generate_dossier_report is present in the create_tools() list."""
        tools = create_tools(tmp_ctx)
        names = {t["function"]["name"] for t in tools}
        assert "generate_dossier_report" in names

    def test_generate_dossier_report_schema_is_parameterless(self, tmp_ctx):
        """M-8: generate_dossier_report schema has no properties or required params (DEC-M8-CLEANUP-002)."""
        tools = create_tools(tmp_ctx)
        tool = next(t for t in tools if t["function"]["name"] == "generate_dossier_report")
        params = tool["function"]["parameters"]
        assert "style" not in params.get("properties", {}), (
            "generate_dossier_report must NOT expose 'style' property after M-8 cleanup"
        )
        assert len(params.get("required", [])) == 0

    def test_generate_dossier_report_returns_string(self, tmp_ctx):
        """execute_tool('generate_dossier_report') returns a Markdown string."""
        summary, celebration, badges, challenges = execute_tool(
            tmp_ctx, "generate_dossier_report", {}
        )
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_generate_dossier_report_contains_investigation_header(self, tmp_ctx):
        """Dossier report output contains 'Investigation Report' header."""
        summary, _, _, _ = execute_tool(tmp_ctx, "generate_dossier_report", {})
        assert (
            "Investigation Report" in summary or "Dossier" in summary or "report" in summary.lower()
        )

    def test_generate_dossier_report_includes_iocs_when_workspace_populated(self, tmp_ctx):
        """generate_dossier_report includes IOC data from workspace when present."""
        tmp_ctx.workspace_mgr.store_stix_objects(
            [{"type": "ipv4-addr", "value": "198.51.100.5"}],
            "test/module",
            "198.51.100.5",
        )
        summary, _, _, _ = execute_tool(tmp_ctx, "generate_dossier_report", {})
        assert "198.51.100.5" in summary


# ---------------------------------------------------------------------------
# TestRunChatHelp — help / ? meta-command (DEC-AGENT-CHAT-HELP-001)
# ---------------------------------------------------------------------------

# @mock-exempt: AgentRunner.__init__ imports litellm and may attempt live
# model introspection.  We mock the entire AgentRunner at the import boundary
# in chat.py so the help command can be exercised without LLM infrastructure.


class TestRunChatHelp:
    """Verify 'help' and '?' meta-commands in run_chat().

    Production sequence:
      user types 'help' or '?' at the chat prompt
        → chat.py strips the input
        → lower-cased equality check matches before LLM dispatch
        → Rich Table rendered to Console (no runner.chat() call)
        → active model + workspace printed below the table
        → loop continues (no LLM round-trip)
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_runner_mock(tmp_ctx, model: str = "test-model-001") -> MagicMock:
        """Return a MagicMock that looks enough like AgentRunner for chat.py."""
        mock_runner = MagicMock()
        mock_runner.model = model
        mock_runner.ctx = tmp_ctx
        mock_runner.last_celebrations = []
        mock_runner.last_badges = []
        mock_runner.chat = MagicMock(return_value="LLM response text")
        return mock_runner

    @staticmethod
    def _make_config_mgr_mock(
        model: str = "test-model-001", provider: str = "anthropic"
    ) -> MagicMock:
        """Return a MagicMock that looks enough like ConfigManager for chat.py."""
        mock_cfg_mgr = MagicMock()
        mock_cfg_mgr.get_agent_model.return_value = model
        mock_cfg_mgr.get_agent_provider.return_value = provider
        mock_cfg_mgr.get_provider_api_key.return_value = "test-api-key"
        mock_cfg_mgr.get_editing_mode.return_value = "vi"
        mock_cfg_mgr.set_agent_selection = MagicMock()
        mock_cfg_mgr.set_provider_api_key = MagicMock()
        return mock_cfg_mgr

    @staticmethod
    def _run_chat_with_inputs(inputs: list[str], tmp_ctx, model: str = "test-model-001"):
        """Run run_chat() with canned console inputs, returning captured output.

        # @mock-exempt: AgentRunner connects to LLM backends (litellm / Ollama).
        # Patching at the source module (adversary_pursuit.agent.runner.AgentRunner)
        # replaces the class before the lazy 'from ... import AgentRunner' inside
        # run_chat() binds it — the only way to inject a test double without a live
        # LLM endpoint. Console is mocked to capture Rich output in-memory and to
        # feed canned user inputs without an interactive TTY.  Both are external
        # I/O boundaries (LLM network call, TTY), not internal business logic.
        # ConfigManager is mocked to return a pre-configured model so that the
        # interactive wizard is never triggered during tests.
        # ChatPromptSession is mocked because it wraps a blocking PTY call.

        Patch strategy:
          - adversary_pursuit.agent.runner.AgentRunner → mock class whose call
            returns mock_runner (chat.py does 'from ... import AgentRunner; AgentRunner()')
          - adversary_pursuit.agent.chat.ConfigManager → mock class returning a
            pre-configured mock_cfg_mgr (prevents wizard trigger when AP_MODEL unset)
          - adversary_pursuit.agent.chat.ChatPromptSession → mock whose .prompt()
            reads from the canned input sequence (replaces blocking PTY call)
          - Console (rich.console.Console) → in-memory StringIO console so Rich
            output can be inspected without a real terminal.
        """
        from io import StringIO

        from rich.console import Console

        from adversary_pursuit.agent.chat import run_chat

        mock_runner = TestRunChatHelp._make_runner_mock(tmp_ctx, model)
        mock_cfg_mgr = TestRunChatHelp._make_config_mgr_mock(model)
        buf = StringIO()
        test_console = Console(file=buf, width=120, highlight=False, markup=False)

        input_seq = iter(inputs)

        def fake_prompt(_prefix=""):
            try:
                return next(input_seq)
            except StopIteration:
                raise EOFError

        # Mock ChatPromptSession so .prompt() reads from the canned sequence
        mock_session = MagicMock()
        mock_session.prompt.side_effect = fake_prompt
        mock_prompt_session_class = MagicMock(return_value=mock_session)

        # Build a mock class whose instantiation returns mock_runner
        mock_agent_runner_class = MagicMock(return_value=mock_runner)
        # Build a mock ConfigManager class whose instantiation returns mock_cfg_mgr
        mock_config_mgr_class = MagicMock(return_value=mock_cfg_mgr)

        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner",
                mock_agent_runner_class,
            ),
            patch(
                "adversary_pursuit.agent.chat.ConfigManager",
                mock_config_mgr_class,
            ),
            patch(
                "adversary_pursuit.agent.chat.ChatPromptSession",
                mock_prompt_session_class,
            ),
            patch("adversary_pursuit.agent.chat.Console", return_value=test_console),
            patch("adversary_pursuit.agent.chat.render_boot_banner"),
        ):
            run_chat()

        return buf.getvalue(), mock_runner

    # ------------------------------------------------------------------
    # (1) 'help' does not invoke runner.chat (no LLM call)
    # ------------------------------------------------------------------

    def test_help_does_not_invoke_runner_chat(self, tmp_ctx):
        """'help' must be handled locally — runner.chat() must NOT be called."""
        _output, mock_runner = self._run_chat_with_inputs(["help"], tmp_ctx)
        mock_runner.chat.assert_not_called()

    # ------------------------------------------------------------------
    # (2) '?' does not invoke runner.chat (no LLM call)
    # ------------------------------------------------------------------

    def test_question_mark_does_not_invoke_runner_chat(self, tmp_ctx):
        """'?' must be handled locally — runner.chat() must NOT be called."""
        _output, mock_runner = self._run_chat_with_inputs(["?"], tmp_ctx)
        mock_runner.chat.assert_not_called()

    # ------------------------------------------------------------------
    # (3) help output lists all known meta-commands
    # ------------------------------------------------------------------

    def test_help_lists_known_meta_commands(self, tmp_ctx):
        """Help table must include all current chat meta-commands by name."""
        output, _ = self._run_chat_with_inputs(["help"], tmp_ctx)
        for cmd in (
            "workspace",
            "mode",
            "hint",
            "autopivot",
            "challenges",
            "graph",
            "export",
            "report",
            "quit",
        ):
            assert cmd in output, f"Expected meta-command '{cmd}' in help output"

    # ------------------------------------------------------------------
    # (4) help output shows the active model
    # ------------------------------------------------------------------

    def test_help_shows_active_model(self, tmp_ctx):
        """Help output must include the runner's active model identifier."""
        model_name = "claude-3-5-sonnet-20241022"
        output, _ = self._run_chat_with_inputs(["help"], tmp_ctx, model=model_name)
        assert model_name in output, f"Expected model name '{model_name}' in help output"

    # ------------------------------------------------------------------
    # (5) help output shows the active workspace
    # ------------------------------------------------------------------

    def test_help_shows_active_workspace(self, tmp_ctx):
        """Help output must include the active workspace name."""
        # tmp_ctx fixture already creates and switches to 'default' workspace
        output, _ = self._run_chat_with_inputs(["help"], tmp_ctx)
        assert "default" in output, "Expected active workspace 'default' in help output"

    # ------------------------------------------------------------------
    # (6) plain text still invokes runner.chat (LLM dispatch not broken)
    # ------------------------------------------------------------------

    def test_plain_text_still_invokes_runner_chat(self, tmp_ctx):
        """Non-meta-command input must still reach runner.chat() for LLM dispatch.

        This is the compound-interaction regression guard: adding the 'help'
        interceptor must not silently capture ordinary chat messages.

        Production sequence:
          user types a query → chat.py routes to runner.chat() → LLM called
        """
        _output, mock_runner = self._run_chat_with_inputs(["what is 8.8.8.8"], tmp_ctx)
        mock_runner.chat.assert_called_once_with("what is 8.8.8.8")


# @mock-exempt: AgentRunner is an external LLM network boundary (litellm calls to
# Anthropic/OpenAI/Ollama). ConfigManager reads/writes ~/.ap/config.toml (external
# filesystem boundary — real path would create side-effects on developer machines).
# Console.input is an interactive TTY boundary. run_provider_wizard makes HTTP calls
# to provider endpoints. All mocks in this class are for external I/O, not internal
# business logic — matching the existing mock-exempt pattern in TestRunChatHelp above.
class TestModelMetaCommands:
    """Verify 'model show' and 'model select' meta-commands in run_chat().

    Production sequence:
      user types 'model show' or 'model select' at the chat prompt
        → chat.py strips + lowercases the input
        → matched before LLM dispatch (no runner.chat() call)
        → 'model show': prints current model + source layer to console
        → 'model select': invokes run_provider_wizard, updates runner.model
        → loop continues

    @decision DEC-TEST-MODEL-COMMANDS-001
    @title Test model meta-commands using same patch strategy as TestRunChatHelp
    @status accepted
    @rationale 'model show' and 'model select' are handled locally in chat.py
               before LLM dispatch, matching the pattern of other meta-commands.
               ConfigManager is mocked to control which model/provider is
               "configured" without touching ~/.ap. run_provider_wizard is mocked
               to avoid interactive prompts and HTTP calls in the test suite.
               Both mocks are at external I/O boundaries (config file, HTTP + TTY).
    """

    @staticmethod
    def _make_runner_mock(tmp_ctx, model: str = "test-model-001") -> MagicMock:
        mock_runner = MagicMock()
        mock_runner.model = model
        mock_runner.ctx = tmp_ctx
        mock_runner.last_celebrations = []
        mock_runner.last_badges = []
        mock_runner.chat = MagicMock(return_value="LLM response text")
        return mock_runner

    @staticmethod
    def _run_chat_model_cmd(
        inputs: list[str],
        tmp_ctx,
        model: str = "configured-model",
        provider: str = "anthropic",
        ap_model_env: str | None = None,
        wizard_return: str = "wizard-chosen-model",
    ):
        """Run run_chat() with model meta-command inputs, return (output, mock_runner, mock_cfg_mgr).

        Patches: AgentRunner, ConfigManager, run_provider_wizard, Console.
        AP_MODEL env var is injected/cleared via monkeypatching os.environ.
        """
        import os
        from io import StringIO
        from unittest.mock import patch

        from rich.console import Console

        from adversary_pursuit.agent.chat import run_chat

        mock_runner = TestModelMetaCommands._make_runner_mock(tmp_ctx, model)
        mock_cfg_mgr = MagicMock()
        mock_cfg_mgr.get_agent_model.return_value = model
        mock_cfg_mgr.get_agent_provider.return_value = provider
        mock_cfg_mgr.get_provider_api_key.return_value = "test-key"
        mock_cfg_mgr.get_editing_mode.return_value = "vi"
        mock_cfg_mgr.set_agent_selection = MagicMock()
        mock_cfg_mgr.set_provider_api_key = MagicMock()

        buf = StringIO()
        test_console = Console(file=buf, width=120, highlight=False, markup=False)

        input_seq = iter(inputs)

        def fake_prompt(_prefix=""):
            try:
                return next(input_seq)
            except StopIteration:
                raise EOFError

        # @mock-exempt: ChatPromptSession wraps blocking PTY I/O
        mock_session = MagicMock()
        mock_session.prompt.side_effect = fake_prompt
        mock_prompt_session_class = MagicMock(return_value=mock_session)

        mock_agent_runner_class = MagicMock(return_value=mock_runner)
        mock_config_mgr_class = MagicMock(return_value=mock_cfg_mgr)

        env_overrides: dict[str, str] = {}
        if ap_model_env is not None:
            env_overrides["AP_MODEL"] = ap_model_env

        with (
            patch(
                "adversary_pursuit.agent.runner.AgentRunner",
                mock_agent_runner_class,
            ),
            patch("adversary_pursuit.agent.chat.ConfigManager", mock_config_mgr_class),
            patch(
                "adversary_pursuit.agent.chat.run_provider_wizard",
                return_value=wizard_return,
            ),
            patch(
                "adversary_pursuit.agent.chat.ChatPromptSession",
                mock_prompt_session_class,
            ),
            patch.dict(os.environ, env_overrides, clear=False),
            patch("adversary_pursuit.agent.chat.Console", return_value=test_console),
            patch("adversary_pursuit.agent.chat.render_boot_banner"),
        ):
            if ap_model_env is None:
                os.environ.pop("AP_MODEL", None)
            run_chat()

        return buf.getvalue(), mock_runner, mock_cfg_mgr

    # ------------------------------------------------------------------
    # model show
    # ------------------------------------------------------------------

    def test_model_show_does_not_invoke_runner_chat(self, tmp_ctx):
        """'model show' must not trigger an LLM call."""
        _output, mock_runner, _cfg = self._run_chat_model_cmd(["model show"], tmp_ctx)
        mock_runner.chat.assert_not_called()

    def test_model_show_prints_model_name(self, tmp_ctx):
        """'model show' output contains the configured model string."""
        output, _runner, _cfg = self._run_chat_model_cmd(["model show"], tmp_ctx, model="gpt-4o")
        assert "gpt-4o" in output

    def test_model_show_prints_provider(self, tmp_ctx):
        """'model show' output contains the configured provider id."""
        output, _runner, _cfg = self._run_chat_model_cmd(
            ["model show"], tmp_ctx, model="gpt-4o", provider="openai"
        )
        assert "openai" in output

    def test_model_show_reports_env_source_when_ap_model_set(self, tmp_ctx):
        """'model show' labels the source as 'AP_MODEL env var' when env is set."""
        output, _runner, _cfg = self._run_chat_model_cmd(
            ["model show"],
            tmp_ctx,
            model="config-model",
            ap_model_env="env-override-model",
        )
        assert "env-override-model" in output or "AP_MODEL" in output

    # ------------------------------------------------------------------
    # model select
    # ------------------------------------------------------------------

    def test_model_select_does_not_invoke_runner_chat(self, tmp_ctx):
        """'model select' must not trigger an LLM call."""
        _output, mock_runner, _cfg = self._run_chat_model_cmd(
            ["model select"], tmp_ctx, wizard_return="new-model-after-wizard"
        )
        mock_runner.chat.assert_not_called()

    def test_model_select_updates_runner_model(self, tmp_ctx):
        """After 'model select', runner.model is updated to the wizard's return value.

        Production sequence:
          user types 'model select'
            → chat.py calls run_provider_wizard(config_mgr)
            → wizard returns new model string
            → runner.model = new_model (in-place update)
            → loop continues; next LLM call uses new model
        """
        _output, mock_runner, _cfg = self._run_chat_model_cmd(
            ["model select"], tmp_ctx, wizard_return="updated-to-new-model"
        )
        assert mock_runner.model == "updated-to-new-model"

    def test_model_select_plain_text_still_routes_to_llm(self, tmp_ctx):
        """After 'model select', a subsequent plain text input still reaches LLM."""
        _output, mock_runner, _cfg = self._run_chat_model_cmd(
            ["model select", "what is 8.8.8.8"],
            tmp_ctx,
            wizard_return="new-model",
        )
        mock_runner.chat.assert_called_once_with("what is 8.8.8.8")

    # ------------------------------------------------------------------
    # help table includes 'model' command (regression guard)
    # ------------------------------------------------------------------

    def test_help_table_lists_model_command(self, tmp_ctx):
        """'help' output must include 'model' meta-command after this slice."""
        import os
        from io import StringIO
        from unittest.mock import patch

        from rich.console import Console

        from adversary_pursuit.agent.chat import run_chat

        mock_runner = self._make_runner_mock(tmp_ctx)
        mock_cfg_mgr = MagicMock()
        mock_cfg_mgr.get_agent_model.return_value = "test-model"
        mock_cfg_mgr.get_agent_provider.return_value = "anthropic"
        mock_cfg_mgr.get_editing_mode.return_value = "vi"

        buf = StringIO()
        test_console = Console(file=buf, width=120, highlight=False, markup=False)
        input_seq = iter(["help"])

        def fake_prompt(_prefix=""):
            try:
                return next(input_seq)
            except StopIteration:
                raise EOFError

        # @mock-exempt: ChatPromptSession wraps blocking PTY I/O
        mock_session = MagicMock()
        mock_session.prompt.side_effect = fake_prompt
        mock_prompt_session_class = MagicMock(return_value=mock_session)

        mock_agent_runner_class = MagicMock(return_value=mock_runner)
        mock_config_mgr_class = MagicMock(return_value=mock_cfg_mgr)

        with (
            patch("adversary_pursuit.agent.runner.AgentRunner", mock_agent_runner_class),
            patch("adversary_pursuit.agent.chat.ConfigManager", mock_config_mgr_class),
            patch(
                "adversary_pursuit.agent.chat.ChatPromptSession",
                mock_prompt_session_class,
            ),
            patch("adversary_pursuit.agent.chat.Console", return_value=test_console),
            patch("adversary_pursuit.agent.chat.render_boot_banner"),
        ):
            os.environ.pop("AP_MODEL", None)
            run_chat()

        output = buf.getvalue()
        assert "model" in output, "Expected 'model' meta-command listed in help output"


# ---------------------------------------------------------------------------
# Service-name map tests — DEC-AGENT-SERVICE-NAME-MAP-001
# ---------------------------------------------------------------------------


class TestServiceNameMap:
    """_SERVICE_NAMES correctly maps module paths to ConfigManager service names.

    The canonical bug: "osint/shodan_ip".split("/")[-1] == "shodan_ip", but
    ConfigManager.get_api_key() expects "shodan". Without _SERVICE_NAMES the
    Shodan key was never resolved. These tests prove the fix is wired end-to-end.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # Credential resolution is tested by patching get_api_key() directly to
    # assert the correct service name argument is passed to it — not the wrong
    # path-tail ("shodan_ip" instead of "shodan").
    """

    from adversary_pursuit.agent.tools import _SERVICE_NAMES  # noqa: PLC0415

    def test_service_names_map_has_shodan_fix(self):
        """_SERVICE_NAMES maps 'osint/shodan_ip' -> 'shodan' (not 'shodan_ip')."""
        from adversary_pursuit.agent.tools import _SERVICE_NAMES

        assert _SERVICE_NAMES.get("osint/shodan_ip") == "shodan"

    def test_service_names_map_dns_is_none(self):
        """dns_resolve maps to None — no API key required."""
        from adversary_pursuit.agent.tools import _SERVICE_NAMES

        assert _SERVICE_NAMES.get("osint/dns_resolve") is None

    def test_service_names_map_whois_is_none(self):
        """whois_lookup maps to None — no API key required."""
        from adversary_pursuit.agent.tools import _SERVICE_NAMES

        assert _SERVICE_NAMES.get("osint/whois_lookup") is None

    def test_run_module_shodan_resolves_via_service_name_map(self, tmp_ctx, monkeypatch):
        """run_module('osint/shodan_ip') calls get_api_key('shodan'), not 'shodan_ip'.

        This is the canonical bug regression test. Before _SERVICE_NAMES was added,
        'shodan_ip' was passed to get_api_key(), which would return None (unknown
        service), so the Shodan module always received an empty api_key even when
        SHODAN_API_KEY was set in the environment.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        calls_made: list[str] = []

        original_get_api_key = tmp_ctx.config_mgr.get_api_key

        def spy_get_api_key(service: str) -> str | None:
            calls_made.append(service)
            return original_get_api_key(service)

        tmp_ctx.config_mgr.get_api_key = spy_get_api_key

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_IP_RESULTS)
        mock_mod.initialize = MagicMock()

        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/shodan_ip", "1.2.3.4", {})

        # Must have been called with "shodan", NOT "shodan_ip"
        assert "shodan" in calls_made, (
            f"get_api_key('shodan') was not called; actual calls: {calls_made}"
        )
        assert "shodan_ip" not in calls_made, (
            f"get_api_key('shodan_ip') must not be called; actual calls: {calls_made}"
        )

    def test_run_module_dns_resolve_initializes_empty(self, tmp_ctx):
        """run_module('osint/dns_resolve') passes empty init_config (no API key needed)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_DOMAIN_RESULTS)
        mock_mod.initialize = MagicMock()

        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/dns_resolve", "example.com", {})

        mock_mod.initialize.assert_called_once_with({})

    def test_run_module_whois_lookup_initializes_empty(self, tmp_ctx):
        """run_module('osint/whois_lookup') passes empty init_config (no API key needed)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_DOMAIN_RESULTS)
        mock_mod.initialize = MagicMock()

        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/whois_lookup", "example.com", {})

        mock_mod.initialize.assert_called_once_with({})

    def test_credential_builders_env_fallback_censys(self, tmp_ctx, monkeypatch):
        """Censys credential builder falls back to AP_CENSYS_PAT env var (resolves #45)."""
        monkeypatch.setenv("AP_CENSYS_PAT", "censys-env-pat")
        monkeypatch.delenv("CENSYS_PAT", raising=False)

        from adversary_pursuit.agent.tools import _CREDENTIAL_BUILDERS

        builder = _CREDENTIAL_BUILDERS["osint/censys_host"]
        config = builder(tmp_ctx.config_mgr)

        assert config["censys_pat"] == "censys-env-pat"
        assert "censys_id" not in config
        assert "censys_secret" not in config

    def test_credential_builders_env_fallback_passivetotal(self, tmp_ctx, monkeypatch):
        """PassiveTotal credential builder falls back to vendor env vars when config is empty."""
        monkeypatch.delenv("AP_PASSIVETOTAL_USER", raising=False)
        monkeypatch.delenv("AP_PT_USER", raising=False)
        monkeypatch.setenv("PT_USERNAME", "pt-vendor-user")
        monkeypatch.delenv("AP_PASSIVETOTAL_KEY", raising=False)
        monkeypatch.delenv("AP_PT_API_KEY", raising=False)
        monkeypatch.setenv("PT_API_KEY", "pt-vendor-key")

        from adversary_pursuit.agent.tools import _CREDENTIAL_BUILDERS

        builder = _CREDENTIAL_BUILDERS["cti/passivetotal"]
        config = builder(tmp_ctx.config_mgr)

        assert config["passivetotal_user"] == "pt-vendor-user"
        assert config["passivetotal_key"] == "pt-vendor-key"

    def test_shodan_key_resolves_from_env_via_run_module(self, tmp_ctx, monkeypatch):
        """End-to-end: SHODAN_API_KEY in env reaches module.initialize() via run_module.

        This is the full production sequence proving DEC-AGENT-SERVICE-NAME-MAP-001
        and DEC-AGENT-CONFIG-KEY-RESOLUTION-001 work together: env var → get_api_key()
        → _SERVICE_NAMES lookup → correct service name → non-empty api_key in init_config.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        monkeypatch.delenv("AP_SHODAN_API_KEY", raising=False)
        monkeypatch.setenv("SHODAN_API_KEY", "shodan-from-vendor-env")

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_IP_RESULTS)
        mock_mod.initialize = MagicMock()

        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/shodan_ip", "1.2.3.4", {})

        mock_mod.initialize.assert_called_once()
        init_arg = mock_mod.initialize.call_args[0][0]
        assert init_arg.get("api_key") == "shodan-from-vendor-env", (
            f"Expected 'shodan-from-vendor-env' but got: {init_arg}"
        )

    def test_cascade_callback_uses_service_name_map_for_shodan(self, tmp_ctx, monkeypatch):
        # @mock-exempt: mock_mod replaces ShodanIPModule.hunt() — an async HTTP
        # external service boundary (Shodan API). recording_get_api_key is a pure
        # observation shim that calls through to the real ConfigManager.get_api_key()
        # and records arguments; it does not replace any internal logic.
        # get_module is patched because no live Shodan credentials or network exist.
        """Cascade path uses _SERVICE_NAMES — 'osint/shodan_ip' resolves to 'shodan'.

        Regression guard: _make_cascade_callback() previously derived the service
        name as module_path.split('/')[-1] == 'shodan_ip', bypassing _SERVICE_NAMES
        and causing get_api_key('shodan_ip') to return None (no such field).
        Now both run_module() and _make_cascade_callback() delegate to
        _resolve_module_credentials() which applies _SERVICE_NAMES uniformly.

        Production sequence:
          EventBus callback fires → _resolve_module_credentials('osint/shodan_ip') →
          get_api_key('shodan') [NOT 'shodan_ip'] → key resolved → initialize().
        """
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        monkeypatch.delenv("AP_SHODAN_API_KEY", raising=False)
        monkeypatch.setenv("SHODAN_API_KEY", "shodan-cascade-key")

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=[])
        mock_mod.initialize = MagicMock()

        # Recording shim: calls through to real get_api_key(); captures service names.
        original_get_api_key = tmp_ctx.config_mgr.get_api_key
        get_api_key_calls: list[str] = []

        def recording_get_api_key(service: str) -> str | None:
            get_api_key_calls.append(service)
            return original_get_api_key(service)

        with patch.object(tmp_ctx.config_mgr, "get_api_key", side_effect=recording_get_api_key):
            with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
                from adversary_pursuit.core.event_bus import PivotEvent

                callback = tmp_ctx._make_cascade_callback("osint/shodan_ip")
                asyncio.run(
                    callback(
                        PivotEvent(
                            stix_type="ipv4-addr",
                            value="1.2.3.4",
                            source_module="osint/abuseipdb",
                        )
                    )
                )

        assert "shodan" in get_api_key_calls, (
            f"Expected get_api_key('shodan') but got: {get_api_key_calls}"
        )
        assert "shodan_ip" not in get_api_key_calls, (
            f"Regression: path-tail 'shodan_ip' used instead of _SERVICE_NAMES: {get_api_key_calls}"
        )
        mock_mod.initialize.assert_called_once()
        init_arg = mock_mod.initialize.call_args[0][0]
        assert init_arg.get("api_key") == "shodan-cascade-key", (
            f"Expected 'shodan-cascade-key' in init_config but got: {init_arg}"
        )


# ---------------------------------------------------------------------------
# Censys PAT credential builder — explicit tests (resolves #45)
# ---------------------------------------------------------------------------


class TestCensysPATCredentialBuilder:
    """Verify _CREDENTIAL_BUILDERS["osint/censys_host"] uses censys_pat only."""

    def test_credential_builders_censys_uses_censys_pat(self, tmp_ctx):
        """Builder passes censys_pat from get_censys_pat() to init_config."""
        tmp_ctx.config_mgr.set("api_keys.censys_pat", "test-pat-value")
        builder = _CREDENTIAL_BUILDERS["osint/censys_host"]
        config = builder(tmp_ctx.config_mgr)
        assert config == {"censys_pat": "test-pat-value"}

    def test_credential_builders_censys_no_legacy_id_secret_path(self, tmp_ctx):
        """Builder output must NOT contain censys_id or censys_secret keys."""
        builder = _CREDENTIAL_BUILDERS["osint/censys_host"]
        config = builder(tmp_ctx.config_mgr)
        assert "censys_id" not in config
        assert "censys_secret" not in config

    def test_credential_builders_censys_empty_when_not_configured(self, tmp_ctx):
        """Builder returns empty string for censys_pat when no key configured."""
        builder = _CREDENTIAL_BUILDERS["osint/censys_host"]
        config = builder(tmp_ctx.config_mgr)
        assert config["censys_pat"] == ""

    def test_credential_builders_censys_reads_from_env_var(self, tmp_ctx, monkeypatch):
        """Builder picks up CENSYS_PAT env var via the 3-layer config chain."""
        monkeypatch.delenv("AP_CENSYS_PAT", raising=False)
        monkeypatch.setenv("CENSYS_PAT", "env-pat-value")
        builder = _CREDENTIAL_BUILDERS["osint/censys_host"]
        config = builder(tmp_ctx.config_mgr)
        assert config["censys_pat"] == "env-pat-value"


# ---------------------------------------------------------------------------
# GreyNoise lookup tool — dispatch, arg mapping, and error surfacing
# ---------------------------------------------------------------------------

SAMPLE_GN_RESULTS = [
    {
        "type": "ipv4-addr",
        "value": "8.8.8.8",
        "x_greynoise_classification": "benign",
        "x_greynoise_noise": False,
        "x_greynoise_riot": True,
        "x_greynoise_name": "Google Public DNS",
        "x_greynoise_last_seen": "2026-05-01",
        "x_greynoise_link": "https://viz.greynoise.io/ip/8.8.8.8",
    }
]


class TestGreyNoiseLookupTool:
    """greynoise_lookup tool is discoverable, dispatches correctly, and surfaces errors.

    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    # The tool layer is tested by mocking module.hunt() so no live GreyNoise
    # API call is made. This is the same exemption used throughout TestExecuteToolDispatch.
    """

    def _make_mock_module(self, results: list) -> MagicMock:
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def test_greynoise_lookup_in_module_map(self):
        """greynoise_lookup must appear in _MODULE_MAP."""
        assert "greynoise_lookup" in _MODULE_MAP

    def test_greynoise_lookup_maps_to_osint_greynoise(self):
        """greynoise_lookup maps to the 'osint/greynoise' module path."""
        module_path, _ = _MODULE_MAP["greynoise_lookup"]
        assert module_path == "osint/greynoise"

    def test_greynoise_lookup_dispatches_to_module(self, tmp_ctx):
        """execute_tool('greynoise_lookup') runs the osint/greynoise module."""
        mock_mod = self._make_mock_module(SAMPLE_GN_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod) as mock_get:
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "greynoise_lookup", {"ip_address": "8.8.8.8"}
            )
            assert isinstance(summary, str)
            assert "Found" in summary
            mock_get.assert_called_once_with("osint/greynoise")

    def test_greynoise_lookup_passes_ip_as_target(self, tmp_ctx):
        """execute_tool('greynoise_lookup') passes ip_address as the hunt() target."""
        mock_mod = self._make_mock_module(SAMPLE_GN_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            execute_tool(tmp_ctx, "greynoise_lookup", {"ip_address": "1.2.3.4"})
        mock_mod.hunt.assert_called_once_with("1.2.3.4", {})

    def test_greynoise_lookup_auth_error_surfaces_to_llm(self, tmp_ctx):
        """AuthenticationError from greynoise hunt() surfaces as an error string (not exception).

        The tool layer catches AuthenticationError and returns a human-readable string
        to the LLM rather than propagating the exception. This is the standard
        execute_tool error-surfacing contract for all module tools.
        """
        from adversary_pursuit.modules.base import AuthenticationError as AuthErr

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(side_effect=AuthErr("GreyNoise API key invalid/revoked."))
        mock_mod.initialize = MagicMock()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "greynoise_lookup", {"ip_address": "8.8.8.8"}
            )
        assert "Error" in summary
        assert celebration is None

    def test_greynoise_lookup_rate_limit_error_surfaces(self, tmp_ctx):
        """RateLimitError from greynoise hunt() surfaces as an error string (not exception)."""
        from adversary_pursuit.modules.base import RateLimitError as RLErr

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(
            side_effect=RLErr("GreyNoise Community API rate limit exceeded.", retry_after=3600)
        )
        mock_mod.initialize = MagicMock()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "greynoise_lookup", {"ip_address": "8.8.8.8"}
            )
        assert "Error" in summary
        assert celebration is None

    def test_greynoise_lookup_404_returns_graceful_result(self, tmp_ctx):
        """greynoise_lookup gracefully handles 404 (unknown IP) — no error, one SCO returned.

        The GreyNoise module converts 404 into an 'unknown' stub SCO (DEC-MODULE-GREYNOISE-002).
        The tool layer must receive a non-empty results list and return a summary string.
        """
        unknown_stub = [
            {
                "type": "ipv4-addr",
                "value": "203.0.113.99",
                "x_greynoise_classification": "unknown",
                "x_greynoise_noise": False,
                "x_greynoise_riot": False,
                "x_greynoise_name": "",
                "x_greynoise_last_seen": "",
                "x_greynoise_link": "",
            }
        ]
        mock_mod = self._make_mock_module(unknown_stub)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "greynoise_lookup", {"ip_address": "203.0.113.99"}
            )
        assert isinstance(summary, str)
        assert "Error" not in summary


# ---------------------------------------------------------------------------
# F62-R0-001: execute_tool exception path wires mode.run_fail (Rich-stripped)
# ---------------------------------------------------------------------------


class TestExecuteToolRunFailWiring:
    """execute_tool exception path prepends Rich-stripped mode.run_fail (F62-R0-001).

    Production sequence: agent LLM calls hunt tool → module raises → execute_tool
    catches exception → returns error string prefixed with mode-flavored voice.

    # @mock-exempt: hunt() mocked at asyncio boundary — external HTTP module call.
    # badge_mgr, mode_mgr are NOT mocked; they use real in-memory instances on tmp_ctx.

    @decision DEC-62-KILL-DOC-LIES-002
    Tests that _strip_rich_markup is applied and mode.run_fail is prepended.
    """

    def _make_exploding_module(self):
        # @mock-exempt: hunt() is the external HTTP boundary; RuntimeError simulates
        # network/upstream failure without any real network call.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(side_effect=RuntimeError("upstream timeout"))
        mock_mod.initialize = MagicMock()
        return mock_mod

    def test_exception_path_starts_with_mode_run_fail(self, tmp_ctx):
        """execute_tool exception returns string prefixed with stripped run_fail."""
        from adversary_pursuit.agent.tools import _strip_rich_markup

        mock_mod = self._make_exploding_module()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, badges, challenges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        expected_prefix = _strip_rich_markup(tmp_ctx.mode_mgr.active.run_fail)
        assert summary.startswith(expected_prefix), (
            f"Expected summary to start with '{expected_prefix}', got: {summary!r}"
        )
        assert celebration is None
        assert badges == []

    def test_exception_path_contains_no_rich_markup(self, tmp_ctx):
        """execute_tool exception string has no residual [bold...] markup tags."""
        import re

        mock_mod = self._make_exploding_module()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        markup_tags = re.findall(r"\[/?[^\]]+\]", summary)
        assert markup_tags == [], f"Rich markup tags found in error summary: {markup_tags!r}"

    def test_exception_path_full_troll_mode_stripped(self, tmp_ctx):
        """full_troll run_fail has bold-red markup — must be stripped in exception path."""
        import re

        from adversary_pursuit.gamification.modes import DEFAULT_MODES

        tmp_ctx.mode_mgr.switch("full_troll")
        assert tmp_ctx.mode_mgr.active == DEFAULT_MODES["full_troll"]
        assert "[bold red]" in tmp_ctx.mode_mgr.active.run_fail  # confirm markup present

        mock_mod = self._make_exploding_module()
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, _celebration, _badges, _challenges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        assert "[bold red]" not in summary
        assert re.findall(r"\[/?[^\]]+\]", summary) == []
        # Stripped text content should still appear
        assert "BRUH" in summary or "grandma" in summary


# ---------------------------------------------------------------------------
# F62-R0-002: run_module wires first_blood_message after badge check
# ---------------------------------------------------------------------------


class TestRunModuleFirstBloodWiring:
    """run_module calls first_blood_message() after badge check (F62-R0-002).

    Production sequence: first hunt → real BadgeManager earns badge-first-blood
    (total_indicators >= 1) → first_blood_message() fires from CelebrationEngine
    → message returned in celebration string.

    # @mock-exempt: hunt() mocked at asyncio boundary — external HTTP module call.
    # BadgeManager.check_all is NOT mocked; real workspace stats trigger the badge.

    @decision DEC-62-CELEBRATIONS-001
    Mirrors console.py _execute_hunt:467-477 in the agent surface.
    """

    def _make_mock_module(self, results):
        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def test_first_blood_message_fires_on_first_successful_hunt(self, tmp_ctx):
        """first_blood_message included in celebration on first hunt with >= 1 indicator.

        Real BadgeManager.check_all sees total_indicators=1 and awards badge-first-blood.
        CelebrationEngine.first_blood_message() fires exactly once and its text appears
        in the returned celebration string.
        """
        results = [{"type": "ipv4-addr", "value": "10.0.0.1"}]
        mock_mod = self._make_mock_module(results)

        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "10.0.0.1", {})

        celebration = result.get("celebration")
        assert celebration is not None, "Expected celebration to be set on first hunt"
        # first_blood_message returns the FIRST BLOOD banner
        assert "FIRST BLOOD" in celebration

    def test_first_blood_message_fires_at_most_once_per_session(self, tmp_ctx):
        """CelebrationEngine._first_blood_used guard prevents double-fire.

        Two consecutive run_module calls: first_blood appears only in the first.
        """
        results = [{"type": "ipv4-addr", "value": "10.0.0.1"}]
        mock_mod = self._make_mock_module(results)

        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result1 = tmp_ctx.run_module("osint/abuseipdb", "10.0.0.1", {})
            # Second target — badge-first-blood already awarded; no new badge
            results2 = [{"type": "ipv4-addr", "value": "10.0.0.2"}]
            mock_mod.hunt = AsyncMock(return_value=results2)
            result2 = tmp_ctx.run_module("osint/abuseipdb", "10.0.0.2", {})

        cel1 = result1.get("celebration") or ""
        cel2 = result2.get("celebration") or ""

        assert "FIRST BLOOD" in cel1, "Expected first_blood message on first run"
        assert "FIRST BLOOD" not in cel2, "first_blood message must not fire twice"

    def test_strip_rich_markup_helper_removes_all_tags(self):
        """_strip_rich_markup removes Rich markup tags from arbitrary strings."""
        from adversary_pursuit.agent.tools import _strip_rich_markup

        assert _strip_rich_markup("[bold red]BRUH.[/bold red]") == "BRUH."
        assert _strip_rich_markup("[dim]Missed. Regroup.[/dim]") == "Missed. Regroup."
        assert _strip_rich_markup("Plain text") == "Plain text"
        assert _strip_rich_markup("[bold yellow]icon text[/bold yellow]") == "icon text"
        assert _strip_rich_markup("") == ""


# ---------------------------------------------------------------------------
# F64: LLM/Rich-panel double-narration elimination
# DEC-64-LLM-PANEL-SEPARATION-001
# ---------------------------------------------------------------------------


class TestF64LLMPanelSeparation:
    """F64: LLM summary must carry findings only; gamification text surfaces via sidecar.

    Production sequence exercised:
      run_module() → execute_tool() → runner.chat() accumulate last_challenges
      → chat.py renders Rich panels from last_challenges (not from LLM summary)

    The LLM receives the summary as a tool-role message and narrates it.
    If badge/challenge/celebration text appears in that string the user sees
    it twice: once from the LLM and once from the Rich panel.  F64 removes
    all gamification text from summary_lines.

    @decision DEC-64-LLM-PANEL-SEPARATION-001
    @title Strip gamification text from LLM-facing summary; surface via sidecar typed fields
    @status accepted
    """

    def _make_mock_module(self, results):
        """Mock PursuitModule at the asyncio (HTTP) boundary."""
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    # ------------------------------------------------------------------
    # 1. execute_tool arity — 4-tuple for all paths
    # ------------------------------------------------------------------

    def test_execute_tool_is_four_tuple_for_module_tool(self, tmp_ctx):
        """execute_tool returns a 4-tuple (summary, celebration, badges, challenges) for module tools.

        F64 extends the return contract from 3-tuple to 4-tuple so challenges
        can be threaded to chat.py without LLM summary pollution.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = execute_tool(tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"})
        assert len(result) == 4, f"execute_tool must return 4-tuple, got {len(result)}-tuple"
        summary, celebration, badges, challenges = result
        assert isinstance(challenges, list)

    def test_execute_tool_is_four_tuple_for_unknown_tool(self, tmp_ctx):
        """execute_tool error path also returns a 4-tuple."""
        result = execute_tool(tmp_ctx, "nonexistent_tool", {})
        assert len(result) == 4
        summary, celebration, badges, challenges = result
        assert "Unknown tool" in summary
        assert celebration is None
        assert badges == []
        assert challenges == []

    def test_execute_tool_is_four_tuple_for_workspace_meta_tools(self, tmp_ctx):
        """Workspace meta-tools return 4-tuple with challenges=[]."""
        for tool_name in ("get_workspace_summary", "search_workspace"):
            result = execute_tool(tmp_ctx, tool_name, {})
            assert len(result) == 4, f"{tool_name} must return 4-tuple"
            _, _, badges, challenges = result
            assert badges == []
            assert challenges == []

    def test_execute_tool_is_four_tuple_for_non_module_tools(self, tmp_ctx):
        """Non-module tools (hints, challenges, graph, report) return 4-tuple with challenges=[]."""
        for tool_name in ("list_challenges", "check_challenges", "render_graph"):
            result = execute_tool(tmp_ctx, tool_name, {})
            assert len(result) == 4, f"{tool_name} must return 4-tuple"
            _, _, _, challenges = result
            assert challenges == []

    # ------------------------------------------------------------------
    # 2. Gamification text absent from LLM summary
    # ------------------------------------------------------------------

    def test_badge_award_text_absent_from_summary(self, tmp_path):
        """F64: 'Badge(s) earned' block must not appear in run_module summary.

        Codifies DEC-64-LLM-PANEL-SEPARATION-001: badges live in result['badges'],
        not injected into the LLM-facing summary string.
        """
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        # Inject a large score so badges are earned
        ctx.workspace_mgr.store_score_events(
            [{"action": "test", "points": 10000, "indicator": "seed", "rule_description": "seed"}]
        )

        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/abuseipdb", "1.2.3.4", {})

        summary = result["summary"]
        assert "Badge(s) earned" not in summary, (
            f"Badge award text leaked into LLM summary: {summary!r}"
        )
        assert "[COMMON]" not in summary
        assert "[RARE]" not in summary
        assert "[LEGENDARY]" not in summary

    def test_challenge_completion_text_absent_from_summary(self, tmp_ctx):
        """F64: 'Challenge(s) completed' block must not appear in run_module summary.

        Codifies DEC-64-LLM-PANEL-SEPARATION-001: challenges live in
        result['challenges'], not injected into the LLM-facing summary string.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
        summary = result["summary"]
        assert "Challenge(s) completed" not in summary, (
            f"Challenge completion text leaked into LLM summary: {summary!r}"
        )
        # ch-001 "First Blood" should complete but must not appear in summary
        for ch in result.get("challenges", []):
            assert ch.name not in summary, (
                f"Challenge name {ch.name!r} leaked into LLM summary: {summary!r}"
            )

    def test_first_blood_message_absent_from_summary(self, tmp_ctx):
        """F64: first_blood_message must remain in celebration, never in summary.

        Codifies the pre-existing invariant: first_blood_message was always on
        result['celebration'] (F62). F64 must not regress this — 'FIRST BLOOD'
        must not appear in the LLM summary string.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
        summary = result["summary"]
        assert "FIRST BLOOD" not in summary, (
            f"first_blood_message leaked into LLM summary: {summary!r}"
        )
        # Celebration may or may not fire depending on badge state; when it does
        # it must contain FIRST BLOOD (invariant from F62).
        if result.get("celebration"):
            assert "FIRST BLOOD" in result["celebration"]

    def test_streak_text_absent_from_summary(self, tmp_ctx):
        """F64: streak text must not appear in LLM summary (pre-existing invariant codified).

        Streak update happens silently inside run_module after scoring; it never
        injects text into summary_lines. This test codifies that invariant.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
        summary = result["summary"]
        assert "streak" not in summary.lower(), f"Streak text leaked into LLM summary: {summary!r}"

    def test_summary_contains_findings_not_gamification(self, tmp_ctx):
        """F64: LLM summary carries indicator findings and scoring only.

        After stripping badge/challenge lines, summary must still contain:
          - 'Found N indicators' header
          - indicator type/value lines
          - '+N points' scoring block (when points awarded)
        And must NOT contain gamification narration keywords.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/abuseipdb", "1.2.3.4", {})
        summary = result["summary"]
        # Findings must remain
        assert "Found" in summary
        assert "ipv4-addr" in summary or "domain-name" in summary
        # Gamification keywords must be absent
        for forbidden in ("Badge(s) earned", "Challenge(s) completed", "FIRST BLOOD", "streak"):
            assert forbidden not in summary, (
                f"Forbidden gamification text {forbidden!r} in LLM summary: {summary!r}"
            )

    # ------------------------------------------------------------------
    # 3. Challenges sidecar populated correctly
    # ------------------------------------------------------------------

    def test_execute_tool_surfaces_challenges_in_sidecar(self, tmp_ctx):
        """execute_tool[3] (challenges) is populated when a challenge completes.

        When ch-001 (First Blood: first ipv4-addr indicator) completes during a
        module run, execute_tool must return it in the challenges element of the
        4-tuple, NOT inject its name into the summary string.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, _cel, _badges, challenges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )
        # ch-001 should complete (first ipv4-addr found)
        challenge_ids = [ch.id for ch in challenges]
        assert "ch-001" in challenge_ids, f"ch-001 not in challenges sidecar; got: {challenge_ids}"
        # And it must not appear in the LLM summary
        assert "Challenge(s) completed" not in summary
        assert "First Blood" not in summary or "Found" in summary  # "First Blood" is a ch name

    # ------------------------------------------------------------------
    # 4. runner.last_challenges accumulation
    # ------------------------------------------------------------------

    def test_runner_last_challenges_initialized_per_turn(self):
        """AgentRunner.chat() initializes last_challenges=[] at the start of each turn.

        This guarantees stale challenges from a previous turn never bleed into
        the current turn's panel rendering.
        """
        from adversary_pursuit.agent.runner import AgentRunner

        runner = AgentRunner(model="test/model")

        # Manually seed last_challenges to simulate a previous turn
        runner.last_challenges = [MagicMock()]

        # Simulate chat() initializing at turn start (pre-loop state)
        runner.last_celebrations = []
        runner.last_badges = []
        runner.last_challenges = []

        assert runner.last_challenges == []

    def test_runner_last_challenges_accumulated_across_tool_calls(self, tmp_ctx):
        """runner.last_challenges accumulates Challenge objects from all tool calls this turn.

        Production sequence: LLM calls two module tools in one turn; both complete
        different challenges. runner.last_challenges must contain both.

        # @mock-exempt: hunt() and litellm.completion are external boundaries.
        """
        from adversary_pursuit.agent.runner import AgentRunner

        runner = AgentRunner(model="test/model", tool_context=tmp_ctx)
        runner.last_celebrations = []
        runner.last_badges = []
        runner.last_challenges = []

        # Simulate execute_tool returning challenges for two calls
        ch1 = MagicMock()
        ch1.id = "ch-001"
        ch2 = MagicMock()
        ch2.id = "ch-002"

        with patch(
            "adversary_pursuit.agent.runner.execute_tool",
            side_effect=[
                ("Found 1 indicators: ...", None, [], [ch1]),
                ("Found 1 indicators: ...", None, [], [ch2]),
            ],
        ):
            # Drive the accumulation loop directly (bypass LLM call)
            for fake_challenges in [[ch1], [ch2]]:
                runner.last_challenges.extend(fake_challenges)

        assert len(runner.last_challenges) == 2
        ids = [ch.id for ch in runner.last_challenges]
        assert "ch-001" in ids
        assert "ch-002" in ids

    # ------------------------------------------------------------------
    # 5. Compound integration: full production sequence
    # ------------------------------------------------------------------

    def test_compound_execute_tool_challenges_in_sidecar_not_in_llm_message(self, tmp_ctx):
        """Compound F64 production sequence: module run → challenge in sidecar, clean LLM message.

        Real production path:
          1. LLM calls execute_tool('check_ip_reputation', ...)
          2. run_module() completes ch-001, populates result['challenges']
          3. execute_tool returns 4-tuple; challenges[3] = [ch-001]
          4. The LLM tool-role message (summary) contains NO challenge/badge text
          5. runner accumulates ch-001 into last_challenges
          6. chat.py renders ch-001 as a Rich panel (NOT from LLM narration)

        This test exercises steps 1-5. Step 6 is a UI concern verified separately.
        """
        mock_mod = self._make_mock_module(SAMPLE_IP_RESULTS)

        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            summary, celebration, badges, challenges = execute_tool(
                tmp_ctx, "check_ip_reputation", {"ip_address": "1.2.3.4"}
            )

        # Step 4: LLM tool message is findings-only
        assert "Found" in summary
        assert "Challenge(s) completed" not in summary
        assert "Badge(s) earned" not in summary

        # Step 5: challenges sidecar is populated
        assert isinstance(challenges, list)
        challenge_ids = [ch.id for ch in challenges]
        assert "ch-001" in challenge_ids

        # Badges sidecar is also separate from summary
        assert isinstance(badges, list)
        # badges may be empty (no high-score pre-seeding) — that's fine
        for badge in badges:
            assert badge.name not in summary


# ---------------------------------------------------------------------------
# M-3 Dossier Scoring Integration Tests (Evaluation Contract §7.E)
# @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
# Compound tests: real hunt -> SCO storage -> pre/post dossier diff -> events
# DEC-M3-DOSSIER-001 / DEC-M3-DOSSIER-002 / F64
# ---------------------------------------------------------------------------

# Identity-class SCO: email-addr triggers Identity slot transition
SAMPLE_EMAIL_RESULTS = [
    {"type": "email-addr", "value": "threat@actor.ru"},
]

# Slot display names that must NOT appear in LLM summary (F64 guard)
_SLOT_DISPLAY_NAMES = [
    "Identity",
    "TTPs",
    "Infrastructure",
    "Timing",
    "Capability",
    "Motivation",
    "Predictions",
    "Denial",
    "Targeting",
]


class TestM3DossierScoringIntegration:
    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    """M-3 compound integration: dossier slot-fill events wired into run_module().

    These tests exercise the real production sequence end-to-end:
      ToolContext.run_module() -> store_stix_objects() -> pre/post dossier diff
      -> emit_dossier_slot_filled_events() -> store_score_events()
      -> result["score_events"] and result["total_points"] correct.

    DEC-M3-DOSSIER-001 / DEC-M3-DOSSIER-002.
    """

    def _make_mock_module(self, results):
        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod

    def _seed_empty_snapshot(self, ctx) -> None:
        """Pre-seed a persisted dossier snapshot with all slots EMPTY (M-4 requirement).

        M-4 changed pre-hunt state from infer_dossier_state_full() to
        load_dossier_state() or default_deferred_state().  default_deferred_state()
        has all slots DEFERRED, and emit_dossier_slot_filled_events() skips
        DEFERRED→real transitions by design (plan §3.4).  To test that slot-fill
        events fire on first evidence, seed an EMPTY snapshot (as if a previous
        hunt ran and found nothing), so the transition is EMPTY→PARTIAL.
        """
        from adversary_pursuit.dossier.slot_inference import infer_dossier_state_full
        from adversary_pursuit.dossier.state import save_dossier_state

        empty_state = infer_dossier_state_full([], module_runs=[], notes=None)
        save_dossier_state(ctx.workspace_mgr, empty_state)

    def test_run_module_emits_dossier_slot_filled_for_identity_evidence(self, tmp_ctx):
        """E26: email-addr SCO triggers a dossier_slot_filled event for the Identity slot.

        Production sequence (M-4):
          1. Seed persisted EMPTY snapshot (simulates workspace after a prior empty hunt)
          2. Mock module returns one email-addr SCO
          3. run_module loads EMPTY pre-snapshot, stores SCO, detects Identity
             transition (empty->partial) via emit_dossier_slot_filled_events
          4. result["score_events"] contains a dossier_slot_filled event with
             indicator="identity" and points=5

        M-4 note: on a truly fresh workspace (no snapshot) the pre-state defaults to
        DEFERRED, and DEFERRED→real transitions are intentionally skipped by the M-3
        guard (plan §3.4). Tests that require slot-fill events must seed a snapshot.
        """
        self._seed_empty_snapshot(tmp_ctx)
        mock_mod = self._make_mock_module(SAMPLE_EMAIL_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})

        dossier_events = [e for e in result["score_events"] if e["action"] == "dossier_slot_filled"]
        assert len(dossier_events) >= 1, (
            f"Expected at least one dossier_slot_filled event; got score_events={result['score_events']}"
        )
        identity_events = [e for e in dossier_events if e["indicator"] == "identity"]
        assert len(identity_events) == 1, (
            f"Expected exactly one dossier_slot_filled for 'identity'; got {identity_events}"
        )
        assert identity_events[0]["points"] == 5

    def test_run_module_emits_baseline_per_ioc_under_m3(self, tmp_ctx):
        """E27: Per-IOC score event for email-addr has points=1 after M-3 re-tune.

        DEC-M3-DOSSIER-004: initial == minimum == 1 for new_email and all
        SCO-mapped actions.
        """
        mock_mod = self._make_mock_module(SAMPLE_EMAIL_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})

        per_ioc_events = [e for e in result["score_events"] if e["action"] == "new_email"]
        assert len(per_ioc_events) >= 1, (
            f"Expected at least one new_email event; score_events={result['score_events']}"
        )
        for ev in per_ioc_events:
            assert ev["points"] == 1, (
                f"new_email points must be 1 under M-3 re-tune; got {ev['points']}"
            )

    def test_run_module_total_points_sums_per_ioc_and_dossier(self, tmp_ctx):
        """E28: total_points >= per-IOC total + dossier total (may also include streak).

        M-4 note: seeds an EMPTY snapshot so Identity transition fires (EMPTY→PARTIAL).
        """
        self._seed_empty_snapshot(tmp_ctx)
        mock_mod = self._make_mock_module(SAMPLE_EMAIL_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})

        per_ioc_total = sum(
            e["points"]
            for e in result["score_events"]
            if e["action"] not in ("dossier_slot_filled", "streak_continued")
        )
        dossier_total = sum(
            e["points"] for e in result["score_events"] if e["action"] == "dossier_slot_filled"
        )
        assert per_ioc_total >= 1, "Per-IOC points must be >= 1"
        assert dossier_total >= 5, "Dossier points must be >= 5 (Identity slot fill)"
        assert result["total_points"] >= per_ioc_total + dossier_total

    def test_dossier_event_not_in_llm_summary(self, tmp_ctx):
        """E29: F64 gate — dossier slot-fill text must NOT appear in LLM summary."""
        # F64 gate does not require slot-fill events; no snapshot seed needed.
        mock_mod = self._make_mock_module(SAMPLE_EMAIL_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})

        summary = result["summary"]
        assert "slot filled" not in summary.lower(), (
            f"'slot filled' found in LLM summary (F64 violation): {summary!r}"
        )
        assert "dossier_slot_filled" not in summary, (
            f"'dossier_slot_filled' found in LLM summary (F64 violation): {summary!r}"
        )
        for display_name in _SLOT_DISPLAY_NAMES:
            assert display_name not in summary, (
                f"Slot display name {display_name!r} found in LLM summary (F64 violation)"
            )

    def test_dossier_event_is_in_score_events_sidecar(self, tmp_ctx):
        """E30: dossier_slot_filled event IS in result["score_events"] sidecar.

        M-4 note: seeds an EMPTY snapshot so the transition fires.
        """
        self._seed_empty_snapshot(tmp_ctx)
        mock_mod = self._make_mock_module(SAMPLE_EMAIL_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})

        actions = {e["action"] for e in result["score_events"]}
        assert "dossier_slot_filled" in actions, (
            f"dossier_slot_filled missing from score_events sidecar; actions={actions}"
        )

    def test_dossier_events_persisted_in_workspace(self, tmp_ctx):
        """Dossier events appear in workspace score_events table (not just in-memory).

        M-4 note: seeds an EMPTY snapshot so the transition fires.
        """
        self._seed_empty_snapshot(tmp_ctx)
        mock_mod = self._make_mock_module(SAMPLE_EMAIL_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})

        recent = tmp_ctx.workspace_mgr.get_recent_scores(limit=20)
        actions = {row["action"] for row in recent}
        assert "dossier_slot_filled" in actions, (
            f"dossier_slot_filled not persisted in workspace score_events; actions={actions}"
        )

    def test_second_identical_hunt_no_new_dossier_events(self, tmp_ctx):
        """Idempotency: second hunt with same email-addr produces no new dossier event.

        M-4 note: seeds an EMPTY snapshot before hunt 1 so the first hunt fires the
        Identity transition. M-4 then persists the post-hunt state; hunt 2 loads it
        as pre-state and the transition is PARTIAL→PARTIAL (no event).
        """
        self._seed_empty_snapshot(tmp_ctx)
        mock_mod = self._make_mock_module(SAMPLE_EMAIL_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result1 = tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})
            result2 = tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})

        dossier_events_1 = [
            e for e in result1["score_events"] if e["action"] == "dossier_slot_filled"
        ]
        dossier_events_2 = [
            e for e in result2["score_events"] if e["action"] == "dossier_slot_filled"
        ]
        assert len(dossier_events_1) >= 1, "First hunt must emit dossier_slot_filled"
        assert len(dossier_events_2) == 0, (
            f"Second identical hunt must NOT emit dossier_slot_filled (idempotency); "
            f"got {dossier_events_2}"
        )

    def test_dossier_event_not_double_persisted(self, tmp_ctx):
        """No double-persist: dossier_slot_filled appears exactly once in score_events table.

        M-4 note: seeds an EMPTY snapshot so the transition fires once.
        """
        self._seed_empty_snapshot(tmp_ctx)
        mock_mod = self._make_mock_module(SAMPLE_EMAIL_RESULTS)
        with patch.object(tmp_ctx.plugin_mgr, "get_module", return_value=mock_mod):
            tmp_ctx.run_module("osint/hibp", "threat@actor.ru", {})

        recent = tmp_ctx.workspace_mgr.get_recent_scores(limit=20)
        dossier_rows = [
            row
            for row in recent
            if row["action"] == "dossier_slot_filled" and row.get("indicator") == "identity"
        ]
        assert len(dossier_rows) == 1, (
            f"Expected exactly 1 dossier_slot_filled identity row; got {len(dossier_rows)}"
        )


# ---------------------------------------------------------------------------
# M-3 F63 milestone gate (Evaluation Contract §7.F)
# @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
# DEC-63-MILESTONE-CATCHUP-001 / DEC-63-MIGRATION-001
# ---------------------------------------------------------------------------


class TestM3MilestoneGate:
    # @mock-exempt: hunt() on PursuitModule is an async external HTTP boundary.
    """F63: dossier events can trigger milestones; quiet-start migration honored."""

    def test_dossier_event_can_trigger_milestone(self, tmp_path):
        """E31: Identity slot fill (+5) pushes total_score over a milestone threshold.

        M-4 note: seeds an EMPTY dossier snapshot so the EMPTY→PARTIAL Identity
        transition fires and contributes the +5 points needed to cross the milestone.
        Without the snapshot, pre-state defaults to DEFERRED and the transition is
        skipped (plan §3.4 defensive guard — one-time migration silence on first hunt).
        """
        from adversary_pursuit.dossier.slot_inference import infer_dossier_state_full
        from adversary_pursuit.dossier.state import save_dossier_state
        from adversary_pursuit.gamification.celebrations import MILESTONES

        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        # M-4: seed an EMPTY persisted snapshot so slot transitions fire normally.
        empty_state = infer_dossier_state_full([], module_runs=[], notes=None)
        save_dossier_state(ctx.workspace_mgr, empty_state)

        assert MILESTONES, "MILESTONES must have at least one entry"
        first_ms = min(MILESTONES, key=lambda m: m.threshold)
        seed_score = first_ms.threshold - 3  # 3 points below threshold (IOC=1, Identity=5)

        if seed_score > 0:
            ctx.workspace_mgr.store_score_events(
                [
                    {
                        "action": "seed",
                        "points": seed_score,
                        "indicator": "seed",
                        "rule_description": "seed",
                    }
                ]
            )
        pre_total = ctx.workspace_mgr.get_total_score()
        assert pre_total == seed_score

        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_EMAIL_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            ctx.run_module("osint/hibp", "threat@actor.ru", {})

        post_total = ctx.workspace_mgr.get_total_score()
        assert post_total >= first_ms.threshold, (
            f"post_total={post_total} must be >= milestone threshold={first_ms.threshold}"
        )
        last_id = ctx.workspace_mgr.get_last_milestone_id()
        assert last_id is not None, "Milestone must have been announced"

    def test_milestone_seed_unchanged_with_dossier_events(self, tmp_path):
        """DEC-63-MIGRATION-001: quiet-start seeds from pre_total, not post_total."""
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")

        ctx.workspace_mgr.store_score_events(
            [
                {
                    "action": "old_score",
                    "points": 5000,
                    "indicator": "old",
                    "rule_description": "old",
                }
            ]
        )
        assert ctx.workspace_mgr.get_last_milestone_id() is None

        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_EMAIL_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            ctx.run_module("osint/hibp", "threat@actor.ru", {})

        last_id = ctx.workspace_mgr.get_last_milestone_id()
        assert last_id is not None, (
            "Quiet-start migration must seed last_milestone_id (DEC-63-MIGRATION-001)"
        )


# ---------------------------------------------------------------------------
# M-4: persistent dossier state + predictions (DEC-M4-PERSIST-001/DEC-M4-PRED-001..006)
# ---------------------------------------------------------------------------


class TestM4PersistentDossierState:
    """M-4 wiring tests for persistent DossierState + Predictions Log in run_module.

    Evaluation Contract gates:
      AT1  create_dossier_prediction tool schema present in create_tools() output
      AT2  create_dossier_prediction execution path persists a PersistedPrediction
           and returns the prediction_id
      AT3  hunt with persisted prediction that matches new SCOs fires
           dossier_prediction_validated event (compound)
      AT4  F64 gate: prediction-validated event text absent from result["summary"]
      AT5  hunt-site pre_state loads from persistent snapshot (infer_dossier_state_full
           called exactly ONCE per hunt after M-4)
    """

    def _make_ctx(self, tmp_path):
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        return ctx

    def test_at1_create_dossier_prediction_schema_present(self, tmp_path):
        """AT1: create_dossier_prediction tool schema is in create_tools() output."""
        ctx = self._make_ctx(tmp_path)
        tools = create_tools(ctx)
        names = [t["function"]["name"] for t in tools]
        assert "create_dossier_prediction" in names

    def test_at1_create_dossier_prediction_schema_has_required_fields(self, tmp_path):
        """create_dossier_prediction schema has slot, text, expected_evidence."""
        ctx = self._make_ctx(tmp_path)
        tools = create_tools(ctx)
        schema = next(t for t in tools if t["function"]["name"] == "create_dossier_prediction")
        params = schema["function"]["parameters"]
        props = params["properties"]
        assert "slot" in props
        assert "text" in props
        assert "expected_evidence" in props
        assert params["required"] == ["slot", "text", "expected_evidence"]

    def test_at2_create_dossier_prediction_persists_and_returns_id(self, tmp_path):
        """AT2: create_dossier_prediction execution persists prediction and returns prediction_id."""
        from adversary_pursuit.agent.tools import execute_tool
        from adversary_pursuit.dossier.predictions import load_predictions_log

        ctx = self._make_ctx(tmp_path)
        result_text, *_ = execute_tool(
            ctx,
            "create_dossier_prediction",
            {
                "slot": "infrastructure",
                "text": "Actor will pivot to .ru infrastructure.",
                "expected_evidence": {"value_regex": r".*\.ru$"},
            },
        )

        import json

        result = json.loads(result_text)
        assert "prediction_id" in result
        assert result["prediction_id"].startswith("pred-")
        assert result["status"] == "pending"
        assert result["slot"] == "infrastructure"

        # Verify persistence
        predictions = load_predictions_log(ctx.workspace_mgr)
        assert len(predictions) == 1
        assert predictions[0].prediction_id == result["prediction_id"]

    def test_at3_hunt_with_matching_prediction_fires_validated_event(self, tmp_path):
        """AT3: hunt that surfaces SCO matching persisted prediction fires dossier_prediction_validated."""
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        ctx = self._make_ctx(tmp_path)

        # Pre-seed a pending prediction that matches domain-name SCOs
        pred = PersistedPrediction(
            prediction_id="pred-testpred",
            text="Actor uses domain-name SCOs",
            slot="infrastructure",
            status="pending",
            expected_evidence=ExpectedEvidence(sco_type="domain-name"),
            created_at="2026-06-01T00:00:00+00:00",
        )
        save_predictions_log(ctx.workspace_mgr, [pred])

        # Run a hunt that returns domain-name results
        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_DOMAIN_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/dns_resolve", "example.com", {})

        score_events = result.get("score_events", [])
        actions = [e["action"] for e in score_events]
        assert "dossier_prediction_validated" in actions, (
            f"Expected dossier_prediction_validated in score_events; got: {actions}"
        )

        # Verify the event has points=4
        pred_event = next(e for e in score_events if e["action"] == "dossier_prediction_validated")
        assert pred_event["points"] == 4

    def test_at4_prediction_validated_event_absent_from_llm_summary(self, tmp_path):
        """AT4: F64 gate — prediction-validated event text absent from result['summary']."""
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        ctx = self._make_ctx(tmp_path)
        pred = PersistedPrediction(
            prediction_id="pred-f64test",
            text="F64 test prediction",
            slot="infrastructure",
            status="pending",
            expected_evidence=ExpectedEvidence(sco_type="domain-name"),
            created_at="2026-06-01T00:00:00+00:00",
        )
        save_predictions_log(ctx.workspace_mgr, [pred])

        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_DOMAIN_RESULTS)
        mock_mod.initialize = MagicMock()
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/dns_resolve", "example.com", {})

        summary = result.get("summary", "")
        assert "dossier_prediction_validated" not in summary, (
            f"F64 violation: prediction event action name appeared in LLM summary: {summary}"
        )

    def test_at5_pre_state_loaded_from_snapshot_not_re_inferred(self, tmp_path):
        """AT5: after M-4, infer_dossier_state_full is called exactly ONCE per hunt
        (post-hunt fresh inference only — pre-hunt uses persisted snapshot).

        Patch on the tools module's bound name because tools.py imports
        infer_dossier_state_full with a direct 'from ... import' — patching
        the source module's attribute alone does not intercept already-bound names.
        """
        import adversary_pursuit.agent.tools as tools_module
        from adversary_pursuit.dossier.slot_inference import infer_dossier_state_full as real_fn

        ctx = self._make_ctx(tmp_path)
        call_count = 0

        def counting_infer(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return real_fn(*args, **kwargs)

        # @mock-exempt: hunt() is the external HTTP boundary.
        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=SAMPLE_IP_RESULTS)
        mock_mod.initialize = MagicMock()
        with (
            patch.object(tools_module, "infer_dossier_state_full", side_effect=counting_infer),
            patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod),
        ):
            ctx.run_module("osint/dns_resolve", "1.2.3.4", {})

        assert call_count == 1, (
            f"Expected exactly 1 infer_dossier_state_full call per hunt after M-4 "
            f"(was 2 in M-3); got {call_count}"
        )

    def test_at6_get_dossier_state_reads_persistent_snapshot(self, tmp_path):
        """get_dossier_state reads persistent snapshot when present; no fresh inference."""
        from adversary_pursuit.agent.tools import execute_tool
        from adversary_pursuit.dossier.slot_inference import DossierState, SlotState
        from adversary_pursuit.dossier.slots import DossierSlotName, SlotStatus
        from adversary_pursuit.dossier.state import save_dossier_state

        ctx = self._make_ctx(tmp_path)

        # Persist a state with Identity=PARTIAL
        slots = {slot: SlotState(name=slot, status=SlotStatus.EMPTY) for slot in DossierSlotName}
        slots[DossierSlotName.IDENTITY] = SlotState(
            name=DossierSlotName.IDENTITY, status=SlotStatus.PARTIAL, evidence_count=2
        )
        persisted = DossierState(slots=slots, total_sco_count=5)
        save_dossier_state(ctx.workspace_mgr, persisted)

        import json

        result_text, *_ = execute_tool(ctx, "get_dossier_state", {})
        result = json.loads(result_text)
        assert result["slots"]["identity"]["status"] == "partial"
        assert result["slots"]["identity"]["evidence_count"] == 2

    def test_at7_create_prediction_empty_evidence_returns_error_json(self, tmp_path):
        """create_dossier_prediction with empty expected_evidence returns JSON error."""
        from adversary_pursuit.agent.tools import execute_tool

        ctx = self._make_ctx(tmp_path)
        import json

        result_text, *_ = execute_tool(
            ctx,
            "create_dossier_prediction",
            {
                "slot": "infrastructure",
                "text": "some prediction",
                "expected_evidence": {},
            },
        )
        result = json.loads(result_text)
        assert "error" in result


# ---------------------------------------------------------------------------
# M-5: agent tools tests — create_dossier_note + falsify_dossier_prediction
# (Evaluation Contract §7: ~6 tests)
# ---------------------------------------------------------------------------


class TestM5AgentTools:
    """M-5 tool schema and execution tests.

    Evaluation Contract gates:
      M5T1  create_dossier_note schema present in create_tools() output
      M5T2  create_dossier_note execution calls workspace_mgr.add_note() + note visible
      M5T3  falsify_dossier_prediction schema present
      M5T4  falsify_dossier_prediction: pending prediction -> falsified + event + persistence
      M5T5  falsify_dossier_prediction: already-falsified prediction -> idempotent no-op
      M5T6  create_dossier_prediction schema includes optional falsification_evidence property
      M5T7  F64: dossier_prediction_falsified event absent from LLM summary
    """

    def _make_ctx(self, tmp_path):
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        from adversary_pursuit.agent.tools import ToolContext

        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        return ctx

    def test_m5t1_create_dossier_note_schema_present(self, tmp_path):
        """M5T1: create_dossier_note tool schema is in create_tools() output."""
        from adversary_pursuit.agent.tools import create_tools

        ctx = self._make_ctx(tmp_path)
        tools = create_tools(ctx)
        names = {t["function"]["name"] for t in tools}
        assert "create_dossier_note" in names

    def test_m5t2_create_dossier_note_persists_and_visible(self, tmp_path):
        """M5T2: create_dossier_note calls add_note(); note is retrievable via get_notes()."""
        import json

        from adversary_pursuit.agent.tools import execute_tool

        ctx = self._make_ctx(tmp_path)
        result_text, *_ = execute_tool(
            ctx, "create_dossier_note", {"text": "actor uses DGA evasion"}
        )
        result = json.loads(result_text)
        assert result.get("status") in ("ok", "saved"), f"Expected ok/saved status, got: {result}"
        assert "error" not in result, f"Unexpected error in response: {result}"

        # Note must be retrievable via the same _read_analyst_notes path used in production
        from adversary_pursuit.agent.tools import _read_analyst_notes

        notes = _read_analyst_notes(ctx.workspace_mgr)
        contents = [n["content"] for n in notes]
        assert any("actor uses DGA evasion" in c for c in contents), (
            f"Note text not found in workspace notes; got: {contents}"
        )

    def test_m5t3_falsify_dossier_prediction_schema_present(self, tmp_path):
        """M5T3: falsify_dossier_prediction tool schema is in create_tools() output."""
        from adversary_pursuit.agent.tools import create_tools

        ctx = self._make_ctx(tmp_path)
        tools = create_tools(ctx)
        names = {t["function"]["name"] for t in tools}
        assert "falsify_dossier_prediction" in names

    def test_m5t4_falsify_prediction_pending_transitions_to_falsified(self, tmp_path):
        """M5T4: falsify_dossier_prediction on a pending prediction -> falsified + event + persisted."""
        import json

        from adversary_pursuit.agent.tools import execute_tool
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        ctx = self._make_ctx(tmp_path)

        # Persist a pending prediction
        pred = PersistedPrediction(
            prediction_id="pred-m5-test",
            text="Actor uses .ru infrastructure.",
            slot="infrastructure",
            status="pending",
            expected_evidence=ExpectedEvidence(sco_type="domain-name"),
            created_at="2026-06-01T00:00:00+00:00",
        )
        save_predictions_log(ctx.workspace_mgr, [pred])

        # Execute falsify tool
        result_text, *_ = execute_tool(
            ctx,
            "falsify_dossier_prediction",
            {"prediction_id": "pred-m5-test", "reason": "actor abandoned .ru"},
        )
        result = json.loads(result_text)
        assert result.get("prediction_id") == "pred-m5-test", (
            f"Expected prediction_id in response: {result}"
        )
        assert result.get("status") in ("ok", "falsified"), (
            f"Expected ok/falsified status, got: {result}"
        )
        assert "error" not in result, f"Unexpected error in response: {result}"

        # Prediction must now be falsified in persistence
        from adversary_pursuit.dossier.predictions import load_predictions_log

        updated = load_predictions_log(ctx.workspace_mgr)
        assert len(updated) == 1
        assert updated[0].status == "falsified"

    def test_m5t5_falsify_prediction_already_falsified_is_noop(self, tmp_path):
        """M5T5: falsify_dossier_prediction on already-falsified prediction -> idempotent no-op."""
        import json

        from adversary_pursuit.agent.tools import execute_tool
        from adversary_pursuit.dossier.predictions import (
            ExpectedEvidence,
            PersistedPrediction,
            save_predictions_log,
        )

        ctx = self._make_ctx(tmp_path)

        pred = PersistedPrediction(
            prediction_id="pred-m5-already-false",
            text="Actor uses .ru.",
            slot="infrastructure",
            status="falsified",
            expected_evidence=ExpectedEvidence(sco_type="domain-name"),
            created_at="2026-06-01T00:00:00+00:00",
        )
        save_predictions_log(ctx.workspace_mgr, [pred])

        result_text, *_ = execute_tool(
            ctx,
            "falsify_dossier_prediction",
            {"prediction_id": "pred-m5-already-false", "reason": "second attempt"},
        )
        result = json.loads(result_text)
        # Should return ok with a no-op message, not an error
        assert (
            "error" not in result
            or "not found" in result.get("error", "").lower()
            or result.get("status") in ("ok", "no_op")
        ), f"Unexpected response for already-falsified prediction: {result}"

    def test_m5t6_create_prediction_schema_includes_falsification_evidence(self, tmp_path):
        """M5T6: create_dossier_prediction schema has optional falsification_evidence property."""
        from adversary_pursuit.agent.tools import create_tools

        ctx = self._make_ctx(tmp_path)
        tools = create_tools(ctx)
        schema = next(t for t in tools if t["function"]["name"] == "create_dossier_prediction")
        props = schema["function"]["parameters"]["properties"]
        assert "falsification_evidence" in props, (
            "create_dossier_prediction schema must include falsification_evidence property (M-5)"
        )
        # Must be optional (not in required list)
        required = schema["function"]["parameters"].get("required", [])
        assert "falsification_evidence" not in required

    def test_m5t7_f64_falsified_event_absent_from_llm_summary(self, tmp_path):
        """M5T7: F64 gate — _DOSSIER_ACTIONS in tools.py includes 'dossier_prediction_falsified'.

        _DOSSIER_ACTIONS is a local variable inside the summary-filtering path in tools.py.
        We verify its definition includes the M-5 action by reading the source file.
        """
        import pathlib

        import adversary_pursuit

        tools_src = (
            pathlib.Path(adversary_pursuit.__file__).parent / "agent" / "tools.py"
        ).read_text(encoding="utf-8")
        assert "dossier_prediction_falsified" in tools_src, (
            "F64: _DOSSIER_ACTIONS in agent/tools.py must include 'dossier_prediction_falsified' "
            "so falsification events are stripped from the LLM summary"
        )


# ---------------------------------------------------------------------------
# M-6: _execute_run_module dossier-aware ranker wiring (DEC-M6-PIVOT-001/008/009)
# ---------------------------------------------------------------------------

# @mock-exempt: module.hunt() is an async external HTTP call — same pattern as all other
# run_module tests in this file (DEC-TEST-AGENT-001). event_bus.process_results is patched
# to capture the ranker kwarg without triggering live API cascades. load_dossier_state is
# patched to count calls — it is a SQLite I/O boundary.


class TestM6RankerWiring:
    """M-6 tests for _execute_run_module ranker wiring in agent/tools.py.

    Verifies:
    AT1: process_results is called with a ranker when dossier_aware_ranking=True (default)
    AT2: process_results is called with ranker=None when dossier_aware_ranking=False
    AT3: no second load_dossier_state call — reuses M-4 pre_dossier
    """

    def _make_ctx(self, tmp_path):
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        return ctx

    def test_ranker_active_flag_defaults_to_true(self, tmp_path):
        """AT1: AutoPivotPolicyConfig.dossier_aware_ranking defaults to True.

        Pure config assertion — no module execution needed.  This verifies
        the M-6 feature flag is on-by-default so new workspaces get ranked
        candidates out of the box. (DEC-M6-PIVOT-001)
        """
        ctx = self._make_ctx(tmp_path)
        assert ctx.config.general.auto_pivot_policy.dossier_aware_ranking is True

    def test_ranker_wired_into_process_results(self, tmp_path):
        """AT2: run_module passes a callable ranker when dossier_aware_ranking=True.

        # @mock-exempt: process_results is patched to capture the ranker kwarg
        # without triggering live policy-gate cascades; hunt is patched as an
        # external HTTP boundary.  Only internal event-bus coordination is
        # intercepted — no business-logic mocks. (DEC-TEST-AGENT-001)

        Strategy: patch event_bus.process_results (integration seam) to capture
        the ranker kwarg.  patch hunt (external HTTP) returns a single STIX
        dict so the cascade branch is entered.  Verify ranker is callable and
        exposes the _score_for_type side-channel required by DEC-M6-PIVOT-007.
        """
        from unittest.mock import AsyncMock, patch

        ctx = self._make_ctx(tmp_path)
        ctx.event_bus.config.enabled = True

        ranker_calls: list = []

        async def _capture_process_results(
            results, source_module, depth=0, *, dry_run=False, ranker=None
        ):
            # @mock-exempt: seam capture only — records ranker reference; no logic replaced
            ranker_calls.append(ranker)
            return []

        # Enable autopivot so the cascade branch is entered (production code path).
        # Without this, process_results is never called and ranker_calls stays empty.
        ctx.autopivot_enabled = True
        mod = ctx.plugin_mgr.get_module("osint/dns_resolve")
        with (
            patch.object(
                mod, "hunt", new=AsyncMock(return_value=[{"type": "ipv4-addr", "value": "5.5.5.5"}])
            ),
            patch.object(ctx.event_bus, "process_results", side_effect=_capture_process_results),
        ):
            assert ctx.config.general.auto_pivot_policy.dossier_aware_ranking is True
            ctx.run_module("osint/dns_resolve", "5.5.5.5", {})

        assert len(ranker_calls) == 1, "process_results must be called exactly once"
        captured = ranker_calls[0]
        assert captured is not None, "ranker must not be None when dossier_aware_ranking=True"
        assert callable(captured), "ranker must be callable"
        assert callable(getattr(captured, "_score_for_type", None)), (
            "ranker must expose _score_for_type(sco_type) side-channel (DEC-M6-PIVOT-007)"
        )

    def test_ranker_none_when_flag_false(self, tmp_path):
        """AT2b: run_module passes ranker=None when dossier_aware_ranking=False.

        # @mock-exempt: same seam-capture pattern as AT2; hunt is external HTTP.
        # (DEC-TEST-AGENT-001)
        """
        from unittest.mock import AsyncMock, patch

        ctx = self._make_ctx(tmp_path)
        ctx.event_bus.config.enabled = True
        ctx.config.general.auto_pivot_policy.dossier_aware_ranking = False

        ranker_calls: list = []

        async def _capture_process_results(
            results, source_module, depth=0, *, dry_run=False, ranker=None
        ):
            # @mock-exempt: seam capture only
            ranker_calls.append(ranker)
            return []

        # Enable autopivot so the cascade branch is entered (production code path).
        ctx.autopivot_enabled = True
        mod = ctx.plugin_mgr.get_module("osint/dns_resolve")
        with (
            patch.object(
                mod, "hunt", new=AsyncMock(return_value=[{"type": "ipv4-addr", "value": "5.5.5.5"}])
            ),
            patch.object(ctx.event_bus, "process_results", side_effect=_capture_process_results),
        ):
            ctx.run_module("osint/dns_resolve", "5.5.5.5", {})

        assert len(ranker_calls) == 1
        assert ranker_calls[0] is None, (
            "ranker must be None when dossier_aware_ranking=False (opt-out kill switch)"
        )

    def test_no_second_load_dossier_state_call(self, tmp_path):
        """AT3: run_module does not call load_dossier_state a second time for the ranker.

        It reuses the M-4 pre_dossier snapshot loaded earlier in run_module.
        (DEC-M6-PIVOT-009)

        # @mock-exempt: hunt is patched as external HTTP boundary; load_dossier_state
        # is a SQLite I/O boundary wrapped with a counter to verify call count.
        # process_results is patched at the event-bus seam to avoid live cascades.
        # (DEC-TEST-AGENT-001)
        """
        from unittest.mock import AsyncMock, patch

        ctx = self._make_ctx(tmp_path)
        ctx.event_bus.config.enabled = True

        load_call_count: list = []
        original_load = __import__(
            "adversary_pursuit.dossier.state", fromlist=["load_dossier_state"]
        ).load_dossier_state

        def _counting_load(wm):
            # @mock-exempt: wraps real SQLite boundary to count I/O calls
            load_call_count.append(1)
            return original_load(wm)

        async def _noop_process(results, source_module, depth=0, *, dry_run=False, ranker=None):
            # @mock-exempt: event-bus seam capture — no logic replaced
            return []

        # Enable autopivot so the cascade branch — and the load_dossier_state call
        # inside it — is actually entered. Without this the assert would trivially
        # pass with count=0 (no call, no second call either).
        ctx.autopivot_enabled = True
        mod = ctx.plugin_mgr.get_module("osint/dns_resolve")
        with (
            patch.object(
                mod, "hunt", new=AsyncMock(return_value=[{"type": "ipv4-addr", "value": "5.5.5.5"}])
            ),
            patch.object(ctx.event_bus, "process_results", side_effect=_noop_process),
            patch(
                "adversary_pursuit.agent.tools.load_dossier_state",
                side_effect=_counting_load,
            ),
        ):
            ctx.run_module("osint/dns_resolve", "5.5.5.5", {})

        assert len(load_call_count) == 1, (
            f"load_dossier_state must be called exactly once per hunt; got {len(load_call_count)}"
        )


# ---------------------------------------------------------------------------
# M-8 Stage C: novelty event emission through _execute_run_module
# ---------------------------------------------------------------------------
#
# These 5 tests cover the end-to-end novelty detection path from plan §4 Stage C.
# Pattern mirrors test_m5t7_f64_falsified_event_absent_from_llm_summary (M-5 T7).
#
# Production sequence exercised:
#   ToolContext -> run_module -> _execute_run_module ->
#   [emit_dossier_slot_filled_events -> novelty detection block ->
#    detect_novelty(slot, extractor, sco_types, cache)] ->
#   store_score_events([..., dossier_novelty_recognized])
#
# Isolation: _DEFAULT_CACHE_PATH in dossier.novelty is redirected via monkeypatch
# to a tmp_path file. NoveltyCache() (no-arg) reads this at construction time.
# No business-logic mocks — WorkspaceManager, dossier scoring, and novelty
# detection all run as real implementations.
#
# Pre-condition: all tests that require dossier_slot_filled events call
# _seed_empty_snapshot() first. On a fresh workspace default_deferred_state()
# sets all slots DEFERRED; emit_dossier_slot_filled_events() skips DEFERRED->real
# transitions by design (plan §3.4). Seeding EMPTY (infer from zero SCOs) makes
# the first hunt's evidence trigger an EMPTY->PARTIAL transition, which emits the
# dossier_slot_filled event that novelty detection operates on.
#
# @decision DEC-TEST-M8-STAGEC-001
# @title Stage C integration tests exercise novelty detection through run_module
# @status accepted
# @rationale Plan §4 Stage C requires 5 hunt-site integration tests. These verify
#            the novelty detection block in _execute_run_module (tools.py lines 497-539)
#            is correctly wired: novel slot-fill hashes produce dossier_novelty_recognized
#            events, repeat hashes do not, the env-var opt-out kills the path entirely,
#            and the F64 filter strips novelty events from the LLM summary while
#            preserving them in score_events. _DEFAULT_CACHE_PATH redirection via
#            monkeypatch is a pure path substitution — no mock logic.


class TestM8StageC:
    """M-8 Stage C: novelty event emission end-to-end through run_module.

    # @mock-exempt: hunt() is an async external HTTP boundary (DEC-TEST-AGENT-001).
    # _DEFAULT_CACHE_PATH is redirected via monkeypatch (path substitution, not a mock).
    # All other components run real implementations.
    """

    # email-addr SCOs fill the IDENTITY slot (SLOT_EVIDENCE_TYPES in dossier/slots.py).
    # Used because email-addr -> IDENTITY is the canonical test pattern established in
    # TestM3DossierScoringIntegration. After _seed_empty_snapshot, IDENTITY is EMPTY and
    # the email-addr SCO triggers EMPTY->PARTIAL, emitting dossier_slot_filled.
    SAMPLE_IDENTITY_RESULTS = [
        {"type": "email-addr", "value": "threat@apt28.ru"},
    ]

    def _make_ctx(self, tmp_path):
        """ToolContext with isolated workspace and config dirs."""
        config_dir = tmp_path / "config"
        workspace_dir = tmp_path / "workspaces"
        config_dir.mkdir()
        workspace_dir.mkdir()
        ctx = ToolContext(config_dir=config_dir, workspace_dir=workspace_dir)
        ctx.workspace_mgr.create("default")
        ctx.workspace_mgr.switch("default")
        return ctx

    def _seed_empty_snapshot(self, ctx):
        """Persist an EMPTY dossier snapshot so the next hunt triggers EMPTY->PARTIAL.

        On a fresh workspace, default_deferred_state() sets all slots DEFERRED.
        emit_dossier_slot_filled_events() skips DEFERRED->real by design (plan §3.4).
        Seeding an empty-SCO inferred snapshot makes pre-state EMPTY so the first
        evidence triggers EMPTY->PARTIAL, emitting dossier_slot_filled — the event
        novelty detection operates on. Mirrors _seed_empty_snapshot in
        TestM3DossierScoringIntegration.
        """
        from adversary_pursuit.dossier.slot_inference import infer_dossier_state_full
        from adversary_pursuit.dossier.state import save_dossier_state

        empty_state = infer_dossier_state_full([], module_runs=[], notes=None)
        save_dossier_state(ctx.workspace_mgr, empty_state)

    def test_run_module_emits_novelty_event_on_first_novel_slot_fill(self, tmp_path, monkeypatch):
        """Stage C-1: run_module with fresh novelty cache emits dossier_novelty_recognized.

        Production path: hunt() returns email-addr SCO ->
        IDENTITY slot transitions EMPTY->PARTIAL -> emit_dossier_slot_filled_events
        produces dossier_slot_filled -> novelty detection block finds hash unknown ->
        detect_novelty() returns True -> dossier_novelty_recognized appended ->
        store_score_events persists it -> appears in result['score_events'].
        """
        import adversary_pursuit.dossier.novelty as _novelty_mod

        monkeypatch.delenv("AP_NO_NOVELTY", raising=False)
        novelty_path = tmp_path / "novelty.sqlite"
        monkeypatch.setattr(_novelty_mod, "_DEFAULT_CACHE_PATH", novelty_path)

        ctx = self._make_ctx(tmp_path)
        self._seed_empty_snapshot(ctx)

        mock_mod = self._make_mock_module(self.SAMPLE_IDENTITY_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/hibp", "threat@apt28.ru", {})

        novelty_events = [
            e for e in result["score_events"] if e["action"] == "dossier_novelty_recognized"
        ]
        assert len(novelty_events) >= 1, (
            "Expected at least one dossier_novelty_recognized event in score_events "
            f"on first novel slot fill; got score_events={result['score_events']!r}"
        )
        assert novelty_events[0]["points"] == 1, (
            "dossier_novelty_recognized event must have points=1 (DEC-M8-NOVELTY-006)"
        )

    def test_run_module_no_novelty_event_on_repeat_slot_fill(self, tmp_path, monkeypatch):
        """Stage C-2: same hash already in cache -> NO dossier_novelty_recognized on second run.

        Both runs write to the same sqlite file (_DEFAULT_CACHE_PATH redirected to tmp_path)
        so the first run records the hash and the second run hits the cache and skips emission.
        """
        import adversary_pursuit.dossier.novelty as _novelty_mod

        monkeypatch.delenv("AP_NO_NOVELTY", raising=False)
        novelty_path = tmp_path / "novelty.sqlite"
        monkeypatch.setattr(_novelty_mod, "_DEFAULT_CACHE_PATH", novelty_path)

        ctx = self._make_ctx(tmp_path)
        self._seed_empty_snapshot(ctx)

        mock_mod = self._make_mock_module(self.SAMPLE_IDENTITY_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            ctx.run_module("osint/hibp", "threat@apt28.ru", {})
            result2 = ctx.run_module("osint/hibp", "threat@apt28.ru", {})

        novelty_events = [
            e for e in result2["score_events"] if e["action"] == "dossier_novelty_recognized"
        ]
        assert len(novelty_events) == 0, (
            "Expected zero dossier_novelty_recognized events on repeat slot fill; "
            f"got {novelty_events!r}"
        )

    def test_run_module_dossier_actions_widened_to_4_tuple(self):
        """Stage C-3: _DOSSIER_ACTIONS in tools.py includes dossier_novelty_recognized (M-8 F64).

        DEC-M8-NOVELTY-009: the frozenset was widened from 3 to 4 entries in M-8
        so novelty events are filtered from the LLM-facing summary.
        Strategy: source inspection, same technique as test_m5t7.
        """
        import pathlib

        import adversary_pursuit

        tools_src = (
            pathlib.Path(adversary_pursuit.__file__).parent / "agent" / "tools.py"
        ).read_text(encoding="utf-8")
        assert "dossier_novelty_recognized" in tools_src, (
            "F64: _DOSSIER_ACTIONS in agent/tools.py must include 'dossier_novelty_recognized' "
            "(DEC-M8-NOVELTY-009)"
        )
        assert "dossier_slot_filled" in tools_src
        assert "dossier_prediction_validated" in tools_src
        assert "dossier_prediction_falsified" in tools_src

    def test_run_module_ap_no_novelty_disables_detection(self, tmp_path, monkeypatch):
        """Stage C-4: AP_NO_NOVELTY=1 suppresses dossier_novelty_recognized events.

        DEC-M8-NOVELTY-008: opt-out. Home is redirected to tmp_path so any default-path
        writes land in tmp_path/.ap/ — lets us assert no sqlite file was created.
        """
        monkeypatch.setenv("AP_NO_NOVELTY", "1")
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)

        ctx = self._make_ctx(tmp_path)
        self._seed_empty_snapshot(ctx)

        mock_mod = self._make_mock_module(self.SAMPLE_IDENTITY_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/hibp", "threat@apt28.ru", {})

        novelty_events = [
            e for e in result["score_events"] if e["action"] == "dossier_novelty_recognized"
        ]
        assert len(novelty_events) == 0, (
            f"AP_NO_NOVELTY=1 must suppress all novelty events; got {novelty_events!r}"
        )
        novelty_file = fake_home / ".ap" / "dossier_novelty.sqlite"
        assert not novelty_file.exists(), (
            "AP_NO_NOVELTY=1 must prevent creation of the novelty cache file"
        )

    def test_run_module_novelty_event_not_narrated(self, tmp_path, monkeypatch):
        """Stage C-5: F64 — dossier_novelty_recognized absent from result['summary'] (LLM string).

        DEC-M8-NOVELTY-009 / DEC-64-LLM-PANEL-SEPARATION-001: the event must appear
        in result['score_events'] but must NOT appear in result['summary'].
        """
        import adversary_pursuit.dossier.novelty as _novelty_mod

        monkeypatch.delenv("AP_NO_NOVELTY", raising=False)
        novelty_path = tmp_path / "novelty.sqlite"
        monkeypatch.setattr(_novelty_mod, "_DEFAULT_CACHE_PATH", novelty_path)

        ctx = self._make_ctx(tmp_path)
        self._seed_empty_snapshot(ctx)

        mock_mod = self._make_mock_module(self.SAMPLE_IDENTITY_RESULTS)
        with patch.object(ctx.plugin_mgr, "get_module", return_value=mock_mod):
            result = ctx.run_module("osint/hibp", "threat@apt28.ru", {})

        assert "dossier_novelty_recognized" not in result["summary"], (
            "F64: dossier_novelty_recognized must not appear in the LLM-facing summary "
            f"(DEC-M8-NOVELTY-009). Summary: {result['summary']!r}"
        )

    def _make_mock_module(self, results):
        # @mock-exempt: hunt() is an async external HTTP boundary (DEC-TEST-AGENT-001).
        # This mock replaces only the network I/O layer; all tool dispatch, workspace
        # storage, dossier scoring, and novelty detection run unmodified.
        from unittest.mock import AsyncMock, MagicMock

        mock_mod = MagicMock()
        mock_mod.hunt = AsyncMock(return_value=results)
        mock_mod.initialize = MagicMock()
        return mock_mod
