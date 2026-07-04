<!-- generated-by: gsd-doc-writer -->
# Testing

BudgetingApp currently has **no automated test suite**. There are no test files, no test framework
dependencies, no test configuration, and no CI workflow anywhere in the repository as of this writing.
This document describes that current state and lays out the testing approach the project is set up to
adopt, based on the tooling already chosen for the stack.

## Test framework and setup

No test framework is installed or configured yet:

- **Backend** (`backend/requirements.txt`) lists only runtime dependencies (`fastapi`, `sqlalchemy`,
  `asyncpg`, `alembic`, `openai`, `httpx`, `pydantic`, etc.) — there is no `pytest`, `pytest-asyncio`, or
  `pytest-cov` entry, and no `pyproject.toml`, `pytest.ini`, or `conftest.py` exists in the repo.
- **Frontend** (`frontend/package.json`) lists only `react`, `react-dom`, `react-router-dom` as
  dependencies and `@vitejs/plugin-react`, `typescript`, `vite`, and their `@types` packages as
  devDependencies — there is no `vitest`, `@testing-library/react`, or `jsdom` entry, and no
  `vitest.config.ts` exists.
- No `tests/`, `test/`, or `__tests__/` directory exists in either `backend/` or `frontend/`.

The project's own tooling guidance (`.claude/CLAUDE.md`) recommends **pytest** (with `pytest-asyncio` for
the async FastAPI/SQLAlchemy code paths) for the backend and **Vitest** for the frontend, since Vitest is
Vite-native and the frontend is already built on Vite 6. Adopting a test suite would mean adding these as
dev dependencies:

```bash
# backend
pip install pytest pytest-asyncio pytest-cov

# frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

<!-- VERIFY: Whether test dependencies and configuration have been added in a phase after this document was generated -->

## Running tests

No test command exists today:

- `backend/requirements.txt` has no associated test runner script, and there is no `Makefile` in the
  repository.
- `frontend/package.json` `scripts` only defines `dev`, `build`, and `preview` (see
  `frontend/package.json`) — there is no `test` or `test:watch` script.

Once a framework is added, the expected commands (matching stack conventions used elsewhere in this
project) would be:

```bash
# backend — run from backend/ with the virtualenv activated
pytest

# frontend — run from frontend/
npm run test
```

<!-- VERIFY: Add a `scripts.test` entry to frontend/package.json and a documented pytest invocation once the test suite exists -->

## Writing new tests

No test file naming convention exists yet because no test files have been written. If a suite is
introduced, the natural conventions for the chosen tools would be:

- **Backend:** `pytest` discovers files matching `test_*.py` or `*_test.py`. Given the existing layout
  (`backend/app/parsers/`, `backend/app/services/`, `backend/app/routers/`), tests would likely live in a
  parallel `backend/tests/` directory (e.g., `backend/tests/parsers/test_revolut.py`,
  `backend/tests/services/test_currency.py`), or co-located as `backend/app/parsers/test_revolut.py`.
  Priority candidates for first tests based on current code complexity: `backend/app/parsers/detector.py`
  and `backend/app/parsers/revolut.py`/`ca.py` (format-detection and CSV-parsing edge cases),
  `backend/app/services/currency.py` (Frankfurter API cross-rate math and fallback-rate behavior), and
  `backend/app/services/categorizer.py` (batching and fallback-to-`Uncategorized` behavior when
  `OPENAI_API_KEY` is unset or the API call fails).
- **Frontend:** Vitest conventionally discovers `*.test.ts(x)` or `*.spec.ts(x)` files, commonly
  co-located next to the source file (e.g., `frontend/src/api/client.test.ts`). The most testable surface
  today is `frontend/src/api/client.ts` (fetch wrapper functions), since `frontend/src/pages/` currently
  mixes data-fetching and rendering logic directly in the page components.

<!-- VERIFY: Confirm chosen test directory layout and naming convention once the first test files are added -->

## Coverage requirements

No coverage threshold is configured. There is no `.coveragerc`, no `pyproject.toml`
`[tool.coverage.report]` section, no `pytest.ini` `--cov-fail-under` flag, and no `vitest.config.ts`
`coverage` block anywhere in the repository.

## CI integration

There is no CI/CD pipeline in this repository — no `.github/workflows/` directory exists, and no other CI
configuration (`.gitlab-ci.yml`, `.circleci/`, etc.) was found. Tests are not currently run automatically
on push or pull request.

<!-- VERIFY: Confirm whether a CI workflow is planned; if added, this section should document the workflow file, trigger, and test command it runs -->
