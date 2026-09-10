"""Shared test setup for the FastAPI backend."""

import os
import sys
from pathlib import Path

import httpx
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2] / "Backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Backend settings are intentionally strict in production. Tests use safe,
# non-production placeholders so they never require local or CI credentials.
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-role-key"
os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost:5432/test"
os.environ["OPENAI_API_KEY"] = "test-openai-key"


@pytest.fixture(autouse=True)
def block_live_http(monkeypatch):
    """Backend unit tests may use MockTransport, never the real HTTP transports."""

    def blocked(*args, **kwargs):
        raise AssertionError("Live HTTP is forbidden in backend unit tests")

    async def async_blocked(*args, **kwargs):
        blocked()

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", async_blocked)
