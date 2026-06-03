"""Supabase Storage — PDF upload and signed URL generation."""

import hashlib
import time
from pathlib import Path

import requests


def _headers(supabase_key: str) -> dict:
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }


def upload_pdf(
    supabase_url: str,
    supabase_key: str,
    bucket: str,
    job_id: str,
    record_id: str,
    local_path: Path,
    expiry_seconds: int = 3600,
) -> str:
    """Upload PDF to Supabase Storage, verify integrity, return signed URL.

    Raises if the file is too small (corrupt/partial download guard).
    """
    if local_path.stat().st_size < 1024:
        raise RuntimeError(f"PDF for {record_id} is too small — likely corrupt or partial.")

    object_path = f"{job_id}/{record_id}.pdf"
    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path}"

    with open(local_path, "rb") as f:
        data = f.read()

    headers = _headers(supabase_key)
    headers["Content-Type"] = "application/pdf"
    headers["x-upsert"] = "true"

    r = requests.post(upload_url, headers=headers, data=data, timeout=60)
    r.raise_for_status()

    # Generate a signed URL valid for expiry_seconds
    sign_url = f"{supabase_url}/storage/v1/object/sign/{bucket}/{object_path}"
    r2 = requests.post(
        sign_url,
        headers={**_headers(supabase_key), "Content-Type": "application/json"},
        json={"expiresIn": expiry_seconds},
        timeout=15,
    )
    r2.raise_for_status()
    signed_path = r2.json()["signedURL"]

    # signedURL is a path — prepend the Supabase storage base
    base = supabase_url.rstrip("/")
    return f"{base}/storage/v1{signed_path}"
