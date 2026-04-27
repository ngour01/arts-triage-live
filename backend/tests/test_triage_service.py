"""
Unit tests for the waterfall triage service and shared scrub utility.
"""

import json
import pytest

from app.services import triage_service
from app.services.fingerprint_service import generate_fingerprint
from shared.scrub import scrub_message


class TestScrubMessage:
    def test_empty_returns_na(self):
        assert scrub_message("") == "N/A"
        assert scrub_message(None) == "N/A"

    def test_ip_scrubbing(self):
        assert "<IP>" in scrub_message("Connection to 10.112.43.5 refused")

    def test_host_scrubbing(self):
        assert "<HOST>" in scrub_message("Error on sc2-rdops-vm1.esx:443")

    def test_hex_scrubbing(self):
        assert "<HEX>" in scrub_message("Crash at address 0xDEADBEEF")

    def test_psod_preserved_verbatim(self):
        msg = "PSOD: Failed at bora/modules/vmkernel/rdt/rdt-iopath.c:6907"
        assert scrub_message(msg) == msg.strip()

    def test_core_preserved_verbatim(self):
        msg = "core file name: vmkernel-zdump.1"
        assert scrub_message(msg) == msg.strip()

    def test_test_spec_scrubbing(self):
        result = scrub_message("Invalid test: test-vpx-vsanBasicOps-1234")
        assert "<TEST_SPEC>" in result


class TestFingerprintService:
    def test_deterministic(self):
        fp1 = generate_fingerprint("TestError", "Connection refused", 2)
        fp2 = generate_fingerprint("TestError", "Connection refused", 2)
        assert fp1 == fp2

    def test_different_buckets_differ(self):
        fp1 = generate_fingerprint("TestError", "same msg", 2)
        fp2 = generate_fingerprint("TestError", "same msg", 3)
        assert fp1 != fp2

    def test_sha256_length(self):
        fp = generate_fingerprint("cls", "msg", 1)
        assert len(fp) == 64


class TestTriageClassify:
    @pytest.fixture(autouse=True)
    def _load_rules(self, mock_buckets_meta):
        triage_service._buckets_meta = mock_buckets_meta
        triage_service._rules = [
            {
                "id": 1,
                "target_bucket_id": 2,
                "pattern_text": json.dumps({"msg_pattern": "CONNECTION REFUSED"}),
            },
            {
                "id": 2,
                "target_bucket_id": 5,
                "pattern_text": json.dumps({"res_type": "test_error"}),
            },
        ]
        triage_service._rules.sort(
            key=lambda r: triage_service.BUCKET_PRIORITY.get(r["target_bucket_id"], 99)
        )

    def test_psod_always_bucket_3(self):
        bucket, action = triage_service.classify("PSOD detected", "err", "t", "FAIL", False)
        assert bucket == 3
        assert action is None

    def test_core_always_bucket_3(self):
        bucket, action = triage_service.classify("core file found", "err", "t", "FAIL", False)
        assert bucket == 3
        assert action is None

    def test_atomic_always_bucket_3(self):
        bucket, action = triage_service.classify("some signal", "err", "t", "FAIL", True)
        assert bucket == 3
        assert action is None

    def test_timeout_bucket_6(self):
        bucket, action = triage_service.classify(
            "Test is still running before timeout",
            "err", "test_error", "TIMEOUT", False,
        )
        assert bucket == 6
        assert action is None

    def test_connection_refused_bucket_2(self):
        bucket, action = triage_service.classify(
            "Connection refused on port 443",
            "Errno::ECONNREFUSED", "infra_error", "FAIL", False,
        )
        assert bucket == 2
        assert action is None

    def test_unknown_fallback_bucket_4(self):
        bucket, action = triage_service.classify(
            "Some completely unknown error", "unknown", "unknown", "FAIL", False,
        )
        assert bucket == 4
        assert action is None
