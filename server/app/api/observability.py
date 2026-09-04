import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status

from app.api.dependencies import app_state, current_user, get_db
from app.database import AppDatabase
from app.models import FeedbackRequest
from app.utils.ids import new_id
from app.utils.logging import get_logger
from app.utils.time import utc_now

logger = get_logger(__name__)

router = APIRouter(tags=["observability"])


async def _health_payload():
    # Liveness only: process is up. Use /ready for dependency checks.
    return {"ok": True, "service": "RAGnostic"}


@router.get("/health")
async def health():
    return await _health_payload()


@router.get("/api/health")
async def health_api():
    return await _health_payload()


async def _ready_payload(state) -> dict:
    """Readiness: dependencies the request path needs (DB, vector index)."""
    checks: dict[str, str] = {}
    try:
        db = getattr(state, "db", None)
        if db is None:
            checks["database"] = "missing"
        else:
            await db.collection("users").find_one({"_id": "__health__"})
            checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
    try:
        vs = getattr(state, "vector_store", None)
        if vs is None or getattr(vs, "collection", None) is None:
            checks["vector_store"] = "missing"
        else:
            await asyncio.to_thread(vs.size)
            checks["vector_store"] = "ok"
    except Exception as exc:
        checks["vector_store"] = f"error: {exc}"
    ready = all(v == "ok" for v in checks.values())
    return {"ready": ready, "checks": checks}


@router.get("/ready")
async def ready(state=Depends(app_state)):
    payload = await _ready_payload(state)
    return payload


@router.get("/api/ready")
async def ready_api(state=Depends(app_state)):
    return await _ready_payload(state)


async def _app_config_payload():
    return {
        "name": "RAGnostic",
        "features": ["adaptive-retrieval", "graph-rag", "streaming", "threshold-policy"],
    }


@router.get("/app-config")
async def app_config():
    return await _app_config_payload()


@router.get("/api/app-config")
async def app_config_api():
    return await _app_config_payload()


async def _metrics_snapshot(state) -> dict:
    state.metrics.record_request("metrics")
    graph = getattr(state, "graph_store", None)
    stats = graph.stats() if graph and hasattr(graph, "stats") else {"nodes": 0, "edges": 0}
    try:
        size = await asyncio.to_thread(state.vector_store.size)
    except Exception as exc:
        logger.warning("metrics vector size failed: %s", exc)
        size = -1
    return state.metrics.snapshot(size, stats)


@router.get("/metrics")
async def metrics(user: dict = Depends(current_user), state=Depends(app_state)):
    return await _metrics_snapshot(state)


@router.get("/api/metrics")
async def metrics_api(user: dict = Depends(current_user), state=Depends(app_state)):
    return await _metrics_snapshot(state)


async def _retrieval_debug_impl(session_id: str | None, limit: int, user: dict, db: AppDatabase, state):
    state.metrics.record_request("retrieval-debug")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    query = {"user_id": user["_id"]}
    if session_id:
        query["session_id"] = session_id
    logs = await db.collection("retrieval_logs").find(query).sort("created_at", -1).limit(limit).to_list(limit)
    return {"logs": logs}


@router.get("/retrieval-debug")
async def retrieval_debug(
    session_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _retrieval_debug_impl(session_id, limit, user, db, state)


@router.get("/api/retrieval-debug")
async def retrieval_debug_api(
    session_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _retrieval_debug_impl(session_id, limit, user, db, state)


@router.post("/feedback")
async def feedback(payload: FeedbackRequest, user: dict = Depends(current_user), db: AppDatabase = Depends(get_db), state=Depends(app_state)):
    return await _feedback_impl(payload, user, db, state)


async def _feedback_impl(payload: FeedbackRequest, user: dict, db: AppDatabase, state):
    state.metrics.record_request("feedback")
    message = await db.collection("messages").find_one({"_id": payload.message_id, "user_id": user["_id"]})
    if not message:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Message not found or access denied",
        )
    if message.get("session_id") != payload.session_id:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="session_id does not match the message's chat.",
        )
    record = {
        "_id": new_id("fb"),
        "user_id": user["_id"],
        "session_id": payload.session_id,
        "message_id": payload.message_id,
        "rating": payload.rating,
        "comment": payload.comment,
        "created_at": utc_now(),
    }
    await db.collection("reward_logs").insert_one(record)
    return {"ok": True, "feedback": record}


@router.post("/api/feedback")
async def feedback_api(payload: FeedbackRequest, user: dict = Depends(current_user), db: AppDatabase = Depends(get_db), state=Depends(app_state)):
    return await _feedback_impl(payload, user, db, state)

