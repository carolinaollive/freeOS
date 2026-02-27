"""Manipulate the iOS SMS/iMessage SQLite database (sms.db).

The iOS Messages database contains these key tables:

  handle - Contact identifiers (phone numbers, email addresses)
    ROWID INTEGER PRIMARY KEY
    id TEXT (phone number like +12345678900)
    country TEXT (two-letter code like 'us')
    service TEXT ('SMS' or 'iMessage')
    uncanonicalized_id TEXT

  chat - Conversations
    ROWID INTEGER PRIMARY KEY
    guid TEXT (e.g., 'SMS;-;+12345678900')
    style INTEGER (43=1-on-1, 47=group)
    state INTEGER (default 3)
    account_id TEXT
    chat_identifier TEXT (phone number or group id)
    service_name TEXT ('SMS' or 'iMessage')
    display_name TEXT
    group_id TEXT

  message - Individual messages
    ROWID INTEGER PRIMARY KEY
    guid TEXT (unique identifier)
    text TEXT
    handle_id INTEGER (FK to handle.ROWID, 0 if sent by self)
    service TEXT ('SMS' or 'iMessage')
    date INTEGER (nanoseconds since 2001-01-01 00:00:00 UTC)
    date_read INTEGER
    date_delivered INTEGER
    is_from_me INTEGER (1=sent, 0=received)
    is_read INTEGER
    is_delivered INTEGER
    is_sent INTEGER
    is_finished INTEGER (1 for completed messages)
    is_prepared INTEGER (1 for completed messages)
    type INTEGER (0 for normal messages)
    cache_has_attachments INTEGER
    account_guid TEXT
    subject TEXT

  chat_message_join - Links messages to chats
    chat_id INTEGER
    message_id INTEGER
    message_date INTEGER (same as message.date)

  chat_handle_join - Links handles to chats
    chat_id INTEGER
    handle_id INTEGER

  attachment - Media attachments
    ROWID INTEGER PRIMARY KEY
    guid TEXT
    created_date INTEGER
    filename TEXT (relative path like '~/Library/SMS/Attachments/...')
    mime_type TEXT
    transfer_name TEXT (display filename)
    total_bytes INTEGER
    transfer_state INTEGER (5 = complete)
    is_outgoing INTEGER

  message_attachment_join - Links attachments to messages
    message_id INTEGER
    attachment_id INTEGER

Date conversion:
  iOS uses "Core Data timestamp" = nanoseconds since 2001-01-01 00:00:00 UTC
  Unix epoch to Core Data: (unix_timestamp - 978307200) * 1_000_000_000
"""

import logging
import sqlite3
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# Core Data epoch offset: seconds between 1970-01-01 and 2001-01-01
COREDATA_EPOCH_OFFSET = 978307200

# Nanosecond multiplier for iOS 11+ dates
NANOSECOND = 1_000_000_000


def unix_ms_to_ios_date(unix_ms: int) -> int:
    """Convert Unix timestamp in milliseconds to iOS Core Data date (nanoseconds)."""
    unix_seconds = unix_ms / 1000.0
    core_data_seconds = unix_seconds - COREDATA_EPOCH_OFFSET
    return int(core_data_seconds * NANOSECOND)


def _generate_guid() -> str:
    """Generate a unique GUID for an iOS message."""
    return str(uuid.uuid4()).upper()


