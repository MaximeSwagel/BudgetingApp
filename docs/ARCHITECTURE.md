<!-- generated-by: gsd-doc-writer -->
# Architecture

## System Overview

BudgetingApp is a personal finance tool that ingests bank CSV exports (Revolut in French/English formats,
Crédit Agricole), auto-categorizes each transaction using the OpenAI API, converts amounts across currencies
(EUR, USD, DKK, ILS) into a single base currency via the Frankfurter exchange rate API, and stores everything
in PostgreSQL for two presentation views: a raw chronological transaction list and a budget summary matching
the shape of the user's existing Excel budget (category groups × months).

The system follows a classic three-tier layered architecture:

- **Frontend** — a React 19 + Vite single-page app (`frontend/`) that renders the Transactions and Budget
  views and talks to the backend exclusively over `/api/*` HTTP calls (proxied by Vite's dev server to the
  backend container).
- **Backend** — a FastAPI application (`backend/app/`) organized into routers (HTTP layer), services
  (business logic: categorization, currency conversion), parsers (bank-specific CSV ingestion), and
  SQLAlchemy models (persistence).
- **Database** — PostgreSQL 16, accessed asynchronously via SQLAlchemy 2.0 + `asyncpg`. Table creation is
  currently handled by `Base.metadata.create_all` on FastAPI startup (`backend/app/main.py`) rather than by
  Alembic migrations — `backend/alembic/versions/` contains no revision files yet, so Alembic is scaffolded
  but not yet in active use.

All three components run as separate services under Docker Compose (`docker-compose.yml`) for local
development: `db` (Postgres), `backend` (Uvicorn + FastAPI, hot-reload), and `frontend` (Vite dev server).

## Component Diagram

```
┌─────────────────────────────┐
│  Browser (React SPA)        │
│  frontend/src/pages/        │
│   - TransactionsPage.tsx    │
│   - BudgetPage.tsx          │
└──────────────┬──────────────┘
               │ fetch() via frontend/src/api/client.ts
               │ (Vite dev-server proxies /api → backend)
               ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI app (backend/app/main.py)                           │
│                                                                │
│  Routers (backend/app/routers/)                               │
│   - upload.py        POST /api/upload                        │
│   - transactions.py  GET/PATCH /api/transactions              │
│   - categories.py    GET/POST/PUT /api/categories              │
│   - budget.py        GET/POST /api/budget/*                    │
│           │                                                    │
│           ▼                                                    │
│  Parsers (backend/app/parsers/)      Services (backend/app/services/) │
│   - detector.py (bank format sniff)   - classifier.py + agents/        │
│   - revolut.py  (FR/EN CSV parsing)   - currency.py (Frankfurter API)  │
│   - ca.py       (Crédit Agricole)                                     │
│           │                                   │                        │
│           ▼                                   ▼                        │
│  Models (backend/app/models/) via SQLAlchemy async session            │
│   - Transaction, ImportBatch, Category, CategoryGroup,                │
│     CategoryGroupTarget, UserSettings                                 │
└──────────────────────────┬────────────────────────────────────────────┘
                           │ asyncpg
                           ▼
                  ┌──────────────────┐
                  │  PostgreSQL 16   │
                  │  (docker: db)    │
                  └──────────────────┘

External services called by the backend:
  - OpenAI / Anthropic / OpenRouter (Jev) → backend/app/services/agents/
  - Frankfurter API (frankfurter.dev) → backend/app/services/currency.py
```

## Data Flow

A typical CSV import request flows through the system as follows:

1. **Upload** — The user selects a CSV file in `TransactionsPage.tsx`, which calls `uploadCSV()`
   (`frontend/src/api/client.ts`), POSTing multipart form data to `/api/upload`.
2. **Format detection** — `upload_csv()` in `backend/app/routers/upload.py` reads the file bytes and calls
   `detect_bank_format()` (`backend/app/parsers/detector.py`), which sniffs the first CSV line for
   bank-specific markers (`Libellé`/`Débit` for Crédit Agricole, `Date de début`/`Montant` for Revolut French
   export, `Started Date`/`Completed Date` for Revolut English export). Merged multi-currency Revolut exports
   are explicitly rejected with an error message asking for per-currency statements.
3. **Parsing** — The matched parser (`parse_revolut_fr`, `parse_revolut_en`, or `parse_credit_agricole` in
   `backend/app/parsers/`) decodes the file using `charset-normalizer` (handling encoding differences between
   banks) and returns a list of transaction dicts (`date`, `description`, `original_amount`,
   `original_currency`, `bank`, `is_expense`).
4. **Categorization** — The parsed transactions are passed to `categorize_transactions()`
   (`backend/app/services/classifier.py`), which hands them to the agent selected by the persisted
   `ai_provider` and gets back a `general_category` (category group) and `precise_category` (category) per
   transaction. The hierarchy is loaded from the `category_groups`/`categories` tables on every call by
   `load_category_hierarchy()` (`backend/app/services/taxonomy.py`), so Budget-page additions and renames apply
   on the next upload. If the active provider's key is not configured, or its
   calls fail, the affected transactions fall back to `"Uncategorized"`. See "Categorization agents" below.
