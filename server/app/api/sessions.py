from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import app_state, current_user, get_db
from app.database import AppDatabase
from app.models import SessionCreateRequest, TruncateRequest

router = APIRouter(tags=["sessions"])
api_router = APIRouter(tags=["sessions"])


async def _list_impl(user: dict, state):
    state.metrics.record_request("sessions")
    return await state.session_service.list(user["_id"])


async def _create_impl(payload: SessionCreateRequest, user: dict, state):
    state.metrics.record_request("create-session")
    return await state.session_service.create(user["_id"], payload.title)


async def _history_impl(session_id: str, user: dict, db: AppDatabase, state):
    state.metrics.record_request("chat-history")
    session = await db.collection("chat_sessions").find_one({"_id": session_id, "user_id": user["_id"]})
    if not session:
        return {"session": None, "messages": []}
    messages = await db.collection("messages").find({"session_id": session_id, "user_id": user["_id"]}).sort("created_at", 1).to_list(500)
    return {"session": session, "messages": messages}


async def _truncate_impl(session_id: str, payload: TruncateRequest, user: dict, db: AppDatabase, state):
    """Delete a message and everything after it (edit-and-resend support)."""
    state.metrics.record_request("truncate-session")
    session = await db.collection("chat_sessions").find_one(
        {"_id": session_id, "user_id": user["_id"]}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    message = await db.collection("messages").find_one(
        {"_id": payload.message_id, "session_id": session_id}
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    result = await db.collection("messages").delete_many(
        {
            "session_id": session_id,
            "created_at": {"$gte": message["created_at"]},
        }
    )
    await state.session_service.touch(session_id)
    return {"ok": True, "deleted": result.deleted_count}


@router.get("/sessions")
async def list_sessions(user: dict = Depends(current_user), state=Depends(app_state)):
    return await _list_impl(user, state)


@router.post("/sessions")
async def create_session(payload: SessionCreateRequest, user: dict = Depends(current_user), state=Depends(app_state)):
    return await _create_impl(payload, user, state)


@router.get("/chat-history/{session_id}")
async def chat_history(session_id: str, user: dict = Depends(current_user), db: AppDatabase = Depends(get_db), state=Depends(app_state)):
    return await _history_impl(session_id, user, db, state)


@router.post("/sessions/{session_id}/truncate")
async def truncate_session(
    session_id: str,
    payload: TruncateRequest,
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _truncate_impl(session_id, payload, user, db, state)


@api_router.get("/api/sessions")
async def list_sessions_api(user: dict = Depends(current_user), state=Depends(app_state)):
    return await _list_impl(user, state)


@api_router.post("/api/sessions")
async def create_session_api(payload: SessionCreateRequest, user: dict = Depends(current_user), state=Depends(app_state)):
    return await _create_impl(payload, user, state)


@api_router.get("/api/chat-history/{session_id}")
async def chat_history_api(session_id: str, user: dict = Depends(current_user), db: AppDatabase = Depends(get_db), state=Depends(app_state)):
    return await _history_impl(session_id, user, db, state)


@api_router.post("/api/sessions/{session_id}/truncate")
async def truncate_session_api(
    session_id: str,
    payload: TruncateRequest,
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _truncate_impl(session_id, payload, user, db, state)

