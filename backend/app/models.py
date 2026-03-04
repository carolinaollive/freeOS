"""SQLAlchemy database models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_id = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    picture_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    transfers = relationship("Transfer", back_populates="user", cascade="all, delete-orphan")


class Transfer(Base):
    """A transfer session — one Android-to-iPhone migration."""

    __tablename__ = "transfers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(
        Enum("uploading", "ready", "downloading", "completed", "expired",
             name="transfer_status"),
        default="uploading",
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Stats
    total_messages = Column(Integer, default=0)
    sms_count = Column(Integer, default=0)
    mms_count = Column(Integer, default=0)
    rcs_count = Column(Integer, default=0)
    total_contacts = Column(Integer, default=0)
    total_attachments = Column(Integer, default=0)
    upload_size_bytes = Column(BigInteger, default=0)

    # Storage reference
    storage_key = Column(String(512), nullable=True)

    user = relationship("User", back_populates="transfers")
    messages = relationship("TransferMessage", back_populates="transfer",
                            cascade="all, delete-orphan")


class TransferMessage(Base):
    """Individual message within a transfer."""

    __tablename__ = "transfer_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transfer_id = Column(UUID(as_uuid=True), ForeignKey("transfers.id"), nullable=False)

    address = Column(String(255), nullable=False, index=True)
    timestamp_ms = Column(BigInteger, nullable=False)
    is_sent = Column(Boolean, nullable=False)
    body = Column(Text, default="")
    msg_type = Column(String(10), default="sms")  # sms, mms, rcs
    subject = Column(Text, nullable=True)
    is_group = Column(Boolean, default=False)
    participants_json = Column(Text, default="[]")

    transfer = relationship("Transfer", back_populates="messages")
    attachments = relationship("TransferAttachment", back_populates="message",
                               cascade="all, delete-orphan")


class TransferAttachment(Base):
    """Attachment blob reference for MMS/RCS messages."""

    __tablename__ = "transfer_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("transfer_messages.id"), nullable=False)
    content_type = Column(String(255), nullable=False)
    filename = Column(String(512), nullable=False)
    size_bytes = Column(BigInteger, default=0)
    storage_key = Column(String(512), nullable=False)

    message = relationship("TransferMessage", back_populates="attachments")
