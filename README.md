
# ARTs v1.0.0 — Autonomous Relational Triage System

**CI/CD Failure Analytics & Classification Platform**

An intelligent triage system for Broadcom/VMware DragonSuite test logs.
ARTs ingests test failures, classifies them into 6 relational buckets using a
waterfall-priority rules engine, and surfaces trends via a Tremor-based
management dashboard.

| Component | Stack |
|-----------|-------|
| Backend   | FastAPI 0.109 + Gunicorn/Uvicorn, Python 3.11+ |
| Frontend  | Next.js 14 (App Router) + Tremor + Tailwind |
| Database  | PostgreSQL 15 (partitioned `test_attempts`) |
| Cache     | Redis 7 (analytics query caching) |
| Ops       | Docker Compose + Makefile |

---

## Project Structure

```
arts/
├── Makefile                    # One-command local ops
├── docker-compose.yml          # Full stack orchestration
├── .env / .env.example         # Environment variables
├── .dockerignore
│
├── shared/
│   └── scrub.py                # Single-source scrub_message() utility
│
├── backend/
│   ├── Dockerfile              # Multi-stage Python image
│   ├── requirements.txt        # Pinned Python deps
│   ├── app/
│   │   ├── main.py             # FastAPI entrypoint + lifespan
│   │   ├── config.py           # pydantic-settings configuration
│   │   ├── database.py         # Connection pool management
│   │   ├── models.py           # Pydantic request/response schemas
│   │   ├── routers/
│   │   │   ├── runs.py         # POST/PUT  /api/v1/runs
│   │   │   ├── triage.py       # POST      /api/v1/triage/attempt & /batch
│   │   │   ├── export.py       # GET       /api/v1/export/{cycle_id}
│   │   │   └── analytics.py    # GET       /api/v1/analytics/*
│   │   └── services/
│   │       ├── triage_service.py       # Waterfall classification engine
│   │       ├── fingerprint_service.py  # SHA-256 composite hashing
│   │       └── cache_service.py        # Redis caching layer
│   ├── scripts/
│   │   ├── setup_db.py         # Create schema from init.sql
│   │   ├── seed_rules.py       # Populate master_rules table
│   │   └── reset_db.py         # Truncate all data tables
│   └── tests/
│       ├── conftest.py
│       ├── test_triage_service.py
│       └── test_api.py
│
├── frontend/
│   ├── Dockerfile              # Multi-stage Node image (standalone)
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx      # Root layout (Inter font)
│   │   │   ├── page.tsx        # Dashboard (metrics + charts + table)
│   │   │   └── attention/
│   │   │       └── page.tsx    # Filtered Bucket 3 & 4 view
│   │   ├── components/
│   │   │   ├── MetricsBar.tsx
│   │   │   ├── FailureVolumeChart.tsx   # Tremor BarChart
│   │   │   ├── TriageProgressChart.tsx  # Tremor AreaChart
│   │   │   ├── BucketCards.tsx
│   │   │   ├── FailuresTable.tsx
│   │   │   └── DashboardShell.tsx
│   │   └── lib/
│   │       └── api.ts          # Typed fetch wrapper
│   └── vitest.config.ts
│
└── docker/
    └── postgres/
        └── init.sql            # Partitioned production schema
```

---

## Prerequisites

- **Python 3.11+** with `pip`
- **Node.js 20+** with `npm`
- **Docker & Docker Compose** (for containerised mode)
- **Redis** (local install or Docker)
- **PostgreSQL** — local install or the Postgres service from `docker compose` (default DSN targets `localhost:5432`)

---

## Quick Start

### 1. Clone & configure environment

```bash
git clone <repo-url> && cd arts
cp .env.example .env
# DATABASE_URL defaults to local Postgres: postgres@localhost:5432/art_triage
# Use `make dev` to start Postgres + Redis in Docker, then run the backend.
```

### 2. Choose your mode

| Mode | Command | What it does |
|------|---------|-------------|
| Full Docker stack | `make dev` | Starts DB, Redis, backend, frontend in Docker |
| Backend only (local) | See "Local Backend" below | Run FastAPI directly on your machine |
| Frontend only (local) | See "Local Frontend" below | Run Next.js dev server on your machine |

---

## Local Backend Setup (without Docker)

```bash
# 1. Install Python dependencies
cd backend
pip install -r requirements.txt

# 2. Ensure .env exists at the repo root with your DATABASE_URL
#    The backend reads from ../.env automatically via pydantic-settings.

# 3. Set up the database schema (first time only)
python -m scripts.setup_db

# 4. Seed classification rules (first time, or after rule changes)
python -m scripts.seed_rules

# 5. Start the API server with hot-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now live at **http://localhost:8000**.
Check health: `curl http://localhost:8000/health`

Swagger docs: **http://localhost:8000/docs**

### Cycle harvest (DragonSuite → API)

Use the single CLI — **`backend/scripts/log_crawler.py`** — to pull failing tests from a DragonSuite-compatible `getCycleRecords` API and batch them into ARTs. It shares **`shared/crawler_utils`** with **`POST /api/v1/triage/discover`**.

