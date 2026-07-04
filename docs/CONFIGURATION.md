<!-- generated-by: gsd-doc-writer -->
# Configuration

BudgetingApp is configured primarily through environment variables loaded from a `.env` file at the
project root (backend) and via `docker-compose.yml` service environments. There is no separate YAML/JSON
config file — backend settings are defined and validated in `backend/app/config.py` using
`pydantic-settings`.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|--------------|
| `DATABASE_URL` | Optional | `sqlite+aiosqlite:///./budgetingapp.db` | SQLAlchemy async database URL. In Docker Compose this is overridden to `postgresql+asyncpg://budget:budget_dev@db:5432/budgetingapp` to point at the `db` Postgres service. |
| `OPENAI_API_KEY` | Optional (required for AI categorization) | `""` (empty) | OpenAI API key used by `backend/app/services/categorizer.py` to categorize uploaded transactions via the `gpt-4o-mini` model. If unset, the app logs a warning and marks all imported transactions as `Uncategorized` instead of failing. |
| `BASE_CURRENCY` | Optional | `ILS` | Target currency defined in `Settings.base_currency` (`backend/app/config.py`) for currency conversion. <!-- VERIFY: backend/app/routers/upload.py currently hardcodes `base_currency = "ILS"` locally and does not read this setting, so changing `BASE_CURRENCY` has no effect on the upload flow as of this writing --> |
| `VITE_API_URL` | Optional | `http://localhost:8000` | Backend URL used by the Vite dev server proxy (`frontend/vite.config.ts`) to forward `/api` requests. In `docker-compose.yml` this is set to `http://backend:8000` so the frontend container can reach the backend container by service name. |

A `.env` file exists at the project root (referenced by `Settings.model_config["env_file"] = ".env"` in
`backend/app/config.py`) with a companion `.env.example` template. Both are excluded from version control
via `.gitignore`. <!-- VERIFY: exact variable names and example values inside .env.example — file contents were not accessible during doc generation --> Copy `.env.example` to `.env` and fill in real values (at minimum `OPENAI_API_KEY`) before running the app.

## Config file format

There is no dedicated config file (no `config.json`, `config.yaml`, or similar). All backend configuration
is defined in a single Pydantic settings class:

```python
# backend/app/config.py
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./budgetingapp.db"
    openai_api_key: str = ""
    base_currency: str = "ILS"

    model_config = {"env_file": ".env"}
```

Pydantic-settings maps each field to an environment variable of the same name (case-insensitive), so
`database_url` reads from `DATABASE_URL`, `openai_api_key` reads from `OPENAI_API_KEY`, and `base_currency`
reads from `BASE_CURRENCY`.

The frontend has no runtime config file either — its only externally configurable value is `VITE_API_URL`,
consumed directly in `frontend/vite.config.ts` via `process.env.VITE_API_URL`.

## Required vs optional settings

- None of the backend settings are strictly required at startup — every field in `Settings` has a default,
  so the app will boot without a `.env` file present.
- `OPENAI_API_KEY` is functionally required for AI categorization to work as intended. Without it,
  `categorize_transactions()` in `backend/app/services/categorizer.py` short-circuits and labels every
  transaction `Uncategorized` rather than raising an error.
- `DATABASE_URL` defaults to a local SQLite file (`budgetingapp.db`), which is sufficient for the bundled
  `sqlite+aiosqlite` driver but is overridden to Postgres whenever running via Docker Compose.
- `VITE_API_URL` only affects the frontend dev server proxy; if unset, it falls back to
  `http://localhost:8000`, which works for local (non-Docker) development where both services run on the
  host.

## Defaults

| Variable | Default | Set in |
|----------|---------|--------|
| `database_url` | `sqlite+aiosqlite:///./budgetingapp.db` | `backend/app/config.py` |
| `openai_api_key` | `""` | `backend/app/config.py` |
| `base_currency` | `ILS` | `backend/app/config.py` |
| `VITE_API_URL` | `http://localhost:8000` | `frontend/vite.config.ts` |

## Per-environment overrides

Two runtime environments exist today: local host development and Docker Compose.

**Local (host) development:**
- Backend reads `.env` at the project root via `model_config = {"env_file": ".env"}` — copy
  `.env.example` to `.env` and set values there.
- Frontend reads `VITE_API_URL` from the shell environment (or falls back to
  `http://localhost:8000`) when Vite starts.

**Docker Compose (`docker-compose.yml`):**
- The `backend` service explicitly sets `DATABASE_URL` to the containerized Postgres connection string
  (`postgresql+asyncpg://budget:budget_dev@db:5432/budgetingapp`) and passes through `OPENAI_API_KEY` from
  the host shell environment (`${OPENAI_API_KEY}`).
- The `db` service (image `postgres:16-alpine`) is configured with `POSTGRES_USER=budget`,
  `POSTGRES_PASSWORD=budget_dev`, `POSTGRES_DB=budgetingapp` directly in the compose file. <!-- VERIFY: these are development-only credentials defined inline in docker-compose.yml; confirm no separate production secrets management is expected before deploying this configuration anywhere beyond local development -->
- The `frontend` service sets `VITE_API_URL=http://backend:8000` so the Vite proxy can resolve the
  backend by its Docker Compose service name instead of `localhost`.

There are no separate `.env.development`, `.env.production`, or `.env.test` files in the repository, and no
`NODE_ENV`/environment-conditional branching was found in the backend or frontend configuration code.
