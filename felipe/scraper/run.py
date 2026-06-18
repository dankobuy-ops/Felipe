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
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from checkpoint import mark_job_status, read_checkpoint, write_checkpoints
from storage import upload_pdf

STATUS_FILE  = Path("/tmp/scrape_status")
DOWNLOAD_DIR = Path("/tmp/pdfs")

SEL_ENTRY_LINK = "a:has-text('CONSULTA DE CAUSAS'), a:has-text('Consulta de Causas')"
# ASP.NET form (vitacura): radio selects search type, then txtRut + btnAceptar.
SEL_RADIO_RUT  = "#ctl00_ContentPlaceHolder1_RdBoRut, input[type='radio'][value='RdBoRut']"
SEL_RUT_INPUT  = "#ctl00_ContentPlaceHolder1_txtRut, input[type='text'][id*='txtRut'], input[type='text'][id*='Rut']"
SEL_SEARCH_BTN = "#ctl00_ContentPlaceHolder1_btnAceptar, input[type='submit'][value='Aceptar'], input[type='submit']"
SEL_RESULTS    = "table tbody tr"

# Text that only appears on the SEARCH FORM — if we still see it after submitting,
# the search did not execute (no search-type selected / postback re-rendered form).
FORM_MARKERS = ("seleccione la opción", "ej: 12345678", "ej: aa1111", "placa:")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--job-id",      required=True)
    p.add_argument("--search-code", required=True)
    p.add_argument("--target-url",  required=True)
    p.add_argument("--max-seconds", type=int, default=240)
    p.add_argument("--year",        default="", help="Keep only entries whose fecha_proceso contains this year (e.g. 2024). Empty = all years.")
    p.add_argument("--juzgado",     default="", help="Court identifier (e.g. vitacura, lobarnechea)")
    return p.parse_args()


def norm_rut(r):
    """Normalize RUT for comparison — strips dots and spaces, lowercases."""
    return re.sub(r'[\.\s]', '', str(r or '')).lower()


def extract_year(fecha_str):
    """Return 4-digit year string from dates like '01/01/2024', '2024-01-01', or None if unparseable."""
    for part in fecha_str.strip().replace("-", "/").replace(".", "/").split("/"):
        if len(part) == 4 and part.isdigit():
            return part
    return None


def filter_by_year(records, year):
    """Return only records whose fecha_proceso matches year. Unparseable dates are kept."""
    if not year:
        return records
    kept = [r for r in records if extract_year(r.get("fecha_proceso", "")) in (year, None)]
    log(f"[INFO] Year filter {year!r}: {len(kept)} / {len(records)} causas match")
    return kept


def write_status(s):
    STATUS_FILE.write_text(s)


def log(msg):
    print(msg, flush=True)


def dump_page(page, label):
    log(f"[DEBUG {label}] URL: {page.url}")
    log(f"[DEBUG {label}] HTML:\n{page.content()[:5000]}")


# ── Level 1 → Level 2: entry via parent ───────────────────────────────────────

