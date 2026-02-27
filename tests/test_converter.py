"""Tests for the end-to-end message converter."""

import os
import plistlib
import sqlite3
import tempfile

import pytest

from android_sms_to_iphone.converter import convert, ConversionStats
from android_sms_to_iphone.ios_backup import SMS_DB_FILE_ID, compute_file_id


def _create_test_backup() -> str:
    """Create a minimal fake iOS backup directory for testing."""
    backup_dir = tempfile.mkdtemp()

    # Create Manifest.plist (unencrypted)
    manifest_plist = {"IsEncrypted": False, "Version": "10.0"}
    with open(os.path.join(backup_dir, "Manifest.plist"), "wb") as f:
        plistlib.dump(manifest_plist, f)

    # Create Manifest.db
    manifest_db_path = os.path.join(backup_dir, "Manifest.db")
    conn = sqlite3.connect(manifest_db_path)
    conn.executescript("""
        CREATE TABLE Files (
            fileID TEXT PRIMARY KEY,
            domain TEXT,
            relativePath TEXT,
            flags INTEGER,
            file BLOB
        );
        CREATE TABLE Properties (
            key TEXT PRIMARY KEY,
            value BLOB
        );
    """)
    # Insert SMS db entry
    conn.execute(
        "INSERT INTO Files (fileID, domain, relativePath, flags, file) "
        "VALUES (?, ?, ?, ?, ?)",
        (SMS_DB_FILE_ID, "HomeDomain", "Library/SMS/sms.db", 1, b"")
    )
    conn.commit()
    conn.close()

    # Create the SMS database file
    sms_dir = os.path.join(backup_dir, SMS_DB_FILE_ID[:2])
    os.makedirs(sms_dir, exist_ok=True)
    sms_db_path = os.path.join(sms_dir, SMS_DB_FILE_ID)

    conn = sqlite3.connect(sms_db_path)
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

    return backup_dir


def _create_test_export() -> str:
    """Create a test Android SMS export NDJSON file (SMS Import / Export format)."""
    import json

    lines = [
        json.dumps({"_id": "1", "address": "+12025551234", "date": "1609459200000",
                     "type": "1", "body": "Hello from Android!", "read": "1"}),
        json.dumps({"_id": "2", "address": "+12025551234", "date": "1609459260000",
                     "type": "2", "body": "Hello back!", "read": "1"}),
        json.dumps({"_id": "3", "address": "+12025559999", "date": "1609459300000",
                     "type": "1", "body": "Different contact", "read": "1"}),
        json.dumps({
            "_id": "100", "date": "1609459400", "msg_box": "1",
            "ct_t": "application/vnd.wap.multipart.related",
            "__sender_address": {"address": "+12025551234", "type": "137"},
            "__recipient_addresses": [{"address": "+10000000000", "type": "151"}],
            "__parts": [
                {"seq": "0", "ct": "text/plain", "text": "MMS with attachment"},
                {"seq": "1", "ct": "image/jpeg", "_data": "photo.jpg",
                 "cl": "photo.jpg", "fn": "photo.jpg"},
            ],
        }),
    ]
    ndjson = "\n".join(lines)

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name

    import zipfile
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("messages.ndjson", ndjson)
        zf.writestr("data/photo.jpg", b"fake jpeg data")

    return zip_path


class TestConvert:
    def test_basic_conversion(self):
        backup_dir = _create_test_backup()
        export_path = _create_test_export()

        try:
            stats = convert(export_path, backup_dir, skip_duplicates=True)

            assert stats.total_parsed == 4
            assert stats.sms_count == 3
            assert stats.mms_count == 1
            assert stats.inserted == 4
            assert stats.skipped_duplicate == 0

            # Verify messages in the database
            sms_db_path = os.path.join(backup_dir, SMS_DB_FILE_ID[:2], SMS_DB_FILE_ID)
            conn = sqlite3.connect(sms_db_path)

            msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
            assert msg_count == 4

            handle_count = conn.execute("SELECT COUNT(*) FROM handle").fetchone()[0]
            assert handle_count == 2  # two unique contacts

            chat_count = conn.execute("SELECT COUNT(*) FROM chat").fetchone()[0]
            assert chat_count == 2

            conn.close()
        finally:
            if os.path.exists(export_path):
                os.unlink(export_path)
            import shutil
            shutil.rmtree(backup_dir, ignore_errors=True)

    def test_dry_run(self):
        backup_dir = _create_test_backup()
        export_path = _create_test_export()

        try:
            stats = convert(export_path, backup_dir, dry_run=True)

            assert stats.total_parsed == 4
            assert stats.inserted == 0

            # Verify no changes to database
            sms_db_path = os.path.join(backup_dir, SMS_DB_FILE_ID[:2], SMS_DB_FILE_ID)
            conn = sqlite3.connect(sms_db_path)
            msg_count = conn.execute("SELECT COUNT(*) FROM message").fetchone()[0]
            assert msg_count == 0
            conn.close()
        finally:
            if os.path.exists(export_path):
                os.unlink(export_path)
            import shutil
            shutil.rmtree(backup_dir, ignore_errors=True)

    def test_duplicate_detection(self):
        backup_dir = _create_test_backup()
        export_path = _create_test_export()

        try:
            # First run
            stats1 = convert(export_path, backup_dir, skip_duplicates=True)
            assert stats1.inserted == 4

            # Second run - should skip all as duplicates
            stats2 = convert(export_path, backup_dir, skip_duplicates=True)
            assert stats2.inserted == 0
            assert stats2.skipped_duplicate == 4
        finally:
            if os.path.exists(export_path):
                os.unlink(export_path)
            import shutil
            shutil.rmtree(backup_dir, ignore_errors=True)

    def test_allow_duplicates(self):
        backup_dir = _create_test_backup()
        export_path = _create_test_export()

        try:
            stats1 = convert(export_path, backup_dir)
            assert stats1.inserted == 4

            stats2 = convert(export_path, backup_dir, skip_duplicates=False)
            assert stats2.inserted == 4  # All inserted again
        finally:
            if os.path.exists(export_path):
                os.unlink(export_path)
            import shutil
            shutil.rmtree(backup_dir, ignore_errors=True)


class TestConversionStats:
    def test_summary(self):
        stats = ConversionStats(
            total_parsed=100,
            sms_count=80,
            mms_count=15,
            rcs_count=5,
            inserted=95,
            skipped_duplicate=5,
        )
        summary = stats.summary()
        assert "100 messages" in summary
        assert "80 SMS" in summary
        assert "15 MMS" in summary
        assert "5 RCS" in summary
        assert "95 messages" in summary
        assert "5 skipped" in summary
