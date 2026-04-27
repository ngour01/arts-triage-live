"""
Run lifecycle — create, update, list, per-run summary/stats, refresh snapshots.
"""

from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor

from app.database import get_conn, get_cursor
from app.deps import require_write_auth
from app.models import RunCreate, RunUpdate, RunResponse
from app.services.run_queries import fetch_run_stats

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("")
def list_runs():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, identifier, created_at, status, run_type, total_tests
                FROM runs
                ORDER BY created_at DESC NULLS LAST;
                """
            )
            return cur.fetchall()


@router.post("", response_model=RunResponse)
def create_or_get_run(
    payload: RunCreate,
    _: None = Depends(require_write_auth),
):
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO runs (run_type, identifier, status)
            VALUES (%s, %s, 'PROCESSING')
            ON CONFLICT (identifier) DO UPDATE SET status = 'PROCESSING'
            RETURNING id;
            """,
            (payload.run_type, payload.identifier),
        )
        run_id = cur.fetchone()[0]
    return {"id": run_id}


@router.get("/{identifier}/summary")
def run_summary(identifier: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM runs WHERE identifier = %s", (identifier,))
            run = cur.fetchone()
            if not run:
                raise HTTPException(status_code=404, detail="Run not found")

            rid = run["id"]

            cur.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN is_currently_passing THEN 1 ELSE 0 END), 0) as passing,
                    COALESCE(SUM(CASE WHEN NOT is_currently_passing THEN 1 ELSE 0 END), 0) as failing,
                    COALESCE(SUM(CASE WHEN has_sticky_failure THEN 1 ELSE 0 END), 0) as sticky_failures
                FROM test_executions WHERE run_id = %s
                """,
                (rid,),
            )
            counts = cur.fetchone()

            cur.execute(
                """
                SELECT b.id, b.name, b.is_sticky, COUNT(te.id) as count
                FROM buckets b
                LEFT JOIN test_executions te ON te.latest_bucket_id = b.id
                    AND te.run_id = %s
                    AND (NOT te.is_currently_passing OR te.has_sticky_failure)
                GROUP BY b.id, b.name, b.is_sticky
                ORDER BY b.id
                """,
                (rid,),
            )
            buckets = cur.fetchall()

            return {
                "run": {"id": rid, "identifier": identifier},
                "total": counts["total"] or 0,
                "passing": counts["passing"] or 0,
                "failing": counts["failing"] or 0,
                "sticky_failures": counts["sticky_failures"] or 0,
                "buckets": buckets,
            }


@router.get("/{identifier}/stats")
def run_stats(identifier: str):
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM runs WHERE identifier = %s", (identifier,))
            run = cur.fetchone()
            if not run:
                raise HTTPException(status_code=404, detail="Run not found")
            rid = run[0]
            return fetch_run_stats(cur, rid, identifier)
        finally:
            cur.close()


@router.post("/{identifier}/refresh")
def refresh_run(
    identifier: str,
    _: None = Depends(require_write_auth),
):
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM runs WHERE identifier = %s", (identifier,))
            run = cur.fetchone()
            if not run:
                raise HTTPException(status_code=404, detail="Run not found")
            rid = run[0]

            cur.execute(
                """
                INSERT INTO run_stats_snapshots (run_id, bucket_id, test_count, feature_count, suite_count)
                SELECT %(rid)s, b.id,
                    COUNT(DISTINCT te.id),
                    COUNT(DISTINCT te.feature_name),
                    COUNT(DISTINCT te.feature_name)
                FROM buckets b
                LEFT JOIN test_executions te
                    ON te.latest_bucket_id = b.id
                    AND te.run_id = %(rid)s
                    AND NOT te.is_currently_passing
                GROUP BY b.id
                ON CONFLICT (run_id, bucket_id) DO UPDATE SET
                    test_count = EXCLUDED.test_count,
                    feature_count = EXCLUDED.feature_count,
                    suite_count = EXCLUDED.suite_count,
                    captured_at = CURRENT_TIMESTAMP
                """,
                {"rid": rid},
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

    return {"status": "refreshed", "run_id": identifier}


@router.put("/{run_id}")
def update_run(
    run_id: int,
    payload: RunUpdate,
    _: None = Depends(require_write_auth),
):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE runs SET status = %s, total_tests = %s WHERE id = %s;",
            (payload.status, payload.total_tests, run_id),
        )
    return {"success": True}
