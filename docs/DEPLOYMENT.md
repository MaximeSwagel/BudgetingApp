<!-- generated-by: gsd-doc-writer -->
# Deployment

BudgetingApp currently has no production deployment target configured. The only orchestration
that exists in the repository is `docker-compose.yml`, which is built for **local development**
(hot-reload backend, Vite dev server, and a Postgres container with development credentials
committed inline). There is no CI/CD pipeline, hosting platform config, or monitoring integration
in the repository as of this writing.

## Deployment Targets

| Target | Config file | Status |
|--------|-------------|--------|
| Docker Compose (local dev) | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | The only deployment mechanism present in the repo |
| Production hosting (Vercel, Fly.io, Railway, etc.) | none found | Not configured — no `vercel.json`, `netlify.toml`, `fly.toml`, `railway.json`, `serverless.yml`, or Kubernetes manifests exist in the repository |

`docker-compose.yml` defines three services:

- **`db`** — `postgres:16-alpine`, with credentials (`budget` / `budget_dev`) and database name
  (`budgetingapp`) hardcoded directly in the compose file, port `5432` published to the host.
- **`backend`** — built from `backend/Dockerfile` (`python:3.12-slim`), started with
  `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` — the `--reload` flag and the bind-mounted
  `./backend:/app` volume mean this container is running in development mode, not a production
  build.
- **`frontend`** — built from `frontend/Dockerfile` (`node:20-alpine`), started with
  `npm run dev -- --host 0.0.0.0` — this runs the Vite **dev server** inside the container, not a
  static production build (`vite build` + a static file server). There is no production-oriented
  Dockerfile stage (e.g., a multi-stage build that runs `npm run build` and serves the output via
  Nginx or similar) in the repository.

<!-- VERIFY: No production Dockerfile, build stage, or hosting platform has been defined yet. Before deploying anywhere beyond a developer's own machine, both Dockerfiles and docker-compose.yml would need production-oriented equivalents (non-reload Uvicorn command, `vite build` + static serving, externalized Postgres credentials). -->

## Build Pipeline

No CI/CD pipeline detected. There is no `.github/workflows/` directory (or any other CI config
such as `.gitlab-ci.yml`, `.circleci/config.yml`) in the repository, so there is currently no
automated build, test, or deploy step triggered by pushes or pull requests.

To build the images manually today:

```bash
docker compose build
docker compose up
```

This rebuilds `backend` and `frontend` from their respective Dockerfiles and starts all three
services (see [README.md](../README.md#installation) for the full local setup flow).

## Environment Setup

Full details on every environment variable, its default, and whether it is required are documented
in [CONFIGURATION.md](./CONFIGURATION.md). In summary, for any deployment beyond local Docker
Compose you would need to supply:

- `OPENAI_API_KEY` — required for AI categorization to function (without it, all transactions are
  labeled `Uncategorized` rather than the app failing to start).
- `DATABASE_URL` — must point at a reachable PostgreSQL instance (the SQLite default,
  `sqlite+aiosqlite:///./budgetingapp.db`, is not durable across container restarts and is not
  suitable for a deployed environment).
- `BASE_CURRENCY` — optional, defaults to `ILS`. <!-- VERIFY: backend/app/routers/upload.py currently hardcodes the base currency to "ILS" locally rather than reading this setting; confirm this is resolved before relying on BASE_CURRENCY in a deployed environment -->
- `VITE_API_URL` — must be set to the publicly reachable backend URL for the frontend build/dev
  server to reach the API correctly.

<!-- VERIFY: Where production secrets (OPENAI_API_KEY, database credentials) would be stored and injected — no secret manager, platform environment configuration, or `.env.production` file exists in the repository to verify this against. -->

## Rollback Procedure

No rollback procedure is documented or automated in the repository, since no CI/CD pipeline or
hosting platform is configured. Until one exists, the general approach for local Docker Compose is:

1. Identify the last known-good commit: `git log --oneline`.
2. Check out or reset to that commit (or the corresponding tagged Docker image, once image tagging
   exists).
3. Rebuild and restart: `docker compose build && docker compose up`.
4. If the Postgres schema changed, note that the current backend creates tables via
   `Base.metadata.create_all` on startup rather than via reversible Alembic migrations
   (`backend/alembic/versions/` contains no revision files yet — see
   [ARCHITECTURE.md](./ARCHITECTURE.md)), so schema rollback is not currently automated and would
   require manual intervention or a restored database volume/backup.

<!-- VERIFY: No backup/restore strategy for the `pgdata` Docker volume exists in the repository — confirm whether the local Postgres volume is backed up anywhere before relying on it for anything beyond disposable local development data. -->

## Monitoring

No monitoring, logging, or error-tracking integration is configured. No monitoring-related
dependencies (e.g., `@sentry/*`, `dd-trace`, `newrelic`, `@opentelemetry/*`) appear in
`backend/requirements.txt` or `frontend/package.json`, and no monitoring config files
(`sentry.config.*`, `datadog.config.*`) exist in the repository. The only observability endpoint
present is the health check exposed by the backend at `GET /api/health` (see
[README.md](../README.md#api-overview)).

<!-- VERIFY: Whether any external monitoring/alerting will be added before a production deployment — none is present today. -->
