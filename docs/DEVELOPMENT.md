<!-- generated-by: gsd-doc-writer -->
# Development

This guide covers setting up BudgetingApp for local development, running the build/dev commands,
and the conventions used when contributing changes. For first-run instructions (prerequisites,
installation, quick start), see [README.md](../README.md). For environment variables and settings,
see [CONFIGURATION.md](CONFIGURATION.md). For the system's overall design, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Local setup

BudgetingApp has two independently runnable services — a FastAPI backend (`backend/`) and a Vite +
React frontend (`frontend/`) — plus a PostgreSQL 16 database, most easily started together via
Docker Compose.

**Backend (development mode):**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

By default the backend connects to a local SQLite database (`backend/budgetingapp.db`, created
automatically via `Base.metadata.create_all` on startup — see `backend/app/main.py`). To develop
against PostgreSQL instead, set `DATABASE_URL` (see [CONFIGURATION.md](CONFIGURATION.md)) or use
Docker Compose.

**Frontend (development mode):**

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to the backend (`frontend/vite.config.ts`), defaulting
to `http://localhost:8000` unless `VITE_API_URL` is set.

**Both services together (Docker Compose):**

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
docker compose up
```

This starts `db` (Postgres 16), `backend` (Uvicorn with `--reload`, bind-mounted to `backend/`),
and `frontend` (Vite dev server, bind-mounted to `frontend/`) — see `docker-compose.yml`. Both
mounted services hot-reload on source changes, so this is also a viable way to develop without
installing Python or Node locally.

There is no separate `.env.example` copy step for the backend beyond the root `.env` file — Pydantic
settings (`backend/app/config.py`) read directly from the project-root `.env` regardless of whether
the backend runs in a virtualenv or in Docker.

## Build commands

**Frontend (`frontend/package.json` scripts):**

| Command | Description |
|---------|--------------|
| `npm run dev` | Starts the Vite dev server with hot module reload (default port 5173). |
| `npm run build` | Type-checks the project (`tsc -b`) and produces a production build via `vite build`. |
| `npm run preview` | Serves the production build locally (`vite preview`) for a final check before deploy. |

**Backend:** there is no `package.json`-style script runner for the Python side. The commands used
directly are:

| Command | Description |
|---------|--------------|
| `uvicorn app.main:app --reload` | Runs the FastAPI app with auto-reload, from inside `backend/` with the virtualenv active. |
| `pip install -r requirements.txt` | Installs backend dependencies (FastAPI, SQLAlchemy, asyncpg, openai, etc. — see `backend/requirements.txt`). |

No `Makefile`, `tox.ini`, or `pyproject.toml`-based task runner is present in the repository.
Alembic is included in `backend/requirements.txt` and `backend/alembic/` is scaffolded, but
`backend/alembic/versions/` currently contains no revision files — schema changes are applied via
`Base.metadata.create_all` on startup rather than migrations (see [ARCHITECTURE.md](ARCHITECTURE.md)).

## Code style

No linting or formatting tool is currently configured in this repository:

- No ESLint config (`.eslintrc*`, `eslint.config.*`) or `eslint`/`prettier` entries exist in
  `frontend/package.json` `devDependencies`.
- No Ruff, Black, or Flake8 configuration (`pyproject.toml`, `ruff.toml`, `.flake8`) exists for the
  backend, and none of these tools are listed in `backend/requirements.txt`.
- No `.editorconfig` file is present.

TypeScript strict mode is enabled (`frontend/tsconfig.json` sets `"strict": true`), which is the
only automated code-quality check currently enforced, via `npm run build` (`tsc -b`).

<!-- VERIFY: Confirm whether ESLint/Prettier (frontend) and Ruff (backend) — both recommended in this project's stack guidance — are intended to be added in a future phase, since none are configured as of this writing. -->

## Branch conventions

The repository currently has a single branch, `main` (also the remote default branch,
`origin/main`). No branch naming convention is documented in the repository (no `CONTRIBUTING.md`
or `.github/PULL_REQUEST_TEMPLATE.md` exists to define one).

## PR process

No `.github/PULL_REQUEST_TEMPLATE.md`, `CONTRIBUTING.md`, or GitHub Actions CI workflow exists in
this repository, so there is no documented or automated PR process to follow. If opening a pull
request:

- Branch from `main` before making changes.
- Ensure `npm run build` (frontend type-check + build) succeeds, since it is the only automated
  verification currently available.
- Since no automated test suite exists yet, manually verify affected flows (CSV upload,
  categorization, currency conversion, budget summary) before submitting.
- Describe the change and its motivation in the PR description; no required checklist format is
  enforced.
