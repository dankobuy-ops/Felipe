"""Scraper for Chilean JPL (Juzgado de Policía Local) — vitacura.cl pattern.

Flow:
  1. Navigate to municipality parent page, click "CONSULTA DE CAUSAS" (session recovery)
  2. Fill RUT field, submit search
  3. Results list: FECHA PROCESO | JUZGADO | ROL | DESCRIPCIÓN | Ver
  4. For each ROL: click Ver → extract Sección A.1, A.2, B, C → download PDFs from Sección C
  5. Write checkpoint immediately after each case
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

STATUS_FILE  = Path("/tmp/scrape_status")
DOWNLOAD_DIR = Path("/tmp/pdfs")

# ── Selectors ─────────────────────────────────────────────────────────────────
SEL_ENTRY_LINK  = "a:has-text('CONSULTA DE CAUSAS'), a:has-text('Consulta de Causas'), a:has-text('consulta de causas')"
SEL_RUT_INPUT   = "input[type='text'][id*='Rut'], input[type='text'][id*='rut'], input[type='text'][name*='Rut'], input[type='text'][name*='rut'], input[type='text'][id*='txt']"
SEL_SEARCH_BTN  = "input[id*='Buscar'], input[id*='buscar'], input[id*='Search'], button:has-text('Buscar'), input[type='submit']"
SEL_RESULTS_TBL = "table tbody tr"
SEL_VER_LINK    = "a"  # last <a> in each results row (the Ver eye icon)
SEL_ABRIR_LINK  = "a:has-text('Abrir'), a:has-text('abrir'), a[href*='documento'], a[href*='Documento'], a[href*='.pdf']"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--job-id",       required=True)
    p.add_argument("--search-code",  required=True, help="RUT")
    p.add_argument("--target-url",   required=True, help="Municipality parent page URL")
    p.add_argument("--max-seconds",  type=int, default=240)
    return p.parse_args()


def write_status(s: str) -> None:
    STATUS_FILE.write_text(s)


def log(msg: str) -> None:
    print(msg, flush=True)


def dump_page(page, label: str) -> None:
    log(f"[DEBUG {label}] URL: {page.url}")
    log(f"[DEBUG {label}] HTML:\n{page.content()[:4000]}")


# ── Phase 1: Entry via parent ──────────────────────────────────────────────────
def enter_via_parent(page, context, parent_url: str):
    """Navigate via parent page to establish a fresh JPL session. Returns active page."""
    try:
        page.goto(parent_url, wait_until="domcontentloaded", timeout=45_000)
    except PlaywrightTimeout:
        write_status("crashed")
        raise RuntimeError(f"Parent page timed out: {parent_url}")

    try:
        page.wait_for_selector(SEL_ENTRY_LINK, timeout=15_000)
    except PlaywrightTimeout:
        dump_page(page, "entry-link-not-found")
        write_status("crashed")
        raise RuntimeError("'CONSULTA DE CAUSAS' link not found on parent page.")

    link = page.query_selector(SEL_ENTRY_LINK)
    opens_new_tab = (link.get_attribute("target") or "").strip() == "_blank"

    if opens_new_tab:
        with context.expect_page(timeout=30_000) as info:
            page.click(SEL_ENTRY_LINK)
        p = info.value
        p.wait_for_load_state("domcontentloaded", timeout=30_000)
        return p
    else:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.click(SEL_ENTRY_LINK)
        return page


# ── Phase 2: RUT search ────────────────────────────────────────────────────────
def search_rut(page, rut: str) -> None:
    try:
        page.wait_for_selector(SEL_RUT_INPUT, timeout=20_000)
    except PlaywrightTimeout:
        dump_page(page, "rut-input-not-found")
        write_status("crashed")
        raise RuntimeError("RUT input field not found.")

    page.fill(SEL_RUT_INPUT, rut)

    try:
        page.wait_for_selector(SEL_SEARCH_BTN, timeout=5_000)
        page.click(SEL_SEARCH_BTN)
    except PlaywrightTimeout:
        page.keyboard.press("Enter")


# ── Phase 3: Results list ──────────────────────────────────────────────────────
def get_results_list(page) -> list[dict]:
    """Wait for results table and return list of {rol, fecha, juzgado, descripcion, row_index}."""
    try:
        page.wait_for_selector(SEL_RESULTS_TBL, timeout=25_000)
    except PlaywrightTimeout:
        dump_page(page, "results-not-found")
        write_status("crashed")
        raise RuntimeError(
            "Results table never appeared — target crashed or RUT returned nothing. "
            "Cannot distinguish 0-results from crash."
        )

    rows = page.query_selector_all(SEL_RESULTS_TBL)
    records = []
    for i, row in enumerate(rows):
        if row.query_selector("th"):
            continue  # skip header
        cells = row.query_selector_all("td")
        if len(cells) < 3:
            continue
        records.append({
            "row_index": i,
            "fecha_proceso": cells[0].inner_text().strip() if len(cells) > 0 else "",
            "juzgado":       cells[1].inner_text().strip() if len(cells) > 1 else "",
            "rol":           cells[2].inner_text().strip() if len(cells) > 2 else "",
            "descripcion":   cells[3].inner_text().strip() if len(cells) > 3 else "",
        })

    if not records:
        write_status("crashed")
        raise RuntimeError("No data rows found in results table.")

    log(f"[INFO] Found {len(records)} cases")
    return records


# ── Phase 4: Detail page extraction ───────────────────────────────────────────
def extract_label_value_table(page, section_text: str) -> list[dict]:
    """Extract label→value pairs from a section identified by its header text."""
    parties = []
    # Find all tables or divs within the section
    # ASP.NET WebForms uses nested tables — scan all <tr> pairs near the section header
    try:
        # Get the section container by looking for td containing section_text
        section_cells = page.query_selector_all("td")
        in_section = False
        current_party: dict = {}

        for cell in section_cells:
            text = cell.inner_text().strip().upper()

            if section_text.upper() in text and len(text) < 80:
                in_section = True
                if current_party:
                    parties.append(current_party)
                    current_party = {}
                continue

            # Stop at next section header
            if in_section and any(s in text for s in ["SECCION A.2", "SECCION B", "SECCION C", "SECCIÓN"]):
                if current_party:
                    parties.append(current_party)
                break

            if not in_section:
                continue

            if "NOMBRE O RAZON SOCIAL" in text or "NOMBRE O RAZÓN SOCIAL" in text:
                if current_party:
                    parties.append(current_party)
                current_party = {}
                # Get next sibling cell value
                val = _next_sibling_text(page, cell)
                current_party["nombre"] = val
                rut_val = _find_label_value(page, cell, "RUT")
                if rut_val:
                    current_party["rut"] = rut_val
            elif "DIRECCION" in text or "DIRECCIÓN" in text:
                current_party["direccion"] = _next_sibling_text(page, cell)
            elif "COMUNA" in text:
                current_party["comuna"] = _next_sibling_text(page, cell)

        if current_party:
            parties.append(current_party)
    except Exception as e:
        log(f"[WARN] Section extraction error ({section_text}): {e}")

    return parties


def _next_sibling_text(page, cell) -> str:
    """Try to get the text of the next <td> sibling."""
    try:
        return cell.evaluate("el => { const next = el.nextElementSibling; return next ? next.innerText.trim() : ''; }")
    except Exception:
        return ""


def _find_label_value(page, anchor_cell, label: str) -> str:
    """Find a label in the same row and return its value."""
    try:
        return anchor_cell.evaluate(f"""el => {{
            const row = el.closest('tr');
            if (!row) return '';
            const cells = row.querySelectorAll('td');
            for (let i = 0; i < cells.length - 1; i++) {{
                if (cells[i].innerText.includes('{label}')) return cells[i+1].innerText.trim();
            }}
            return '';
        }}""")
    except Exception:
        return ""


def extract_section_b(page) -> dict:
    """Extract Sección B: Datos de la Causa."""
    fields = {}
    labels = [
        "ROL INICIO", "DESCRIPCION", "DESCRIPCIÓN", "FECHA CAUSA",
        "ACTUARIO", "PLACA PATENTE", "REMISOR", "FECHA CITACION",
        "FECHA CITACIÓN", "ESTADO", "FECHA ESTADO"
    ]
    try:
        all_cells = page.query_selector_all("td")
        cells_text = [(c, c.inner_text().strip()) for c in all_cells]

        for i, (cell, text) in enumerate(cells_text):
            for label in labels:
                if text.upper() == label.upper() and i + 1 < len(cells_text):
                    val = cells_text[i + 1][1]
                    if val and not any(l.upper() == val.upper() for l in labels):
                        fields[label.lower().replace(" ", "_")] = val
    except Exception as e:
        log(f"[WARN] Section B extraction error: {e}")
    return fields


def extract_section_c(page) -> tuple[list[dict], list[str]]:
    """Extract Sección C: Trámites. Returns (tramites_list, abrir_hrefs)."""
    tramites = []
    hrefs = []
    try:
        abrir_links = page.query_selector_all(SEL_ABRIR_LINK)
        for link in abrir_links:
            row = link.evaluate_handle("el => el.closest('tr')")
            fecha = ""
            desc = ""
            try:
                cells = row.as_element().query_selector_all("td")
                if len(cells) >= 2:
                    fecha = cells[0].inner_text().strip()
                    desc  = cells[1].inner_text().strip()
            except Exception:
                pass
            href = link.get_attribute("href") or ""
            tramites.append({"fecha": fecha, "descripcion": desc, "href": href})
            hrefs.append(href)
    except Exception as e:
        log(f"[WARN] Section C extraction error: {e}")
    return tramites, hrefs


def download_and_upload_pdfs(page, context, job_id: str, rol: str,
                              tramites: list[dict],
                              supabase_url: str, supabase_key: str, bucket: str) -> list[str]:
    """Click each Abrir link, download PDF, upload to Supabase. Returns list of signed URLs."""
    pdf_urls = []
    abrir_links = page.query_selector_all(SEL_ABRIR_LINK)

    for i, link in enumerate(abrir_links):
        local_pdf = DOWNLOAD_DIR / f"{rol}_doc{i}.pdf"
        try:
            with context.expect_page(timeout=20_000) as new_page_info:
                link.click()
            doc_page = new_page_info.value
            doc_page.wait_for_load_state("load", timeout=20_000)

            # Some docs open as PDF in new tab — trigger download
            with doc_page.expect_download(timeout=20_000) as dl_info:
                doc_page.evaluate("window.print()")  # won't work for actual download
            dl_info.value.save_as(str(local_pdf))
            doc_page.close()
        except Exception:
            # Try direct download via fetch if page approach fails
            try:
                href = link.get_attribute("href") or ""
                if href and not href.startswith("javascript"):
                    with page.expect_download(timeout=20_000) as dl_info:
                        link.click()
                    dl_info.value.save_as(str(local_pdf))
                else:
                    # postback — click and wait for download
                    with page.expect_download(timeout=20_000) as dl_info:
                        link.click()
                    dl_info.value.save_as(str(local_pdf))
            except Exception as e2:
                log(f"[WARN] PDF download failed for {rol} doc{i}: {e2}")
                continue

        try:
            url = upload_pdf(supabase_url, supabase_key, bucket,
                             job_id, f"{rol}_doc{i}", local_pdf)
            pdf_urls.append(url)
            log(f"[INFO] Uploaded PDF {i} for ROL {rol}")
        except Exception as e:
            log(f"[WARN] PDF upload failed for {rol} doc{i}: {e}")

    return pdf_urls


# ── Main scrape loop ───────────────────────────────────────────────────────────
def scrape(args, supabase_url: str, supabase_key: str, supabase_bucket: str) -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_seconds

    checkpoint = read_checkpoint(supabase_url, supabase_key, args.job_id)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        page = context.new_page()

        # Enter via parent site every time (session recovery)
        active = enter_via_parent(page, context, args.target_url)

        # Search RUT
        search_rut(active, args.search_code)

        # Get full results list before navigating away
        records = get_results_list(active)

        for rec in records:
            if time.monotonic() >= deadline:
                log("[INFO] Time limit — stopping for re-dispatch")
                break

            rol = rec["rol"]
            if not rol:
                continue
            if checkpoint.get(rol) == "done":
                log(f"[INFO] Skip (already done): ROL {rol}")
                continue

            log(f"[INFO] Processing ROL {rol}")

            try:
                # Re-query rows (page may have refreshed after go_back)
                rows = active.query_selector_all(SEL_RESULTS_TBL)
                data_rows = [r for r in rows if not r.query_selector("th")]

                # Find the row matching this ROL
                target_row = None
                for row in data_rows:
                    cells = row.query_selector_all("td")
                    if len(cells) > 2 and cells[2].inner_text().strip() == rol:
                        target_row = row
                        break

                if not target_row:
                    log(f"[WARN] Could not re-find ROL {rol} in table — skipping")
                    continue

                # Click the Ver link (last <a> in the row)
                links_in_row = target_row.query_selector_all("a")
                if not links_in_row:
                    log(f"[WARN] No Ver link found for ROL {rol}")
                    continue

                ver_link = links_in_row[-1]
                with active.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                    ver_link.click()

                # ── Extract detail page ──────────────────────────────────────
                demandados  = extract_label_value_table(active, "SECCION A.1")
                demandantes = extract_label_value_table(active, "SECCION A.2")
                causa_data  = extract_section_b(active)
                tramites, _ = extract_section_c(active)

                case_data = {
                    **rec,
                    "demandados":  demandados,
                    "demandantes": demandantes,
                    "causa":       causa_data,
                    "tramites":    tramites,
                }

                # ── Download PDFs from Sección C ─────────────────────────────
                pdf_urls = download_and_upload_pdfs(
                    active, context, args.job_id, rol, tramites,
                    supabase_url, supabase_key, supabase_bucket,
                )

                # ── Write checkpoint ─────────────────────────────────────────
                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id":    args.job_id,
                    "record_id": rol,
                    "status":    "done",
                    "text":      json.dumps(case_data, ensure_ascii=False),
                    "pdf_url":   pdf_urls[0] if pdf_urls else "",
                }])
                log(f"[INFO] Done: ROL {rol} — {len(pdf_urls)} PDFs")

                # ── Go back to results list ───────────────────────────────────
                active.go_back(wait_until="domcontentloaded", timeout=20_000)
                active.wait_for_selector(SEL_RESULTS_TBL, timeout=15_000)

            except PlaywrightTimeout as e:
                log(f"[WARN] Timeout on ROL {rol}: {e}")
                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id": args.job_id, "record_id": rol,
                    "status": "failed", "text": json.dumps(rec), "pdf_url": "",
                }])
                write_status("crashed")
                raise
            except Exception as e:
                log(f"[WARN] Error on ROL {rol}: {e}")
                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id": args.job_id, "record_id": rol,
                    "status": "failed", "text": json.dumps(rec), "pdf_url": "",
                }])

        context.close()
        browser.close()

    final    = read_checkpoint(supabase_url, supabase_key, args.job_id)
    all_done = all(v == "done" for k, v in final.items() if k != "__job__")

    if all_done and final:
        mark_job_status(supabase_url, supabase_key, args.job_id, "complete")
        write_status("complete")
        log(f"[INFO] Job {args.job_id} complete")
    else:
        write_status("incomplete")
        log(f"[INFO] Job {args.job_id} incomplete — will re-dispatch")


def main():
    args          = parse_args()
    supabase_url  = os.environ["SUPABASE_URL"]
    supabase_key  = os.environ["SUPABASE_SERVICE_KEY"]
    supabase_bucket = os.environ.get("SUPABASE_BUCKET", "pdfs")
    try:
        scrape(args, supabase_url, supabase_key, supabase_bucket)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
