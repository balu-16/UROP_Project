from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import app_state, current_user
from app.models import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request, user: dict = Depends(current_user), state=Depends(app_state)):
    state.metrics.record_request("chat")
    return StreamingResponse(
        state.chat_service.stream(user, payload.message, payload.session_id, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

