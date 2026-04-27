"""
Seed the master_rules table with the multi-condition JSON classification rules.

Usage:
    python -m scripts.seed_rules          (from backend/)
    python backend/scripts/seed_rules.py  (from repo root)
"""

import os
import sys
import json
import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.config import get_settings

SEED_RULES = [
    # --- BUCKET 1: USER ERRORS ---
    {"conditions": {"msg_pattern": "INVALID TEST:"}, "bucket": 1, "action": "Fix User Config/Setup"},
    {"conditions": {"msg_pattern": r"\b40[0-9]\b"}, "bucket": 1, "action": "Fix test file, HTTP 40x error"},
    {"conditions": {"msg_pattern": "build-artifactory.eng.vmware.com"}, "bucket": 1, "action": "Replace with packages.vcfd..."},
    {"conditions": {"msg_pattern": "UNEXPECTED CHARACTER"}, "bucket": 1, "action": "Fix json/ruby file syntax"},
    {"conditions": {"msg_pattern": "UNEXPECTED TOKEN"}, "bucket": 1, "action": "Fix json/ruby file syntax"},
    {"conditions": {"msg_pattern": "syntax error, unexpected"}, "bucket": 1, "action": "Fix test script syntax"},
    {"conditions": {"err_class": "nimbususererror", "res_type": "test_error"}, "bucket": 1, "action": "Fix User Config/Setup"},

    # --- BUCKET 2: INFRA ERRORS ---
    {"conditions": {"result": "INVALID", "res_type": "infra_error", "err_class": "nimbusinfraruntimeerror"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"res_type": "infra_error"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"err_class": "nimbusinfraruntimeerror"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"msg_pattern": "FAILED TO GET IP", "res_type": "infra_error"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"msg_pattern": "INVALIDLOGIN"}, "bucket": 2, "action": "Fix Credentials (Re-run)"},
    {"conditions": {"msg_pattern": "INVALIDGUESTLOGIN"}, "bucket": 2, "action": "Re-run Workload (Guest Auth)"},
    {"conditions": {"msg_pattern": "PLATFORMCONFIGFAULT"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"msg_pattern": "CONNECTION REFUSED"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"msg_pattern": "CONNECTION TIMED OUT - CONNECT"}, "bucket": 2, "action": "Re-run Workload (Network Drop)"},
    {"conditions": {"msg_pattern": "NETWORK IS UNREACHABLE"}, "bucket": 2, "action": "Re-run Workload (Network Drop)"},
    {"conditions": {"msg_pattern": "SERVICE NOT UP"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"msg_pattern": "HOSTD ERROR"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"msg_pattern": "HOSTD SEEMS NOT UP"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"msg_pattern": "CANNOTCREATEFILE"}, "bucket": 2, "action": "Re-run Workload (Datastore Issue)"},
    {"conditions": {"msg_pattern": "INSUFFICIENTCPURESOURCESFAULT"}, "bucket": 2, "action": "Re-run (Capacity Issue)"},
    {"conditions": {"msg_pattern": "FAILED TO DEPLOY WORKER"}, "bucket": 2, "action": "Re-run Workload (Infra Transient)"},
    {"conditions": {"msg_pattern": "VIM CONNECTING FAILED AFTER RETRYING"}, "bucket": 2, "action": "Re-run Workload (VIM Service)"},

    # --- BUCKET 5: TEST ERRORS ---
    {"conditions": {"res_type": "test_error"}, "bucket": 5, "action": "Bug to User (Fix Test Logic)"},
    {"conditions": {"err_class": "test error"}, "bucket": 5, "action": "Bug to User (Fix Test Logic)"},
    {"conditions": {"err_class": "AssertionError"}, "bucket": 5, "action": "Bug to User (Assertion Failed)"},
    {"conditions": {"msg_pattern": "undefined local variable or method"}, "bucket": 5, "action": "Bug to User (Fix Test Logic)"},
    {"conditions": {"msg_pattern": "NameError: uninitialized constant"}, "bucket": 5, "action": "Bug to User (Fix Test Logic)"},

    # --- BUCKET 4: SPECIFIC UNKNOWN OVERRIDES ---
    {"conditions": {"msg_pattern": "WDC-PRD-RDOPS-TEMPLATES"}, "bucket": 4, "action": "File User Bug (Re-run)"},
    {"conditions": {"msg_pattern": "IS NOT ALIVE AFTER TESTS DONE"}, "bucket": 4, "action": "File User Bug (Re-run)"},
    {"conditions": {"msg_pattern": "ARTIFACTORY:80"}, "bucket": 4, "action": "File User Bug (Re-run)"},
]


def seed_database(full_cleanup: bool = True):
    settings = get_settings()
    print(f"--> Connecting to {settings.database_url} ...")

    try:
        conn = psycopg2.connect(dsn=settings.database_url)
        cur = conn.cursor()

        if full_cleanup:
            print("--> Full cleanup: wiping cycles, patterns, and rules...")
            cur.execute("""
                TRUNCATE TABLE triage_signals CASCADE;
                TRUNCATE TABLE error_patterns CASCADE;
                TRUNCATE TABLE test_attempts CASCADE;
                TRUNCATE TABLE test_executions CASCADE;
                TRUNCATE TABLE runs CASCADE;
                TRUNCATE TABLE master_rules RESTART IDENTITY CASCADE;
            """)
            conn.commit()

        print("--> Inserting seed rules...")
        inserted = 0
        for rule in SEED_RULES:
            try:
                pattern_json = json.dumps(rule["conditions"], sort_keys=True)
                cur.execute(
                    """
                    INSERT INTO master_rules (pattern_text, target_bucket_id, specific_action, added_by)
                    VALUES (%s, %s, %s, 'System_Seeder')
                    ON CONFLICT (pattern_text) DO NOTHING;
                    """,
                    (pattern_json, rule["bucket"], rule["action"]),
                )
                inserted += 1
            except Exception as e:
                print(f"  Error inserting rule {rule['conditions']}: {e}")
                conn.rollback()

        conn.commit()
        cur.close()
        conn.close()
        print(f"--> Success! Inserted {inserted} rules.")
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    seed_database(full_cleanup=True)
