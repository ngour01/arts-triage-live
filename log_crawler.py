import os
import sys
import re
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("art_triage.crawler")

API = "http://localhost:8000/api/v1"
DRAGON_SUITE = "http://dragonsuite-app.vdp.lvn.broadcom.net/apis/v1/getCycleRecords"
API_KEY = os.environ.get("ART_API_KEY")
API_HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}


def fetch(url, retries=3, timeout=30):
    """GET with automatic retry and exponential back-off."""
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=timeout)
            return r.text if r.status_code == 200 else None
        except Exception as e:
            if attempt < retries - 1:
                delay = 2.0 * (attempt + 1)
                logger.debug("Fetch retry %d/%d for %s: %s", attempt + 1, retries, url, e)
                time.sleep(delay)
            else:
                logger.warning("Failed to fetch %s after %d attempts: %s", url, retries, e)
                return None


def get_full_psod_trace(summary_txt):
    if not summary_txt:
        return []
    text = re.sub(r'<(script|style)[^>]*>[\s\S]*?</\1>', '', summary_txt, flags=re.IGNORECASE)
    text = re.sub(r'<br[^>]*>|<\/p>|</div|\\n>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)

    raw = []
    for keyword in ["PSOD:", "Panic:", "Exception 14", "core file"]:
        start = 0
        while True:
            idx = text.find(keyword, start)
            if idx == -1:
                break
            trace = text[idx:idx + 4000].strip()
            trace = re.split(r'\n\s*\n\s*\n', trace)[0]
            if trace:
                raw.append(trace)
            start = idx + len(keyword)

    raw = list(set(raw))
    raw.sort(key=len, reverse=True)
    unique = []
    for t in raw:
        if not any(t in longer for longer in unique):
            unique.append(t)
    return unique


def find_log_files(url, depth=0, max_depth=3, visited=None):
    """Recursively discover stateDump.json.txt files up to *max_depth* levels."""
    if visited is None:
        visited = set()
    if depth > max_depth or url in visited:
        return []
    visited.add(url)

    txt = fetch(url)
    if not txt:
        return []

    files = [urljoin(url, f) for f in re.findall(r'href="([^"]*stateDump\.json\.txt[^"]*)"', txt)]

    if depth < max_depth:
        sub_dirs = [urljoin(url, d) for d in re.findall(r'href="([^/."][^"]*/)"', txt)]
        for sd in sub_dirs:
            if sd not in visited:
                files.extend(find_log_files(sd, depth + 1, max_depth, visited))

    return list(set(files))


def process_record_folder(record, run_id):
    """Runs inside a background thread. Finds URLs, fetches JSON, builds payloads."""
    url = record['log_location']
    feature = record.get('display_name') or 'Unknown'

    files = find_log_files(url)
    payloads = []

    for l_url in files:
        try:
            log_data = requests.get(l_url, timeout=30).json()
            summary_url = urljoin(l_url.rsplit('/', 1)[0] + '/', "testbedSummary.html")
            atomic_sigs = get_full_psod_trace(fetch(summary_url))

            payloads.append({
                "run_id": run_id,
                "feature_name": str(feature).strip(),
                "test_case_name": str(l_url.split('/')[-2]).strip(),
                "log_url": str(l_url),
                "status": str(log_data.get("result") or "FAIL").upper(),
                "result": str(log_data.get("result") or "FAIL").upper(),
                "result_type": str(log_data.get("result_type") or "N/A"),
                "error_class": str(log_data.get("error_class") or "N/A"),
                "json_error_message": str(
                    log_data.get("error_message") or log_data.get("result_msg") or "N/A"
                ),
                "atomic_signals": atomic_sigs,
            })
        except Exception as e:
            logger.warning("Failed to process %s: %s", l_url, e)

    return payloads


def upload_chunk(chunk_data, chunk_num):
    try:
        res = requests.post(
            f"{API}/triage/attempts/batch",
            json=chunk_data,
            headers=API_HEADERS,
            timeout=60,
        )
        if res.status_code == 200:
            logger.info("Uploaded batch %d (%d items)", chunk_num, len(chunk_data))
        elif res.status_code == 401:
            logger.error("Batch %d rejected: authentication failed (set ART_API_KEY)", chunk_num)
        else:
            logger.error("Batch %d upload failed (%d): %s", chunk_num, res.status_code, res.text)
    except Exception as e:
        logger.error("Batch %d API error: %s", chunk_num, e)


def run_triage(cycle_id):
    logger.info("[1/4] Registering Cycle %s…", cycle_id)
    try:
        run_id = requests.post(
            f"{API}/runs",
            json={"identifier": cycle_id},
            headers=API_HEADERS,
            timeout=10,
        ).json()['id']
    except Exception as e:
        logger.error("API offline! Error: %s", e)
        return

    logger.info("[2/4] Fetching failure records from DragonSuite…")
    try:
        records = requests.get(
            f"{DRAGON_SUITE}?cycle_id={cycle_id}&job_status=fail",
            timeout=60,
        ).json().get("cycle_records", [])
    except Exception as e:
        logger.error("DragonSuite API Error: %s", e)
        records = []

    if records:
        logger.info("[3/4] Harvesting %d test folders in parallel…", len(records))

        current_chunk = []
        chunk_count = 0
        chunk_size = 50
        completed_folders = 0

        with ThreadPoolExecutor(max_workers=100) as exe:
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

                if completed_folders % 20 == 0 or completed_folders == len(records):
                    logger.info("  Progress: %d/%d folders checked", completed_folders, len(records))

                while len(current_chunk) >= chunk_size:
                    chunk_count += 1
                    upload_chunk(current_chunk[:chunk_size], chunk_count)
                    current_chunk = current_chunk[chunk_size:]

        if current_chunk:
            chunk_count += 1
            upload_chunk(current_chunk, chunk_count)
    else:
        logger.warning("No records found for Cycle %s.", cycle_id)

    logger.info("[4/4] Storing stats & sending notification…")
    try:
        requests.post(f"{API}/runs/{cycle_id}/refresh", headers=API_HEADERS, timeout=15)
    except Exception as e:
        logger.warning("Failed to refresh run stats: %s", e)

    try:
        from messenger import Messenger
        Messenger().send_summary(cycle_id)
    except ImportError:
        logger.info("Messenger module not configured — skipping notification")
    except Exception as e:
        logger.warning("Messenger failed: %s", e)

    logger.info("Triage process complete for Cycle %s.", cycle_id)


if __name__ == "__main__":
    target_id = sys.argv[1] if len(sys.argv) > 1 else "580"
    run_triage(target_id)
