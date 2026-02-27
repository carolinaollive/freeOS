"""Read and modify unencrypted iOS backups (created by Finder/iTunes).

iOS backup structure:
  BackupDir/
    Info.plist          - Device info, backup date, etc.
    Manifest.plist      - Backup metadata, IsEncrypted flag
    Manifest.db         - SQLite database listing all backed-up files
    Status.plist        - Backup completion status
    xx/                 - Two-char hex prefix directories
      xxYYYY...         - Files stored by SHA1 hash of (domain-relativePath)

Manifest.db schema:
  CREATE TABLE Files (
    fileID TEXT PRIMARY KEY,
    domain TEXT,
    relativePath TEXT,
    flags INTEGER,
    file BLOB       -- binary plist with metadata (size, mode, mtime, etc.)
  );
  CREATE TABLE Properties (
    key TEXT PRIMARY KEY,
    value BLOB
  );

The fileID is computed as: SHA1(utf8(domain + "-" + relativePath))

The SMS database is stored at:
  domain: HomeDomain
  relativePath: Library/SMS/sms.db
  fileID: 3d0d7e5fb2ce288813306e4d4636395e047a3d28
"""

import hashlib
import logging
import os
import plistlib
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Well-known file IDs
SMS_DB_FILE_ID = "3d0d7e5fb2ce288813306e4d4636395e047a3d28"
SMS_DB_DOMAIN = "HomeDomain"
SMS_DB_RELATIVE_PATH = "Library/SMS/sms.db"

# Attachment domain and base path
ATTACHMENT_DOMAIN = "MediaDomain"
ATTACHMENT_BASE_PATH = "Library/SMS/Attachments"


def compute_file_id(domain: str, relative_path: str) -> str:
    """Compute the iOS backup fileID (SHA1 hash of domain-relativePath)."""
    raw = f"{domain}-{relative_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _default_backup_dir() -> Optional[str]:
    """Return the default iOS backup directory on macOS."""
    home = os.path.expanduser("~")
    backup_base = os.path.join(home, "Library", "Application Support",
                               "MobileSync", "Backup")
    if not os.path.isdir(backup_base):
        return None
    # List backup directories, sorted by modification time (newest first)
    try:
        backups = sorted(
            [os.path.join(backup_base, d) for d in os.listdir(backup_base)
             if os.path.isdir(os.path.join(backup_base, d))],
            key=os.path.getmtime,
            reverse=True,
        )
        return backups[0] if backups else None
    except OSError:
        return None


def find_backup(backup_path: Optional[str] = None) -> str:
    """Find and validate an iOS backup directory.

    If backup_path is None, tries to find the most recent backup on macOS.
    """
    if backup_path:
        bp = os.path.expanduser(backup_path)
    else:
        bp = _default_backup_dir()
        if not bp:
            raise FileNotFoundError(
                "No iOS backup found. On macOS, backups are typically at:\n"
                "  ~/Library/Application Support/MobileSync/Backup/\n"
                "Create an unencrypted backup using Finder, then try again."
            )

    if not os.path.isdir(bp):
        raise FileNotFoundError(f"Backup directory not found: {bp}")

    # Validate it looks like an iOS backup
    manifest_db = os.path.join(bp, "Manifest.db")
    manifest_plist = os.path.join(bp, "Manifest.plist")

    if not os.path.isfile(manifest_db):
        raise FileNotFoundError(
            f"Not a valid iOS backup (missing Manifest.db): {bp}"
        )

    # Check if encrypted
    if os.path.isfile(manifest_plist):
        with open(manifest_plist, "rb") as f:
            try:
                plist = plistlib.load(f)
                if plist.get("IsEncrypted", False):
                    raise ValueError(
                        "This backup is encrypted. Please create an unencrypted "
                        "backup in Finder (uncheck 'Encrypt local backup') and try again.\n"
                        "Your messages will still be safe - the tool only adds messages, "
                        "it does not delete any existing data."
                    )
            except plistlib.InvalidFileException:
                logger.warning("Could not parse Manifest.plist, proceeding anyway")

    logger.info("Using iOS backup: %s", bp)
    return bp


