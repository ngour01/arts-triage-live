"""
Database connection pool management.

Provides a context-managed connection from a psycopg2 ThreadedConnectionPool,
matching the pattern used in the POC but driven by pydantic-settings config.
"""

from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

from app.config import get_settings

_pool: ThreadedConnectionPool | None = None


def init_pool() -> ThreadedConnectionPool:
    """Create the connection pool (called once at app startup)."""
    global _pool
    settings = get_settings()
    _pool = ThreadedConnectionPool(
        settings.db_pool_min,
        settings.db_pool_max,
        dsn=settings.database_url,
    )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None


@contextmanager
def get_conn():
    """Yield a connection and return it to the pool on exit."""
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor(dict_cursor: bool = False):
    """Yield a connection+cursor pair, auto-committing on success."""
    with get_conn() as conn:
        factory = RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=factory)
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
