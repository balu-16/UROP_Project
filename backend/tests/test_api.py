import os
import shutil
from pathlib import Path

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_URL", "memory://tests")
os.environ.setdefault("MONGODB_DB_NAME", "ragnostic_tests")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("MOCK_OPENROUTER", "true")
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
    storage = Path(os.environ["STORAGE_DIR"])
    if storage.exists():
        shutil.rmtree(storage)
    app = create_app()
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


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
        "RAGnostic uses contextual bandits for adaptive retrieval. "
        "Graph RAG expands entity neighborhoods with NetworkX. "
        "Kimi K2.6 streams answers through OpenRouter. "
    ) * 80
    ingest = await client.post(
        "/index-documents",
        headers=headers,
        files={"files": ("ragnostic.md", document, "text/markdown")},
    )
    assert ingest.status_code == 200, ingest.text
    assert ingest.json()["chunk_count"] >= 1
    assert ingest.json()["vector_index_size"] >= 1

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
        "hybrid",
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
