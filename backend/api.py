import os
import time
import hashlib
import json
import re
import logging

from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from typing import Annotated, List, Literal, Optional
import psycopg2
import psycopg2.pool
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
import requests as http_requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("art_triage")

DB_CONFIG = {
    "dbname": "art_triage",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432",
}

API_KEY = os.environ.get("ART_API_KEY")

_write_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

db_pool = None
_triage_state = {"rules": [], "buckets": {}}

PRIORITY = {3: 1, 6: 2, 2: 3, 1: 4, 5: 5, 4: 6}

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')
HOST_PATTERN = re.compile(r'[\w\-]+\.(esx|vc)')
IP_PATTERN = re.compile(r'\d{1,3}(\.\d{1,3}){3}')
HEX_PATTERN = re.compile(r'0x[0-9a-fA-F]+')


def load_rules_to_memory(conn):
    """Build new rule/bucket structures, then swap via single atomic reference."""
    global _triage_state
    new_buckets = {}
    new_rules = []

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name, is_sticky FROM buckets WHERE deleted_at IS NULL;")
        for row in cur.fetchall():
            new_buckets[row['id']] = row

        cur.execute("SELECT target_bucket_id, pattern_text FROM master_rules WHERE is_active = TRUE;")
        for r in cur.fetchall():
            conds = json.loads(r['pattern_text'])
            weight = PRIORITY.get(r['target_bucket_id'], 99) + (-0.5 if "msg_pattern" in conds else 0)
            compiled_conds = {k: re.compile(v, re.IGNORECASE) for k, v in conds.items()}
            new_rules.append({
                "weight": weight,
                "target_bucket_id": r['target_bucket_id'],
                "conditions": compiled_conds,
            })

    new_rules = sorted(new_rules, key=lambda x: x["weight"])

    _triage_state = {"rules": new_rules, "buckets": new_buckets}

    logger.info("Loaded %d rules and %d buckets into memory", len(new_rules), len(new_buckets))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    db_pool = ThreadedConnectionPool(1, 50, **DB_CONFIG)
    logger.info("Database connection pool created (max=50)")
    conn = db_pool.getconn()
    try:
        load_rules_to_memory(conn)
    finally:
        db_pool.putconn(conn)
    yield
    if db_pool:
        db_pool.closeall()
        logger.info("Database connection pool closed")


