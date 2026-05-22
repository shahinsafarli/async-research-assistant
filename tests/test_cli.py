"""CLI tests using Click's CliRunner — fully offline."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---- help / version tests ------------------------------------------------

def test_cli_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ask" in result.output


def test_ask_help(runner):
    result = runner.invoke(cli, ["ask", "--help"])
    assert result.exit_code == 0
    assert "--sources" in result.output
    assert "--no-cache" in result.output


def test_history_help(runner):
    result = runner.invoke(cli, ["history", "--help"])
    assert result.exit_code == 0
    assert "--limit" in result.output


# ---- validation errors ---------------------------------------------------

def test_ask_empty_question_rejected(runner):
    """Passing a blank question should exit with an error."""
    result = runner.invoke(cli, ["ask", ""])
    assert result.exit_code != 0


def test_ask_invalid_source_rejected(runner):
    """Passing an unknown source name should exit with an error."""
    result = runner.invoke(cli, ["ask", "What is AI?", "--sources", "invalid_source"])
    assert result.exit_code != 0


def test_history_invalid_limit(runner):
    """--limit 0 should exit non-zero."""
    result = runner.invoke(cli, ["history", "--limit", "0"])
    assert result.exit_code != 0


# ---- happy-path tests (mocked engine) ------------------------------------

def _make_mock_result():
    from src.models import CitationRecord, ResearchResult, SourceResult
    return ResearchResult(
        question="What is photosynthesis?",
        answer="Photosynthesis converts light into energy [1].",
        citations=[CitationRecord(index=1, title="Photosynthesis", url="https://en.wikipedia.org/wiki/Photosynthesis", origin="wikipedia")],
        sources_used=[SourceResult(title="Photosynthesis", url="https://en.wikipedia.org/wiki/Photosynthesis", snippet="...", origin="wikipedia")],
        sources_failed=[],
        elapsed_seconds=0.42,
    )


def test_ask_displays_answer(runner):
    """ask command prints the question and answer."""
    mock_result = _make_mock_result()

    with patch("src.cli.ResearchEngine") as MockEngine:
        instance = MagicMock()
        instance.research = AsyncMock(return_value=mock_result)
        MockEngine.return_value = instance

        result = runner.invoke(cli, ["ask", "What is photosynthesis?"])

    assert result.exit_code == 0
    assert "Photosynthesis" in result.output
    assert "[1]" in result.output


def test_ask_displays_failed_sources_note(runner):
    """When sources fail, a note is printed to stderr."""
    from src.models import CitationRecord, ResearchResult
    mock_result = ResearchResult(
        question="Q?",
        answer="Partial answer [1].",
        citations=[CitationRecord(index=1, title="T", url="U", origin="wikipedia")],
        sources_used=[],
        sources_failed=["arxiv"],
        elapsed_seconds=1.1,
    )

    with patch("src.cli.ResearchEngine") as MockEngine:
        instance = MagicMock()
        instance.research = AsyncMock(return_value=mock_result)
        MockEngine.return_value = instance

        result = runner.invoke(cli, ["ask", "What is Q?"])

    assert "arxiv" in result.output


def test_history_displays_sessions(runner):
    """history command renders a table of past sessions."""
    sessions = [
        {
            "id": 1,
            "question": "What is photosynthesis?",
            "answer": "...",
            "citations": "[]",
            "sources_count": 3,
            "sources_failed": "[]",
            "elapsed_s": 0.5,
            "created_at": "2026-05-14T10:00:00",
        }
    ]

    with patch("src.cli.ResearchEngine") as MockEngine:
        instance = MagicMock()
        instance.get_history = AsyncMock(return_value=sessions)
        MockEngine.return_value = instance

        result = runner.invoke(cli, ["history", "--limit", "5"])

    assert result.exit_code == 0
    assert "photosynthesis" in result.output.lower()


# ---- error-path tests ---------------------------------------------------

def test_ask_engine_exception_exits_nonzero(runner):
    """If the research engine raises, the CLI exits non-zero."""
    with patch("src.cli.ResearchEngine") as MockEngine:
        instance = MagicMock()
        instance.research = AsyncMock(side_effect=RuntimeError("network down"))
        MockEngine.return_value = instance

        result = runner.invoke(cli, ["ask", "What is AI?"])

    assert result.exit_code != 0


def test_ask_sources_wiki_only(runner):
    """--sources wiki only queries wikipedia."""
    mock_result = _make_mock_result()

    with patch("src.cli.ResearchEngine") as MockEngine:
        instance = MagicMock()
        instance.research = AsyncMock(return_value=mock_result)
        MockEngine.return_value = instance

        result = runner.invoke(cli, ["ask", "What is photosynthesis?", "--sources", "wiki"])

    assert result.exit_code == 0
    called_request = instance.research.call_args[0][0]
    assert called_request.sources == ["wiki"]
