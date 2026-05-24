# Contribution Statement

**Team:** shahinsafarli / Emil-Jafarov-06 / Jeyhunaa  
**Topic:** Topic 4 — Async Research Assistant  
**Repository:** https://github.com/shahinsafarli/async-research-assistant  
**Final tag:** `v1.0-final`  
**Submission date:** 2026-05-23

\---

## Commit and PR ownership summary

This statement follows the final repository commit/PR history. Each pull request is assigned to the member who owned the branch and authored the main implementation work. Reviewer assignments are listed separately from merge attribution.

|PR|Branch / work item|Main owner|Reviewer|Merge attribution|
|-|-|-|-|-|
|#1|`emil/config-and-models` — configuration and models|Emil Jafarov|Shahin Safarli|Merged by Emil Jafarov|
|#2|`jeyhuna/architecture-docs` — architecture docs and package entry point|Jeyhuna Sevdiyeva|Emil Jafarov|Merged by Jeyhuna Sevdiyeva|
|#3|`emil/ai-service-and-core` — AI service with retries and logging|Emil Jafarov|Shahin Safarli|Merged by Emil Jafarov|
|#4|`jeyhuna/storage-layer` — SQLite storage repository|Jeyhuna Sevdiyeva|Shahin Safarli|Merged by Jeyhuna Sevdiyeva|
|#5|`jeyhuna/cache-and-search-utils` — TTL cache, query utility, benchmark script|Jeyhuna Sevdiyeva|Emil Jafarov|Merged by Jeyhuna Sevdiyeva|
|#6|`emil/concurrency-and-core` — async orchestration and core researcher logic|Emil Jafarov|Jeyhuna Sevdiyeva|Merged by Emil Jafarov|
|#7|`shahin/cli-and-researcher` — CLI commands and researcher entry point|Shahin Safarli|Jeyhuna Sevdiyeva|Merged by Shahin Safarli|
|#8|`jeyhuna/add-demo-script` — demo script|Jeyhuna Sevdiyeva|Emil Jafarov|Merged by Jeyhuna Sevdiyeva|
|#9|`shahin/combined-testing-suite` — unified offline testing framework|Shahin Safarli|Jeyhuna Sevdiyeva|Merged by Shahin Safarli|
|#11|`emil/streamlit-and-docker` — Streamlit app and Docker setup|Emil Jafarov|Shahin Safarli|Merged by Emil Jafarov|
|#15|`shahin/postgresql-adaptation` — PostgreSQL adaptation and related file edits|Shahin Safarli|Emil Jafarov|Merged by Shahin Safarli|
|#16|`emil/report-and-readme` — final report and README|Emil Jafarov|Jeyhuna Sevdiyeva|Merged by Emil Jafarov|
|#17|`jeyhuna/presentation-and-contribution` — presentation files and contribution statement|Jeyhuna Sevdiyeva|Shahin Safarli|Merged by Jeyhuna Sevdiyeva|
|#18|`emil/readme-name-and-contribution-fix` — README name fix and contribution statement updates in MD and PDF formats|Emil Jafarov|Shahin Safarli|Merged by Emil Jafarov|
|#19|`shahin/artifacts-and-final-tag` — project artefacts and final tag addition|Shahin Safarli|Emil Jafarov|Merged by Shahin Safarli|

\---

## Member A — Shahin Safarli (`@shahinsafarli`)

**Owned (sole author of these files / PRs):**

* Project scaffolding: `.gitignore`, GitHub PR template, topic-4 template, provided `ai/` module placement, smoke tests, data files, and `.env.example`
* `src/cli/` — CLI commands including `ask` and `history`
* Researcher package entry point used by the CLI flow
* `tests/` — unified offline testing framework covering configuration, storage, service, researcher, concurrency, CLI, and utility modules
* PostgreSQL adaptation — adapted the codebase to support PostgreSQL storage and edited the related files accordingly
* PRs: #7, #9, #15, #19

**Reviewed:**

* PR #1 — reviewed Emil's `emil/config-and-models` branch
* PR #3 — reviewed Emil's AI service work
* PR #4 — reviewed Jeyhuna's SQLite storage layer work
* PR #11 — reviewed Emil's Streamlit and Docker work
* PR #17 — reviewed Jeyhuna's presentation and contribution statement work
* PR #18 — reviewed Emil's README name fix and contribution statement updates