app = FastAPI(
    title="ART v3 Engine",
    version="3.0",
    lifespan=lifespan,
    description="Ingest test results, classify failures, export dashboards; writes need X-API-Key when ART_API_KEY is set.",
    openapi_tags=[
        {"name": "Health", "description": "Service and database health."},
        {"name": "Runs", "description": "Create runs and refresh stats."},
        {"name": "Rules", "description": "Classification rules."},
        {"name": "Triage", "description": "Ingest attempts and assign bugs."},
        {"name": "Dashboard", "description": "Read runs, buckets, exports."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "message": str(exc), "path": request.url.path},
    )


def get_db():
    """Yield a pooled connection with retry on pool exhaustion."""
    conn = None
    for attempt in range(3):
        try:
            conn = db_pool.getconn()
            break
        except psycopg2.pool.PoolError:
            if attempt < 2:
                logger.warning("Connection pool exhausted, retrying (%d/3)…", attempt + 1)
                time.sleep(0.5 * (attempt + 1))
    if conn is None:
        logger.error("Failed to acquire DB connection after 3 retries")
        raise HTTPException(status_code=503, detail="Database connection pool exhausted")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        db_pool.putconn(conn)


def require_write_auth(x_api_key: Optional[str] = Depends(_write_api_key_header)):
    """Require X-API-Key when ART_API_KEY is set (enables Swagger header on writes)."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# --- MODELS ---

class RunCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"identifier": "Cycle-580"}})
    identifier: str = "UNKNOWN"


class RuleCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "pattern_text": {"msg_pattern": "INVALID LOGIN"},
                "target_bucket_id": 1,
                "added_by": "api",
            }
        }
    )
    pattern_text: dict
    target_bucket_id: int
    added_by: str = "User"


class TriageRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "log_url": "https://logs.example/build/42/stateDump.json.txt",
                "user_id": "api",
                "run_identifier": "Cycle-580",
            }
        }
    )
    log_url: str
    user_id: str = "Anonymous"
    run_identifier: Optional[str] = None


class DiscoverRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://jenkins.example/job/1/artifact/logs/myTest/",
                "run_identifier": "Cycle-580",
                "feature_name": "Storage",
            }
        }
    )
    url: str
    run_identifier: str
    feature_name: Optional[str] = None


class SignalBugUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "test_attempt_id": 12345,
                "fingerprint": "<64-char sha256 hex>",
                "bug_id": "JIRA-12345",
            }
        }
    )
    test_attempt_id: int
    fingerprint: str
    bug_id: Optional[str] = None


class AttemptPayload(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "run_id": 1,
                "feature_name": "Networking",
                "test_case_name": "vMotionStress",
                "log_url": "https://logs.example/run/99/stateDump.json.txt",
                "status": "FAIL",
                "result": "FAIL",
                "json_error_message": "Host unreachable",
                "atomic_signals": [],
            }
        }
    )
    run_id: Optional[int] = 0
    user_id: Optional[str] = "System"
    feature_name: Optional[str] = "Unknown"
    test_case_name: Optional[str] = "Unknown"
    log_url: str
    status: Optional[str] = "FAIL"
    result: Optional[str] = "FAIL"
    result_type: Optional[str] = "N/A"
    error_class: Optional[str] = "N/A"
    json_error_message: Optional[str] = "N/A"
    atomic_signals: Optional[List[str]] = None


# --- CORE LOGIC ---

def scrub(msg: str):
    if not msg:
        return "N/A"
    m = str(msg)
    m = ANSI_ESCAPE.sub('', m)
    mu = m.upper()
    if "PSOD" in mu or "CORE" in mu:
        return m.strip()
    m = HOST_PATTERN.sub('<HOST>', m)
    m = IP_PATTERN.sub('<IP>', m)
    m = HEX_PATTERN.sub('<HEX>', m)
    m = m.replace('\n', ' ')
    return m.strip()


def classify(msg: str, result: str = "FAIL", res_type: str = "N/A", err_class: str = "N/A"):
    mu = msg.upper()
    if "PSOD" in mu or "CORE" in mu:
        return 3
    if result.upper() == "TIMEOUT":
        return 6
    for rule in _triage_state["rules"]:
        conds = rule['conditions']
        matched = True
        if "msg_pattern" in conds and not conds["msg_pattern"].search(msg):
            matched = False
        if matched and "result" in conds and not conds["result"].search(result):
            matched = False
        if matched and "res_type" in conds and not conds["res_type"].search(res_type):
            matched = False
        if matched and "err_class" in conds and not conds["err_class"].search(err_class):
            matched = False
        if matched:
            return rule['target_bucket_id']
    return 4


def _insert_attempt_logic(cur, p: AttemptPayload):
    run_id = p.run_id or 0
    feature = (p.feature_name or "Unknown").strip()
    test_case = (p.test_case_name or "Unknown").strip()
    status = p.status or "FAIL"
    res_val = p.result or "FAIL"
    err_class = p.error_class or "N/A"
    json_err = p.json_error_message or "N/A"
    atom_sigs = p.atomic_signals or []

    cur.execute(
        "SELECT ta.id, ta.status FROM test_attempts ta "
        "JOIN test_executions te ON ta.test_execution_id=te.id "
        "WHERE ta.log_url=%s AND te.run_id=%s",
        (p.log_url, run_id))
    existing = cur.fetchone()

    cur.execute(
        "INSERT INTO test_executions (run_id, feature_name, test_case_name) "
        "VALUES (%s,%s,%s) ON CONFLICT (run_id, feature_name, test_case_name) "
        "DO UPDATE SET updated_at=NOW() RETURNING id, latest_attempt_number, has_sticky_failure",
        (run_id, feature, test_case))
    ex_id, last_att, was_sticky = cur.fetchone()

    if existing:
        att_id = existing[0]
        att_num = last_att
        cur.execute("UPDATE test_attempts SET status=%s, updated_at=NOW() WHERE id=%s", (status, att_id))
    else:
        att_num = (last_att or 0) + 1
        cur.execute(
            "INSERT INTO test_attempts (test_execution_id, attempt_number, status, log_url) "
            "VALUES (%s,%s,%s,%s) RETURNING id",
            (ex_id, att_num, status, p.log_url))
        att_id = cur.fetchone()[0]

    is_pass = (status.upper() == "PASS")
    bid, sticky = None, was_sticky
    bm_snapshot = _triage_state["buckets"]

    if not is_pass and status.upper() != "IN_PROGRESS":
        if atom_sigs:
            all_signals = list(atom_sigs)
        elif json_err and json_err != "N/A":
            all_signals = [json_err]
        else:
            all_signals = ["N/A"]

        best_bid = 4
        best_priority = PRIORITY.get(4, 99)

        for sig in all_signals:
            msg = scrub(sig)
            sig_bid = classify(msg, res_val, p.result_type or "N/A", err_class)
            fp = hashlib.sha256(f"{err_class}|{msg}".encode()).hexdigest()

            cur.execute(
                "INSERT INTO error_patterns (fingerprint, scrubbed_message, error_class, resolved_bucket_id) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (fingerprint) DO UPDATE SET resolved_bucket_id=EXCLUDED.resolved_bucket_id",
                (fp, msg, err_class, sig_bid))
            cur.execute(
                "INSERT INTO triage_signals (test_attempt_id, fingerprint) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (att_id, fp))

            sig_priority = PRIORITY.get(sig_bid, 99)
            if sig_priority < best_priority:
                best_priority = sig_priority
                best_bid = sig_bid

            if bm_snapshot.get(sig_bid, {}).get('is_sticky'):
                sticky = True

        bid = best_bid
    elif is_pass and was_sticky:
        cur.execute("SELECT latest_bucket_id FROM test_executions WHERE id=%s", (ex_id,))
        prev = cur.fetchone()
        bid = prev[0] if prev else None

    cur.execute(
        "UPDATE test_executions SET latest_attempt_number=%s, is_currently_passing=%s, "
        "has_sticky_failure=%s, latest_bucket_id=%s WHERE id=%s",
        (att_num, is_pass, sticky, bid, ex_id))


def _fetch_run_stats(cur, rid: int, identifier: str) -> dict:
    """Aggregate totals, per-bucket counts, triage signals, and unique bug/issue ids for one run."""
    cur.execute(
        """
        SELECT
            COUNT(*)::int AS total,
            COALESCE(SUM(CASE WHEN is_currently_passing THEN 1 ELSE 0 END), 0)::int AS passing,
            COALESCE(SUM(CASE WHEN NOT is_currently_passing THEN 1 ELSE 0 END), 0)::int AS failing,
            COALESCE(SUM(CASE WHEN has_sticky_failure THEN 1 ELSE 0 END), 0)::int AS sticky_failures
        FROM test_executions WHERE run_id = %s AND deleted_at IS NULL
        """,
        (rid,),
    )
    exe = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*)::int AS c FROM test_attempts ta
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s AND te.deleted_at IS NULL
        """,
        (rid,),
    )
    attempt_count = cur.fetchone()["c"]

    cur.execute(
        """
        SELECT COUNT(*)::int AS c FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s AND te.deleted_at IS NULL AND ts.deleted_at IS NULL
        """,
        (rid,),
    )
    signal_total = cur.fetchone()["c"]

    cur.execute(
        """
        SELECT COUNT(*)::int AS c FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s AND te.deleted_at IS NULL AND ts.deleted_at IS NULL
          AND ts.bug_id IS NOT NULL AND TRIM(ts.bug_id) <> ''
        """,
        (rid,),
    )
    signals_with_bug = cur.fetchone()["c"]

    cur.execute(
        """
        SELECT COUNT(DISTINCT ts.fingerprint)::int AS c FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s AND te.deleted_at IS NULL AND ts.deleted_at IS NULL
        """,
        (rid,),
    )
    unique_fingerprints = cur.fetchone()["c"]

    cur.execute(
        """
        SELECT b.id, b.name, b.is_sticky,
               COUNT(te.id)::int AS failing_or_sticky_executions
        FROM buckets b
        LEFT JOIN test_executions te ON te.latest_bucket_id = b.id
            AND te.run_id = %s AND te.deleted_at IS NULL
            AND (NOT te.is_currently_passing OR te.has_sticky_failure)
        WHERE b.deleted_at IS NULL
        GROUP BY b.id, b.name, b.is_sticky
        ORDER BY b.id
        """,
        (rid,),
    )
    bucket_rows = cur.fetchall()

    cur.execute(
        """
        SELECT ep.resolved_bucket_id AS bucket_id, COUNT(*)::int AS signal_count
        FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        JOIN error_patterns ep ON ts.fingerprint = ep.fingerprint
        WHERE te.run_id = %s AND te.deleted_at IS NULL AND ts.deleted_at IS NULL
        GROUP BY ep.resolved_bucket_id
        """,
        (rid,),
    )
    sig_by_b = {r["bucket_id"]: r["signal_count"] for r in cur.fetchall()}

    cur.execute(
        """
        SELECT ep.resolved_bucket_id AS bucket_id, TRIM(ts.bug_id) AS bug_id
        FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        JOIN error_patterns ep ON ts.fingerprint = ep.fingerprint
        WHERE te.run_id = %s AND te.deleted_at IS NULL AND ts.deleted_at IS NULL
          AND ts.bug_id IS NOT NULL AND TRIM(ts.bug_id) <> ''
        GROUP BY ep.resolved_bucket_id, TRIM(ts.bug_id)
        ORDER BY TRIM(ts.bug_id)
        """,
        (rid,),
    )
    bugs_by_bucket: dict = {}
    for r in cur.fetchall():
        bid = r["bucket_id"]
        bugs_by_bucket.setdefault(bid, []).append(r["bug_id"])

    cur.execute(
        """
        SELECT DISTINCT TRIM(ts.bug_id) AS bug_id
        FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s AND te.deleted_at IS NULL AND ts.deleted_at IS NULL
          AND ts.bug_id IS NOT NULL AND TRIM(ts.bug_id) <> ''
        ORDER BY bug_id
        """,
        (rid,),
    )
    unique_bug_ids = [r["bug_id"] for r in cur.fetchall()]

    buckets_out = []
    for row in bucket_rows:
        bid = row["id"]
        bugs = sorted(bugs_by_bucket.get(bid, []))
        buckets_out.append({
            "id": bid,
            "name": row["name"],
            "is_sticky": row["is_sticky"],
            "failing_or_sticky_executions": row["failing_or_sticky_executions"],
            "signal_count": sig_by_b.get(bid, 0),
            "unique_bug_ids": bugs,
            "unique_bug_count": len(bugs),
        })

    return {
        "run": {"id": rid, "identifier": identifier},
        "totals": {
            "test_executions": exe["total"],
            "passing": exe["passing"],
            "failing": exe["failing"],
            "sticky_failures": exe["sticky_failures"],
            "test_attempts": attempt_count,
            "triage_signals": signal_total,
            "signals_with_bug": signals_with_bug,
            "unique_bug_count": len(unique_bug_ids),
            "unique_error_patterns": unique_fingerprints,
        },
        "buckets": buckets_out,
        "unique_bug_ids": unique_bug_ids,
    }


