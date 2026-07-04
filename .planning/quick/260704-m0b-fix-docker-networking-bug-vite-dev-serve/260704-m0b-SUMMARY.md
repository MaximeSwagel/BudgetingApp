---
phase: quick-260704-m0b
plan: 01
subsystem: infra
tags: [vite, docker-compose, proxy, networking]

# Dependency graph
requires: []
provides:
  - Env-driven Vite dev-server proxy target for the /api route
  - docker-compose frontend service pointed at backend via Docker DNS
affects: [frontend-dev-server, docker-compose]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Vite dev-server proxy target resolved from process.env.VITE_API_URL with a localhost fallback, so the same vite.config.ts works both natively and under docker-compose"

key-files:
  created: []
  modified:
    - frontend/vite.config.ts
    - docker-compose.yml

key-decisions:
  - "Read process.env.VITE_API_URL directly in vite.config.ts (Node context) rather than import.meta.env, since vite.config.ts executes in Node, not the browser"
  - "Used Docker Compose service DNS name (backend) instead of localhost so the frontend container can reach the backend container"

patterns-established:
  - "Environment-driven proxy/service targets: default to localhost for native/host runs, override via env var for containerized runs"

requirements-completed: [QUICK-M0B]

# Metrics
duration: 5min
completed: 2026-07-04
status: complete
---

# Quick Task 260704-m0b: Fix Docker Networking Bug (Vite Dev-Server Proxy) Summary

**Vite dev-server `/api` proxy now reads `VITE_API_URL` (falling back to `http://localhost:8000`), and docker-compose points the frontend at `http://backend:8000` via Docker DNS, fixing ECONNREFUSED under docker-compose.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-04
- **Completed:** 2026-07-04
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Vite proxy target for `/api` is now env-driven (`process.env.VITE_API_URL`) with a `http://localhost:8000` fallback for native/host runs
- `docker-compose.yml` frontend service `VITE_API_URL` corrected to `http://backend:8000`, resolving via Docker's internal DNS to the backend container
- Verified with `npx vite build --mode development` that the updated config loads and builds cleanly

## Task Commits

Both tasks were combined into a single atomic commit (small, tightly-coupled two-line fix):

1. **Task 1: Read Vite proxy target from `VITE_API_URL` with localhost fallback** - `104ec0c` (fix)
2. **Task 2: Point frontend `VITE_API_URL` at the backend service DNS name** - `104ec0c` (fix)

## Files Created/Modified
- `frontend/vite.config.ts` - `/api` proxy target now reads `process.env.VITE_API_URL`, falling back to `http://localhost:8000`; `changeOrigin: true` preserved
- `docker-compose.yml` - frontend service `VITE_API_URL` changed from `http://localhost:8000` to `http://backend:8000`

## Decisions Made
- Combined both tasks into one commit since they are two lines that only make sense together (env var producer + consumer)
- Kept the fix minimal: no new dependencies, no config abstraction layer beyond a single local `const apiTarget`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required. Change is self-contained; docker-compose users get the fix automatically on next `docker compose up`.

## Next Phase Readiness
- Docker-compose frontend can now reach the backend container's `/api/*` routes without ECONNREFUSED
- Native `npm run dev` (no `VITE_API_URL` set) continues to proxy to `http://localhost:8000` unchanged

---
*Quick task: 260704-m0b*
*Completed: 2026-07-04*

## Self-Check: PASSED

- FOUND: frontend/vite.config.ts contains `process.env.VITE_API_URL` and `http://localhost:8000` fallback
- FOUND: docker-compose.yml contains `VITE_API_URL: http://backend:8000`
- FOUND: commit 104ec0c in `git log --oneline`
