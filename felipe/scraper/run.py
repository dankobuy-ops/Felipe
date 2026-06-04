"""Scraper for Chilean JPL (Juzgado de Policía Local) — vitacura.cl pattern.

Flow:
  1. Navigate to municipality parent page → click CONSULTA DE CAUSAS (session recovery)
  2. Fill RUT → submit → results list
  3. For each ROL: click Ver → extract all sections via JS → download PDFs → checkpoint
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

SEL_ENTRY_LINK = "a:has-text('CONSULTA DE CAUSAS'), a:has-text('Consulta de Causas')"
SEL_RUT_INPUT  = "input[type='text'][id*='Rut'], input[type='text'][id*='rut'], input[type='text'][id*='txt']"
SEL_SEARCH_BTN = "input[id*='Buscar'], input[id*='buscar'], input[type='submit']"
SEL_RESULTS    = "table tbody tr"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--job-id",      required=True)
    p.add_argument("--search-code", required=True)
    p.add_argument("--target-url",  required=True)
    p.add_argument("--max-seconds", type=int, default=240)
    return p.parse_args()


def write_status(s):
    STATUS_FILE.write_text(s)


def log(msg):
    print(msg, flush=True)


def dump_page(page, label):
    log(f"[DEBUG {label}] URL: {page.url}")
    log(f"[DEBUG {label}] HTML:\n{page.content()[:4000]}")


# ── Entry ─────────────────────────────────────────────────────────────────────

def enter_via_parent(page, context, parent_url):
    try:
        page.goto(parent_url, wait_until="domcontentloaded", timeout=45_000)
    except PlaywrightTimeout:
        write_status("crashed")
        raise RuntimeError(f"Parent page timed out: {parent_url}")

    try:
        page.wait_for_selector(SEL_ENTRY_LINK, timeout=15_000)
    except PlaywrightTimeout:
        dump_page(page, "no-entry-link")
        write_status("crashed")
        raise RuntimeError("CONSULTA DE CAUSAS link not found.")

    target_attr = page.get_attribute(SEL_ENTRY_LINK, "target") or ""
    if target_attr.strip() == "_blank":
        with context.expect_page(timeout=30_000) as info:
            page.click(SEL_ENTRY_LINK)
        p = info.value
        p.wait_for_load_state("domcontentloaded", timeout=30_000)
        return p
    else:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.click(SEL_ENTRY_LINK)
        return page


# ── Search ────────────────────────────────────────────────────────────────────

def search_rut(page, rut):
    try:
        page.wait_for_selector(SEL_RUT_INPUT, timeout=20_000)
    except PlaywrightTimeout:
        dump_page(page, "no-rut-input")
        write_status("crashed")
        raise RuntimeError("RUT input not found.")

    page.fill(SEL_RUT_INPUT, rut)
    log(f"[INFO] Filled RUT: {rut}")

    try:
        page.wait_for_selector(SEL_SEARCH_BTN, timeout=5_000)
        page.click(SEL_SEARCH_BTN)
    except PlaywrightTimeout:
        page.keyboard.press("Enter")
    log("[INFO] Search submitted")


# ── Results list ──────────────────────────────────────────────────────────────

def get_results_list(page):
    try:
        page.wait_for_selector(SEL_RESULTS, timeout=25_000)
    except PlaywrightTimeout:
        dump_page(page, "no-results")
        write_status("crashed")
        raise RuntimeError("Results table never appeared.")

    # Extract all row data using JS — avoids element handle issues
    records = page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        return rows
            .filter(r => !r.querySelector('th'))
            .map(r => {
                const cells = Array.from(r.querySelectorAll('td'));
                return {
                    fecha_proceso: cells[0] ? cells[0].innerText.trim() : '',
                    juzgado:       cells[1] ? cells[1].innerText.trim() : '',
                    rol:           cells[2] ? cells[2].innerText.trim() : '',
                    descripcion:   cells[3] ? cells[3].innerText.trim() : '',
                };
            })
            .filter(r => r.rol !== '');
    }""")

    if not records:
        write_status("crashed")
        raise RuntimeError("No data rows found.")

    log(f"[INFO] Found {len(records)} cases")
    return records


# ── Detail page extraction (all via JS) ───────────────────────────────────────

