<!-- generated-by: gsd-doc-writer -->
# Getting Started

This guide gets BudgetingApp running locally, from a clean clone to your first CSV import.

## Prerequisites

Pick one of the two paths below and make sure you have the matching tools installed.

**Option A — Docker Compose (recommended):**
- Docker and Docker Compose (runs the frontend, backend, and Postgres together with one command)

**Option B — Run services individually:**
- Python `3.12+` (backend Dockerfile pins `python:3.12-slim`)
- Node.js `20+` (frontend Dockerfile pins `node:20-alpine`)
- PostgreSQL 16, if you want parity with Docker Compose — otherwise the backend falls back to a local
  SQLite file with no extra setup

**Both paths require:**
- An OpenAI API key. Without one, uploaded transactions are still imported but every transaction is
  labeled `Uncategorized` instead of being categorized by AI (see `backend/app/services/categorizer.py`).

## Installation Steps

1. Clone the repository and move into the project directory:
   ```bash
   git clone <repository-url>
   cd BudgetingApp
   ```

2. Create your local environment file and add your OpenAI API key:
   ```bash
   cp .env.example .env
   # then edit .env and set OPENAI_API_KEY=sk-...
   ```

3. Install dependencies for your chosen path:

   **Docker Compose** — no separate install step; `docker compose up` builds both images (see First Run below).

   **Individually:**
   ```bash
   # Backend
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cd ..

   # Frontend
   cd frontend
   npm install
   cd ..
   ```

## First Run

**Docker Compose:**
```bash
docker compose up
```

This builds and starts three services defined in `docker-compose.yml`:

| Service | Image / Build | Host port | Purpose |
|---------|----------------|-----------|---------|
| `db` | `postgres:16-alpine` | 5432 | PostgreSQL database (`budgetingapp`) |
| `backend` | `./backend` (Uvicorn + FastAPI, `--reload`) | 8000 | REST API |
| `frontend` | `./frontend` (Vite dev server) | 5173 | React SPA |

Once the logs settle, open:
- Frontend: http://localhost:5173
- Backend health check: http://localhost:8000/api/health

**Running services individually:**
```bash
# Terminal 1 — backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload

# Terminal 2 — frontend
cd frontend
npm run dev
```

By default the backend uses a local SQLite database (`backend/budgetingapp.db`) when run this way, since
`DATABASE_URL` defaults to `sqlite+aiosqlite:///./budgetingapp.db` in `backend/app/config.py`. Set
`DATABASE_URL` in `.env` if you want to point it at a Postgres instance instead (see
[docs/CONFIGURATION.md](./CONFIGURATION.md)).

Once both processes are running, open http://localhost:5173. On first upload, try the **Transactions**
page: click **Upload CSV** and select a Revolut (French or English) or Crédit Agricole export. The app
auto-detects the bank format, parses the rows, categorizes them via OpenAI (or marks them
`Uncategorized` if no API key is set), converts amounts to the base currency, and skips duplicates from
any previous import. Switch to the **Budget** page to see the monthly, category-grouped summary.

## Common Setup Issues

- **Every transaction imports as "Uncategorized".** `OPENAI_API_KEY` is missing or invalid in `.env` (or not
  passed through in `docker-compose.yml`, which forwards it from the host shell as `${OPENAI_API_KEY}`).
  Set a valid key and re-upload, or manually correct categories via
  `PATCH /api/transactions/{id}/category`.
- **CSV upload fails with a format error.** Only Revolut (French export), Revolut (English export), and
  Crédit Agricole CSVs are recognized by `detect_bank_format()`
  (`backend/app/parsers/detector.py`). Merged multi-currency Revolut exports are explicitly rejected —
  upload the per-currency account statement instead.
- **Frontend can't reach the backend (`/api/*` requests fail).** The Vite dev server proxies `/api` to
  the URL in `VITE_API_URL` (`frontend/vite.config.ts`), which defaults to `http://localhost:8000` and is
  set to `http://backend:8000` in `docker-compose.yml` for container-to-container networking. If you're
  mixing modes (e.g., frontend in Docker, backend on host), this value will be wrong — set it explicitly.
- **Port conflict on 5432, 8000, or 5173.** Another local Postgres instance, API server, or dev server is
  likely already bound to that port. Stop the conflicting process, or edit the host-side port mapping in
  `docker-compose.yml`.
- **`pip install` or `npm install` fails on an unsupported runtime version.** Confirm you're on Python
  3.12+ and Node.js 20+ (matching the versions pinned in `backend/Dockerfile` and `frontend/Dockerfile`)
  before installing dependencies for the individual-services path.

## Next Steps

- [docs/CONFIGURATION.md](./CONFIGURATION.md) — full list of environment variables, defaults, and
  per-environment overrides
- [docs/ARCHITECTURE.md](./ARCHITECTURE.md) — how the upload, categorization, currency conversion, and
  budget summary pipeline fits together
- [README.md](../README.md) — project overview, feature list, and API endpoint summary