def _log_run_stats(stats: dict) -> None:
    """Emit one summary line plus per-bucket lines and the full unique issue list."""
    ident = stats["run"]["identifier"]
    t = stats["totals"]
    logger.info(
        "Run %s — totals: executions=%d passing=%d failing=%d sticky=%d attempts=%d "
        "signals=%d signals_w_bug=%d unique_issues=%d unique_patterns=%d",
        ident,
        t["test_executions"],
        t["passing"],
        t["failing"],
        t["sticky_failures"],
        t["test_attempts"],
        t["triage_signals"],
        t["signals_with_bug"],
        t["unique_bug_count"],
        t["unique_error_patterns"],
    )
    for b in stats["buckets"]:
        if b["failing_or_sticky_executions"] or b["signal_count"] or b["unique_bug_ids"]:
            issues = ",".join(b["unique_bug_ids"]) if b["unique_bug_ids"] else "-"
            logger.info(
                "Run %s — bucket %d %s: failing/sticky_exec=%d signals=%d unique_issues=[%s]",
                ident,
                b["id"],
                b["name"],
                b["failing_or_sticky_executions"],
                b["signal_count"],
                issues,
            )
    if stats["unique_bug_ids"]:
        logger.info("Run %s — unique issues (all buckets): %s", ident, ", ".join(stats["unique_bug_ids"]))


