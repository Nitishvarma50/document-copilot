"""FastAPI dependencies for Supabase JWT authentication."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Annotated

import httpx
from app.config import settings
from app.Database.supabase import managed_client
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthApiError, AuthRetryableError

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    token = credentials.credentials.strip()
    if not token or len(token.split()) != 1:
        raise _unauthorized()
    return token


async def get_current_user(
    access_token: Annotated[str, Depends(get_access_token)],
) -> CurrentUser:
    try:
        async with asyncio.timeout(settings.supabase_request_timeout_seconds):
            async with managed_client() as client:
                response = await client.auth.get_user(jwt=access_token)
    except AuthApiError as exc:
        if exc.status in (400, 401, 403, 422):
            raise _unauthorized("Invalid or expired token") from exc
        raise HTTPException(503, "Authentication service unavailable") from exc
    except (AuthRetryableError, httpx.HTTPError, TimeoutError) as exc:
        raise HTTPException(503, "Authentication service unavailable") from exc
    if response is None or response.user is None or not response.user.email:
        raise _unauthorized("Invalid or expired token")
    return CurrentUser(
        id=uuid.UUID(response.user.id),
        email=response.user.email,
    )