5. **Currency conversion** — For each transaction not already in the base currency (`"ILS"`, hardcoded in
   `upload.py`), `convert_amount()` (`backend/app/services/currency.py`) calls the Frankfurter API
   (`https://api.frankfurter.dev/v1/...`) to fetch a historical exchange rate for the transaction date. Since
   Frankfurter does not natively support ILS, rate lookups routed through ILS are computed via a USD
   cross-rate (`from_currency → USD`, `to_currency → USD`, then divided). If the API call fails, a table of
   hardcoded fallback rates is used, and in-memory results are cached per `(from, to, date)` key for the
   life of the process.
6. **Deduplication and persistence** — Each transaction is checked against existing rows using a composite
   uniqueness match (`date`, `original_amount`, `original_currency`, `bank`, `description` — also enforced at
   the database level via `uq_transaction_dedup`). Non-duplicate transactions are inserted, associated with
   an `ImportBatch` row that records the source filename and count. The endpoint returns a summary
   (`imported`, `duplicates_skipped`, `batch_id`).
7. **Read paths** — `TransactionsPage.tsx` calls `GET /api/transactions` (with optional bank/currency/date/
   category filters and pagination) to render the chronological list, and can `PATCH
   /api/transactions/{id}/category` to manually recategorize a row. `BudgetPage.tsx` calls
   `GET /api/budget/summary?year=` (`backend/app/routers/budget.py`), which aggregates `converted_amount` by
   month and category (via SQL `extract('month', ...)` + `GROUP BY`) and merges in each primary category's
   current target (`CategoryGroupTarget`, set/cleared via `POST`/`DELETE
   /api/budget/group-targets`), producing the nested group → category → month structure the frontend
   renders as a spreadsheet-style table, plus a per-group `targets`/`current_target` pair used to colour
   the group-total row. For a group with no target yet, the same endpoint also computes
   `suggested_target` -- the average expense magnitude over the last 3 completed calendar months
   (`group_totals_for_month` called once per window month) -- which the frontend can apply with a single
   click via the same `POST /api/budget/group-targets` call.

## Categorization agents

`classifier.py` knows nothing about any specific model. It calls `get_active_agent()`, which looks up
`settings.ai_provider` in `AGENT_REGISTRY` (`agents/registry.py`) on every call, so a provider change on the
Settings page applies without a restart. An unknown value falls back to OpenAI.

- **Contract:** `CategorizationAgent.classify(transactions, categories) -> list[dict]` returns one
  `{general_category, precise_category, [confidence]}` per input, in order and same length. `categories` is an
  ordered `{group: [subcategory, ...]}` dict supplied by the classifier (display order); agents never touch the
  DB, and groups without subcategories are not offered. An empty hierarchy skips the agent
  (`skipped=no_categories`). The classifier pads,
  truncates and replaces malformed items, and turns an agent exception into all-`Uncategorized`.
- **LLM agents** (`OpenAiAgent`, `AnthropicAgent` in `agents/llm.py`): one batched prompt per 30 transactions.
- **Jev agent** (`agents/jev.py`): classifies each line on its own with OpenRouter's Jev decision model. Two
  sequential Decisions calls per line, first the budget group (plus an "other" option), then a sub-category
  offered only from that group; they cannot be one request because questions in a request cannot see each
  other's answers. A step whose confidence is below `JEV_CONFIDENCE_THRESHOLD` (default 0.6) leaves the line
  `Uncategorized`. Options are built per call from `categories`; past the 255-option cap (254 groups plus
  "other", or 255 sub-categories) they are truncated in display order with an `event=agent_taxonomy` warning.
  Lines run 8 at a time with a 20s timeout, retry on 429/5xx with capped backoff, and a failing
  line never fails the request. An auth error (401/402/403) skips the remaining lines.
- **Run stats:** an agent may set `last_run_stats` (a small dict of counts and scores) at the end of `classify`.
  The classifier sanitizes it (whitelisted keys, numeric values only) and appends it to the `llm_categorize` log
  line together with a per-call `run=<id>`.