```bash
# From repo root (requires backend deps + running API + DB)
cd backend && PYTHONPATH=.. python3 scripts/log_crawler.py 580
# Or: make log-crawl CYCLE=580
# Optional record cap: make log-crawl CYCLE=580 LIMIT=100
```

Point **`DRAGONSUITE_API_BASE`** at your real service, or run a local mock:  
`cd backend/scripts && uvicorn mock_dragonsuite:app --host 127.0.0.1 --port 9000`

### Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/health` | Health check |
| POST | `/api/v1/runs` | Create/resume a triage cycle |
| PUT  | `/api/v1/runs/{id}` | Update cycle status |
| POST | `/api/v1/triage/attempt` | Classify a single test failure |
| POST | `/api/v1/triage/batch` | Classify up to 500 failures in one transaction |
| GET  | `/api/v1/export/{cycle_id}` | Export full triage data for a cycle |
| GET  | `/api/v1/analytics/summary` | Dashboard summary metrics |
| GET  | `/api/v1/analytics/volume-by-bucket?days=30` | Bucket distribution |
| GET  | `/api/v1/analytics/triage-progress?days=30` | Daily triage trend |

---

## Local Frontend Setup (without Docker)

```bash
# 1. Install Node dependencies
cd frontend
npm install

# 2. Set the API URL (backend must be running)
export NEXT_PUBLIC_API_URL=http://localhost:8000

# 3. Start the dev server with hot-reload
npm run dev
```

The dashboard is now live at **http://localhost:3000**.

- **Dashboard** (`/`) — Metrics bar, bucket volume chart, triage progress chart, failure table.
- **Attention** (`/attention`) — Filtered view of Product (Bucket 3) and Unknown (Bucket 4) failures.

---

## Docker Compose (Full Stack)

```bash
# Start everything (Postgres, Redis, Backend, Frontend)
make dev

# Or in detached mode
make run
```

| Service  | Port  | URL |
|----------|-------|-----|
| Frontend | 3000  | http://localhost:3000 |
| Backend  | 8000  | http://localhost:8000 |
| Postgres | 5432  | `psql -h localhost -U postgres -d art_triage` |
| Redis    | 6379  | `redis-cli` |

---

## Running Tests

```bash
# All tests (backend + frontend)
make test

# Backend only
make test-backend
# or directly:
cd backend && python -m pytest tests/ -v

# Frontend only
make test-frontend
# or directly:
cd frontend && npx vitest run
```

---

## Makefile Reference

| Target | Description |
|--------|-------------|
| `make help` | List all available targets |
| `make dev` | Start full stack with hot-reload |
| `make run` | Production build and launch (detached) |
| `make stop` | Stop all Docker services |
| `make reset` | Wipe volumes and rebuild everything |
| `make setup` | Run schema + seed inside Docker backend |
| `make seed` | Re-seed classification rules only |
| `make test` | Run all tests (pytest + vitest) |
| `make test-backend` | Backend tests only |
| `make test-frontend` | Frontend tests only |
| `make logs` | Tail all service logs |
| `make logs-backend` | Tail backend logs only |

---

## Architecture

### Waterfall Priority Engine

Failures are classified in strict priority order. The first match wins:

| Priority | Bucket | ID | Trigger |
|----------|--------|----|---------|
| 1 | Product (PSOD) | 3 | PSOD, core dumps, firstboot errors |
| 2 | Timeouts | 6 | `TIMEOUT` + `TEST IS STILL RUNNING` |
| 3 | Infra Errors | 2 | Connection refused, platform faults, deploy failures |
| 4 | User Errors | 1 | Invalid test specs, HTTP 40x, syntax errors |
| 5 | Test Logic | 5 | Assertion errors, undefined variables |
| 6 | Unknown | 4 | No rule matched (fallback) |

### Composite Fingerprinting

Each error pattern is hashed with SHA-256 using three fields:

```
SHA-256( error_class | scrubbed_message | bucket_id )
```

This ensures identical errors always map to the same fingerprint while
different bucket assignments produce distinct fingerprints.

### Database Partitioning

The `test_attempts` table is range-partitioned by `created_at` month,
with 12 months of partitions pre-created. This keeps queries fast even
at high volume.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...@localhost:5432/art_triage` | Full Postgres DSN |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `DB_POOL_MIN` | `1` | Minimum DB connections in pool |
| `DB_POOL_MAX` | `20` | Maximum DB connections in pool |
| `REDIS_CACHE_TTL` | `300` | Analytics cache TTL in seconds |
| `BATCH_MAX_SIZE` | `500` | Max records per batch request |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL for frontend |

---

<img width="1728" alt="Screenshot 2026-03-12 at 4 20 17 AM" src="https://github-vcf.devops.broadcom.net/vcf/arts/assets/3687/9bdbbb87-714c-40e9-b29c-48386a4e48ff">
<img width="1728" alt="Screenshot 2026-03-12 at 4 20 12 AM" src="https://github-vcf.devops.broadcom.net/vcf/arts/assets/3687/5a13f91e-bf9f-4fef-b5a4-7968215fdeda">
