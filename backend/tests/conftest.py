"""
Shared test fixtures for backend tests.
"""

import os
import sys
import pytest

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def mock_buckets_meta():
    """Minimal bucket metadata matching production structure."""
    return {
        1: {"id": 1, "name": "User Errors", "is_sticky": False},
        2: {"id": 2, "name": "Infra Errors", "is_sticky": False},
        3: {"id": 3, "name": "Product (PSOD)", "is_sticky": True},
        4: {"id": 4, "name": "Unknown", "is_sticky": False},
        5: {"id": 5, "name": "Test Logic", "is_sticky": False},
        6: {"id": 6, "name": "Timeouts", "is_sticky": False},
    }
