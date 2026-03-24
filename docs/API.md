# ART v3 — API (one-line reference)

Base: `http://localhost:8000` — interactive docs: `/docs`.

**Auth:** If `ART_API_KEY` is set, send `X-API-Key` on all **write** methods below.

| Method | Path | What it does |
|--------|------|----------------|
| GET | `/api/v1/health` | Check database connectivity and counts of loaded rules and buckets. |
| POST | `/api/v1/runs` | Create or upsert a run by identifier and return its numeric id. |
| POST | `/api/v1/runs/{identifier}/refresh` | Recompute per-bucket snapshot stats for this run (failing executions only). |
| POST | `/api/v1/rules` | Add or update a classification rule and reload rules in memory. |
| POST | `/api/v1/triage/url` | GET log_url as JSON and record one triaged attempt under run_identifier (or auto name). |
| POST | `/api/v1/triage/attempt` | Ingest one test attempt (classify errors, update execution and signals). |
| POST | `/api/v1/triage/attempts/batch` | Ingest many attempts in one database transaction. |
| POST | `/api/v1/triage/discover` | Crawl url for stateDump JSON (file or directory) and triage into run_identifier. |
| PATCH | `/api/v1/triage/signals` | Set or clear bug_id on one triage signal (by attempt id and fingerprint). |
| GET | `/api/v1/runs` | List all runs (newest first). |
| GET | `/api/v1/buckets` | List failure buckets (id, name, is_sticky). |
| GET | `/api/v1/runs/{identifier}/summary` | Return pass/fail/sticky counts and per-bucket totals for one run. |
| GET | `/api/v1/runs/{identifier}/stats` | Full stats: totals, per-bucket exec/signal counts, unique bug/issue ids (PR/Jira/etc.). |
| GET | `/api/v1/export/{identifier}` | Error patterns + failure rows (`limit`, `skip`). Optional `bucket_id`; `bucket_scope=signal` (pattern bucket, default) or `execution` (test `latest_bucket_id`). |
