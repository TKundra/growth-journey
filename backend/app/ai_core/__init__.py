"""Shared AI primitives: Claude client, structured output, search providers."""

from app.ai_core.llm import LLMClient, get_llm

__all__ = ["LLMClient", "get_llm"]
