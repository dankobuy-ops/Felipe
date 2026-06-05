"""Scraper for Chilean JPL (Juzgado de Policía Local) — vitacura.cl pattern.

Navigation:
  Level 1 — Parent page → click CONSULTA DE CAUSAS → RUT search form
  Level 2 — Results list: FECHA PROCESO | JUZGADO | ROL | DESCRIPCIÓN | [Abrir]
  Level 3 — Case detail: Sección A.1 (demandados), A.2 (demandantes),
                          B (datos causa), C (trámites + PDF Abrir links)
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
    log(f"[DEBUG {label}] HTML:\n{page.content()[:5000]}")


# ── Level 1 → Level 2: entry via parent ───────────────────────────────────────

def enter_via_parent(page, context, parent_url):
    """Navigate via parent page to establish a fresh JPL session. Returns active page."""
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
        raise RuntimeError("CONSULTA DE CAUSAS link not found on parent page.")

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


def search_rut(page, rut):
    """Fill RUT and submit — arrives at Level 2 (results list)."""
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

    # Wait for AJAX/UpdatePanel to complete after search
    page.wait_for_load_state("networkidle", timeout=20_000)
    log("[INFO] Search submitted and network idle")

    # ── DEBUG: dump all tables with id/class so we can pick the right selector ──
    table_info = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('table')).map((t, i) => {
            const rows = t.querySelectorAll('tbody tr');
            const headers = Array.from(t.querySelectorAll('th')).map(h => h.innerText.trim());
            const firstRow = rows[0] ? Array.from(rows[0].querySelectorAll('td')).map(c => c.innerText.trim().substring(0,40)) : [];
            return {
                index: i,
                id: t.id || '',
                className: t.className || '',
                rowCount: rows.length,
                headers: headers,
                firstRow: firstRow,
            };
        });
    }""")
    log("[DEBUG TABLES]")
    for t in table_info:
        log(f"  table[{t['index']}] id={t['id']!r} class={t['className']!r} rows={t['rowCount']} headers={t['headers']} firstRow={t['firstRow']}")

    # ── DEBUG: dump all inputs so we can verify RUT selector ──
    input_info = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('input')).map(i => ({
            id: i.id, name: i.name, type: i.type, value: i.value.substring(0,30)
        }));
    }""")
    log("[DEBUG INPUTS]")
    for inp in input_info:
        log(f"  input id={inp['id']!r} name={inp['name']!r} type={inp['type']!r} value={inp['value']!r}")


# ── Level 2: results list ──────────────────────────────────────────────────────

def get_results_list(page):
    """Parse Level 2 table. Returns list of {rol, fecha, juzgado, descripcion, row_index}."""
    try:
        page.wait_for_selector(SEL_RESULTS, timeout=25_000)
    except PlaywrightTimeout:
        dump_page(page, "no-results")
        write_status("crashed")
        raise RuntimeError("Results table never appeared — target crashed or RUT returned nothing.")

    records = page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll('table tbody tr'));
        const data = [];
        rows.forEach((row, index) => {
            if (row.querySelector('th')) return;
            const cells = Array.from(row.querySelectorAll('td'));
            if (cells.length < 3) return;
            // Find the Abrir link (last <a> in the row, or img link)
            const links = row.querySelectorAll('a');
            const abrirHref = links.length > 0 ? links[links.length - 1].href : null;
            data.push({
                row_index:    index,
                fecha_proceso: cells[0] ? cells[0].innerText.trim() : '',
                juzgado:       cells[1] ? cells[1].innerText.trim() : '',
                rol:           cells[2] ? cells[2].innerText.trim() : '',
                descripcion:   cells[3] ? cells[3].innerText.trim() : '',
                abrir_href:    abrirHref,
            });
        });
        return data.filter(r => r.rol !== '');
    }""")

    if not records:
        dump_page(page, "level2-no-records")
        write_status("crashed")
        raise RuntimeError("No data rows found in results table.")

    # ── DEBUG: dump column mapping + Abrir link HTML so selectors can be fixed ──
    debug_info = page.evaluate("""() => {
        const rows = Array.from(document.querySelectorAll('table tbody tr')).slice(0, 5);
        const rowData = rows.map((r, ri) => {
            const cells = Array.from(r.querySelectorAll('td'));
            const links = Array.from(r.querySelectorAll('a'));
            return {
                rowIndex: ri,
                cells: cells.map((c, i) => i + ':' + c.innerText.trim().substring(0, 40)),
                links: links.map(a => ({
                    text: a.innerText.trim(),
                    href: a.href,
                    onclick: a.getAttribute('onclick') || '',
                    id: a.id || '',
                })),
            };
        });
        return rowData;
    }""")
    log("[DEBUG Level2 rows]")
    for row in debug_info:
        log(f"  row[{row['rowIndex']}] cells={row['cells']}")
        for lnk in row['links']:
            log(f"    link text={lnk['text']!r} href={lnk['href']!r} onclick={lnk['onclick']!r} id={lnk['id']!r}")

    log(f"[INFO] Level 2: found {len(records)} causas")
    return records