# --- WRITE ENDPOINTS ---

@app.post(
    "/api/v1/runs",
    tags=["Runs"],
    summary="Create or upsert a run by identifier and return its numeric id.",
    dependencies=[Depends(require_write_auth)],
)
def create_run(p: RunCreate, conn=Depends(get_db)):
    identifier = (p.identifier or "UNKNOWN").strip() or "UNKNOWN"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs (identifier) VALUES (%s) "
            "ON CONFLICT (identifier) DO UPDATE SET updated_at=NOW() RETURNING id",
            (identifier,))
        run_id = cur.fetchone()[0]
    logger.info("Run registered: %s (id=%s)", identifier, run_id)
    return {"id": run_id}


@app.post(
    "/api/v1/runs/{identifier}/refresh",
    tags=["Runs"],
    summary="Recompute per-bucket snapshot stats for this run (failing executions only).",
    dependencies=[Depends(require_write_auth)],
)
def refresh_run(identifier: str, conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM runs WHERE identifier = %s", (identifier,))
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        rid = run['id']

        cur.execute("""
            INSERT INTO run_stats_snapshots (run_id, bucket_id, test_count, feature_count, suite_count)
            SELECT %(rid)s, b.id,
                COUNT(DISTINCT te.id),
                COUNT(DISTINCT te.feature_name),
                COUNT(DISTINCT te.feature_name)
            FROM buckets b
            LEFT JOIN test_executions te
                ON te.latest_bucket_id = b.id
                AND te.run_id = %(rid)s
                AND te.deleted_at IS NULL
                AND NOT te.is_currently_passing
            WHERE b.deleted_at IS NULL
            GROUP BY b.id
            ON CONFLICT (run_id, bucket_id) DO UPDATE SET
                test_count = EXCLUDED.test_count,
                feature_count = EXCLUDED.feature_count,
                suite_count = EXCLUDED.suite_count,
                captured_at = NOW()
        """, {"rid": rid})

    logger.info("Stats refreshed for run %s", identifier)
    return {"status": "refreshed", "run_id": identifier}


@app.post(
    "/api/v1/rules",
    tags=["Rules"],
    summary="Add or update a classification rule and reload rules in memory.",
    dependencies=[Depends(require_write_auth)],
)
def add_master_rule(req: RuleCreate, conn=Depends(get_db)):
    pattern_json = json.dumps(req.pattern_text, sort_keys=True)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO master_rules (pattern_text, target_bucket_id, added_by) "
            "VALUES (%s, %s, %s) ON CONFLICT (pattern_text) DO "
            "UPDATE SET target_bucket_id = EXCLUDED.target_bucket_id",
            (pattern_json, req.target_bucket_id, req.added_by))
    load_rules_to_memory(conn)
    logger.info("Master rule added/updated for bucket %s", req.target_bucket_id)
    return {"status": "success", "message": "Rule added for future triage."}