def get_file_path(backup_dir: str, file_id: str) -> str:
    """Get the full filesystem path for a file in the backup by its fileID."""
    # Files are stored in two-char prefix subdirectories
    return os.path.join(backup_dir, file_id[:2], file_id)


def get_sms_db_path(backup_dir: str) -> str:
    """Get the path to the SMS database in the backup."""
    path = get_file_path(backup_dir, SMS_DB_FILE_ID)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"SMS database not found in backup at: {path}\n"
            "Make sure you have a valid, unencrypted iOS backup that includes Messages."
        )
    return path


def backup_file(path: str) -> str:
    """Create a backup copy of a file, returning the backup path."""
    backup_path = path + ".bak"
    if os.path.exists(backup_path):
        # Don't overwrite existing backup
        i = 1
        while os.path.exists(f"{path}.bak.{i}"):
            i += 1
        backup_path = f"{path}.bak.{i}"
    shutil.copy2(path, backup_path)
    logger.info("Created backup: %s", backup_path)
    return backup_path


def add_attachment_to_backup(backup_dir: str, attachment_data: bytes,
                             attachment_filename: str,
                             unique_id: str) -> tuple[str, str]:
    """Add an attachment file to the iOS backup.

    Returns (file_id, relative_path) for the attachment.
    """
    # iOS stores SMS attachments at:
    #   MediaDomain - Library/SMS/Attachments/XX/YY/filename
    # where XX and YY are two-digit hex subdirectories derived from some hash
    # We use the unique_id to create a deterministic but unique path
    hash_bytes = hashlib.sha256(unique_id.encode()).hexdigest()
    sub1 = hash_bytes[:2]
    sub2 = hash_bytes[2:4]

    relative_path = f"{ATTACHMENT_BASE_PATH}/{sub1}/{sub2}/{attachment_filename}"
    file_id = compute_file_id(ATTACHMENT_DOMAIN, relative_path)

    # Write the file
    file_path = get_file_path(backup_dir, file_id)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(attachment_data)

    # Update Manifest.db
    _add_manifest_entry(backup_dir, file_id, ATTACHMENT_DOMAIN,
                        relative_path, len(attachment_data))

    logger.debug("Added attachment to backup: %s -> %s", attachment_filename, file_id)
    return file_id, relative_path


def _add_manifest_entry(backup_dir: str, file_id: str, domain: str,
                        relative_path: str, file_size: int):
    """Add or update an entry in Manifest.db for a file."""
    manifest_db = os.path.join(backup_dir, "Manifest.db")

    # Create a minimal file metadata blob (binary plist)
    # The 'file' column contains a binary plist with keys like:
    # $archiver, $objects, $top, $version (NSKeyedArchiver format)
    # For simplicity, we create a minimal valid entry
    file_metadata = _create_file_metadata_blob(file_size)

    conn = sqlite3.connect(manifest_db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO Files (fileID, domain, relativePath, flags, file) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_id, domain, relative_path, 1, file_metadata)
        )
        conn.commit()
    finally:
        conn.close()


