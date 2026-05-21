#!/usr/bin/env python
"""
Benchmark: sequential vs concurrent source fetching.

Run:
    python scripts/bench.py --n 5 --offline
    python scripts/bench.py --n 5              # requires API keys

The script runs the same N questions twice:
  1. Sequential:  await each (wiki + arxiv + web) fetch one by one
  2. Concurrent:  asyncio.gather all three fetches per question in parallel

Copy the printed table into README.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.services.ai_service import AIService


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=5, help="Number of questions to benchmark (default 5).")
    p.add_argument("--offline", action="store_true", help="Use fake providers (no API keys needed).")
    p.add_argument("--delay", type=float, default=0.15, help="Per-source fake latency in seconds for --offline.")
    return p.parse_args()


def _get_questions(n: int) -> list[str]:
    here = Path(__file__).parent.parent
    qfile = here / "data" / "research_questions.json"
    if qfile.exists():
        qs = json.loads(qfile.read_text(encoding="utf-8"))["questions"]
        return [q["text"] for q in qs[:n]]
    return [f"What is topic {i}?" for i in range(n)]


class OfflineBenchmarkService:
    """Fake source service with realistic IO latency for reproducible benchmarks."""

    def __init__(self, delay: float) -> None:
        from ai.schemas import Source
        self.delay = delay
        self._wiki = [Source(title="Wiki", url="https://en.wikipedia.org/wiki/T", snippet="snippet", origin="wikipedia")]
        self._arxiv = [Source(title="arXiv", url="https://arxiv.org/abs/0000", snippet="snippet", origin="arxiv")]
        self._web = [Source(title="Web", url="https://example.com", snippet="snippet", origin="web")]

    async def fetch_wikipedia(self, query: str, **kwargs):
        await asyncio.sleep(self.delay)
        return self._wiki

    async def fetch_arxiv(self, query: str, **kwargs):
        await asyncio.sleep(self.delay)
        return self._arxiv

    async def fetch_web(self, query: str, **kwargs):
        await asyncio.sleep(self.delay)
        return self._web


def _offline_svc(delay: float):
    return OfflineBenchmarkService(delay=delay)


async def run_sequential(svc, questions: list[str]) -> float:
    """Fetch all three sources for each question one at a time."""
    t0 = time.perf_counter()
    for q in questions:
        await svc.fetch_wikipedia(q)
        await svc.fetch_arxiv(q)
        await svc.fetch_web(q)
    return time.perf_counter() - t0


async def run_concurrent(svc, questions: list[str]) -> float:
    """Fetch all three sources for each question in parallel."""
    t0 = time.perf_counter()
    for q in questions:
        await asyncio.gather(
            svc.fetch_wikipedia(q),
            svc.fetch_arxiv(q),
            svc.fetch_web(q),
            return_exceptions=True,
        )
    return time.perf_counter() - t0


async def main_async(args: argparse.Namespace) -> None:
    questions = _get_questions(args.n)
    svc = _offline_svc(args.delay) if args.offline else AIService()

    print(f"\nBenchmarking {args.n} question(s) ({'OFFLINE' if args.offline else 'LIVE'}) ...")
    print("Clearing any cached state between runs.\n")

    seq_time = await run_sequential(svc, questions)
    con_time = await run_concurrent(svc, questions)
    speedup = seq_time / con_time if con_time > 0 else float("inf")

    print(f"\n{'Mode':<15} {'Time (s)':>10} {'Speedup':>10}")
    print("-" * 38)
    print(f"{'Sequential':<15} {seq_time:>10.3f} {'1.0x':>10}")
    print(f"{'Concurrent':<15} {con_time:>10.3f} {speedup:>9.1f}x")
    print(f"\nN={args.n}  sources=wiki+arxiv+web  max_concurrent={settings.max_concurrent}")
    print("\nCopy this table into README.md ↑\n")


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
