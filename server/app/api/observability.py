from fastapi import APIRouter, Depends, HTTPException, status as http_status

from app.api.dependencies import app_state, current_user, get_db
from app.database import AppDatabase
from app.models import FeedbackRequest
from app.utils.ids import new_id
from app.utils.time import utc_now

router = APIRouter(tags=["observability"])


async def _health_payload():
    return {"ok": True, "service": "RAGnostic"}


@router.get("/health")
async def health():
    return await _health_payload()


@router.get("/api/health")
async def health_api():
    return await _health_payload()


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


@router.get("/metrics")
async def metrics(user: dict = Depends(current_user), state=Depends(app_state)):
    state.metrics.record_request("metrics")
    graph = getattr(state, "graph_store", None)
    stats = graph.stats() if graph and hasattr(graph, "stats") else {"nodes": 0, "edges": 0}
    return state.metrics.snapshot(state.vector_store.size(), stats)


@router.get("/api/metrics")
async def metrics_api(user: dict = Depends(current_user), state=Depends(app_state)):
    state.metrics.record_request("metrics")
    graph = getattr(state, "graph_store", None)
    stats = graph.stats() if graph and hasattr(graph, "stats") else {"nodes": 0, "edges": 0}
    return state.metrics.snapshot(state.vector_store.size(), stats)


async def _retrieval_debug_impl(session_id: str | None, limit: int, user: dict, db: AppDatabase, state):
    state.metrics.record_request("retrieval-debug")
    query = {"user_id": user["_id"]}
    if session_id:
        query["session_id"] = session_id
    logs = await db.collection("retrieval_logs").find(query).sort("created_at", -1).limit(min(limit, 100)).to_list(min(limit, 100))
    return {"logs": logs}


@router.get("/retrieval-debug")
async def retrieval_debug(
    session_id: str | None = None,
    limit: int = 20,
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _retrieval_debug_impl(session_id, limit, user, db, state)


@router.get("/api/retrieval-debug")
async def retrieval_debug_api(
    session_id: str | None = None,
    limit: int = 20,
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _retrieval_debug_impl(session_id, limit, user, db, state)


@router.post("/feedback")
async def feedback(payload: FeedbackRequest, user: dict = Depends(current_user), db: AppDatabase = Depends(get_db), state=Depends(app_state)):
    state.metrics.record_request("feedback")
    message = await db.collection("messages").find_one({"_id": payload.message_id, "user_id": user["_id"]})
    if not message:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Message not found or access denied",
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
    return await feedback(payload, user, db, state)

