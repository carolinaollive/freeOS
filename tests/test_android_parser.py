"""Tests for the Android SMS/MMS/RCS parser."""

import json
import os
import tempfile
import zipfile

import pytest

from android_sms_to_iphone.android_parser import (
    Message,
    normalize_phone,
    parse_export,
    parse_ndjson,
    parse_xml_file,
)


class TestNormalizePhone:
    def test_basic(self):
        assert normalize_phone("+12345678900") == "+12345678900"

    def test_strips_formatting(self):
        assert normalize_phone("+1 (234) 567-8900") == "+12345678900"

    def test_no_plus(self):
        assert normalize_phone("2345678900") == "2345678900"

    def test_empty(self):
        assert normalize_phone("") == ""

    def test_whitespace(self):
        assert normalize_phone("  +1234  ") == "+1234"


# ── NDJSON test data (SMS Import / Export format) ────────────────────

NDJSON_SMS_LINES = [
    json.dumps({
        "_id": "1", "address": "+12025551234", "date": "1609459200000",
        "type": "1", "body": "Happy New Year!", "read": "1",
        "__display_name": "Alice",
    }),
    json.dumps({
        "_id": "2", "address": "+12025551234", "date": "1609459260000",
        "type": "2", "body": "Thanks! You too!", "read": "1",
        "__display_name": "Alice",
    }),
    json.dumps({
        "_id": "3", "address": "+12025559999", "date": "1609459300000",
        "type": "1", "body": "Hey there", "read": "1",
        "__display_name": "Bob",
    }),
]

NDJSON_MMS = json.dumps({
    "_id": "100", "date": "1609459200", "msg_box": "1",
    "ct_t": "application/vnd.wap.multipart.related",
    "__sender_address": {
        "address": "+12025551234", "type": "137", "charset": "106",
        "__display_name": "Alice",
    },
    "__recipient_addresses": [
        {"address": "+12025559999", "type": "151", "charset": "106"},
    ],
    "__parts": [
        {"seq": "0", "ct": "application/smil", "text": "<smil>...</smil>"},
        {"seq": "1", "ct": "text/plain", "text": "Check this out!"},
        {"seq": "2", "ct": "image/jpeg", "_data": "photo.jpg",
         "cl": "photo.jpg", "fn": "photo.jpg"},
    ],
})

NDJSON_RCS = json.dumps({
    "_id": "200", "date": "1609459200", "msg_box": "2",
    "ct_t": "application/vnd.rcs",
    "__sender_address": {
        "address": "+12025559999", "type": "137",
    },
    "__recipient_addresses": [
        {"address": "+12025551234", "type": "151"},
    ],
    "__parts": [
        {"seq": "0", "ct": "text/plain", "text": "RCS message here"},
    ],
})

NDJSON_GROUP_MMS = json.dumps({
    "_id": "300", "date": "1609459200", "msg_box": "1",
    "__sender_address": {
        "address": "+12025551111", "type": "137",
    },
    "__recipient_addresses": [
        {"address": "+12025552222", "type": "151"},
        {"address": "+12025553333", "type": "151"},
    ],
    "__parts": [
        {"seq": "0", "ct": "text/plain", "text": "Group message!"},
    ],
})


# ── XML test data (SMS Backup & Restore fallback) ───────────────────

SIMPLE_SMS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<smses count="3">
  <sms protocol="0" address="+12025551234" date="1609459200000" type="1"
       subject="null" body="Happy New Year!" read="1" status="-1" />
  <sms protocol="0" address="+12025551234" date="1609459260000" type="2"
       subject="null" body="Thanks! You too!" read="1" status="-1" />
  <sms protocol="0" address="+12025559999" date="1609459300000" type="1"
       subject="null" body="Hey there" read="1" status="-1" />
</smses>
"""

MMS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<smses count="1">
  <mms date="1609459200000" msg_box="1" address="+12025551234"
       ct_t="application/vnd.wap.multipart.related" sub="null">
    <parts>
      <part seq="0" ct="application/smil" data="null" text="&lt;smil&gt;" />
      <part seq="1" ct="text/plain" data="null" text="Check this out!" />
      <part seq="2" ct="image/jpeg" data="iVBORw0KGgo=" cl="photo.jpg" name="photo.jpg" />
    </parts>
    <addrs>
      <addr address="+12025551234" type="137" />
      <addr address="+12025559999" type="151" />
    </addrs>
  </mms>
</smses>
"""


