"""
Shared log-crawling helpers for triage/discover and standalone crawlers.
"""

import json
import logging
import re
import requests
from urllib.parse import urljoin

logger = logging.getLogger("arts.crawler_utils")


def fetch(url: str, timeout: int = 15):
    """Single-attempt GET. Returns text on 200, None on any failure."""
    try:
        r = requests.get(url, timeout=timeout)
        return r.text if r.status_code == 200 else None
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None


def get_full_psod_trace(summary_txt: str | None):
    """Extract distinct PSOD / Panic / core traces from testbedSummary HTML."""
    if not summary_txt:
        return []
    text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", "", summary_txt, flags=re.IGNORECASE)
    text = re.sub(r"<br[^>]*>|<\/p>|</div|\\n>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)

    raw = []
    for keyword in ["PSOD:", "Panic:", "Exception 14", "core file"]:
        start = 0
        while True:
            idx = text.find(keyword, start)
            if idx == -1:
                break
            trace = text[idx : idx + 4000].strip()
            trace = re.split(r"\n\s*\n\s*\n", trace)[0]
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


def find_log_files(url: str, depth: int = 0, max_depth: int = 3, visited=None):
    """Recursively discover stateDump.json.txt files starting from *url*."""
    if visited is None:
        visited = set()
    if depth > max_depth or url in visited:
        return []
    visited.add(url)

    txt = fetch(url)
    if not txt:
        return []

    files = [urljoin(url, f) for f in re.findall(r'href="([^"]*stateDump\.json\.txt)"', txt)]

    if depth < max_depth:
        sub_dirs = [urljoin(url, d) for d in re.findall(r'href="([^/."][^"]*/)"', txt)]
        for sd in sub_dirs:
            if sd not in visited:
                files.extend(find_log_files(sd, depth + 1, max_depth, visited))

    return list(set(files))


def is_state_dump_json(text: str) -> bool:
    """Return True if the text looks like a stateDump JSON (has 'result' key)."""
    try:
        data = json.loads(text)
        return isinstance(data, dict) and "result" in data
    except Exception:
        return False


def discover_payloads(base_url: str, run_id: int, feature_name: str | None = None):
    """
    Smart discovery from *base_url*: single JSON or HTML directory crawl.
    Returns payload dicts ready for AttemptPayload / triage ingest.
    """
    txt = fetch(base_url)
    if not txt:
        return []

    if is_state_dump_json(txt):
        log_files = [base_url]
    else:
        log_files = find_log_files(base_url)
        if not log_files:
            logger.info("No stateDump.json.txt files found under %s", base_url)
            return []

    logger.info("discover_payloads: %d log file(s) under %s", len(log_files), base_url)
    payloads = []

    for l_url in log_files:
        try:
            raw = fetch(l_url)
            if not raw:
                logger.warning("Could not read %s", l_url)
                continue
            log_data = json.loads(raw)

            dir_url = l_url.rsplit("/", 1)[0] + "/"
            summary_url = urljoin(dir_url, "testbedSummary.html")
            atomic_sigs = get_full_psod_trace(fetch(summary_url))

            test_case = l_url.split("/")[-2].strip() or "Unknown"
            feat = (feature_name or base_url.rstrip("/").split("/")[-1] or "Unknown").strip()

            payloads.append(
                {
                    "run_id": run_id,
                    "feature_name": feat,
                    "test_case_name": test_case,
                    "log_url": l_url,
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
            logger.warning("Failed to build payload for %s: %s", l_url, e)

    return payloads
