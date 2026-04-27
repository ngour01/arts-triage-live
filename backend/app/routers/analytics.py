"""
Analytics endpoints — pre-computed dashboard data with Redis caching.
"""

from typing import List

from fastapi import APIRouter, Query

from app.database import get_cursor
from app.models import SummaryResponse, BucketVolume, TriageProgressDay
from app.services import cache_service

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary", response_model=SummaryResponse)
def get_summary(days: int = Query(default=30, ge=1, le=365)):
    cache_key = f"analytics:summary:{days}"
    cached = cache_service.get_cached(cache_key)
    if cached:
        return cached

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE NOT is_currently_passing OR has_sticky_failure)
                    AS total_failures,
                COUNT(*) FILTER (
                    WHERE latest_bucket_id IS NOT NULL
                    AND latest_bucket_id != 4
                    AND (NOT is_currently_passing OR has_sticky_failure)
                ) AS auto_triaged,
                COUNT(*) FILTER (
                    WHERE latest_bucket_id = 3
                    AND (NOT is_currently_passing OR has_sticky_failure)
                ) AS active_product_bugs
            FROM test_executions;
            """
        )
        row = cur.fetchone()

    total = row["total_failures"] or 0
    triaged = row["auto_triaged"] or 0
    pct = round((triaged / total * 100), 1) if total > 0 else 0.0

    trends = _compute_trends(days)

    result = {
        "total_failures": total,
        "auto_triaged_pct": pct,
        "active_product_bugs": row["active_product_bugs"] or 0,
        "trends": trends,
    }
    cache_service.set_cached(cache_key, result)
    return result


def _compute_trends(days: int) -> dict:
    """Compare current period vs previous period of the same length."""
    try:
        with get_cursor(dict_cursor=True) as cur:
            cur.execute(
                """
                WITH current_period AS (
                    SELECT
                        COUNT(DISTINCT ta.test_execution_id) AS total,
                        COUNT(DISTINCT ta.test_execution_id) FILTER (
                            WHERE te.latest_bucket_id IS NOT NULL AND te.latest_bucket_id != 4
                        ) AS triaged,
                        COUNT(DISTINCT ta.test_execution_id) FILTER (
                            WHERE te.latest_bucket_id = 3
                        ) AS product_bugs
                    FROM test_attempts ta
                    JOIN test_executions te ON te.id = ta.test_execution_id
                    WHERE ta.created_at >= NOW() - INTERVAL '%s days'
                ),
                previous_period AS (
                    SELECT
                        COUNT(DISTINCT ta.test_execution_id) AS total,
                        COUNT(DISTINCT ta.test_execution_id) FILTER (
                            WHERE te.latest_bucket_id IS NOT NULL AND te.latest_bucket_id != 4
                        ) AS triaged,
                        COUNT(DISTINCT ta.test_execution_id) FILTER (
                            WHERE te.latest_bucket_id = 3
                        ) AS product_bugs
                    FROM test_attempts ta
                    JOIN test_executions te ON te.id = ta.test_execution_id
                    WHERE ta.created_at >= NOW() - INTERVAL '%s days'
                      AND ta.created_at < NOW() - INTERVAL '%s days'
                )
                SELECT
                    c.total AS c_total, c.triaged AS c_triaged, c.product_bugs AS c_bugs,
                    p.total AS p_total, p.triaged AS p_triaged, p.product_bugs AS p_bugs
                FROM current_period c, previous_period p;
                """,
                (days, days * 2, days),
            )
            r = cur.fetchone()

        def pct_change(current, previous):
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            return round(((current - previous) / previous) * 100, 1)

        return {
            "total_failures_trend": pct_change(r["c_total"], r["p_total"]),
            "auto_triaged_trend": pct_change(r["c_triaged"], r["p_triaged"]),
            "product_bugs_trend": pct_change(r["c_bugs"], r["p_bugs"]),
        }
    except Exception:
        return {
            "total_failures_trend": 0.0,
            "auto_triaged_trend": 0.0,
            "product_bugs_trend": 0.0,
        }


@router.get("/volume-by-bucket", response_model=List[BucketVolume])
def get_volume_by_bucket(days: int = Query(default=30, ge=1, le=365)):
    cache_key = f"analytics:volume:{days}"
    cached = cache_service.get_cached(cache_key)
    if cached:
        return cached

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT b.id AS bucket_id, b.name AS bucket_name,
                   COUNT(te.id) AS count
            FROM buckets b
            LEFT JOIN test_executions te
                ON te.latest_bucket_id = b.id
                AND (NOT te.is_currently_passing OR te.has_sticky_failure)
                AND te.id IN (
                    SELECT test_execution_id FROM test_attempts
                    WHERE created_at >= NOW() - INTERVAL '%s days'
                )
            GROUP BY b.id, b.name
            ORDER BY b.id;
            """,
            (days,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    cache_service.set_cached(cache_key, rows)
    return rows


@router.get("/triage-progress", response_model=List[TriageProgressDay])
def get_triage_progress(days: int = Query(default=30, ge=1, le=365)):
    cache_key = f"analytics:progress:{days}"
    cached = cache_service.get_cached(cache_key)
    if cached:
        return cached

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            """
            SELECT
                d.dt::date AS date,
                COUNT(ta.id) FILTER (WHERE te.latest_bucket_id IS NOT NULL AND te.latest_bucket_id != 4)
                    AS triaged,
                COUNT(ta.id) FILTER (WHERE te.latest_bucket_id IS NULL OR te.latest_bucket_id = 4)
                    AS untriaged
            FROM generate_series(
                NOW() - INTERVAL '%s days', NOW(), '1 day'
            ) AS d(dt)
            LEFT JOIN test_attempts ta
                ON ta.created_at::date = d.dt::date
            LEFT JOIN test_executions te
                ON te.id = ta.test_execution_id
            GROUP BY d.dt::date
            ORDER BY d.dt::date;
            """,
            (days,),
        )
        rows = [
            {"date": str(r["date"]), "triaged": r["triaged"], "untriaged": r["untriaged"]}
            for r in cur.fetchall()
        ]

    cache_service.set_cached(cache_key, rows)
    return rows
