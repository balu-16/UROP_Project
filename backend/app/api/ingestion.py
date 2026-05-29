from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.dependencies import app_state, current_user

MAX_FILES_PER_REQUEST = 20

router = APIRouter(tags=["ingestion"])


@router.post("/index-documents")
async def index_documents(
    files: list[UploadFile] = File(...),
    user: dict = Depends(current_user),
    state=Depends(app_state),
):
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files. Maximum {MAX_FILES_PER_REQUEST} files per request.",
        )
    state.metrics.record_request("index-documents")
    return await state.ingestion_service.index_uploads(user["_id"], files)
