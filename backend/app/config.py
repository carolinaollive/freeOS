"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "FreeOS SMS Transfer"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/freeos"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 30  # 30 days

    # Storage (S3-compatible)
    storage_bucket: str = "freeos-transfers"
    storage_endpoint: str = ""  # leave empty for AWS S3
    storage_access_key: str = ""
    storage_secret_key: str = ""
    storage_region: str = "us-east-1"

    # Transfer settings
    max_upload_size_mb: int = 500
    transfer_expiry_hours: int = 72  # auto-delete after 72h

    # Encryption key for messages at rest
    encryption_key: str = ""  # Fernet key, generated if empty

    model_config = {"env_prefix": "FREEOS_"}


settings = Settings()
