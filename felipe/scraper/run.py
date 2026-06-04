"""Main scraper — crash-aware, checkpointed, time-bounded.

Entry pattern: always navigate via the municipality parent page and click
"CONSULTA DE CAUSAS" to establish a fresh session on the JPL system.
Direct navigation to appl.smc.cl does NOT recover a crashed session.
"""

import argparse
import json
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

# Selectors for Chilean JPL (ASP.NET WebForms pattern, shared by all municipalities)
SEL_ENTRY_LINK   = "a:has-text('CONSULTA DE CAUSAS'), a:has-text('Consulta de Causas'), a:has-text('consulta de causas')"
SEL_RUT_INPUT    = "input[id$='txtRut'], input[name*='Rut'], input[name*='rut'], input[id*='Rut']"
SEL_SEARCH_BTN   = "input[id$='btnBuscar'], input[id$='btnSearch'], button:has-text('Buscar'), input[type='submit']"
SEL_RESULTS_ROW  = "table#gvResultados tbody tr, table[id*='Grid'] tbody tr, table[id*='grid'] tbody tr, table tbody tr"
SEL_PDF_LINK     = "a[href$='.pdf'], a[href*='GetDocumento'], a[href*='documento'], a[href*='Documento']"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--job-id", required=True)
    p.add_argument("--search-code", required=True, help="RUT to search")
    p.add_argument("--target-url", required=True, help="Municipality parent page URL")
    p.add_argument("--max-seconds", type=int, default=240)
    return p.parse_args()


def write_status(status: str) -> None:
    STATUS_FILE.write_text(status)


def _dump_page(page, label: str) -> None:
    """Log current URL + HTML to stdout so GHA logs show the page state on failure."""
    print(f"[DEBUG {label}] URL: {page.url}", flush=True)
    print(f"[DEBUG {label}] HTML (first 3000 chars):\n{page.content()[:3000]}", flush=True)


def enter_via_parent(page, parent_url: str) -> None:
    """Navigate to municipality page and click the entry link to establish a fresh JPL session."""
    try:
        page.goto(parent_url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        write_status("crashed")
        raise RuntimeError(f"Parent page did not load within 30s: {parent_url}")

    try:
        page.wait_for_selector(SEL_ENTRY_LINK, timeout=15_000)
    except PlaywrightTimeout:
        _dump_page(page, "entry-link-not-found")
        write_status("crashed")
        raise RuntimeError(
            f"Could not find 'CONSULTA DE CAUSAS' link on parent page. "
            f"Check selector SEL_ENTRY_LINK or parent URL."
        )

    with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
        page.click(SEL_ENTRY_LINK)


def search_rut(page, rut: str) -> None:
    """Fill the RUT field and submit the search."""
    try:
        page.wait_for_selector(SEL_RUT_INPUT, timeout=20_000)
    except PlaywrightTimeout:
        _dump_page(page, "rut-input-not-found")
        write_status("crashed")
        raise RuntimeError("RUT input field not found. Check selector SEL_RUT_INPUT.")

    page.fill(SEL_RUT_INPUT, rut)

    try:
        page.wait_for_selector(SEL_SEARCH_BTN, timeout=5_000)
        page.click(SEL_SEARCH_BTN)
    except PlaywrightTimeout:
        # Fall back to Enter key if no button found
        page.keyboard.press("Enter")


def wait_for_results(page) -> list:
    """Wait for results table rows. Raises if none appear (never accept silence as 0 results)."""
    try:
        page.wait_for_selector(SEL_RESULTS_ROW, timeout=25_000)
    except PlaywrightTimeout:
        _dump_page(page, "results-not-found")
        write_status("crashed")
        raise RuntimeError(
            "Results table never appeared — target may have crashed or RUT returned nothing. "
            "Cannot distinguish 0-results from crash without a positive signal."
        )

    rows = page.query_selector_all(SEL_RESULTS_ROW)
    # Filter out header rows (those with <th> children)
    data_rows = [r for r in rows if not r.query_selector("th")]
    if not data_rows:
        write_status("crashed")
        raise RuntimeError("Only header rows found — results table appeared but is empty.")

    return data_rows


def extract_row_data(row) -> dict:
    """Extract all cell text from a result row as a structured dict."""
    cells = row.query_selector_all("td")
    values = [c.inner_text().strip() for c in cells]
    # Map positionally — JPL tables typically: causa, caratula, fecha, estado, juzgado
    keys = ["causa", "caratula", "fecha_ingreso", "estado", "juzgado", "extra1", "extra2"]
    return {keys[i]: v for i, v in enumerate(values) if i < len(keys) and v}


def get_record_id(row_data: dict) -> str:
    """Use case number as stable record ID. Falls back to caratula if missing."""
    return row_data.get("causa") or row_data.get("caratula", "")[:40]


def download_pdfs_for_row(page, row, job_id: str, record_id: str,
                           supabase_url: str, supabase_key: str, supabase_bucket: str) -> list[str]:
    """Click into the case detail, download all PDFs, upload to Supabase. Returns list of URLs."""
    pdf_urls = []

    # Try clicking the case link to open detail view
    detail_link = row.query_selector("td:first-child a, td a")
    if not detail_link:
        return pdf_urls

    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=20_000):
            detail_link.click()
    except PlaywrightTimeout:
        return pdf_urls

    # Find PDF links on detail page
    pdf_links = page.query_selector_all(SEL_PDF_LINK)
    for i, link in enumerate(pdf_links):
        local_pdf = DOWNLOAD_DIR / f"{record_id}_doc{i}.pdf"
        try:
            with page.expect_download(timeout=30_000) as dl_info:
                link.click()
            dl_info.value.save_as(str(local_pdf))

            url = upload_pdf(
                supabase_url, supabase_key, supabase_bucket,
                job_id, f"{record_id}_doc{i}", local_pdf,
            )
            pdf_urls.append(url)
        except (PlaywrightTimeout, Exception) as e:
            print(f"[WARN] PDF download failed for {record_id} doc{i}: {e}", flush=True)

    # Go back to results list
    try:
        page.go_back(wait_until="domcontentloaded", timeout=15_000)
    except PlaywrightTimeout:
        pass

    return pdf_urls


