"""
CLI entry point for the Async Research Assistant.

Commands
--------
  ask     Ask a research question and display a cited answer.
  history Show recent research sessions.

Run:
    python -m researcher ask "What is photosynthesis?"
    python -m researcher ask "quantum computing basics" --sources wiki,arxiv
    python -m researcher ask "latest LLM research" --no-cache
    python -m researcher history --limit 5
"""
from __future__ import annotations

import asyncio
import logging
import sys

import click

from src.core.researcher import ResearchEngine
from src.models import QuestionRequest
from src.services.cache import FilesystemCache

logger = logging.getLogger(__name__)


@click.group()
@click.option("--log-level", default="INFO", show_default=True, help="Logging verbosity.")
def cli(log_level: str) -> None:
    """Async Research Assistant — query Wikipedia, arXiv, and web in parallel."""
    logging.getLogger().setLevel(log_level.upper())


@cli.command("ask")
@click.argument("question")
@click.option(
    "--sources",
    default="wiki,arxiv,web",
    show_default=True,
    help="Comma-separated subset of: wiki, arxiv, web.",
)
@click.option("--no-cache", "no_cache", is_flag=True, default=False, help="Bypass the cache.")
def ask_command(question: str, sources: str, no_cache: bool) -> None:
    """Ask a research question and display a cited answer."""
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    try:
        request = QuestionRequest(question=question, sources=source_list, no_cache=no_cache)
    except Exception as exc:
        click.echo(f"Validation error: {exc}", err=True)
        sys.exit(1)

    cache = FilesystemCache()
    eng = ResearchEngine(cache=cache)

    try:
        result = asyncio.run(eng.research(request))
    except Exception as exc:
        logger.error("ask_failed", extra={"error": str(exc)})
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    _render_result(result)

    if result.sources_failed:
        click.echo(
            f"\n[note] The following sources could not be reached: "
            f"{', '.join(result.sources_failed)}",
            err=True,
        )


@cli.command("history")
@click.option("--limit", default=10, show_default=True, type=int, help="Number of sessions.")
def history_command(limit: int) -> None:
    """Show recent research sessions from local storage."""
    if limit < 1:
        click.echo("--limit must be >= 1", err=True)
        sys.exit(1)

    eng = ResearchEngine()
    try:
        sessions = asyncio.run(eng.get_history(limit=limit))
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if not sessions:
        click.echo("No research sessions found.")
        return

    click.echo(f"\n{'ID':<6} {'Question':<55} {'Sources':>7} {'Time(s)':>7}  {'Date'}")
    click.echo("-" * 90)
    for s in sessions:
        q = s["question"][:53] + ".." if len(s["question"]) > 55 else s["question"]
        click.echo(
            f"{s['id']:<6} {q:<55} {s['sources_count']:>7} "
            f"{s['elapsed_s']:>7.2f}  {s['created_at']}"
        )


def _render_result(result: "ResearchResult") -> None:  # noqa: F821
    """Pretty-print a ResearchResult to stdout."""
    click.echo(f"\nQ: {result.question}\n")
    click.echo(f"A: {result.answer}\n")
    if result.citations:
        click.echo("References:")
        for c in result.citations:
            click.echo(f"  [{c.index}] ({c.origin}) {c.title}")
            click.echo(f"      {c.url}")
    click.echo(f"\n[elapsed: {result.elapsed_seconds:.2f}s]")


if __name__ == "__main__":
    cli()
