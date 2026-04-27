"""Per-run aggregates for summary and stats endpoints (aligned with arts-triage-live)."""


def fetch_run_stats(cur, rid: int, identifier: str) -> dict:
    """Totals, per-bucket counts, triage signals, and unique bug ids for one run."""
    cur.execute(
        """
        SELECT
            COUNT(*)::int AS total,
            COALESCE(SUM(CASE WHEN is_currently_passing THEN 1 ELSE 0 END), 0)::int AS passing,
            COALESCE(SUM(CASE WHEN NOT is_currently_passing THEN 1 ELSE 0 END), 0)::int AS failing,
            COALESCE(SUM(CASE WHEN has_sticky_failure THEN 1 ELSE 0 END), 0)::int AS sticky_failures
        FROM test_executions WHERE run_id = %s
        """,
        (rid,),
    )
    exe = cur.fetchone()
    total, passing, failing, sticky_failures = exe[0], exe[1], exe[2], exe[3]

    cur.execute(
        """
        SELECT COUNT(*)::int FROM test_attempts ta
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s
        """,
        (rid,),
    )
    attempt_count = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)::int FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s
        """,
        (rid,),
    )
    signal_total = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)::int FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s
          AND ts.bug_id IS NOT NULL AND TRIM(ts.bug_id) <> ''
        """,
        (rid,),
    )
    signals_with_bug = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(DISTINCT ts.fingerprint)::int FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s
        """,
        (rid,),
    )
    unique_fingerprints = cur.fetchone()[0]

    cur.execute(
        """
        SELECT b.id, b.name, b.is_sticky,
               COUNT(te.id)::int AS failing_or_sticky_executions
        FROM buckets b
        LEFT JOIN test_executions te ON te.latest_bucket_id = b.id
            AND te.run_id = %s
            AND (NOT te.is_currently_passing OR te.has_sticky_failure)
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
        WHERE te.run_id = %s
        GROUP BY ep.resolved_bucket_id
        """,
        (rid,),
    )
    sig_by_b = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute(
        """
        SELECT ep.resolved_bucket_id AS bucket_id, TRIM(ts.bug_id) AS bug_id
        FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        JOIN error_patterns ep ON ts.fingerprint = ep.fingerprint
        WHERE te.run_id = %s
          AND ts.bug_id IS NOT NULL AND TRIM(ts.bug_id) <> ''
        GROUP BY ep.resolved_bucket_id, TRIM(ts.bug_id)
        ORDER BY TRIM(ts.bug_id)
        """,
        (rid,),
    )
    bugs_by_bucket: dict = {}
    for r in cur.fetchall():
        bid = r[0]
        bugs_by_bucket.setdefault(bid, []).append(r[1])

    cur.execute(
        """
        SELECT DISTINCT TRIM(ts.bug_id) AS bug_id
        FROM triage_signals ts
        JOIN test_attempts ta ON ts.test_attempt_id = ta.id
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE te.run_id = %s
          AND ts.bug_id IS NOT NULL AND TRIM(ts.bug_id) <> ''
        ORDER BY 1
        """,
        (rid,),
    )
    unique_bug_ids = [r[0] for r in cur.fetchall()]

    buckets_out = []
    for row in bucket_rows:
        bid = row[0]
        bugs = sorted(bugs_by_bucket.get(bid, []))
        buckets_out.append(
            {
                "id": bid,
                "name": row[1],
                "is_sticky": row[2],
                "failing_or_sticky_executions": row[3],
                "signal_count": sig_by_b.get(bid, 0),
                "unique_bug_ids": bugs,
                "unique_bug_count": len(bugs),
            }
        )

    return {
        "run": {"id": rid, "identifier": identifier},
        "totals": {
            "test_executions": total,
            "passing": passing,
            "failing": failing,
            "sticky_failures": sticky_failures,
            "test_attempts": attempt_count,
            "triage_signals": signal_total,
            "signals_with_bug": signals_with_bug,
            "unique_bug_count": len(unique_bug_ids),
            "unique_error_patterns": unique_fingerprints,
        },
        "buckets": buckets_out,
        "unique_bug_ids": unique_bug_ids,
    }


def get_run_id_by_identifier(cur, identifier: str) -> int | None:
    cur.execute("SELECT id FROM runs WHERE identifier = %s;", (identifier,))
    row = cur.fetchone()
    return row[0] if row else None