- **Trace files:** when `AGENT_LOG_DIR` is set, `app/agent_trace.py` writes per-provider JSON-lines files with
  the full inputs and outputs of every agent call, joinable to stdout by `run_id`. Off by default; see
  [CONFIGURATION.md](CONFIGURATION.md#agent-trace-logs).
- **Seam, not built:** `JevAgent._unresolved()` is where an LLM fallback or a composite agent would plug in.
  Registry factories are zero-argument callables, so a composite's factory can call `build_agent()`. A composite
  agent receives `categories` and passes the same value to its inner agents.
- **Fallback telemetry:** when an agent answers with a valid group but an unknown sub-category, the row is still
  filed under the group's first category, and each upload or auto-categorize run logs one
  `event=category_fallback` warning with counts only.
- All Decisions wire-format knowledge (URL, model alias, request/response shape) is isolated in
  `services/openrouter_client.py`, because the endpoint is alpha.

## Key Abstractions

| Abstraction | Location | Purpose |
|---|---|---|
| `Transaction` model | `backend/app/models/transaction.py` | Central record: original amount/currency, converted amount/rate/base currency, bank, category link, duplicate flag, expense flag. Uses `Numeric(12,2)` (not `float`) for all money columns. |
| `ImportBatch` model | `backend/app/models/transaction.py` | Groups transactions by upload event (filename, bank, timestamp, count) for traceability of each CSV import. |
| `Category` / `CategoryGroup` models | `backend/app/models/transaction.py` | Two-level budget hierarchy (e.g., group `"Home Expenses"` → category `"Rent"`) mirroring the user's Excel budget structure. Seeded on startup from `SEED_CATEGORIES` in `main.py`; seeding only bootstraps the tables, which are the source of truth for categorization. |
| `load_category_hierarchy()` | `backend/app/services/taxonomy.py` | Reads the group/category tables into an ordered `{group: [category, ...]}` dict (by `display_order`, then id) on every categorize call; nothing is cached. |
| `CategoryGroupTarget` model | `backend/app/models/transaction.py` | A single current target amount per primary category (`CategoryGroup`), applying to every month shown, past and future, joined against actual spend in the budget summary endpoint. `amount` is nullable, meaning "cleared". `effective_month` records which month a row was written against and is retained as groundwork for possible future versioning, but is not consulted on read -- only the most recently written row per group is used. |
| Bank parser functions | `backend/app/parsers/revolut.py`, `backend/app/parsers/ca.py` | Each bank/format has its own pure function (`content: bytes -> list[dict]`) that normalizes rows into a common transaction-dict shape, isolating bank-specific CSV quirks (delimiters, encodings, multi-line wrapped labels for Crédit Agricole). |
| `detect_bank_format()` | `backend/app/parsers/detector.py` | Single dispatch point that inspects CSV header content to pick the correct parser, raising `ValueError` on unrecognized formats. |
| `categorize_transactions()` | `backend/app/services/classifier.py` | Agent-agnostic entry point: resolves the active agent, skips it when unconfigured, and guarantees one result per input so persistence never misaligns. |
| `CategorizationAgent` / `build_agent()` | `backend/app/services/agents/` | Pluggable agent contract and the registry that maps `ai_provider` to an agent. |
| `convert_amount()` / `get_exchange_rate()` | `backend/app/services/currency.py` | Currency conversion with in-memory rate caching and hardcoded fallback rates, isolating all Frankfurter API interaction. |
| `get_db()` | `backend/app/database.py` | FastAPI dependency yielding an `AsyncSession` per request, used via `Depends(get_db)` in every router. |
| `Settings` | `backend/app/config.py` | `pydantic-settings`-based config loader reading `DATABASE_URL`, the provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`), `BASE_CURRENCY` from environment/`.env`. |

## Directory Structure Rationale

```
BudgetingApp/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app factory, CORS, startup seed logic, router registration
│   │   ├── config.py        # Settings (env-driven: DATABASE_URL, OPENAI_API_KEY, BASE_CURRENCY)
│   │   ├── database.py      # Async SQLAlchemy engine/session + get_db() dependency
│   │   ├── models/          # SQLAlchemy ORM models (Transaction, Category, CategoryGroupTarget, etc.)
│   │   ├── parsers/         # Bank-specific CSV format detection and parsing (pure functions)
│   │   ├── routers/         # FastAPI route handlers, one module per resource (upload/transactions/categories/budget)
│   │   └── services/        # Business logic that talks to external APIs (OpenAI, Frankfurter)
│   ├── alembic/              # Migration scaffolding (versions/ currently empty — schema is created via create_all)
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── main.tsx          # App shell, React Router routes (/ and /budget)
│   │   ├── api/client.ts     # Thin fetch wrappers for every backend endpoint
│   │   ├── pages/            # TransactionsPage.tsx (upload + filterable list), BudgetPage.tsx (summary grid)
│   │   ├── components/       # (currently empty — no shared components extracted yet)
│   │   └── types/            # (currently empty — types are defined inline in page files)
│   └── Dockerfile
├── docker-compose.yml         # Orchestrates db (Postgres 16), backend (Uvicorn), frontend (Vite) services
└── docs/                      # Generated project documentation
```

The backend is organized by responsibility layer (routers → services/parsers → models) rather than by
feature, which keeps bank-format quirks (`parsers/`) and external-API integration concerns
(`services/`) isolated from HTTP routing and persistence. The frontend is currently a two-page app with
no shared component library extracted yet (`components/` and `types/` are placeholders); page-level
components (`TransactionsPage.tsx`, `BudgetPage.tsx`) currently hold both data-fetching and rendering logic
directly, using local `useState`/`useEffect` rather than a server-state library.

<!-- VERIFY: Whether a server-state library (e.g., TanStack Query) or component library (e.g., shadcn/ui) will be adopted in a future phase — the current implementation uses plain fetch calls and hand-rolled state management in frontend/src/pages/. -->
