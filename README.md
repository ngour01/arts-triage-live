# ART Triage (ART v3)

Web service and tools to **ingest test run results**, **classify failures** into buckets (user / infra / PSOD / unknown / …), **deduplicate error text**, attach **bug or issue IDs** per signal, and **browse** everything in a small dashboard.

## Stack

- **API & UI host:** FastAPI + Uvicorn (`backend/api.py`), static dashboard (`frontend/`)
- **Database:** PostgreSQL (`schema.sql`)
- **Crawler:** `log_crawler.py` pulls failed cycle records (DragonSuite-shaped API) and posts batches to the ART API

## Prerequisites

- Python 3.9+ (project uses a local `venv`)
- PostgreSQL with a database you can point the app at (default name below)

## Quick start

1. **Create the database and apply schema**

   ```bash
   createdb art_triage   # or use your admin tool
   psql -d art_triage -f schema.sql
   ```

2. **Python environment**

   ```bash
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Seed classification rules** (optional but typical for a new DB)

   ```bash
   python seeder.py
   ```

4. **Match DB credentials** to your Postgres install. Defaults are in `backend/api.py` (`DB_CONFIG`: `art_triage`, `postgres` / `password`, `localhost:5432`). Change them there if needed.

5. **Run the API** (serves `/` dashboard and `/api/v1/...`)

   ```bash
   uvicorn backend.api:app --host 127.0.0.1 --port 8000 --reload
   ```

   - Dashboard: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
   - OpenAPI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Optional: mock DragonSuite + crawler

For local development, `mock_server.py` mimics the cycle-records API. `log_crawler.py` is configured to call **`http://localhost:9000`** for `getCycleRecords` by default.

```bash
# Terminal 1 — mock DragonSuite
uvicorn mock_server:app --host 127.0.0.1 --port 9000

# Terminal 2 — ART API (as above)

# Terminal 3 — crawl cycle id (example: 7); optional max records for testing: `python log_crawler.py 7 100`
python log_crawler.py 7
```

Point `log_crawler.py` at your real DragonSuite base URL when not using the mock (edit the `getCycleRecords` URL or keep a separate clone such as `arts-triage-live` with a different URL).

## Authentication (writes)

If you set **`ART_API_KEY`** in the environment when starting Uvicorn, all **write** routes require header **`X-API-Key: <same value>`**. Reads (GET) stay open unless you change the code.

The crawler sends this header when `ART_API_KEY` is set.

## Useful API routes

| Area | Example |
|------|---------|
| Health | `GET /api/v1/health` |
| List runs | `GET /api/v1/runs` |
| Summary + bucket counts | `GET /api/v1/runs/{identifier}/summary` |
| Full stats + unique issue ids per bucket | `GET /api/v1/runs/{identifier}/stats` |
| Export rows (optional `bucket_id`, `bucket_scope`) | `GET /api/v1/export/{identifier}` |
| Smart URL ingest | `POST /api/v1/triage/discover` |

One-line reference: [docs/API.md](docs/API.md).

## Project layout

```
backend/          api.py, crawler_utils.py
frontend/         Dashboard (HTML/CSS/JS)
docs/API.md       HTTP reference table
schema.sql        PostgreSQL DDL
seeder.py         Initial master_rules
log_crawler.py    Cycle harvest → ART API
mock_server.py    Local DragonSuite stub
messenger.py      Optional notifications hook
```

## `arts-triage-live`

A sibling folder is sometimes used for **production-style** settings (e.g. real DragonSuite URL). Keep it in sync with this tree via your own process, or rsync/copy the same files and override only URLs and secrets.
