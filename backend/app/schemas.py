"""Pydantic request/response schemas."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    id_token: str = Field(..., description="Google ID token from client-side sign-in")


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    picture_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Transfers ─────────────────────────────────────────────────────────

class TransferCreate(BaseModel):
    """Starts a new transfer session from the Android app."""
    pass


class TransferResponse(BaseModel):
    id: uuid.UUID
    status: str
    created_at: datetime
    expires_at: datetime
    total_messages: int
    sms_count: int
    mms_count: int
    rcs_count: int
    total_contacts: int
    total_attachments: int
    upload_size_bytes: int

    model_config = {"from_attributes": True}


class TransferListResponse(BaseModel):
    transfers: list[TransferResponse]


# ── Messages ──────────────────────────────────────────────────────────

class MessageUpload(BaseModel):
    address: str
    timestamp_ms: int
    is_sent: bool
    body: str = ""
    msg_type: str = "sms"
    subject: Optional[str] = None
    is_group: bool = False
    participants: list[str] = Field(default_factory=list)


class MessageBatchUpload(BaseModel):
    """Upload a batch of messages from the Android app."""
    messages: list[MessageUpload]


class AttachmentUploadResponse(BaseModel):
    id: uuid.UUID
    upload_url: str  # pre-signed URL for direct upload


class MessageResponse(BaseModel):
    id: uuid.UUID
    address: str
    timestamp_ms: int
    is_sent: bool
    body: str
    msg_type: str
    subject: Optional[str] = None
    is_group: bool
    participants: list[str]
    attachments: list["AttachmentResponse"]

    model_config = {"from_attributes": True}


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    content_type: str
    filename: str
    size_bytes: int
    download_url: Optional[str] = None

    model_config = {"from_attributes": True}


class MessageBatchResponse(BaseModel):
    messages: list[MessageResponse]
    total: int
    offset: int
    limit: int
