"""Shared FastAPI dependencies (optional API key on writes)."""

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from app.config import get_settings

_write_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_write_auth(x_api_key: Optional[str] = Depends(_write_api_key_header)) -> None:
    """Require X-API-Key when ART_API_KEY is set in the environment."""
    key = get_settings().art_api_key
    if key and x_api_key != key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
