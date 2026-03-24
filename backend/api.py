import os
import time
import hashlib
import json
import re
import logging
import threading
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
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

db_pool = None
master_rules: list = []
buckets_meta: dict = {}
_rules_lock = threading.Lock()

PRIORITY = {3: 1, 6: 2, 2: 3, 1: 4, 5: 5, 4: 6}

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')
HOST_PATTERN = re.compile(r'[\w\-]+\.(esx|vc)')
IP_PATTERN = re.compile(r'\d{1,3}(\.\d{1,3}){3}')
HEX_PATTERN = re.compile(r'0x[0-9a-fA-F]+')


def load_rules_to_memory(conn):
    """Build new rule/bucket structures, then swap atomically under lock."""
    global master_rules, buckets_meta
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

    with _rules_lock:
        master_rules = new_rules
        buckets_meta = new_buckets

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


app = FastAPI(title="ART v3 Engine", lifespan=lifespan)

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


def require_write_auth(request: Request):
    """Opt-in API-key guard for write endpoints (set ART_API_KEY env var to enable)."""
    if API_KEY and request.headers.get("X-API-Key") != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# --- MODELS ---

class RuleCreate(BaseModel):
    pattern_text: dict
    target_bucket_id: int
    added_by: str = "User"


class TriageRequest(BaseModel):
    log_url: str
    user_id: str = "Anonymous"
    run_identifier: Optional[str] = None


class AttemptPayload(BaseModel):
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
    atomic_signals: Optional[List[str]] = []


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
    rules_snapshot = master_rules
    for rule in rules_snapshot:
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
    bm_snapshot = buckets_meta

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

    cur.execute(
        "UPDATE test_executions SET latest_attempt_number=%s, is_currently_passing=%s, "
        "has_sticky_failure=%s, latest_bucket_id=%s WHERE id=%s",
        (att_num, is_pass, sticky, bid, ex_id))


# --- WRITE ENDPOINTS ---

@app.post("/api/v1/runs", dependencies=[Depends(require_write_auth)])
def create_run(p: dict, conn=Depends(get_db)):
    identifier = p.get('identifier', 'UNKNOWN')
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs (identifier) VALUES (%s) "
            "ON CONFLICT (identifier) DO UPDATE SET updated_at=NOW() RETURNING id",
            (identifier,))
        run_id = cur.fetchone()[0]
    logger.info("Run registered: %s (id=%s)", identifier, run_id)
    return {"id": run_id}


@app.post("/api/v1/runs/{identifier}/refresh", dependencies=[Depends(require_write_auth)])
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


@app.post("/api/v1/rules", dependencies=[Depends(require_write_auth)])
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


@app.post("/api/v1/triage/url", dependencies=[Depends(require_write_auth)])
def triage_url(req: TriageRequest, conn=Depends(get_db)):
    run_name = req.run_identifier or f"QUICK_{datetime.now().strftime('%m%d_%H%M')}"
    try:
        data = http_requests.get(req.log_url, timeout=10).json()
    except Exception as e:
        logger.warning("Failed to fetch log URL %s: %s", req.log_url, e)
        raise HTTPException(status_code=400, detail="Invalid Log URL")

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
            return {"status": "exists", "run_id": run_name}

        status = str(data.get("result", "IN_PROGRESS")).upper()
        payload = AttemptPayload(
            run_id=rid, feature_name=data.get("display_name", "Manual"),
            test_case_name=data.get("test_case", "Test"),
            log_url=req.log_url, status=status, result=status,
            json_error_message=data.get("error_message", "N/A"))
        _insert_attempt_logic(cur, payload)

    return {"status": "success", "run_id": run_name}


@app.post("/api/v1/triage/attempt", dependencies=[Depends(require_write_auth)])
def process_attempt(p: AttemptPayload, conn=Depends(get_db)):
    with conn.cursor() as cur:
        _insert_attempt_logic(cur, p)
    return {"status": "ok"}


@app.post("/api/v1/triage/attempts/batch", dependencies=[Depends(require_write_auth)])
def process_attempt_batch(payloads: List[AttemptPayload], conn=Depends(get_db)):
    with conn.cursor() as cur:
        for p in payloads:
            _insert_attempt_logic(cur, p)
    logger.info("Batch processed: %d attempts", len(payloads))
    return {"status": "ok", "processed": len(payloads)}


# --- READ / DASHBOARD ENDPOINTS ---

@app.get("/api/v1/health")
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
            "rules_loaded": len(master_rules),
            "buckets_loaded": len(buckets_meta),
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)},
        )


@app.get("/api/v1/runs")
def list_runs(conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, identifier, created_at, updated_at "
            "FROM runs WHERE deleted_at IS NULL ORDER BY created_at DESC")
        return cur.fetchall()


@app.get("/api/v1/buckets")
def list_buckets(conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name, is_sticky FROM buckets WHERE deleted_at IS NULL ORDER BY id")
        return cur.fetchall()


@app.get("/api/v1/runs/{identifier}/summary")
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
                AND te.run_id = %s AND te.deleted_at IS NULL AND NOT te.is_currently_passing
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


@app.get("/api/v1/export/{identifier}")
def export_report(identifier: str, limit: int = 500, skip: int = 0, conn=Depends(get_db)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM runs WHERE identifier = %s", (identifier,))
        run = cur.fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        rid = run['id']

        cur.execute("""
            SELECT DISTINCT ep.*
            FROM error_patterns ep
            JOIN triage_signals ts ON ep.fingerprint = ts.fingerprint
            JOIN test_attempts ta ON ts.test_attempt_id = ta.id
            JOIN test_executions te ON ta.test_execution_id = te.id
            WHERE te.run_id = %s
        """, (rid,))
        pats = cur.fetchall()

        cur.execute("""
            SELECT te.feature_name,
                te.test_case_name,
                te.latest_bucket_id,
                te.has_sticky_failure,
                te.is_currently_passing,
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
            WHERE te.run_id = %s
            ORDER BY te.test_case_name, ta.attempt_number ASC
            LIMIT %s OFFSET %s
        """, (rid, limit, skip))
        fails = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*) as total
            FROM test_executions te
            JOIN test_attempts ta ON te.id = ta.test_execution_id
            LEFT JOIN triage_signals ts ON ta.id = ts.test_attempt_id
            LEFT JOIN error_patterns ep ON ts.fingerprint = ep.fingerprint
            WHERE te.run_id = %s
        """, (rid,))
        total_count = cur.fetchone()['total']

        return {
            "cycle": {"cycle_id": identifier},
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