@app.post(
    "/api/v1/triage/url",
    tags=["Triage"],
    summary="GET log_url as JSON and record one triaged attempt under run_identifier (or auto name).",
    dependencies=[Depends(require_write_auth)],
)
def triage_url(req: TriageRequest, conn=Depends(get_db)):
    run_name = req.run_identifier or f"QUICK_{datetime.now().strftime('%m%d_%H%M')}"
    try:
        data = http_requests.get(req.log_url, timeout=10).json()
    except Exception as e:
        logger.warning("Failed to fetch log URL %s: %s", req.log_url, e)
        raise HTTPException(status_code=400, detail="Invalid Log URL")

    skipped_duplicate = False
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs (identifier) VALUES (%s) "
            "ON CONFLICT (identifier) DO UPDATE SET updated_at=NOW() RETURNING id",
            (run_name,))
        rid = cur.fetchone()[0]

        cur.execute(
            "SELECT status FROM test_attempts ta "
            "JOIN test_executions te ON ta.test_execution_id=te.id "
            "WHERE ta.log_url=%s AND te.run_id=%s",
            (req.log_url, rid))
        row = cur.fetchone()
        if row and row[0].upper() in ["PASS", "FAIL"]:
            skipped_duplicate = True
        else:
            status = str(data.get("result", "IN_PROGRESS")).upper()
            payload = AttemptPayload(
                run_id=rid, feature_name=data.get("display_name", "Manual"),
                test_case_name=data.get("test_case", "Test"),
                log_url=req.log_url, status=status, result=status,
                json_error_message=data.get("error_message", "N/A"))
            _insert_attempt_logic(cur, payload)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        stats = _fetch_run_stats(cur, rid, run_name)
    _log_run_stats(stats)

    if skipped_duplicate:
        return {"status": "exists", "run_id": run_name, "stats": stats}
    return {"status": "success", "run_id": run_name, "stats": stats}


