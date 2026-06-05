"""Supabase checkpoint store.

Table schema (create this in Supabase SQL editor):

  create table checkpoints (
    id          bigint generated always as identity primary key,
    job_id      text not null,
    record_id   text not null,
    status      text not null,  -- pending | done | failed | stalled
    text        text default '',
    pdf_url     text default '',
    updated_at  timestamptz default now(),
    unique (job_id, record_id)
  );

  create index on checkpoints (job_id);
"""

import os
import time
from typing import Literal

import requests

Status = Literal["pending", "done", "failed", "stalled", "complete", "running"]


def _headers(supabase_key: str) -> dict:
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",  # upsert behaviour
    }


def read_checkpoint(supabase_url: str, supabase_key: str, job_id: str) -> dict[str, str]:
    """Return {record_id: status} for all rows belonging to job_id.

    Raises on any HTTP error — never defaults to empty (resume-read-safety rule).
    """
    url = f"{supabase_url}/rest/v1/checkpoints"
    params = {"job_id": f"eq.{job_id}", "select": "record_id,status"}
    r = requests.get(url, headers=_headers(supabase_key), params=params, timeout=15)
    r.raise_for_status()
    return {row["record_id"]: row["status"] for row in r.json()}


def write_checkpoints(
    supabase_url: str,
    supabase_key: str,
    rows: list[dict],
    batch_size: int = 50,
) -> None:
    """Upsert checkpoint rows in batches.

    Each item in rows: {job_id, record_id, status, text, pdf_url}
    Sanitizes text against formula injection (defensive even without Sheets).
    """
    # on_conflict tells PostgREST to merge on the (job_id, record_id) unique
    # constraint rather than the primary key. Without it, an upsert that
    # collides on that constraint returns 409 Conflict instead of merging.
    url = f"{supabase_url}/rest/v1/checkpoints?on_conflict=job_id,record_id"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _safe(value: str) -> str:
        if value and value[0] in ("=", "+", "-", "@"):
            return "'" + value
        return value

    for i in range(0, len(rows), batch_size):
        chunk = [
            {
                "job_id": r["job_id"],
                "record_id": r["record_id"],
                "status": r["status"],
                "text": _safe(r.get("text", "")),
                "pdf_url": r.get("pdf_url", ""),
                "updated_at": now,
            }
            for r in rows[i : i + batch_size]
        ]
        headers = _headers(supabase_key)
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        r = requests.post(url, headers=headers, json=chunk, timeout=15)
        r.raise_for_status()


def mark_job_status(
    supabase_url: str,
    supabase_key: str,
    job_id: str,
    status: Status,
) -> None:
    write_checkpoints(
        supabase_url,
        supabase_key,
        [{"job_id": job_id, "record_id": "__job__", "status": status, "text": "", "pdf_url": ""}],
    )