def extract_detail_page(page):
    """Extract all sections from detail page using a single JS evaluation."""
    return page.evaluate("""() => {
        function rowsOfTable(table) {
            if (!table) return [];
            return Array.from(table.querySelectorAll('tr'))
                .map(r => Array.from(r.querySelectorAll('td')).map(c => c.innerText.trim()));
        }

        function extractParties(sectionLabel) {
            const parties = [];
            const tds = Array.from(document.querySelectorAll('td'));
            let inSection = false;
            let party = null;

            for (let i = 0; i < tds.length; i++) {
                const txt = tds[i].innerText.trim().toUpperCase();

                if (txt.includes(sectionLabel.toUpperCase()) && txt.length < 100) {
                    inSection = true;
                    continue;
                }
                if (inSection && (txt.includes('SECCION') || txt.includes('SECCIÓN'))) {
                    if (party) parties.push(party);
                    break;
                }
                if (!inSection) continue;

                if (txt.includes('NOMBRE') || txt.includes('RAZÓN') || txt.includes('RAZON')) {
                    if (party) parties.push(party);
                    party = {};
                    const next = tds[i+1] ? tds[i+1].innerText.trim() : '';
                    party.nombre = next;
                    // Look for RUT in same row
                    const row = tds[i].closest('tr');
                    if (row) {
                        const rowCells = Array.from(row.querySelectorAll('td'));
                        for (let j = 0; j < rowCells.length - 1; j++) {
                            if (rowCells[j].innerText.trim().toUpperCase() === 'RUT:' ||
                                rowCells[j].innerText.trim().toUpperCase() === 'RUT') {
                                party.rut = rowCells[j+1].innerText.trim();
                            }
                        }
                    }
                } else if (party && (txt === 'DIRECCION:' || txt === 'DIRECCIÓN:' || txt === 'DIRECCION' || txt === 'DIRECCIÓN')) {
                    party.direccion = tds[i+1] ? tds[i+1].innerText.trim() : '';
                } else if (party && txt === 'COMUNA:' || txt === 'COMUNA') {
                    party.comuna = tds[i+1] ? tds[i+1].innerText.trim() : '';
                }
            }
            if (party) parties.push(party);
            return parties;
        }

        function extractSectionB() {
            const fields = {};
            const labels = ['ROL INICIO','DESCRIPCION','DESCRIPCIÓN','FECHA CAUSA',
                            'ACTUARIO','PLACA PATENTE','REMISOR','FECHA CITACION',
                            'FECHA CITACIÓN','ESTADO','FECHA ESTADO'];
            const tds = Array.from(document.querySelectorAll('td'));
            for (let i = 0; i < tds.length - 1; i++) {
                const txt = tds[i].innerText.trim().replace(':','').toUpperCase();
                if (labels.some(l => l === txt)) {
                    const val = tds[i+1].innerText.trim();
                    if (val && !labels.some(l => l === val.toUpperCase().replace(':',''))) {
                        fields[txt.toLowerCase().replace(/ /g,'_')] = val;
                    }
                }
            }
            return fields;
        }

        function extractSectionC() {
            const tramites = [];
            const links = Array.from(document.querySelectorAll('a')).filter(a =>
                a.innerText.trim().toLowerCase() === 'abrir' ||
                (a.href && (a.href.includes('.pdf') || a.href.includes('documento') || a.href.includes('Documento')))
            );
            links.forEach(link => {
                const row = link.closest('tr');
                const cells = row ? Array.from(row.querySelectorAll('td')) : [];
                tramites.push({
                    fecha:       cells[0] ? cells[0].innerText.trim() : '',
                    descripcion: cells[1] ? cells[1].innerText.trim() : '',
                    href:        link.href || '',
                    text:        link.innerText.trim(),
                });
            });
            return tramites;
        }

        return {
            demandados:  extractParties('SECCION A.1'),
            demandantes: extractParties('SECCION A.2'),
            causa:       extractSectionB(),
            tramites:    extractSectionC(),
        };
    }""")


# ── Click Ver and navigate ────────────────────────────────────────────────────

def click_ver_for_rol(page, rol):
    """Find the row with this ROL and click its Ver link. Uses JS to find the link href."""
    # Get the Ver link href for this ROL using JS
    ver_href = page.evaluate(f"""() => {{
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        for (const row of rows) {{
            const cells = row.querySelectorAll('td');
            if (cells[2] && cells[2].innerText.trim() === '{rol}') {{
                const links = row.querySelectorAll('a');
                const last = links[links.length - 1];
                return last ? last.href : null;
            }}
        }}
        return null;
    }}""")

    if ver_href and not ver_href.startswith("javascript"):
        # Direct link — navigate to it
        page.goto(ver_href, wait_until="domcontentloaded", timeout=30_000)
    else:
        # Postback — click via JS to avoid element handle issues
        clicked = page.evaluate(f"""() => {{
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            for (const row of rows) {{
                const cells = row.querySelectorAll('td');
                if (cells[2] && cells[2].innerText.trim() === '{rol}') {{
                    const links = row.querySelectorAll('a');
                    if (links.length > 0) {{ links[links.length-1].click(); return true; }}
                }}
            }}
            return false;
        }}""")
        if clicked:
            page.wait_for_load_state("domcontentloaded", timeout=30_000)
        else:
            raise RuntimeError(f"Could not find Ver link for ROL {rol}")


