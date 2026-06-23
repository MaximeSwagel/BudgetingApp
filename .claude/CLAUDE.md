<!-- GSD:project-start source:PROJECT.md -->

## Project

**BudgetingApp**

A personal budgeting web app that ingests bank CSV exports from multiple banks (Revolut, Crédit Agricole) across multiple currencies (ILS, EUR, USD, DKK), auto-categorizes transactions using OpenAI, converts everything to a configurable base currency, and presents spending data in two views: raw chronological transactions and a structured budget view matching the user's existing Excel budget layout with monthly columns, category totals, and percentage breakdowns.

**Core Value:** See all spending across all bank accounts and currencies in one place, automatically categorized and mapped to a personal budget structure — replacing the manual Excel pipeline.

### Constraints

- **Stack**: React (frontend), Python + FastAPI (backend), PostgreSQL (database)
- **AI Provider**: OpenAI API for transaction categorization
- **Deployment**: Local development for MVP (Docker Compose)
- **Budget**: Personal project, minimize infrastructure costs

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| React | 19.x | Frontend UI framework | Industry standard SPA framework; vast ecosystem of compatible libraries; shadcn/ui and TanStack all target React 19 |
| Vite | 6.x | Frontend build tool & dev server | Sub-second HMR, native ESM, standard React scaffolding via `npm create vite@latest -- --template react-ts`; CRA is dead |
| TypeScript | 5.x | Frontend type safety | Catches bugs at compile time; required by shadcn/ui; TanStack Table/Query ship first-class TS types |
| Python | 3.12+ | Backend runtime | Latest stable with performance improvements; required by FastAPI/Pydantic; avoid 3.13+ unless needed |
| FastAPI | 0.138.0 | Backend REST framework | Async-native, auto-generated OpenAPI docs, Pydantic integration for request/response validation, file upload support |
| PostgreSQL | 16 | Relational database | NUMERIC type for precise money storage, JSONB for flexible metadata, robust indexing, Docker-friendly |
| Docker Compose | 2.x | Local development orchestration | Single `docker compose up` for API + DB + frontend; reproducible environments; standard for full-stack dev |

### Database & ORM

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| SQLAlchemy | 2.0.51 | ORM + query builder | Industry standard Python ORM; 2.0 style with native async support; type-safe query building; excellent PostgreSQL dialect |
| Alembic | 1.18.4 | Database migrations | Only serious migration tool for SQLAlchemy; auto-generates migrations from model changes; reversible upgrades |
| asyncpg | 0.31.0 | Async PostgreSQL driver | 5x faster than psycopg3 for async workloads; purpose-built for asyncio; binary protocol for speed |
| Pydantic | 2.13 | Data validation & settings | FastAPI's native validation layer; 5-50x faster than v1; `pydantic-settings` for env/config management |

### Frontend Libraries

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| shadcn/ui | latest (CLI) | UI component library | Not an npm dependency -- copies source into your project; built on Radix UI + Tailwind; fully customizable; includes Table, Dialog, Form, Select, etc. |
| Tailwind CSS | 4.3 | Utility-first CSS | Zero-config in v4; CSS-first configuration; no tailwind.config.js needed; shadcn/ui requires it |
| TanStack Table | 8.21.3 | Headless data table | Full control over table markup; sorting, filtering, pagination built-in; pairs with shadcn/ui Table component; handles thousands of rows |
| TanStack Query | 5.101.0 | Server state management | Automatic caching, refetching, loading/error states for API calls; eliminates hand-rolled fetch logic; devtools included |
| Recharts | 3.9.0 | Charts & data visualization | React-native composable chart components; BarChart, LineChart, PieChart for budget views; lightweight; large community |
| React Router | 7.18.0 | Client-side routing | Stable v7 with data loading; type-safe routes; v8 exists but requires React 19.2.7+ and Vite 7+ -- stick with v7 for now |

