"""HTTP and orchestration tests with a deliberately in-memory test double.

These prove API behavior, not PostgreSQL locking, constraints, or RLS.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Annotated
from uuid import uuid4

import pytest
from app.api.chat import get_chat_store
from app.auth import dependencies
from app.auth.dependencies import CurrentUser, get_current_user
from app.chat.body_limit import MAX_CHAT_BODY_BYTES
from app.chat.errors import ChatError
from app.chat.schemas import MessagePage, StoredMessage, Thread, ThreadPage, Turn
from app.chat.streaming import STUB_RESPONSE, stream_turn
from app.config import settings
from app.main import app
from fastapi import Depends
from fastapi.testclient import TestClient

ALICE, BOB = uuid4(), uuid4()


class MemoryStore:
    def __init__(self, owner=ALICE):
        self.owner = owner
        self.thread = Thread(
            id=uuid4(),
            title="New chat",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.history = []
        self.turns = {}
        self.saved = False
        self.abandoned = False
        self.fail_completion = False

    async def create_thread(self, title):
        self.thread.title = title
        return self.thread

    async def list_threads(self, limit, cursor):
        return ThreadPage(threads=[self.thread])

    async def messages(self, thread_id, limit, after_sequence):
        if thread_id != self.thread.id:
            raise ChatError(404, "Thread not found")
        rows = [m for m in self.history if m.metadata.sequence > after_sequence]
        return MessagePage(
            thread=self.thread,
            messages=rows[:limit],
            next_after_sequence=(
                rows[limit - 1].metadata.sequence if len(rows) > limit else None
            ),
        )

    async def accept(self, thread_id, message_id, text):
        if thread_id != self.thread.id:
            raise ChatError(404, "Thread not found")
        if message_id in self.turns:
            turn, old_text = self.turns[message_id]
            if text != old_text:
                raise ChatError(409, "Turn conflict")
            if self.saved:
                return turn.model_copy(
                    update={"replay": True, "content": STUB_RESPONSE}
                )
            raise ChatError(409, "Turn conflict")
        turn = Turn(assistant_id=uuid4(), attempt_id=uuid4())
        self.turns[message_id] = (turn, text)
        self.history.append(
            StoredMessage(
                id=message_id,
                role="user",
                parts=[{"type": "text", "text": text}],
                metadata={
                    "sequence": len(self.history) + 1,
                    "createdAt": datetime.now(UTC),
                },
            )
        )
        return turn

    async def complete(self, thread_id, turn, text):
        if self.fail_completion:
            raise ChatError(502, "private database diagnostics")
        self.saved = True
        self.history.append(
            StoredMessage(
                id=turn.assistant_id,
                role="assistant",
                parts=[{"type": "text", "text": text}],
                metadata={
                    "sequence": len(self.history) + 1,
                    "createdAt": datetime.now(UTC),
                },
            )
        )

    async def abandon(self, thread_id, turn):
        self.abandoned = True


@pytest.fixture
def chat_client(monkeypatch):
    stores = {ALICE: MemoryStore(ALICE), BOB: MemoryStore(BOB)}

    async def verify(*, jwt):
        user = ALICE if jwt == "alice" else BOB
        return SimpleNamespace(
            user=SimpleNamespace(id=str(user), email=f"{jwt}@example.com")
        )

    @asynccontextmanager
    async def managed_client():
        yield SimpleNamespace(auth=SimpleNamespace(get_user=verify))

    def fake_store(user: Annotated[CurrentUser, Depends(get_current_user)]):
        return stores[user.id]

    monkeypatch.setattr(dependencies, "managed_client", managed_client)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_chat_store] = fake_store
    try:
        with TestClient(app) as client:
            yield client, stores
    finally:
        app.dependency_overrides = previous


def body(store, *, message_id=None, text="Hello"):
    return {
        "threadId": str(store.thread.id),
        "trigger": "submit-message",
        "messages": [
            {
                "id": str(message_id or uuid4()),
                "role": "user",
                "parts": [{"type": "text", "text": text}],
            }
        ],
    }


def frames(response):
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/threads", None),
        ("POST", "/threads", {}),
        ("GET", f"/threads/{uuid4()}/messages", None),
        ("POST", "/chat/stream", {}),
    ],
)
def test_chat_requires_auth(method, path, payload):
    response = TestClient(app).request(method, path, json=payload)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_create_stream_and_reload(chat_client):
    client, stores = chat_client
    headers = {"Authorization": "Bearer alice"}
    store = stores[ALICE]
    created = client.post("/threads", json={}, headers=headers)
    assert created.status_code == 201
    assert set(created.json()) == {"id", "title", "createdAt", "updatedAt"}
    assert (
        client.get("/threads", headers=headers).json()["threads"][0] == created.json()
    )
    request = body(store)
    response = client.post("/chat/stream", json=request, headers=headers)
    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert response.headers["content-type"].startswith("text/event-stream")
    events = frames(response)
    assert [e["type"] for e in events[:2]] == ["start", "text-start"]
    assert [e["type"] for e in events[-2:]] == ["text-end", "finish"]
    assert response.text.endswith("data: [DONE]\n\n")
    assert (
        "".join(e["delta"] for e in events if e["type"] == "text-delta")
        == STUB_RESPONSE
    )
    history = client.get(f"/threads/{store.thread.id}/messages", headers=headers).json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
    assert history["messages"][1]["id"] == events[0]["messageId"]
    assert [m["metadata"]["sequence"] for m in history["messages"]] == [1, 2]
    page = client.get(
        f"/threads/{store.thread.id}/messages?limit=1", headers=headers
    ).json()
    assert page["nextAfterSequence"] == 1
    assert len(page["messages"]) == 1
    replay = client.post("/chat/stream", json=request, headers=headers)
    assert replay.status_code == 200
    assert frames(replay)[0] == events[0]
    assert len(store.history) == 2
    request["messages"][0]["parts"][0]["text"] = "Changed"
    assert client.post("/chat/stream", json=request, headers=headers).status_code == 409


def test_cross_user_and_missing_thread_return_404(chat_client):
    client, stores = chat_client
    headers = {"Authorization": "Bearer bob"}
    alice = stores[ALICE]
    listed = client.get("/threads", headers=headers).json()["threads"]
    assert str(alice.thread.id) not in [t["id"] for t in listed]
    response = client.get(f"/threads/{alice.thread.id}/messages", headers=headers)
    assert response.status_code == 404
    response = client.post("/chat/stream", json=body(alice), headers=headers)
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert not alice.history


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(trigger="regenerate-message"),
        lambda p: p.update(userId=str(BOB)),
        lambda p: p.update(threadId="invalid"),
        lambda p: p.update(messages=[]),
        lambda p: p["messages"].append(p["messages"][0].copy()),
        lambda p: p["messages"][0].update(role="assistant"),
        lambda p: p["messages"][0].update(id="invalid"),
        lambda p: p["messages"][0].update(parts=[{"type": "file", "url": "x"}]),
        lambda p: p["messages"][0]["parts"][0].update(text="  "),
        lambda p: p["messages"][0]["parts"][0].update(text="x" * 16001),
    ],
)
def test_invalid_stream_requests(chat_client, change):
    client, stores = chat_client
    request = body(stores[ALICE])
    change(request)
    assert (
        client.post(
            "/chat/stream", json=request, headers={"Authorization": "Bearer alice"}
        ).status_code
        == 422
    )
    assert not stores[ALICE].history


@pytest.mark.parametrize("path", ["/chat/stream", "/threads"])
def test_body_limit_before_json_parsing(chat_client, path):
    client, _ = chat_client
    response = client.post(
        path,
        content=b"x" * (MAX_CHAT_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize("query", ["limit=0", "limit=501", "afterSequence=-1"])
def test_history_query_limits(chat_client, query):
    client, stores = chat_client
    response = client.get(
        f"/threads/{stores[ALICE].thread.id}/messages?{query}",
        headers={"Authorization": "Bearer alice"},
    )
    assert response.status_code == 422


def test_persistence_failure_is_sse_error_not_success(chat_client):
    client, stores = chat_client
    stores[ALICE].fail_completion = True
    response = client.post(
        "/chat/stream",
        json=body(stores[ALICE]),
        headers={"Authorization": "Bearer alice"},
    )
    assert response.status_code == 200  # headers already sent
    assert "error" in [e["type"] for e in frames(response)]
    assert "finish" not in [e["type"] for e in frames(response)]
    assert "private database" not in response.text
    assert len(stores[ALICE].history) == 1
    assert stores[ALICE].abandoned


def test_active_turn_conflict_is_json_before_stream_headers(chat_client, monkeypatch):
    client, stores = chat_client

    async def busy(*args):
        raise ChatError(409, "Thread is busy")

    monkeypatch.setattr(stores[ALICE], "accept", busy)
    response = client.post(
        "/chat/stream",
        json=body(stores[ALICE]),
        headers={"Authorization": "Bearer alice"},
    )
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/json"
    assert "x-vercel-ai-ui-message-stream" not in response.headers


def test_commit_precedes_finish():
    async def run():
        store = MemoryStore()
        turn = await store.accept(store.thread.id, uuid4(), "hi")
        async for frame in stream_turn(store, store.thread.id, turn):
            if '"type": "finish"' in frame:
                assert store.saved
        assert not store.abandoned

    asyncio.run(run())


def test_cancellation_releases_reservation_without_saving_answer():
    async def run():
        store = MemoryStore()
        turn = await store.accept(store.thread.id, uuid4(), "hi")
        started = asyncio.Event()

        async def consume():
            async for _ in stream_turn(store, store.thread.id, turn):
                started.set()

        task = asyncio.create_task(consume())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert store.abandoned and not store.saved

    asyncio.run(run())


def test_turn_timeout_does_not_persist_partial_answer(monkeypatch):
    monkeypatch.setattr(settings, "chat_turn_timeout_seconds", 0.001)

    async def run():
        store = MemoryStore()
        turn = await store.accept(store.thread.id, uuid4(), "hi")
        output = [frame async for frame in stream_turn(store, store.thread.id, turn)]
        assert any('"type": "error"' in frame for frame in output)
        assert not any('"type": "finish"' in frame for frame in output)
        assert store.abandoned and not store.saved

    asyncio.run(run())
