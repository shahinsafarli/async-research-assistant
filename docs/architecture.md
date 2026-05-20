# Architecture — Async Research Assistant

## Day 2 Architecture Diagram

```
+----------+          +------------------+
|   CLI    |          |  Streamlit UI    |
| (click)  |          |   (app.py)       |
+----+-----+          +--------+---------+
     |                         |
     +----------+--------------+
                |
                v
+----------------------------------+
|        ResearchEngine            |
|        src/core/researcher.py    |
|                                  |
|  1. Validates QuestionRequest    |
|  2. Delegates to orchestrator    |
|  3. Calls ai.synthesize()        |
|  4. Persists session             |
|  5. Returns ResearchResult       |
+------+-------------------+-------+
       |                   |
       v                   v
+------+------+    +-------+--------+
| Research    |    | ResearchRepo   |
| Orchestrator|    | (SQLite via    |
| (concurrency|    |  aiosqlite)    |
|  layer)     |    +----------------+
+------+------+
       |
       | run_concurrent([wiki, arxiv, web], max_concurrent=MAX_CONCURRENT)
       | + per-source timeouts
       | + graceful degradation
       |
+------+------+------+
|       |            |
v       v            v
wiki  arxiv         web
      
       ↓
+------------------------+
|  AIService             |
|  (retries + timeout +  |
|   logging wrapper)     |
+----------+-------------+
           |
           v
+----------+-------------+
|  provided ai/ package  |
|  - fetch_wikipedia()   |
|  - fetch_arxiv()       |
|  - fetch_web()         |
|  - synthesize()        |
+----------+-------------+
           |
           v
  CacheBackend (ABC)
  ├── InMemoryCache
  └── FilesystemCache
```

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `src/config.py` | Single source of truth for all settings; read from `.env` via pydantic-settings |
| `src/models.py` | SE-layer Pydantic models; no naked dicts cross module boundaries |
| `src/services/ai_service.py` | Retry + timeout + logging wrapper around `ai.*`; TRANSIENT_ERRORS retried with tenacity |
| `src/services/cache.py` | `CacheBackend` ABC with `InMemoryCache` and `FilesystemCache` implementations |
| `src/concurrency/pipeline.py` | Generic `run_concurrent(coroutines, max_concurrent)` with semaphore |
| `src/concurrency/orchestrator.py` | Per-question parallel fetch through the bounded semaphore pipeline + per-source timeout + graceful degradation |
| `src/core/researcher.py` | Business logic; owns the `ResearchEngine` class that coordinates everything |
| `src/storage/repository.py` | `ResearchRepository` class; all SQL in one place; aiosqlite async |
| `src/cli.py` | Click CLI: `ask` and `history` commands |
| `app.py` | Streamlit UI (bonus) |

## Key Design Decisions

1. **asyncio over threads** — the bottleneck is I/O (HTTP to Wikipedia/arXiv/web). asyncio gives cooperative multitasking with minimal overhead; threads would add unnecessary synchronization complexity.

2. **Semaphore(5) default** — prevents unbounded bursts to free-tier APIs. Configurable via `MAX_CONCURRENT` env var.

3. **`return_exceptions=True` in gather** — ensures a single failing source (e.g. arXiv timeout) does not cancel the other two fetches.

4. **CacheBackend ABC** — makes the cache backend swappable without touching business logic. The test suite injects `InMemoryCache(ttl=0)` to disable caching; production uses `FilesystemCache`.

5. **Pydantic everywhere** — all cross-module data uses typed models; never raw dicts.
