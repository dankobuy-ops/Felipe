"""Google Cloud Storage — PDF upload + signed URL generation."""

import hashlib
import json
import os
import time
from pathlib import Path

from google.cloud import storage
from google.oauth2 import service_account


def _client(credentials_json: str) -> storage.Client:
    info = json.loads(credentials_json)
    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return storage.Client(credentials=creds, project=info["project_id"])


def upload_pdf(
    bucket_name: str,
    job_id: str,
    record_id: str,
    local_path: Path,
    credentials_json: str,
    expiry_seconds: int = 3600,
) -> str:
    """Upload PDF, verify integrity, return signed URL valid for expiry_seconds.

    Raises if the uploaded object hash doesn't match the local file (PDF integrity check).
    """
    client = _client(credentials_json)
    bucket = client.bucket(bucket_name)
    blob_name = f"{job_id}/{record_id}.pdf"
    blob = bucket.blob(blob_name)

    local_md5 = _md5(local_path)

    blob.upload_from_filename(str(local_path), content_type="application/pdf")

    # Reload to get the server-side MD5
    blob.reload()
    remote_md5 = blob.md5_hash  # base64-encoded by GCS
    import base64
    remote_md5_hex = base64.b64decode(remote_md5).hex()

    if remote_md5_hex != local_md5:
        blob.delete()
        raise RuntimeError(
            f"PDF integrity check failed for {record_id}: "
            f"local={local_md5} remote={remote_md5_hex}. Deleted remote copy."
        )

    info = json.loads(credentials_json)
    signing_creds = service_account.Credentials.from_service_account_info(info)
    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=expiry_seconds,
        method="GET",
        credentials=signing_creds,
    )
    return signed_url


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