**Co-owned (paired or substantially edited):**

* Repository initialization and branch strategy with all team members
* Storage backend integration after PostgreSQL support was added, while preserving Jeyhuna's original SQLite storage work

**Approximate share of commits:** 33%

\---

## Member B — Emil Jafarov (`@Emil-Jafarov-06`)

**Owned (sole author of these files / PRs):**

* `src/config.py` — initial configuration scaffold with typed environment variables
* Core model/config setup from PR #1
* `src/services/ai\\\\\\\_service.py` — AI service wrapper with retry logic and structured logging
* `src/concurrency/` — async orchestrator with per-source timeouts and graceful degradation
* Core researcher logic connected to the async orchestration flow
* `app/` — Streamlit application
* Docker setup — `Dockerfile`, `docker-compose.yml`, and related Docker configuration files
* `README.md` — project overview, setup instructions, usage examples, and environment configuration guide
* `docs/report.md` / `docs/report.pdf` — final project report covering architecture, design decisions, async patterns, testing, and evaluation
* PRs: #1, #3, #6, #11, #16, #18

**Reviewed:**

* PR #2 — reviewed Jeyhuna's architecture documentation and entry point work; this PR is still treated as merged by Jeyhuna herself
* PR #5 — reviewed Jeyhuna's cache, search utility, and benchmark work
* PR #8 — reviewed Jeyhuna's demo script work
* PR #15 — reviewed Shahin's PostgreSQL adaptation work
* PR #19 — reviewed Shahin's project artefacts and final tag addition

**Co-owned (paired or substantially edited):**

* No co-ownership or merge ownership is claimed.

**Approximate share of commits:** 33%

\---

## Member C — Jeyhuna Sevdiyeva (`@Jeyhunaa`)

**Owned (sole author of these files / PRs):**

* `docs/architecture.md` — architecture documentation
* `src/\\\\\\\_\\\\\\\_main\\\\\\\_\\\\\\\_.py` — package entry point
* `src/storage/` — SQLite storage repository with session persistence
* `src/services/cache\\\\\\\_service.py` — TTL cache service
* `src/utils/search\\\\\\\_query.py` — search query utility
* `scripts/bench.py` — benchmarking script
* `scripts/demo.py` — demo script for project demonstration
* `docs/presentation.pptx` — project presentation slides
* `docs/presentation.pdf` — exported PDF version of the project presentation
* `CONTRIBUTION\\\\\\\_STATEMENT.md` — contribution statement documenting individual contributions, PR ownership, and AI tool disclosure for the full team
* PRs: #2, #4, #5, #8, #17

**Reviewed:**

* PR #6 — reviewed Emil's concurrency and core researcher work
* PR #7 — reviewed Shahin's CLI/researcher work
* PR #9 — reviewed Shahin's combined testing suite
* PR #16 — reviewed Emil's final report and README work

**Co-owned (paired or substantially edited):**

* Storage layer integration with the CLI history command, coordinated with Shahin after the CLI and PostgreSQL-related work

**Approximate share of commits:** 33%

\---

## AI tool disclosure

We used AI coding assistants as support tools. Each item lists the module, the assistant, and what the team did with the output.

|Module / file|Assistant|What we did with it|
|-|-|-|
|`src/services/ai\\\_service.py`|Claude|Suggested retry/backoff structure; the team revised error handling and integrated the project-specific logging format.|
|`src/concurrency/orchestrator.py`|Claude|Drafted the initial async task structure; the team rewrote the per-source timeout logic and graceful degradation after integration testing.|
|`tests/`|Claude|Proposed test scaffolding; the team reviewed all cases, removed mocks that did not match actual interfaces, and added concurrency and CLI edge-case tests.|

We affirm that we can defend every line of code in this repository during the oral defense. "The AI wrote it" is not an answer we will use.

\---

## Signatures

By signing below, we affirm that:

* The contributions described above are accurate.
* The commit percentages reflect actual work, not artificially split commits.
* Every line of code in the repository can be defended by at least one team member.
* AI assistant usage has been disclosed as described above.

|Member|Signature|Date|
|-|-|-|
|Shahin Safarli|\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_|2026-05-23|
|Emil Jafarov|\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_|2026-05-23|
|Jeyhuna Sevdiyeva|\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_|2026-05-23|



