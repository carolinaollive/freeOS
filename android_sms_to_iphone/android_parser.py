"""Parse SMS/MMS/RCS messages exported by the 'SMS Import / Export' Android app.

The 'SMS Import / Export' app (tmo1/sms-ie) exports messages as a ZIP containing:
  - messages.ndjson  (one JSON object per line: SMS records first, then MMS)
  - data/            (binary MMS attachment files)

NDJSON SMS record example:
  {"_id":"123","address":"+15551234567","date":"1700000000000","type":"1",
   "body":"Hello!","__display_name":"Alice"}

NDJSON MMS record example:
  {"_id":"456","date":"1700000","msg_box":"1",
   "__sender_address":{"address":"+15559876543","type":"137"},
   "__recipient_addresses":[{"address":"+15551234567","type":"151"}],
   "__parts":[
     {"ct":"text/plain","text":"Check this out!"},
     {"ct":"image/jpeg","_data":"PART_1234","cl":"photo.jpg","fn":"photo.jpg"}
   ]}

Also supports XML format from 'SMS Backup & Restore' (SyncTech) as a fallback.

SMS type values: 1=received, 2=sent, 3=draft, 4=outbox, 5=failed, 6=queued
MMS msg_box values: 1=received, 2=sent, 3=draft, 4=outbox
MMS addr type values: 137=FROM, 151=TO, 130=BCC, 129=CC
"""

import base64
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# SMS type constants
SMS_RECEIVED = 1
SMS_SENT = 2

# MMS msg_box constants
MMS_RECEIVED = 1
MMS_SENT = 2

# MMS address type constants
MMS_ADDR_FROM = 137
MMS_ADDR_TO = 151


@dataclass
class Attachment:
    """A media attachment from an MMS/RCS message."""
    content_type: str
    data: bytes
    filename: str
    content_location: str = ""


@dataclass
class Message:
    """A parsed message (SMS, MMS, or RCS) from Android export."""
    address: str  # phone number (normalized)
    timestamp_ms: int  # Unix timestamp in milliseconds
    is_sent: bool  # True if sent by user, False if received
    body: str  # Text content

    msg_type: str = "sms"  # "sms", "mms", or "rcs"

    attachments: list[Attachment] = field(default_factory=list)
    subject: Optional[str] = None

    # Group MMS: list of all participant addresses (excluding primary)
    participants: list[str] = field(default_factory=list)
    is_group: bool = False

    raw_attrs: dict = field(default_factory=dict)


def normalize_phone(number: str) -> str:
    """Normalize a phone number by stripping non-digit chars except leading +."""
    if not number:
        return number
    number = number.strip()
    if number.startswith("+"):
        return "+" + re.sub(r"[^\d]", "", number[1:])
    return re.sub(r"[^\d]", "", number)


def _ext_for_mime(mime: str) -> str:
    """Get a file extension for a MIME type."""
    mapping = {
        "image/jpeg": "jpg", "image/png": "png", "image/gif": "gif",
        "image/webp": "webp", "image/bmp": "bmp",
        "video/mp4": "mp4", "video/3gpp": "3gp", "video/3gpp2": "3g2",
        "audio/amr": "amr", "audio/mpeg": "mp3", "audio/ogg": "ogg",
        "audio/aac": "aac", "application/pdf": "pdf",
        "text/vcard": "vcf", "text/x-vcard": "vcf",
    }
    return mapping.get(mime, "bin")


# ── NDJSON parsing (SMS Import / Export app by tmo1) ─────────────────


def _parse_ndjson_sms(record: dict) -> Optional[Message]:
    """Parse a single SMS JSON record from NDJSON export."""
    address = normalize_phone(record.get("address", ""))
    if not address:
        logger.warning("Skipping SMS with no address")
        return None

    try:
        timestamp_ms = int(record.get("date", "0"))
    except (ValueError, TypeError):
        timestamp_ms = 0

    try:
        sms_type = int(record.get("type", "1"))
    except (ValueError, TypeError):
        sms_type = 1

    body = record.get("body", "") or ""
    subject = record.get("subject")
    if subject in (None, "null", ""):
        subject = None

    return Message(
        address=address,
        timestamp_ms=timestamp_ms,
        is_sent=(sms_type == SMS_SENT),
        body=body,
        msg_type="sms",
        subject=subject,
        raw_attrs=record,
    )


