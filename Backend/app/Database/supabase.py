"""Supabase client construction for server-side database and auth access."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from app.config import settings
from supabase import AsyncClient, acreate_client
from supabase.lib.client_options import AsyncClientOptions


@asynccontextmanager
async def managed_client(
    *, access_token: str | None = None, privileged: bool = False
) -> AsyncIterator[AsyncClient]:
    """Own HTTP resources for one request; never share a user's auth state."""
    if privileged and access_token is not None:
        raise ValueError("Privileged and user-scoped clients must be separate")
    key = (
        settings.supabase_service_role_key if privileged else settings.supabase_anon_key
    )
    # Supabase injects its own `apiKey` header. Adding a differently cased
    # `apikey` duplicates it when the SDK merges its case-sensitive dictionaries.
    headers = {"Authorization": f"Bearer {access_token or key}"}
    async with httpx.AsyncClient(
        headers=headers,
        timeout=settings.supabase_request_timeout_seconds,
    ) as http_client:
        client = await acreate_client(
            settings.supabase_url,
            key,
            options=AsyncClientOptions(
                headers=headers,
                httpx_client=http_client,
                auto_refresh_token=False,
                persist_session=False,
            ),
        )
        yield client


_service_role_client: AsyncClient | None = None


def _server_client_options(
    *,
    access_token: str | None = None,
) -> AsyncClientOptions:
    headers: dict[str, str] = {}
    if access_token is not None:
        headers["Authorization"] = f"Bearer {access_token}"

    return AsyncClientOptions(
        headers=headers,
        auto_refresh_token=False,
        persist_session=False,
    )


def _normalize_access_token(access_token: str) -> str:
    prefix = "Bearer "
    if access_token.startswith(prefix):
        return access_token[len(prefix) :]
    return access_token


async def get_service_role_client() -> AsyncClient:
    """Return a shared client that bypasses RLS -backend-only privileged access."""
    global _service_role_client
    if _service_role_client is None:
        _service_role_client = await acreate_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
            options=_server_client_options(),
        )
    return _service_role_client


async def create_user_client(access_token: str) -> AsyncClient:
    """Return a request-scoped Supabase client that enforces user RLS."""
    return await acreate_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=_server_client_options(
            access_token=_normalize_access_token(access_token),
        ),
    )
