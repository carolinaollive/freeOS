# android-sms-to-iphone

Transfer SMS, MMS, and RCS messages from Android to iPhone — no jailbreak required.

This tool takes an export from the free [SMS Import / Export](https://github.com/tmo1/sms-ie) Android app and injects the messages into an iOS backup. When you restore that backup to your iPhone, all your Android messages appear in the Messages app.

The official "Move to iOS" app is notoriously unreliable, and third-party tools are expensive and sketchy. This is a free, open-source alternative.

## How It Works

1. **Export** your Android messages using the free "SMS Import / Export" app
2. **Create** an unencrypted iPhone backup on your Mac (via Finder)
3. **Run** this tool to inject the Android messages into the backup
4. **Restore** the modified backup to your iPhone

The tool directly modifies the SQLite SMS database inside your iPhone backup. No jailbreak, no cloud services, no proprietary software.

## Requirements

- **macOS** (needed for iPhone backups via Finder)
- **Python 3.9+** (pre-installed on modern macOS)
- **An unencrypted iPhone backup** (created via Finder)
- An Android SMS export from [SMS Import / Export](https://github.com/tmo1/sms-ie)

## Supported Message Types

| Type | Supported | Notes |
|------|-----------|-------|
| SMS  | Yes       | Text messages, fully supported |
| MMS  | Yes       | Group messages and media attachments (images, video, audio) |
| RCS  | Yes       | Parsed from export; imported as SMS (iPhone doesn't have RCS history format) |

## Installation

```bash
pip install .
```

Or run directly without installing:

```bash
python -m android_sms_to_iphone.cli convert export.zip
```

## Quick Start

### Step 1: Export Android Messages

1. Install [SMS Import / Export](https://play.google.com/store/apps/details?id=com.github.tmo1.sms_ie) on your Android phone (also available on [F-Droid](https://f-droid.org/packages/com.github.tmo1.sms_ie/))
2. Open the app and tap **Export Messages**
3. Choose **ZIP** format (this preserves MMS attachments)
4. Save the ZIP file and transfer it to your Mac (via AirDrop, email, USB, cloud drive, etc.)

### Step 2: Create an iPhone Backup

1. Connect your iPhone to your Mac via USB/USB-C
2. Open **Finder** and select your iPhone in the sidebar
3. Under "Backups", **uncheck** "Encrypt local backup"
4. Click **Back Up Now**
5. Wait for the backup to complete

> **Important:** The backup must be **unencrypted**. If you normally use an encrypted backup, temporarily disable encryption for this process, then re-enable it after restoring.

### Step 3: Inject Messages

```bash
# See what's in your export (optional)
android-sms-to-iphone info export.zip

# Dry run — see what would happen without making changes
android-sms-to-iphone convert --dry-run export.zip

# Do the actual conversion
android-sms-to-iphone convert export.zip
```

The tool auto-detects your most recent iOS backup. To specify a backup manually:

```bash
android-sms-to-iphone convert -b ~/Library/Application\ Support/MobileSync/Backup/XXXXX export.zip
```

### Step 4: Restore the Backup

1. Connect your iPhone to your Mac
2. Open **Finder** and select your iPhone
3. Click **Restore Backup...**
4. Select the backup you modified
5. Wait for the restore to complete
6. Your Android messages should now appear in the Messages app!

> **Note:** Restoring a backup replaces the current data on your iPhone with the backup data. Since you just created the backup in Step 2, you won't lose any data — but make sure you didn't receive important new messages between making the backup and restoring.

## Commands

### `convert`

Convert and inject messages into an iOS backup:

```bash
android-sms-to-iphone convert [OPTIONS] INPUT
```

| Option | Description |
|--------|-------------|
| `INPUT` | Path to Android export (ZIP or XML) |
| `-b, --backup PATH` | Path to iOS backup directory (auto-detected if omitted) |
| `--dry-run` | Parse and report without modifying anything |
| `--allow-duplicates` | Don't skip messages that already exist |
| `-v, --verbose` | Show debug output |

### `info`

Show details about an Android export file:

```bash
android-sms-to-iphone info export.zip
```

### `list-backups`

List iOS backups found on this Mac:

```bash
android-sms-to-iphone list-backups
```

## Safety

- The tool **creates backups** of the SMS database and Manifest.db before making changes (`.bak` files alongside the originals)
- Use `--dry-run` first to preview what will happen
- The tool **only adds** messages — it never deletes existing messages or data
- Duplicate detection prevents the same message from being imported twice
- Database integrity checks run automatically after import

## Troubleshooting

### "This backup is encrypted"

Create a new unencrypted backup:
1. Open Finder → Select iPhone → Uncheck "Encrypt local backup"
2. Click "Back Up Now"

### "No iOS backup found"

Make sure you've created a backup via Finder. Backups are stored at:
```
~/Library/Application Support/MobileSync/Backup/
```

### Messages don't appear after restore

- Make sure you restored the correct backup (the one you modified)
- Check that the restore completed without errors
- Try opening a conversation with a contact who sent you messages on Android

### "SMS database not found in backup"

The backup may not include Messages data. Create a new backup and make sure Messages is enabled in your iPhone's iCloud settings (or temporarily disable Messages in iCloud before backing up).

## How It Works (Technical Details)

1. **Parse**: Reads the XML export from "SMS Import / Export" which uses the same format as SMS Backup & Restore (industry standard for Android SMS exports)
2. **Map**: Converts Android message fields to iOS equivalents:
   - Phone numbers → `handle` entries
   - Conversations → `chat` entries
   - Messages → `message` entries with proper iOS timestamps (nanoseconds since 2001-01-01)
   - MMS attachments → `attachment` entries + files in the backup
3. **Inject**: Writes directly into the SQLite SMS database (`sms.db`) inside the iOS backup
4. **Update**: Updates the backup's `Manifest.db` to reflect the modified database

The iOS backup stores files by SHA1 hash. The SMS database is always at hash `3d0d7e5fb2ce288813306e4d4636395e047a3d28` (SHA1 of `HomeDomain-Library/SMS/sms.db`).

## License

MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Some areas that could use help:

- Testing with more export formats and edge cases
- Support for encrypted iOS backups
- Better group chat handling
- Contact name resolution
- Windows/Linux support (would need alternative backup methods)