@app.post(
    "/api/v1/triage/attempt",
    tags=["Triage"],
    summary="Ingest one test attempt (classify errors, update execution and signals).",
    dependencies=[Depends(require_write_auth)],
)
def process_attempt(p: AttemptPayload, conn=Depends(get_db)):
    with conn.cursor() as cur:
        _insert_attempt_logic(cur, p)
    return {"status": "ok"}


@app.post(
    "/api/v1/triage/attempts/batch",
    tags=["Triage"],
    summary="Ingest many attempts in one database transaction.",
    dependencies=[Depends(require_write_auth)],
)
def process_attempt_batch(payloads: List[AttemptPayload], conn=Depends(get_db)):
    with conn.cursor() as cur:
        for p in payloads:
            _insert_attempt_logic(cur, p)

    stats_by_run: List[dict] = []
    seen_runs: set = set()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for p in payloads:
            rid = p.run_id or 0
            if rid and rid not in seen_runs:
                seen_runs.add(rid)
                cur.execute("SELECT identifier FROM runs WHERE id=%s", (rid,))
                rr = cur.fetchone()
                if rr:
                    stats_by_run.append(_fetch_run_stats(cur, rid, rr["identifier"]))
    for st in stats_by_run:
        _log_run_stats(st)

    logger.info("Batch processed: %d attempts", len(payloads))
    return {"status": "ok", "processed": len(payloads), "stats_by_run": stats_by_run}


@app.post(
    "/api/v1/triage/discover",
    tags=["Triage"],
    summary="Crawl url for stateDump JSON (file or directory) and triage into run_identifier.",
    dependencies=[Depends(require_write_auth)],
)
def triage_discover(req: DiscoverRequest, conn=Depends(get_db)):
    from backend.crawler_utils import discover_payloads

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs (identifier) VALUES (%s) "
            "ON CONFLICT (identifier) DO UPDATE SET updated_at=NOW() RETURNING id",
            (req.run_identifier,))
        run_id = cur.fetchone()[0]

    payloads = discover_payloads(req.url, run_id, feature_name=req.feature_name)
    if not payloads:
        raise HTTPException(
            status_code=422,
            detail="No stateDump.json.txt files found at the provided URL."
        )

    with conn.cursor() as cur:
        for p_dict in payloads:
            p = AttemptPayload(**p_dict)
            _insert_attempt_logic(cur, p)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        stats = _fetch_run_stats(cur, run_id, req.run_identifier)
    _log_run_stats(stats)

    logger.info("Discover ingest: %d test(s) → run '%s'", len(payloads), req.run_identifier)
    return {
        "status": "ok",
        "run_identifier": req.run_identifier,
        "ingested": len(payloads),
        "stats": stats,
        "tests": [{"feature": p["feature_name"], "test_case": p["test_case_name"],
                   "status": p["status"], "log_url": p["log_url"]} for p in payloads],
    }


