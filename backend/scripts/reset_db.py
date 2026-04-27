"""
Hard reset — truncate all data tables, keeping schema and buckets intact.

Usage:
    python -m scripts.reset_db          (from backend/)
    python backend/scripts/reset_db.py  (from repo root)
"""

import os
import sys
import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.config import get_settings


def hard_reset():
    settings = get_settings()
    print(f"--> WARNING: Hard reset on {settings.database_url} ...")

    try:
        conn = psycopg2.connect(dsn=settings.database_url)
        cur = conn.cursor()
        cur.execute("""
            TRUNCATE TABLE triage_signals CASCADE;
            TRUNCATE TABLE error_patterns CASCADE;
            TRUNCATE TABLE test_attempts CASCADE;
            TRUNCATE TABLE test_executions CASCADE;
            TRUNCATE TABLE runs CASCADE;
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("--> Success! Database is now empty and ready for a fresh cycle.")
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    hard_reset()
