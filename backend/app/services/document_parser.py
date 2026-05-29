from pathlib import Path

from fastapi import HTTPException, UploadFile, status


class DocumentParser:
    supported_extensions = {".pdf", ".txt", ".md", ".markdown"}

    async def parse_upload(self, file: UploadFile, max_mb: int) -> tuple[str, dict]:
        filename = file.filename or "document.txt"
        suffix = Path(filename).suffix.lower()
        if suffix not in self.supported_extensions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {suffix}")
        data = await file.read()
        if len(data) > max_mb * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is too large")
        if suffix == ".pdf":
            text = self._parse_pdf(data)
        else:
            text = data.decode("utf-8", errors="ignore")
        return text, {"source": filename, "extension": suffix, "size_bytes": len(data)}

    def _parse_pdf(self, data: bytes) -> str:
        try:
            from pypdf import PdfReader
            from io import BytesIO

            reader = PdfReader(BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to parse PDF: {exc}") from exc

