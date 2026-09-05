"""Tests for backend bearer-token authentication."""

from uuid import UUID

from app.auth.dependencies import CurrentUser, get_current_user
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_authenticated_endpoint_requires_bearer_token() -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_authenticated_endpoint_rejects_malformed_authorization() -> None:
    response = client.get("/auth/me", headers={"Authorization": "Basic token"})

    assert response.status_code == 401


def test_authenticated_endpoint_returns_verified_user() -> None:
    async def fake_get_current_user() -> CurrentUser:
        return CurrentUser(
            id=UUID("11111111-1111-1111-1111-111111111111"),
            email="user@example.com",
        )

    app.dependency_overrides[get_current_user] = fake_get_current_user
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer valid-token"},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json() == {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "user@example.com",
    }


def test_authenticated_endpoint_rejects_invalid_token(monkeypatch) -> None:
    async def fake_get_current_user() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid or expired token")

    app.dependency_overrides[get_current_user] = fake_get_current_user
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 401
