#!/usr/bin/env python
"""
End-to-end scripted demo — runs all 5 questions from data/research_questions.json.

Modes
-----
  python scripts/demo.py              # live mode (requires API keys in .env)
  python scripts/demo.py --offline    # offline mode (fake LLM + no network)

Output is written to stdout and also saved to artefacts/demo_YYYY-MM-DD.txt.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path regardless of where the script is run from.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.models import QuestionRequest
from src.concurrency.orchestrator import ResearchOrchestrator
from src.core.researcher import ResearchEngine
from src.services.cache import InMemoryCache


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--offline", action="store_true", help="Use fake providers (no API keys needed).")
    p.add_argument("--limit", type=int, default=5, help="Max number of questions to run (default 5).")
    p.add_argument("--sources", default="wiki,arxiv,web", help="Comma-separated source list.")
    return p.parse_args()


def _offline_llm():
    """Return a fake LLM that works without any API key."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tests.conftest import FakeLLM
    return FakeLLM(
        response=(
            "Based on the available sources, this topic involves several important "
            "concepts [1]. Research in this area has grown substantially [2]. "
            "Multiple perspectives exist on the subject [1][2][3]."
        )
    )


def _offline_ai_service():
    """Patch the AI service to return canned sources without network."""
    from tests.conftest import FakeAIService
    from ai.schemas import Source

    canned = [
        Source(title="Wikipedia Overview", url="https://en.wikipedia.org/wiki/Example",
               snippet="A comprehensive overview of the topic.", origin="wikipedia"),
        Source(title="arXiv Research Paper", url="https://arxiv.org/abs/0000.00000",
               snippet="Recent research covering key aspects of this domain.", origin="arxiv"),
        Source(title="Web Resource", url="https://example.com/resource",
               snippet="Practical information on the topic from the web.", origin="web"),
    ]
    return FakeAIService(sources=canned)


def render(result) -> str:
    lines = [
        "=" * 72,
        f"Q: {result.question}",
        "",
        f"A: {result.answer}",
        "",
    ]
    if result.citations:
        lines.append("References:")
        for c in result.citations:
            lines.append(f"  [{c.index}] ({c.origin}) {c.title}")
            lines.append(f"      {c.url}")
    lines.append(f"\n[elapsed: {result.elapsed_seconds:.2f}s | "
                 f"sources: {len(result.sources_used)} | "
                 f"failed: {result.sources_failed or 'none'}]")
    return "\n".join(lines)


async def run_demo(args: argparse.Namespace) -> None:
    here = Path(__file__).parent.parent
    qfile = here / "data" / "research_questions.json"
    if not qfile.exists():
        print(f"!! Missing {qfile}", file=sys.stderr)
        sys.exit(2)

    questions = json.loads(qfile.read_text(encoding="utf-8"))["questions"][: args.limit]
    source_list = [s.strip() for s in args.sources.split(",") if s.strip()]

    llm = _offline_llm() if args.offline else None
    ai_svc = _offline_ai_service() if args.offline else None

    cache = InMemoryCache(ttl_seconds=0 if not args.offline else 3600)
    orch = ResearchOrchestrator(ai_svc=ai_svc, cache=cache) if ai_svc else ResearchOrchestrator(cache=cache)
    engine = ResearchEngine(orchestrator=orch, ai_svc=ai_svc)

    output_lines: list[str] = []
    total_start = time.perf_counter()

    print(f"\nAsync Research Assistant — Demo ({'OFFLINE' if args.offline else 'LIVE'})")
    print(f"Questions: {len(questions)}  Sources: {source_list}\n")

    for q_data in questions:
        request = QuestionRequest(question=q_data["text"], sources=source_list)
        result = await engine.research(request, llm=llm)
        rendered = render(result)
        print(rendered)
        output_lines.append(rendered)

    total = time.perf_counter() - total_start
    summary = f"\n{'=' * 72}\nTotal wall-clock time: {total:.2f}s for {len(questions)} question(s)\n"
    print(summary)
    output_lines.append(summary)

    artefacts_dir = here / "artefacts"
    artefacts_dir.mkdir(exist_ok=True)
    out_file = artefacts_dir / f"demo_{date.today().isoformat()}.txt"
    out_file.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"[output saved to {out_file}]")


def main() -> None:
    args = parse_args()
    asyncio.run(run_demo(args))


if __name__ == "__main__":
    main()
