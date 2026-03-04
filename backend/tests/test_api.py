"""Tests for the backend API routes."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import Transfer, TransferMessage, User
from app.schemas import MessageBatchUpload, MessageUpload


@pytest.fixture
def sample_user():
    return User(
        id=uuid4(),
        google_id="google-123",
        email="test@example.com",
        name="Test User",
        created_at=datetime.now(timezone.utc),
        last_login=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_transfer(sample_user):
    return Transfer(
        id=uuid4(),
        user_id=sample_user.id,
        status="uploading",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
        total_messages=0,
        sms_count=0,
        mms_count=0,
        rcs_count=0,
        total_contacts=0,
        total_attachments=0,
        upload_size_bytes=0,
    )


class TestSchemas:
    def test_message_upload_schema(self):
        msg = MessageUpload(
            address="+15551234567",
            timestamp_ms=1700000000000,
            is_sent=False,
            body="Hello!",
            msg_type="sms",
        )
        assert msg.address == "+15551234567"
        assert msg.timestamp_ms == 1700000000000
        assert not msg.is_sent
        assert msg.body == "Hello!"
        assert msg.msg_type == "sms"
        assert not msg.is_group
        assert msg.participants == []

    def test_message_batch_upload_schema(self):
        batch = MessageBatchUpload(
            messages=[
                MessageUpload(
                    address="+15551234567",
                    timestamp_ms=1700000000000,
                    is_sent=False,
                    body="Hello!",
                ),
                MessageUpload(
                    address="+15559876543",
                    timestamp_ms=1700000001000,
                    is_sent=True,
                    body="Hi there!",
                    msg_type="mms",
                    is_group=True,
                    participants=["+15551111111"],
                ),
            ]
        )
        assert len(batch.messages) == 2
        assert batch.messages[0].msg_type == "sms"
        assert batch.messages[1].is_group

    def test_message_upload_defaults(self):
        msg = MessageUpload(
            address="+15551234567",
            timestamp_ms=1700000000000,
            is_sent=True,
        )
        assert msg.body == ""
        assert msg.msg_type == "sms"
        assert msg.subject is None
        assert not msg.is_group


class TestModels:
    def test_user_creation(self, sample_user):
        assert sample_user.email == "test@example.com"
        assert sample_user.google_id == "google-123"

    def test_transfer_creation(self, sample_transfer):
        assert sample_transfer.status == "uploading"
        assert sample_transfer.total_messages == 0

    def test_transfer_message_creation(self, sample_transfer):
        msg = TransferMessage(
            transfer_id=sample_transfer.id,
            address="+15551234567",
            timestamp_ms=1700000000000,
            is_sent=False,
            body="Test message",
            msg_type="sms",
        )
        assert msg.address == "+15551234567"
        assert msg.msg_type == "sms"


class TestAuthToken:
    def test_create_and_decode_token(self):
        from app.auth import create_access_token
        from jose import jwt
        from app.config import settings

        user_id = uuid4()
        token = create_access_token(user_id)
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == str(user_id)
        assert "exp" in payload
