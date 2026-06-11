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
) -> str:
    """Upload PDF to a PUBLIC Supabase Storage bucket, return its public URL.

    The bucket must be public (no token, never expires). Raises if the file is
    too small (corrupt/partial download guard).
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

    # Public URL — permanent, no token (bucket is public).
    base = supabase_url.rstrip("/")
    return f"{base}/storage/v1/object/public/{bucket}/{object_path}"
