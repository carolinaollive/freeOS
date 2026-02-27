"""Tests for iOS backup handling."""

import os
import tempfile

import pytest

from android_sms_to_iphone.ios_backup import compute_file_id, backup_file


class TestComputeFileId:
    def test_sms_db(self):
        """Verify the well-known SHA1 hash for sms.db."""
        file_id = compute_file_id("HomeDomain", "Library/SMS/sms.db")
        assert file_id == "3d0d7e5fb2ce288813306e4d4636395e047a3d28"

    def test_deterministic(self):
        """Same inputs should produce the same hash."""
        a = compute_file_id("MediaDomain", "Library/SMS/Attachments/ab/cd/photo.jpg")
        b = compute_file_id("MediaDomain", "Library/SMS/Attachments/ab/cd/photo.jpg")
        assert a == b

    def test_different_inputs(self):
        """Different inputs should produce different hashes."""
        a = compute_file_id("HomeDomain", "Library/SMS/sms.db")
        b = compute_file_id("HomeDomain", "Library/SMS/sms.db-wal")
        assert a != b


class TestBackupFile:
    def test_creates_bak(self):
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, b"test content")
            os.close(fd)

            bak_path = backup_file(path)
            assert os.path.exists(bak_path)
            assert bak_path.endswith(".bak")

            with open(bak_path, "rb") as f:
                assert f.read() == b"test content"

            os.unlink(bak_path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_incremental_backup(self):
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, b"test content")
            os.close(fd)

            bak1 = backup_file(path)
            bak2 = backup_file(path)
            assert bak1 != bak2
            assert os.path.exists(bak1)
            assert os.path.exists(bak2)

            os.unlink(bak1)
            os.unlink(bak2)
        finally:
            if os.path.exists(path):
                os.unlink(path)
