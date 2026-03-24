import psycopg2
import json

DB_CONFIG = {
    "dbname": "art_triage",
    "user": "postgres",
    "password": "password",
    "host": "localhost",
    "port": "5432"
}

SEED_RULES = [
    # Bucket 1: User Errors
    {"conditions": {"msg_pattern": "INVALID TEST:"}, "bucket": 1},
    {"conditions": {"msg_pattern": r"\b40[0-9]\b"}, "bucket": 1},
    {"conditions": {"msg_pattern": "build-artifactory.eng.vmware.com"}, "bucket": 1},
    {"conditions": {"msg_pattern": "UNEXPECTED CHARACTER"}, "bucket": 1},
    {"conditions": {"msg_pattern": "UNEXPECTED TOKEN"}, "bucket": 1},
    {"conditions": {"msg_pattern": "syntax error, unexpected"}, "bucket": 1},
    {"conditions": {"err_class": "nimbususererror", "res_type": "test_error"}, "bucket": 1},

    # Bucket 2: Infra Errors
    {"conditions": {"result": "INVALID", "res_type": "infra_error", "err_class": "nimbusinfraruntimeerror"}, "bucket": 2},
    {"conditions": {"res_type": "infra_error"}, "bucket": 2},
    {"conditions": {"err_class": "nimbusinfraruntimeerror"}, "bucket": 2},
    {"conditions": {"msg_pattern": "FAILED TO GET IP", "res_type": "infra_error"}, "bucket": 2},
    {"conditions": {"msg_pattern": "INVALIDLOGIN"}, "bucket": 2},
    {"conditions": {"msg_pattern": "INVALIDGUESTLOGIN"}, "bucket": 2},
    {"conditions": {"msg_pattern": "PLATFORMCONFIGFAULT"}, "bucket": 2},
    {"conditions": {"msg_pattern": "CONNECTION REFUSED"}, "bucket": 2},
    {"conditions": {"msg_pattern": "CONNECTION TIMED OUT - CONNECT"}, "bucket": 2},
    {"conditions": {"msg_pattern": "NETWORK IS UNREACHABLE"}, "bucket": 2},
    {"conditions": {"msg_pattern": "SERVICE NOT UP"}, "bucket": 2},
    {"conditions": {"msg_pattern": "HOSTD ERROR"}, "bucket": 2},
    {"conditions": {"msg_pattern": "HOSTD SEEMS NOT UP"}, "bucket": 2},
    {"conditions": {"msg_pattern": "CANNOTCREATEFILE"}, "bucket": 2},
    {"conditions": {"msg_pattern": "INSUFFICIENTCPURESOURCESFAULT"}, "bucket": 2},
    {"conditions": {"msg_pattern": "FAILED TO DEPLOY WORKER"}, "bucket": 2},
    {"conditions": {"msg_pattern": "VIM CONNECTING FAILED AFTER RETRYING"}, "bucket": 2},

    # Bucket 5: Test Errors
    {"conditions": {"res_type": "test_error"}, "bucket": 5},
    {"conditions": {"err_class": "test error"}, "bucket": 5},
    {"conditions": {"err_class": "AssertionError"}, "bucket": 5},
    {"conditions": {"msg_pattern": "undefined local variable or method"}, "bucket": 5},
    {"conditions": {"msg_pattern": "NameError: uninitialized constant"}, "bucket": 5},

    # Bucket 4: Unknown Overrides
    {"conditions": {"msg_pattern": "WDC-PRD-RDOPS-TEMPLATES"}, "bucket": 4},
    {"conditions": {"msg_pattern": "IS NOT ALIVE AFTER TESTS DONE"}, "bucket": 4},
    {"conditions": {"msg_pattern": "ARTIFACTORY:80"}, "bucket": 4},
]


def seed():
    print("--> Connecting to Database...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("--> Wiping history and rules...")
        cur.execute(
            "TRUNCATE TABLE runs CASCADE; "
            "TRUNCATE TABLE error_patterns CASCADE; "
            "TRUNCATE TABLE master_rules RESTART IDENTITY CASCADE;"
        )
        for r in SEED_RULES:
            pattern_json_str = json.dumps(r['conditions'], sort_keys=True)
            cur.execute(
                "INSERT INTO master_rules (pattern_text, target_bucket_id, added_by, deleted_at) "
                "VALUES (%s, %s, 'System_Seeder', NULL)",
                (pattern_json_str, r['bucket'])
            )
        conn.commit()
        cur.close()
        conn.close()
        print(f"--> Success! Seeded {len(SEED_RULES)} rules.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    seed()
