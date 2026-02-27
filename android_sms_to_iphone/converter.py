"""Convert Android messages to iOS format and inject them into an iOS backup.

This is the main orchestration module that:
1. Parses Android export (ZIP or XML)
2. Opens the iOS backup's SMS database
3. Groups messages by conversation
4. Creates handles, chats, and inserts messages with deduplication
5. Handles MMS/RCS attachments
6. Updates the iOS backup manifest
"""

import hashlib
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from . import android_parser
from . import ios_backup
from . import ios_sms_db

logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # Commit every N messages


@dataclass
class ConversionStats:
    """Statistics from a conversion run."""
    total_parsed: int = 0
    sms_count: int = 0
    mms_count: int = 0
    rcs_count: int = 0
    inserted: int = 0
    skipped_duplicate: int = 0
    skipped_error: int = 0
    attachments_added: int = 0
    handles_created: int = 0
    chats_created: int = 0

    def summary(self) -> str:
        lines = [
            f"Parsed:      {self.total_parsed} messages "
            f"({self.sms_count} SMS, {self.mms_count} MMS, {self.rcs_count} RCS)",
            f"Inserted:    {self.inserted} messages",
            f"Attachments: {self.attachments_added}",
            f"Contacts:    {self.handles_created} new handles",
            f"Chats:       {self.chats_created} new conversations",
        ]
        if self.skipped_duplicate:
            lines.append(f"Duplicates:  {self.skipped_duplicate} skipped")
        if self.skipped_error:
            lines.append(f"Errors:      {self.skipped_error} skipped")
        return "\n".join(lines)


def _detect_country(phone: str) -> str:
    """Detect country code from phone number. Defaults to 'us'."""
    if phone.startswith("+1"):
        return "us"
    elif phone.startswith("+44"):
        return "gb"
    elif phone.startswith("+49"):
        return "de"
    elif phone.startswith("+33"):
        return "fr"
    elif phone.startswith("+81"):
        return "jp"
    elif phone.startswith("+86"):
        return "cn"
    elif phone.startswith("+91"):
        return "in"
    elif phone.startswith("+61"):
        return "au"
    elif phone.startswith("+55"):
        return "br"
    elif phone.startswith("+52"):
        return "mx"
    elif phone.startswith("+82"):
        return "kr"
    elif phone.startswith("+39"):
        return "it"
    elif phone.startswith("+34"):
        return "es"
    elif phone.startswith("+7"):
        return "ru"
    return "us"


