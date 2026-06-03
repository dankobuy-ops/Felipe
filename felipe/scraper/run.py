"""Main scraper entry point — crash-aware, checkpointed, time-bounded."""

import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from sheets import mark_job_status, read_checkpoint, write_checkpoints
from storage import upload_pdf

STATUS_FILE = Path("/tmp/scrape_status")
DOWNLOAD_DIR = Path("/tmp/pdfs")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--job-id", required=True)
    p.add_argument("--search-code", required=True)
    p.add_argument("--target-url", required=True)
    p.add_argument("--max-seconds", type=int, default=240)
    return p.parse_args()


def write_status(status: str) -> None:
    STATUS_FILE.write_text(status)


def scrape(args, sheets_id: str, gcs_bucket: str, credentials_json: str) -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_seconds

    # Read checkpoint — raises on failure (resume-read-safety rule)
    checkpoint = read_checkpoint(sheets_id, args.job_id, credentials_json)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        # Navigate to target
        try:
            page.goto(args.target_url, wait_until="networkidle", timeout=30_000)
        except PlaywrightTimeout:
            write_status("crashed")
            raise RuntimeError(f"Target did not load within 30s: {args.target_url}")

        # Enter search code and submit
        try:
            page.fill("[name=search_code], input[type=text]", args.search_code)
            page.keyboard.press("Enter")
            # Wait for a positive "results loaded" signal — never accept silence as 0 results
            page.wait_for_selector("[data-results], .results-list, table tbody tr", timeout=20_000)
        except PlaywrightTimeout:
            write_status("crashed")
            raise RuntimeError(
                "Results container never appeared — target may have crashed or search returned nothing. "
                "Cannot distinguish 0-results from crash without a positive signal."
            )

        records = page.query_selector_all("[data-record-id], .result-row, table tbody tr")
        if not records:
            write_status("crashed")
            raise RuntimeError("Result list empty after positive signal — unexpected state.")

        pending_checkpoints: list[dict] = []

        for record in records:
            if time.monotonic() >= deadline:
                # Out of time — flush what we have and let the workflow re-dispatch
                break

            record_id = record.get_attribute("data-record-id") or record.inner_text()[:40]

            if checkpoint.get(record_id) == "done":
                continue  # Already processed in a previous run

            try:
                text = record.inner_text().strip()

                # Download PDF if a link exists
                pdf_url = ""
                pdf_link = record.query_selector("a[href$='.pdf'], a[href*='pdf']")
                if pdf_link:
                    local_pdf = DOWNLOAD_DIR / f"{record_id}.pdf"
                    with page.expect_download() as dl_info:
                        pdf_link.click()
                    download = dl_info.value
                    download.save_as(str(local_pdf))

                    # Verify PDF is not empty/corrupt before uploading
                    if local_pdf.stat().st_size < 1024:
                        raise RuntimeError(f"Downloaded PDF for {record_id} is too small — likely corrupt.")

                    pdf_url = upload_pdf(
                        gcs_bucket, args.job_id, record_id, local_pdf, credentials_json
                    )

                pending_checkpoints.append({
                    "job_id": args.job_id,
                    "record_id": record_id,
                    "status": "done",
                    "text": text,
                    "pdf_url": pdf_url,
                })

                # Flush immediately so a crash doesn't lose this record
                write_checkpoints(sheets_id, pending_checkpoints, credentials_json)
                pending_checkpoints.clear()

            except PlaywrightTimeout:
                # Target crashed mid-record — mark failed, stop, let workflow re-dispatch
                pending_checkpoints.append({
                    "job_id": args.job_id,
                    "record_id": record_id,
                    "status": "failed",
                    "text": "",
                    "pdf_url": "",
                })
                write_checkpoints(sheets_id, pending_checkpoints, credentials_json)
                write_status("crashed")
                raise

        browser.close()

    # Check if all records are done
    final_checkpoint = read_checkpoint(sheets_id, args.job_id, credentials_json)
    all_done = all(v == "done" for k, v in final_checkpoint.items() if k != "__job__")

    if all_done and final_checkpoint:
        mark_job_status(sheets_id, args.job_id, "complete", credentials_json)
        write_status("complete")
    else:
        write_status("incomplete")


def main():
    args = parse_args()
    sheets_id = os.environ["SHEETS_ID"]
    gcs_bucket = os.environ["GCS_BUCKET"]
    credentials_json = os.environ["GCP_CREDENTIALS_JSON"]

    try:
        scrape(args, sheets_id, gcs_bucket, credentials_json)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        # Do not catch-all silently — let the workflow see the non-zero exit
        # so the re-dispatch step knows to fire
        sys.exit(1)


if __name__ == "__main__":
    main()
