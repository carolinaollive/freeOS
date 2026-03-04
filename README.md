# FreeOS — Transfer Everything from Android to iPhone

Two apps. One platform. Sign in with Google and transfer all your messages.

No cables, no export apps, no command line. Just install, sign in, and go.

## How it works

### On your Android phone:

1. Install the **FreeOS Transfer** app from Google Play
2. Sign in with Google
3. Tap **Start Transfer** — the app reads your SMS/MMS directly and uploads them

### On your iPhone:

1. Install the **FreeOS Transfer** app from the App Store
2. Sign in with the **same Google account**
3. Tap the ready transfer — your messages download automatically
4. Connect your iPhone to a computer to complete the restore

That's it. Your Android messages appear in the iPhone Messages app.

## What it transfers

| Type | Supported | Notes |
|------|-----------|-------|
| SMS  | Yes       | Text messages |
| MMS  | Yes       | Group messages, images, video, audio |
| RCS  | Yes       | Imported as SMS (iPhone has no RCS history format) |

## Architecture

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│  Android App │ ──────▶ │  Backend API │ ◀────── │   iOS App   │
│  (Kotlin)    │  upload  │  (FastAPI)   │ download │  (Swift)    │
└─────────────┘         └─────────────┘         └─────────────┘
       │                       │                       │
  Google SSO              PostgreSQL              Google SSO
  SMS Reader              S3 Storage           Message Import
  Auto-upload             Auto-cleanup          Backup Restore
```

### Android App (`android/`)
- **Kotlin + Jetpack Compose** — Material 3, Hilt DI
- Reads SMS/MMS directly from the device via `ContentResolver` (no third-party export app needed)
- Google Sign-In for account creation
- Batched upload with progress tracking

### iOS App (`ios/`)
- **Swift + SwiftUI** — native iOS design
- Google Sign-In — same account as Android
- Downloads messages from the backend
- Saves as NDJSON for the desktop restore tool
- Guides the user through the final backup-restore step

### Backend API (`backend/`)
- **Python + FastAPI** — async, high performance
- Google OAuth2 token verification
- PostgreSQL for user accounts and message metadata
- S3-compatible storage for attachments
- JWT authentication
- Auto-cleanup: transfers expire after 72 hours
- Messages encrypted in transit (TLS) and at rest

### CLI Tool (`android_sms_to_iphone/`)
The original command-line tool is still included for power users who prefer to transfer via USB without a cloud service:
```bash
android-sms-to-iphone transfer export.zip
```

## Security

- **Google SSO only** — no passwords to manage
- **Messages encrypted in transit** via TLS
- **Auto-deletion** — all transfer data is automatically deleted after 72 hours
- **No data mining** — messages are never read or analyzed by the platform
- **Open source** — audit the code yourself

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Environment variables (prefix with `FREEOS_`):
- `FREEOS_DATABASE_URL` — PostgreSQL connection string
- `FREEOS_GOOGLE_CLIENT_ID` — Google OAuth client ID
- `FREEOS_GOOGLE_CLIENT_SECRET` — Google OAuth client secret
- `FREEOS_JWT_SECRET` — Secret key for JWT tokens
- `FREEOS_STORAGE_BUCKET` — S3 bucket name
- `FREEOS_STORAGE_ENDPOINT` — S3-compatible endpoint (optional)
- `FREEOS_STORAGE_ACCESS_KEY` — S3 access key
- `FREEOS_STORAGE_SECRET_KEY` — S3 secret key

### Android

Open `android/` in Android Studio. Set your Google Client ID in `app/build.gradle.kts`.

### iOS

Open `ios/SMSTransfer/` in Xcode. Set your Google Client ID in `Services/AppConfig.swift`.

### CLI (legacy)

```bash
pip install .
android-sms-to-iphone transfer export.zip
```

## Project structure

```
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── main.py             # App entry point
│   │   ├── config.py           # Environment config
│   │   ├── auth.py             # Google SSO + JWT
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── schemas.py          # Pydantic schemas
│   │   ├── database.py         # DB connection
│   │   ├── routes/
│   │   │   ├── auth.py         # POST /auth/google, GET /auth/me
│   │   │   ├── transfers.py    # CRUD for transfer sessions
│   │   │   └── messages.py     # Upload/download messages
│   │   └── services/
│   │       ├── storage.py      # S3 attachment storage
│   │       └── transfer.py     # Transfer business logic
│   ├── Dockerfile
│   └── requirements.txt
├── android/                    # Android app (Kotlin)
│   └── app/src/main/java/com/freeos/smstransfer/
│       ├── MainActivity.kt
│       ├── sms/SmsReader.kt    # Reads SMS/MMS from device
│       ├── data/api/           # Retrofit API client
│       ├── data/repository/    # Transfer orchestration
│       └── ui/screens/         # Compose UI
├── ios/                        # iOS app (Swift)
│   └── SMSTransfer/
│       ├── SMSTransferApp.swift
│       ├── Auth/               # Google Sign-In
│       ├── Services/           # API client, message importer
│       └── Views/              # SwiftUI screens
├── android_sms_to_iphone/      # Original CLI tool
└── tests/                      # CLI tool tests
```

## License

MIT License. See [LICENSE](LICENSE) for details.
