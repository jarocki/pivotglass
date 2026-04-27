"""Agent infrastructure for conversational CTI interface.

Provides the tool layer and runner for AP's conversational interface.
The tool layer wraps existing PursuitModules as OpenAI function-calling
compatible tools. The runner orchestrates the LLM interaction loop.

@decision DEC-AGENT-ARCH-001
@title Separate tool layer from LLM runner for testability
@status accepted
@rationale tools.py must work without litellm installed (no LLM needed to
           dispatch tool calls in tests). runner.py imports litellm and raises
           a clear error when missing. This separation allows the tool dispatch
           layer to be fully unit-tested without an LLM backend.
"""