# ── PDF download ──────────────────────────────────────────────────────────────

def download_pdfs(page, context, tramites, job_id, rol, supabase_url, supabase_key, bucket):
    """Download PDFs from Sección C Abrir links. Returns list of uploaded URLs."""
    pdf_urls = []
    abrir_links = [t for t in tramites if t.get("href") or t.get("text", "").lower() == "abrir"]

    for i, tramite in enumerate(abrir_links):
        local_pdf = DOWNLOAD_DIR / f"{rol}_doc{i}.pdf"
        href = tramite.get("href", "")
        try:
            if href and not href.startswith("javascript"):
                with page.expect_download(timeout=25_000) as dl:
                    page.goto(href, wait_until="domcontentloaded", timeout=25_000)
                dl.value.save_as(str(local_pdf))
            else:
                # Click via JS to avoid stale element
                with page.expect_download(timeout=25_000) as dl:
                    page.evaluate(f"""() => {{
                        const links = Array.from(document.querySelectorAll('a'));
                        const abrir = links.filter(a => a.innerText.trim().toLowerCase() === 'abrir');
                        if (abrir[{i}]) abrir[{i}].click();
                    }}""")
                dl.value.save_as(str(local_pdf))

            url = upload_pdf(supabase_url, supabase_key, bucket, job_id, f"{rol}_doc{i}", local_pdf)
            pdf_urls.append(url)
            log(f"[INFO] PDF {i} uploaded for ROL {rol}")
        except Exception as e:
            log(f"[WARN] PDF {i} failed for ROL {rol}: {e}")

    return pdf_urls


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape(args, supabase_url, supabase_key, supabase_bucket):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_seconds

    checkpoint = read_checkpoint(supabase_url, supabase_key, args.job_id)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx     = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        page    = ctx.new_page()

        active = enter_via_parent(page, ctx, args.target_url)
        search_rut(active, args.search_code)
        records = get_results_list(active)
        results_url = active.url  # save to return here after each detail page

        for rec in records:
            if time.monotonic() >= deadline:
                log("[INFO] Time limit — stopping for re-dispatch")
                break

            rol = rec["rol"]
            if not rol:
                continue
            if checkpoint.get(rol) == "done":
                log(f"[INFO] Skip (done): {rol}")
                continue

            log(f"[INFO] Processing ROL {rol}")
            try:
                # Navigate to detail page
                click_ver_for_rol(active, rol)

                # Extract everything via JS (no element handle issues)
                detail = extract_detail_page(active)
                case_data = {**rec, **detail}

                # Download PDFs from Sección C
                pdf_urls = download_pdfs(
                    active, ctx, detail.get("tramites", []),
                    args.job_id, rol, supabase_url, supabase_key, supabase_bucket,
                )

                # Checkpoint
                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id":    args.job_id,
                    "record_id": rol,
                    "status":    "done",
                    "text":      json.dumps(case_data, ensure_ascii=False),
                    "pdf_url":   pdf_urls[0] if pdf_urls else "",
                }])
                log(f"[INFO] Done ROL {rol} — {len(pdf_urls)} PDFs")

                # Return to results page
                active.goto(results_url, wait_until="domcontentloaded", timeout=30_000)
                active.wait_for_selector(SEL_RESULTS, timeout=15_000)

            except PlaywrightTimeout as e:
                log(f"[WARN] Timeout ROL {rol}: {e}")
                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id": args.job_id, "record_id": rol,
                    "status": "failed", "text": json.dumps(rec), "pdf_url": "",
                }])
                write_status("crashed")
                raise
            except Exception as e:
                log(f"[WARN] Error ROL {rol}: {e}")
                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id": args.job_id, "record_id": rol,
                    "status": "failed", "text": json.dumps(rec), "pdf_url": "",
                }])

        ctx.close()
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
    args = parse_args()
    try:
        scrape(args, os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"],
               os.environ.get("SUPABASE_BUCKET", "pdfs"))
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
