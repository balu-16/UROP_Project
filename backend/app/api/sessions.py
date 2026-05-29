from fastapi import APIRouter, Depends

from app.api.dependencies import app_state, current_user, get_db
from app.database import AppDatabase
from app.models import SessionCreateRequest

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
async def list_sessions(user: dict = Depends(current_user), state=Depends(app_state)):
    state.metrics.record_request("sessions")
    return await state.session_service.list(user["_id"])


@router.post("/sessions")
async def create_session(payload: SessionCreateRequest, user: dict = Depends(current_user), state=Depends(app_state)):
    state.metrics.record_request("create-session")
    return await state.session_service.create(user["_id"], payload.title)


@router.get("/chat-history/{session_id}")
async def chat_history(session_id: str, user: dict = Depends(current_user), db: AppDatabase = Depends(get_db), state=Depends(app_state)):
    state.metrics.record_request("chat-history")
    session = await db.collection("chat_sessions").find_one({"_id": session_id, "user_id": user["_id"]})
    if not session:
        return {"session": None, "messages": []}
    messages = await db.collection("messages").find({"session_id": session_id, "user_id": user["_id"]}).sort("created_at", 1).to_list(500)
    return {"session": session, "messages": messages}

