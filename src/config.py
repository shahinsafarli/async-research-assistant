"""
Application configuration.
Read from .env via pydantic-settings.
All other modules import from here — never from os.environ directly.
"""
from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    llm_api_key: str = ""

    # Web search
    web_search_provider: str = "tavily"
    tavily_api_key: str = ""
    serper_api_key: str = ""

    # App
    log_level: str = "INFO"
    max_concurrent: int = Field(default=5, ge=1, le=50)
    cache_ttl_seconds: int = Field(default=3600, ge=0)
    cache_dir: str = "./.cache"
    source_rate_limit_seconds: float = Field(default=0.2, ge=0.0)

    # Per-source timeouts (seconds)
    wikipedia_timeout: float = Field(default=10.0, ge=1.0)
    arxiv_timeout: float = Field(default=30.0, ge=1.0)
    arxiv_rate_limit_seconds: float = Field(
        default=3.0,
        ge=0.0,
        description="Minimum delay between arXiv API calls (arXiv asks for >= 3s).",
    )
    arxiv_contact_email: str = Field(
        default="async-research-assistant@example.com",
        description="Contact email embedded in the User-Agent for arXiv API policy.",
    )
    web_timeout: float = Field(default=10.0, ge=1.0)

    # Query limits
    max_sources_per_query: int = Field(default=3, ge=1, le=10)
    max_question_length: int = Field(default=1000, ge=10)

    # Database (optional; used for persistent session/cache storage)
    database_url: str = "sqlite+aiosqlite:///./researcher.db"


def sync_settings_to_environ(cfg: Settings) -> None:
    """Mirror pydantic-loaded settings into os.environ for the provided ai/ package.

    The SE layer reads .env via pydantic-settings; ai.providers and ai.sources use
    os.getenv. Syncing on startup keeps CLI, Streamlit, and demos aligned with .env.
    """
    mapping = {
        "LLM_PROVIDER": cfg.llm_provider,
        "LLM_MODEL": cfg.llm_model,
        "ANTHROPIC_API_KEY": cfg.anthropic_api_key,
        "OPENAI_API_KEY": cfg.openai_api_key,
        "GOOGLE_API_KEY": cfg.google_api_key,
        "LLM_API_KEY": cfg.llm_api_key,
        "WEB_SEARCH_PROVIDER": cfg.web_search_provider,
        "TAVILY_API_KEY": cfg.tavily_api_key,
        "SERPER_API_KEY": cfg.serper_api_key,
    }
    for key, value in mapping.items():
        if value:
            os.environ[key] = value


settings = Settings()
sync_settings_to_environ(settings)
