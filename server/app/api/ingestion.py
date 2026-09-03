from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import app_state, current_user, get_db
from app.database import AppDatabase

MAX_FILES_PER_REQUEST = 20

router = APIRouter(tags=["ingestion"])


async def _index_impl(
    files: list[UploadFile],
    session_id: str,
    user: dict,
    db: AppDatabase,
    state,
):
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Maximum {MAX_FILES_PER_REQUEST} files per request.",
        )
    if not session_id or not session_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An open chat is required: pass session_id of the chat this upload belongs to.",
        )
    session = await db.collection("chat_sessions").find_one(
        {"_id": session_id, "user_id": user["_id"]}
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )
    state.metrics.record_request("index-documents")
    try:
        return await state.ingestion_service.index_uploads(user["_id"], session_id, files)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("/index-documents")
async def index_documents(
    files: list[UploadFile] = File(...),
    session_id: str = Form(...),
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _index_impl(files, session_id, user, db, state)


@router.post("/api/index-documents")
async def index_documents_api(
    files: list[UploadFile] = File(...),
    session_id: str = Form(...),
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _index_impl(files, session_id, user, db, state)


@router.post("/api/ingestion")
async def ingestion_api(
    files: list[UploadFile] = File(...),
    session_id: str = Form(...),
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _index_impl(files, session_id, user, db, state)


@router.post("/ingestion")
async def ingestion(
    files: list[UploadFile] = File(...),
    session_id: str = Form(...),
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _index_impl(files, session_id, user, db, state)
