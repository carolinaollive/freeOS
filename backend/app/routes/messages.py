"""Message upload (Android) and download (iOS) routes."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import Transfer, TransferAttachment, TransferMessage, User
from ..schemas import (
    AttachmentResponse,
    AttachmentUploadResponse,
    MessageBatchResponse,
    MessageBatchUpload,
    MessageResponse,
)
from ..services import storage, transfer as transfer_service

router = APIRouter(prefix="/transfers/{transfer_id}/messages", tags=["messages"])


@router.post("", status_code=201)
async def upload_messages(
    transfer_id: UUID,
    batch: MessageBatchUpload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a batch of messages from the Android app.

    Messages are sent in batches of up to 500 to keep request sizes manageable.
    The Android app calls this repeatedly until all messages are uploaded,
    then calls POST /transfers/{id}/finalize.
    """
    transfer = await db.get(Transfer, transfer_id)
    if not transfer or transfer.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.status != "uploading":
        raise HTTPException(status_code=400, detail="Transfer is not accepting uploads")

    messages_data = [m.model_dump() for m in batch.messages]
    count = await transfer_service.add_messages(db, transfer_id, messages_data)
    return {"inserted": count, "total": transfer.total_messages}


@router.get("", response_model=MessageBatchResponse)
async def download_messages(
    transfer_id: UUID,
    offset: int = 0,
    limit: int = 500,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download messages for a transfer (used by the iOS app).

    Paginated — call with increasing offset until you've fetched `total` messages.
    """
    transfer = await db.get(Transfer, transfer_id)
    if not transfer or transfer.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if transfer.status not in ("ready", "downloading", "completed"):
        raise HTTPException(status_code=400, detail="Transfer is not ready for download")

    if transfer.status == "ready":
        transfer.status = "downloading"
        await db.commit()

    messages, total = await transfer_service.get_messages(db, transfer_id, offset, limit)

    return MessageBatchResponse(
        messages=[_message_to_response(m) for m in messages],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/{message_id}/attachments", response_model=AttachmentUploadResponse)
async def upload_attachment(
    transfer_id: UUID,
    message_id: UUID,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an attachment file for a message (from the Android app).

    The attachment binary is uploaded directly. For large files, use the
    pre-signed URL returned in the response for subsequent uploads.
    """
    transfer = await db.get(Transfer, transfer_id)
    if not transfer or transfer.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transfer not found")

    message = await db.get(TransferMessage, message_id)
    if not message or message.transfer_id != transfer_id:
        raise HTTPException(status_code=404, detail="Message not found")

    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "attachment"

    storage_key = storage.upload_attachment(
        str(transfer_id), str(message_id), filename, data, content_type
    )

    attachment = TransferAttachment(
        message_id=message_id,
        content_type=content_type,
        filename=filename,
        size_bytes=len(data),
        storage_key=storage_key,
    )
    db.add(attachment)
    transfer.total_attachments += 1
    transfer.upload_size_bytes += len(data)
    await db.commit()
    await db.refresh(attachment)

    upload_url = storage.generate_upload_url(storage_key, content_type)

    return AttachmentUploadResponse(id=attachment.id, upload_url=upload_url)


@router.get("/{message_id}/attachments/{attachment_id}/download")
async def download_attachment(
    transfer_id: UUID,
    message_id: UUID,
    attachment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a pre-signed download URL for an attachment (used by the iOS app)."""
    transfer = await db.get(Transfer, transfer_id)
    if not transfer or transfer.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transfer not found")

    attachment = await db.get(TransferAttachment, attachment_id)
    if not attachment or attachment.message_id != message_id:
        raise HTTPException(status_code=404, detail="Attachment not found")

    url = storage.generate_download_url(attachment.storage_key)
    return {"download_url": url}


def _message_to_response(msg: TransferMessage) -> MessageResponse:
    participants = json.loads(msg.participants_json) if msg.participants_json else []
    attachments = [
        AttachmentResponse(
            id=att.id,
            content_type=att.content_type,
            filename=att.filename,
            size_bytes=att.size_bytes,
        )
        for att in (msg.attachments or [])
    ]
    return MessageResponse(
        id=msg.id,
        address=msg.address,
        timestamp_ms=msg.timestamp_ms,
        is_sent=msg.is_sent,
        body=msg.body,
        msg_type=msg.msg_type,
        subject=msg.subject,
        is_group=msg.is_group,
        participants=participants,
        attachments=attachments,
    )