def enter_via_parent(page, context, parent_url):
    """Load the municipality/court parent page and click the Consulta de Causas link."""
    # Navigate to the parent page, then click the consulta link
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
    """Select RUT search type, fill RUT, submit — arrives at Level 2 (results list).

    The form REQUIRES selecting the RdBoRut radio first; submitting without a
    search type just re-renders the form (no results).
    """
    try:
        page.wait_for_selector(SEL_RUT_INPUT, timeout=20_000)
    except PlaywrightTimeout:
        dump_page(page, "no-rut-input")
        write_status("crashed")
        raise RuntimeError("RUT input not found.")

    # 1. Ensure the RUT search-type radio is selected. It is selected by default,
    #    so only click it if needed — avoids a spurious AutoPostBack that could
    #    reset the form.
    try:
        if not page.is_checked(SEL_RADIO_RUT):
            page.check(SEL_RADIO_RUT, timeout=5_000)
            log("[INFO] Selected RUT search-type radio")
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except PlaywrightTimeout:
                pass
            page.wait_for_selector(SEL_RUT_INPUT, timeout=10_000)
        else:
            log("[INFO] RUT radio already selected")
    except PlaywrightTimeout:
        log("[WARN] RUT radio not found — proceeding without it")

    # 2. Fill the RUT (after any radio postback, so the value survives).
    page.fill(SEL_RUT_INPUT, rut)
    log(f"[INFO] Filled RUT: {rut}")

    # 3. Submit. A valid RUT triggers a full postback that redirects to
    #    frmBusqueda.aspx (with a loading overlay). Wait for that navigation;
    #    if the click doesn't fire it, trigger the ASP.NET postback directly.
    def _on_results():
        return "frmbusqueda" in page.url.lower()

    try:
        page.wait_for_selector(SEL_SEARCH_BTN, timeout=5_000)
    except PlaywrightTimeout:
        pass

    log(f"[INFO] Submitting search. URL before click: {page.url}")
    try:
        with page.expect_navigation(url="**frmBusqueda*", timeout=20_000):
            page.click(SEL_SEARCH_BTN)
        log("[INFO] Click navigated to results page")
    except PlaywrightTimeout:
        log(f"[WARN] Click did not navigate (url={page.url}). Trying __doPostBack fallback")
        try:
            with page.expect_navigation(url="**frmBusqueda*", timeout=20_000):
                page.evaluate(
                    "() => { if (window.__doPostBack) __doPostBack('ctl00$ContentPlaceHolder1$btnAceptar',''); }"
                )
            log("[INFO] __doPostBack navigated to results page")
        except PlaywrightTimeout:
            log(f"[WARN] Still not on results after fallback (url={page.url})")

    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeout:
        pass

    # Diagnostic: capture any validation / status message the server returned.
    try:
        msgs = page.evaluate("""() => {
            const re = /no existe|inv[aá]lid|incorrect|debe ingresar|sin resultado|error/i;
            return Array.from(document.querySelectorAll('span,div,td,p,label'))
                .map(e => (e.innerText || '').trim())
                .filter(t => t && t.length < 120 && re.test(t))
                .slice(0, 8);
        }""")
        if msgs:
            log(f"[INFO] Page messages after submit: {msgs}")
    except Exception:
        pass

    log(f"[INFO] After submit: on_results={_on_results()} url={page.url}")
    return page

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

    # Guard: if the search form is still visible, the search did NOT execute.
    # Don't scrape the form's layout tables as fake causas.
    page_text = page.evaluate("() => document.body.innerText.toLowerCase()")
    if any(m in page_text for m in FORM_MARKERS):
        dump_page(page, "still-on-form")
        write_status("crashed")
        raise RuntimeError("Still on search form after submit — search did not execute.")

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


