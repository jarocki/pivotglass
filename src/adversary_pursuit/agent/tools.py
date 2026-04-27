"""AP module tools for the agent framework.

Each tool wraps an existing PursuitModule, handling initialization,
execution, result formatting, and workspace storage.

@decision DEC-AGENT-TOOLS-001
@title Thin tool wrappers delegating to existing PursuitModule infrastructure
@status accepted
@rationale The existing modules (whois, dns, abuseipdb, shodan, hibp, otx, urlscan)
           are already tested and working. Tool wrappers are thin adapters that:
           (1) accept simple string args from the LLM, (2) initialize the module
           with config, (3) call hunt(), (4) format + store results. No business
           logic duplication.

@decision DEC-AGENT-TOOLS-002
@title OpenAI function-calling format for tool definitions
@status accepted
@rationale The OpenAI function-calling schema (list of {type, function: {name,
           description, parameters}}) is now the de facto standard. litellm
           passes this format to every supported LLM provider, translating as
           needed. By producing tool definitions in this format, the tool layer
           is compatible with any litellm-supported backend (Ollama, OpenAI,
           Anthropic, etc.) without changes.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.gamification.scoring import ScoringEngine

logger = logging.getLogger(__name__)


class ToolContext:
    """Shared context for all tools — config, workspace, scoring, plugins.

    A single ToolContext is created per agent session and shared across
    all tool invocations. This ensures workspace state accumulates correctly
    across multiple tool calls in one conversation.

    Parameters
    ----------
    config_dir:
        Path to config directory. Defaults to ~/.ap. Pass tmp_path in tests.
    workspace_dir:
        Path to workspace directory. Defaults to ~/.ap/workspaces.
        Pass tmp_path in tests.
    """

    def __init__(self, config_dir=None, workspace_dir=None):
        self.config_mgr = ConfigManager(config_dir=config_dir)
        self.config = self.config_mgr.load()
        self.workspace_mgr = WorkspaceManager(workspace_dir=workspace_dir)
        self.plugin_mgr = PluginManager()
        self.plugin_mgr.load_plugins()
        self.scoring = ScoringEngine()

    def run_module(self, module_path: str, target: str, options: dict = None) -> dict:
        """Run a module and return formatted results with scoring.

        Dispatches to the named PursuitModule, runs hunt(), stores results in
        the workspace, applies scoring, and returns a summary dict.

        Parameters
        ----------
        module_path:
            Canonical module path, e.g. "osint/abuseipdb".
        target:
            The target string (IP, domain, URL, email) to hunt.
        options:
            Optional options dict passed to hunt(). Defaults to {}.

        Returns
        -------
        dict with keys:
            results (list[dict]): raw hunt() output
            score_events (list[dict]): scoring events generated
            total_points (int): total points awarded
            summary (str): human-readable summary for the LLM

        Returns {"error": str} if the module is not found.
        """
        mod = self.plugin_mgr.get_module(module_path)
        if mod is None:
            return {"error": f"Module '{module_path}' not found"}

        # Determine service name for API key lookup:
        # "osint/abuseipdb" -> "abuseipdb", "cti/otx" -> "otx"
        service_name = module_path.split("/")[-1]
        api_key = self.config_mgr.get_api_key(service_name) or ""
        mod.initialize({"api_key": api_key})

        # Run hunt() via asyncio — modules are async
        results = asyncio.run(mod.hunt(target, options or {}))

        # Store in workspace (auto-creates default if none active)
        count = self.workspace_mgr.store_stix_objects(results, module_path, target)

        # Score using current workspace state
        stats = self.workspace_mgr.get_stix_type_counts()
        events = self.scoring.score_results(results, stats)
        total = self.scoring.total_score(events)
        if events:
            self.workspace_mgr.store_score_events(events)

        # Build human-readable summary for the LLM response
        summary_lines = [f"Found {count} indicators:"]
        for r in results[:10]:
            summary_lines.append(f"  {r.get('type', '?')}: {r.get('value', '?')}")
        if len(results) > 10:
            summary_lines.append(f"  ... and {len(results) - 10} more")
        if total > 0:
            summary_lines.append(f"\n+{total} points!")
            for e in events:
                summary_lines.append(f"  {e['action']}: +{e['points']} ({e['indicator']})")

        return {
            "results": results,
            "score_events": events,
            "total_points": total,
            "summary": "\n".join(summary_lines),
        }


def create_tools(ctx: ToolContext) -> list[dict]:
    """Create tool definitions for the agent.

    Returns a list of tool dicts in OpenAI function-calling format:
    [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]

    The ctx parameter is accepted for interface consistency (future tools may
    need dynamic schema generation based on loaded modules).

    Parameters
    ----------
    ctx:
        The shared ToolContext (used for future dynamic tool generation).

    Returns
    -------
    list[dict]
        9 tool definitions covering all built-in AP modules plus workspace ops.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "dns_resolve",
                "description": (
                    "Resolve DNS records for a domain. "
                    "Returns IP addresses and domain information."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Domain name to resolve",
                        },
                        "record_type": {
                            "type": "string",
                            "description": "DNS record type (A, AAAA, MX, NS, TXT)",
                            "default": "A",
                        },
                    },
                    "required": ["domain"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "whois_lookup",
                "description": (
                    "WHOIS lookup for domain or IP. "
                    "Returns registration details, registrant info, creation/expiry dates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Domain or IP to look up",
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_ip_reputation",
                "description": (
                    "Check IP address reputation via AbuseIPDB. "
                    "Returns abuse confidence score, ISP, usage type, report count."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ip_address": {
                            "type": "string",
                            "description": "IP address to check",
                        },
                        "max_age_days": {
                            "type": "integer",
                            "description": "Max age of reports in days (1-365)",
                            "default": 90,
                        },
                    },
                    "required": ["ip_address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "shodan_host_lookup",
                "description": (
                    "Query Shodan for IP host information including open ports, "
                    "services, OS, vulnerabilities (CVEs), and hostnames."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ip_address": {
                            "type": "string",
                            "description": "IP address to query",
                        },
                        "minify": {
                            "type": "boolean",
                            "description": "Return only basic info",
                            "default": False,
                        },
                    },
                    "required": ["ip_address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_breaches",
                "description": (
                    "Check email address against HaveIBeenPwned breach database. "
                    "Returns breach names, dates, and exposed data types."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "email": {
                            "type": "string",
                            "description": "Email address to check",
                        },
                    },
                    "required": ["email"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "otx_threat_intel",
                "description": (
                    "Query AlienVault OTX for threat intelligence on an IP or domain. "
                    "Returns pulse data, reputation, and passive DNS."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "IP address or domain to query",
                        },
                        "include_passive_dns": {
                            "type": "boolean",
                            "description": "Include passive DNS results",
                            "default": True,
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scan_url",
                "description": (
                    "Submit a URL to URLScan.io for analysis. "
                    "Returns page details, contacted IPs/domains, and screenshot URL."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to scan",
                        },
                        "visibility": {
                            "type": "string",
                            "description": "Scan visibility: public, unlisted, private",
                            "default": "unlisted",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_workspace_summary",
                "description": (
                    "Get a summary of the current workspace — total indicators, "
                    "types, module runs, score, and recent activity."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_workspace",
                "description": (
                    "Search the current workspace for STIX objects by type or value."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "type_filter": {
                            "type": "string",
                            "description": (
                                "STIX type to filter by "
                                "(ipv4-addr, domain-name, url, email-addr)"
                            ),
                        },
                    },
                },
            },
        },
    ]


# ---------------------------------------------------------------------------
# Module → tool name mapping
# ---------------------------------------------------------------------------

# Maps tool name -> (module_path, arg_extractor)
# arg_extractor is a callable that takes the arguments dict and returns
# (target: str, options: dict) for run_module().
_MODULE_MAP: dict[str, tuple[str, Any]] = {
    "dns_resolve": (
        "osint/dns_resolve",
        lambda a: (a["domain"], {"RECORD_TYPE": a.get("record_type", "A")}),
    ),
    "whois_lookup": (
        "osint/whois_lookup",
        lambda a: (a["target"], {}),
    ),
    "check_ip_reputation": (
        "osint/abuseipdb",
        lambda a: (a["ip_address"], {"MAX_AGE": str(a.get("max_age_days", 90))}),
    ),
    "shodan_host_lookup": (
        "osint/shodan_ip",
        lambda a: (a["ip_address"], {"MINIFY": str(a.get("minify", False)).lower()}),
    ),
    "check_breaches": (
        "osint/hibp",
        lambda a: (a["email"], {}),
    ),
    "otx_threat_intel": (
        "cti/otx",
        lambda a: (
            a["target"],
            {"INCLUDE_PASSIVE_DNS": str(a.get("include_passive_dns", True)).lower()},
        ),
    ),
    "scan_url": (
        "osint/urlscan",
        lambda a: (a["url"], {"VISIBILITY": a.get("visibility", "unlisted")}),
    ),
}


def execute_tool(ctx: ToolContext, tool_name: str, arguments: dict) -> str:
    """Execute a tool call and return the result as a string.

    This is the dispatcher that maps LLM tool call names to module invocations.
    All results are formatted as strings suitable for inclusion in the LLM
    conversation as a "tool" role message.

    Parameters
    ----------
    ctx:
        The shared ToolContext providing workspace, modules, and scoring.
    tool_name:
        Name of the tool to execute (matches names in create_tools()).
    arguments:
        Dict of arguments from the LLM tool call.

    Returns
    -------
    str
        Human-readable result string. Returns an error string (not raises)
        when the tool fails — errors are reported to the LLM as tool results.
    """
    # Workspace meta-tools
    if tool_name == "get_workspace_summary":
        return _workspace_summary(ctx)

    if tool_name == "search_workspace":
        return _search_workspace(ctx, arguments.get("type_filter"))

    # Module dispatch
    if tool_name not in _MODULE_MAP:
        return f"Unknown tool: {tool_name}"

    module_path, arg_mapper = _MODULE_MAP[tool_name]
    try:
        target, options = arg_mapper(arguments)
        result = ctx.run_module(module_path, target, options)
        if "error" in result:
            return f"Error: {result['error']}"
        return result["summary"]
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return f"Error running {tool_name}: {e}"


def _workspace_summary(ctx: ToolContext) -> str:
    """Generate a workspace summary string for the LLM.

    Returns a multi-line string with workspace name, indicator count,
    score, module runs, and per-type breakdown.
    """
    try:
        objects = ctx.workspace_mgr.get_stix_objects()
        runs = ctx.workspace_mgr.get_module_runs()
        score = ctx.workspace_mgr.get_total_score()
        counts = ctx.workspace_mgr.get_stix_type_counts()

        lines = [
            f"Workspace: {ctx.workspace_mgr.active}",
            f"Total indicators: {len(objects)}",
            f"Total score: {score}",
            f"Module runs: {len(runs)}",
        ]
        if counts:
            lines.append("By type:")
            for t, c in sorted(counts.items()):
                lines.append(f"  {t}: {c}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Failed to get workspace summary")
        return f"Error getting workspace summary: {e}"


def _search_workspace(ctx: ToolContext, type_filter: str | None = None) -> str:
    """Search workspace STIX objects and return a formatted string.

    Parameters
    ----------
    ctx:
        The shared ToolContext.
    type_filter:
        Optional STIX type to filter by (e.g. "ipv4-addr").

    Returns
    -------
    str
        Formatted list of matching objects, or a 'no results' message.
    """
    try:
        objects = ctx.workspace_mgr.get_stix_objects(type_filter=type_filter)
        if not objects:
            label = type_filter or "objects"
            return f"No {label} found in workspace."
        lines = [f"Found {len(objects)} {type_filter or 'objects'}:"]
        for obj in objects[:20]:
            lines.append(f"  {obj.get('type', '?')}: {obj.get('value', '?')}")
        if len(objects) > 20:
            lines.append(f"  ... and {len(objects) - 20} more")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("Failed to search workspace")
        return f"Error searching workspace: {e}"
