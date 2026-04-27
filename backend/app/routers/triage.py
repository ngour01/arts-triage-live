"""
Triage endpoints — ingest, discover, URL fetch, signal updates.
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import List

import requests
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_conn
from app.deps import require_write_auth
from app.models import (
    AttemptPayload,
    AttemptResult,
    BatchPayload,
    BatchResult,
    DiscoverRequest,
    SignalBugUpdate,
    TriageUrlRequest,
)
from app.services import triage_service
from app.services.ingest import process_attempt_row
from app.services.run_queries import fetch_run_stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.crawler_utils import discover_payloads

logger = logging.getLogger("arts.triage")

router = APIRouter(prefix="/api/v1/triage", tags=["triage"])


@router.post("/attempt", response_model=AttemptResult)
def process_attempt(
    payload: AttemptPayload,
    _: None = Depends(require_write_auth),
):
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            result = process_attempt_row(cur, payload)
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            cur.close()


@router.post("/batch", response_model=BatchResult)
def process_batch(
    payload: BatchPayload,
    _: None = Depends(require_write_auth),
):
    results: List[AttemptResult] = []
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            for attempt in payload.attempts:
                result = process_attempt_row(cur, attempt)
                results.append(result)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            cur.close()
    return BatchResult(processed=len(results), results=results)


@router.post("/url")
def triage_url(
    req: TriageUrlRequest,
    _: None = Depends(require_write_auth),
):
    run_name = req.run_identifier or f"QUICK_{datetime.now().strftime('%m%d_%H%M')}"
    try:
        data = requests.get(req.log_url, timeout=10).json()
    except Exception as e:
        logger.warning("Failed to fetch log URL %s: %s", req.log_url, e)
        raise HTTPException(status_code=400, detail="Invalid Log URL")

    skipped_duplicate = False
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO runs (run_type, identifier, status)
                VALUES ('CYCLE', %s, 'PROCESSING')
                ON CONFLICT (identifier) DO UPDATE SET status = 'PROCESSING'
                RETURNING id;
                """,
                (run_name,),
            )
            rid = cur.fetchone()[0]

            cur.execute(
                """
                SELECT status FROM test_attempts ta
                JOIN test_executions te ON ta.test_execution_id = te.id
                WHERE ta.log_url = %s AND te.run_id = %s
                """,
                (req.log_url, rid),
            )
            row = cur.fetchone()
            if row and row[0].upper() in ("PASS", "FAIL"):
                skipped_duplicate = True
            else:
                status = str(data.get("result", "IN_PROGRESS")).upper()
                payload = AttemptPayload(
                    run_id=rid,
                    feature_name=str(data.get("display_name", "Manual")),
                    test_case_name=str(data.get("test_case", "Test")),
                    log_url=req.log_url,
                    status=status,
                    result=status,
                    json_error_message=str(data.get("error_message", "N/A")),
                )
                process_attempt_row(cur, payload)

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            cur.close()

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM runs WHERE identifier = %s;", (run_name,))
            rid = cur.fetchone()[0]
            stats = fetch_run_stats(cur, rid, run_name)
            conn.commit()
        finally:
            cur.close()

    if skipped_duplicate:
        return {"status": "exists", "run_id": run_name, "stats": stats}
    return {"status": "success", "run_id": run_name, "stats": stats}


@router.post("/discover")
def triage_discover(
    req: DiscoverRequest,
    _: None = Depends(require_write_auth),
):
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO runs (run_type, identifier, status)
                VALUES ('CYCLE', %s, 'PROCESSING')
                ON CONFLICT (identifier) DO UPDATE SET status = 'PROCESSING'
                RETURNING id;
                """,
                (req.run_identifier,),
            )
            run_id = cur.fetchone()[0]
            conn.commit()
        finally:
            cur.close()

    payloads = discover_payloads(req.url, run_id, feature_name=req.feature_name)
    if not payloads:
        raise HTTPException(
            status_code=422,
            detail="No stateDump.json.txt files found at the provided URL.",
        )

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            for p_dict in payloads:
                p = AttemptPayload(**p_dict)
                process_attempt_row(cur, p)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            cur.close()

    with get_conn() as conn:
        cur = conn.cursor()
        try:
            stats = fetch_run_stats(cur, run_id, req.run_identifier)
            conn.commit()
        finally:
            cur.close()

    logger.info("Discover ingest: %d test(s) → run '%s'", len(payloads), req.run_identifier)
    return {
        "status": "ok",
        "run_identifier": req.run_identifier,
        "ingested": len(payloads),
        "stats": stats,
        "tests": [
            {
                "feature": p["feature_name"],
                "test_case": p["test_case_name"],
                "status": p["status"],
                "log_url": p["log_url"],
            }
            for p in payloads
        ],
    }


@router.patch("/signals")
def update_signal_bug(
    req: SignalBugUpdate,
    _: None = Depends(require_write_auth),
):
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id FROM triage_signals
                WHERE test_attempt_id = %s AND fingerprint = %s
                """,
                (req.test_attempt_id, req.fingerprint),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Signal not found")

            cur.execute(
                """
                UPDATE triage_signals SET bug_id = %s
                WHERE test_attempt_id = %s AND fingerprint = %s
                """,
                (req.bug_id, req.test_attempt_id, req.fingerprint),
            )
            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            cur.close()

    return {"status": "ok", "bug_id": req.bug_id}


# Rules live under /api/v1/rules — see rules.py router
