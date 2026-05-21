"""
TTL-aware source cache keyed by (source_name, canonicalized_query).

Architecture — abstract base + two concrete backends:
  - InMemoryCache  : fast, lost on restart, no dependencies
  - FilesystemCache: survives restarts, stored as JSON under CACHE_DIR

The CLI selects InMemoryCache by default; the production path wires
FilesystemCache.  Both honour the same interface (CacheBackend ABC) so the
orchestrator is backend-agnostic.
"""
from __future__ import annotations

import abc
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)


def canonicalize_query(query: str) -> str:
    """Normalise a query string into a stable cache key.

    Lower-case, collapse whitespace, strip punctuation at the edges so that
    'WHAT IS PHOTOSYNTHESIS?' and 'what is photosynthesis' map to the same key.
    """
    q = query.lower().strip()
    q = re.sub(r"\s+", " ", q)
    q = q.strip("?!.,;:")
    return q


def _cache_key(source: str, query: str) -> str:
    """Produce a short stable key for the (source, canonicalized_query) pair."""
    raw = f"{source}:{canonicalize_query(query)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class CacheBackend(abc.ABC):
    """Abstract cache that stores and retrieves lists of source dicts."""

    @abc.abstractmethod
    def get(self, source: str, query: str) -> list[dict] | None:
        """Return cached sources or None on miss / expiry."""
        raise NotImplementedError

    @abc.abstractmethod
    def set(self, source: str, query: str, data: list[dict]) -> None:
        """Store sources for the given (source, query) pair."""
        raise NotImplementedError

    @abc.abstractmethod
    def invalidate(self, source: str, query: str) -> None:
        """Remove a specific cache entry."""
        raise NotImplementedError

    @abc.abstractmethod
    def clear(self) -> None:
        """Remove all entries."""
        raise NotImplementedError


class InMemoryCache(CacheBackend):
    """Process-local TTL cache backed by a plain dict."""

    def __init__(self, ttl_seconds: int | None = None) -> None:
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
        self._store: dict[str, tuple[float, list[dict]]] = {}

    def get(self, source: str, query: str) -> list[dict] | None:
        key = _cache_key(source, query)
        entry = self._store.get(key)
        if entry is None:
            logger.debug("cache_miss", extra={"source": source, "key": key[:8]})
            return None
        timestamp, data = entry
        if self._ttl > 0 and (time.time() - timestamp) > self._ttl:
            del self._store[key]
            logger.debug("cache_expired", extra={"source": source, "key": key[:8]})
            return None
        logger.debug("cache_hit", extra={"source": source, "key": key[:8]})
        return data

    def set(self, source: str, query: str, data: list[dict]) -> None:
        key = _cache_key(source, query)
        self._store[key] = (time.time(), data)
        logger.debug("cache_set", extra={"source": source, "key": key[:8], "n": len(data)})

    def invalidate(self, source: str, query: str) -> None:
        key = _cache_key(source, query)
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


class FilesystemCache(CacheBackend):
    """JSON files on disk under CACHE_DIR/{key}.json — survives restarts."""

    def __init__(self, cache_dir: str | None = None, ttl_seconds: int | None = None) -> None:
        self._dir = Path(cache_dir or settings.cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, source: str, query: str) -> list[dict] | None:
        key = _cache_key(source, query)
        p = self._path(key)
        if not p.exists():
            logger.debug("fs_cache_miss", extra={"source": source, "key": key[:8]})
            return None
        try:
            payload: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("fs_cache_corrupt", extra={"key": key[:8], "error": str(exc)})
            return None
        if self._ttl > 0 and (time.time() - payload["ts"]) > self._ttl:
            p.unlink(missing_ok=True)
            logger.debug("fs_cache_expired", extra={"source": source, "key": key[:8]})
            return None
        logger.debug("fs_cache_hit", extra={"source": source, "key": key[:8]})
        return payload["data"]

    def set(self, source: str, query: str, data: list[dict]) -> None:
        key = _cache_key(source, query)
        payload = {"ts": time.time(), "source": source, "data": data}
        try:
            self._path(key).write_text(json.dumps(payload), encoding="utf-8")
        except OSError as exc:
            logger.warning("fs_cache_write_failed", extra={"key": key[:8], "error": str(exc)})
        logger.debug("fs_cache_set", extra={"source": source, "key": key[:8], "n": len(data)})

    def invalidate(self, source: str, query: str) -> None:
        key = _cache_key(source, query)
        self._path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        for p in self._dir.glob("*.json"):
            p.unlink(missing_ok=True)
