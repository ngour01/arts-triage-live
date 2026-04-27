"""
Application settings loaded from environment variables with sensible defaults.
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from functools import lru_cache

_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_CANDIDATES = [_ROOT / ".env", Path(".env")]
_ENV_FILE = next((p for p in _ENV_CANDIDATES if p.is_file()), ".env")


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:password@localhost:5432/art_triage"
    redis_url: str = "redis://localhost:6379/0"

    db_pool_min: int = 1
    db_pool_max: int = 20

    redis_cache_ttl: int = 300  # 5 minutes

    batch_max_size: int = 500

    art_api_key: Optional[str] = None  # ART_API_KEY in environment

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
