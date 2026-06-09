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
from typing import TYPE_CHECKING

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

    def chat(self, user_message: str) -> str:
        """Process a user message and return the agent's response.

        Handles the full loop: message → LLM → tool calls → results → LLM → response.
        Supports up to 5 rounds of tool calling per message.

        Parameters
        ----------
        user_message:
            The user's input message.

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

        self.conversation.append({"role": "user", "content": user_message})

        # Accumulate celebration strings, newly-earned Badge objects, and
        # newly-completed Challenge objects from all tool calls this turn.
        # chat.py reads all three after chat() returns to render Rich panels for
        # the user — separate from the LLM conversation content.
        # DEC-64-LLM-PANEL-SEPARATION-001: challenges surface here, not via LLM summary.
        self.last_celebrations: list[str] = []
        self.last_badges: list = []  # list[Badge] — newly earned this turn
        self.last_challenges: list = []  # list[Challenge] — newly completed this turn

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
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}
                summary, celebration, badges, challenges = execute_tool(
                    self.ctx,
                    tc["function"]["name"],
                    args,
                )
                if celebration:
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