@app.patch(
    "/api/v1/triage/signals",
    tags=["Triage"],
    summary="Set or clear bug_id on one triage signal (by attempt id and fingerprint).",
    dependencies=[Depends(require_write_auth)],
)
def update_signal_bug(req: SignalBugUpdate, conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id FROM triage_signals WHERE test_attempt_id=%s AND fingerprint=%s",
            (req.test_attempt_id, req.fingerprint))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")

        cur.execute(
            "UPDATE triage_signals SET bug_id=%s "
            "WHERE test_attempt_id=%s AND fingerprint=%s",
            (req.bug_id or None, req.test_attempt_id, req.fingerprint))

    action = f"set to {req.bug_id!r}" if req.bug_id else "cleared"
    logger.info("Bug ID %s for attempt=%s fp=%s…", action, req.test_attempt_id, req.fingerprint[:12])
    return {"status": "ok", "bug_id": req.bug_id}


# --- READ / DASHBOARD ENDPOINTS ---

@app.get(
    "/api/v1/health",
    tags=["Health"],
    summary="Check database connectivity and counts of loaded rules and buckets.",
)
def health_check():
    try:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            db_pool.putconn(conn)
        return {
            "status": "healthy",
            "db": "connected",
            "rules_loaded": len(_triage_state["rules"]),
            "buckets_loaded": len(_triage_state["buckets"]),
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)},
        )


@app.get(
    "/api/v1/runs",
    tags=["Dashboard"],
    summary="List all runs (newest first).",
)
def list_runs(conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, identifier, created_at, updated_at "
            "FROM runs WHERE deleted_at IS NULL ORDER BY created_at DESC")
        return cur.fetchall()