def convert(export_path: str, backup_dir: str,
            skip_duplicates: bool = True,
            dry_run: bool = False) -> ConversionStats:
    """Convert Android messages and inject them into an iOS backup.

    Args:
        export_path: Path to the Android SMS export (ZIP or XML file)
        backup_dir: Path to the iOS backup directory
        skip_duplicates: If True, skip messages that appear to already exist
        dry_run: If True, parse and report but don't modify the backup

    Returns:
        ConversionStats with details about what was done
    """
    stats = ConversionStats()

    # 1. Parse Android export
    logger.info("Parsing Android export: %s", export_path)
    messages = android_parser.parse_export(export_path)
    stats.total_parsed = len(messages)

    for msg in messages:
        if msg.msg_type == "sms":
            stats.sms_count += 1
        elif msg.msg_type == "mms":
            stats.mms_count += 1
        elif msg.msg_type == "rcs":
            stats.rcs_count += 1

    if not messages:
        logger.warning("No messages found in export")
        return stats

    logger.info("Parsed %d messages", len(messages))

    if dry_run:
        logger.info("Dry run mode - not modifying backup")
        return stats

    # 2. Open iOS SMS database
    sms_db_path = ios_backup.get_sms_db_path(backup_dir)

    # Create a safety backup
    ios_backup.backup_file(sms_db_path)

    # Also backup Manifest.db
    manifest_path = os.path.join(backup_dir, "Manifest.db")
    ios_backup.backup_file(manifest_path)

    existing_msg_count = 0
    existing_handle_count = 0
    existing_chat_count = 0

    with ios_sms_db.iOSSmsDb(sms_db_path) as db:
        existing_msg_count = db.get_message_count()
        existing_handle_count = db.get_handle_count()
        existing_chat_count = db.get_chat_count()

        logger.info("Existing database: %d messages, %d handles, %d chats",
                     existing_msg_count, existing_handle_count, existing_chat_count)

        # 3. Group messages by conversation (address)
        conversations: dict[str, list[android_parser.Message]] = defaultdict(list)
        for msg in messages:
            conversations[msg.address].append(msg)

        logger.info("Found %d unique conversations", len(conversations))

        # Cache for deduplication (keyed by chat_id)
        existing_dates_cache: dict[int, set[int]] = {}

        # 4. Process each conversation
        batch_count = 0

        for address, conv_messages in conversations.items():
            # Sort messages by timestamp
            conv_messages.sort(key=lambda m: m.timestamp_ms)

            # All Android SMS/MMS arrive as "SMS" service in iOS
            # (they weren't iMessages on Android)
            service = "SMS"
            country = _detect_country(address)

            # Get or create handle
            handle_id = db.get_or_create_handle(address, service, country)
            if handle_id > existing_handle_count:
                stats.handles_created += 1

            # Get or create chat
            is_group = any(m.is_group for m in conv_messages)
            chat_id = db.get_or_create_chat(
                address, service,
                display_name="",
                is_group=is_group,
            )
            if chat_id > existing_chat_count:
                stats.chats_created += 1

            # Link handle to chat
            db.link_chat_handle(chat_id, handle_id)

            # For group chats, also create handles for other participants
            if is_group:
                for msg in conv_messages:
                    for participant in msg.participants:
                        p_handle_id = db.get_or_create_handle(
                            participant, service, _detect_country(participant)
                        )
                        db.link_chat_handle(chat_id, p_handle_id)

            # Load existing dates for deduplication (keyed by chat)
            if skip_duplicates and chat_id not in existing_dates_cache:
                existing_dates_cache[chat_id] = db.get_existing_dates_for_chat(chat_id)

            # 5. Insert messages
            for msg in conv_messages:
                ios_date = ios_sms_db.unix_ms_to_ios_date(msg.timestamp_ms)

                # Deduplication: check if message with same date exists in this chat
                if skip_duplicates:
                    existing = existing_dates_cache.get(chat_id, set())
                    if ios_date in existing:
                        stats.skipped_duplicate += 1
                        continue

                try:
                    has_attachments = bool(msg.attachments)

                    # Insert message
                    message_id = db.insert_message(
                        text=msg.body,
                        handle_id=handle_id,
                        service=service,
                        date_ns=ios_date,
                        is_from_me=msg.is_sent,
                        subject=msg.subject,
                        has_attachments=has_attachments,
                    )

                    # Link message to chat
                    db.link_message_to_chat(chat_id, message_id, ios_date)

                    # Handle attachments
                    for i, att in enumerate(msg.attachments):
                        unique_id = f"{msg.address}_{msg.timestamp_ms}_{i}"
                        hash_prefix = hashlib.sha256(unique_id.encode()).hexdigest()[:8]
                        att_filename = f"{hash_prefix}/{att.filename}"

                        # Add attachment file to backup
                        file_id, rel_path = ios_backup.add_attachment_to_backup(
                            backup_dir, att.data, att.filename, unique_id
                        )

                        # Insert attachment record in SMS database
                        att_id = db.insert_attachment(
                            filename=rel_path,
                            mime_type=att.content_type,
                            transfer_name=att.filename,
                            total_bytes=len(att.data),
                            created_date=ios_date,
                            is_outgoing=msg.is_sent,
                        )

                        # Link attachment to message
                        db.link_attachment_to_message(message_id, att_id)
                        stats.attachments_added += 1

                    stats.inserted += 1

                    # Track for deduplication
                    if skip_duplicates:
                        if chat_id not in existing_dates_cache:
                            existing_dates_cache[chat_id] = set()
                        existing_dates_cache[chat_id].add(ios_date)

                    # Batch commit
                    batch_count += 1
                    if batch_count >= BATCH_SIZE:
                        db.commit()
                        batch_count = 0
                        logger.info("Progress: %d/%d messages inserted",
                                    stats.inserted, stats.total_parsed)

                except Exception as e:
                    logger.error("Failed to insert message (date=%s, addr=%s): %s",
                                 msg.timestamp_ms, msg.address, e)
                    stats.skipped_error += 1

        # Final commit
        db.commit()

        # Verify database integrity
        if not db.verify_integrity():
            logger.error("WARNING: Database integrity check failed after import!")
        else:
            logger.info("Database integrity check passed")

        final_count = db.get_message_count()
        logger.info("Final database: %d messages (was %d, added %d)",
                     final_count, existing_msg_count,
                     final_count - existing_msg_count)

    # 6. Update manifest
    ios_backup.update_sms_db_manifest(backup_dir)

    logger.info("Conversion complete!\n%s", stats.summary())
    return stats