def _parse_ndjson_mms(record: dict,
                      zip_file: Optional[zipfile.ZipFile] = None) -> Optional[Message]:
    """Parse a single MMS JSON record from NDJSON export."""
    try:
        date_val = int(record.get("date", "0"))
    except (ValueError, TypeError):
        date_val = 0

    # MMS dates from Android are in SECONDS, not milliseconds
    if date_val > 0 and date_val < 10_000_000_000:
        timestamp_ms = date_val * 1000
    else:
        timestamp_ms = date_val

    try:
        msg_box = int(record.get("msg_box", "1"))
    except (ValueError, TypeError):
        msg_box = 1

    is_sent = (msg_box == MMS_SENT)

    subject = record.get("sub") or record.get("subject")
    if subject in (None, "null", ""):
        subject = None

    # Detect RCS from content type
    ct_t = (record.get("ct_t", "") or "").lower()
    is_rcs = "rcs" in ct_t

    # Parse addresses from __sender_address and __recipient_addresses
    from_addresses = []
    to_addresses = []
    all_addresses = []

    sender = record.get("__sender_address")
    if sender and isinstance(sender, dict):
        addr = normalize_phone(sender.get("address", ""))
        if addr and addr != "insert-address-token":
            from_addresses.append(addr)
            all_addresses.append(addr)

    recipients = record.get("__recipient_addresses", [])
    if isinstance(recipients, list):
        for r in recipients:
            if isinstance(r, dict):
                addr = normalize_phone(r.get("address", ""))
                if addr and addr != "insert-address-token":
                    to_addresses.append(addr)
                    all_addresses.append(addr)

    # Determine primary address (the other party)
    if is_sent and to_addresses:
        address = to_addresses[0]
    elif not is_sent and from_addresses:
        address = from_addresses[0]
    elif all_addresses:
        address = all_addresses[0]
    else:
        logger.warning("Skipping MMS with no address, date=%s", timestamp_ms)
        return None

    # Group detection
    participants = list(set(all_addresses) - {address})
    is_group = len(set(all_addresses)) > 2 or len(to_addresses) > 1

    # Parse parts
    body_parts = []
    attachments = []
    parts = record.get("__parts", [])

    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue

            ct = part.get("ct", "")
            text = part.get("text", "")
            data_ref = part.get("_data", "")
            cl = part.get("cl", "")
            fn = part.get("fn", "") or part.get("name", "") or cl

            if ct == "text/plain":
                if text and text != "null":
                    body_parts.append(text)
            elif ct.startswith("application/smil"):
                continue
            else:
                # Media attachment
                data = b""

                # Check for base64-encoded BLOB data
                for key in part:
                    if key.endswith("__base64__"):
                        try:
                            data = base64.b64decode(part[key])
                        except Exception:
                            logger.warning("Failed to decode base64 for %s", fn)
                        break

                # Load from ZIP data/ directory
                if not data and zip_file and data_ref:
                    # _data contains the filename (just the last path segment)
                    data_filename = os.path.basename(data_ref)
                    possible_paths = [
                        f"data/{data_filename}",
                        data_filename,
                        data_ref,
                    ]
                    for p in possible_paths:
                        try:
                            data = zip_file.read(p)
                            break
                        except KeyError:
                            continue

                if data:
                    filename = fn or f"attachment.{_ext_for_mime(ct)}"
                    attachments.append(Attachment(
                        content_type=ct,
                        data=data,
                        filename=filename,
                        content_location=cl,
                    ))
                elif ct not in ("text/plain",):
                    logger.debug("MMS part with no data: ct=%s fn=%s", ct, fn)

    body = "\n".join(body_parts)

    return Message(
        address=address,
        timestamp_ms=timestamp_ms,
        is_sent=is_sent,
        body=body,
        msg_type="rcs" if is_rcs else "mms",
        attachments=attachments,
        subject=subject,
        participants=participants,
        is_group=is_group,
        raw_attrs=record,
    )


def _is_mms_record(record: dict) -> bool:
    """Determine if a JSON record is MMS (vs SMS).

    MMS records have __parts, __sender_address, or msg_box fields.
    SMS records have type, body, protocol fields.
    """
    return ("__parts" in record or "__sender_address" in record or
            "msg_box" in record)


def parse_ndjson(data: str,
                 zip_file: Optional[zipfile.ZipFile] = None) -> list[Message]:
    """Parse NDJSON-formatted message data (from SMS Import / Export app)."""
    messages = []
    sms_count = mms_count = rcs_count = skipped = 0

    for line_num, line in enumerate(data.splitlines(), 1):
        line = line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as e:
            logger.warning("Skipping invalid JSON on line %d: %s", line_num, e)
            skipped += 1
            continue

        if not isinstance(record, dict):
            skipped += 1
            continue

        if _is_mms_record(record):
            msg = _parse_ndjson_mms(record, zip_file=zip_file)
            if msg:
                messages.append(msg)
                if msg.msg_type == "rcs":
                    rcs_count += 1
                else:
                    mms_count += 1
            else:
                skipped += 1
        else:
            msg = _parse_ndjson_sms(record)
            if msg:
                messages.append(msg)
                sms_count += 1
            else:
                skipped += 1

    logger.info("Parsed %d messages: %d SMS, %d MMS, %d RCS (%d skipped)",
                len(messages), sms_count, mms_count, rcs_count, skipped)
    return messages


