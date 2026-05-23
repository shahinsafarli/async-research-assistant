"""
Persistent storage for research sessions.

Supports two backends selected by DATABASE_URL:
  - SQLite   (default dev):  sqlite+aiosqlite:///./researcher.db
  - PostgreSQL (production): postgresql+asyncpg://user:pass@host:5432/dbname

Both are fully async.  Switch by setting DATABASE_URL in .env or via Docker
environment.  The schema and query interface are identical on both backends.

PostgreSQL uses $1/$2 parameter style and SERIAL; SQLite uses ? and
AUTOINCREMENT.  The factory function `get_repository()` (and the module-level
`repository` singleton) return the right implementation automatically.
"""
from __future__ import annotations

import abc
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from src.config import settings
from src.models import ResearchResult

logger = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────────────────────

def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql") or url.startswith("postgres://")


_SQLITE_PATH = settings.database_url.replace("sqlite+aiosqlite:///", "")
_PG_DSN = settings.database_url if _is_postgres(settings.database_url) else None
# backward-compat alias used by the tmp_db test fixture
_DB_PATH = _SQLITE_PATH

# Normalise postgresql+asyncpg:// → asyncpg-native DSN (drop the SA prefix)
if _PG_DSN and _PG_DSN.startswith("postgresql+asyncpg://"):
    _PG_DSN = _PG_DSN.replace("postgresql+asyncpg://", "postgresql://", 1)


# ── abstract base ─────────────────────────────────────────────────────────────

class BaseRepository(abc.ABC):
    """Backend-agnostic interface for research session persistence."""

    @abc.abstractmethod
    async def save_session(self, result: ResearchResult) -> int:
        """Persist a ResearchResult and return the new row id."""
        raise NotImplementedError

    @abc.abstractmethod
    async def list_sessions(self, limit: int = 20) -> list[dict]:
        """Return the N most recent research sessions."""
        raise NotImplementedError

    @abc.abstractmethod
    async def get_session(self, session_id: int) -> dict | None:
        """Fetch a single session by id."""
        raise NotImplementedError


# ── SQLite backend ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def _sqlite_connect() -> AsyncIterator[aiosqlite.Connection]:
    db_path = _SQLITE_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


_SQLITE_DDL = """
    CREATE TABLE IF NOT EXISTS research_sessions (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        question      TEXT    NOT NULL,
        answer        TEXT    NOT NULL,
        citations     TEXT    NOT NULL,
        sources_count INTEGER NOT NULL DEFAULT 0,
        sources_failed TEXT   NOT NULL DEFAULT '[]',
        elapsed_s     REAL    NOT NULL DEFAULT 0.0,
        created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
    )
"""


class SQLiteRepository(BaseRepository):
    """aiosqlite-backed repository (default for local dev)."""

    async def _init(self) -> None:
        async with _sqlite_connect() as conn:
            await conn.execute(_SQLITE_DDL)
            await conn.commit()
        logger.info("sqlite_db_initialized", extra={"path": _SQLITE_PATH})

    async def save_session(self, result: ResearchResult) -> int:
        await self._init()
        citations_json = json.dumps([c.model_dump() for c in result.citations])
        failed_json = json.dumps(result.sources_failed)
        async with _sqlite_connect() as conn:
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
            sid = cursor.lastrowid
        logger.info("session_saved", extra={"id": sid, "backend": "sqlite",
                                            "question": result.question[:60]})
        return sid

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        await self._init()
        async with _sqlite_connect() as conn:
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
        await self._init()
        async with _sqlite_connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM research_sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None


# ── PostgreSQL backend ────────────────────────────────────────────────────────

_PG_DDL = """
    CREATE TABLE IF NOT EXISTS research_sessions (
        id            SERIAL PRIMARY KEY,
        question      TEXT        NOT NULL,
        answer        TEXT        NOT NULL,
        citations     TEXT        NOT NULL,
        sources_count INTEGER     NOT NULL DEFAULT 0,
        sources_failed TEXT       NOT NULL DEFAULT '[]',
        elapsed_s     FLOAT       NOT NULL DEFAULT 0.0,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
"""


class PostgreSQLRepository(BaseRepository):
    """asyncpg-backed repository (production / Docker Compose)."""

    async def _pool(self):
        try:
            import asyncpg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "asyncpg is not installed. Add 'asyncpg' to requirements.txt."
            ) from exc
        return await asyncpg.create_pool(_PG_DSN, min_size=1, max_size=5)

    async def _init(self, conn) -> None:
        await conn.execute(_PG_DDL)

    async def save_session(self, result: ResearchResult) -> int:
        import asyncpg  # noqa: F401
        citations_json = json.dumps([c.model_dump() for c in result.citations])
        failed_json = json.dumps(result.sources_failed)
        pool = await self._pool()
        try:
            async with pool.acquire() as conn:
                await self._init(conn)
                sid = await conn.fetchval(
                    """
                    INSERT INTO research_sessions
                        (question, answer, citations, sources_count, sources_failed, elapsed_s)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                    """,
                    result.question,
                    result.answer,
                    citations_json,
                    len(result.sources_used),
                    failed_json,
                    result.elapsed_seconds,
                )
        finally:
            await pool.close()
        logger.info("session_saved", extra={"id": sid, "backend": "postgresql",
                                            "question": result.question[:60]})
        return sid

    async def list_sessions(self, limit: int = 20) -> list[dict]:
        import asyncpg  # noqa: F401
        pool = await self._pool()
        try:
            async with pool.acquire() as conn:
                await self._init(conn)
                rows = await conn.fetch(
                    """
                    SELECT id, question, answer, citations, sources_count,
                           sources_failed, elapsed_s,
                           created_at::text AS created_at
                    FROM research_sessions
                    ORDER BY created_at DESC, id DESC
                    LIMIT $1
                    """,
                    limit,
                )
        finally:
            await pool.close()
        return [dict(r) for r in rows]

    async def get_session(self, session_id: int) -> dict | None:
        import asyncpg  # noqa: F401
        pool = await self._pool()
        try:
            async with pool.acquire() as conn:
                await self._init(conn)
                row = await conn.fetchrow(
                    "SELECT *, created_at::text AS created_at "
                    "FROM research_sessions WHERE id = $1",
                    session_id,
                )
        finally:
            await pool.close()
        return dict(row) if row else None


# ── factory + singleton ───────────────────────────────────────────────────────

def get_repository() -> BaseRepository:
    """Return the repository implementation matching DATABASE_URL."""
    url = settings.database_url
    if _is_postgres(url):
        logger.info("storage_backend", extra={"backend": "postgresql", "url": url[:40]})
        return PostgreSQLRepository()
    logger.info("storage_backend", extra={"backend": "sqlite", "path": _SQLITE_PATH})
    return SQLiteRepository()


# Module-level singleton — used by ResearchEngine unless overridden in tests.
repository: BaseRepository = get_repository()

# backward-compat alias — old tests import ResearchRepository
ResearchRepository = SQLiteRepository
