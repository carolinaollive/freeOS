"""Command-line interface for android-sms-to-iphone."""

import argparse
import logging
import sys

from . import __version__
from . import converter
from . import ios_backup


def setup_logging(verbose: bool = False):
    """Configure logging output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def cmd_convert(args):
    """Run the message conversion."""
    backup_dir = ios_backup.find_backup(args.backup)

    print(f"Android export: {args.input}")
    print(f"iOS backup:     {backup_dir}")
    print()

    if args.dry_run:
        print("DRY RUN MODE - no changes will be made")
        print()

    stats = converter.convert(
        export_path=args.input,
        backup_dir=backup_dir,
        skip_duplicates=not args.allow_duplicates,
        dry_run=args.dry_run,
    )

    print()
    print("=" * 50)
    print("CONVERSION RESULTS")
    print("=" * 50)
    print(stats.summary())
    print()

    if not args.dry_run and stats.inserted > 0:
        print("SUCCESS! Next steps:")
        print("  1. Open Finder on your Mac")
        print("  2. Connect your iPhone via USB")
        print("  3. Select your iPhone in Finder's sidebar")
        print("  4. Click 'Restore Backup...'")
        print(f"  5. Select the backup at: {backup_dir}")
        print("  6. Wait for the restore to complete")
        print("  7. Your Android messages should now appear in the Messages app!")
        print()
        print("NOTE: Restoring a backup will replace current iPhone data with the")
        print("      backup data. Make sure your backup is recent before restoring.")
    elif args.dry_run:
        print("Dry run complete. Run without --dry-run to apply changes.")


def cmd_list_backups(args):
    """List available iOS backups."""
    backups = ios_backup.list_backups()

    if not backups:
        print("No iOS backups found.")
        print()
        print("To create a backup:")
        print("  1. Connect your iPhone to your Mac via USB")
        print("  2. Open Finder and select your iPhone")
        print("  3. Make sure 'Encrypt local backup' is UNCHECKED")
        print("  4. Click 'Back Up Now'")
        return

    print(f"Found {len(backups)} iOS backup(s):\n")
    for i, b in enumerate(backups, 1):
        name = b.get("device_name", "Unknown")
        model = b.get("product_type", "")
        ios_ver = b.get("ios_version", "")
        encrypted = b.get("encrypted")
        last = b.get("last_backup")

        enc_str = ""
        if encrypted is True:
            enc_str = " [ENCRYPTED - cannot use]"
        elif encrypted is False:
            enc_str = " [unencrypted - OK]"

        print(f"  {i}. {name} ({model}, iOS {ios_ver}){enc_str}")
        if last:
            print(f"     Last backup: {last}")
        print(f"     Path: {b['path']}")
        print()


def cmd_info(args):
    """Show info about an Android export file."""
    from . import android_parser

    print(f"Parsing: {args.input}")
    print()

    messages = android_parser.parse_export(args.input)

    if not messages:
        print("No messages found in export.")
        return

    # Gather stats
    sms = sum(1 for m in messages if m.msg_type == "sms")
    mms = sum(1 for m in messages if m.msg_type == "mms")
    rcs = sum(1 for m in messages if m.msg_type == "rcs")
    sent = sum(1 for m in messages if m.is_sent)
    received = sum(1 for m in messages if not m.is_sent)
    with_attachments = sum(1 for m in messages if m.attachments)
    total_attachments = sum(len(m.attachments) for m in messages)

    # Unique contacts
    contacts = set(m.address for m in messages)

    # Date range
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
        print(f"Date range:    {earliest.strftime('%Y-%m-%d')} to {latest.strftime('%Y-%m-%d')}")

    if args.verbose:
        print(f"\nTop contacts by message count:")
        from collections import Counter
        contact_counts = Counter(m.address for m in messages)
        for addr, count in contact_counts.most_common(20):
            print(f"  {addr}: {count} messages")


def main():
    parser = argparse.ArgumentParser(
        prog="android-sms-to-iphone",
        description="Transfer SMS/MMS/RCS messages from Android to iPhone",
        epilog="For detailed instructions, see: https://github.com/nicholasgasior/android-sms-to-iphone",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose/debug output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # convert command
    p_convert = subparsers.add_parser(
        "convert",
        help="Convert Android messages and inject into iOS backup",
        description="Parse an Android SMS export and inject messages into an iOS backup.",
    )
    p_convert.add_argument(
        "input",
        help="Path to Android SMS export file (ZIP or XML from 'SMS Import / Export' app)",
    )
    p_convert.add_argument(
        "-b", "--backup",
        help="Path to iOS backup directory (auto-detected on macOS if not specified)",
    )
    p_convert.add_argument(
        "--dry-run", action="store_true",
        help="Parse and report without modifying the backup",
    )
    p_convert.add_argument(
        "--allow-duplicates", action="store_true",
        help="Don't skip messages that appear to already exist in the backup",
    )
    p_convert.set_defaults(func=cmd_convert)

    # list-backups command
    p_list = subparsers.add_parser(
        "list-backups",
        help="List available iOS backups on this Mac",
    )
    p_list.set_defaults(func=cmd_list_backups)

    # info command
    p_info = subparsers.add_parser(
        "info",
        help="Show information about an Android SMS export file",
    )
    p_info.add_argument(
        "input",
        help="Path to Android SMS export file (ZIP or XML)",
    )
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
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