# ── XML parsing (SMS Backup & Restore fallback) ─────────────────────


def _parse_xml_sms(elem: ET.Element) -> Optional[Message]:
    """Parse a single <sms> XML element."""
    attrs = dict(elem.attrib)
    address = normalize_phone(attrs.get("address", ""))
    if not address:
        logger.warning("Skipping SMS with no address")
        return None

    try:
        timestamp_ms = int(attrs.get("date", "0"))
    except ValueError:
        timestamp_ms = 0

    try:
        sms_type = int(attrs.get("type", "1"))
    except ValueError:
        sms_type = 1

    body = attrs.get("body", "")
    subject_raw = attrs.get("subject", "null")
    subject = None if subject_raw == "null" else subject_raw

    return Message(
        address=address,
        timestamp_ms=timestamp_ms,
        is_sent=(sms_type == SMS_SENT),
        body=body or "",
        msg_type="sms",
        subject=subject,
        raw_attrs=attrs,
    )


def _parse_xml_mms(elem: ET.Element,
                   zip_file: Optional[zipfile.ZipFile] = None,
                   xml_dir: str = "") -> Optional[Message]:
    """Parse a single <mms> XML element including parts and addresses."""
    attrs = dict(elem.attrib)

    try:
        timestamp_ms = int(attrs.get("date", "0"))
    except ValueError:
        timestamp_ms = 0

    if timestamp_ms > 0 and timestamp_ms < 10_000_000_000:
        timestamp_ms *= 1000

    try:
        msg_box = int(attrs.get("msg_box", "1"))
    except ValueError:
        msg_box = 1

    is_sent = (msg_box == MMS_SENT)

    subject_raw = attrs.get("sub", attrs.get("subject", "null"))
    subject = None if subject_raw in ("null", "None", "") else subject_raw

    ct = attrs.get("ct_t", "")
    is_rcs = "rcs" in ct.lower()

    # Parse addresses
    from_addresses = []
    to_addresses = []
    all_addresses = []

    addrs_elem = elem.find("addrs")
    if addrs_elem is not None:
        for addr_elem in addrs_elem.findall("addr"):
            addr_str = normalize_phone(addr_elem.get("address", ""))
            if not addr_str or addr_str == "insert-address-token":
                continue
            try:
                addr_type = int(addr_elem.get("type", "151"))
            except ValueError:
                addr_type = 151

            all_addresses.append(addr_str)
            if addr_type == MMS_ADDR_FROM:
                from_addresses.append(addr_str)
            else:
                to_addresses.append(addr_str)

    address = attrs.get("address", "")
    if address:
        address = normalize_phone(address)
    elif is_sent and to_addresses:
        address = to_addresses[0]
    elif not is_sent and from_addresses:
        address = from_addresses[0]
    elif all_addresses:
        address = all_addresses[0]

    if not address:
        logger.warning("Skipping MMS with no address, date=%s", timestamp_ms)
        return None

    participants = list(set(all_addresses) - {address})
    is_group = len(set(all_addresses)) > 2 or len(to_addresses) > 1

    body_parts = []
    attachments = []
    parts_elem = elem.find("parts")

    if parts_elem is not None:
        for part_elem in parts_elem.findall("part"):
            part_ct = part_elem.get("ct", "")
            part_text = part_elem.get("text", "")
            part_data = part_elem.get("data", "")
            part_cl = part_elem.get("cl", "")
            part_name = part_elem.get("name", part_cl)

            if part_ct == "text/plain":
                if part_text and part_text != "null":
                    body_parts.append(part_text)
            elif part_ct.startswith("application/smil"):
                continue
            else:
                data = b""
                if part_data and part_data != "null":
                    try:
                        data = base64.b64decode(part_data)
                    except Exception:
                        logger.warning("Failed to decode base64 for %s", part_name)

                if not data and zip_file and part_cl:
                    for p in [part_cl, os.path.join(xml_dir, part_cl),
                              part_name, os.path.join(xml_dir, part_name)]:
                        try:
                            data = zip_file.read(p)
                            break
                        except KeyError:
                            continue

                if data:
                    filename = part_name or part_cl or f"attachment.{_ext_for_mime(part_ct)}"
                    attachments.append(Attachment(
                        content_type=part_ct, data=data,
                        filename=filename, content_location=part_cl,
                    ))

    body = "\n".join(body_parts)

    return Message(
        address=address,
        timestamp_ms=timestamp_ms,
        is_sent=is_sent,
        body=body,
        msg_type="rcs" if is_rcs else "mms",
        attachments=attachments,
        subject=subject,
        participants=participants,
        is_group=is_group,
        raw_attrs=attrs,
    )


