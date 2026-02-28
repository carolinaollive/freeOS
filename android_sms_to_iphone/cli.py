"""Command-line interface for android-sms-to-iphone.

The primary command is `transfer`: plug in your iPhone, point it at your
Android export ZIP, and it handles everything (backup, inject, restore).
"""

import argparse
import logging
import os
import sys
import tempfile

from . import __version__
from . import converter
from . import device
from . import ios_backup


def setup_logging(verbose: bool = False):
    """Configure logging output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def cmd_transfer(args):
    """Full automated transfer: backup iPhone -> inject messages -> restore."""
    export_path = args.input

    if not os.path.isfile(export_path):
        print(f"Error: File not found: {export_path}", file=sys.stderr)
        sys.exit(1)

    # Preview what we're importing
    from . import android_parser
    print(f"Reading: {export_path}")
    messages = android_parser.parse_export(export_path)
    if not messages:
        print("No messages found in export file.")
        sys.exit(1)

    sms = sum(1 for m in messages if m.msg_type == "sms")
    mms = sum(1 for m in messages if m.msg_type == "mms")
    rcs = sum(1 for m in messages if m.msg_type == "rcs")
    contacts = len(set(m.address for m in messages))
    print(f"Found {len(messages)} messages ({sms} SMS, {mms} MMS, {rcs} RCS) "
          f"across {contacts} contacts")
    print()

    if args.dry_run:
        print("Dry run complete. Run without --dry-run to transfer.")
        return

    # Check for libimobiledevice tools
    device.check_tools()

    # Detect iPhone
    udid = device.wait_for_device(timeout=30)
    device_name = device.get_device_name(udid)
    print(f"Found: {device_name}")
    print()

    # Make sure we're paired
    device.ensure_paired(udid)

    # Determine backup location
    if args.backup_dir:
        backup_parent = os.path.expanduser(args.backup_dir)
    else:
        backup_parent = tempfile.mkdtemp(prefix="android-sms-to-iphone-")

    # Step 1: Create backup
    print("=" * 50)
    print("STEP 1/3: Backing up iPhone")
    print("=" * 50)
    backup_dir = device.create_backup(backup_parent, udid)
    print()

    # Step 2: Inject messages
    print("=" * 50)
    print("STEP 2/3: Injecting messages")
    print("=" * 50)
    stats = converter.convert(
        export_path=export_path,
        backup_dir=backup_dir,
        skip_duplicates=not args.allow_duplicates,
    )
    print(stats.summary())
    print()

    if stats.inserted == 0:
        print("No new messages to add (all duplicates). Done!")
        return

    # Step 3: Restore backup
    print("=" * 50)
    print("STEP 3/3: Restoring to iPhone")
    print("=" * 50)
    device.restore_backup(backup_dir, udid)
    print()

    print("=" * 50)
    print("DONE!")
    print("=" * 50)
    print(f"Transferred {stats.inserted} messages to your iPhone.")
    print("Open the Messages app to see your Android messages.")


def cmd_info(args):
    """Show info about an Android export file."""
    from . import android_parser

    print(f"Parsing: {args.input}")
    print()

    messages = android_parser.parse_export(args.input)

    if not messages:
        print("No messages found in export.")
        return

    sms = sum(1 for m in messages if m.msg_type == "sms")
    mms = sum(1 for m in messages if m.msg_type == "mms")
    rcs = sum(1 for m in messages if m.msg_type == "rcs")
    sent = sum(1 for m in messages if m.is_sent)
    received = sum(1 for m in messages if not m.is_sent)
    with_attachments = sum(1 for m in messages if m.attachments)
    total_attachments = sum(len(m.attachments) for m in messages)
    contacts = set(m.address for m in messages)

    dates = [m.timestamp_ms for m in messages if m.timestamp_ms > 0]
    if dates:
        from datetime import datetime, timezone
        earliest = datetime.fromtimestamp(min(dates) / 1000, tz=timezone.utc)
        latest = datetime.fromtimestamp(max(dates) / 1000, tz=timezone.utc)
    else:
        earliest = latest = None

    print(f"Messages:      {len(messages)} total")
    print(f"  SMS:         {sms}")
    print(f"  MMS:         {mms}")
    print(f"  RCS:         {rcs}")
    print(f"  Sent:        {sent}")
    print(f"  Received:    {received}")
    print(f"Contacts:      {len(contacts)} unique")
    print(f"Attachments:   {total_attachments} across {with_attachments} messages")
    if earliest and latest:
        print(f"Date range:    {earliest.strftime('%Y-%m-%d')} to "
              f"{latest.strftime('%Y-%m-%d')}")

    if args.verbose:
        print(f"\nTop contacts by message count:")
        from collections import Counter
        contact_counts = Counter(m.address for m in messages)
        for addr, count in contact_counts.most_common(20):
            print(f"  {addr}: {count} messages")


def main():
    parser = argparse.ArgumentParser(
        prog="android-sms-to-iphone",
        description=(
            "Transfer SMS/MMS/RCS messages from Android to iPhone.\n\n"
            "Quick start:\n"
            "  1. Export messages on Android using the 'SMS Import / Export' app\n"
            "  2. Connect your iPhone via USB\n"
            "  3. Run: android-sms-to-iphone transfer export.zip"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose/debug output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # transfer command (primary)
    p_transfer = subparsers.add_parser(
        "transfer",
        help="Transfer Android messages to a connected iPhone (one step)",
        description=(
            "Backs up your iPhone, injects the Android messages, "
            "and restores -- all automatically."
        ),
    )
    p_transfer.add_argument(
        "input",
        help="Path to Android SMS export (ZIP from 'SMS Import / Export' app)",
    )
    p_transfer.add_argument(
        "--backup-dir",
        help="Directory to store the iPhone backup (temp dir if not specified)",
    )
    p_transfer.add_argument(
        "--dry-run", action="store_true",
        help="Just show what would be transferred, don't touch the iPhone",
    )
    p_transfer.add_argument(
        "--allow-duplicates", action="store_true",
        help="Don't skip messages that already exist on the iPhone",
    )
    p_transfer.set_defaults(func=cmd_transfer)

    # info command
    p_info = subparsers.add_parser(
        "info",
        help="Show details about an Android SMS export file",
    )
    p_info.add_argument(
        "input",
        help="Path to Android SMS export (ZIP or NDJSON)",
    )
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except device.DeviceError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
