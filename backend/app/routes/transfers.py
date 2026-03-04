"""Transfer session management routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import Transfer, User
from ..schemas import TransferCreate, TransferListResponse, TransferResponse
from ..services import transfer as transfer_service

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("", response_model=TransferResponse, status_code=201)
async def create_transfer(
    body: TransferCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a new transfer session. Called from the Android app."""
    transfer = await transfer_service.create_transfer(db, user.id)
    return TransferResponse.model_validate(transfer)


@router.get("", response_model=TransferListResponse)
async def list_transfers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all transfers for the current user."""
    result = await db.execute(
        select(Transfer)
        .where(Transfer.user_id == user.id)
        .order_by(Transfer.created_at.desc())
    )
    transfers = list(result.scalars().all())
    return TransferListResponse(
        transfers=[TransferResponse.model_validate(t) for t in transfers]
    )


@router.get("/{transfer_id}", response_model=TransferResponse)
async def get_transfer(
    transfer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details of a specific transfer."""
    transfer = await _get_user_transfer(db, transfer_id, user.id)
    return TransferResponse.model_validate(transfer)


@router.post("/{transfer_id}/finalize", response_model=TransferResponse)
async def finalize_transfer(
    transfer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark upload as complete — transfer is now ready for the iOS app."""
    await _get_user_transfer(db, transfer_id, user.id)
    transfer = await transfer_service.finalize_upload(db, transfer_id)
    return TransferResponse.model_validate(transfer)


@router.post("/{transfer_id}/complete", response_model=TransferResponse)
async def complete_transfer(
    transfer_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark transfer as completed after iOS restore finishes."""
    await _get_user_transfer(db, transfer_id, user.id)
    transfer = await transfer_service.mark_completed(db, transfer_id)
    return TransferResponse.model_validate(transfer)


async def _get_user_transfer(db: AsyncSession, transfer_id: UUID, user_id) -> Transfer:
    """Get a transfer that belongs to the given user, or 404."""
    transfer = await db.get(Transfer, transfer_id)
    if not transfer or transfer.user_id != user_id:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer
