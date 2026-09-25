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
| `OPENAI_API_KEY` | Optional (needed when the active provider is OpenAI) | `""` (empty) | OpenAI API key used by the OpenAI agent (`backend/app/services/agents/llm.py`) to categorize transactions. If the active provider's key is unset, the app logs a warning and marks all imported transactions as `Uncategorized` instead of failing. |
| `ANTHROPIC_API_KEY` | Optional (needed when the active provider is Anthropic) | `""` (empty) | Anthropic API key used by the Anthropic agent (`backend/app/services/agents/llm.py`). |
| `OPENROUTER_API_KEY` | Optional (needed when the active provider is OpenRouter) | `""` (empty) | OpenRouter API key used by the Jev agent (`backend/app/services/agents/jev.py`). Env-only: it is never stored in the database or returned by the API. |
| `JEV_CONFIDENCE_THRESHOLD` | Optional | `0.6` | Minimum Jev confidence (per step: group, then sub-category) for a line to receive a category. Lines below it stay `Uncategorized`. |
| `AGENT_LOG_DIR` | Optional | `""` (empty = off) | Directory for per-provider agent trace files (`openrouter.log`, `openai.log`, `anthropic.log`). The files contain financial data, so leave it unset unless you control the host. See [Agent trace logs](#agent-trace-logs). |
| `BASE_CURRENCY` | Optional | `ILS` | Target currency defined in `Settings.base_currency` (`backend/app/config.py`) for currency conversion. <!-- VERIFY: backend/app/routers/upload.py currently hardcodes `base_currency = "ILS"` locally and does not read this setting, so changing `BASE_CURRENCY` has no effect on the upload flow as of this writing --> |
| `VITE_API_URL` | Optional | `http://localhost:8000` | Backend URL used by the Vite dev server proxy (`frontend/vite.config.ts`) to forward `/api` requests. In `docker-compose.yml` this is set to `http://backend:8000` so the frontend container can reach the backend container by service name. |

A `.env` file exists at the project root (referenced by `Settings.model_config["env_file"] = ".env"` in
`backend/app/config.py`) with a companion `.env.example` template. Both are excluded from version control
via `.gitignore`. <!-- VERIFY: exact variable names and example values inside .env.example — file contents were not accessible during doc generation --> Copy `.env.example` to `.env` and fill in real values (the key of the provider you use, e.g. `OPENAI_API_KEY`) before running the app.

## Config file format

There is no dedicated config file (no `config.json`, `config.yaml`, or similar). All backend configuration
is defined in a single Pydantic settings class:

```python
# backend/app/config.py
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./budgetingapp.db"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    jev_confidence_threshold: float = 0.6
    agent_log_dir: str = ""
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
- The API key of the active AI provider (`ai_provider`: `openai`, `anthropic` or `openrouter`, chosen on the
  Settings page) is functionally required for AI categorization. Without it,
  `categorize_transactions()` in `backend/app/services/classifier.py` short-circuits and labels every
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
| `anthropic_api_key` | `""` | `backend/app/config.py` |
| `openrouter_api_key` | `""` | `backend/app/config.py` |
| `jev_confidence_threshold` | `0.6` | `backend/app/config.py` |
| `agent_log_dir` | `""` (tracing off) | `backend/app/config.py` |
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
  (`postgresql+asyncpg://budget:budget_dev@db:5432/budgetingapp`) and passes through `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY` from the host shell environment (`${OPENROUTER_API_KEY}` etc.).
- The `db` service (image `postgres:16-alpine`) is configured with `POSTGRES_USER=budget`,
  `POSTGRES_PASSWORD=budget_dev`, `POSTGRES_DB=budgetingapp` directly in the compose file. <!-- VERIFY: these are development-only credentials defined inline in docker-compose.yml; confirm no separate production secrets management is expected before deploying this configuration anywhere beyond local development -->
- The `frontend` service sets `VITE_API_URL=http://backend:8000` so the Vite proxy can resolve the
  backend by its Docker Compose service name instead of `localhost`.

There are no separate `.env.development`, `.env.production`, or `.env.test` files in the repository, and no
`NODE_ENV`/environment-conditional branching was found in the backend or frontend configuration code.

## Agent trace logs

Set `AGENT_LOG_DIR` to write one JSON-lines trace file per categorization provider, next to the normal stdout
events: `openrouter.log` (Jev), `openai.log` and `anthropic.log`. Leave it unset or empty (the default) and
nothing is written anywhere. Prod keeps it off; the dev instance turns it on (see
[DEPLOYMENT.md](DEPLOYMENT.md#agent-trace-logs-on-the-dev-instance)).

**Privacy warning.** Unlike stdout, these files hold descriptions, amounts, currencies, banks, the exact LLM
prompts and the model outputs. Enable them only on a host you control, never in prod by default, and never commit
or share them. API keys and Authorization headers are never written. The directory is created `0700` and the
files are `0600`. `agent-logs/` is gitignored.

Each file rotates at 10 MB and keeps 5 backups (`openai.log.1` to `openai.log.5`). A trace problem (unwritable
directory, disk error) never fails an upload: the app emits one `event=agent_trace ok=false disabled=true
error=<ExceptionClass>` warning and stops tracing until the process restarts.

Every record carries `ts` (UTC ISO ms `Z`), `run_id`, `provider`, `model` and `stage`. `run_id` is one id per
categorize call (one CSV upload) and is also printed as `run=<id>` at the end of that call's
`event=llm_categorize` stdout line, so a console line joins to its trace records with
`jq 'select(.run_id=="<id>")'`.

| Stage | Written by | One per | Extra fields |
|-------|------------|---------|--------------|
| `group`, `category` | Jev | Decisions call | `line`, `input` (`state` sent + `options` offered), `output` (`choice`, `confidence`, `top` = top-3 `[key, prob]`, or null on error), `ms`, `queue_ms` (wait on the concurrency semaphore; 0 on `category`), `attempts`, `status` (`ok` or exception class), `status_code`, `cost`, `decision`, `threshold` |
| `line` | Jev | input transaction | `line`, `input.state`, `group`, `category`, `group_score`, `category_score` (null when not reached), `decision`, `threshold`, `queue_ms`, `total_ms`, `cost` (sum of both calls) |
| `batch` | OpenAI, Anthropic | batch of up to 30 | `batch` (`i/n`), `size`, `prompt_hash`, `input.prompt` (exact prompt), `output` (`results` parsed, `raw` text; null on error), `padded`, `ms`, `attempts` (null: SDK retries are internal), `status`, `status_code`, `cost` (null), `usage` (`input_tokens`, `output_tokens`, or null) |
| `run` | any | categorize call | `rows`, `uncategorized`, `stats`, `ms`, `status` (`ok`, `no_api_key` or exception class) |

`prompt_hash` is the first 12 hex of the sha256 of the prompt template with the category list, so it changes only
when the template or the categories change.

Jev `decision` values: `accepted` (line categorized), `other` (group step chose "other"), `group_low`
(group confidence under the threshold), `category_low` (sub-category confidence under it), `error`, `auth`
(401/402/403, remaining lines skipped). `group` and `category` records only use the values that can occur at
their step.

### Reason fields on the stdout line

`event=llm_categorize provider=<p> model=<m> rows=<n> uncategorized=<n> <agent fields> ms=<x> run=<id>`.
The agent fields are counts and scores only, never text:

- Jev: `accepted`, `group_other`, `group_low`, `category_low`, `errors`, `auth` (they sum to `rows`), then
  `group_score_min/p50/max` over every line that got a group answer and `cat_score_min/p50/max` over every
  sub-category answer.
- OpenAI / Anthropic: `batches`, `failed_batches`, `padded` (results the model omitted, filled `Uncategorized`).
