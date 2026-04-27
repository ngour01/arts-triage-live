"""
ARTs v1.0.0 — FastAPI Application Entry Point.

Initializes the database pool, Redis cache, and triage intelligence on
startup.  Includes all API routers under /api/v1.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app.database import init_pool, close_pool, get_conn
from app.services import triage_service, cache_service
from app.routers import runs, triage, export, analytics, rules, buckets


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("--> ARTs v1.0.0: Initializing...")
    pool = init_pool()
    cache_service.init_cache()

    with get_conn() as conn:
        triage_service.load_intelligence(conn)

    meta = triage_service.get_buckets_meta()
    print(
        f"--> Loaded {len(triage_service._rules)} rules, "
        f"{len(meta)} buckets. Ready."
    )

    yield

    cache_service.close_cache()
    close_pool()
    print("--> ARTs shutdown complete.")


app = FastAPI(
    title="ARTs v1.0.0",
    description="Autonomous Relational Triage System for CI/CD Failure Analytics",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router)
app.include_router(triage.router)
app.include_router(export.router)
app.include_router(analytics.router)
app.include_router(rules.router)
app.include_router(buckets.router)


def _root_payload() -> dict:
    rules_count = len(triage_service._rules)
    buckets_count = len(triage_service.get_buckets_meta())
    return {
        "name": "ARTs — Autonomous Relational Triage System",
        "version": "1.0.0",
        "status": "live",
        "description": (
            "CI/CD failure analytics platform. Ingests test failures, "
            "classifies them via a waterfall-priority rules engine across "
            "6 relational buckets, and surfaces trends for management."
        ),
        "intelligence": {
            "rules_loaded": rules_count,
            "buckets": buckets_count,
        },
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "analytics": "/api/v1/analytics/summary",
            "triage": "/api/v1/triage/attempt",
            "batch": "/api/v1/triage/batch",
            "export": "/api/v1/export/{cycle_id}",
        },
    }


def _root_html() -> str:
    data = _root_payload()
    rules = data["intelligence"]["rules_loaded"]
    buckets = data["intelligence"]["buckets"]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ARTs API</title>
  <style>
    body{{font-family:system-ui,Segoe UI,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.6}}
    a{{color:#2563eb}} code{{background:#f1f5f9;padding:0 .2em;border-radius:3px}}
    ul{{line-height:1.8}}
  </style>
</head>
<body>
  <h1>ARTs API</h1>
  <p><strong>Status:</strong> {data['status']} &mdash; {data['version']}</p>
  <p>{data['description']}</p>
  <p><strong>Intelligence loaded:</strong> {rules} rules, {buckets} buckets.</p>
  <h2>Quick links</h2>
  <ul>
    <li><a href="/docs">Interactive API docs (Swagger)</a></li>
    <li><a href="/redoc">ReDoc</a></li>
    <li><a href="/health"><code>GET /health</code></a></li>
    <li><a href="/meta">Machine-readable metadata (JSON) — <code>GET /meta</code></a></li>
  </ul>
  <h2>Dashboard</h2>
  <p>Web UI (run <code>npm run dev</code> in the frontend): <a href="http://localhost:3000">http://localhost:3000</a></p>
</body>
</html>"""


@app.get("/")
def root_landing() -> HTMLResponse:
    """
    HTML landing for GET /. JSON: GET /meta.
    """
    return HTMLResponse(_root_html())


@app.head("/")
def root_landing_head() -> Response:
    """HEAD for link checkers; empty body, 200."""
    return Response()


@app.get("/meta", include_in_schema=True)
def root_metadata():
    """JSON metadata about this server (same data that used to be returned from GET /)."""
    return _root_payload()


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/v1/health")
def api_v1_health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {
            "status": "healthy",
            "db": "connected",
            "rules_loaded": len(triage_service._rules),
            "buckets_loaded": len(triage_service.get_buckets_meta()),
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)},
        )
