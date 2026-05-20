"""
Wraps the provided ai.* functions with:
- Exponential backoff retries (tenacity)
- Per-call timeout (asyncio.wait_for)
- A small async rate limiter for live source calls
- Structured logging
- Provider-level error normalization

This is the single entry point to all ai.* calls from the SE layer.
Do NOT call ai.* functions directly from business logic — always go through
this class.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Callable

import httpx
from tenacity import (
    AsyncRetrying,
    Retrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

import ai
from ai.providers.base import LLMProvider, ProviderError
from ai.schemas import Source, AnswerWithCitations
from src.config import settings

logger = logging.getLogger(__name__)


class SourceFetchError(RuntimeError):
    """Raised when a specific source cannot be fetched after retries."""

    def __init__(self, source: str, message: str) -> None:
        super().__init__(message)
        self.source = source


def _is_retryable(exc: BaseException) -> bool:
    """Return True for transient network/provider failures.

    The provided ai/ package wraps most HTTP errors in ProviderError. We also
    handle raw httpx status errors here so 429 and 5xx responses receive the
    same exponential-backoff treatment if they escape directly.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or 500 <= code <= 599
    if isinstance(exc, (ConnectionError, TimeoutError, OSError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, ProviderError):
        return True
    return False


def _make_async_retry(max_attempts: int = 4, *, min_wait_seconds: float = 1.0) -> AsyncRetrying:
    """Factory for the tenacity async retry policy."""
    return AsyncRetrying(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=min_wait_seconds, max=30),
        stop=stop_after_attempt(max_attempts),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def _make_sync_retry(max_attempts: int = 4) -> Retrying:
    """Factory for the tenacity sync retry policy used by ai.synthesize."""
    return Retrying(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(max_attempts),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


class AsyncRateLimiter:
    """Very small per-key async rate limiter.

    It enforces a minimum delay between live calls for the same source. This is
    intentionally simple and deterministic, making it easy to test and enough
    for the course requirement to avoid burst traffic and handle rate limits.
    arXiv requests use a longer interval (see settings.arxiv_rate_limit_seconds).
    """

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        per_key_intervals: dict[str, float] | None = None,
    ) -> None:
        self._default_interval = max(0.0, min_interval_seconds)
        self._per_key_intervals = {
            k: max(0.0, v) for k, v in (per_key_intervals or {}).items()
        }
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_call: dict[str, float] = defaultdict(float)

    def _interval_for(self, key: str) -> float:
        return self._per_key_intervals.get(key, self._default_interval)

    async def wait(self, key: str) -> None:
        interval = self._interval_for(key)
        if interval <= 0:
            return
        async with self._locks[key]:
            now = time.monotonic()
            elapsed = now - self._last_call[key]
            remaining = interval - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_call[key] = time.monotonic()


class AIService:
    """Service layer around the provided ai module.

    Applies retries, timeouts, rate limiting, and structured logging to every
    ai.* call. The concrete LLM/web provider still comes from the provided ai/
    package; this layer only selects and configures it without changing ai/.
    """

    def __init__(self, *, rate_limiter: AsyncRateLimiter | None = None) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._rate_limiter = rate_limiter or AsyncRateLimiter(
            settings.source_rate_limit_seconds,
            per_key_intervals={"arxiv": settings.arxiv_rate_limit_seconds},
        )

    @staticmethod
    def _llm_from_settings(llm: Any = None) -> LLMProvider:
        """Build the configured LLM from pydantic settings (honors .env)."""
        if llm is not None:
            return llm

        provider = settings.llm_provider.lower().strip()
        model = settings.llm_model
        if provider == "anthropic":
            from ai.providers.anthropic import AnthropicLLM

            key = settings.anthropic_api_key or settings.llm_api_key
            return AnthropicLLM(model=model, api_key=key or None)
        if provider == "openai":
            from ai.providers.openai import OpenAILLM

            key = settings.openai_api_key or settings.llm_api_key
            return OpenAILLM(model=model, api_key=key or None)
        if provider in ("google", "gemini"):
            from ai.providers.google import GeminiLLM

            key = settings.google_api_key or settings.llm_api_key
            return GeminiLLM(model=model, api_key=key or None)

        from ai.providers.factory import get_llm

        return get_llm()

    def _web_provider(self) -> ai.WebSearchProvider:
        """Create the configured web provider from settings.

        We do this here instead of relying on os.getenv inside ai/ so values
        loaded from .env by pydantic-settings are honored. The actual provider
        classes and fetch contract still belong to ai/.
        """
        provider_name = settings.web_search_provider.lower().strip()
        if provider_name == "tavily":
            if not settings.tavily_api_key:
                # Lets tests monkeypatch ai.get_web_search_provider while still
                # failing clearly in production if no key is available.
                return ai.get_web_search_provider()
            return ai.TavilyProvider(api_key=settings.tavily_api_key, timeout=settings.web_timeout)
        if provider_name == "serper":
            if not settings.serper_api_key:
                return ai.get_web_search_provider()
            return ai.SerperProvider(api_key=settings.serper_api_key, timeout=settings.web_timeout)
        if provider_name in {"duckduckgo", "ddg"}:
            return ai.DuckDuckGoProvider()
        raise ProviderError(
            f"Unknown WEB_SEARCH_PROVIDER={settings.web_search_provider!r}. "
            "Expected tavily | serper | duckduckgo."
        )

    async def _run_fetch(
        self,
        source_name: str,
        func: Callable[[], Any],
        *,
        timeout: float,
        raise_on_failure: bool,
        min_retry_wait: float = 1.0,
    ) -> list[Source]:
        t0 = time.perf_counter()
        try:
            async for attempt in _make_async_retry(min_wait_seconds=min_retry_wait):
                with attempt:
                    await self._rate_limiter.wait(source_name)
                    result = await asyncio.wait_for(func(), timeout=timeout)
        except Exception as exc:
            self._logger.warning(
                "fetch_source_failed",
                extra={"source": source_name, "error": str(exc)},
            )
            if raise_on_failure:
                raise SourceFetchError(source_name, f"{source_name} fetch failed: {exc}") from exc
            return []

        elapsed = time.perf_counter() - t0
        self._logger.info(
            "fetch_source_ok",
            extra={"source": source_name, "count": len(result), "elapsed_s": round(elapsed, 3)},
        )
        return result

    async def fetch_wikipedia(
        self,
        query: str,
        *,
        client: httpx.AsyncClient | None = None,
        max_results: int | None = None,
        raise_on_failure: bool = False,
    ) -> list[Source]:
        n = max_results or settings.max_sources_per_query
        self._logger.info("fetch_wikipedia_start", extra={"query": query[:80], "max_results": n})
        return await self._run_fetch(
            "wiki",
            lambda: ai.fetch_wikipedia(
                query,
                max_results=n,
                client=client,
                timeout=settings.wikipedia_timeout,
            ),
            timeout=settings.wikipedia_timeout,
            raise_on_failure=raise_on_failure,
        )

    async def fetch_arxiv(
        self,
        query: str,
        *,
        client: httpx.AsyncClient | None = None,
        max_results: int | None = None,
        raise_on_failure: bool = False,
    ) -> list[Source]:
        n = max_results or settings.max_sources_per_query
        self._logger.info("fetch_arxiv_start", extra={"query": query[:80], "max_results": n})
        return await self._run_fetch(
            "arxiv",
            lambda: ai.fetch_arxiv(
                query,
                max_results=n,
                client=client,
                timeout=settings.arxiv_timeout,
            ),
            timeout=settings.arxiv_timeout,
            raise_on_failure=raise_on_failure,
            min_retry_wait=settings.arxiv_rate_limit_seconds,
        )

    async def fetch_web(
        self,
        query: str,
        *,
        client: httpx.AsyncClient | None = None,
        max_results: int | None = None,
        raise_on_failure: bool = False,
    ) -> list[Source]:
        n = max_results or settings.max_sources_per_query
        self._logger.info("fetch_web_start", extra={"query": query[:80], "max_results": n})
        provider = self._web_provider()
        return await self._run_fetch(
            "web",
            lambda: ai.fetch_web(
                query,
                max_results=n,
                client=client,
                provider=provider,
            ),
            timeout=settings.web_timeout,
            raise_on_failure=raise_on_failure,
        )

    def synthesize(
        self,
        question: str,
        sources: list[Source],
        *,
        llm: Any = None,
    ) -> AnswerWithCitations:
        """Call ai.synthesize with retry and structured logging."""
        if not sources:
            raise ValueError("Cannot synthesize with zero sources")
        self._logger.info(
            "synthesize_start",
            extra={"question": question[:80], "n_sources": len(sources)},
        )
        t0 = time.perf_counter()
        try:
            resolved_llm = self._llm_from_settings(llm)
            for attempt in _make_sync_retry():
                with attempt:
                    result = ai.synthesize(question, sources, llm=resolved_llm)
        except Exception as exc:
            self._logger.error("synthesize_failed", extra={"error": str(exc)})
            raise
        elapsed = time.perf_counter() - t0
        self._logger.info(
            "synthesize_ok",
            extra={"n_citations": len(result.citations), "elapsed_s": round(elapsed, 3)},
        )
        return result


ai_service = AIService()
