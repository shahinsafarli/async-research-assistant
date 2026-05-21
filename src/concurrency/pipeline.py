"""
Generic concurrent pipeline with bounded parallelism.

Usage:
    results = await run_concurrent(coroutines, max_concurrent=5)

Returns results (or exceptions) in the same order as input.
Never raises — caller inspects each element to detect failures.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, TypeVar

from src.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def run_concurrent(
    coroutines: list[Awaitable[T]],
    max_concurrent: int | None = None,
) -> list[T | BaseException]:
    """Run coroutines concurrently, bounded by a semaphore.

    Parameters
    ----------
    coroutines:
        Awaitables to run.
    max_concurrent:
        Upper bound on simultaneous tasks; falls back to ``settings.max_concurrent``.

    Returns
    -------
    list[T | BaseException]
        Results in input order.  Exceptions are *returned*, not raised, so a
        single failure does not abort the batch.
    """
    limit = max_concurrent or settings.max_concurrent
    sem = asyncio.Semaphore(limit)

    async def _guarded(coro: Awaitable[T]) -> T:
        async with sem:
            return await coro

    results = await asyncio.gather(
        *[_guarded(c) for c in coroutines],
        return_exceptions=True,
    )
    errors = [r for r in results if isinstance(r, BaseException)]
    if errors:
        logger.warning(
            "pipeline_partial_failure",
            extra={"total": len(coroutines), "errors": len(errors)},
        )
    return list(results)
