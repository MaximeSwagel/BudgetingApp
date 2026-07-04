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
│   - detector.py (bank format sniff)   - categorizer.py (OpenAI)        │
│   - revolut.py  (FR/EN CSV parsing)   - currency.py (Frankfurter API)  │
│   - ca.py       (Crédit Agricole)                                     │
│           │                                   │                        │
│           ▼                                   ▼                        │
│  Models (backend/app/models/) via SQLAlchemy async session            │
│   - Transaction, ImportBatch, Category, CategoryGroup,                │
│     BudgetTarget, UserSettings                                        │
└──────────────────────────┬────────────────────────────────────────────┘
                           │ asyncpg
                           ▼
                  ┌──────────────────┐
                  │  PostgreSQL 16   │
                  │  (docker: db)    │
                  └──────────────────┘

External services called by the backend:
  - OpenAI API (gpt-4o-mini)      → backend/app/services/categorizer.py
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
4. **Categorization** — The parsed transactions are batched (30 at a time) and sent to
   `categorize_transactions()` (`backend/app/services/categorizer.py`), which prompts OpenAI's `gpt-4o-mini`
   model to assign each transaction a `general_category` (category group) and `precise_category` (category)
   from the fixed `CATEGORY_HIERARCHY`. If no `OPENAI_API_KEY` is configured, or the OpenAI call fails, all
   transactions fall back to `"Uncategorized"`.
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
   month and category (via SQL `extract('month', ...)` + `GROUP BY`) and merges in any `BudgetTarget` values
   set via `POST /api/budget/targets`, producing the nested group → category → month structure the frontend
   renders as a spreadsheet-style table.

## Key Abstractions

| Abstraction | Location | Purpose |
|---|---|---|
| `Transaction` model | `backend/app/models/transaction.py` | Central record: original amount/currency, converted amount/rate/base currency, bank, category link, duplicate flag, expense flag. Uses `Numeric(12,2)` (not `float`) for all money columns. |
| `ImportBatch` model | `backend/app/models/transaction.py` | Groups transactions by upload event (filename, bank, timestamp, count) for traceability of each CSV import. |
| `Category` / `CategoryGroup` models | `backend/app/models/transaction.py` | Two-level budget hierarchy (e.g., group `"Home Expenses"` → category `"Rent"`) mirroring the user's Excel budget structure. Seeded on startup from `SEED_CATEGORIES` in `main.py`. |
| `BudgetTarget` model | `backend/app/models/transaction.py` | Per-category, per-month target amount, joined against actual spend in the budget summary endpoint. |
| Bank parser functions | `backend/app/parsers/revolut.py`, `backend/app/parsers/ca.py` | Each bank/format has its own pure function (`content: bytes -> list[dict]`) that normalizes rows into a common transaction-dict shape, isolating bank-specific CSV quirks (delimiters, encodings, multi-line wrapped labels for Crédit Agricole). |
| `detect_bank_format()` | `backend/app/parsers/detector.py` | Single dispatch point that inspects CSV header content to pick the correct parser, raising `ValueError` on unrecognized formats. |
| `categorize_transactions()` | `backend/app/services/categorizer.py` | Wraps the OpenAI chat completion call, including batching, prompt construction from the fixed category hierarchy, and defensive fallback to `"Uncategorized"` on any parsing/API failure. |
| `convert_amount()` / `get_exchange_rate()` | `backend/app/services/currency.py` | Currency conversion with in-memory rate caching and hardcoded fallback rates, isolating all Frankfurter API interaction. |
| `get_db()` | `backend/app/database.py` | FastAPI dependency yielding an `AsyncSession` per request, used via `Depends(get_db)` in every router. |
| `Settings` | `backend/app/config.py` | `pydantic-settings`-based config loader reading `DATABASE_URL`, `OPENAI_API_KEY`, `BASE_CURRENCY` from environment/`.env`. |

## Directory Structure Rationale

```
BudgetingApp/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app factory, CORS, startup seed logic, router registration
│   │   ├── config.py        # Settings (env-driven: DATABASE_URL, OPENAI_API_KEY, BASE_CURRENCY)
│   │   ├── database.py      # Async SQLAlchemy engine/session + get_db() dependency
│   │   ├── models/          # SQLAlchemy ORM models (Transaction, Category, BudgetTarget, etc.)
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
