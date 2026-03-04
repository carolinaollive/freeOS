"""Object storage service for transfer data (S3-compatible)."""

import hashlib
import logging
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

from ..config import settings

logger = logging.getLogger(__name__)


def _get_s3_client():
    """Create an S3 client from settings."""
    kwargs = {
        "region_name": settings.storage_region,
        "config": BotoConfig(signature_version="s3v4"),
    }
    if settings.storage_endpoint:
        kwargs["endpoint_url"] = settings.storage_endpoint
    if settings.storage_access_key:
        kwargs["aws_access_key_id"] = settings.storage_access_key
        kwargs["aws_secret_access_key"] = settings.storage_secret_key
    return boto3.client("s3", **kwargs)


def upload_attachment(transfer_id: str, message_id: str, filename: str,
                      data: bytes, content_type: str) -> str:
    """Upload an attachment to object storage. Returns the storage key."""
    data_hash = hashlib.sha256(data).hexdigest()[:12]
    key = f"transfers/{transfer_id}/attachments/{message_id}/{data_hash}/{filename}"

    client = _get_s3_client()
    client.put_object(
        Bucket=settings.storage_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    logger.info("Uploaded attachment: %s (%d bytes)", key, len(data))
    return key


def generate_download_url(storage_key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed download URL for an attachment."""
    client = _get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.storage_bucket, "Key": storage_key},
        ExpiresIn=expires_in,
    )


def generate_upload_url(storage_key: str, content_type: str,
                        expires_in: int = 3600) -> str:
    """Generate a pre-signed upload URL for direct client upload."""
    client = _get_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.storage_bucket,
            "Key": storage_key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )


def delete_transfer_data(transfer_id: str):
    """Delete all stored data for a transfer."""
    client = _get_s3_client()
    prefix = f"transfers/{transfer_id}/"

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.storage_bucket, Prefix=prefix):
        objects = page.get("Contents", [])
        if objects:
            client.delete_objects(
                Bucket=settings.storage_bucket,
                Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
            )
    logger.info("Deleted transfer data: %s", prefix)
