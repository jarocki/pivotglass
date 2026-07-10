"""Agent runner for conversational CTI interface.

Manages the LLM interaction loop: user message → tool calls → response.
Supports multiple LLM backends via litellm.

@decision DEC-AGENT-RUNNER-001
@title litellm for LLM backend abstraction instead of direct smolagents
@status accepted
@rationale litellm provides a unified interface to 100+ LLM providers (local
           Ollama/vLLM, OpenAI, Anthropic, etc.) with OpenAI-compatible
           function-calling. This gives users maximum flexibility in choosing
           their LLM backend. smolagents' CodeAgent approach is powerful but
           adds complexity; the simpler tool-calling pattern via litellm is
           sufficient for AP's needs and easier to test.

@decision DEC-AGENT-RUNNER-002
@title Graceful ImportError when litellm not installed
@status accepted
@rationale litellm is in [project.optional-dependencies.agent], not core deps.
           The tool layer (tools.py) must work without it. AgentRunner raises
           a clear ImportError at .chat() time (not import time) so the module
           can always be imported and instantiated — the error only surfaces
           when the user actually tries to chat. This pattern matches how
           optional features are handled throughout the codebase.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from adversary_pursuit.core.config import ConfigManager

logger = logging.getLogger(__name__)

# Try litellm first — optional dependency
try:
    import litellm

    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

from adversary_pursuit.agent.tools import ToolContext, create_tools, execute_tool  # noqa: E402
from adversary_pursuit.gamification.modes import CharacterMode  # noqa: E402

# ---------------------------------------------------------------------------
# StatusHook protocol and NullStatusHook default
# ---------------------------------------------------------------------------
# @decision DEC-STATUS-ACTIVITY-WIRING-001
# @title _StatusHook Protocol for decoupling runner from Rich imports
# @status accepted
# @rationale runner.py must not import Rich directly — it is a library module
#            used in non-Rich contexts (tests, cmd2 console). The Protocol lets
#            StatusBar from banner.py satisfy the interface without a hard import.
#            NullStatusHook (_NULL_STATUS_HOOK singleton) is the default so every
#            call site in chat() is unconditional — no "if status_bar is not None"
#            guards scattered across the hot path. Sacred Practice 12: one authority
#            (PHRASES via StatusBar.set_activity) and one call pattern.
#            The slug-mapping helper (_status_slug_for_tool) is colocated with the
#            wiring so future tool additions only require one dict update, not
#            two separate files.


@runtime_checkable
class _StatusHook(Protocol):
    """Minimal interface for a status bar hook.

    StatusBar in banner.py satisfies this protocol. NullStatusHook below is
    the no-op default.  The runner depends only on this protocol — no Rich
    import required at runner.py level.
    """

    def set_activity(self, tool_slug: str | None) -> None:
        """Set the current tool-activity slug, or None to revert to idle."""
        ...

    def set_battery(self, name: str | None) -> None:
        """Set the current active battery name, or None when idle."""
        ...

    def set_hypothesis(self, text: str | None) -> None:
        """Set the current hypothesis text."""
        ...


class NullStatusHook:
    """No-op _StatusHook used when no status bar is active.

    A single module-level instance (_NULL_STATUS_HOOK) is the default so the
    runner never needs ``if status_bar is not None:`` guards.
    """

    def set_activity(self, tool_slug: str | None) -> None:  # noqa: ARG002
        """No-op: silently ignore all activity updates."""

    def set_battery(self, name: str | None) -> None:  # noqa: ARG002
        """No-op."""

    def set_hypothesis(self, text: str | None) -> None:  # noqa: ARG002
        """No-op."""


_NULL_STATUS_HOOK: NullStatusHook = NullStatusHook()


# ---------------------------------------------------------------------------
# Tool-name → activity-slug mapping
# ---------------------------------------------------------------------------

# Maps every LLM-facing tool name (from create_tools) to the status-bar
# activity slug used in pick(character, "activity:<slug>").
# Keys must stay in sync with the tool names in tools.py:create_tools().
# When a new tool is added, add an entry here; the test
# test_all_registered_tools_covered will fail loudly if the mapping drifts.
_TOOL_SLUG_MAP: dict[str, str] = {
    "dns_resolve": "dns_resolve",
    "whois_lookup": "whois",
    "check_ip_reputation": "check_ip_reputation",
    "shodan_host_lookup": "shodan",
    "check_breaches": "check_breaches",
    "otx_threat_intel": "otx",
    "scan_url": "scan_url",
    "virustotal_lookup": "virustotal",
    "censys_host_lookup": "censys_host_lookup",
    "passivetotal_lookup": "passivetotal_lookup",
    "greynoise_lookup": "greynoise_lookup",
    "urlhaus_lookup": "urlhaus_lookup",
    "threatfox_lookup": "threatfox",
    "malwarebazaar_lookup": "malwarebazaar_lookup",
    "crtsh_lookup": "crtsh_lookup",
    # workspace / meta tools — all use "default_tool" slug (no activity phrase)
    "get_workspace_summary": "default_tool",
    "search_workspace": "default_tool",
    "get_next_hint": "default_tool",
    "buy_hint": "default_tool",
    "list_challenges": "default_tool",
    "check_challenges": "default_tool",
    "render_graph": "default_tool",
    "export_workspace": "default_tool",
    "get_dossier_state": "default_tool",
    "create_dossier_prediction": "default_tool",
    "create_dossier_note": "default_tool",
    "falsify_dossier_prediction": "default_tool",
    "generate_dossier_report": "default_tool",
    "export_dossier": "default_tool",
    "compare_dossier": "default_tool",
}


def _status_slug_for_tool(tool_name: str) -> str:
    """Return the activity slug for *tool_name*, falling back to ``'default_tool'``.

    The slug is used as the ``activity:<slug>`` phrase category key in the
    phrases cache (DEC-PHRASE-CACHE-001). Unknown tool names are logged at
    DEBUG and return ``'default_tool'`` so new tools degrade gracefully while
    the test ``test_all_registered_tools_covered`` catches the gap loudly
    (Sacred Practice 5 — fail loud where it matters, degrade gracefully at
    runtime).

    Parameters
    ----------
    tool_name:
        LLM-facing tool name as registered in ``create_tools()``.

    Returns
    -------
    str
        Activity slug string, always non-empty.
    """
    slug = _TOOL_SLUG_MAP.get(tool_name)
    if slug is None:
        logger.debug(
            "No activity slug mapping for tool %r — using 'default_tool'. "
            "Add an entry to _TOOL_SLUG_MAP to suppress this warning.",
            tool_name,
        )
        return "default_tool"
    return slug


class AgentRunner:
    """Orchestrates conversational CTI interactions.

    Manages the loop:
    user message → LLM → tool calls → tool results → LLM → response.

    The runner supports multiple LLM backends via litellm. The default model
    is a local Ollama model, requiring no API key. Set model to any
    litellm-supported string (e.g. "gpt-4o", "claude-3-5-sonnet-20241022",
    "ollama/qwen2.5:8b").

    Model selection precedence (highest to lowest):
      1. Explicit ``model=`` argument passed to ``__init__``
      2. ``AP_MODEL`` environment variable
      3. ``config_mgr.get_agent_model()`` — saved via interactive wizard
      4. ``DEFAULT_MODEL`` class constant (``ollama/qwen2.5:8b``)

    Parameters
    ----------
    model:
        litellm model string. When provided, takes precedence over AP_MODEL,
        config, and DEFAULT_MODEL.
    tool_context:
        Shared ToolContext. Created automatically if not provided.
    system_prompt:
        Override the default system prompt.
    config_mgr:
        Optional ConfigManager for reading/writing provider and model config.
        When provided, the config layer is checked in the model precedence
        chain and API keys are injected into litellm calls.
    """

    DEFAULT_MODEL = "ollama/qwen2.5:8b"  # Local default via Ollama

    def __init__(
        self,
        model: str | None = None,
        tool_context: ToolContext | None = None,
        system_prompt: str | None = None,
        config_mgr: ConfigManager | None = None,
    ) -> None:
        # @decision DEC-AGENT-MODEL-ENV-001
        # @title AP_MODEL env-var and config.toml override for runner model selection
        # @status accepted
        # @rationale Precedence chain (highest → lowest):
        #   1. explicit model= arg — tests and programmatic callers retain full control.
        #   2. AP_MODEL env var — operator/user runtime override without file edits.
        #   3. config_mgr.get_agent_model() — selection persisted by the interactive
        #      wizard; lives in ~/.ap/config.toml (chmod 0600).
        #   4. DEFAULT_MODEL — zero-config local fallback (Ollama).
        #   Empty-string AP_MODEL and empty-string config values are treated as unset
        #   because Python's `or` chain skips falsy values — consistent with the rest of
        #   the codebase. The config layer is skipped when config_mgr is None so that
        #   existing callers that don't pass config_mgr are unaffected.
        self._config_mgr = config_mgr
        self.model = (
            model
            or os.environ.get("AP_MODEL")
            or (config_mgr.get_agent_model() if config_mgr is not None else None)
            or self.DEFAULT_MODEL
        )
        self.ctx = tool_context or ToolContext()
        self.tools = create_tools(self.ctx)
        self.conversation: list[dict] = []
        self.system_prompt = system_prompt or self._default_system_prompt()

        # Initialize conversation with system prompt
        self.conversation.append({"role": "system", "content": self.system_prompt})

    def _default_system_prompt(self) -> str:
        """Return the default system prompt for the AP agent."""
        return (
            "You are Adversary Pursuit, a gamified cyber threat intelligence assistant.\n\n"
            "You help analysts investigate threats by querying OSINT and CTI data sources. "
            "You have access to tools for DNS resolution, WHOIS lookups, IP reputation checks "
            "(AbuseIPDB, Shodan), email breach checks (HIBP), threat intelligence (OTX), "
            "and URL scanning (URLScan.io).\n\n"
            "When a user asks about an indicator (IP, domain, URL, email), use the appropriate "
            "tools to gather intelligence. Combine results from multiple sources for comprehensive "
            "analysis. Store everything in the workspace for the investigation record.\n\n"
            "Be concise but thorough. Present findings in a clear, structured way. Highlight "
            "anything suspicious or noteworthy. When you see patterns across multiple indicators, "
            "point them out."
        )

    def chat(self, user_message: str, status_bar: "_StatusHook | None" = None) -> str:
        """Process a user message and return the agent's response.

        Handles the full loop: message → LLM → tool calls → results → LLM → response.
        Supports up to 5 rounds of tool calling per message.

        Parameters
        ----------
        user_message:
            The user's input message.
        status_bar:
            Optional status hook that receives ``set_activity(slug)`` before each
            tool call and ``set_activity(None)`` after.  When None, a
            ``NullStatusHook`` is used so there are no None-guards in the hot
            path (DEC-STATUS-ACTIVITY-WIRING-001).  Pass the ``StatusBar``
            instance from ``banner.py`` at the call site in ``chat.py``.

        Returns
        -------
        str
            The agent's final text response.

        Raises
        ------
        ImportError
            If litellm is not installed.
        """
        if not HAS_LITELLM:
            raise ImportError(
                "litellm is required for the conversational interface. "
                "Install it with: uv pip install 'adversary-pursuit[agent]'"
            )

        # Resolve hook — NullStatusHook eliminates None-check guards below.
        _hook: _StatusHook = status_bar if status_bar is not None else _NULL_STATUS_HOOK

        self.conversation.append({"role": "user", "content": user_message})

        # Accumulate celebration strings, newly-earned Badge objects, and
        # newly-completed Challenge objects from all tool calls this turn.
        # chat.py reads all three after chat() returns to render Rich panels for
        # the user — separate from the LLM conversation content.
        # DEC-64-LLM-PANEL-SEPARATION-001: challenges surface here, not via LLM summary.
        self.last_celebrations: list[str] = []
        self.last_badges: list = []  # list[Badge] — newly earned this turn
        self.last_challenges: list = []  # list[Challenge] — newly completed this turn
        # Per-turn dedup set: an achievement key fires at most once per REPL turn.
        # Bug 6 fix (DEC-P18S4-ACHIEVEMENT-DEDUP-001): "show details" from a single
        # workspace command with N indicators would fire Nice find! N times.
        #
        # @decision DEC-P18S4-ACHIEVEMENT-DEDUP-001
        # @title Achievement dedupe by celebration string hash per REPL turn
        # @status accepted
        # @rationale The tool loop processes N tool calls per turn; each call independently
        #            computes a celebration and appends it. When the same celebration fires
        #            multiple times in one turn (same art string), we coalesce to one.
        _turn_seen_celebrations: set[str] = set()

        # M-7: wire self into ToolContext so run_module() can call self.narrate()
        # for high-weight dossier event celebration text (DEC-M7-CELEB-001).
        # Cleared to None after chat() returns to prevent stale runner references.
        self.ctx._narration_runner = self

        max_rounds = 5
        for _ in range(max_rounds):
            response = self._call_llm()

            # Check if LLM wants to call tools
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                # No tool calls — this is the final text response
                # Clear narration runner reference before returning (M-7 cleanup).
                self.ctx._narration_runner = None
                assistant_msg = self._extract_text(response)
                self.conversation.append({"role": "assistant", "content": assistant_msg})
                return assistant_msg

            # Execute all tool calls in this round
            self.conversation.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls,
                }
            )
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}
                # Signal the status bar with the tool-specific activity slug
                # before execution, then clear to idle (None) after — whether
                # the call succeeds or raises. DEC-STATUS-ACTIVITY-WIRING-001.
                _hook.set_activity(_status_slug_for_tool(tool_name))
                try:
                    summary, celebration, badges, challenges = execute_tool(
                        self.ctx,
                        tool_name,
                        args,
                    )
                finally:
                    _hook.set_activity(None)
                if celebration and celebration not in _turn_seen_celebrations:
                    _turn_seen_celebrations.add(celebration)
                    self.last_celebrations.append(celebration)
                if badges:
                    self.last_badges.extend(badges)
                if challenges:
                    self.last_challenges.extend(challenges)
                self.conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": summary,
                    }
                )

        # Fallback if we hit max_rounds without a final text response
        # Clear narration runner reference before returning (M-7 cleanup).
        self.ctx._narration_runner = None
        # Bug 3 fix: when all tool calls errored, the results above will be error panels.
        # Detect whether any tool produced a real result (no [USER_SAW_PANEL] prefix).
        # If every result is an error/empty, emit an honest fallback instead of filler.
        _all_tool_messages = [
            msg["content"]
            for msg in self.conversation
            if msg.get("role") == "tool" and isinstance(msg.get("content"), str)
        ]
        _any_real_result = any(
            not c.startswith("[USER_SAW_PANEL]") and "error" not in c.lower()[:50]
            for c in _all_tool_messages
        )
        if not _any_real_result and _all_tool_messages:
            return "None of the queried services returned data. See the error panels above for details."
        return "I've completed several tool calls. Here's what I found based on the results above."

    def _call_llm(self) -> object:
        """Call the LLM with current conversation and tools.

        When a config_mgr was provided at construction and the configured
        provider has an API key stored in config.toml, that key is passed to
        litellm via the ``api_key`` kwarg so it takes precedence over any
        environment variable that litellm would otherwise read.  This lets
        the wizard-persisted key work even when the user has no env vars set.

        Returns the message object from the LLM response.
        """
        kwargs: dict = {
            "model": self.model,
            "messages": self.conversation,
            "tools": self.tools,
            "tool_choice": "auto",
        }
        if self._config_mgr is not None:
            provider_id = self._config_mgr.get_agent_provider()
            if provider_id:
                stored_key = self._config_mgr.get_provider_api_key(provider_id)
                if stored_key:
                    kwargs["api_key"] = stored_key
        response = litellm.completion(**kwargs)
        return response.choices[0].message

    def _extract_tool_calls(self, message: object) -> list[dict]:
        """Extract tool calls from LLM response message.

        Returns a list of tool call dicts in the format:
        [{"id": ..., "type": "function", "function": {"name": ..., "arguments": ...}}]
        Returns [] if no tool calls were requested.
        """
        if hasattr(message, "tool_calls") and message.tool_calls:
            return [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        return []

    def _extract_text(self, message: object) -> str:
        """Extract text content from LLM response message."""
        if hasattr(message, "content") and message.content:
            return message.content
        return ""

    def narrate(self, prompt: str, *, max_tokens: int) -> str | None:
        """Produce a short LLM narration string without mutating conversation history.

        Single-turn, no tools, no conversation mutation. Reuses the active model,
        the active persona system prompt (so character voice flows through naturally),
        and the active API-key resolution from ``_call_llm``. Used by
        ``dossier_celebrations.narrate_celebration()`` to produce high-weight
        slot-fill celebration text (DEC-M7-CELEB-001, DEC-M7-CELEB-003).

        Does NOT pass ``tools`` or ``tool_choice`` — this is a pure completion call.
        Does NOT append to ``self.conversation`` — the narration is panel content
        (F64 / DEC-64-LLM-PANEL-SEPARATION-001), not part of the analytical dialogue.

        Parameters
        ----------
        prompt:
            User-role content for the narration request (built by
            ``build_narration_prompt()`` in ``dossier_celebrations.py``).
        max_tokens:
            Hard token ceiling for the narration response. Enforced by litellm.

        Returns
        -------
        str | None
            Narration text on success, or None on LLM failure. Callers (narrate_celebration)
            handle None by returning None themselves, falling back to ASCII art.
        """
        if not HAS_LITELLM:
            return None

        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ]
            kwargs: dict = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
            }
            # Thread API key through the same path as _call_llm (DEC-M7-CELEB-001).
            if self._config_mgr is not None:
                provider_id = self._config_mgr.get_agent_provider()
                if provider_id:
                    stored_key = self._config_mgr.get_provider_api_key(provider_id)
                    if stored_key:
                        kwargs["api_key"] = stored_key
            response = litellm.completion(**kwargs)
            msg = response.choices[0].message
            if hasattr(msg, "content") and msg.content:
                return msg.content
            return None
        except Exception:  # noqa: BLE001
            return None

    def handle_input(self, text: str, status_bar: "_StatusHook | None" = None) -> str:
        """Route user input from the TUI to a yield command or the LLM.

        This is the single authoritative entry point for TUI input (Sacred
        Practice 12).  The legacy REPL calls ``.chat()`` directly because it
        owns its own yield-command parsing.  The TUI must NEVER call ``.chat()``
        directly — all TUI input goes through this method.

        Routing contract (DEC-RUNNER-HANDLE-INPUT-001):

        1. Attempt ``yield_commands.parse_yield(text)``.
           - On a valid YieldCommand: call ``dispatch_yield`` and return its
             character-voiced feedback string.  ``chat()`` is NOT called.
           - On ``None`` (input is not a yield command): fall through to LLM.
        2. If the verb looks like a yield verb but ``parse_yield`` returns None
           (e.g. ``"focus"`` with no arg), route to the LLM rather than raising.
           This is the graceful-degradation path: users who mistype a yield
           command get an LLM response instead of a crash (Sacred Practice 5).
        3. For all non-yield input call ``self.chat(text, status_bar=status_bar)``
           and return the result.

        Returns a string in every code path — never None — so callers can
        unconditionally append the result to the scrollback buffer.

        Parameters
        ----------
        text:
            Raw input string from the TUI, already stripped.
        status_bar:
            Optional status hook forwarded to ``chat()`` for tool-activity
            display.  The LivePane in ``TuiApplication`` satisfies the
            ``_StatusHook`` protocol and is wired here by ``_on_input_accepted``.

        Returns
        -------
        str
            LLM response text, or a character-voiced yield acknowledgement.

        @decision DEC-RUNNER-HANDLE-INPUT-001
        @title handle_input as single TUI entry point — yield-first routing
        @status accepted
        @rationale TuiApplication previously called runner.handle_input() which
                   did not exist, causing AttributeError on every user keystroke.
                   Adding handle_input() as the authoritative TUI entry point:
                   (a) fixes the crash, (b) unifies yield-command detection at
                   the runner boundary so the TUI never calls .chat() directly
                   (Sacred Practice 12 — single source of truth per input path),
                   (c) gracefully routes malformed yield-shaped input to the LLM
                   rather than crashing (Sacred Practice 5 — fail loud on
                   unexpected state, fail graceful on user-typed ambiguity).
                   The legacy REPL in chat.py is unaffected — it calls .chat()
                   directly and handles its own yield parsing.
        """
        from adversary_pursuit.agent.yield_commands import parse_yield

        # Try yield-command parsing first.  parse_yield returns None for:
        #   - input that doesn't start with a known verb
        #   - verbs with missing or extra argument tokens (e.g. "focus" alone)
        # In all None cases we fall through to the LLM — no exception is raised.
        try:
            cmd = parse_yield(text)
        except Exception:  # noqa: BLE001
            # parse_yield is pure string logic and should never raise, but
            # defensive catch: treat unexpected parser errors as "not a yield".
            cmd = None

        if cmd is not None:
            from adversary_pursuit.agent.yield_commands import dispatch_yield

            # Use the runner's active character name if available via the mode
            # manager held by the TUI caller.  When the runner itself has no
            # character attribute (duck-typed callers) default to "default".
            character = getattr(self, "_character", "default")

            # No active battery run at this layer — dispatch_yield accepts None.
            # EventBus is not held directly by the runner; pass None-safe stub
            # when unavailable.  The TuiApplication's event_bus is wired through
            # dispatch_yield at the call site in _on_input_accepted for the
            # full-featured path; here we use the fallback None bus guard inside
            # dispatch_yield (which always publishes to a real bus when given one).
            #
            # For the runner-level entry point, use a minimal no-op bus when the
            # caller did not inject one.  TuiApplication._on_input_accepted calls
            # dispatch_yield itself for the yield path and does NOT call
            # handle_input for yield commands — so this code path is reached only
            # by tests or callers that want unified routing.
            try:
                from adversary_pursuit.agent.tui.events import EventBus as _EventBus

                _bus = _EventBus()
                feedback = dispatch_yield(cmd, None, _bus, character)
            except Exception:  # noqa: BLE001
                feedback = f"[{cmd.primitive}]"
            return feedback

        # Non-yield input: route to the LLM via chat().
        return self.chat(text, status_bar=status_bar)

    def reset(self) -> None:
        """Reset conversation history to just the system prompt."""
        self.conversation = [{"role": "system", "content": self.system_prompt}]

    def set_character(self, mode: CharacterMode) -> None:
        """Update the LLM system prompt to reflect the given character mode.

        When mode.llm_profile is None (the default for all F62 modes), uses
        the v1 composition verbatim: ``'Character mode: {name}\n{personality}\n\n'``
        prepended to the default system prompt. Behavior is byte-identical to
        pre-C-1 for all modes that have not been upgraded (DEC-C1-FULLTROLL-002).

        When mode.llm_profile is not None (C-1+: full_troll and later C-2/C-3/C-4
        modes), composes the structured LLM profile into the system prompt per
        the roadmap §3.3 template. This is the SOLE injection site for the persona
        profile — no sidecar agent, no post-processor (DEC-C1-FULLTROLL-003).

        Only the system message slot (conversation[0]) is modified —
        conversation history is preserved in both code paths.

        Parameters
        ----------
        mode:
            The CharacterMode to activate. mode.name is used for debug logging.
            When mode.llm_profile is not None, the structured profile fields
            replace the simple ``mode.personality`` prefix.
        """
        logger.debug("Setting character mode: %s", mode.name)
        if mode.llm_profile is not None:
            # v2 path: inject structured LLM persona profile (roadmap §3.3 template).
            # @decision DEC-C1-FULLTROLL-003
            # @title Injection via in-place concatenation at the existing set_character site
            # @status accepted
            # @rationale Single integration site (runner.py:278-295); no new LLM round-trips;
            #            no sidecar agent; no response post-processor. DEC-30-CHARACTER-V2-003
            #            option (a) executed. Reverting C-1 restores v1 behavior verbatim
            #            because the None-default branch preserves the v1 string.
            p = mode.llm_profile
            # Render signature_phrases and tool_preferences as readable inline lists.
            sig_phrases = ", ".join(f'"{ph}"' for ph in p.signature_phrases)
            tool_prefs = "; ".join(p.tool_preferences) if p.tool_preferences else "none"
            ctx_hooks = "; ".join(p.context_hooks) if p.context_hooks else "none"
            forbidden = "; ".join(p.forbidden_voice) if p.forbidden_voice else "none"
            tone = ", ".join(p.tone_registers)
            profile_fragment = (
                f"Character mode: {mode.name}\n"
                f"Voice: {p.voice_summary}\n"
                f"Tone: {tone}\n"
                f"Cadence: {p.dialect_cadence}\n"
                f"Stance: {p.fourth_wall_stance}\n"
                f"Signature phrases (use sparingly, not every turn): {sig_phrases}\n"
                f"Investigation-context hooks: {ctx_hooks}\n"
                f"Tool voice affinity (flavor only — never selection bias): {tool_prefs}\n"
                f"Forbidden voice patterns: {forbidden}\n\n"
            )
            self.system_prompt = profile_fragment + self._default_system_prompt()
        else:
            # v1 path: F62 composition verbatim — preserved byte-identical for all
            # modes with llm_profile=None (default, ninja, and 7 not-yet-upgraded modes).
            self.system_prompt = (
                f"Character mode: {mode.name}\n{mode.personality}\n\n"
                + self._default_system_prompt()
            )
        self.conversation[0] = {"role": "system", "content": self.system_prompt}
