"""Google Sheets checkpoint store.

Schema (one row per record):
  A: job_id  B: record_id  C: status (pending/done/failed)
  D: text    E: pdf_url    F: updated_at
"""

import json
import os
import time
from typing import Literal

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
Status = Literal["pending", "done", "failed", "stalled"]


def _client(credentials_json: str):
    info = json.loads(credentials_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def read_checkpoint(sheets_id: str, job_id: str, credentials_json: str) -> dict[str, Status]:
    """Return {record_id: status} for all rows belonging to job_id.

    Raises on any API error — never defaults to empty (resume-read-safety rule).
    """
    svc = _client(credentials_json)
    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=sheets_id, range="Sheet1!A:C")
        .execute()
    )
    rows = result.get("values", [])
    checkpoint: dict[str, Status] = {}
    for row in rows:
        if len(row) < 3:
            continue
        if row[0] == job_id:
            checkpoint[row[1]] = row[2]
    return checkpoint


def write_checkpoints(
    sheets_id: str,
    rows: list[dict],
    credentials_json: str,
    batch_size: int = 50,
) -> None:
    """Append or update checkpoint rows in batches to stay under Sheets write quota.

    Each item in rows: {job_id, record_id, status, text, pdf_url}
    Sanitizes text fields against formula injection.
    """
    svc = _client(credentials_json)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _safe(value: str) -> str:
        # Guard against Sheets formula injection
        if value and value[0] in ("=", "+", "-", "@"):
            return "'" + value
        return value

    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        values = [
            [
                r["job_id"],
                r["record_id"],
                r["status"],
                _safe(r.get("text", "")),
                r.get("pdf_url", ""),
                now,
            ]
            for r in chunk
        ]
        body = {"values": values}
        svc.spreadsheets().values().append(
            spreadsheetId=sheets_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
        # Avoid hammering write quota between batches
        if i + batch_size < len(rows):
            time.sleep(0.5)


def mark_job_status(
    sheets_id: str,
    job_id: str,
    status: Status,
    credentials_json: str,
) -> None:
    """Write a single job-level status row (complete / stalled)."""
    write_checkpoints(
        sheets_id,
        [{"job_id": job_id, "record_id": "__job__", "status": status, "text": "", "pdf_url": ""}],
        credentials_json,
    )