def _write_temp(content: str, suffix: str = ".xml") -> str:
    """Write content to a temporary file and return the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


# ── NDJSON Tests ─────────────────────────────────────────────────────

class TestParseNdjsonSms:
    def test_parse_sms(self):
        data = "\n".join(NDJSON_SMS_LINES)
        messages = parse_ndjson(data)
        assert len(messages) == 3

        m = messages[0]
        assert m.address == "+12025551234"
        assert m.timestamp_ms == 1609459200000
        assert m.is_sent is False
        assert m.body == "Happy New Year!"
        assert m.msg_type == "sms"

        m = messages[1]
        assert m.is_sent is True
        assert m.body == "Thanks! You too!"

        m = messages[2]
        assert m.address == "+12025559999"

    def test_parse_mms(self):
        messages = parse_ndjson(NDJSON_MMS)
        assert len(messages) == 1

        m = messages[0]
        assert m.msg_type == "mms"
        assert m.is_sent is False
        assert m.body == "Check this out!"
        assert m.address == "+12025551234"
        # No attachment data loaded (no ZIP file provided)
        assert len(m.attachments) == 0

    def test_parse_mms_date_in_seconds(self):
        """MMS dates from Android are in seconds, should be converted to ms."""
        messages = parse_ndjson(NDJSON_MMS)
        m = messages[0]
        assert m.timestamp_ms == 1609459200000  # 1609459200 * 1000

    def test_parse_rcs(self):
        messages = parse_ndjson(NDJSON_RCS)
        assert len(messages) == 1

        m = messages[0]
        assert m.msg_type == "rcs"
        assert m.is_sent is True
        assert m.body == "RCS message here"

    def test_parse_group_mms(self):
        messages = parse_ndjson(NDJSON_GROUP_MMS)
        assert len(messages) == 1

        m = messages[0]
        assert m.is_group is True
        assert m.msg_type == "mms"
        assert m.body == "Group message!"

    def test_skips_invalid_json(self):
        data = "not valid json\n" + NDJSON_SMS_LINES[0]
        messages = parse_ndjson(data)
        assert len(messages) == 1

    def test_empty_lines_skipped(self):
        data = "\n\n" + NDJSON_SMS_LINES[0] + "\n\n"
        messages = parse_ndjson(data)
        assert len(messages) == 1

    def test_mixed_sms_and_mms(self):
        data = "\n".join(NDJSON_SMS_LINES + [NDJSON_MMS])
        messages = parse_ndjson(data)
        sms = [m for m in messages if m.msg_type == "sms"]
        mms = [m for m in messages if m.msg_type == "mms"]
        assert len(sms) == 3
        assert len(mms) == 1


class TestParseNdjsonZip:
    def test_parse_ndjson_zip(self):
        """Test parsing NDJSON messages from a ZIP file."""
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = tmp.name

        try:
            ndjson_data = "\n".join(NDJSON_SMS_LINES)
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("messages.ndjson", ndjson_data)

            messages = parse_export(zip_path)
            assert len(messages) == 3
            assert messages[0].body == "Happy New Year!"
        finally:
            os.unlink(zip_path)

    def test_parse_zip_with_mms_attachments(self):
        """Test parsing MMS with attachments from ZIP data/ directory."""
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = tmp.name

        try:
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("messages.ndjson", NDJSON_MMS)
                zf.writestr("data/photo.jpg", b"fake jpeg data")

            messages = parse_export(zip_path)
            assert len(messages) == 1
            m = messages[0]
            assert len(m.attachments) == 1
            assert m.attachments[0].content_type == "image/jpeg"
            assert m.attachments[0].data == b"fake jpeg data"
            assert m.attachments[0].filename == "photo.jpg"
        finally:
            os.unlink(zip_path)


# ── XML Tests (SMS Backup & Restore fallback) ───────────────────────

class TestParseXml:
    def test_parse_simple_sms_xml(self):
        path = _write_temp(SIMPLE_SMS_XML)
        try:
            messages = parse_xml_file(path)
            assert len(messages) == 3

            m = messages[0]
            assert m.address == "+12025551234"
            assert m.timestamp_ms == 1609459200000
            assert m.is_sent is False
            assert m.body == "Happy New Year!"
            assert m.msg_type == "sms"
        finally:
            os.unlink(path)

    def test_parse_mms_xml(self):
        path = _write_temp(MMS_XML)
        try:
            messages = parse_xml_file(path)
            assert len(messages) == 1

            m = messages[0]
            assert m.msg_type == "mms"
            assert m.body == "Check this out!"
            assert len(m.attachments) == 1
            assert m.attachments[0].content_type == "image/jpeg"
        finally:
            os.unlink(path)

    def test_parse_xml_in_zip(self):
        """Test parsing XML format inside a ZIP (SMS Backup & Restore)."""
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = tmp.name

        try:
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("messages.xml", SIMPLE_SMS_XML)

            messages = parse_export(zip_path)
            assert len(messages) == 3
        finally:
            os.unlink(zip_path)


# ── Format detection tests ───────────────────────────────────────────

class TestFormatDetection:
    def test_detect_ndjson_file(self):
        """parse_export should auto-detect raw NDJSON files."""
        path = _write_temp("\n".join(NDJSON_SMS_LINES), suffix=".ndjson")
        try:
            messages = parse_export(path)
            assert len(messages) == 3
        finally:
            os.unlink(path)

    def test_detect_xml_file(self):
        """parse_export should auto-detect raw XML files."""
        path = _write_temp(SIMPLE_SMS_XML, suffix=".xml")
        try:
            messages = parse_export(path)
            assert len(messages) == 3
        finally:
            os.unlink(path)

    def test_ndjson_zip_preferred_over_xml(self):
        """When ZIP has both NDJSON and XML, NDJSON should be preferred."""
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = tmp.name

        try:
            ndjson_data = NDJSON_SMS_LINES[0]  # 1 message
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("messages.ndjson", ndjson_data)
                zf.writestr("messages.xml", SIMPLE_SMS_XML)  # 3 messages

            messages = parse_export(zip_path)
            # Should parse NDJSON (1 msg), not XML (3 msgs)
            assert len(messages) == 1
        finally:
            os.unlink(zip_path)
