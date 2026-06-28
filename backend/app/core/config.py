"""Application settings, loaded from environment / .env (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_debug: bool = True
    app_secret_key: str = "change-me-in-production"

    # Auth / JWT (HS256 signed with app_secret_key)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 1 day

    # Database (plain libpq URL for psycopg — no "+psycopg" suffix)
    database_url: str = "postgresql://admin:admin@localhost:5432/student_journey"

    # LLM (Ollama Cloud). A single key for now; key-rotation service merged later.
    ollama_host: str = "https://ollama.com"
    ollama_api_key: str | None = None

    # Embeddings run on a SEPARATE host: Ollama Cloud does not serve embedding
    # models (its /api/embed returns 401), so RAG embedding goes to a local /
    # self-hosted Ollama. Auth is optional (local Ollama needs none).
    ollama_embed_host: str = "http://localhost:11434"
    ollama_embed_api_key: str | None = None

    # Multiple models, size/cost-tiered (see docs/ARCHITECTURE.md)
    llm_model_cheap: str = "gpt-oss:20b"
    llm_model_default: str = "gpt-oss:120b"
    llm_model_smart: str = "deepseek-v3.1:671b"

    # Embeddings for RAG (Phase 2). Dimension must match the vector(N) column in
    # 0003_phase2_study_material.sql — nomic-embed-text is 768-dim.
    llm_model_embed: str = "nomic-embed-text"

    # Web search. SearXNG (self-hosted metasearch, free, no key) is the default;
    # Tavily (LLM-grade extraction, paid) and DuckDuckGo (keyless fallback) remain.
    search_provider: str = "searxng"  # searxng | tavily | duckduckgo
    searxng_url: str = "http://localhost:8080"
    searxng_timeout: float = 12.0
    tavily_api_key: str | None = None

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
