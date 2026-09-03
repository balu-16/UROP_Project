import os
import shutil
from pathlib import Path

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "memory://tests")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("DISABLE_LOCAL_MODELS", "true")
os.environ.setdefault(
    "STORAGE_DIR", str(Path(__file__).resolve().parents[1] / "storage_test")
)
os.environ.setdefault("JWT_SECRET", "test-secret-with-enough-length")

from app.config.settings import get_settings  # noqa: E402

get_settings.cache_clear()

from app.main import create_app  # noqa: E402


@pytest_asyncio.fixture()
async def client():
    import gc
    import time

    storage = Path(os.environ["STORAGE_DIR"])
    # Robust cleanup: previous Chroma client may still hold SQLite handles
    # briefly after shutdown; retry rmtree instead of failing with readonly DB.
    for _ in range(3):
        try:
            if storage.exists():
                shutil.rmtree(storage, ignore_errors=False)
            break
        except Exception:
            gc.collect()
            time.sleep(0.5)
            if storage.exists():
                shutil.rmtree(storage, ignore_errors=True)
                break
    app = create_app()
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    # Teardown: ensure Chroma handles released before next test's cleanup
    gc.collect()


async def auth_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/auth/signup",
        json={
            "name": "RAG Tester",
            "email": "tester@example.com",
            "password": "password123",
        },
    )
    if response.status_code == 409:
        response = await client.post(
            "/auth/login",
            json={"email": "tester@example.com", "password": "password123"},
        )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_health_and_config(client: AsyncClient):
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    config = await client.get("/app-config")
    assert config.status_code == 200
    assert config.json()["name"] == "RAGnostic"


@pytest.mark.asyncio
async def test_auth_refresh_logout_me(client: AsyncClient):
    response = await client.post(
        "/auth/signup",
        json={
            "name": "Auth User",
            "email": "auth@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "auth@example.com"
    refreshed = await client.post("/auth/refresh")
    assert refreshed.status_code == 200
    logged_out = await client.post("/auth/logout")
    assert logged_out.status_code == 200


@pytest.mark.asyncio
async def test_sessions_ingestion_retrieval_chat_feedback_metrics(client: AsyncClient):
    headers = await auth_headers(client)

    session = await client.post(
        "/sessions", headers=headers, json={"title": "Research test"}
    )
    assert session.status_code == 200, session.text
    session_id = session.json()["_id"]

    sessions = await client.get("/sessions", headers=headers)
    assert sessions.status_code == 200
    assert len(sessions.json()) >= 1

    document = (
        "RAGnostic uses threshold-based adaptive retrieval. "
        "Graph RAG expands entity neighborhoods over Postgres. "
        "Nemotron streams answers through the LLM gateway. "
    ) * 80
    ingest = await client.post(
        "/index-documents",
        headers=headers,
        files={"files": ("ragnostic.md", document, "text/markdown")},
        data={"session_id": session_id},
    )
    assert ingest.status_code == 200, ingest.text
    assert ingest.json()["chunk_count"] >= 1
    assert ingest.json()["vector_index_size"] >= 1

    # Uploads require an open chat: missing session -> 400, foreign session -> 404
    no_session = await client.post(
        "/index-documents",
        headers=headers,
        files={"files": ("ragnostic.md", document, "text/markdown")},
    )
    assert no_session.status_code in (400, 422), no_session.text
    foreign = await client.post(
        "/index-documents",
        headers=headers,
        files={"files": ("ragnostic.md", document, "text/markdown")},
        data={"session_id": "chat_doesnotexist"},
    )
    assert foreign.status_code == 404, foreign.text

    chat = await client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": session_id,
            "message": "How does RAGnostic choose retrieval strategies?",
        },
    )
    assert chat.status_code == 200, chat.text
    stream_text = chat.text
    assert "event: metadata" in stream_text
    assert "event: token" in stream_text
    assert "event: reward" in stream_text
    assert "event: done" in stream_text

    history = await client.get(f"/chat-history/{session_id}", headers=headers)
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert len(messages) >= 2
    assistant = [message for message in messages if message["role"] == "assistant"][-1]
    assert assistant["selected_arm"] in {
        "standard_rag",
        "graph_rag_1hop",
        "graph_rag_2hop",
    }

    debug = await client.get(
        "/retrieval-debug", headers=headers, params={"session_id": session_id}
    )
    assert debug.status_code == 200
    assert len(debug.json()["logs"]) >= 1

    feedback = await client.post(
        "/feedback",
        headers=headers,
        json={
            "message_id": assistant["_id"],
            "session_id": session_id,
            "rating": 0.9,
            "comment": "good",
        },
    )
    assert feedback.status_code == 200

    metrics = await client.get("/metrics", headers=headers)
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["vector_index_size"] >= 1
    assert "arm_distribution" in payload

    # Per-chat isolation: a second chat must not see the first chat's documents
    other = await client.post(
        "/sessions", headers=headers, json={"title": "Other chat"}
    )
    assert other.status_code == 200, other.text
    other_id = other.json()["_id"]
    other_chat = await client.post(
        "/chat",
        headers=headers,
        json={
            "session_id": other_id,
            "message": "How does RAGnostic choose retrieval strategies?",
        },
    )
    assert other_chat.status_code == 200, other_chat.text
    assert '"sources": []' in other_chat.text

    # Chatting without an open chat is rejected
    no_chat = await client.post(
        "/chat",
        headers=headers,
        json={"session_id": None, "message": "Hello?"},
    )
    assert no_chat.status_code == 200, no_chat.text
    assert "An open chat is required" in no_chat.text
