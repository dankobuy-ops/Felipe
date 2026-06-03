"""Main scraper entry point — crash-aware, checkpointed, time-bounded."""

import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from checkpoint import mark_job_status, read_checkpoint, write_checkpoints
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


def scrape(args, supabase_url: str, supabase_key: str, supabase_bucket: str) -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_seconds

    # Read checkpoint — raises on failure (resume-read-safety rule)
    checkpoint = read_checkpoint(supabase_url, supabase_key, args.job_id)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            page.goto(args.target_url, wait_until="networkidle", timeout=30_000)
        except PlaywrightTimeout:
            write_status("crashed")
            raise RuntimeError(f"Target did not load within 30s: {args.target_url}")

        try:
            page.fill("[name=search_code], input[type=text]", args.search_code)
            page.keyboard.press("Enter")
            # Wait for a positive "results loaded" signal — never accept silence as 0 results
            page.wait_for_selector("[data-results], .results-list, table tbody tr", timeout=20_000)
        except PlaywrightTimeout:
            write_status("crashed")
            raise RuntimeError(
                "Results container never appeared — target may have crashed or returned nothing. "
                "Cannot distinguish 0-results from crash without a positive signal."
            )

        records = page.query_selector_all("[data-record-id], .result-row, table tbody tr")
        if not records:
            write_status("crashed")
            raise RuntimeError("Result list empty after positive signal — unexpected state.")

        pending: list[dict] = []

        for record in records:
            if time.monotonic() >= deadline:
                break

            record_id = record.get_attribute("data-record-id") or record.inner_text()[:40]

            if checkpoint.get(record_id) == "done":
                continue

            try:
                text = record.inner_text().strip()
                pdf_url = ""

                pdf_link = record.query_selector("a[href$='.pdf'], a[href*='pdf']")
                if pdf_link:
                    local_pdf = DOWNLOAD_DIR / f"{record_id}.pdf"
                    with page.expect_download() as dl_info:
                        pdf_link.click()
                    dl_info.value.save_as(str(local_pdf))

                    pdf_url = upload_pdf(
                        supabase_url, supabase_key, supabase_bucket,
                        args.job_id, record_id, local_pdf,
                    )

                pending.append({
                    "job_id": args.job_id,
                    "record_id": record_id,
                    "status": "done",
                    "text": text,
                    "pdf_url": pdf_url,
                })

                # Flush immediately so a crash doesn't lose this record
                write_checkpoints(supabase_url, supabase_key, pending)
                pending.clear()

            except PlaywrightTimeout:
                pending.append({
                    "job_id": args.job_id,
                    "record_id": record_id,
                    "status": "failed",
                    "text": "",
                    "pdf_url": "",
                })
                write_checkpoints(supabase_url, supabase_key, pending)
                write_status("crashed")
                raise

        browser.close()

    final = read_checkpoint(supabase_url, supabase_key, args.job_id)
    all_done = all(v == "done" for k, v in final.items() if k != "__job__")

    if all_done and final:
        mark_job_status(supabase_url, supabase_key, args.job_id, "complete")
        write_status("complete")
    else:
        write_status("incomplete")


def main():
    args = parse_args()
    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_SERVICE_KEY"]
    supabase_bucket = os.environ.get("SUPABASE_BUCKET", "pdfs")

    try:
        scrape(args, supabase_url, supabase_key, supabase_bucket)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