# ── Level 2 → Level 3: click Abrir ────────────────────────────────────────────

def open_causa(page, rec, results_url):
    """Click Abrir for a causa row to navigate to Level 3. Returns active page."""
    href = rec.get("abrir_href", "")
    rol  = rec["rol"]

    if href and not href.startswith("javascript") and href != results_url:
        log(f"[INFO] Navigating to Level 3 via href for ROL {rol}")
        page.goto(href, wait_until="domcontentloaded", timeout=30_000)
    else:
        # Postback or javascript — click by row index via JS
        log(f"[INFO] Clicking Abrir (postback) for ROL {rol} at row {rec['row_index']}")
        clicked = page.evaluate(f"""() => {{
            const rows = Array.from(document.querySelectorAll('table tbody tr'))
                .filter(r => !r.querySelector('th'));
            const row = rows[{rec['row_index']}];
            if (!row) return false;
            const links = row.querySelectorAll('a');
            if (links.length === 0) return false;
            links[links.length - 1].click();
            return true;
        }}""")
        if not clicked:
            raise RuntimeError(f"Could not find Abrir link for ROL {rol}")
        page.wait_for_load_state("domcontentloaded", timeout=30_000)

    log(f"[INFO] Arrived at Level 3 for ROL {rol}: {page.url}")
    return page


# ── Level 3: extract all data via JS ──────────────────────────────────────────

