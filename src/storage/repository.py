"""
Persistent storage for research sessions.

Uses aiosqlite so the SE layer stays fully async. The schema is intentionally
minimal — we store what's needed for the `history` command and for the report's
"cache hit rate" measurement.

PostgreSQL can replace SQLite by changing DATABASE_URL to a postgresql+asyncpg://
connection string and replacing `aiosqlite` with `asyncpg` — the SQL is
compatible.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from src.config import settings
from src.models import ResearchResult

logger = logging.getLogger(__name__)

_DB_PATH = settings.database_url.replace("sqlite+aiosqlite:///", "")


@asynccontextmanager
async def _connect() -> AsyncIterator[aiosqlite.Connection]:
    """Open an aiosqlite connection as an async context manager."""
    db_path = _DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


async def init_db() -> None:
    """Create tables if they do not exist yet."""
    async with _connect() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS research_sessions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                question     TEXT    NOT NULL,
                answer       TEXT    NOT NULL,
                citations    TEXT    NOT NULL,
                sources_count INTEGER NOT NULL DEFAULT 0,
                sources_failed TEXT NOT NULL DEFAULT '[]',
                elapsed_s    REAL    NOT NULL DEFAULT 0.0,
                created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await conn.commit()
    logger.info("db_initialized", extra={"path": _DB_PATH})


class ResearchRepository:
    """Encapsulates all SQL for research session persistence.

    Using a class (not bare functions) so it can be injected and mocked in
    tests.
    """

    async def save_session(self, result: ResearchResult) -> int:
        """Persist a ResearchResult and return the new row id."""
        await init_db()
        citations_json = json.dumps([c.model_dump() for c in result.citations])
        failed_json = json.dumps(result.sources_failed)
        async with _connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO research_sessions
                    (question, answer, citations, sources_count, sources_failed, elapsed_s)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.question,
                    result.answer,
                    citations_json,
                    len(result.sources_used),
                    failed_json,
                    result.elapsed_seconds,
                ),
            )
            await conn.commit()
            session_id = cursor.lastrowid
        logger.info("session_saved", extra={"id": session_id, "question": result.question[:60]})
        return session_id

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """Return the N most recent research sessions."""
        await init_db()
        async with _connect() as conn:
            cursor = await conn.execute(
                """
                SELECT id, question, answer, citations, sources_count,
                       sources_failed, elapsed_s, created_at
                FROM research_sessions
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_session(self, session_id: int) -> dict | None:
        """Fetch a single session by id."""
        await init_db()
        async with _connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM research_sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None


repository = ResearchRepository()