@app.get(
    "/api/v1/buckets",
    tags=["Dashboard"],
    summary="List failure buckets (id, name, is_sticky).",
)
def list_buckets(conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name, is_sticky FROM buckets WHERE deleted_at IS NULL ORDER BY id")
        return cur.fetchall()


@app.get(
    "/api/v1/runs/{identifier}/summary",
    tags=["Dashboard"],
    summary="Return pass/fail/sticky counts and per-bucket totals for one run.",
)
def run_summary(identifier: str, conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM runs WHERE identifier = %s", (identifier,))
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        rid = run['id']

        cur.execute("""
            SELECT
                COUNT(*) as total,
                COALESCE(SUM(CASE WHEN is_currently_passing THEN 1 ELSE 0 END), 0) as passing,
                COALESCE(SUM(CASE WHEN NOT is_currently_passing THEN 1 ELSE 0 END), 0) as failing,
                COALESCE(SUM(CASE WHEN has_sticky_failure THEN 1 ELSE 0 END), 0) as sticky_failures
            FROM test_executions WHERE run_id = %s AND deleted_at IS NULL
        """, (rid,))
        counts = cur.fetchone()

        cur.execute("""
            SELECT b.id, b.name, b.is_sticky, COUNT(te.id) as count
            FROM buckets b
            LEFT JOIN test_executions te ON te.latest_bucket_id = b.id
                AND te.run_id = %s AND te.deleted_at IS NULL
                AND (NOT te.is_currently_passing OR te.has_sticky_failure)
            WHERE b.deleted_at IS NULL
            GROUP BY b.id, b.name, b.is_sticky
            ORDER BY b.id
        """, (rid,))
        buckets = cur.fetchall()

        return {
            "run": {"id": rid, "identifier": identifier},
            "total": counts['total'] or 0,
            "passing": counts['passing'] or 0,
            "failing": counts['failing'] or 0,
            "sticky_failures": counts['sticky_failures'] or 0,
            "buckets": buckets,
        }


@app.get(
    "/api/v1/runs/{identifier}/stats",
    tags=["Dashboard"],
    summary="Full run stats: totals, per-bucket counts/signals, unique bug/issue ids.",
)
def run_stats(identifier: str, conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM runs WHERE identifier = %s", (identifier,))
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        rid = run["id"]
        return _fetch_run_stats(cur, rid, identifier)


@app.get(
    "/api/v1/export/{identifier}",
    tags=["Dashboard"],
    summary="Export patterns and failure rows (paginated); optional bucket_id + bucket_scope filter.",
)
def export_report(
    identifier: str,
    limit: Annotated[int, Query(ge=1, le=20000)] = 500,
    skip: Annotated[int, Query(ge=0)] = 0,
    bucket_id: Annotated[Optional[int], Query(description="If set, restrict rows to this bucket.")] = None,
    bucket_scope: Annotated[
        Literal["signal", "execution"],
        Query(description="signal=ep.resolved_bucket_id; execution=te.latest_bucket_id."),
    ] = "signal",
    conn=Depends(get_db),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM runs WHERE identifier = %s", (identifier,))
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        rid = run["id"]

        if bucket_id is not None:
            cur.execute("SELECT 1 FROM buckets WHERE id = %s AND deleted_at IS NULL", (bucket_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Bucket not found")

        bucket_filter = ""
        filter_params: List = [rid]
        if bucket_id is not None:
            if bucket_scope == "signal":
                bucket_filter = " AND ep.resolved_bucket_id = %s"
            else:
                bucket_filter = " AND te.latest_bucket_id = %s"
            filter_params.append(bucket_id)

        cur.execute(
            f"""
            SELECT DISTINCT ep.*
            FROM error_patterns ep
            JOIN triage_signals ts ON ep.fingerprint = ts.fingerprint
            JOIN test_attempts ta ON ts.test_attempt_id = ta.id
            JOIN test_executions te ON ta.test_execution_id = te.id
            WHERE te.run_id = %s{bucket_filter}
            """,
            tuple(filter_params),
        )
        pats = cur.fetchall()

        list_params = tuple(filter_params + [limit, skip])
        cur.execute(
            f"""
            SELECT te.feature_name,
                te.test_case_name,
                te.latest_bucket_id,
                te.has_sticky_failure,
                te.is_currently_passing,
                ta.id as attempt_id,
                ta.attempt_number,
                ta.status as att_status,
                ta.log_url,
                ts.bug_id,
                ts.fingerprint,
                ep.scrubbed_message,
                ep.error_class as pattern_error_class,
                ep.resolved_bucket_id as signal_bucket_id
            FROM test_executions te
            JOIN test_attempts ta ON te.id = ta.test_execution_id
            LEFT JOIN triage_signals ts ON ta.id = ts.test_attempt_id
            LEFT JOIN error_patterns ep ON ts.fingerprint = ep.fingerprint
            WHERE te.run_id = %s{bucket_filter}
            ORDER BY te.test_case_name, ta.attempt_number ASC
            LIMIT %s OFFSET %s
            """,
            list_params,
        )
        fails = cur.fetchall()

        cur.execute(
            f"""
            SELECT COUNT(*) as total
            FROM test_executions te
            JOIN test_attempts ta ON te.id = ta.test_execution_id
            LEFT JOIN triage_signals ts ON ta.id = ts.test_attempt_id
            LEFT JOIN error_patterns ep ON ts.fingerprint = ep.fingerprint
            WHERE te.run_id = %s{bucket_filter}
            """,
            tuple(filter_params),
        )
        total_count = cur.fetchone()["total"]

        return {
            "cycle": {"cycle_id": identifier},
            "filters": {
                "bucket_id": bucket_id,
                "bucket_scope": bucket_scope if bucket_id is not None else None,
            },
            "patterns": pats,
            "failures": fails,
            "pagination": {
                "limit": limit,
                "skip": skip,
                "total_records": total_count,
                "has_more": (skip + limit) < total_count,
            },
        }


# Mount frontend static files (after all API routes)
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
