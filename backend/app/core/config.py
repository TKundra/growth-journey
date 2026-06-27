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

    # Multiple models, size/cost-tiered (see docs/ARCHITECTURE.md)
    llm_model_cheap: str = "gpt-oss:20b"
    llm_model_default: str = "gpt-oss:120b"
    llm_model_smart: str = "deepseek-v3.1:671b"

    # Web search
    search_provider: str = "tavily"  # tavily | duckduckgo
    tavily_api_key: str | None = None

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
