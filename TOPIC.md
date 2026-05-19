# Topic 4 — Async Research Assistant

> **What you receive:** a working AI module (async source fetchers, pluggable web search, LLM synthesizer with bracketed citations), example research questions, an end-to-end demo, and smoke tests.
> **What you build:** the full software-engineering layer around it (concurrency orchestration, caching, CLI, retries, logging, validation, tests, Docker, README, report).

---

## The problem

The user asks a research question. The system queries Wikipedia, arXiv, and a web-search API **in parallel**, retrieves relevant excerpts, then synthesises a single answer with inline citations.

## What the AI does

1. **Async source fetchers** — three coroutines, all returning `list[Source]`:
   - `fetch_wikipedia(query)` — Wikipedia REST API, no key needed.
   - `fetch_arxiv(query)` — arXiv public Atom API, no key needed.
   - `fetch_web(query)` — pluggable web search (Tavily / Serper / DuckDuckGo).
   Each accepts an optional `client: httpx.AsyncClient` so the SE layer can share a single connection pool across calls.
2. **Web search abstraction** — `WebSearchProvider` ABC with three concrete adapters. Pick one via `WEB_SEARCH_PROVIDER` env var.
3. **Synthesizer** — `synthesize(question, sources)` prompts the LLM to write a 3–6 sentence answer with inline `[N]` citations referring to the indexed sources. Out-of-range/hallucinated citation numbers are dropped automatically; only the indices the answer actually used end up in `AnswerWithCitations.citations`.

The LLM is provider-agnostic (Anthropic / OpenAI / Gemini), selected via env vars:

```bash
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=...

WEB_SEARCH_PROVIDER=tavily    # tavily | serper | duckduckgo
TAVILY_API_KEY=...            # or SERPER_API_KEY, or none for ddg
```

DuckDuckGo requires no key — useful for free demos. Tavily and Serper have generous free tiers.

## What you build (the SE layer)

| Component | Required | Notes |
|---|---|---|
| `config.py` | yes | Read env, expose typed settings. |
| Concurrent orchestration | **yes** | All three sources queried via `asyncio.gather` with **per-source timeouts** and **graceful degradation** (if arXiv fails, the answer is still produced from the other two with a note in the citations). |
| Caching | yes | Keyed by `(source, query)` with a configurable TTL (PostgreSQL, filesystem JSON, or in-memory). `--no-cache` flag bypasses. |
| CLI | yes | `python -m researcher ask "your question"` prints the synthesized answer + references; `--sources wiki,arxiv` restricts to a subset. |
| Citation tracking | yes | The provided `synthesize` already returns `AnswerWithCitations` — your CLI must render numeric refs cleanly. |
| Retries | yes | Exponential backoff on every `ai.*` call and every HTTP fetch. |
| Validation | yes | Reject empty/oversized questions; sanitise output. |
| Logging | yes | `logging` module, env-driven level. |
| Tests | yes | ≥60% coverage, all offline (mock async HTTP via `respx` or `pytest-httpx`). |
| Dockerfile | yes | Builds and runs end-to-end. |
| README | yes | Setup, env, run, test, parallel-vs-sequential timings. |

## How to run what we shipped

```bash
# (1) Install the AI-layer dependencies:
pip install httpx pydantic pytest-asyncio

# Optional, only needed if you actually call the providers:
pip install anthropic openai google-genai
pip install duckduckgo-search        # only if WEB_SEARCH_PROVIDER=duckduckgo

# (2) Try the offline demo (no API keys, no network):
python demo_ai.py --offline
python demo_ai.py --offline --limit 5

# (3) Run the smoke tests (offline):
pytest tests/test_ai_smoke.py -v
```

Sample output of `python demo_ai.py --offline`:

```
Researching: What is photosynthesis and what are its main stages?

  retrieved 3 sources (1 wiki, 1 arxiv, 1 web)

Q: What is photosynthesis and what are its main stages?

A: Based on the available sources, here is a synthesized answer that draws
   from multiple references [1], [2], [3]. ...

References:
  [1] (wikipedia) Photosynthesis
      https://en.wikipedia.org/wiki/Photosynthesis
  [2] (arxiv) Light-Dependent Reactions of Photosynthesis
      https://arxiv.org/abs/1706.03762
  [3] (web) How Plants Make Food
      https://example.com/plants
```

## The contract (do not break)

- **Do not** edit any file under `ai/`. If you find a bug, file an issue with the instructor.
- **Do not** delete or weaken `tests/test_ai_smoke.py`. These tests are run during grading; they must pass on your final repo.
- **Do not** call provider SDKs or source APIs directly from your business logic. Always go through `ai.fetch_wikipedia`, `ai.fetch_arxiv`, `ai.fetch_web`, and `ai.synthesize`.

## Recommended folder layout for your project

```
your-project/
├── ai/                        # COPIED FROM HERE, unchanged
├── src/
│   ├── config.py
│   ├── models.py              # YOUR pydantic models: ResearchSession, ...
│   ├── services/
│   │   ├── ai_service.py      # retries, logging around ai.*
│   │   └── cache.py           # TTL-aware (source, query) cache
│   ├── core/
│   │   └── researcher.py      # business logic
│   ├── concurrency/
│   │   └── orchestrator.py    # asyncio.gather with timeouts + degradation
│   ├── storage/
│   │   └── cache_store.py     # PostgreSQL, filesystem JSON, or in-memory
│   └── cli.py                 # `ask` command
├── tests/                     # YOUR tests + the provided smoke tests
├── data/                      # COPIED FROM HERE
├── Dockerfile
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Sample data

`data/research_questions.json` contains 5 example questions of varying difficulty, each tagged with the sources that should plausibly help. Use them for end-to-end smoke runs in your CI and to drive your sequential-vs-parallel benchmark.

## Tips for the SE layer

- **Share one `httpx.AsyncClient` across all three fetchers in a request.** All three accept a `client` kwarg. Connection reuse roughly doubles throughput on the small queries this app produces.
- **Wrap `asyncio.gather` with `return_exceptions=True`** so one failed source doesn't kill the whole research call. The demo demonstrates the pattern.
- **Use `asyncio.timeout()` per task**, not just on the gather. A slow Wikipedia response shouldn't block arXiv for the same window.
- **Cache by canonicalised query.** `"WHAT IS PHOTOSYNTHESIS?"` and `"what is photosynthesis"` should hit the same cache key.
- **Log the per-source timing.** Your report should show wall-clock timings for sequential (sum of three) vs. parallel (max of three) — this is the headline benchmark.

## Free-tier API options

| Source | Free? | Notes |
|---|---|---|
| Wikipedia | Yes, no key | Subject to rate limits — be polite. |
| arXiv | Yes, no key | Be polite, no more than ~1 req/sec. |
| Tavily | 1000 req/month | Best web-search quality for research. |
| Serper | 2500 req free | Google-quality results. |
| DuckDuckGo | Free, no key | Lower quality; use as fallback. |
| Anthropic / OpenAI / Gemini | Trial credit / cheap | LLM synthesis. |

A demo run of all 5 questions costs under $0.05 on Anthropic + Tavily.
