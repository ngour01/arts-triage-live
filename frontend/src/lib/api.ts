const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getExtraHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  const key = process.env.NEXT_PUBLIC_ART_API_KEY;
  if (key) {
    h["X-API-Key"] = key;
  }
  return h;
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...getExtraHeaders(),
      ...init?.headers,
    },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json();
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getExtraHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (j.detail !== undefined) {
        msg =
          typeof j.detail === "string"
            ? j.detail
            : JSON.stringify(j.detail);
      }
    } catch {
      /* ignore */
    }
    throw new Error(`API ${res.status}: ${msg}`);
  }
  return res.json();
}

// ── Types ──────────────────────────────────────────────────────────

export interface TrendData {
  total_failures_trend: number;
  auto_triaged_trend: number;
  product_bugs_trend: number;
}

export interface Summary {
  total_failures: number;
  auto_triaged_pct: number;
  active_product_bugs: number;
  trends?: TrendData;
}

export interface BucketVolume {
  bucket_id: number;
  bucket_name: string;
  count: number;
}

export interface TriageProgressDay {
  date: string;
  triaged: number;
  untriaged: number;
}

export interface RunRow {
  id: number;
  identifier: string;
  created_at?: string;
  status?: string;
  run_type?: string;
  total_tests?: number;
}

export interface ExportFailure {
  feature_name: string;
  test_case_name: string;
  latest_bucket_id: number;
  is_currently_passing: boolean;
  has_sticky_failure: boolean;
  attempt_id: number;
  attempt_number: number;
  att_status?: string;
  log_url: string;
  bug_id: string | null;
  fingerprint: string;
  scrubbed_message?: string;
  pattern_error_class?: string;
  signal_bucket_id?: number;
  is_latest: number;
}

export interface ExportPattern {
  fingerprint: string;
  scrubbed_pattern: string;
  error_class: string;
  bucket_id: number;
}

export interface ExportPagination {
  limit: number;
  skip: number;
  total_records: number;
  has_more: boolean;
}

export interface ExportData {
  cycle: {
    cycle_id: string;
    total_passed: number;
    total_failed: number;
    total_invalid: number;
  };
  patterns: ExportPattern[];
  failures: ExportFailure[];
  pagination?: ExportPagination;
}

// ── API Functions ──────────────────────────────────────────────────

export async function getSummary(days = 30): Promise<Summary> {
  return fetchJSON<Summary>(`/api/v1/analytics/summary?days=${days}`);
}

export async function getVolumeByBucket(days = 30): Promise<BucketVolume[]> {
  return fetchJSON<BucketVolume[]>(
    `/api/v1/analytics/volume-by-bucket?days=${days}`
  );
}

export async function getTriageProgress(days = 30): Promise<TriageProgressDay[]> {
  return fetchJSON<TriageProgressDay[]>(
    `/api/v1/analytics/triage-progress?days=${days}`
  );
}

export async function listRuns(): Promise<RunRow[]> {
  return fetchJSON<RunRow[]>(`/api/v1/runs`);
}

const EXPORT_PAGE_SIZE = 20000;

export async function getExportData(
  cycleId: string,
  opts?: { limit?: number; skip?: number; bucketId?: number; bucketScope?: "signal" | "execution" }
): Promise<ExportData> {
  const p = new URLSearchParams();
  if (opts?.limit != null) p.set("limit", String(opts.limit));
  if (opts?.skip != null) p.set("skip", String(opts.skip));
  if (opts?.bucketId != null) p.set("bucket_id", String(opts.bucketId));
  if (opts?.bucketScope) p.set("bucket_scope", opts.bucketScope);
  const q = p.toString();
  return fetchJSON<ExportData>(
    `/api/v1/export/${encodeURIComponent(cycleId)}${q ? `?${q}` : ""}`
  );
}

/** Fetches every failure row for the cycle (paginates until the server reports no more). */
export async function getExportDataAll(
  cycleId: string,
  opts?: { bucketId?: number; bucketScope?: "signal" | "execution" }
): Promise<ExportData> {
  let skip = 0;
  let base: ExportData | null = null;
  for (;;) {
    const chunk = await getExportData(cycleId, {
      ...opts,
      limit: EXPORT_PAGE_SIZE,
      skip,
    });
    if (!base) {
      base = chunk;
    } else {
      base.failures = [...base.failures, ...chunk.failures];
    }
    const pag = chunk.pagination;
    if (!pag?.has_more) break;
    skip += EXPORT_PAGE_SIZE;
  }
  if (base?.pagination) {
    const total = base.pagination.total_records;
    base.pagination = {
      limit: total,
      skip: 0,
      total_records: total,
      has_more: false,
    };
  }
  return base!;
}

export async function patchSignalBug(body: {
  test_attempt_id: number;
  fingerprint: string;
  bug_id: string | null;
}): Promise<{ status: string; bug_id: string | null }> {
  return fetchJSON(`/api/v1/triage/signals`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export interface TriageUrlResponse {
  status: string;
  run_id: string;
  stats: unknown;
}

export async function triageLogUrl(
  logUrl: string,
  runIdentifier?: string | null
): Promise<TriageUrlResponse> {
  return postJSON<TriageUrlResponse>("/api/v1/triage/url", {
    log_url: logUrl.trim(),
    ...(runIdentifier?.trim()
      ? { run_identifier: runIdentifier.trim() }
      : {}),
  });
}

export interface TriageDiscoverResponse {
  status: string;
  run_identifier: string;
  ingested: number;
  stats: unknown;
  tests: Array<{
    feature: string;
    test_case: string;
    status: string;
    log_url: string;
  }>;
}

export async function triageDiscover(
  url: string,
  runIdentifier: string,
  featureName?: string | null
): Promise<TriageDiscoverResponse> {
  return postJSON<TriageDiscoverResponse>("/api/v1/triage/discover", {
    url: url.trim(),
    run_identifier: runIdentifier.trim(),
    ...(featureName?.trim()
      ? { feature_name: featureName.trim() }
      : {}),
  });
}
