"""Tests for the iOS SMS database manipulator."""

import os
import sqlite3
import tempfile

import pytest

from android_sms_to_iphone.ios_sms_db import (
    COREDATA_EPOCH_OFFSET,
    NANOSECOND,
    iOSSmsDb,
    unix_ms_to_ios_date,
)


def _create_test_db() -> str:
    """Create a minimal iOS SMS database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT DEFAULT NULL,
            country TEXT DEFAULT 'us',
            service TEXT DEFAULT 'SMS',
            uncanonicalized_id TEXT DEFAULT NULL
        );

        CREATE TABLE chat (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            style INTEGER DEFAULT 43,
            state INTEGER DEFAULT 3,
            account_id TEXT DEFAULT NULL,
            chat_identifier TEXT DEFAULT NULL,
            service_name TEXT DEFAULT 'SMS',
            display_name TEXT DEFAULT '',
            group_id TEXT DEFAULT ''
        );

        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            text TEXT,
            handle_id INTEGER DEFAULT 0,
            service TEXT DEFAULT 'SMS',
            date INTEGER DEFAULT 0,
            date_read INTEGER DEFAULT 0,
            date_delivered INTEGER DEFAULT 0,
            is_from_me INTEGER DEFAULT 0,
            is_read INTEGER DEFAULT 0,
            is_delivered INTEGER DEFAULT 0,
            is_sent INTEGER DEFAULT 0,
            is_finished INTEGER DEFAULT 1,
            is_prepared INTEGER DEFAULT 1,
            type INTEGER DEFAULT 0,
            cache_has_attachments INTEGER DEFAULT 0,
            subject TEXT DEFAULT NULL,
            account_guid TEXT DEFAULT NULL
        );

        CREATE TABLE chat_message_join (
            chat_id INTEGER,
            message_id INTEGER,
            message_date INTEGER DEFAULT 0
        );

        CREATE TABLE chat_handle_join (
            chat_id INTEGER,
            handle_id INTEGER
        );

        CREATE TABLE attachment (
            ROWID INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            created_date INTEGER DEFAULT 0,
            filename TEXT DEFAULT NULL,
            mime_type TEXT DEFAULT NULL,
            transfer_name TEXT DEFAULT NULL,
            total_bytes INTEGER DEFAULT 0,
            transfer_state INTEGER DEFAULT 0,
            is_outgoing INTEGER DEFAULT 0
        );

        CREATE TABLE message_attachment_join (
            message_id INTEGER,
            attachment_id INTEGER
        );
    """)
    conn.close()
    return path


class TestTimestampConversion:
    def test_known_date(self):
        """Test converting a known Unix timestamp."""
        # 2021-01-01 00:00:00 UTC = 1609459200 seconds (Unix)
        # 2021-01-01 00:00:00 UTC = 631152000 seconds (Core Data)
        unix_ms = 1609459200000
        ios_date = unix_ms_to_ios_date(unix_ms)

        expected_cd_seconds = 1609459200 - COREDATA_EPOCH_OFFSET
        expected_ns = expected_cd_seconds * NANOSECOND

        assert ios_date == expected_ns

    def test_epoch(self):
        """Test Unix epoch converts correctly."""
        # Unix epoch = 1970-01-01 which is before Core Data epoch
        ios_date = unix_ms_to_ios_date(0)
        assert ios_date == -COREDATA_EPOCH_OFFSET * NANOSECOND

    def test_core_data_epoch(self):
        """Test that Core Data epoch (2001-01-01) converts to 0."""
        unix_ms = COREDATA_EPOCH_OFFSET * 1000
        ios_date = unix_ms_to_ios_date(unix_ms)
        assert ios_date == 0


class TestiOSSmsDb:
    def test_create_handle(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                handle_id = db.create_handle("+12025551234", "SMS", "us")
                assert handle_id == 1

                handle_id2 = db.get_handle("+12025551234", "SMS")
                assert handle_id2 == 1
        finally:
            os.unlink(path)

    def test_get_or_create_handle(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                h1 = db.get_or_create_handle("+12025551234")
                h2 = db.get_or_create_handle("+12025551234")
                assert h1 == h2

                h3 = db.get_or_create_handle("+12025559999")
                assert h3 != h1
        finally:
            os.unlink(path)

    def test_create_chat(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                chat_id = db.create_chat("+12025551234", "SMS")
                assert chat_id == 1

                chat_id2 = db.get_chat("+12025551234", "SMS")
                assert chat_id2 == 1
        finally:
            os.unlink(path)

    def test_insert_message(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                handle_id = db.create_handle("+12025551234")
                date_ns = unix_ms_to_ios_date(1609459200000)

                msg_id = db.insert_message(
                    text="Hello!",
                    handle_id=handle_id,
                    service="SMS",
                    date_ns=date_ns,
                    is_from_me=False,
                )
                db.commit()

                assert msg_id == 1
                assert db.get_message_count() == 1
        finally:
            os.unlink(path)

    def test_insert_sent_message(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                handle_id = db.create_handle("+12025551234")
                date_ns = unix_ms_to_ios_date(1609459200000)

                msg_id = db.insert_message(
                    text="Reply",
                    handle_id=handle_id,
                    service="SMS",
                    date_ns=date_ns,
                    is_from_me=True,
                )
                db.commit()

                # Verify handle_id is 0 for sent messages
                conn = sqlite3.connect(path)
                row = conn.execute(
                    "SELECT handle_id, is_from_me, is_sent FROM message WHERE ROWID = ?",
                    (msg_id,)
                ).fetchone()
                conn.close()

                assert row[0] == 0  # handle_id
                assert row[1] == 1  # is_from_me
                assert row[2] == 1  # is_sent
        finally:
            os.unlink(path)

    def test_link_message_to_chat(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                handle_id = db.create_handle("+12025551234")
                chat_id = db.create_chat("+12025551234")
                date_ns = unix_ms_to_ios_date(1609459200000)

                msg_id = db.insert_message("Hello!", handle_id, "SMS",
                                           date_ns, False)
                db.link_message_to_chat(chat_id, msg_id, date_ns)
                db.commit()

                conn = sqlite3.connect(path)
                row = conn.execute(
                    "SELECT * FROM chat_message_join WHERE chat_id = ?",
                    (chat_id,)
                ).fetchone()
                conn.close()

                assert row is not None
                assert row[1] == msg_id
        finally:
            os.unlink(path)

    def test_insert_attachment(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                date_ns = unix_ms_to_ios_date(1609459200000)

                att_id = db.insert_attachment(
                    filename="ab/cd/photo.jpg",
                    mime_type="image/jpeg",
                    transfer_name="photo.jpg",
                    total_bytes=12345,
                    created_date=date_ns,
                    is_outgoing=False,
                )
                db.commit()

                assert att_id == 1
        finally:
            os.unlink(path)

    def test_deduplication(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                handle_id = db.create_handle("+12025551234")
                chat_id = db.create_chat("+12025551234")
                date_ns = unix_ms_to_ios_date(1609459200000)

                msg_id = db.insert_message("Hello!", handle_id, "SMS", date_ns, False)
                db.link_message_to_chat(chat_id, msg_id, date_ns)
                db.commit()

                existing = db.get_existing_dates_for_chat(chat_id)
                assert date_ns in existing
        finally:
            os.unlink(path)

    def test_integrity_check(self):
        path = _create_test_db()
        try:
            with iOSSmsDb(path) as db:
                assert db.verify_integrity() is True
        finally:
            os.unlink(path)
