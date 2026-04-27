"""
Pydantic request / response schemas for the ARTs API.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


# ── Runs ──────────────────────────────────────────────────────────────

class RunCreate(BaseModel):
    identifier: str
    run_type: str = "CYCLE"


class RunUpdate(BaseModel):
    status: str
    total_tests: int


class RunResponse(BaseModel):
    id: int


# ── Triage ────────────────────────────────────────────────────────────

class AttemptPayload(BaseModel):
    run_id: int
    feature_name: str
    test_case_name: str
    log_url: str
    status: str
    result: str = "FAIL"
    result_type: str = "N/A"
    error_class: str = "N/A"
    json_error_message: str = "N/A"
    atomic_signals: List[str] = []


class BatchPayload(BaseModel):
    attempts: List[AttemptPayload] = Field(..., max_length=500)


class AttemptResult(BaseModel):
    success: bool
    attempt_num: int
    status: str


class BatchResult(BaseModel):
    processed: int
    results: List[AttemptResult]


class TriageUrlRequest(BaseModel):
    log_url: str
    user_id: str = "Anonymous"
    run_identifier: Optional[str] = None


class DiscoverRequest(BaseModel):
    url: str
    run_identifier: str
    feature_name: Optional[str] = None


class SignalBugUpdate(BaseModel):
    test_attempt_id: int
    fingerprint: str
    bug_id: Optional[str] = None


class RuleCreate(BaseModel):
    pattern_text: dict
    target_bucket_id: int
    added_by: str = "api"


# ── Analytics ─────────────────────────────────────────────────────────

class TrendData(BaseModel):
    total_failures_trend: float = 0.0
    auto_triaged_trend: float = 0.0
    product_bugs_trend: float = 0.0


class SummaryResponse(BaseModel):
    total_failures: int
    auto_triaged_pct: float
    active_product_bugs: int
    trends: Optional[TrendData] = None


class BucketVolume(BaseModel):
    bucket_id: int
    bucket_name: str
    count: int


class TriageProgressDay(BaseModel):
    date: str
    triaged: int
    untriaged: int
