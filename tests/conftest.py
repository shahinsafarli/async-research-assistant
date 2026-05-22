"""
Shared pytest fixtures for the SE-layer tests.

The provided tests/conftest.py (shipped with the ai/ module) defines:
  FakeLLM, FakeWebSearch, fake_llm, fake_web, sample_sources.

This file EXTENDS that with SE-layer fixtures so all test files can import
from a single place.  We re-export the ai-module fixtures so they are
available project-wide.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ai.providers.base import LLMProvider
from ai.sources import WebSearchProvider
from ai.schemas import Source


# ---- Re-usable source fixtures -------------------------------------------

@pytest.fixture
def wiki_source() -> Source:
    return Source(
        title="Photosynthesis (Wikipedia)",
        url="https://en.wikipedia.org/wiki/Photosynthesis",
        snippet="Photosynthesis is the process by which plants convert light energy "
                "into chemical energy.",
        origin="wikipedia",
    )


@pytest.fixture
def arxiv_source() -> Source:
    return Source(
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762",
        snippet="We propose the Transformer, based solely on attention mechanisms.",
        origin="arxiv",
    )


@pytest.fixture
def web_source() -> Source:
    return Source(
        title="How Plants Make Food",
        url="https://example.com/plants",
        snippet="Plants use chlorophyll to absorb sunlight.",
        origin="web",
    )


@pytest.fixture
def sample_sources() -> list[Source]:
    """Matches the provided test_ai_smoke.py expectations exactly."""
    return [
        Source(
            title="Photosynthesis (Wikipedia)",
            url="https://en.wikipedia.org/wiki/Photosynthesis",
            snippet="Photosynthesis is a process used by plants and other organisms "
                    "to convert light energy into chemical energy.",
            origin="wikipedia",
        ),
        Source(
            title="Calvin cycle (Wikipedia)",
            url="https://en.wikipedia.org/wiki/Calvin_cycle",
            snippet="The Calvin cycle is a series of biochemical redox reactions "
                    "in the stroma of chloroplasts.",
            origin="wikipedia",
        ),
        Source(
            title="Attention Is All You Need",
            url="https://arxiv.org/abs/1706.03762",
            snippet="We propose the Transformer, based solely on attention mechanisms.",
            origin="arxiv",
        ),
        Source(
            title="How Plants Make Food",
            url="https://example.com/plants",
            snippet="Plants use chlorophyll to absorb sunlight.",
            origin="web",
        ),
    ]


# ---- Fake LLM (SE-layer version with configurable response) --------------

class FakeLLM(LLMProvider):
    """Controllable fake LLM for SE-layer tests."""

    def __init__(self, response: str | None = None) -> None:
        self.response = response or (
            "Photosynthesis converts light energy into chemical energy [1]. "
            "The Calvin cycle is the key light-independent reaction [2]."
        )
        self.calls: list[str] = []

    def complete(
        self,
        prompt: str,
        *,
        json_schema: dict | None = None,
        max_tokens: int = 1024,
    ) -> str:
        self.calls.append(prompt)
        return self.response


class FakeWebSearch(WebSearchProvider):
    """Returns canned web results without touching the network."""

    def __init__(self, results: list[Source] | None = None) -> None:
        self.results = results or [
            Source(
                title="Photosynthesis — Encyclopedia",
                url="https://example.com/photosynthesis",
                snippet="A biological process used by plants and some bacteria.",
                origin="web",
            )
        ]
        self.calls: list[str] = []

    async def search(
        self,
        query: str,
        *,
        max_results: int = 3,
        client: Any = None,
    ) -> list[Source]:
        self.calls.append(query)
        return self.results[:max_results]


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_web() -> FakeWebSearch:
    return FakeWebSearch()


# ---- Fake AI service (for orchestrator / researcher tests) ---------------

class FakeAIService:
    """Async-safe fake that returns canned sources without network calls."""

    def __init__(self, sources: list[Source] | None = None) -> None:
        self._sources = sources or []
        self.wiki_calls: list[str] = []
        self.arxiv_calls: list[str] = []
        self.web_calls: list[str] = []
        self._llm = FakeLLM()

    async def fetch_wikipedia(self, query: str, **kwargs) -> list[Source]:
        self.wiki_calls.append(query)
        return [s for s in self._sources if s.origin == "wikipedia"]

    async def fetch_arxiv(self, query: str, **kwargs) -> list[Source]:
        self.arxiv_calls.append(query)
        return [s for s in self._sources if s.origin == "arxiv"]

    async def fetch_web(self, query: str, **kwargs) -> list[Source]:
        self.web_calls.append(query)
        return [s for s in self._sources if s.origin == "web"]

    def synthesize(self, question: str, sources: list[Source], *, llm=None) -> Any:
        from ai import synthesize
        return synthesize(question, sources, llm=llm or self._llm)


@pytest.fixture
def three_sources() -> list[Source]:
    """Three sources (one per origin) for orchestrator/researcher tests."""
    return [
        Source(
            title="Photosynthesis",
            url="https://en.wikipedia.org/wiki/Photosynthesis",
            snippet="Photosynthesis is the process by which plants convert light energy.",
            origin="wikipedia",
        ),
        Source(
            title="Attention Is All You Need",
            url="https://arxiv.org/abs/1706.03762",
            snippet="We propose the Transformer, based solely on attention mechanisms.",
            origin="arxiv",
        ),
        Source(
            title="How Plants Make Food",
            url="https://example.com/plants",
            snippet="Plants use chlorophyll to absorb sunlight.",
            origin="web",
        ),
    ]


@pytest.fixture
def fake_ai_service(three_sources) -> FakeAIService:
    return FakeAIService(sources=three_sources)


# ---- Fake repository -----------------------------------------------------

class FakeRepository:
    """In-memory repository that never touches disk."""

    def __init__(self) -> None:
        self.sessions: list[dict] = []

    async def save_session(self, result: Any) -> int:
        self.sessions.append({"question": result.question, "answer": result.answer})
        return len(self.sessions)

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        return self.sessions[-limit:]

    async def get_session(self, session_id: int) -> dict | None:
        if 1 <= session_id <= len(self.sessions):
            return self.sessions[session_id - 1]
        return None


@pytest.fixture
def fake_repo() -> FakeRepository:
    return FakeRepository()
