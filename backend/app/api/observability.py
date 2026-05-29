from fastapi import APIRouter, Depends

from app.api.dependencies import app_state, current_user, get_db
from app.database import AppDatabase
from app.models import FeedbackRequest
from app.utils.ids import new_id
from app.utils.time import utc_now

router = APIRouter(tags=["observability"])


@router.get("/health")
async def health():
    return {"ok": True, "service": "RAGnostic"}


@router.get("/app-config")
async def app_config():
    return {
        "name": "RAGnostic",
        "model": "moonshotai/kimi-k2.6:free",
        "features": ["adaptive-retrieval", "graph-rag", "streaming", "contextual-bandits"],
    }


@router.get("/metrics")
async def metrics(user: dict = Depends(current_user), state=Depends(app_state)):
    state.metrics.record_request("metrics")
    return state.metrics.snapshot(state.vector_store.size(), state.entity_graph.stats())


@router.get("/retrieval-debug")
async def retrieval_debug(
    session_id: str | None = None,
    limit: int = 20,
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    state.metrics.record_request("retrieval-debug")
    query = {"user_id": user["_id"]}
    if session_id:
        query["session_id"] = session_id
    logs = await db.collection("retrieval_logs").find(query).sort("created_at", -1).limit(min(limit, 100)).to_list(min(limit, 100))
    return {"logs": logs}


@router.post("/feedback")
async def feedback(payload: FeedbackRequest, user: dict = Depends(current_user), db: AppDatabase = Depends(get_db), state=Depends(app_state)):
    state.metrics.record_request("feedback")
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
    message = await db.collection("messages").find_one({"_id": payload.message_id, "user_id": user["_id"]})
    if message and message.get("selected_arm"):
        retrieval_log_id = message.get("retrieval_log_id")
        retrieval_log = await db.collection("retrieval_logs").find_one({"_id": retrieval_log_id}) if retrieval_log_id else None
        if retrieval_log:
            state.bandit.update(message["selected_arm"], retrieval_log.get("feature_vector", [0] * 7), payload.rating)
    return {"ok": True, "feedback": record}

