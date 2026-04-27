"""
Seed realistic demo data for the dashboard charts.

Generates 30 days of triage data across all 6 buckets so the
BarChart, AreaChart, and MetricsBar have meaningful content.

Usage:
    python -m scripts.seed_demo_data   (from backend/)
"""

import os
import sys
import random
from datetime import datetime, timedelta, timezone

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.config import get_settings
from app.services.fingerprint_service import generate_fingerprint

DEMO_FAILURES = [
    # (feature, test_case, error_class, message, bucket_id, action)
    ("vSANEncryption", "testEncryptionKeyRotation", "product error", "PSOD: Failed at bora/modules/vmkernel/rdt/rdt-iopath.c:6907", 3, "File Product Bug"),
    ("vSANEncryption", "testEncryptionRekey", "product error", "core file name: vmkernel-zdump.1", 3, "File Product Bug"),
    ("vSANLifecycle", "testRollingUpgrade", "NimbusFirstBootError", "Firstboot Error: VCVA Firstboot failure: Failed firstboot: vpxd", 3, "File Product Bug"),
    ("vSANPerformance", "testIOPSBaseline", "product error", "PSOD: Metadata inconsistency detected.", 3, "File Product Bug"),
    ("vSANStretched", "testWitnessFailover", "product error", "PSOD: RAID1/RAID-EC inconsistency detected.", 3, "File Product Bug"),
    ("vSANNetworking", "testVMknicFailover", "NimbusInfraRuntimeError", "Connection refused - connect(2) for <IP>:22", 2, "Re-run Workload (Infra Transient)"),
    ("vSANNetworking", "testMulticastSetup", "Errno::ECONNREFUSED", "Connection refused on port 443", 2, "Re-run Workload (Infra Transient)"),
    ("vSANDeployment", "testClusterDeploy", "NimbusInfraRuntimeError", "PlatformConfigFault: An error occurred during host configuration", 2, "Re-run Workload (Infra Transient)"),
    ("vSANDeployment", "testHostAdd", "NimbusExceptionNoIp", "<HOST>: Failed to get IP", 2, "Re-run Workload (Infra Transient)"),
    ("vSANDeployment", "testVCDeploy", "NimbusInfraRuntimeError", "InsufficientCpuResourcesFault", 2, "Re-run (Capacity Issue)"),
    ("vSANStorage", "testDiskGroupCreate", "NimbusInfraRuntimeError", "Hostd Error: hostd seems not up at <IP>", 2, "Re-run Workload (Infra Transient)"),
    ("vSANDataMigration", "testEvacuation", "NimbusInfraRuntimeError", "VIM connecting failed after retrying 5 times", 2, "Re-run Workload (VIM Service)"),
    ("vSANBasicOps", "testVMCreate", "NimbusExceptionInvalidTest", "Invalid test: <TEST_SPEC>", 1, "Fix User Config/Setup"),
    ("vSANBasicOps", "testVMPowerOn", "OpenURI::HTTPError", "404 Not Found", 1, "Fix test file, HTTP 40x error"),
    ("vSANBasicOps", "testVMClone", "OpenURI::HTTPError", "401 Unauthorized", 1, "Fix test file, HTTP 40x error"),
    ("vSANUpgrade", "testPatchInstall", "test error", "syntax error, unexpected end-of-input", 1, "Fix test script syntax"),
    ("vSANFaultDomain", "testDomainRebalance", "test error", "Test error", 5, "Bug to User (Fix Test Logic)"),
    ("vSANFaultDomain", "testDomainIsolation", "AssertionError", "Expected 3 but got 2", 5, "Bug to User (Assertion Failed)"),
    ("vSANCompression", "testCompressionRatio", "test error", "undefined local variable or method 'ratio'", 5, "Bug to User (Fix Test Logic)"),
    ("vSANDedup", "testDedupSavings", "test error", "NameError: uninitialized constant DedupHelper", 5, "Bug to User (Fix Test Logic)"),
    ("vSANiSCSI", "testTargetCreate", "test error", "Test is still running before timeout", 6, "Increase test timeout"),
    ("vSANiSCSI", "testLUNExpand", "test error", "Test is still running before timeout", 6, "Increase test timeout"),
    ("vSANFileService", "testNFSShare", "NimbusTestbedLivenessError", "Testbed is not alive after tests done", 4, "File User Bug (Re-run)"),
    ("vSANFileService", "testSMBMount", "Net::OpenTimeout", "Failed to open TCP connection to artifactory:80", 4, "File User Bug (Re-run)"),
]


def seed_demo():
    settings = get_settings()
    print(f"--> Seeding demo data into {settings.database_url} ...")

    conn = psycopg2.connect(dsn=settings.database_url)
    cur = conn.cursor()

    cur.execute("INSERT INTO runs (run_type, identifier, status, total_tests) VALUES ('CYCLE', 'demo-cycle', 'COMPLETED', %s) ON CONFLICT (identifier) DO UPDATE SET total_tests = EXCLUDED.total_tests RETURNING id;", (len(DEMO_FAILURES),))
    run_id = cur.fetchone()[0]
    conn.commit()

    now = datetime.now(timezone.utc)
    inserted = 0

    for i, (feature, test_case, err_class, message, bucket_id, action) in enumerate(DEMO_FAILURES):
        days_ago = random.randint(0, 29)
        created_at = now - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))

        cur.execute("""
            INSERT INTO test_executions (run_id, feature_name, test_case_name, latest_attempt_number, is_currently_passing, has_sticky_failure, latest_bucket_id)
            VALUES (%s, %s, %s, 1, FALSE, %s, %s)
            ON CONFLICT (run_id, feature_name, test_case_name) DO UPDATE SET latest_bucket_id = EXCLUDED.latest_bucket_id
            RETURNING id;
        """, (run_id, feature, test_case, bucket_id == 3, bucket_id))
        exec_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO test_attempts (test_execution_id, attempt_number, status, log_url, created_at)
            VALUES (%s, 1, 'FAIL', %s, %s)
            RETURNING id;
        """, (exec_id, f"https://uts-logs.example.com/{feature}/{test_case}/stateDump.json.txt", created_at))
        attempt_id = cur.fetchone()[0]

        fingerprint = generate_fingerprint(err_class, message, bucket_id)

        cur.execute("""
            INSERT INTO error_patterns (fingerprint, scrubbed_message, error_class, resolved_bucket_id, resolved_action)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (fingerprint) DO UPDATE SET
                last_seen = CURRENT_TIMESTAMP,
                global_hit_count = error_patterns.global_hit_count + 1;
        """, (fingerprint, message, err_class, bucket_id, action))

        cur.execute("""
            INSERT INTO triage_signals (test_attempt_id, fingerprint)
            VALUES (%s, %s) ON CONFLICT DO NOTHING;
        """, (attempt_id, fingerprint))

        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"--> Success! Inserted {inserted} demo failures across 30 days.")
    print(f"    Bucket distribution: Product=5, Infra=7, User=4, Test=4, Timeout=2, Unknown=2")


if __name__ == "__main__":
    seed_demo()
