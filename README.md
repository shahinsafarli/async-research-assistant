# Async Research Assistant

> A user asks a research question; the system queries Wikipedia, arXiv, and a
> web-search API **in parallel**, then synthesizes a single cited answer using
> an LLM.

**Team:** Shahin Safarli · Jeyhun Aliyev · Emil Jafarov  
**Topic:** 4 — Async Research Assistant · **Course:** AI-ENG-110 Software Engineering, AI Academy  
**Repository:** https://github.com/shahinsafarli/async-research-assistant  
**Due:** May 23, 2026 at 23:59 (UTC+4)

---

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/shahinsafarli/async-research-assistant
cd async-research-assistant
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env             # fill in your API keys

# 3. Run provided smoke tests (must pass)
pytest tests/test_ai_smoke.py -v

# 4. Run offline demo (no API keys needed)
python demo_ai.py --offline
python scripts/demo.py --offline
```

---

## CLI Usage

```bash
# Ask a research question (all three sources)
python -m researcher ask "What is photosynthesis?"

# Restrict to specific sources
python -m researcher ask "quantum computing basics" --sources wiki,arxiv

# Bypass the cache
python -m researcher ask "latest LLM research" --no-cache

# View session history
python -m researcher history --limit 10
```

---

## Streamlit Web UI (Bonus)

```bash
streamlit run app.py
# Open http://localhost:8501
```

---

## Docker — SQLite (zero-config local)

```bash
# Build
docker build -t async-research-assistant .

# Offline demo — no keys, no external services
docker run async-research-assistant

# Live mode
docker run --env-file .env async-research-assistant python scripts/demo.py

# CLI inside Docker
docker run --env-file .env async-research-assistant \
  python -m researcher ask "What is photosynthesis?"

# Streamlit
docker run --env-file .env -p 8501:8501 async-research-assistant \
  streamlit run app.py --server.address 0.0.0.0
```

---

## Docker Compose — PostgreSQL (production)

Docker Compose starts **two services**: a PostgreSQL 16 database and the
application.  The app waits for the database healthcheck before starting.

```bash
# 1. Configure
cp .env.example .env   # fill in LLM / web-search API keys

# 2. Start both services
docker compose up --build

# 3. One-off CLI command
docker compose run --rm researcher \
  python -m researcher ask "What is photosynthesis?"

# 4. Offline demo (no API keys needed)
docker compose run --rm researcher python scripts/demo.py --offline

# 5. Run tests inside the container
docker compose run --rm researcher pytest --cov=src -v

# 6. Teardown (keep data)
docker compose down

# 7. Teardown and wipe the database volume
docker compose down -v
```

The Compose file sets `DATABASE_URL=postgresql+asyncpg://researcher:researcher@db:5432/researcher`
automatically.  The application auto-detects the URL prefix and switches from
the SQLite backend to the asyncpg/PostgreSQL backend — no code change needed.

### Storage backends

| `DATABASE_URL` prefix | Backend | When to use |
|---|---|---|
| `sqlite+aiosqlite://` | SQLite + aiosqlite | Local dev, single container |
| `postgresql+asyncpg://` | PostgreSQL + asyncpg | Docker Compose, production |

Switch by changing `DATABASE_URL` in `.env`.  Both use the same schema and
`BaseRepository` interface; business logic is unaffected.

---

## Testing

```bash
# Full suite with coverage
pytest --cov=src --cov-report=term-missing

# Provided smoke tests only
pytest tests/test_ai_smoke.py -v

# Run without network (all tests are offline)
pytest -v
```

**Coverage: 86% · 81 passed · 0 failed** — all tests fully offline (AI module
mocked, HTTP layer mocked, SQLite in-memory via `tmp_path`).

```
Name                              Stmts   Miss  Cover
-----------------------------------------------------
src/config.py                        35      0   100%
src/models.py                        60      1    98%
src/services/ai_service.py          133     23    83%
src/services/cache.py               100     12    88%
src/concurrency/pipeline.py          18      0   100%
src/concurrency/orchestrator.py     107     10    91%
src/core/researcher.py               56     11    80%
src/storage/repository.py           111     35    68%
src/cli.py                           66      6    91%
-----------------------------------------------------
TOTAL                               720    103    86%
```

---

## Sequential vs Concurrent Benchmark

```bash
# Reproduce
python scripts/bench.py --n 5 --offline --delay 0.10
```

| Mode | Time (s) | Speedup |
|---|---|---|
| Sequential | 1.505 | 1.0× |
| Concurrent | 0.502 | **3.0×** |

N=5 questions · sources=wiki+arxiv+web · `MAX_CONCURRENT=5` · offline mode
with 0.10 s simulated latency per source call.

**Why 3×:** each question fetches three sources.  Sequential waits for wiki,
then arXiv, then web — three round-trips.  Concurrent runs all three with
`asyncio.gather`, so the question resolves in one round-trip (the slowest of
the three).  `asyncio.Semaphore(MAX_CONCURRENT)` bounds simultaneous tasks so
free-tier providers are not flooded.

In live mode the per-source RTT is roughly 200 ms (Wikipedia), 400 ms (arXiv),
300 ms (web).  Sequential ≈ 900 ms/question; concurrent ≈ 400 ms/question.
See `artefacts/bench_2026-05-23.txt` for raw timing tables across multiple
simulated latency values.

---

## Architecture

