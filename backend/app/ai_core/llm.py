"""Ollama Cloud client with size/cost-tiered model selection.

Tiers (configured in settings, see docs/ARCHITECTURE.md):
  - "cheap"   -> small model  : bulk MCQ generation, short summaries
  - "default" -> medium model : study-material curation, the interviewer agent
  - "smart"   -> large model  : hard evaluation / final scoring

Two entry points:
  - complete(): free-form text out
  - parse():    validated structured output into a Pydantic model

Key rotation: for now we build one ollama.Client from OLLAMA_HOST + OLLAMA_API_KEY.
The key-rotation service is merged in later by replacing _build_client() — callers
(complete/parse) don't change.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TypeVar
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger

import ollama

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_TIERS = {
    "cheap": lambda: settings.llm_model_cheap,
    "default": lambda: settings.llm_model_default,
    "smart": lambda: settings.llm_model_smart,
}

class LLMNotConfigured(RuntimeError):
    """Raised when an LLM call is attempted without OLLAMA_API_KEY set."""

class LLMClient:
    def __init__(self) -> None:
        self._client: ollama.Client | None = None

    def _build_client(self) -> ollama.Client:
        """Construct the Ollama client.

        SWAP POINT: replace the body with your key-rotation service when ready —
        it just needs to return an object exposing .chat(model, messages, ...).
        """
        if not settings.ollama_api_key:
            raise LLMNotConfigured("OLLAMA_API_KEY is not set. Add it to your .env to use the LLM.")
        return ollama.Client(
            host=settings.ollama_host,
            headers={"Authorization": f"Bearer {settings.ollama_api_key}"},
        )

    def _client_or_build(self) -> ollama.Client:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _model(self, tier: str) -> str:
        return _TIERS.get(tier, _TIERS["default"])()

    @staticmethod
    def _messages(prompt: str, system: str | None) -> list[dict]:
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    def _log_usage(self, model: str, resp) -> None:
        logger.info(
            "llm.call model=%s prompt_tokens=%s eval_tokens=%s",
            model,
            getattr(resp, "prompt_eval_count", "?"),
            getattr(resp, "eval_count", "?"),
        )

    def complete(
        self,
        prompt: str,
        *,
        tier: str = "default",
        system: str | None = None,
        options: dict | None = None,
    ) -> str:
        """Single-turn completion. Returns the assistant text.

        `options` maps to Ollama options, e.g. {"num_predict": 1024, "temperature": 0.2}.
        """
        client = self._client_or_build()
        model = self._model(tier)
        resp = client.chat(
            model=model,
            messages=self._messages(prompt, system),
            options=options or {},
        )
        self._log_usage(model, resp)
        return resp.message.content or ""

    def parse(
        self,
        prompt: str,
        schema: type[T],
        *,
        tier: str = "default",
        system: str | None = None,
        options: dict | None = None,
    ) -> T:
        """Structured output validated into the given Pydantic model.

        Used for MCQ generation, interview rubrics, etc. Ollama constrains output
        to the JSON schema; we then validate it into the Pydantic type.
        """
        client = self._client_or_build()
        model = self._model(tier)
        resp = client.chat(
            model=model,
            messages=self._messages(prompt, system),
            format=schema.model_json_schema(),
            options=options or {},
        )
        self._log_usage(model, resp)
        return schema.model_validate_json(resp.message.content or "")

@lru_cache
def get_llm() -> LLMClient:
    return LLMClient()
