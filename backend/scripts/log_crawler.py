"""
Harvest DragonSuite-style cycle records and POST batches to the ARTs API.

This is the single CLI for ingesting cycle failures. Logic shared with the API
is in ``shared.crawler_utils`` (same module used by POST /api/v1/triage/discover).

Env:
  ARTS_API_BASE — default http://localhost:8000/api/v1
  ART_API_KEY     — optional; sent as X-API-Key
  DRAGONSUITE_API_BASE — default http://localhost:9000 (use with mock_dragonsuite.py)
"""

import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests

# Repo root (parent of ``backend/``) so ``import shared`` works when run as a script
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared.crawler_utils import fetch, find_log_files, get_full_psod_trace

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("arts.log_crawler")

API = os.environ.get("ARTS_API_BASE", "http://localhost:8000/api/v1")
DS_BASE = os.environ.get("DRAGONSUITE_API_BASE", "http://localhost:9000")
API_KEY = os.environ.get("ART_API_KEY")
API_HEADERS = (
    {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    if API_KEY
    else {"Content-Type": "application/json"}
)


def process_record_folder(record, run_id):
    url = record["log_location"]
    feature = record.get("display_name") or "Unknown"

    files = find_log_files(url)
    payloads = []

    for l_url in files:
        try:
            raw = fetch(l_url, timeout=10)
            if not raw:
                continue
            log_data = json.loads(raw)
            summary_url = urljoin(l_url.rsplit("/", 1)[0] + "/", "testbedSummary.html")
            atomic_sigs = get_full_psod_trace(fetch(summary_url))

            payloads.append(
                {
                    "run_id": run_id,
                    "feature_name": str(feature).strip(),
                    "test_case_name": str(l_url.split("/")[-2]).strip(),
                    "log_url": str(l_url),
                    "status": str(log_data.get("result") or "FAIL").upper(),
                    "result": str(log_data.get("result") or "FAIL").upper(),
                    "result_type": str(log_data.get("result_type") or "N/A"),
                    "error_class": str(log_data.get("error_class") or "N/A"),
                    "json_error_message": str(
                        log_data.get("error_message") or log_data.get("result_msg") or "N/A"
                    ),
                    "atomic_signals": atomic_sigs,
                }
            )
        except Exception as e:
            logger.warning("Failed to process %s: %s", l_url, e)

    return payloads


def upload_chunk(chunk_data, chunk_num):
    try:
        res = requests.post(
            f"{API}/triage/batch",
            json={"attempts": chunk_data},
            headers=API_HEADERS,
            timeout=60,
        )
        if res.status_code == 200:
            logger.info("Uploaded batch %d (%d items)", chunk_num, len(chunk_data))
        elif res.status_code == 401:
            logger.error("Batch %d rejected: set ART_API_KEY to match server", chunk_num)
        else:
            logger.error(
                "Batch %d upload failed (%d): %s",
                chunk_num,
                res.status_code,
                res.text,
            )
    except Exception as e:
        logger.error("Batch %d API error: %s", chunk_num, e)


def run_triage(cycle_id, record_limit=None):
    logger.info("[1/4] Registering cycle %s…", cycle_id)
    try:
        run_id = requests.post(
            f"{API}/runs",
            json={"identifier": str(cycle_id), "run_type": "CYCLE"},
            headers=API_HEADERS,
            timeout=15,
        ).json()["id"]
    except Exception as e:
        logger.error("API offline! Error: %s", e)
        return

    logger.info("[2/4] Fetching failure records…")
    try:
        records = requests.get(
            f"{DS_BASE}/apis/v1/getCycleRecords?cycle_id={cycle_id}&job_status=fail",
            timeout=20,
        ).json().get("cycle_records", [])
    except Exception as e:
        logger.error("Cycle records API error: %s", e)
        records = []

    if record_limit is not None and record_limit > 0 and records:
        n = len(records)
        records = records[:record_limit]
        if len(records) < n:
            logger.info("Record limit: processing %d of %d records", len(records), n)

    if records:
        logger.info("[3/4] Harvesting %d test folders in parallel…", len(records))

        current_chunk = []
        chunk_count = 0
        chunk_size = 50
        completed_folders = 0

        with ThreadPoolExecutor(max_workers=20) as exe:
            futs = [exe.submit(process_record_folder, r, run_id) for r in records]

            for f in as_completed(futs):
                completed_folders += 1
                try:
                    payloads_found = f.result()
                except Exception as e:
                    logger.error("Folder processing thread raised: %s", e)
                    payloads_found = []

                if payloads_found:
                    current_chunk.extend(payloads_found)

                logger.info(
                    "  Progress: %d/%d folders (%d payloads)",
                    completed_folders,
                    len(records),
                    len(current_chunk),
                )

                while len(current_chunk) >= chunk_size:
                    chunk_count += 1
                    upload_chunk(current_chunk[:chunk_size], chunk_count)
                    current_chunk = current_chunk[chunk_size:]

        if current_chunk:
            chunk_count += 1
            upload_chunk(current_chunk, chunk_count)
    else:
        logger.warning("No records found for cycle %s.", cycle_id)

    logger.info("[4/4] Refresh + stats…")
    try:
        requests.post(f"{API}/runs/{cycle_id}/refresh", headers=API_HEADERS, timeout=30)
    except Exception as e:
        logger.warning("Refresh failed: %s", e)

    try:
        sr = requests.get(f"{API}/runs/{cycle_id}/stats", timeout=20)
        if sr.ok:
            logger.info("Stats: %s", sr.json().get("totals"))
    except Exception as e:
        logger.warning("Stats fetch failed: %s", e)

    logger.info("Done for cycle %s.", cycle_id)


if __name__ == "__main__":
    target_id = sys.argv[1] if len(sys.argv) > 1 else "580"
    limit = None
    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
            if limit <= 0:
                limit = None
        except ValueError:
            limit = None
    run_triage(target_id, record_limit=limit)