def update_sms_db_manifest(backup_dir: str):
    """Update the Manifest.db entry for sms.db after modification.

    This reads the existing manifest entry blob and updates its Size field
    to match the actual file size, preserving all other metadata.
    """
    sms_path = get_sms_db_path(backup_dir)
    file_size = os.path.getsize(sms_path)

    manifest_db = os.path.join(backup_dir, "Manifest.db")
    conn = sqlite3.connect(manifest_db)
    try:
        row = conn.execute(
            "SELECT file FROM Files WHERE fileID = ?", (SMS_DB_FILE_ID,)
        ).fetchone()

        if row and row[0]:
            # Update existing blob - preserve all fields, just update Size and Digest
            try:
                plist_data = plistlib.loads(row[0])
                objects = plist_data["$objects"]
                root_uid = plist_data["$top"]["root"]
                mbfile = objects[root_uid]
                mbfile["Size"] = file_size
                mbfile["LastModified"] = int(time.time())

                # Update Digest (SHA-1 of file contents) if present
                if "Digest" in mbfile:
                    with open(sms_path, "rb") as f:
                        digest = hashlib.sha1(f.read()).digest()
                    digest_uid = mbfile["Digest"]
                    if hasattr(digest_uid, "data"):
                        # Direct data reference
                        mbfile["Digest"] = digest
                    elif isinstance(digest_uid, plistlib.UID):
                        # UID reference into $objects
                        digest_obj = objects[digest_uid]
                        if isinstance(digest_obj, dict) and "NS.data" in digest_obj:
                            digest_obj["NS.data"] = digest
                        else:
                            objects[digest_uid] = digest

                file_metadata = plistlib.dumps(plist_data, fmt=plistlib.FMT_BINARY)
            except Exception:
                # Fallback: create a fresh blob
                file_metadata = _create_file_metadata_blob(file_size)
        else:
            file_metadata = _create_file_metadata_blob(file_size)

        conn.execute(
            "UPDATE Files SET file = ? WHERE fileID = ?",
            (file_metadata, SMS_DB_FILE_ID)
        )
        conn.commit()
    finally:
        conn.close()

    logger.info("Updated Manifest.db entry for sms.db (size: %d bytes)", file_size)


def _create_file_metadata_blob(file_size: int) -> bytes:
    """Create a binary plist blob for the Manifest.db file column.

    The file column uses NSKeyedArchiver format. We create a minimal
    representation that iOS will accept.
    """
    # Create the metadata dictionary that goes into the plist
    # iOS expects certain fields. We create a minimal but valid blob.
    metadata = {
        "$archiver": "NSKeyedArchiver",
        "$version": 100000,
        "$top": {"root": plistlib.UID(1)},
        "$objects": [
            "$null",
            {
                "$class": plistlib.UID(3),
                "Size": file_size,
                "Mode": 33188,  # regular file, 0644 permissions
                "InodeNumber": 0,
                "UserID": 501,
                "GroupID": 501,
                "LastModified": 0,
                "LastStatusChange": 0,
                "Birth": 0,
                "ProtectionClass": 3,
            },
            {
                "$classes": ["MBFile", "NSObject"],
                "$classname": "MBFile",
            },
            {
                "$classes": ["MBFile", "NSObject"],
                "$classname": "MBFile",
            },
        ],
    }

    return plistlib.dumps(metadata, fmt=plistlib.FMT_BINARY)


def list_backups() -> list[dict]:
    """List all iOS backups found on this system."""
    home = os.path.expanduser("~")
    backup_base = os.path.join(home, "Library", "Application Support",
                               "MobileSync", "Backup")

    if not os.path.isdir(backup_base):
        return []

    results = []
    for dirname in os.listdir(backup_base):
        bp = os.path.join(backup_base, dirname)
        if not os.path.isdir(bp):
            continue

        info = {"path": bp, "udid": dirname}

        # Try to read device info
        info_plist = os.path.join(bp, "Info.plist")
        if os.path.isfile(info_plist):
            try:
                with open(info_plist, "rb") as f:
                    plist = plistlib.load(f)
                info["device_name"] = plist.get("Device Name", "Unknown")
                info["product_type"] = plist.get("Product Type", "Unknown")
                info["ios_version"] = plist.get("Product Version", "Unknown")
                info["last_backup"] = plist.get("Last Backup Date", None)
            except Exception:
                pass

        # Check encryption
        manifest_plist = os.path.join(bp, "Manifest.plist")
        if os.path.isfile(manifest_plist):
            try:
                with open(manifest_plist, "rb") as f:
                    plist = plistlib.load(f)
                info["encrypted"] = plist.get("IsEncrypted", False)
            except Exception:
                info["encrypted"] = None

        results.append(info)

    return sorted(results, key=lambda x: x.get("last_backup") or "", reverse=True)
