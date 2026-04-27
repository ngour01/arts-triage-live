"""
Decoupled Waterfall Triage Engine.

Loads classification rules from the database once at startup, sorts them
by the strict waterfall priority, and exposes a pure-function classifier
with no database dependency at call time.

Buckets carry only id, name, and stickiness. No remediation action is returned.

Priority order:  Product(3) > Timeout(6) > Infra(2) > User(1) > Test(5) > Unknown(4)
"""

import json
import re
from typing import Optional, Tuple

from psycopg2.extras import RealDictCursor

# Waterfall priority — lower number = higher priority
BUCKET_PRIORITY = {3: 1, 6: 2, 2: 3, 1: 4, 5: 5, 4: 6}

_rules: list[dict] = []
_buckets_meta: dict[int, dict] = {}


def load_intelligence(conn) -> None:
    """Load buckets and rules from DB, sort rules by waterfall priority."""
    global _rules, _buckets_meta

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name, is_sticky FROM buckets;")
        _buckets_meta = {row["id"]: dict(row) for row in cur.fetchall()}

        cur.execute("SELECT id, target_bucket_id, pattern_text FROM master_rules;")
        _rules = [dict(r) for r in cur.fetchall()]

    _rules.sort(key=lambda r: BUCKET_PRIORITY.get(r["target_bucket_id"], 99))


def get_buckets_meta() -> dict[int, dict]:
    return _buckets_meta


def classify(
    scrubbed_msg: str,
    error_class: str,
    result_type: str,
    result_status: str,
    is_atomic: bool,
) -> Tuple[int, Optional[str]]:
    """Run the waterfall classification against the loaded rule set.

    Returns (bucket_id, action). Action is always None.
    """
    msg_upper = scrubbed_msg.upper()
    res_type = result_type.lower()
    res_status = result_status.upper()
    err_class = error_class.lower()

    # Failsafe 1 — absolute product crashes
    if is_atomic or "PSOD" in msg_upper or "CORE" in msg_upper or "FIRSTBOOT ERROR" in msg_upper:
        bucket_id = 3
        return bucket_id, None

    # Failsafe 2 — strict timeouts
    if (
        res_status == "TIMEOUT"
        and res_type == "test_error"
        and "TEST IS STILL RUNNING BEFORE TIMEOUT" in msg_upper
    ):
        bucket_id = 6
        return bucket_id, None

    # Waterfall — multi-condition JSON rules
    for rule in _rules:
        try:
            conditions = json.loads(rule["pattern_text"])
        except json.JSONDecodeError:
            conditions = {"msg_pattern": rule["pattern_text"]}

        matched = True
        if "msg_pattern" in conditions:
            if not re.search(conditions["msg_pattern"], scrubbed_msg, re.IGNORECASE):
                matched = False
        if "result" in conditions:
            if not re.search(conditions["result"], res_status, re.IGNORECASE):
                matched = False
        if "res_type" in conditions:
            if not re.search(conditions["res_type"], res_type, re.IGNORECASE):
                matched = False
        if "err_class" in conditions:
            if not re.search(conditions["err_class"], err_class, re.IGNORECASE):
                matched = False

        if matched:
            target_bucket = rule["target_bucket_id"]
            return target_bucket, None

    # Fallback — Unknown
    bucket_id = 4
    return bucket_id, None
