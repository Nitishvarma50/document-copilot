"""Exercise the real auth dependency without calling Supabase."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from app.auth import dependencies
from app.main import app
from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError, AuthRetryableError

client = TestClient(app)


@pytest.fixture
def verifier(monkeypatch):
    verify = AsyncMock()

    @asynccontextmanager
    async def managed_client():
        yield SimpleNamespace(auth=SimpleNamespace(get_user=verify))

    monkeypatch.setattr(dependencies, "managed_client", managed_client)
    return verify


@pytest.mark.parametrize(
    "header", [None, "Basic token", "Bearer", "Bearer   ", "Bearer token extra"]
)
def test_missing_or_malformed_token(header, verifier):
    response = client.get(
        "/auth/me", headers=({"Authorization": header} if header is not None else {})
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    verifier.assert_not_awaited()


def test_authenticated_endpoint_returns_verified_user(verifier):
    user_id = str(uuid4())
    verifier.return_value = SimpleNamespace(
        user=SimpleNamespace(id=user_id, email="user@example.com")
    )
    response = client.get("/auth/me", headers={"Authorization": "Bearer valid-token"})
    assert response.status_code == 200
    assert response.json() == {"id": user_id, "email": "user@example.com"}
    verifier.assert_awaited_once_with(jwt="valid-token")


@pytest.mark.parametrize("code", ["bad_jwt", "session_expired"])
def test_invalid_or_expired_tokens(verifier, code):
    verifier.side_effect = AuthApiError("private upstream details", 401, code)
    response = client.get("/auth/me", headers={"Authorization": "Bearer bad-token"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "private" not in response.text


@pytest.mark.parametrize("result", [None, SimpleNamespace(user=None)])
def test_missing_user_response(verifier, result):
    verifier.return_value = result
    assert (
        client.get("/auth/me", headers={"Authorization": "Bearer token"}).status_code
        == 401
    )


@pytest.mark.parametrize(
    "error",
    [
        AuthApiError("private details", 500, None),
        AuthApiError("rate limit", 429, None),
        AuthRetryableError("unavailable", 503),
        httpx.ConnectError("private network details"),
    ],
)
def test_auth_outage_is_not_an_invalid_login(verifier, error):
    verifier.side_effect = error
    response = client.get("/auth/me", headers={"Authorization": "Bearer token"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication service unavailable"}
