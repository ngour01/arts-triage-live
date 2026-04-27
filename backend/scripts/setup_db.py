"""
Database setup — execute the partitioned init.sql schema.

Usage:
    python -m scripts.setup_db          (from backend/)
    python backend/scripts/setup_db.py  (from repo root)
"""

import os
import sys
import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.config import get_settings


def setup_database():
    settings = get_settings()
    print(f"--> Setting up ARTs database via {settings.database_url} ...")

    schema_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docker", "postgres", "init.sql"
    )
    if not os.path.exists(schema_path):
        print(f"Error: Schema file not found at {schema_path}")
        sys.exit(1)

    with open(schema_path, "r") as f:
        schema_sql = f.read()

    try:
        conn = psycopg2.connect(dsn=settings.database_url)
        cur = conn.cursor()
        cur.execute(schema_sql)
        conn.commit()
        cur.close()
        conn.close()
        print("--> Success! All tables and partitions created.")
    except psycopg2.OperationalError as e:
        print(f"\n[DB CONNECTION ERROR] {e}")
        print("Ensure PostgreSQL is running and the database exists.")
        sys.exit(1)


if __name__ == "__main__":
    setup_database()
