"""
Core business logic: coordinate source fetching → synthesis → result.

This module is the heart of the application.  It:
  1. Validates the incoming QuestionRequest.
  2. Delegates concurrent fetching to the orchestrator.
  3. Falls back gracefully if all sources fail.
  4. Calls the LLM synthesizer via AIService.
  5. Persists the session via the repository.
  6. Returns a typed ResearchResult to the caller.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ai.schemas import Source
from src.config import settings
from src.models import CitationRecord, QuestionRequest, ResearchResult, SourceResult
from src.concurrency.orchestrator import ResearchOrchestrator
from src.services.ai_service import AIService
from src.services.cache import CacheBackend
from src.storage.repository import ResearchRepository

logger = logging.getLogger(__name__)


class ResearchEngine:
    """Orchestrates an end-to-end research query.

    Composition pattern: owns an orchestrator, an AI service, and a repository.
    Each dependency can be injected for testing.
    """

    def __init__(
        self,
        orchestrator: ResearchOrchestrator | None = None,
        ai_svc: AIService | None = None,
        repository: ResearchRepository | None = None,
        cache: CacheBackend | None = None,
    ) -> None:
        from src.services.ai_service import ai_service as _default_svc
        from src.storage.repository import repository as _default_repo

        self._ai = ai_svc or _default_svc
        self._repo = repository or _default_repo
        self._orchestrator = orchestrator or ResearchOrchestrator(
            ai_svc=self._ai,
            cache=cache,
        )

    async def research(
        self,
        request: QuestionRequest,
        *,
        llm: Any = None,
    ) -> ResearchResult:
        """Execute a research query end-to-end.

        Parameters
        ----------
        request:
            Validated QuestionRequest from the CLI or HTTP layer.
        llm:
            Optional LLM override (used in tests with FakeLLM).

        Returns
        -------
        ResearchResult with answer, citations, timing, and metadata.
        """
        t0 = time.perf_counter()
        logger.info(
            "research_start",
            extra={"question": request.question[:80], "sources": request.sources},
        )

        sources, failed = await self._orchestrator.fetch_all(
            request.question,
            sources=request.sources,
            no_cache=request.no_cache,
        )

        if not sources:
            logger.warning(
                "research_no_sources",
                extra={"question": request.question[:80], "failed": failed},
            )
            elapsed = time.perf_counter() - t0
            result = ResearchResult(
                question=request.question,
                answer=(
                    "No sources could be retrieved for this question. "
                    f"Failed sources: {', '.join(failed) or 'all'}. "
                    "Please try again or check your network connection."
                ),
                citations=[],
                sources_used=[],
                sources_failed=failed,
                from_cache=False,
                elapsed_seconds=round(elapsed, 3),
            )
            await self._persist(result)
            return result

        try:
            answer_obj = await asyncio.to_thread(
                self._ai.synthesize, request.question, sources, llm=llm
            )
        except Exception as exc:
            logger.error("synthesis_failed", extra={"error": str(exc)})
            elapsed = time.perf_counter() - t0
            result = ResearchResult(
                question=request.question,
                answer=f"Synthesis failed: {exc}",
                citations=[],
                sources_used=self._orchestrator.to_source_results(sources, failed),
                sources_failed=failed,
                from_cache=False,
                elapsed_seconds=round(elapsed, 3),
            )
            await self._persist(result)
            return result

        citations = [
            CitationRecord(
                index=c.index,
                title=c.source.title,
                url=c.source.url,
                origin=c.source.origin,
            )
            for c in answer_obj.citations
        ]
        source_results = self._orchestrator.to_source_results(sources, failed)
        elapsed = time.perf_counter() - t0

        result = ResearchResult(
            question=request.question,
            answer=answer_obj.answer,
            citations=citations,
            sources_used=source_results,
            sources_failed=failed,
            from_cache=False,
            elapsed_seconds=round(elapsed, 3),
        )

        logger.info(
            "research_done",
            extra={
                "n_citations": len(citations),
                "n_sources": len(sources),
                "elapsed_s": round(elapsed, 3),
                "failed": failed,
            },
        )

        await self._persist(result)
        return result

    async def _persist(self, result: ResearchResult) -> None:
        """Save result to storage; log but do not raise on failure."""
        try:
            await self._repo.save_session(result)
        except Exception as exc:
            logger.warning("persist_failed", extra={"error": str(exc)})

    async def get_history(self, limit: int = 20) -> list[dict]:
        """Return recent research sessions from storage."""
        try:
            return await self._repo.list_sessions(limit=limit)
        except Exception as exc:
            logger.error("history_failed", extra={"error": str(exc)})
            return []

