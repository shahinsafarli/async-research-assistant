"""Configuration and .env integration tests."""
from __future__ import annotations

import os

from src.config import Settings, sync_settings_to_environ


def test_sync_settings_to_environ_exports_llm_provider(monkeypatch):
    cfg = Settings(
        llm_provider="gemini",
        llm_model="gemini-2.5-flash-lite",
        google_api_key="test-google-key",
    )
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    sync_settings_to_environ(cfg)

    assert os.environ["LLM_PROVIDER"] == "gemini"
    assert os.environ["GOOGLE_API_KEY"] == "test-google-key"


def test_llm_from_settings_uses_gemini(monkeypatch):
    from src.config import settings
    from src.services.ai_service import AIService

    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_model", "gemini-2.5-flash-lite")
    monkeypatch.setattr(settings, "google_api_key", "test-key")

    llm = AIService._llm_from_settings()
    assert llm.__class__.__name__ == "GeminiLLM"
