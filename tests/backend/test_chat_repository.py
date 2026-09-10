"""Exercise real Supabase SDK request construction via httpx.MockTransport."""

import asyncio
import base64
import json
from uuid import uuid4

import httpx
import pytest
from app.auth.dependencies import CurrentUser
from app.chat.errors import ChatError
from app.chat.schemas import Thread
from app.config import settings
from app.Database.chats import SupabaseChatStore, decode_cursor, encode_cursor
from app.Database.supabase import managed_client

USER = CurrentUser(id=uuid4(), email="alice@example.com")
THREAD_ID = uuid4()
ROW = {
    "id": str(THREAD_ID),
    "user_id": str(USER.id),
    "title": "New chat",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


@pytest.fixture
def transport(monkeypatch):
    original = httpx.AsyncClient

    def install(handler):
        clients = []

        def factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            client = original(*args, **kwargs)
            clients.append(client)
            return client

        monkeypatch.setattr(httpx, "AsyncClient", factory)
        return clients

    return install


async def with_store(action):
    async with managed_client(access_token="user-token") as reader:
        async with managed_client(privileged=True) as writer:
            return await action(SupabaseChatStore(reader, writer, USER))


def test_create_uses_verified_identity_and_server_credentials(transport):
    def handler(request):
        assert request.url.path == "/rest/v1/rpc/chat_create_thread"
        assert request.headers["apikey"] == "test-service-role-key"
        assert request.headers["authorization"] == "Bearer test-service-role-key"
        assert json.loads(request.content) == {
            "p_user_id": str(USER.id),
            "p_email": USER.email,
            "p_title": "New chat",
        }
        return httpx.Response(200, json=ROW)

    clients = transport(handler)
    thread = asyncio.run(with_store(lambda store: store.create_thread("New chat")))
    assert thread.id == THREAD_ID
    assert "userId" not in thread.model_dump(by_alias=True)
    assert clients and all(client.is_closed for client in clients)


def test_paginated_reads_use_user_jwt_and_explicit_owner_filter(transport):
    thread = Thread(**{key: value for key, value in ROW.items() if key != "user_id"})
    cursor = encode_cursor(thread)

    def handler(request):
        assert request.headers["apikey"] == "test-anon-key"
        assert request.headers["authorization"] == "Bearer user-token"
        params = request.url.params
        assert params["user_id"] == f"eq.{USER.id}"
        assert params["order"] == "updated_at.desc,id.desc"
        assert params["limit"] == "2"
        assert "updated_at.lt." in params["or"]
        return httpx.Response(200, json=[ROW, {**ROW, "id": str(uuid4())}])

    transport(handler)
    page = asyncio.run(with_store(lambda store: store.list_threads(1, cursor)))
    assert len(page.threads) == 1 and page.next_cursor == cursor


def test_history_checks_ownership_before_reading_messages(transport):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        assert request.url.params["id"] == f"eq.{THREAD_ID}"
        assert request.url.params["user_id"] == f"eq.{USER.id}"
        return httpx.Response(200, json=[])

    transport(handler)
    with pytest.raises(ChatError) as error:
        asyncio.run(with_store(lambda store: store.messages(THREAD_ID, 100, 0)))
    assert error.value.status_code == 404
    assert paths == ["/rest/v1/chat_threads"]


def test_history_is_sdk_shaped_and_paginated(transport):
    message_id = uuid4()

    def handler(request):
        if request.url.path.endswith("chat_threads"):
            return httpx.Response(200, json=[ROW])
        assert request.url.params["thread_id"] == f"eq.{THREAD_ID}"
        assert request.url.params["sequence"] == "gt.1"
        assert request.url.params["order"] == "sequence.asc"
        assert request.url.params["limit"] == "2"
        message = {
            "id": str(message_id),
            "role": "assistant",
            "sequence": 2,
            "created_at": ROW["created_at"],
            "parts": [{"type": "text", "text": "Stub response"}],
        }
        return httpx.Response(200, json=[message, {**message, "sequence": 3}])

    transport(handler)
    page = asyncio.run(with_store(lambda store: store.messages(THREAD_ID, 1, 1)))
    assert page.messages[0].id == message_id
    assert page.next_after_sequence == 2
    assert page.messages[0].parts[0].text == "Stub response"


def test_transactional_rpc_arguments_and_stable_turn_ids(transport):
    assistant_id, attempt_id, message_id = uuid4(), uuid4(), uuid4()
    calls = []

    def handler(request):
        params = json.loads(request.content)
        calls.append(request.url.path)
        assert params["p_user_id"] == str(USER.id)
        assert params["p_thread_id"] == str(THREAD_ID)
        assert request.headers["authorization"] == "Bearer test-service-role-key"
        if request.url.path.endswith("chat_accept_turn"):
            assert params["p_message_id"] == str(message_id)
            assert params["p_text"] == "Hi"
            return httpx.Response(
                200,
                json={
                    "assistantId": str(assistant_id),
                    "attemptId": str(attempt_id),
                    "replay": False,
                },
            )
        assert params["p_assistant_id"] == str(assistant_id)
        assert params["p_attempt_id"] == str(attempt_id)
        return httpx.Response(200, json={})

    transport(handler)

    async def action(store):
        turn = await store.accept(THREAD_ID, message_id, "Hi")
        await store.complete(THREAD_ID, turn, "Stub response")
        await store.abandon(THREAD_ID, turn)

    asyncio.run(with_store(action))
    assert [path.split("/")[-1] for path in calls] == [
        "chat_accept_turn",
        "chat_complete_turn",
        "chat_abandon_turn",
    ]


@pytest.mark.parametrize(
    "code,status",
    [
        ("PT404", 404),
        ("PT409", 409),
        ("PT422", 422),
        ("23505", 409),
        ("PGRST301", 401),
        ("PGRST303", 401),
        ("XX000", 502),
    ],
)
def test_rpc_errors_are_sanitized(transport, code, status):
    transport(
        lambda request: httpx.Response(
            400,
            json={
                "code": code,
                "message": "private SQL details",
                "details": None,
                "hint": None,
            },
        )
    )
    with pytest.raises(ChatError) as error:
        asyncio.run(with_store(lambda store: store.accept(THREAD_ID, uuid4(), "hi")))
    assert error.value.status_code == status
    assert "private" not in error.value.detail


def test_network_failure_maps_to_503(transport):
    def handler(request):
        raise httpx.ReadTimeout("private host details", request=request)

    transport(handler)
    with pytest.raises(ChatError) as error:
        asyncio.run(with_store(lambda store: store.list_threads(50, None)))
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64",
        "!!!",
        base64.urlsafe_b64encode(b"null").decode(),
        base64.urlsafe_b64encode(b'["2026-01-01", "invalid"]').decode(),
        base64.urlsafe_b64encode(b'["2026-01-01T00:00:00Z", {}]').decode(),
    ],
)
def test_bad_cursors_are_validation_errors(cursor):
    with pytest.raises(ChatError) as error:
        decode_cursor(cursor)
    assert error.value.status_code == 422


def test_overall_storage_timeout_is_bounded(transport, monkeypatch):
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=[])

    transport(handler)
    monkeypatch.setattr(settings, "supabase_request_timeout_seconds", 0.001)
    with pytest.raises(ChatError) as error:
        asyncio.run(with_store(lambda store: store.list_threads(50, None)))
    assert error.value.status_code == 503


def test_privileged_client_cannot_carry_user_token():
    async def run():
        async with managed_client(access_token="token", privileged=True):
            pytest.fail("Mixed authority client must not be created")

    with pytest.raises(ValueError):
        asyncio.run(run())
