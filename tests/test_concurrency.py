"""Tests for the concurrent pipeline and orchestrator."""
from __future__ import annotations

import asyncio
import time

import pytest

from src.concurrency.pipeline import run_concurrent
from src.concurrency.orchestrator import ResearchOrchestrator
from src.services.cache import InMemoryCache


# ---- pipeline.py tests ---------------------------------------------------

@pytest.mark.asyncio
async def test_all_coroutines_succeed():
    """All coroutines succeed → results returned in input order."""
    async def task(n: int) -> int:
        await asyncio.sleep(0.001)
        return n * 2

    results = await run_concurrent([task(i) for i in range(5)])
    assert results == [0, 2, 4, 6, 8]


@pytest.mark.asyncio
async def test_one_fails_others_succeed():
    """If one coroutine raises, the other results are still returned."""
    async def good(n: int) -> int:
        return n

    async def bad() -> int:
        raise ValueError("simulated failure")

    results = await run_concurrent([good(1), bad(), good(3)])
    assert results[0] == 1
    assert isinstance(results[1], ValueError)
    assert results[2] == 3


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    """At most max_concurrent tasks run simultaneously."""
    running = 0
    peak = 0

    async def task() -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1

    await run_concurrent([task() for _ in range(10)], max_concurrent=3)
    assert peak <= 3


@pytest.mark.asyncio
async def test_concurrent_faster_than_sequential():
    """Concurrent execution of IO-bound tasks is faster than sequential."""
    delay = 0.05
    n = 6

    async def slow_task(_: int) -> int:
        await asyncio.sleep(delay)
        return 1

    t0 = time.perf_counter()
    await run_concurrent([slow_task(i) for i in range(n)], max_concurrent=n)
    concurrent_time = time.perf_counter() - t0

    t0 = time.perf_counter()
    for i in range(n):
        await slow_task(i)
    sequential_time = time.perf_counter() - t0

    assert concurrent_time < sequential_time * 0.75


@pytest.mark.asyncio
async def test_empty_coroutine_list():
    """Passing an empty list returns an empty list without error."""
    results = await run_concurrent([])
    assert results == []


# ---- orchestrator tests --------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_uses_all_three_sources(fake_ai_service, three_sources):
    """Orchestrator calls wiki, arxiv, and web when all three are requested."""
    cache = InMemoryCache(ttl_seconds=0)
    orch = ResearchOrchestrator(ai_svc=fake_ai_service, cache=cache)
    sources, failed = await orch.fetch_all("photosynthesis", sources=["wiki", "arxiv", "web"])
    assert fake_ai_service.wiki_calls == ["photosynthesis"]
    assert fake_ai_service.arxiv_calls == ["photosynthesis"]
    assert fake_ai_service.web_calls == ["photosynthesis"]
    assert failed == []
    assert len(sources) > 0


@pytest.mark.asyncio
async def test_orchestrator_source_filtering(fake_ai_service):
    """--sources wiki,arxiv skips the web fetcher."""
    cache = InMemoryCache(ttl_seconds=0)
    orch = ResearchOrchestrator(ai_svc=fake_ai_service, cache=cache)
    await orch.fetch_all("photosynthesis", sources=["wiki", "arxiv"])
    assert fake_ai_service.web_calls == []
    assert fake_ai_service.wiki_calls == ["photosynthesis"]


@pytest.mark.asyncio
async def test_orchestrator_graceful_degradation(fake_ai_service):
    """If one source fails, the others still return results."""
    async def _fail(*args, **kwargs):
        raise ConnectionError("arxiv is down")

    fake_ai_service.fetch_arxiv = _fail
    cache = InMemoryCache(ttl_seconds=0)
    orch = ResearchOrchestrator(ai_svc=fake_ai_service, cache=cache)
    sources, failed = await orch.fetch_all("photosynthesis", sources=["wiki", "arxiv", "web"])
    assert "arxiv" in failed
    assert any(s.origin == "wikipedia" for s in sources)


@pytest.mark.asyncio
async def test_orchestrator_cache_hit(fake_ai_service, three_sources):
    """Second call for the same query uses the cache, not the AI service."""
    cache = InMemoryCache(ttl_seconds=3600)
    orch = ResearchOrchestrator(ai_svc=fake_ai_service, cache=cache)

    await orch.fetch_all("photosynthesis", sources=["wiki"])
    first_count = len(fake_ai_service.wiki_calls)

    await orch.fetch_all("photosynthesis", sources=["wiki"])
    assert len(fake_ai_service.wiki_calls) == first_count


@pytest.mark.asyncio
async def test_orchestrator_no_cache_bypass(fake_ai_service):
    """--no-cache always calls the fetcher, even on repeated queries."""
    cache = InMemoryCache(ttl_seconds=3600)
    orch = ResearchOrchestrator(ai_svc=fake_ai_service, cache=cache)

    await orch.fetch_all("photosynthesis", sources=["wiki"], no_cache=True)
    await orch.fetch_all("photosynthesis", sources=["wiki"], no_cache=True)
    assert len(fake_ai_service.wiki_calls) == 2
