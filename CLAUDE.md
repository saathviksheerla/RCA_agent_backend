# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A "Cloud Incident Memory & RCA Engine": a FastAPI backend where you file an incident, the system recalls similar past incidents from a [Cognee](https://cognee.ai) memory layer, feeds them to an LLM to produce a root-cause analysis, then stores the incident back into memory so future recalls get smarter. Cognee stores/retrieves memory; the LLM does the reasoning — these responsibilities are kept strictly separate (see `app/action/`).

## Commands

```bash
uv sync                 # install deps into .venv
uv run main.py          # run locally on http://0.0.0.0:8000 (Swagger at /docs), --reload on
uv run modal serve modal_app.py    # run the Modal serverless deployment locally
uv run modal deploy modal_app.py   # deploy to Modal
```

There is **no test suite, linter, or formatter configured**. Manual testing is done via Swagger UI at `/docs` — the README has ready-to-paste example incident payloads.

Before running, copy `.env.example` → `.env` and fill in credentials. The app will not start without a reachable Postgres (`create_tables()` and Cognee `setup()` both run in the FastAPI lifespan hook in `app/app.py`).

## Architecture

### Request flow (the core loop)

`app/api.py` (routes) → `app/services/incident_service.py` (orchestration) → `app/action/*` (one external effect each).

On **create** (`POST /incidents`), order is deliberate and must not change:
```
recall_similar_incidents()  → pull history from Cognee
generate_rca()              → LLM reasons using that history as context
persist to Postgres         → app's own source of truth
remember_incident()         → store into Cognee AFTER recall
```
Recall happens **before** remember so Cognee can't return the incident you're currently creating as its own "similar" match.

On **resolve** (`POST /incidents/{id}/resolve`), it updates the row, calls `remember_incident()` again with the confirmed root cause + fix, then `cognee.improve()` to enrich the knowledge graph. This is the only path that makes the system "learn" — without a resolve, Cognee never finds out whether an RCA was correct.

### The `app/action/` layer — one function, one responsibility

- `remember_incident.py` — `cognee.remember()`. `incident_to_memory()` serializes an incident into a `Title:/Service:/Environment:/Severity:/Symptoms:/...` line-formatted string. **This format is a contract**: `_parse_recalled()` and `_score_recalled()` in the service parse recalled chunks by these exact line prefixes.
- `recall_similar_incidents.py` — `cognee.recall()` with `SearchType.CHUNKS, only_context=True, top_k=5`. Returns raw text chunks. On `NoDataError` returns `[]`; other errors become HTTP 500.
- `generate_rca.py` — the only LLM call, via `langchain_openai.ChatOpenAI`. Reads the model from `LLM_MODEL` (stripping the `openai/` litellm prefix) and forces `response_format=json_object`, then `json.loads()` the response.

### Two data stores, one Postgres instance

Everything lives in a single Neon Postgres database, but there are **two independent persistence layers** that don't know about each other:

1. **App data** — the `incidents` table (`app/models/incident.py`), managed by SQLAlchemy async engine in `app/database.py`. This is the app's source of truth returned by all endpoints.
2. **Cognee's memory** — its own pgvector (vectors) + graph tables, created and managed entirely by Cognee's `setup()`. The app never queries these directly; it only goes through `cognee.remember/recall/improve`.

### Configuration is env-driven, and split between the app and Cognee

- `app/database.py` reads only `DB_HOST/DB_PORT/DB_USERNAME/DB_PASSWORD/DB_NAME` and builds its own `postgresql+asyncpg://` engine with **hardcoded** pool settings.
- **Everything else** in `.env` (`LLM_*`, `EMBEDDING_*`, `VECTOR_DB_*`, `GRAPH_DATABASE_PROVIDER`, `*_POOL_ARGS`, `CACHING`, `AUTO_FEEDBACK`) is consumed by Cognee via its own env-var conventions, not by this app's code.
- `ENABLE_BACKEND_ACCESS_CONTROL=false` and `REQUIRE_AUTHENTICATION=false` must be set together — Cognee 1.2.2 turns on multi-user auth by default and this app has no login/session system.
- Neon's pooled (pgbouncer) endpoint requires `statement_cache_size: 0` in `DATABASE_CONNECT_ARGS`, or asyncpg prepared-statement errors occur.

## Known gotchas / inconsistencies to be aware of

- **Two separate LLM configs, both now OpenAI.** (1) The app's RCA reasoning in `generate_rca.py` uses `langchain_openai` directly, reading `LLM_MODEL`/`LLM_API_KEY`. (2) Cognee's own graph-extraction LLM is driven by `LLM_PROVIDER`/`LLM_MODEL`/`LLM_API_KEY` via litellm. They happen to share the same env vars, so one OpenAI key powers both — but they are different code paths.
- **`recalled_from` is not what the LLM returns.** `RCAResponse.recalled_from` (a `list[str]` the LLM is asked to fill) is discarded. The `recalled_from` stored on the incident is built independently from the recall chunks via `_parse_recalled()`. **Recall quality depends on the embedding model, not the LLM** — recall uses `SearchType.CHUNKS` (pure vector similarity), which never calls the LLM.
- **Embeddings drive recall; keep dimensions in sync.** Uses OpenAI `text-embedding-3-small` (1536). Changing `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS` requires resetting Cognee's vector store — run `scripts/reset_cognee.py` (calls `prune_system`), or old-dimension collections cause errors.
- **Dependency drift between run targets:** `pyproject.toml` installs `cognee[groq]` (vestigial — the app no longer uses Groq; pgvector/asyncpg are listed explicitly); `modal_app.py` installs `cognee[postgres]` + `psycopg2-binary` + `langchain-openai`. Keep both in sync when changing deps.
- **README is partially stale** — it still describes an "in-memory list, no postgres" MVP. The code has since moved to Neon Postgres + Cognee pgvector/graph. Trust the code over the README on storage.
- CORS in `app/app.py` is pinned to specific frontend origins (Vercel + localhost:3000/3001).