### Backend Libraries

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| openai | 2.43.0 | OpenAI API client | Official Python SDK; async support; structured output via response_format; type-safe request/response |
| charset-normalizer | 3.4.6 | CSV encoding detection | Detects encoding of uploaded bank CSVs (Latin-1, UTF-8-BOM, Windows-1252); MIT licensed; used by requests internally |
| python-multipart | 0.0.x | File upload parsing | Required by FastAPI for `UploadFile` endpoints; handles multipart form data |
| httpx | 0.28.x | HTTP client | Async HTTP client for Frankfurter currency API calls; used internally by openai SDK |
| uvicorn | 0.34.x | ASGI server | Production-grade async server for FastAPI; standard deployment choice |

### Currency Conversion

| Service | Type | Purpose | Why Recommended |
|---------|------|---------|-----------------|
| Frankfurter API | Free REST API | Exchange rate data | No API key required; no quotas; ECB reference rates; 84 central banks, 201 currencies; historical rates back to 1948; open source and self-hostable |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Ruff | Python linting + formatting | Replaces flake8, black, isort in one tool; 10-100x faster; configure in pyproject.toml |
| ESLint + Prettier | JS/TS linting + formatting | Standard frontend tooling; use eslint-config-prettier to avoid conflicts |
| pytest | Python testing | Standard test framework; use pytest-asyncio for async test support |
| Vitest | Frontend testing | Vite-native test runner; compatible with Jest API; fast |

## Installation

### Backend (Python)

# Core

# AI & HTTP

# CSV & encoding

# Dev dependencies

### Frontend (Node.js)

# Scaffold project

# Core

# Styling (Tailwind v4 auto-installs via shadcn init)

# Add shadcn components as needed

# Dev dependencies

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| SQLAlchemy 2.0 | Tortoise ORM | Never for this project; Tortoise has smaller ecosystem, fewer migration tools |
| asyncpg | psycopg 3 | If you need sync + async from same driver; psycopg3 is more Pythonic but slower for pure async |
| Recharts | Nivo, Victory | Nivo for more complex/interactive charts; Victory for fine-grained D3 control; Recharts is simplest for budget bar/line charts |
| TanStack Table | AG Grid | AG Grid for 100K+ rows or enterprise features (column grouping, pivoting); massive bundle; overkill for personal budgets |
| shadcn/ui | MUI, Ant Design | MUI if you want Material Design; Ant Design if you want opinionated Chinese-origin design system; both are heavier and less customizable |
| Frankfurter | ExchangeRate-API | If you need real-time (sub-daily) rates; Frankfurter updates daily which is sufficient for personal budgeting |
| charset-normalizer | chardet 7 | chardet 7 is faster but has disputed relicensing (LGPL->MIT via AI rewrite); charset-normalizer is clean MIT |
| React Router v7 | React Router v8 | v8 requires React 19.2.7+ and Vite 7+; use v8 when those versions stabilize in your stack |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| PostgreSQL `money` type | Locale-dependent, cannot store multiple currencies, deprecated in practice | `NUMERIC(12,2)` + separate `currency` column |
| Python `float` for money | IEEE 754 binary floating point causes rounding errors (0.1 + 0.2 != 0.3) | Python `Decimal` from strings; PostgreSQL `NUMERIC` |
| pandas for CSV parsing | 50MB+ dependency for reading simple CSVs; overkill for known bank formats | Python stdlib `csv.DictReader` with `charset-normalizer` for encoding |
| Create React App (CRA) | Officially deprecated; no maintenance since 2022; slow builds | Vite with React template |
| JavaScript (no types) | Financial app needs type safety for amounts, currencies, categories | TypeScript throughout |
| Redux / Zustand for server state | TanStack Query handles server state (fetching, caching, syncing) better | TanStack Query for server state; local `useState`/`useReducer` for UI state |
| Django / Flask | Django is batteries-included but synchronous by default; Flask lacks async and auto-docs | FastAPI for async-native + OpenAPI auto-docs |
| chardet (pre-7.0) | Slow, GPL-licensed, unmaintained | charset-normalizer |

