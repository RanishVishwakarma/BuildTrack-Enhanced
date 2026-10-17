from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.core.access import ensure_project_access, own_worker_ids
from app.core.permissions import ensure_permission, has_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.documents.db import create_document, delete_document, get_document, list_documents
from app.modules.documents.models import Document

router = APIRouter()

UPLOAD_DIR = Path(__file__).resolve().parents[4] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def serialize_doc(doc: dict) -> dict:
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.post("/upload", response_model=Document)
async def upload_document_endpoint(
    file: UploadFile = File(...),
    category: str | None = Form(default=None),
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Upload a document and store metadata in MongoDB."""
    ensure_permission(current_user, "documents.manage")

    content = await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty files are not allowed")
    if size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 10 MB limit")

    safe_name = file.filename.replace(" ", "_") if file.filename else "upload.bin"
    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
    destination = UPLOAD_DIR / stored_name
    destination.write_bytes(content)

    metadata = {
        "filename": file.filename or stored_name,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": size,
        "storage_path": str(destination),
        "uploaded_by": str(current_user["_id"]),
        "category": category,
    }
    document = await create_document(db, metadata)
    return Document(**serialize_doc(document))


@router.get("/", response_model=list[Document])
async def list_documents_endpoint(
    skip: int = 0,
    limit: int = 20,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "documents.read.assigned")
    docs = await list_documents(db, skip, limit)
    return [Document(**serialize_doc(item)) for item in docs]


@router.get("/{document_id}", response_model=Document)
async def get_document_endpoint(
    document_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "documents.read.assigned")
    document = await get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return Document(**serialize_doc(document))


@router.get("/{document_id}/download")
async def download_document_endpoint(
    document_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "documents.read.assigned")
    document = await get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path = Path(document.get("storage_path", ""))
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found")

    return FileResponse(
        path=str(file_path),
        media_type=document.get("content_type") or "application/octet-stream",
        filename=document.get("filename") or file_path.name,
    )


@router.delete("/{document_id}")
async def delete_document_endpoint(
    document_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    ensure_permission(current_user, "documents.manage")

    document = await get_document(db, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path = Path(document.get("storage_path", ""))
    deleted = await delete_document(db, document_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if file_path.exists() and file_path.is_file():
        file_path.unlink()

    return {"message": "Document deleted successfully"}
