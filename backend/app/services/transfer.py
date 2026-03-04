"""Transfer session management service."""

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Transfer, TransferAttachment, TransferMessage
from . import storage

logger = logging.getLogger(__name__)


async def create_transfer(db: AsyncSession, user_id: UUID) -> Transfer:
    """Create a new transfer session."""
    transfer = Transfer(
        user_id=user_id,
        status="uploading",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.transfer_expiry_hours),
    )
    db.add(transfer)
    await db.commit()
    await db.refresh(transfer)
    logger.info("Created transfer %s for user %s", transfer.id, user_id)
    return transfer


async def add_messages(
    db: AsyncSession,
    transfer_id: UUID,
    messages: list[dict],
) -> int:
    """Add a batch of messages to a transfer. Returns count inserted."""
    transfer = await db.get(Transfer, transfer_id)
    if not transfer:
        raise ValueError(f"Transfer not found: {transfer_id}")
    if transfer.status != "uploading":
        raise ValueError(f"Transfer is not in uploading state: {transfer.status}")

    inserted = 0
    for msg_data in messages:
        msg = TransferMessage(
            transfer_id=transfer_id,
            address=msg_data["address"],
            timestamp_ms=msg_data["timestamp_ms"],
            is_sent=msg_data["is_sent"],
            body=msg_data.get("body", ""),
            msg_type=msg_data.get("msg_type", "sms"),
            subject=msg_data.get("subject"),
            is_group=msg_data.get("is_group", False),
            participants_json=json.dumps(msg_data.get("participants", [])),
        )
        db.add(msg)
        inserted += 1

        # Update stats
        transfer.total_messages += 1
        if msg_data.get("msg_type") == "sms":
            transfer.sms_count += 1
        elif msg_data.get("msg_type") == "mms":
            transfer.mms_count += 1
        elif msg_data.get("msg_type") == "rcs":
            transfer.rcs_count += 1

    # Update contact count
    result = await db.execute(
        select(func.count(func.distinct(TransferMessage.address)))
        .where(TransferMessage.transfer_id == transfer_id)
    )
    transfer.total_contacts = result.scalar() or 0

    await db.commit()
    logger.info("Added %d messages to transfer %s (total: %d)",
                inserted, transfer_id, transfer.total_messages)
    return inserted


async def finalize_upload(db: AsyncSession, transfer_id: UUID) -> Transfer:
    """Mark a transfer as ready for download by the iOS app."""
    transfer = await db.get(Transfer, transfer_id)
    if not transfer:
        raise ValueError(f"Transfer not found: {transfer_id}")
    if transfer.status != "uploading":
        raise ValueError(f"Transfer is not in uploading state: {transfer.status}")

    transfer.status = "ready"
    await db.commit()
    await db.refresh(transfer)
    logger.info("Transfer %s is now ready (%d messages)", transfer_id, transfer.total_messages)
    return transfer


async def get_messages(
    db: AsyncSession,
    transfer_id: UUID,
    offset: int = 0,
    limit: int = 500,
) -> tuple[list[TransferMessage], int]:
    """Get messages for a transfer with pagination."""
    # Total count
    count_result = await db.execute(
        select(func.count(TransferMessage.id))
        .where(TransferMessage.transfer_id == transfer_id)
    )
    total = count_result.scalar() or 0

    # Fetch page
    result = await db.execute(
        select(TransferMessage)
        .where(TransferMessage.transfer_id == transfer_id)
        .order_by(TransferMessage.timestamp_ms)
        .offset(offset)
        .limit(limit)
    )
    messages = list(result.scalars().all())
    return messages, total


async def mark_completed(db: AsyncSession, transfer_id: UUID) -> Transfer:
    """Mark a transfer as completed after the iOS app finishes."""
    transfer = await db.get(Transfer, transfer_id)
    if not transfer:
        raise ValueError(f"Transfer not found: {transfer_id}")

    transfer.status = "completed"
    transfer.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(transfer)
    return transfer


async def cleanup_expired(db: AsyncSession) -> int:
    """Delete expired transfers and their stored data."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Transfer).where(
            Transfer.expires_at < now,
            Transfer.status != "expired",
        )
    )
    expired = list(result.scalars().all())

    for transfer in expired:
        try:
            storage.delete_transfer_data(str(transfer.id))
        except Exception as e:
            logger.warning("Failed to delete storage for %s: %s", transfer.id, e)
        transfer.status = "expired"

    await db.commit()
    logger.info("Cleaned up %d expired transfers", len(expired))
    return len(expired)
