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
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided.",
        )
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Maximum {MAX_FILES_PER_REQUEST} files per request.",
        )
    # Total-request cap (declared sizes when available): 20x25MB must not
    # become a 500MB RAM / embedding bill in one request.
    try:
        from app.config import get_settings as _get_settings

        _total_cap = int(_get_settings().total_upload_max_mb) * 1024 * 1024
        _declared = [getattr(f, "size", None) for f in files]
        if all(isinstance(s, int) for s in _declared):
            if sum(_declared or [0]) > _total_cap:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Combined upload size exceeds the per-request limit.",
                )
    except HTTPException:
        raise
    except Exception:
        pass
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
        msg = str(exc)
        # Oversize payloads deserve 413, not generic 422.
        if "too large" in msg.lower() or "exceeds" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=msg,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=msg,
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


async def _delete_impl(document_id: str, session_id: str, user: dict, state):
    """Un-upload: remove a document and all its artifacts for this chat."""
    if not document_id or not document_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_id is required.",
        )
    if not session_id or not session_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required.",
        )
    state.metrics.record_request("delete-document")
    report = await state.ingestion_service.delete_document(
        user["_id"], session_id, document_id
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found in this chat.",
        )
    return {"ok": True, "deleted": report}


async def _list_impl(session_id: str, user: dict, db: AppDatabase, state):
    """List indexed documents for one chat (session-scoped, ownership-checked).

    Server truth for the frontend strip: localStorage stays as offline cache,
    but this endpoint reconciles on load / new devices.
    """
    if not session_id or not session_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required.",
        )
    state.metrics.record_request("list-documents")
    rows = (
        await db.collection("indexed_documents")
        .find({"user_id": user["_id"], "session_id": session_id})
        .sort("created_at", 1)
        .to_list(500)
    )
    documents = [
        {
            "_id": r.get("_id"),
            "filename": r.get("filename"),
            "chunk_count": r.get("chunk_count", 0),
            "created_at": r.get("created_at"),
        }
        for r in rows
        if r.get("_id")
    ]
    return {"documents": documents}


@router.get("/documents")
async def list_documents(
    session_id: str,
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _list_impl(session_id, user, db, state)


@router.get("/api/documents")
async def list_documents_api(
    session_id: str,
    user: dict = Depends(current_user),
    db: AppDatabase = Depends(get_db),
    state=Depends(app_state),
):
    return await _list_impl(session_id, user, db, state)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    session_id: str,
    user: dict = Depends(current_user),
    state=Depends(app_state),
):
    return await _delete_impl(document_id, session_id, user, state)


@router.delete("/api/documents/{document_id}")
async def delete_document_api(
    document_id: str,
    session_id: str,
    user: dict = Depends(current_user),
    state=Depends(app_state),
):
    return await _delete_impl(document_id, session_id, user, state)
