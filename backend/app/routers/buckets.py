"""List failure buckets (read-only)."""

from fastapi import APIRouter
from psycopg2.extras import RealDictCursor

from app.database import get_conn

router = APIRouter(prefix="/api/v1/buckets", tags=["buckets"])


@router.get("")
def list_buckets():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, is_sticky FROM buckets ORDER BY id;"
            )
            return cur.fetchall()
