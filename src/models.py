"""
Application-level Pydantic models for the SE layer.
These are separate from the ai/ schemas and carry SE-layer concerns
(timestamps, IDs, status fields, cache metadata).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class QuestionRequest(BaseModel):
    """Validated input from the user."""

    question: str = Field(..., min_length=3, max_length=1000)
    sources: list[str] = Field(
        default_factory=lambda: ["wiki", "arxiv", "web"],
        description="Which sources to query: wiki, arxiv, web",
    )
    no_cache: bool = False

    @field_validator("sources")
    @classmethod
    def _valid_sources(cls, v: list[str]) -> list[str]:
        allowed = {"wiki", "arxiv", "web"}
        bad = [s for s in v if s not in allowed]
        if bad:
            raise ValueError(f"Unknown source(s): {bad!r}. Allowed: {sorted(allowed)}")
        return v

    @field_validator("question")
    @classmethod
    def _clean_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be blank")
        return v


class SourceResult(BaseModel):
    """A single retrieved source (mirrors ai.Source but with SE metadata)."""

    title: str
    url: str
    snippet: str
    origin: str
    fetched_from_cache: bool = False


class CitationRecord(BaseModel):
    """A numbered citation in the final answer."""

    index: int
    title: str
    url: str
    origin: str


class ResearchResult(BaseModel):
    """The complete result of a research session."""

    question: str
    answer: str
    citations: list[CitationRecord] = Field(default_factory=list)
    sources_used: list[SourceResult] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
    from_cache: bool = False
    elapsed_seconds: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResearchSession(BaseModel):
    """Persisted research session record."""

    id: Optional[int] = None
    question: str
    answer: str
    citations_json: str
    sources_count: int
    sources_failed: list[str] = Field(default_factory=list)
    elapsed_seconds: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CacheEntry(BaseModel):
    """A cached fetch result keyed by (source, canonicalized_query)."""

    source: str
    query_key: str
    sources_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ErrorResponse(BaseModel):
    """Structured error returned to callers."""

    error: str
    detail: Optional[str] = None
