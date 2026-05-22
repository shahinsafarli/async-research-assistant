"""Tests for AIService — all offline, no real network calls."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.schemas import Source
from src.services.ai_service import AIService


@pytest.fixture
def svc() -> AIService:
    return AIService()


@pytest.mark.asyncio
async def test_fetch_wikipedia_returns_sources(svc, monkeypatch):
    """fetch_wikipedia returns a list of Source objects."""
    fake_sources = [
        Source(title="Photosynthesis", url="https://en.wikipedia.org/wiki/Photosynthesis",
               snippet="Plants convert light.", origin="wikipedia")
    ]

    async def _fake_wiki(*args, **kwargs):
        return fake_sources

    monkeypatch.setattr("ai.fetch_wikipedia", _fake_wiki)
    result = await svc.fetch_wikipedia("photosynthesis")
    assert isinstance(result, list)
    assert all(isinstance(s, Source) for s in result)
    assert result[0].origin == "wikipedia"


@pytest.mark.asyncio
async def test_fetch_arxiv_returns_sources(svc, monkeypatch):
    """fetch_arxiv returns a list of Source objects."""
    fake_sources = [
        Source(title="Transformers", url="https://arxiv.org/abs/1706.03762",
               snippet="Attention is all you need.", origin="arxiv")
    ]

    async def _fake_arxiv(*args, **kwargs):
        return fake_sources

    monkeypatch.setattr("ai.fetch_arxiv", _fake_arxiv)
    result = await svc.fetch_arxiv("transformers")
    assert len(result) == 1
    assert result[0].origin == "arxiv"


@pytest.mark.asyncio
async def test_fetch_web_returns_sources(svc, monkeypatch, fake_web):
    """fetch_web returns a list of Source objects."""
    fake_sources = [
        Source(title="Web result", url="https://example.com",
               snippet="Some web content.", origin="web")
    ]
    monkeypatch.setattr("ai.get_web_search_provider", lambda: fake_web)
    monkeypatch.setattr("ai.fetch_web", AsyncMock(return_value=fake_sources))
    result = await svc.fetch_web("photosynthesis")
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_fetch_wikipedia_returns_empty_on_timeout(svc, monkeypatch):
    """fetch_wikipedia returns [] gracefully when a timeout occurs."""
    async def _timeout(*args, **kwargs):
        await asyncio.sleep(100)  # will be cancelled by wait_for

    monkeypatch.setattr("ai.fetch_wikipedia", _timeout)
    import src.config as cfg
    monkeypatch.setattr(cfg.settings, "wikipedia_timeout", 0.01)
    result = await svc.fetch_wikipedia("photosynthesis")
    assert result == []


@pytest.mark.asyncio
async def test_fetch_arxiv_returns_empty_on_network_error(svc, monkeypatch):
    """fetch_arxiv returns [] gracefully on a connection error."""
    async def _fail(*args, **kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr("ai.fetch_arxiv", _fail)
    result = await svc.fetch_arxiv("quantum computing")
    assert result == []


def test_synthesize_with_fake_llm(svc, fake_llm, sample_sources):
    """synthesize returns an AnswerWithCitations when given sources."""
    from ai.schemas import AnswerWithCitations
    result = svc.synthesize("What is photosynthesis?", sample_sources, llm=fake_llm)
    assert isinstance(result, AnswerWithCitations)
    assert result.question == "What is photosynthesis?"
    assert len(result.answer) > 0


def test_synthesize_raises_on_empty_sources(svc, fake_llm):
    """synthesize raises ValueError when given no sources (validation)."""
    with pytest.raises(ValueError, match="zero sources"):
        svc.synthesize("What is photosynthesis?", [], llm=fake_llm)


def test_synthesize_raises_on_provider_error(svc, fake_llm, sample_sources, monkeypatch):
    """synthesize propagates ProviderError from the LLM."""
    from ai.providers.base import ProviderError

    def _boom(*args, **kwargs):
        raise ProviderError("provider down")

    monkeypatch.setattr("ai.synthesize", _boom)
    with pytest.raises(ProviderError):
        svc.synthesize("Q?", sample_sources, llm=fake_llm)