```
+----------+   +------------------+
|   CLI    |   |  Streamlit UI    |
+----+-----+   +--------+---------+
     |                  |
     v                  v
+----------------------------------+
|        ResearchEngine            |  src/core/researcher.py
|  (business logic + orchestration)|
+-------+----------+---------------+
        |          |
        v          v
+-------+----+  +--+------------+
| Orchestrator|  | AIService    |  src/concurrency/orchestrator.py
| asyncio.    |  | (retries,    |  src/services/ai_service.py
| gather +    |  |  timeouts,   |
| semaphore   |  |  logging)    |
+-------+----+  +--+------------+
        |          |
        v          v
+-------+----------+-------+  +--------------+
|  provided ai/ package     |  | CacheBackend |
|  fetch_wikipedia()        |  | InMemory /   |
|  fetch_arxiv()            |  | Filesystem   |
|  fetch_web()              |  +--------------+
|  synthesize()             |
+---------------------------+
        |
        v
+---------------------------+
|  BaseRepository (ABC)     |  src/storage/repository.py
|  ├── SQLiteRepository     |  ← default (sqlite+aiosqlite)
|  └── PostgreSQLRepository |  ← production (postgresql+asyncpg)
+---------------------------+
```

---

## Environment Variables

| Variable | Required? | Default | Description |
|---|---|---|---|
| `LLM_PROVIDER` | yes | `anthropic` | `anthropic` \| `openai` \| `gemini` |
| `LLM_MODEL` | yes | `claude-sonnet-4-6` | Provider model ID |
| `ANTHROPIC_API_KEY` | if anthropic | — | Anthropic key |
| `OPENAI_API_KEY` | if openai | — | OpenAI key |
| `GOOGLE_API_KEY` | if gemini | — | Google key |
| `WEB_SEARCH_PROVIDER` | no | `tavily` | `tavily` \| `serper` \| `duckduckgo` |
| `TAVILY_API_KEY` | if tavily | — | Tavily web-search key |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `MAX_CONCURRENT` | no | `5` | Semaphore bound for parallel fetches |
| `CACHE_TTL_SECONDS` | no | `3600` | Cache TTL in seconds; 0 = never expire |
| `CACHE_DIR` | no | `./.cache` | Filesystem cache directory |
| `SOURCE_RATE_LIMIT_SECONDS` | no | `0.2` | Minimum delay between live calls per source |
| `WIKIPEDIA_TIMEOUT` | no | `10.0` | Per-request timeout for Wikipedia |
| `ARXIV_TIMEOUT` | no | `30.0` | Per-request timeout for arXiv |
| `ARXIV_RATE_LIMIT_SECONDS` | no | `3.0` | Minimum gap between arXiv API calls |
| `WEB_TIMEOUT` | no | `10.0` | Per-request timeout for web search |
| `DATABASE_URL` | no | `sqlite+aiosqlite:///./researcher.db` | Storage backend (SQLite or PostgreSQL) |

Full list and PostgreSQL example in `.env.example`. **Do not commit a real `.env`.**

---

## Project Layout

```
.
├── ai/                    # PROVIDED — do not modify
├── src/
│   ├── config.py          # pydantic-settings, env-driven
│   ├── models.py          # SE-layer Pydantic models
│   ├── services/
│   │   ├── ai_service.py  # retry + timeout + logging wrapper
│   │   └── cache.py       # InMemoryCache + FilesystemCache (ABC)
│   ├── core/
│   │   └── researcher.py  # ResearchEngine business logic
│   ├── concurrency/
│   │   ├── pipeline.py    # generic asyncio.gather + semaphore
│   │   └── orchestrator.py# per-source async fetch with degradation
│   ├── storage/
│   │   └── repository.py  # BaseRepository ABC; SQLite + PostgreSQL backends
│   └── cli.py             # Click CLI (ask, history)
├── tests/
│   ├── conftest.py        # FakeLLM, FakeAIService, fixtures
│   ├── test_ai_smoke.py   # PROVIDED — do not delete
│   ├── test_service.py
│   ├── test_concurrency.py
│   ├── test_storage.py    # cache + SQLite + factory tests
│   ├── test_cli.py
│   ├── test_researcher.py
│   ├── test_config.py
│   └── test_search_query.py
├── scripts/
│   ├── demo.py            # end-to-end scripted demo (5 questions)
│   └── bench.py           # sequential vs concurrent benchmark
├── data/
│   └── research_questions.json
├── artefacts/
│   ├── demo_2026-05-23.txt         # full offline demo run (5 questions)
│   ├── bench_2026-05-23.txt        # benchmark timing tables
│   └── test_coverage_2026-05-23.txt# pytest --cov full output
├── docs/
│   └── architecture.md
├── report/
│   ├── report.tex
│   └── report.pdf
├── app.py                 # Streamlit web UI (bonus)
├── Dockerfile             # multi-stage (+1 bonus)
├── docker-compose.yml     # PostgreSQL + app services
├── .github/
│   └── workflows/ci.yml   # lint + type-check + test + docker build (+2 bonus)
├── requirements.txt
├── .env.example
├── pytest.ini
└── README.md
```

---

## Limitations

- `FilesystemCache` uses non-atomic writes; a crash mid-write may corrupt a
  cache entry (handled gracefully by `json.JSONDecodeError` catch).
- Tavily is the default web provider and requires `TAVILY_API_KEY`; DuckDuckGo
  is available with no key but is less reliable under burst traffic.
- The SQLite backend is single-writer; horizontal scaling requires PostgreSQL
  (set via `DATABASE_URL`).
- The rate limiter enforces a minimum delay per source rather than a full
  provider-specific token-bucket quota.

See `report/report.pdf` §7 for a full discussion.

---

## Tools & Acknowledgements

AI assistant tools were used for review and improvement suggestions. Every
accepted change was tested locally. See `CONTRIBUTION_STATEMENT.md` for
per-member attribution.
