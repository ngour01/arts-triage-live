"""
Core attempt ingestion: upsert by (run_id, log_url), multi-signal best-bucket selection.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from shared.scrub import scrub_message

from app.models import AttemptPayload, AttemptResult
from app.services import triage_service, fingerprint_service
from app.services.triage_service import BUCKET_PRIORITY


def process_attempt_row(cur, payload: AttemptPayload) -> AttemptResult:
    """Insert or update one test attempt and triage signals."""
    buckets_meta = triage_service.get_buckets_meta()

    cur.execute(
        """
        INSERT INTO test_executions (run_id, feature_name, test_case_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (run_id, feature_name, test_case_name)
        DO UPDATE SET id = test_executions.id
        RETURNING id, latest_attempt_number, has_sticky_failure;
        """,
        (payload.run_id, payload.feature_name, payload.test_case_name),
    )
    row = cur.fetchone()
    exec_id, last_att, was_sticky = row[0], row[1], row[2]

    cur.execute(
        """
        SELECT ta.id, ta.attempt_number
        FROM test_attempts ta
        JOIN test_executions te ON ta.test_execution_id = te.id
        WHERE ta.log_url = %s AND te.run_id = %s;
        """,
        (payload.log_url, payload.run_id),
    )
    existing = cur.fetchone()

    status_upper = (payload.status or "").upper()
    if existing:
        att_id, att_num = existing[0], existing[1]
        cur.execute(
            "UPDATE test_attempts SET status = %s WHERE id = %s;",
            (payload.status, att_id),
        )
    else:
        att_num = (last_att or 0) + 1
        cur.execute(
            """
            INSERT INTO test_attempts (test_execution_id, attempt_number, status, log_url)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (exec_id, att_num, payload.status, payload.log_url),
        )
        att_id = cur.fetchone()[0]

    is_passing = status_upper == "PASS"
    latest_bucket_id = None
    sticky = was_sticky

    if not is_passing and status_upper != "IN_PROGRESS":
        has_atomic = len(payload.atomic_signals) > 0
        errors_to_process = payload.atomic_signals if has_atomic else [payload.json_error_message]

        best_bucket_id = 4
        best_priority = BUCKET_PRIORITY.get(4, 99)

        for raw_msg in errors_to_process:
            scrubbed_msg = scrub_message(raw_msg)
            bucket_id, _ = triage_service.classify(
                scrubbed_msg,
                payload.error_class,
                payload.result_type,
                payload.result,
                has_atomic,
            )
            sig_priority = BUCKET_PRIORITY.get(bucket_id, 99)
            if sig_priority < best_priority:
                best_priority = sig_priority
                best_bucket_id = bucket_id

            fingerprint = fingerprint_service.generate_fingerprint(
                payload.error_class, scrubbed_msg, bucket_id
            )

            cur.execute(
                """
                INSERT INTO error_patterns
                    (fingerprint, scrubbed_message, error_class, resolved_bucket_id, resolved_action)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (fingerprint) DO UPDATE SET
                    resolved_bucket_id = EXCLUDED.resolved_bucket_id,
                    resolved_action    = EXCLUDED.resolved_action,
                    last_seen          = CURRENT_TIMESTAMP,
                    global_hit_count   = error_patterns.global_hit_count + 1;
                """,
                (fingerprint, scrubbed_msg, payload.error_class, bucket_id, None),
            )
            cur.execute(
                """
                INSERT INTO triage_signals (test_attempt_id, fingerprint)
                VALUES (%s, %s)
                ON CONFLICT (test_attempt_id, fingerprint) DO NOTHING;
                """,
                (att_id, fingerprint),
            )
            if buckets_meta[bucket_id]["is_sticky"]:
                sticky = True

        latest_bucket_id = best_bucket_id
    elif is_passing and was_sticky:
        cur.execute(
            "SELECT latest_bucket_id FROM test_executions WHERE id = %s;",
            (exec_id,),
        )
        prev = cur.fetchone()
        latest_bucket_id = prev[0] if prev else None

    cur.execute(
        """
        UPDATE test_executions
        SET latest_attempt_number = %s,
            is_currently_passing  = %s,
            has_sticky_failure    = %s,
            latest_bucket_id      = %s
        WHERE id = %s;
        """,
        (att_num, is_passing, sticky, latest_bucket_id, exec_id),
    )

    status_label = "PASS" if is_passing else f"FAIL (Bucket {latest_bucket_id})"
    return AttemptResult(success=True, attempt_num=att_num, status=status_label)