class iOSSmsDb:
    """Interface to read and write the iOS SMS SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_wal_mode()

    def _ensure_wal_mode(self):
        """Set WAL mode for better concurrent access."""
        self.conn.execute("PRAGMA journal_mode=WAL")

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── Handle operations ─────────────────────────────────────────────

    def get_handle(self, phone: str, service: str = "SMS") -> Optional[int]:
        """Look up a handle by phone number and service, return ROWID or None."""
        row = self.conn.execute(
            "SELECT ROWID FROM handle WHERE id = ? AND service = ?",
            (phone, service)
        ).fetchone()
        return row["ROWID"] if row else None

    def create_handle(self, phone: str, service: str = "SMS",
                      country: str = "us") -> int:
        """Create a new handle entry, return its ROWID."""
        cursor = self.conn.execute(
            "INSERT INTO handle (id, country, service, uncanonicalized_id) "
            "VALUES (?, ?, ?, ?)",
            (phone, country, service, phone)
        )
        self.conn.commit()
        handle_id = cursor.lastrowid
        logger.debug("Created handle %d for %s (%s)", handle_id, phone, service)
        return handle_id

    def get_or_create_handle(self, phone: str, service: str = "SMS",
                             country: str = "us") -> int:
        """Get existing handle or create a new one."""
        handle_id = self.get_handle(phone, service)
        if handle_id is None:
            handle_id = self.create_handle(phone, service, country)
        return handle_id

    # ── Chat operations ───────────────────────────────────────────────

    def get_chat(self, chat_identifier: str, service: str = "SMS") -> Optional[int]:
        """Look up a chat by identifier and service, return ROWID or None."""
        row = self.conn.execute(
            "SELECT ROWID FROM chat WHERE chat_identifier = ? AND service_name = ?",
            (chat_identifier, service)
        ).fetchone()
        return row["ROWID"] if row else None

    def create_chat(self, chat_identifier: str, service: str = "SMS",
                    display_name: str = "", is_group: bool = False) -> int:
        """Create a new chat entry, return its ROWID."""
        # style: 1 = individual (1-on-1), 43 = group
        style = 43 if is_group else 1
        guid = f"{service};-;{chat_identifier}"

        cursor = self.conn.execute(
            "INSERT INTO chat (guid, style, state, account_id, "
            "chat_identifier, service_name, display_name, group_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (guid, style, 3, f"p:0/{service};-;{chat_identifier}",
             chat_identifier, service, display_name,
             guid if is_group else "")
        )
        self.conn.commit()
        chat_id = cursor.lastrowid
        logger.debug("Created chat %d for %s", chat_id, chat_identifier)
        return chat_id

    def get_or_create_chat(self, chat_identifier: str, service: str = "SMS",
                           display_name: str = "",
                           is_group: bool = False) -> int:
        """Get existing chat or create a new one."""
        chat_id = self.get_chat(chat_identifier, service)
        if chat_id is None:
            chat_id = self.create_chat(chat_identifier, service,
                                       display_name, is_group)
        return chat_id

    def link_chat_handle(self, chat_id: int, handle_id: int):
        """Link a handle to a chat if not already linked."""
        existing = self.conn.execute(
            "SELECT 1 FROM chat_handle_join WHERE chat_id = ? AND handle_id = ?",
            (chat_id, handle_id)
        ).fetchone()
        if not existing:
            self.conn.execute(
                "INSERT INTO chat_handle_join (chat_id, handle_id) VALUES (?, ?)",
                (chat_id, handle_id)
            )
            self.conn.commit()

    # ── Message operations ────────────────────────────────────────────

    def insert_message(self, text: str, handle_id: int, service: str,
                       date_ns: int, is_from_me: bool,
                       subject: Optional[str] = None,
                       has_attachments: bool = False) -> int:
        """Insert a message into the database, return its ROWID."""
        guid = _generate_guid()

        cursor = self.conn.execute(
            """INSERT INTO message (
                guid, text, handle_id, service,
                date, date_read, date_delivered,
                is_from_me, is_read, is_delivered, is_sent,
                is_finished, is_prepared,
                type, cache_has_attachments,
                subject, account_guid
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?
            )""",
            (
                guid, text, handle_id if not is_from_me else 0, service,
                date_ns,
                date_ns if not is_from_me else 0,  # date_read
                date_ns if is_from_me else 0,  # date_delivered
                1 if is_from_me else 0,
                1,  # is_read (all imported messages are "read")
                1 if is_from_me else 0,
                1 if is_from_me else 0,
                1,  # is_finished
                1,  # is_prepared
                0,  # type
                1 if has_attachments else 0,
                subject,
                f"p:0,e:+0",
            )
        )
        # Don't commit yet - caller will batch commit
        return cursor.lastrowid

    def link_message_to_chat(self, chat_id: int, message_id: int,
                             message_date: int):
        """Link a message to a chat."""
        self.conn.execute(
            "INSERT INTO chat_message_join (chat_id, message_id, message_date) "
            "VALUES (?, ?, ?)",
            (chat_id, message_id, message_date)
        )

    # ── Attachment operations ─────────────────────────────────────────

    def insert_attachment(self, filename: str, mime_type: str,
                          transfer_name: str, total_bytes: int,
                          created_date: int,
                          is_outgoing: bool = False) -> int:
        """Insert an attachment record, return its ROWID."""
        guid = _generate_guid()

        cursor = self.conn.execute(
            """INSERT INTO attachment (
                guid, created_date, filename, mime_type,
                transfer_name, total_bytes, transfer_state,
                is_outgoing
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                guid,
                created_date,
                f"~/Library/SMS/Attachments/{filename}",
                mime_type,
                transfer_name,
                total_bytes,
                5,  # transfer_state=5 means complete
                1 if is_outgoing else 0,
            )
        )
        return cursor.lastrowid

    def link_attachment_to_message(self, message_id: int, attachment_id: int):
        """Link an attachment to a message."""
        self.conn.execute(
            "INSERT INTO message_attachment_join (message_id, attachment_id) "
            "VALUES (?, ?)",
            (message_id, attachment_id)
        )

    # ── Batch operations ──────────────────────────────────────────────

    def commit(self):
        """Commit pending changes."""
        self.conn.commit()

    def get_message_count(self) -> int:
        """Get the total number of messages in the database."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM message").fetchone()
        return row["cnt"]

    def get_handle_count(self) -> int:
        """Get the total number of handles in the database."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM handle").fetchone()
        return row["cnt"]

    def get_chat_count(self) -> int:
        """Get the total number of chats in the database."""
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM chat").fetchone()
        return row["cnt"]

    def get_existing_dates_for_chat(self, chat_id: int) -> set[int]:
        """Get all existing message dates for a chat (for deduplication).

        Returns a set of iOS date values (nanoseconds).
        Uses chat_message_join to find all messages in the chat, including
        sent messages (which have handle_id=0).
        """
        rows = self.conn.execute(
            "SELECT message_date FROM chat_message_join WHERE chat_id = ?",
            (chat_id,)
        ).fetchall()
        return {row["message_date"] for row in rows}

    def verify_integrity(self) -> bool:
        """Run a quick integrity check on the database."""
        try:
            result = self.conn.execute("PRAGMA integrity_check").fetchone()
            ok = result[0] == "ok"
            if not ok:
                logger.error("Database integrity check failed: %s", result[0])
            return ok
        except sqlite3.Error as e:
            logger.error("Database integrity check error: %s", e)
            return False
