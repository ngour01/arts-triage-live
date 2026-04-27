"""
Integration-style tests for the FastAPI app using TestClient.

These tests use httpx/TestClient and mock the database layer so they
can run without a live Postgres instance.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.services import triage_service


@pytest.fixture
def mock_db():
    """Patch the database pool so no real DB is needed."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("app.database._pool") as mock_pool:
        mock_pool.getconn.return_value = mock_conn
        yield mock_conn, mock_cursor


@pytest.fixture
def client(mock_db, mock_buckets_meta):
    """Create a test client with mocked lifespan."""
    triage_service._buckets_meta = mock_buckets_meta
    triage_service._rules = []

    from app.main import app

    with patch("app.main.init_pool"), \
         patch("app.main.close_pool"), \
         patch("app.services.cache_service.init_cache"), \
         patch("app.services.cache_service.close_cache"), \
         patch("app.services.triage_service.load_intelligence"):
        with TestClient(app) as c:
            yield c


class TestHealthEndpoint:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"


class TestRunsRouter:
    def test_create_run(self, client, mock_db):
        _, mock_cursor = mock_db
        mock_cursor.fetchone.return_value = (42,)

        resp = client.post("/api/v1/runs", json={"identifier": "580", "run_type": "CYCLE"})
        assert resp.status_code == 200
        assert resp.json()["id"] == 42