def extract_level3(page):
    """Extract Secciones A.1, A.2, B, C from the detail page. Pure JS — no element handles."""
    return page.evaluate("""() => {
        // ── helpers ──────────────────────────────────────────────────────────
        function allCells() { return Array.from(document.querySelectorAll('td')); }

        function cellsInSection(startLabel, stopLabels) {
            const cells = allCells();
            const result = [];
            let inside = false;
            for (const cell of cells) {
                const t = cell.innerText.trim().toUpperCase();
                if (!inside) {
                    if (t.includes(startLabel.toUpperCase()) && t.length < 120) inside = true;
                    continue;
                }
                if (stopLabels.some(s => t.includes(s.toUpperCase()) && t.length < 120)) break;
                result.push(cell);
            }
            return result;
        }

        function extractParties(sectionLabel) {
            const stopAt = ['SECCION A.2', 'SECCIÓN A.2', 'SECCION B', 'SECCIÓN B'];
            const cells  = cellsInSection(sectionLabel, stopAt);
            const parties = [];
            let party = null;
            for (let i = 0; i < cells.length; i++) {
                const t = cells[i].innerText.trim().toUpperCase();
                if (t.includes('NOMBRE') && (t.includes('RAZON') || t.includes('RAZÓN'))) {
                    if (party) parties.push(party);
                    party = {};
                    const row  = cells[i].closest('tr');
                    const tds  = row ? Array.from(row.querySelectorAll('td')) : [];
                    // walk the row: label → value pairs
                    for (let j = 0; j < tds.length - 1; j++) {
                        const lbl = tds[j].innerText.trim().toUpperCase().replace(':','');
                        const val = tds[j+1].innerText.trim();
                        if (lbl.includes('NOMBRE') || lbl.includes('RAZON') || lbl.includes('RAZÓN'))
                            party.nombre = val;
                        else if (lbl === 'RUT') party.rut = val;
                    }
                } else if (party) {
                    const row = cells[i].closest('tr');
                    const tds = row ? Array.from(row.querySelectorAll('td')) : [];
                    for (let j = 0; j < tds.length - 1; j++) {
                        const lbl = tds[j].innerText.trim().toUpperCase().replace(':','');
                        const val = tds[j+1].innerText.trim();
                        if (lbl === 'DIRECCION' || lbl === 'DIRECCIÓN') party.direccion = val;
                        else if (lbl === 'COMUNA') party.comuna = val;
                    }
                }
            }
            if (party) parties.push(party);
            return parties.filter(p => p.nombre);
        }

        function extractSectionB() {
            const LABELS = ['ROL INICIO','DESCRIPCION','DESCRIPCIÓN','FECHA CAUSA',
                            'ACTUARIO','PLACA PATENTE','REMISOR','FECHA CITACION',
                            'FECHA CITACIÓN','ESTADO','FECHA ESTADO'];
            const cells = allCells();
            const out   = {};
            for (let i = 0; i < cells.length - 1; i++) {
                const t = cells[i].innerText.trim().replace(':','').toUpperCase();
                if (LABELS.includes(t)) {
                    const val = cells[i+1].innerText.trim();
                    if (val && !LABELS.includes(val.toUpperCase().replace(':','')))
                        out[t.toLowerCase().replace(/ /g,'_')] = val;
                }
                // PARTE Y/O BOLETA DE CITACIÓN row has N° and FECHA as sub-fields
                if (t.includes('PARTE') && t.includes('BOLETA')) {
                    const row = cells[i].closest('tr');
                    const tds = row ? Array.from(row.querySelectorAll('td')) : [];
                    for (let j = 0; j < tds.length - 1; j++) {
                        const lbl = tds[j].innerText.trim().replace(':','').toUpperCase();
                        const val = tds[j+1].innerText.trim();
                        if (lbl === 'N°' || lbl === 'N') out['boleta_numero'] = val;
                        else if (lbl === 'FECHA') out['boleta_fecha'] = val;
                    }
                }
            }
            return out;
        }

        function extractSectionsCD() {
            // Walk ALL rows, detect section C / D headers, capture every data row
            const allRows = Array.from(document.querySelectorAll('tr'));
            const tramites = [];
            const adjuntos = [];
            let section = null;

            for (const row of allRows) {
                const rowText = row.innerText.trim().toUpperCase();
                const cells   = Array.from(row.querySelectorAll('td'));

                // Section header detection (short rows only to avoid false matches)
                if (rowText.length < 80) {
                    if (rowText.includes('SECCION C') || rowText.includes('SECCIÓN C'))  { section = 'C'; continue; }
                    if (rowText.includes('SECCION D') || rowText.includes('SECCIÓN D'))  { section = 'D'; continue; }
                }
                if (!section) continue;

                // Skip column-header rows (th) and empty rows
                if (row.querySelector('th') || cells.length === 0) continue;
                // Skip the sub-header row "Fecha | Descripción"
                const firstCell = cells[0].innerText.trim().toUpperCase();
                if (firstCell === 'FECHA' || firstCell === 'DESCRIPCIÓN' || firstCell === 'DESCRIPCION') continue;

                const link      = row.querySelector('a');
                const href      = link ? link.href : '';
                const linkText  = link ? link.innerText.trim() : '';

                if (section === 'C') {
                    const fecha      = cells[0] ? cells[0].innerText.trim() : '';
                    const descripcion = cells[1] ? cells[1].innerText.trim() : '';
                    if (!fecha && !descripcion) continue;
                    tramites.push({ fecha, descripcion, href, link_text: linkText });
                } else {
                    const descripcion = cells[0] ? cells[0].innerText.trim() : '';
                    if (!descripcion) continue;
                    adjuntos.push({ descripcion, href, link_text: linkText });
                }
            }
            return { tramites, adjuntos };
        }

        const secCD = extractSectionsCD();
        return {
            demandados:  extractParties('SECCION A.1'),
            demandantes: extractParties('SECCION A.2'),
            causa:       extractSectionB(),
            tramites:    secCD.tramites,
            adjuntos:    secCD.adjuntos,
        };
    }""")


# ── PDF download from Level 3 ─────────────────────────────────────────────────

