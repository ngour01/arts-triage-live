"""
Data export — cycle-scoped patterns and failures with optional pagination and bucket filters.
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from psycopg2.extras import RealDictCursor

from app.database import get_conn

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("/{cycle_id}")
def export_cycle_to_json(
    cycle_id: str,
    limit: int = Query(default=500, ge=1, le=20000),
    skip: int = Query(default=0, ge=0),
    bucket_id: Optional[int] = Query(default=None),
    bucket_scope: Literal["signal", "execution"] = Query(
        default="signal",
        description="signal=pattern bucket; execution=test latest_bucket_id",
    ),
):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, status, total_tests FROM runs WHERE identifier = %s;",
                (cycle_id,),
            )
            run = cur.fetchone()
            if not run:
                raise HTTPException(status_code=404, detail="Cycle not found.")

            rid = run["id"]

            if bucket_id is not None:
                cur.execute("SELECT 1 FROM buckets WHERE id = %s", (bucket_id,))
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
                SELECT DISTINCT ep.fingerprint, ep.scrubbed_message AS scrubbed_pattern,
                       ep.error_class, ep.resolved_bucket_id AS bucket_id
                FROM error_patterns ep
                JOIN triage_signals ts ON ep.fingerprint = ts.fingerprint
                JOIN test_attempts ta ON ts.test_attempt_id = ta.id
                JOIN test_executions te ON ta.test_execution_id = te.id
                WHERE te.run_id = %s{bucket_filter}
                """,
                tuple(filter_params),
            )
            patterns = cur.fetchall()

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
                    ep.resolved_bucket_id as signal_bucket_id,
                    CASE WHEN te.latest_attempt_number = ta.attempt_number
                         THEN 1 ELSE 0 END AS is_latest
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
            failures = cur.fetchall()

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

            cur.execute("SELECT id, name FROM buckets ORDER BY id;")
            buckets = cur.fetchall()

    return {
        "cycle": {
            "cycle_id": cycle_id,
            "total_passed": 0,
            "total_failed": run["total_tests"],
            "total_invalid": 0,
        },
        "buckets": buckets,
        "patterns": patterns,
        "failures": failures,
        "filters": {
            "bucket_id": bucket_id,
            "bucket_scope": bucket_scope if bucket_id is not None else None,
        },
        "pagination": {
            "limit": limit,
            "skip": skip,
            "total_records": total_count,
            "has_more": (skip + limit) < total_count,
        },
    }