def scrape(args, supabase_url: str, supabase_key: str, supabase_bucket: str) -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_seconds

    # Read checkpoint — raises on failure (resume-read-safety rule)
    checkpoint = read_checkpoint(supabase_url, supabase_key, args.job_id)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        page = context.new_page()

        # Always enter via parent site to establish a fresh session
        enter_via_parent(page, args.target_url)

        # Fill RUT and search
        search_rut(page, args.search_code)

        # Wait for results
        rows = wait_for_results(page)
        print(f"[INFO] Found {len(rows)} result rows", flush=True)

        pending: list[dict] = []

        for row in rows:
            if time.monotonic() >= deadline:
                print("[INFO] Time limit reached — stopping for re-dispatch", flush=True)
                break

            row_data = extract_row_data(row)
            record_id = get_record_id(row_data)

            if not record_id:
                print("[WARN] Could not determine record_id for a row — skipping", flush=True)
                continue

            if checkpoint.get(record_id) == "done":
                print(f"[INFO] Skipping already-done record: {record_id}", flush=True)
                continue

            try:
                pdf_urls = download_pdfs_for_row(
                    page, row, args.job_id, record_id,
                    supabase_url, supabase_key, supabase_bucket,
                )

                pending.append({
                    "job_id": args.job_id,
                    "record_id": record_id,
                    "status": "done",
                    "text": json.dumps(row_data, ensure_ascii=False),
                    "pdf_url": pdf_urls[0] if pdf_urls else "",
                })

                # Flush immediately — don't lose this record if we crash
                write_checkpoints(supabase_url, supabase_key, pending)
                pending.clear()
                print(f"[INFO] Done: {record_id}", flush=True)

            except PlaywrightTimeout:
                pending.append({
                    "job_id": args.job_id,
                    "record_id": record_id,
                    "status": "failed",
                    "text": json.dumps(row_data, ensure_ascii=False),
                    "pdf_url": "",
                })
                write_checkpoints(supabase_url, supabase_key, pending)
                write_status("crashed")
                raise

        context.close()
        browser.close()

    final = read_checkpoint(supabase_url, supabase_key, args.job_id)
    all_done = all(v == "done" for k, v in final.items() if k != "__job__")

    if all_done and final:
        mark_job_status(supabase_url, supabase_key, args.job_id, "complete")
        write_status("complete")
        print(f"[INFO] Job {args.job_id} complete", flush=True)
    else:
        write_status("incomplete")
        print(f"[INFO] Job {args.job_id} incomplete — will re-dispatch", flush=True)


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