def download_pdfs(page, context, tramites, job_id, rol, supabase_url, supabase_key, bucket):
    """Download PDFs from Sección C Abrir links using page.request (same session/cookies)."""
    pdf_urls = []
    for i, tramite in enumerate(tramites):
        local_pdf = DOWNLOAD_DIR / f"{rol}_doc{i}.pdf"
        href = tramite.get("href", "")
        try:
            if href and not href.startswith("javascript"):
                # Use Playwright's request API — same cookies/session, no page navigation
                response = page.request.get(href, timeout=30_000)
                if response.ok:
                    local_pdf.write_bytes(response.body())
                else:
                    log(f"[WARN] PDF {i+1} HTTP {response.status} for ROL {rol}")
                    continue
            else:
                # Postback link — click it and capture the download
                with page.expect_download(timeout=25_000) as dl:
                    page.evaluate(f"""() => {{
                        const links = Array.from(document.querySelectorAll('a'))
                            .filter(a => a.innerText.trim().toLowerCase() === 'abrir');
                        if (links[{i}]) links[{i}].click();
                    }}""")
                dl.value.save_as(str(local_pdf))

            url = upload_pdf(supabase_url, supabase_key, bucket, job_id, f"{rol}_doc{i}", local_pdf)
            pdf_urls.append(url)
            log(f"[INFO] PDF {i+1} uploaded for ROL {rol}")
        except Exception as e:
            log(f"[WARN] PDF {i+1} failed for ROL {rol}: {e}")

    return pdf_urls


# ── Main loop ─────────────────────────────────────────────────────────────────

def scrape(args, supabase_url, supabase_key, supabase_bucket):
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.max_seconds

    checkpoint = read_checkpoint(supabase_url, supabase_key, args.job_id)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx     = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        page    = ctx.new_page()

        # Level 1 → Level 2
        active = enter_via_parent(page, ctx, args.target_url)
        search_rut(active, args.search_code)
        records = get_results_list(active)
        results_url = active.url  # remember Level 2 URL to return after each detail

        hit_limit = False
        for rec in records:
            if time.monotonic() >= deadline:
                log("[INFO] Time limit — stopping for re-dispatch")
                hit_limit = True
                break

            rol = rec["rol"]
            if not rol:
                continue
            if checkpoint.get(rol) == "done":
                log(f"[INFO] Skip (already done): ROL {rol}")
                continue

            log(f"[INFO] Processing ROL {rol} — {rec.get('descripcion', '')}")
            try:
                # Level 2 → Level 3
                open_causa(active, rec, results_url)

                # Extract all Level 3 data via JS
                detail = extract_level3(active)
                log(f"[INFO] Extracted: {len(detail.get('tramites', []))} trámites, "
                    f"{len(detail.get('demandados', []))} demandados")

                case_data = {**rec, **detail}

                # Download PDFs from Sección C + D (only rows that have an href)
                all_docs = [d for d in detail.get("tramites", []) + detail.get("adjuntos", []) if d.get("href")]
                pdf_urls = download_pdfs(
                    active, ctx, all_docs,
                    args.job_id, rol, supabase_url, supabase_key, supabase_bucket,
                )

                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id":    args.job_id,
                    "record_id": rol,
                    "status":    "done",
                    "text":      json.dumps(case_data, ensure_ascii=False),
                    "pdf_url":   pdf_urls[0] if pdf_urls else "",
                }])
                log(f"[INFO] Done ROL {rol} — {len(pdf_urls)} PDFs saved")

                # Back to Level 2
                try:
                    active.goto(results_url, wait_until="domcontentloaded", timeout=45_000)
                    active.wait_for_selector(SEL_RESULTS, timeout=15_000)
                except PlaywrightTimeout:
                    # Site is slow — re-enter via parent to recover session
                    log(f"[WARN] Return to results timed out — re-entering via parent")
                    active = enter_via_parent(active, ctx, args.target_url)
                    search_rut(active, args.search_code)
                    active.wait_for_selector(SEL_RESULTS, timeout=20_000)
                    results_url = active.url

            except PlaywrightTimeout as e:
                log(f"[WARN] Timeout on ROL {rol}: {e}")
                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id": args.job_id, "record_id": rol,
                    "status": "failed", "text": json.dumps(rec), "pdf_url": "",
                }])
                write_status("incomplete")
            except Exception as e:
                log(f"[WARN] Error on ROL {rol}: {e}")
                write_checkpoints(supabase_url, supabase_key, [{
                    "job_id": args.job_id, "record_id": rol,
                    "status": "failed", "text": json.dumps(rec), "pdf_url": "",
                }])

        ctx.close()
        browser.close()

    final    = read_checkpoint(supabase_url, supabase_key, args.job_id)
    done_count = sum(1 for k, v in final.items() if k != "__job__" and v == "done")
    all_done = not hit_limit and done_count == len(records)

    if all_done and final:
        mark_job_status(supabase_url, supabase_key, args.job_id, "complete")
        write_status("complete")
        log(f"[INFO] Job {args.job_id} complete — {len(final)} causas processed")
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