def write_meta(supabase_url, supabase_key, job_id, total, rut="", year="", juzgado=""):
    """Write __meta__ row with total count + query params so the SPA can list
    and label previous jobs (the 'Jobs anteriores' history)."""
    write_checkpoints(supabase_url, supabase_key, [{
        "job_id":    job_id,
        "record_id": "__meta__",
        "status":    "running",
        "text":      json.dumps({"total": total, "rut": rut, "year": year, "juzgado": juzgado,
                                 "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}),
        "pdf_url":   "",
    }])


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
                        else if (lbl === 'TELEFONO' || lbl === 'TELÉFONO' || lbl === 'FONO' || lbl === 'CELULAR') party.telefono = val;
                        else if (lbl === 'CORREO' || lbl === 'EMAIL' || lbl === 'CORREO ELECTRONICO' || lbl === 'CORREO ELECTRÓNICO') party.email = val;
                        // Vehicle fields — present per-demandado on some JPL layouts
                        else if (lbl.includes('MARCA')) party.marca = val;
                        else if (lbl.includes('MODELO')) party.modelo = val;
                        else if (lbl === 'AÑO' || lbl === 'ANO' || lbl === 'AÑO VEHICULO' || lbl === 'AÑO VEHÍCULO') party.año = val;
                        else if (lbl === 'PATENTE' || lbl.includes('PLACA')) party.patente = val;
                        else if (lbl === 'USO' || lbl === 'USO VEHICULO' || lbl === 'USO VEHÍCULO') party.uso = val;
                    }
                }
            }
            if (party) parties.push(party);

            // Deduplicate by RUT (fallback: nombre) — ASP.NET grids can render
            // the same party twice: once as a label row (no address) and once
            // with full data. Merge both so no field is lost.
            const seen = new Map();
            for (const p of parties) {
                const key = p.rut || p.nombre || '';
                if (!seen.has(key)) {
                    seen.set(key, Object.assign({}, p));
                } else {
                    const ex = seen.get(key);
                    for (const k of Object.keys(p)) { if (!ex[k] && p[k]) ex[k] = p[k]; }
                }
            }
            return Array.from(seen.values()).filter(p => p.nombre);
        }

        function dedupVal(s) {
            if (!s) return s;
            const parts = s.trim().split(/\s+/).filter(Boolean);
            const unique = [...new Set(parts)];
            if (unique.length < parts.length) return unique.join(' ');
            if (s.length % 2 === 0 && s.slice(0, s.length/2) === s.slice(s.length/2))
                return s.slice(0, s.length/2);
            return s;
        }

        function extractSectionB() {
            const LABELS = ['ROL INICIO','DESCRIPCION','DESCRIPCIÓN','FECHA CAUSA',
                            'ACTUARIO','PLACA PATENTE','REMISOR','FECHA CITACION',
                            'FECHA CITACIÓN','ESTADO','FECHA ESTADO',
                            'MONTO','MONTO DEMANDADO','CUANTIA','CUANTÍA','MONTO MULTA',
                            'MARCA','MARCA VEHICULO','MARCA VEHÍCULO',
                            'MODELO','MODELO VEHICULO','MODELO VEHÍCULO',
                            'AÑO','ANO','AÑO VEHICULO','AÑO VEHÍCULO',
                            'MATERIA','MATERIA CAUSA','MATERIA DE LA CAUSA',
                            'USO','USO VEHICULO','USO VEHÍCULO'];
            const cells = allCells();
            const out   = {};
            for (let i = 0; i < cells.length - 1; i++) {
                const t = cells[i].innerText.trim().replace(':','').toUpperCase();
                if (LABELS.includes(t)) {
                    const val = cells[i+1].innerText.trim();
                    if (val && !LABELS.includes(val.toUpperCase().replace(':','')))
                        out[t.toLowerCase().replace(/ /g,'_')] = dedupVal(val);
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

def _resolve_embedded_pdf(html, base_url):
    """If the viewer returned HTML, find the embedded/linked PDF URL inside it."""
    for pat in (
        r'<embed[^>]+src=["\']([^"\']+)["\']',
        r'<iframe[^>]+src=["\']([^"\']+)["\']',
        r'<object[^>]+data=["\']([^"\']+)["\']',
        r'href=["\']([^"\']*(?:MostrarPDF|\.pdf|getfile)[^"\']*)["\']',
    ):
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return urljoin(base_url, m.group(1))
    return None


def _fetch_pdf(context, href, depth=0):
    """Fetch a PDF via the AUTHENTICATED session (context.request shares the
    login cookie). The MostrarPDF.aspx href either streams the PDF directly or
    returns an HTML viewer embedding it — follow one level. Returns bytes/None."""
    resp = context.request.get(href, timeout=30_000)
    if not resp.ok:
        log(f"[WARN]   fetch -> HTTP {resp.status} for {href}")
        return None
    body = resp.body()
    if b"%PDF-" in body[:1024]:
        return body
    if depth == 0:
        html = body.decode("utf-8", "ignore")
        if "login.aspx" in (resp.url or "").lower() or "ReturnUrl" in html:
            log("[WARN]   viewer bounced to Login — session not authenticated")
            return None
        real = _resolve_embedded_pdf(html, resp.url or href)
        if real and real != href:
            log(f"[INFO]   viewer embeds PDF at {real}")
            return _fetch_pdf(context, real, depth + 1)
    return None


def download_pdfs(page, context, docs, job_id, rol, supabase_url, supabase_key, bucket):
    """Download each Sección C/D 'Abrir' document via its captured MostrarPDF.aspx
    href, using the authenticated browser session. (The viewer requires login —
    only works because search_rut established the forms-auth cookie.)"""
    pdf_urls = []
    doc_list = [d for d in docs
                if d.get("href") and not d["href"].startswith("javascript")]
    log(f"[INFO] ROL {rol}: {len(doc_list)} document href(s)")

    for i, doc in enumerate(doc_list):
        local_pdf = DOWNLOAD_DIR / f"{rol}_doc{i}.pdf"
        try:
            body = _fetch_pdf(context, doc["href"])
            if not body:
                log(f"[WARN] ROL {rol} doc {i+1}: no PDF resolved from {doc['href']}")
                continue
            local_pdf.write_bytes(body)
            url = upload_pdf(supabase_url, supabase_key, bucket, job_id, f"{rol}_doc{i}", local_pdf)
            # Tag the trámite/adjunto with its Supabase public URL so the SPA
            # links to the downloaded PDF, not the login-gated source viewer.
            doc["pdf_url"] = url
            pdf_urls.append(url)
            log(f"[INFO] PDF {i+1} uploaded for ROL {rol} ({len(body)} bytes)")
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
        active = search_rut(active, args.search_code)
        records = get_results_list(active)
        records = filter_by_year(records, args.year)

        # Dedupe by ROL: the results list can repeat a ROL, and checkpoints are
        # keyed by (job_id, record_id), so a duplicate would collapse to one row
        # and make the "all done" check unsatisfiable (job never completes).
        seen_rol, unique = set(), []
        for r in records:
            rid = r.get("rol")
            if rid and rid not in seen_rol:
                seen_rol.add(rid)
                unique.append(r)
        if len(unique) != len(records):
            log(f"[INFO] Deduped {len(records)} -> {len(unique)} unique ROLs")
        records = unique

        results_url = active.url  # remember Level 2 URL to return after each detail

        # Tell the SPA the total count immediately so progress is accurate from the start
        write_meta(supabase_url, supabase_key, args.job_id, len(records),
                   rut=args.search_code, year=args.year, juzgado=args.juzgado)

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

                # Remove the demandante (search RUT) from demandados — some JPL
                # layouts include the plaintiff in Section A.1 alongside defendants.
                search_norm = norm_rut(args.search_code)
                detail['demandados'] = [
                    d for d in detail.get('demandados', [])
                    if norm_rut(d.get('rut', '')) != search_norm
                ]

                log(f"[INFO] Extracted: {len(detail.get('tramites', []))} trámites, "
                    f"{len(detail.get('demandados', []))} demandados")

                case_data = {**rec, **detail}

                # Download PDFs from Sección C + D via the captured MostrarPDF.aspx
                # hrefs, using the authenticated session.
                all_docs = detail.get("tramites", []) + detail.get("adjuntos", [])
                pdf_urls = download_pdfs(
                    active, ctx, all_docs,
                    args.job_id, rol, supabase_url, supabase_key, supabase_bucket,
                )

                # Drop adjuntos with no downloaded PDF before persisting
                case_data['adjuntos'] = [
                    a for a in case_data.get('adjuntos', []) if a.get('pdf_url')
                ]

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
                    active = search_rut(active, args.search_code)
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

    final = read_checkpoint(supabase_url, supabase_key, args.job_id)
    # Completion = every target ROL has a 'done' checkpoint. Set-based so a
    # duplicate ROL or a skipped empty row can't make this unsatisfiable.
    target_rols = {r["rol"] for r in records if r.get("rol")}
    done_rols   = {k for k, v in final.items()
                   if k not in ("__job__", "__meta__") and v == "done"}
    all_done = not hit_limit and target_rols.issubset(done_rols)

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
