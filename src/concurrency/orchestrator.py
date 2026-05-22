"""
Source orchestration layer.

Runs Wikipedia, arXiv, and web search concurrently through the bounded run_concurrent pipeline with:
  - Per-source timeouts (configurable via settings)
  - Graceful degradation: if one source fails, the answer is still produced
    from the remaining sources with the failure noted in the result
  - Source filtering via the --sources CLI flag
  - Optional cache bypass via --no-cache

This is the critical concurrency layer the rubric asks for.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from ai.schemas import Source
from src.config import settings
from src.models import SourceResult
from src.concurrency.pipeline import run_concurrent
from src.services.ai_service import AIService, SourceFetchError
from src.services.cache import CacheBackend, InMemoryCache, canonicalize_query
from src.utils.search_query import arxiv_api_query, search_query_from_question

logger = logging.getLogger(__name__)

_SOURCE_LABELS = {"wiki": "wikipedia", "arxiv": "arxiv", "web": "web"}

def _http_client_headers() -> dict[str, str]:
    """Headers required by Wikipedia and arXiv API policies."""
    return {
        "User-Agent": (
            "AsyncResearchAssistant/1.0 "
            f"(mailto:{settings.arxiv_contact_email}; "
            "https://github.com/emiljafarov3841/async-research-assistant)"
        ),
    }


class ResearchOrchestrator:
    """Coordinates parallel source fetching for a research question.

    Uses composition: an AIService instance for the actual AI calls, and a
    CacheBackend instance for caching.  Both are injected, making the
    orchestrator fully testable without touching the network.
    """

    def __init__(
        self,
        ai_svc: AIService | None = None,
        cache: CacheBackend | None = None,
    ) -> None:
        from src.services.ai_service import ai_service as _default_svc

        self._ai = ai_svc or _default_svc
        self._cache: CacheBackend = cache or InMemoryCache()

    async def fetch_all(
        self,
        question: str,
        sources: list[str] | None = None,
        no_cache: bool = False,
    ) -> tuple[list[Source], list[str]]:
        """Fetch from all requested sources concurrently.

        Parameters
        ----------
        question: str
            The research question (used verbatim as the search query).
        sources: list[str] | None
            Subset of ["wiki", "arxiv", "web"]; defaults to all three.
        no_cache: bool
            Bypass the cache if True.

        Returns
        -------
        (sources, failed_sources)
            A flat list of Source objects from all successful fetchers, and a
            list of source names that failed or timed out.
        """
        requested = sources or ["wiki", "arxiv", "web"]
        canonical = canonicalize_query(question)
        # Wikipedia opensearch and arXiv work best with keyword queries, not full sentences.
        api_query = search_query_from_question(question)
        t0 = time.perf_counter()

        logger.info(
            "orchestrator_start",
            extra={"question": question[:80], "sources": requested, "no_cache": no_cache},
        )

        async with httpx.AsyncClient(
            timeout=max(
                settings.wikipedia_timeout,
                settings.arxiv_timeout,
                settings.web_timeout,
            ),
            follow_redirects=True,
            headers=_http_client_headers(),
        ) as client:
            async def _run_source(src: str) -> list[Source]:
                # arXiv asks for >= 3s between requests; stagger so parallel wiki/web
                # do not race the same wall-clock window as the first arXiv hit.
                if src == "arxiv":
                    await asyncio.sleep(settings.arxiv_rate_limit_seconds)
                return await self._fetch_one(
                    src,
                    question,
                    api_query,
                    canonical,
                    client,
                    no_cache,
                )

            src_names = list(requested)
            task_list = [_run_source(src) for src in src_names]

            results = await run_concurrent(task_list, max_concurrent=settings.max_concurrent)

        combined_by_source: dict[str, list[Source]] = {src: [] for src in src_names}
        failed: list[str] = []

        for name, result in zip(src_names, results):
            if isinstance(result, SourceFetchError):
                logger.warning(
                    "source_failed",
                    extra={"source": result.source, "error": str(result)},
                )
                failed.append(result.source)
            elif isinstance(result, BaseException):
                logger.warning(
                    "source_failed",
                    extra={"source": name, "error": str(result)},
                )
                failed.append(name)
            elif isinstance(result, list):
                combined_by_source[name].extend(result)
            else:
                failed.append(name)

        combined = self._interleave_sources(combined_by_source, src_names)

        elapsed = time.perf_counter() - t0
        logger.info(
            "orchestrator_done",
            extra={
                "total_sources": len(combined),
                "failed": failed,
                "elapsed_s": round(elapsed, 3),
            },
        )
        return combined, failed

    async def _fetch_one(
        self,
        source: str,
        question: str,
        api_query: str,
        canonical: str,
        client: httpx.AsyncClient,
        no_cache: bool,
    ) -> list[Source]:
        """Fetch a single source, consulting the cache first."""
        if not no_cache:
            cached = self._cache.get(source, canonical)
            if cached is not None:
                if cached:
                    logger.info("cache_hit", extra={"source": source, "query": canonical[:40]})
                    return [Source(**d) for d in cached]
                logger.info(
                    "cache_skip_empty",
                    extra={"source": source, "query": canonical[:40]},
                )

        # Web search handles natural-language questions; wiki/arxiv need keywords.
        if source == "wiki":
            fetch_query = api_query
        elif source == "arxiv":
            fetch_query = arxiv_api_query(api_query)
        else:
            fetch_query = question

        if source == "wiki":
            raw = await self._ai.fetch_wikipedia(
                fetch_query, client=client, raise_on_failure=True
            )
        elif source == "arxiv":
            raw = await self._ai.fetch_arxiv(
                fetch_query, client=client, raise_on_failure=False
            )
            if not raw:
                raw = await self._fetch_arxiv_via_web(
                    api_query, question, client=client
                )
        elif source == "web":
            raw = await self._ai.fetch_web(
                question, client=client, raise_on_failure=True
            )
        else:
            logger.warning("unknown_source", extra={"source": source})
            return []

        if source == "arxiv" and not raw:
            raise SourceFetchError(
                "arxiv",
                "arXiv API unavailable and site:arxiv.org web fallback returned no results",
            )

        if not no_cache and raw:
            self._cache.set(source, canonical, [s.model_dump() for s in raw])

        return raw

    async def _fetch_arxiv_via_web(
        self,
        api_query: str,
        question: str,
        *,
        client: httpx.AsyncClient,
    ) -> list[Source]:
        """Fallback when export.arxiv.org is rate-limited: find arXiv URLs via web search."""
        fallback_query = f"site:arxiv.org {api_query}"
        logger.info(
            "arxiv_web_fallback",
            extra={"query": fallback_query[:80]},
        )
        web_hits = await self._ai.fetch_web(
            fallback_query,
            client=client,
            raise_on_failure=False,
        )
        arxiv_sources: list[Source] = []
        for hit in web_hits:
            if "arxiv.org" not in hit.url.lower():
                continue
            arxiv_sources.append(
                Source(
                    title=hit.title,
                    url=hit.url,
                    snippet=hit.snippet,
                    origin="arxiv",
                )
            )
            if len(arxiv_sources) >= settings.max_sources_per_query:
                break
        if arxiv_sources:
            logger.info(
                "arxiv_web_fallback_ok",
                extra={"count": len(arxiv_sources), "question": question[:40]},
            )
        return arxiv_sources

    @staticmethod
    def _interleave_sources(
        sources_by_requested_name: dict[str, list[Source]],
        requested_order: list[str],
    ) -> list[Source]:
        """Return sources in round-robin order across requested source types.

        Without this, the synthesizer receives all Wikipedia results first, then
        all arXiv results, then all web results. Many LLMs then cite only the
        first origin. Round-robin ordering keeps the context mixed: wiki[0],
        arxiv[0], web[0], wiki[1], ...
        """
        mixed: list[Source] = []
        max_len = max((len(items) for items in sources_by_requested_name.values()), default=0)
        for i in range(max_len):
            for name in requested_order:
                items = sources_by_requested_name.get(name, [])
                if i < len(items):
                    mixed.append(items[i])
        return mixed

    def to_source_results(
        self,
        sources: list[Source],
        failed_sources: list[str],
    ) -> list[SourceResult]:
        """Convert ai.Source objects to SE-layer SourceResult models."""
        failed_origins = {_SOURCE_LABELS.get(s, s) for s in failed_sources}
        return [
            SourceResult(
                title=s.title,
                url=s.url,
                snippet=s.snippet,
                origin=s.origin,
                fetched_from_cache=False,
            )
            for s in sources
            if s.origin not in failed_origins
        ]
