"""AP module tools for the agent framework.

Each tool wraps an existing PursuitModule, handling initialization,
execution, result formatting, and workspace storage.

@decision DEC-AGENT-TOOLS-001
@title Thin tool wrappers delegating to existing PursuitModule infrastructure
@status accepted
@rationale The existing modules (whois, dns, abuseipdb, shodan, hibp, otx, urlscan,
           virustotal, censys_host, passivetotal) are already tested and working.
           Tool wrappers are thin adapters that: (1) accept simple string args
           from the LLM, (2) initialize the module with config, (3) call hunt(),
           (4) format + store results. No business logic duplication.

@decision DEC-AGENT-TOOLS-002
@title OpenAI function-calling format for tool definitions
@status accepted
@rationale The OpenAI function-calling schema (list of {type, function: {name,
           description, parameters}}) is now the de facto standard. litellm
           passes this format to every supported LLM provider, translating as
           needed. By producing tool definitions in this format, the tool layer
           is compatible with any litellm-supported backend (Ollama, OpenAI,
           Anthropic, etc.) without changes.

@decision DEC-AGENT-TOOLS-003
@title Per-module credential builders for multi-key auth modules
@status accepted
@rationale Most modules use a single api_key, but Censys requires censys_id +
           censys_secret and PassiveTotal requires passivetotal_user +
           passivetotal_key. _CREDENTIAL_BUILDERS maps module paths to callables
           that construct the full init_config dict from ConfigManager. Modules
           not in the map fall back to the legacy {"api_key": ...} pattern.
           This keeps run_module() generic while correctly threading multi-key
           credentials to modules that need them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from adversary_pursuit.core.config import ConfigManager
from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.core.workspace import WorkspaceManager
from adversary_pursuit.gamification.badges import BadgeManager
from adversary_pursuit.gamification.celebrations import CelebrationEngine
from adversary_pursuit.gamification.modes import ModeManager
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
        self.celebration = CelebrationEngine()
        self.badge_mgr = BadgeManager()
        self.mode_mgr = ModeManager()
        # Tracks badge IDs awarded in this session (application-layer dedup, DEC-BADGE-002).
        # Populated from workspace on first badge check; updated as badges are earned.
        self._awarded_badges: set[str] = set()

    def run_module(self, module_path: str, target: str, options: dict = None) -> dict:
        """Run a module and return formatted results with scoring.

        Dispatches to the named PursuitModule, runs hunt(), stores results in
        the workspace, applies scoring, computes the celebration artifact, and
        returns a summary dict.

        @decision DEC-AGENT-CELEBRATIONS-001
        @title CelebrationEngine wired into run_module return value
        @status accepted
        @rationale The cmd2 console renders celebrations in _execute_hunt() after
                   scoring. The agent path must surface the same visual feedback to
                   users. Rather than rendering inside run_module (which has no
                   console reference), the celebration string is computed here and
                   returned under the "celebration" key so the caller (execute_tool,
                   chat.py REPL) can render it at the appropriate display boundary.
                   Keeping computation in run_module means tests can assert the
                   artifact without mocking the Rich console.
                   Silent path: celebration is None when total_points == 0 (no
                   scoring events), matching the cmd2 path which only shows
                   celebration when scoring_events is non-empty.
                   Milestone messages are computed against the post-storage total
                   score and appended to the celebration string when they fire.

        @decision DEC-AGENT-BADGES-001
        @title BadgeManager wired into run_module after scoring, mirroring cmd2 _check_badges_after_run
        @status accepted
        @rationale cmd2 APConsole._check_badges_after_run() calls BadgeManager.check_all()
                   after each module execution, persists newly-earned badge events via
                   workspace_mgr.store_badge_event(), and renders a Rich panel per badge.
                   The agent path mirrors this exactly: (1) build already_awarded from the
                   workspace using get_awarded_badges() on first check then from the session
                   cache _awarded_badges thereafter for dedup; (2) call check_all() against
                   get_workspace_stats(); (3) persist via store_badge_event(); (4) return the
                   newly-earned Badge list under "badges" key so execute_tool can thread it
                   to chat.py for Rich panel rendering.
                   Silent path: badges is [] when no new badges earned, matching cmd2
                   behaviour which only renders panels when newly_earned is non-empty.
                   _awarded_badges set is seeded lazily from the workspace on first call
                   so sessions that resume mid-investigation do not re-award old badges.

        @decision DEC-AGENT-MODES-001
        @title ModeManager wired into ToolContext; mode affects celebration text and LLM persona
        @status accepted
        @rationale Three integration points for character modes in the agent path:
                   (1) ToolContext holds a ModeManager instance (parallel to BadgeManager,
                   CelebrationEngine) so mode state is scoped to the agent session, not
                   imported as a global — matches cmd2 APConsole.mode_mgr pattern.
                   (2) run_module celebration: CelebrationEngine produces the ASCII art;
                   mode_mgr.active.score_celebration.format(points=total) appends the
                   mode-specific points line, mirroring console.py _execute_hunt() which
                   uses the same template call. The field is named 'personality' on
                   CharacterMode (not 'persona_prompt' as the plan draft said).
                   (3) LLM persona: AgentRunner.set_character(mode) prepends mode.personality
                   to the default system prompt. chat.py 'mode <name>' meta-command calls
                   ModeManager.switch(name) then runner.set_character(active_mode) so the
                   LLM voice changes immediately without resetting conversation history beyond
                   the system message slot (conversation[0]).

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
            celebration (str | None): ASCII art celebration string, or None
                when no points were awarded (silent path).
            badges (list[Badge]): newly-earned Badge objects this run, or []
                when no new badges earned (silent path).

        Returns {"error": str} if the module is not found.
        """
        mod = self.plugin_mgr.get_module(module_path)
        if mod is None:
            return {"error": f"Module '{module_path}' not found"}

        # Build init_config for this module. Most modules use a single api_key;
        # multi-key modules (Censys, PassiveTotal) use _CREDENTIAL_BUILDERS.
        # See DEC-AGENT-TOOLS-003.
        credential_builder = _CREDENTIAL_BUILDERS.get(module_path)
        if credential_builder is not None:
            init_config = credential_builder(self.config_mgr)
        else:
            # Legacy path: "osint/abuseipdb" -> service "abuseipdb"
            service_name = module_path.split("/")[-1]
            api_key = self.config_mgr.get_api_key(service_name) or ""
            init_config = {"api_key": api_key}
        mod.initialize(init_config)

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

        # Compute celebration artifact (DEC-AGENT-CELEBRATIONS-001, DEC-AGENT-MODES-001).
        # The ASCII art comes from CelebrationEngine. The points line uses the active
        # mode's score_celebration template (str.format(points=N)) so the character
        # voice matches the chosen persona — mirrors console.py _execute_hunt().
        # Silent path: no celebration when no points awarded.
        celebration: str | None = None
        if total > 0:
            art = self.celebration.celebrate(total)
            mode_points_line = self.mode_mgr.active.score_celebration.format(
                points=total
            )
            celebration = art + "\n" + mode_points_line
            # Check milestone against post-storage total score
            try:
                post_total = self.workspace_mgr.get_total_score()
                milestone = self.celebration.milestone_message(post_total)
                if milestone:
                    celebration = celebration + "\n\n" + milestone
            except Exception:  # noqa: BLE001
                pass  # milestone check must never block tool result delivery

        # Check badges after scoring (DEC-AGENT-BADGES-001).
        # Mirrors cmd2 APConsole._check_badges_after_run() exactly:
        # build already_awarded, evaluate all badges, persist new ones.
        # Lazy-seed _awarded_badges from workspace on first call so sessions
        # resuming mid-investigation don't re-award previously earned badges.
        newly_earned_badges: list = []
        try:
            if not self._awarded_badges:
                # Seed from workspace: captures any badges earned by prior sessions
                awarded_rows = self.workspace_mgr.get_awarded_badges()
                self._awarded_badges = {row["badge_id"] for row in awarded_rows}
            badge_stats = self.workspace_mgr.get_workspace_stats()
            newly_earned_badges = self.badge_mgr.check_all(
                badge_stats, already_awarded=self._awarded_badges
            )
            for badge in newly_earned_badges:
                self.workspace_mgr.store_badge_event(badge.id, badge.name)
                self._awarded_badges.add(badge.id)
        except Exception:  # noqa: BLE001
            pass  # badge check must never block tool result delivery

        # Build human-readable summary for the LLM response
        summary_lines = [f"Found {count} indicators:"]
        for r in results[:10]:
            summary_lines.append(f"  {r.get('type', '?')}: {r.get('value', '?')}")
        if len(results) > 10:
            summary_lines.append(f"  ... and {len(results) - 10} more")
        if total > 0:
            summary_lines.append(f"\n+{total} points!")
            for e in events:
                summary_lines.append(
                    f"  {e['action']}: +{e['points']} ({e['indicator']})"
                )
        if newly_earned_badges:
            summary_lines.append("\nBadge(s) earned:")
            for badge in newly_earned_badges:
                summary_lines.append(
                    f"  [{badge.rarity.value.upper()}] {badge.name}: {badge.description}"
                )

        return {
            "results": results,
            "score_events": events,
            "total_points": total,
            "summary": "\n".join(summary_lines),
            "celebration": celebration,
            "badges": newly_earned_badges,
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
        12 tool definitions covering all built-in AP modules plus workspace ops.
        7 OSINT/CTI modules + VT + Censys + PassiveTotal + 2 workspace tools.
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
        # -----------------------------------------------------------------------
        # Three new tools added in Issue #25 / ADR-010 parity slice:
        # VirusTotal (#7), Censys (#8), PassiveTotal (#13)
        # -----------------------------------------------------------------------
        {
            "type": "function",
            "function": {
                "name": "virustotal_lookup",
                "description": (
                    "Query VirusTotal v3 for threat analysis of an IP, domain, URL, or "
                    "file hash. Returns malicious/suspicious/harmless vendor counts, "
                    "reputation score, and AS/country for IPs and domains. "
                    "Target type is auto-detected from the input."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": (
                                "IP address, domain, URL, or file hash (MD5/SHA-1/SHA-256)"
                            ),
                        },
                        "target_type": {
                            "type": "string",
                            "description": (
                                "Override auto-detection: ip, domain, url, or hash. "
                                "Leave empty for auto-detection."
                            ),
                            "default": "",
                        },
                    },
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "censys_host_lookup",
                "description": (
                    "Query Censys for host intelligence on an IP address. "
                    "Returns open services (port/protocol/service_name), OS fingerprint, "
                    "geolocation country, autonomous system, TLS certificate fingerprints, "
                    "and last-updated timestamp."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ip_address": {
                            "type": "string",
                            "description": "IPv4 address to query",
                        },
                    },
                    "required": ["ip_address"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "passivetotal_lookup",
                "description": (
                    "Query PassiveTotal/RiskIQ for passive DNS records and WHOIS history "
                    "on a domain or IP. Returns first/last seen, total DNS record count, "
                    "related resolved IPs/domains, and optional WHOIS registrant details."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Domain or IP address to query",
                        },
                        "include_whois": {
                            "type": "boolean",
                            "description": "Include WHOIS history (default: true)",
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
# Credential builders for multi-key auth modules (DEC-AGENT-TOOLS-003)
# ---------------------------------------------------------------------------

# Maps module_path -> callable(ConfigManager) -> init_config dict.
# Only modules that require credentials beyond a single "api_key" field
# are listed here. run_module() falls back to {"api_key": ...} for all others.
_CREDENTIAL_BUILDERS: dict[str, Any] = {
    "osint/censys_host": lambda cfg: {
        "censys_id": cfg.get_api_key("censys_id") or "",
        "censys_secret": cfg.get_api_key("censys_secret") or "",
    },
    "cti/passivetotal": lambda cfg: {
        "passivetotal_user": cfg.get_api_key("passivetotal_user") or "",
        "passivetotal_key": cfg.get_api_key("passivetotal_key") or "",
    },
}

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
    # New entries — VT/Censys/PassiveTotal parity with cmd2 console
    "virustotal_lookup": (
        "cti/virustotal",
        lambda a: (a["target"], {"TARGET_TYPE": a.get("target_type", "")}),
    ),
    "censys_host_lookup": (
        "osint/censys_host",
        lambda a: (a["ip_address"], {}),
    ),
    "passivetotal_lookup": (
        "cti/passivetotal",
        lambda a: (
            a["target"],
            {"INCLUDE_WHOIS": str(a.get("include_whois", True)).lower()},
        ),
    ),
}


def execute_tool(
    ctx: ToolContext, tool_name: str, arguments: dict
) -> tuple[str, str | None, list]:
    """Execute a tool call and return (summary, celebration, badges).

    This is the dispatcher that maps LLM tool call names to module invocations.
    The summary string is suitable for inclusion in the LLM conversation as a
    "tool" role message. The celebration string is ASCII art for the user
    terminal (None when no points were awarded — silent path). The badges list
    contains newly-earned Badge objects for Rich panel rendering in chat.py
    ([] when no new badges earned — silent path).

    Workspace meta-tools (get_workspace_summary, search_workspace) always
    return celebration=None and badges=[] because they do not trigger scoring
    or badge evaluation.

    @decision DEC-AGENT-BADGES-001
    (see run_module docstring for full rationale)
    Triple return chosen over a unified user_messages list because celebration
    (plain string) and badges (Badge objects with rarity metadata for styled
    panels) have different rendering logic at the chat.py boundary. Keeping
    them as separate typed values preserves testability and avoids conflating
    two distinct display artifacts into an untyped list.

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
    tuple[str, str | None, list]
        (summary, celebration, badges) where summary is the LLM-facing result
        string, celebration is the ASCII art to display to the user or None,
        and badges is a list of newly-earned Badge objects ([] when none).
        Returns (error_string, None, []) when the tool fails — errors are
        reported to the LLM as tool results.
    """
    # Workspace meta-tools — no scoring, no celebration, no badge check
    if tool_name == "get_workspace_summary":
        return _workspace_summary(ctx), None, []

    if tool_name == "search_workspace":
        return _search_workspace(ctx, arguments.get("type_filter")), None, []

    # Module dispatch
    if tool_name not in _MODULE_MAP:
        return f"Unknown tool: {tool_name}", None, []

    module_path, arg_mapper = _MODULE_MAP[tool_name]
    try:
        target, options = arg_mapper(arguments)
        result = ctx.run_module(module_path, target, options)
        if "error" in result:
            return f"Error: {result['error']}", None, []
        return result["summary"], result.get("celebration"), result.get("badges", [])
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return f"Error running {tool_name}: {e}", None, []


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
