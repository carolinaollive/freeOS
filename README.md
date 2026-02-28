# android-sms-to-iphone

Transfer SMS, MMS, and RCS messages from Android to iPhone — no jailbreak required.

The official "Move to iOS" app is notoriously unreliable, and third-party tools are expensive and sketchy. This is a free, open-source alternative.

## Usage

**On your Android phone:**

1. Install the free [SMS Import / Export](https://github.com/tmo1/sms-ie) app ([Google Play](https://play.google.com/store/apps/details?id=com.github.tmo1.sms_ie) / [F-Droid](https://f-droid.org/packages/com.github.tmo1.sms_ie/))
2. Export your messages as a **ZIP** file
3. Transfer the ZIP to your computer (email it to yourself, USB, cloud drive, etc.)

**On your computer (macOS or Linux):**

4. Connect your iPhone via USB, unlock it, and tap "Trust" if prompted
5. Run:

```bash
android-sms-to-iphone transfer export.zip
```

That's it. The tool automatically backs up your iPhone, injects the messages, and restores. Your Android messages will appear in the Messages app.

## What it supports

| Type | Supported | Notes |
|------|-----------|-------|
| SMS  | Yes       | Text messages |
| MMS  | Yes       | Group messages and media (images, video, audio) |
| RCS  | Yes       | Imported as SMS (iPhone has no RCS history format) |

## Install

**1. Install libimobiledevice** (handles iPhone communication):

```bash
# macOS
brew install libimobiledevice

# Ubuntu / Debian
sudo apt install libimobiledevice-utils

# Fedora
sudo dnf install libimobiledevice-utils
```

**2. Install this tool:**

```bash
pip install .
```

Or run directly without installing:

```bash
python -m android_sms_to_iphone.cli transfer export.zip
```

## Commands

### `transfer` (main command)

```bash
android-sms-to-iphone transfer export.zip
```

Backs up your iPhone, injects messages, and restores — all in one step.

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview what would be transferred without touching the iPhone |
| `--backup-dir DIR` | Store the backup in a specific directory |
| `--allow-duplicates` | Don't skip messages that already exist |
| `-v, --verbose` | Show detailed debug output |

### `info`

```bash
android-sms-to-iphone info export.zip
```

Show what's in an Android export file (message counts, contacts, date range) without connecting an iPhone.

## Important notes

- **No jailbreak required.** The tool works by modifying an iPhone backup and restoring it — a supported Apple workflow.
- **Backup encryption must be off.** If your iPhone uses encrypted backups, temporarily disable it in Finder (or Settings > General > Transfer or Reset) before running the tool. You can re-enable it afterward.
- **Messages in iCloud:** If you use Messages in iCloud, temporarily disable it (Settings > [your name] > iCloud > Messages) before creating the backup, otherwise the SMS database may be empty. Re-enable it after the restore.
- **Your data is safe.** The tool only *adds* messages — it never deletes anything. It also creates `.bak` safety copies of every file it modifies.
- **Duplicate detection** prevents the same message from being imported twice if you run the tool again.

## How it works

1. Creates an iPhone backup via `libimobiledevice` (same protocol as Finder/iTunes)
2. Parses the Android message export (NDJSON from SMS Import / Export, or XML from SMS Backup & Restore)
3. Injects messages into the backup's SQLite SMS database (`sms.db`), creating proper handle, chat, message, and attachment entries
4. Restores the modified backup to the iPhone

No cloud services, no proprietary software, no jailbreak.

## Troubleshooting

### "No iPhone detected"

- Make sure your iPhone is connected via USB and **unlocked**
- Tap "Trust" on the iPhone if it asks
- Try unplugging and re-plugging the cable

### "Backup encryption" error

Disable encrypted backups:
- **macOS:** Finder > select iPhone > uncheck "Encrypt local backup"
- **iPhone:** Settings > General > Transfer or Reset iPhone > Reset All Settings (this resets the encryption flag without erasing data)

### Messages don't appear after restore

- Disable Messages in iCloud (Settings > [your name] > iCloud > Messages) before creating the backup
- Make sure the restore completed without errors
- Try opening a specific conversation — messages may not show in the list until you open the thread

## License

MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Areas that could use help:

- Testing with diverse export files and edge cases
- Support for encrypted iOS backups (decryption + re-encryption)
- Better group chat handling
- Contact name resolution
- Windows support
