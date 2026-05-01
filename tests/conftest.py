"""CryptoMinds test configuration."""
import os
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set internal token before api_server import (module reads env at import)
os.environ["CRYPTOMINDS_INTERNAL_TOKEN"] = "test-token"
os.environ["CRYPTOMINDS_DEBUG"] = "false"

import pytest


@pytest.fixture
def flask_client():
    """Flask test client for API server."""
    from api_server import app
    with app.test_client() as client:
        yield client


@pytest.fixture
def auth_headers():
    """Headers with valid internal token."""
    return {"X-CryptoMinds-Internal-Token": "test-token"}