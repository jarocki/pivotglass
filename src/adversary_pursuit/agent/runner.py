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

logger = logging.getLogger(__name__)

# Try litellm first — optional dependency
try:
    import litellm

    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

from adversary_pursuit.agent.tools import ToolContext, create_tools, execute_tool  # noqa: E402


class AgentRunner:
    """Orchestrates conversational CTI interactions.

    Manages the loop:
    user message → LLM → tool calls → tool results → LLM → response.

    The runner supports multiple LLM backends via litellm. The default model
    is a local Ollama model, requiring no API key. Set model to any
    litellm-supported string (e.g. "gpt-4o", "claude-3-5-sonnet-20241022",
    "ollama/qwen2.5:8b").

    Parameters
    ----------
    model:
        litellm model string. Defaults to DEFAULT_MODEL (local Ollama).
    tool_context:
        Shared ToolContext. Created automatically if not provided.
    system_prompt:
        Override the default system prompt.
    """

    DEFAULT_MODEL = "ollama/qwen2.5:8b"  # Local default via Ollama

    def __init__(
        self,
        model: str | None = None,
        tool_context: ToolContext | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model or self.DEFAULT_MODEL
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

        # Accumulate celebration strings from all tool calls this turn.
        # chat.py reads self.last_celebrations after chat() returns to render
        # Rich panels for the user — separate from the LLM conversation content.
        self.last_celebrations: list[str] = []

        max_rounds = 5
        for _ in range(max_rounds):
            response = self._call_llm()

            # Check if LLM wants to call tools
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                # No tool calls — this is the final text response
                assistant_msg = self._extract_text(response)
                self.conversation.append(
                    {"role": "assistant", "content": assistant_msg}
                )
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
                summary, celebration = execute_tool(
                    self.ctx,
                    tc["function"]["name"],
                    args,
                )
                if celebration:
                    self.last_celebrations.append(celebration)
                self.conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": summary,
                    }
                )

        # Fallback if we hit max_rounds without a final text response
        return (
            "I've completed several tool calls. "
            "Here's what I found based on the results above."
        )

    def _call_llm(self) -> object:
        """Call the LLM with current conversation and tools.

        Returns the message object from the LLM response.
        """
        response = litellm.completion(
            model=self.model,
            messages=self.conversation,
            tools=self.tools,
            tool_choice="auto",
        )
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

    def reset(self) -> None:
        """Reset conversation history to just the system prompt."""
        self.conversation = [{"role": "system", "content": self.system_prompt}]

    def set_character(self, mode_name: str, persona_prompt: str) -> None:
        """Update the system prompt with a character persona.

        Prepends the persona prompt to the default system prompt.
        Resets the conversation to use the new system prompt.

        Parameters
        ----------
        mode_name:
            Character mode name (e.g. "ninja", "drunken_master"). Used for logging.
        persona_prompt:
            The persona-specific system prompt text.
        """
        logger.debug("Setting character mode: %s", mode_name)
        self.system_prompt = persona_prompt + "\n\n" + self._default_system_prompt()
        self.conversation[0] = {"role": "system", "content": self.system_prompt}