def parse_xml_file(xml_path: str,
                   zip_file: Optional[zipfile.ZipFile] = None) -> list[Message]:
    """Parse an SMS/MMS XML export file (SMS Backup & Restore format)."""
    logger.info("Parsing XML file: %s", xml_path)
    xml_dir = os.path.dirname(xml_path) if xml_path else ""

    tree = ET.parse(xml_path)
    root = tree.getroot()

    messages = []
    for elem in root:
        if elem.tag == "sms":
            msg = _parse_xml_sms(elem)
            if msg:
                messages.append(msg)
        elif elem.tag == "mms":
            msg = _parse_xml_mms(elem, zip_file=zip_file, xml_dir=xml_dir)
            if msg:
                messages.append(msg)

    logger.info("Parsed %d messages from XML", len(messages))
    return messages


def parse_xml_string(xml_data: str,
                     zip_file: Optional[zipfile.ZipFile] = None,
                     xml_dir: str = "") -> list[Message]:
    """Parse XML from a string (e.g., extracted from ZIP)."""
    root = ET.fromstring(xml_data)
    messages = []
    for elem in root:
        if elem.tag == "sms":
            msg = _parse_xml_sms(elem)
            if msg:
                messages.append(msg)
        elif elem.tag == "mms":
            msg = _parse_xml_mms(elem, zip_file=zip_file, xml_dir=xml_dir)
            if msg:
                messages.append(msg)
    return messages


# ── Unified entry points ─────────────────────────────────────────────


def parse_export_zip(zip_path: str) -> list[Message]:
    """Parse an SMS Import/Export ZIP file and return all messages.

    Supports both NDJSON (SMS Import / Export by tmo1) and XML
    (SMS Backup & Restore) formats inside the ZIP.
    """
    logger.info("Opening export ZIP: %s", zip_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()

        # Check for NDJSON files (SMS Import / Export format)
        ndjson_files = [n for n in names
                        if n.endswith(".ndjson") or n.endswith(".jsonl")]
        if ndjson_files:
            logger.info("Detected NDJSON format (SMS Import / Export app)")
            all_messages = []
            for ndjson_name in ndjson_files:
                data = zf.read(ndjson_name).decode("utf-8")
                msgs = parse_ndjson(data, zip_file=zf)
                all_messages.extend(msgs)
            logger.info("Total messages parsed from ZIP: %d", len(all_messages))
            return all_messages

        # Fallback: check for XML files (SMS Backup & Restore format)
        xml_files = [n for n in names if n.endswith(".xml")]
        if xml_files:
            logger.info("Detected XML format (SMS Backup & Restore)")
            all_messages = []
            for xml_name in xml_files:
                xml_data = zf.read(xml_name).decode("utf-8")
                msgs = parse_xml_string(xml_data, zip_file=zf,
                                        xml_dir=os.path.dirname(xml_name))
                all_messages.extend(msgs)
            logger.info("Total messages parsed from ZIP: %d", len(all_messages))
            return all_messages

        # Last resort: try to parse any .json files as NDJSON
        json_files = [n for n in names if n.endswith(".json")]
        if json_files:
            logger.info("Trying JSON files as NDJSON")
            all_messages = []
            for json_name in json_files:
                data = zf.read(json_name).decode("utf-8")
                msgs = parse_ndjson(data, zip_file=zf)
                all_messages.extend(msgs)
            if all_messages:
                return all_messages

        raise ValueError(
            f"No message files found in {zip_path}. "
            "Expected .ndjson (SMS Import / Export) or .xml (SMS Backup & Restore) files."
        )


def parse_export(path: str) -> list[Message]:
    """Parse an export file (ZIP, XML, or NDJSON) and return all messages.

    Automatically detects the format.
    """
    if zipfile.is_zipfile(path):
        return parse_export_zip(path)

    # Try to detect format by reading the first bytes
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()

    # NDJSON starts with {
    if first_line.startswith("{"):
        logger.info("Detected NDJSON file")
        with open(path, "r", encoding="utf-8") as f:
            data = f.read()
        return parse_ndjson(data)

    # XML starts with < or <?xml
    if first_line.startswith("<"):
        logger.info("Detected XML file")
        return parse_xml_file(path)

    raise ValueError(
        f"Unrecognized file format: {path}. "
        "Expected a ZIP archive, NDJSON file, or XML file."
    )
