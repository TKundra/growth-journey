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
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.logging import get_logger

import ollama

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

def _extract_json(text: str) -> str | None:
    """Best-effort pull of a JSON object/array out of a chatty model reply.

    Handles ```json fenced blocks and leading/trailing prose by slicing from the
    first opening bracket to its matching close. Returns None if nothing looks
    like JSON.
    """
    if not text:
        return None
    s = text.strip()

    # Prefer the contents of a fenced code block if present.
    if "```" in s:
        fence = s.split("```", 2)
        if len(fence) >= 2:
            block = fence[1]
            if block.lstrip().lower().startswith("json"):
                block = block.lstrip()[4:]
            s = block.strip()

    # Slice from the first { or [ to the last matching } or ].
    start = min((i for i in (s.find("{"), s.find("[")) if i != -1), default=-1)
    if start == -1:
        return None
    open_ch = s[start]
    close_ch = "}" if open_ch == "{" else "]"
    end = s.rfind(close_ch)
    if end == -1 or end < start:
        return None
    return s[start : end + 1]

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
        self._embed_client: ollama.Client | None = None

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

    def _build_embed_client(self) -> ollama.Client:
        """Construct the embedding client (separate host from chat).

        Ollama Cloud (ollama.com) does NOT serve embedding models — its
        /api/embed returns 401 for every model — so embeddings target a local /
        self-hosted Ollama (``OLLAMA_EMBED_HOST``). Auth is sent only if
        ``OLLAMA_EMBED_API_KEY`` is set (a local server needs none).
        """
        host = settings.ollama_embed_host
        if "ollama.com" in (host or ""):
            raise LLMNotConfigured(
                "OLLAMA_EMBED_HOST points at Ollama Cloud, which does not serve "
                "embedding models. Point it at a local/self-hosted Ollama "
                "(default http://localhost:11434) running an embedding model."
            )
        headers = (
            {"Authorization": f"Bearer {settings.ollama_embed_api_key}"}
            if settings.ollama_embed_api_key
            else None
        )
        return ollama.Client(host=host, headers=headers)

    def _embed_client_or_build(self) -> ollama.Client:
        if self._embed_client is None:
            self._embed_client = self._build_embed_client()
        return self._embed_client

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
        content = resp.message.content or ""
        try:
            return schema.model_validate_json(content)
        except ValidationError:
            # Some models ignore the JSON-schema constraint and wrap the object in
            # prose / ```json fences. Extract the JSON object and try once more.
            extracted = _extract_json(content)
            if extracted is None:
                logger.warning("llm.parse could not find JSON in response (model=%s)", model)
                raise
            return schema.model_validate_json(extracted)

    def embed(self, inputs: list[str], *, model: str | None = None) -> list[list[float]]:
        """Embed one or more texts into vectors (for RAG indexing/retrieval).

        Returns one vector per input, in order. The model defaults to
        ``settings.llm_model_embed`` (768-dim) — keep it in sync with the
        ``vector(N)`` column dimension in the study-material migration.

        Runs against ``OLLAMA_EMBED_HOST`` (a local/self-hosted Ollama), NOT the
        cloud chat host — Ollama Cloud does not serve embedding models.
        """
        if not inputs:
            return []
        client = self._embed_client_or_build()
        model = model or settings.llm_model_embed
        resp = client.embed(model=model, input=inputs)
        logger.info("llm.embed model=%s count=%d", model, len(inputs))
        # ollama returns {"embeddings": [[...], ...]} (or an object with .embeddings)
        return getattr(resp, "embeddings", None) or resp["embeddings"]

@lru_cache
def get_llm() -> LLMClient:
    return LLMClient()
