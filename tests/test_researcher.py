"""End-to-end tests for the ResearchEngine business logic — fully offline."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai.schemas import AnswerWithCitations, Citation, Source
from src.core.researcher import ResearchEngine
from src.models import QuestionRequest, ResearchResult
from src.services.cache import InMemoryCache


def _make_engine(fake_ai_service, fake_repo, fake_llm, three_sources=None):
    """Wire up a ResearchEngine with fake dependencies."""
    from src.concurrency.orchestrator import ResearchOrchestrator

    orch = ResearchOrchestrator(
        ai_svc=fake_ai_service,
        cache=InMemoryCache(ttl_seconds=0),
    )
    return ResearchEngine(
        orchestrator=orch,
        ai_svc=fake_ai_service,
        repository=fake_repo,
    ), fake_llm


@pytest.mark.asyncio
async def test_research_returns_result(fake_ai_service, fake_repo, fake_llm, three_sources):
    """Happy-path: engine returns a ResearchResult with answer and citations."""
    engine, llm = _make_engine(fake_ai_service, fake_repo, fake_llm, three_sources)
    request = QuestionRequest(question="What is photosynthesis?")
    result = await engine.research(request, llm=llm)
    assert isinstance(result, ResearchResult)
    assert len(result.answer) > 0


@pytest.mark.asyncio
async def test_research_persists_session(fake_ai_service, fake_repo, fake_llm, three_sources):
    """Engine saves a session to the repository after research."""
    engine, llm = _make_engine(fake_ai_service, fake_repo, fake_llm, three_sources)
    request = QuestionRequest(question="What is photosynthesis?")
    await engine.research(request, llm=llm)
    assert len(fake_repo.sessions) == 1


@pytest.mark.asyncio
async def test_research_no_sources_returns_graceful_error(
    fake_ai_service, fake_repo, fake_llm
):
    """If all sources return empty, engine returns a friendly error message."""
    fake_ai_service._sources = []
    engine, llm = _make_engine(fake_ai_service, fake_repo, fake_llm, [])
    request = QuestionRequest(question="Unknown topic")
    result = await engine.research(request, llm=llm)
    assert isinstance(result, ResearchResult)
    assert len(result.answer) > 0
    assert result.citations == []


@pytest.mark.asyncio
async def test_research_partial_source_failure(
    fake_ai_service, fake_repo, fake_llm, three_sources
):
    """If one source fails, the answer is still produced from the rest."""
    async def _fail(*args, **kwargs):
        raise ConnectionError("arxiv is down")

    fake_ai_service.fetch_arxiv = _fail
    engine, llm = _make_engine(fake_ai_service, fake_repo, fake_llm, three_sources)
    request = QuestionRequest(question="What is photosynthesis?")
    result = await engine.research(request, llm=llm)
    assert "arxiv" in result.sources_failed
    assert len(result.answer) > 0


@pytest.mark.asyncio
async def test_research_elapsed_seconds_set(fake_ai_service, fake_repo, fake_llm, three_sources):
    """elapsed_seconds is a positive number after a successful research call."""
    engine, llm = _make_engine(fake_ai_service, fake_repo, fake_llm, three_sources)
    request = QuestionRequest(question="Photosynthesis stages")
    result = await engine.research(request, llm=llm)
    assert result.elapsed_seconds > 0


@pytest.mark.asyncio
async def test_research_history_empty_at_start(fake_ai_service, fake_repo, fake_llm):
    """get_history returns [] when no sessions have been saved."""
    engine, _ = _make_engine(fake_ai_service, fake_repo, fake_llm, [])
    sessions = await engine.get_history()
    assert sessions == []
