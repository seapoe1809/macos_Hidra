"""Bills endpoints (dashboard box 4 — standalone bills screen).

Add a bill by npub + amount + date with an optional PDF/photo attachment,
search bills by npub, and mark a bill paid (stamping when the button was
clicked). Attachments are stored on disk under config.UPLOAD_DIR.
"""

import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend import config, db

router = APIRouter(prefix="/api/bills", tags=["bills"])

# Accepted attachment types — a scanned bill (PDF) or a photo of one.
_ALLOWED_TYPES = {
    "application/pdf",
    "image/png", "image/jpeg", "image/jpg", "image/webp", "image/heic", "image/gif",
}


@router.post("/add")
async def add_bill(
    member_npub: str = Form(...),
    amount_usd: float = Form(...),
    bill_date: str = Form(...),
    file: UploadFile | None = File(None),
):
    attachment = None
    if file is not None and file.filename:
        if file.content_type not in _ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="Attach a PDF or image file")
        data = await file.read()
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
            )
        os.makedirs(config.UPLOAD_DIR, exist_ok=True)
        # Use only our own extension/name; never trust the client path.
        ext = os.path.splitext(os.path.basename(file.filename))[1][:12]
        stored_name = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(config.UPLOAD_DIR, stored_name)
        with open(path, "wb") as out:
            out.write(data)
        attachment = {"path": path, "name": os.path.basename(file.filename), "type": file.content_type}

    return db.add_bill_record(member_npub.strip(), amount_usd, bill_date.strip(), attachment)


@router.get("/search")
def search(npub: str | None = None):
    return {"bills": db.search_bills(npub)}


@router.post("/{bill_id}/paid")
def mark_paid(bill_id: int):
    bill = db.mark_bill_paid(bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


@router.get("/{bill_id}/attachment")
def attachment(bill_id: int):
    bill = db.get_bill(bill_id)
    if not bill or not bill.get("attachment_path"):
        raise HTTPException(status_code=404, detail="No attachment for this bill")
    if not os.path.exists(bill["attachment_path"]):
        raise HTTPException(status_code=404, detail="Attachment file missing")
    return FileResponse(
        bill["attachment_path"],
        media_type=bill.get("attachment_type") or "application/octet-stream",
        filename=bill.get("attachment_name"),
        content_disposition_type="inline",  # view in browser tab
    )