## Stack Patterns by Variant

- Add `@tanstack/react-virtual` for row virtualization
- Keep TanStack Table for logic, add virtual scrolling for DOM performance
- Switch from Frankfurter to ExchangeRate-API (free tier: 1,500 req/month)
- Or self-host Frankfurter and feed it custom rate sources
- Use Batch API for 50% cost reduction (24h window acceptable for CSV imports)
- Use structured output (JSON schema) to minimize output tokens
- Consider GPT-4o-mini for classification (cheapest with good accuracy)
- Add `python-jose[cryptography]` + `passlib[bcrypt]` for JWT auth
- FastAPI has built-in OAuth2 + security dependency injection

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| FastAPI 0.138.0 | Pydantic 2.13, SQLAlchemy 2.0.51 | FastAPI requires Pydantic v2; deeply integrated |
| SQLAlchemy 2.0.51 | asyncpg 0.31.0, Alembic 1.18.4 | Use `create_async_engine` with asyncpg driver |
| shadcn/ui (latest) | React 19, Tailwind CSS 4.x | Full React 19 + Tailwind v4 support confirmed |
| TanStack Query 5.x | React 18+, React 19 | Works with both React 18 and 19 |
| TanStack Table 8.x | React 16.8+ through React 19 | Broad compatibility; v9 in beta, not production-ready |
| Recharts 3.x | React 18+, React 19 | Stable v3 with React 19 support |
| React Router 7.x | React 18+, React 19 | Stable; v8 requires React 19.2.7+ |
| openai 2.43.0 | Python 3.9+ | Async support via `AsyncOpenAI` client |

## Key Architecture Decisions Embedded in Stack

### Money Storage: NUMERIC(12,2) + Currency Column

### CSV Parsing: Stdlib + Encoding Detection

### API Communication: REST + TanStack Query

## Sources

- [FastAPI 0.138.0 on PyPI](https://pypi.org/project/fastapi/) -- version verified 2026-06-23
- [SQLAlchemy 2.0.51 on PyPI](https://pypi.org/project/SQLAlchemy/) -- version verified 2026-06-23
- [Alembic 1.18.4 on PyPI](https://pypi.org/project/alembic/) -- version verified 2026-06-23
- [OpenAI Python SDK 2.43.0 on PyPI](https://pypi.org/project/openai/) -- version verified 2026-06-23
- [Pydantic 2.13 on PyPI](https://pypi.org/project/pydantic/) -- version verified via web search
- [Recharts 3.9.0 on npm](https://www.npmjs.com/package/recharts) -- version from web search
- [TanStack Query 5.101.0 on npm](https://www.npmjs.com/package/@tanstack/react-query) -- version from web search
- [TanStack Table 8.21.3 on npm](https://www.npmjs.com/package/@tanstack/react-table) -- version from web search
- [Tailwind CSS 4.3 on npm](https://www.npmjs.com/package/tailwindcss) -- version from web search
- [React Router 7.18.0 on npm](https://www.npmjs.com/package/react-router) -- version from web search
- [shadcn/ui installation docs](https://ui.shadcn.com/docs/installation) -- CLI-based, not versioned npm package
- [Frankfurter API](https://frankfurter.dev/) -- free currency API, no key required
- [Crunchy Data: Working with Money in Postgres](https://www.crunchydata.com/blog/working-with-money-in-postgres) -- NUMERIC recommendation
- [OpenAI Cost Optimization Guide](https://developers.openai.com/api/docs/guides/cost-optimization) -- batch API, structured output
- [OpenAI Batch API](https://platform.openai.com/docs/guides/batch) -- 50% discount details
- [charset-normalizer 3.4.6 on PyPI](https://pypi.org/project/charset-normalizer/) -- encoding detection
- [asyncpg 0.31.0 on PyPI](https://pypi.org/project/asyncpg/) -- async PostgreSQL driver
- [Python csv module docs](https://docs.python.org/3/library/csv.html) -- stdlib CSV parsing

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
