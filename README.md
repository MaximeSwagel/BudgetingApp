<!-- generated-by: gsd-doc-writer -->
# BudgetingApp

A personal budgeting web app that ingests bank CSV exports from multiple banks (Revolut, Crédit Agricole) across multiple currencies (ILS, EUR, USD, DKK), auto-categorizes transactions using OpenAI, converts everything to a configurable base currency, and presents spending in a raw transaction view and a structured monthly budget view.

## Features

- **CSV upload with auto-detection** — supports Revolut French exports, Revolut English exports, and Crédit Agricole semicolon-delimited exports; the bank format is detected automatically from the CSV header
- **AI categorization** — uploaded transactions are automatically categorized into a two-level category hierarchy (group + category) using the OpenAI API
- **Currency conversion** — amounts in ILS, EUR, USD, and DKK are converted to a single configurable base currency (default `ILS`)
- **Duplicate detection** — re-uploading a CSV that overlaps a previous import skips transactions already recorded
- **Transactions view** — chronological list of all transactions with filtering by bank, currency, category, and date range, and inline category correction
- **Budget view** — monthly summary matching a spreadsheet-style layout, with category groups, per-category monthly totals, annual totals, and budget targets

## Tech Stack

- **Frontend:** React 19, TypeScript, Vite, React Router
- **Backend:** Python, FastAPI, SQLAlchemy (async), Alembic
- **Database:** PostgreSQL 16 (via Docker Compose); SQLite fallback for local backend-only development
- **AI:** OpenAI API for transaction categorization

## Prerequisites

- Docker and Docker Compose (recommended path, runs frontend, backend, and Postgres together)
- Or, for running services individually: Python 3.12+, Node.js 20+, PostgreSQL 16
- An OpenAI API key (required for transaction categorization)

## Installation

### Option A: Docker Compose (recommended)

1. Clone the repository and move into the project directory:
   ```bash
   git clone <repository-url>
   cd BudgetingApp
   ```
2. Create a `.env` file from the example and add your OpenAI API key:
   ```bash
   cp .env.example .env
   # then edit .env and set OPENAI_API_KEY=sk-...
   ```
3. Start all services:
   ```bash
   docker compose up
   ```

This starts three services:

| Service | Container port | Host port | Description |
|---------|-----------------|-----------|--------------|
| `db` | 5432 | 5432 | PostgreSQL 16 (`budgetingapp` database) |
| `backend` | 8000 | 8000 | FastAPI app (`uvicorn --reload`) |
| `frontend` | 5173 | 5173 | Vite dev server |

Once running:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Health check: http://localhost:8000/api/health

### Option B: Run services individually

**Backend:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

By default the backend uses a local SQLite database (`backend/budgetingapp.db`). To use PostgreSQL instead, set `DATABASE_URL` (see [Configuration](#configuration)).

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Configuration

Settings are read from environment variables (see `backend/app/config.py`):

| Variable | Default | Description |
|----------|---------|--------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./budgetingapp.db` | SQLAlchemy async database URL. Docker Compose overrides this to `postgresql+asyncpg://budget:budget_dev@db:5432/budgetingapp`. |
| `OPENAI_API_KEY` | `""` | Required for AI categorization of uploaded transactions. |
| `BASE_CURRENCY` | `ILS` | Currency all transaction amounts are converted to. |

The frontend reads `VITE_API_URL` to know where to reach the backend API (set to `http://backend:8000` in `docker-compose.yml` for container-to-container networking).

`.env.example` in the project root lists the variables to copy into your own `.env` file.

## Quick Start

1. Start the app with `docker compose up` (see Installation above).
2. Open http://localhost:5173 in a browser.
3. On the Transactions page, click **Upload CSV** and select a bank export (Revolut FR/EN, or Crédit Agricole).
4. The app auto-detects the bank format, parses transactions, categorizes them via OpenAI, converts amounts to the base currency, and skips any duplicates from a previous import.
5. Switch to the Budget page to see the monthly, category-grouped summary.

## API Overview

The backend exposes a REST API under `/api`:

| Method | Path | Description |
|--------|------|--------------|
| `POST` | `/api/upload` | Upload a bank CSV; detects format, parses, categorizes, converts currency, and imports transactions |
| `GET` | `/api/transactions` | List transactions with filters (`bank`, `currency`, `category_group`, `category`, `date_from`, `date_to`) and pagination |
| `PATCH` | `/api/transactions/{id}/category` | Manually correct a transaction's category |
| `GET` | `/api/categories` | List category groups and their categories |
| `POST` | `/api/categories/groups` | Create a new category group |
| `POST` | `/api/categories` | Create a new category within a group |
| `PUT` | `/api/categories/{id}` | Rename a category or move it to a different group |
| `GET` | `/api/budget/summary` | Monthly budget summary by category group/category for a given year, with annual totals |
| `POST` | `/api/budget/targets` | Set a budget target amount for a category/year/month |
| `GET` | `/api/health` | Health check |

Supported bank CSV formats (auto-detected from the header row): Revolut (French), Revolut (English), and Crédit Agricole. Merged multi-currency Revolut exports are not supported — upload per-currency account statements instead.

## Project Structure

```
BudgetingApp/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, category seeding, health check
│   │   ├── config.py        # Settings (database URL, OpenAI key, base currency)
│   │   ├── database.py      # Async SQLAlchemy engine/session
│   │   ├── models/          # Transaction, Category, CategoryGroup, BudgetTarget, ImportBatch
│   │   ├── parsers/         # Bank format detection + CSV parsers (Revolut FR/EN, Crédit Agricole)
│   │   ├── routers/         # upload, transactions, categories, budget endpoints
│   │   └── services/        # categorizer.py (OpenAI), currency.py (conversion)
│   ├── alembic/              # Database migrations
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/            # TransactionsPage, BudgetPage
│   │   ├── api/client.ts     # API client
│   │   └── main.tsx
│   └── Dockerfile
└── docker-compose.yml
```

## License

No LICENSE file is currently present in this repository. <!-- VERIFY: license type -->
