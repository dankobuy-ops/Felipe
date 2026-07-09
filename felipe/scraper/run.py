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

import gstore

STATUS_FILE  = Path("/tmp/scrape_status")
DOWNLOAD_DIR = Path("/tmp/pdfs")

SEL_ENTRY_LINK = "a:has-text('CONSULTA DE CAUSAS'), a:has-text('Consulta de Causas')"
# Lo Barnechea SMC form URL — custhelp JS opens this; we navigate directly after setting Referer.
SMC_LB_URL = "https://appl.smc.cl/JuzgadoDoc/Login.aspx?ReturnUrl=%2fjuzgadodoc%2ffrmBusqueda.aspx"
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
    p.add_argument("--setup", action="store_true",
                   help="One-time: OAuth login + provision the Drive folder/Sheet, then exit.")
    p.add_argument("--wipe", action="store_true",
                   help="Clear all data rows from the Sheet (keep headers), then exit.")
    p.add_argument("--all", action="store_true",
                   help="Batch mode: scrape every active RUT of every juzgado from the "
                        "Sheet's RutsConsulta tab (no --search-code/--target-url needed).")
    p.add_argument("--job-id",      default="")
    p.add_argument("--search-code", default="")
    p.add_argument("--target-url",  default="")
    p.add_argument("--max-seconds", type=int, default=240)
    p.add_argument("--year",        default="", help="Keep only entries whose fecha_proceso contains this year (e.g. 2024). Empty = all years.")
    p.add_argument("--from-year",   default="2020", help="Batch mode: keep causas from this year onward (default 2020).")
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


def filter_min_year(records, from_year):
    """Return only records from `from_year` onward. Unparseable dates are kept."""
    try:
        fy = int(from_year)
    except (TypeError, ValueError):
        return records
    def ok(r):
        y = extract_year(r.get("fecha_proceso", ""))
        return y is None or int(y) >= fy
    kept = [r for r in records if ok(r)]
    log(f"[INFO] Year filter >= {fy}: {len(kept)} / {len(records)} causas match")
    return kept


def write_status(s):
    """CI reads this to decide whether to re-dispatch. Best-effort — tolerate a
    missing /tmp on local (Windows) runs."""
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(s)
    except Exception:
        pass


def log(msg):
    print(msg, flush=True)


def dump_page(page, label):
    log(f"[DEBUG {label}] URL: {page.url}")
    log(f"[DEBUG {label}] HTML:\n{page.content()[:5000]}")


# ── Level 1 → Level 2: entry via parent ───────────────────────────────────────

def enter_via_parent(page, context, parent_url):
    """Load the municipality/court parent page and navigate to the SMC search form."""
    if "custhelp.com" in parent_url:
        # Lo Barnechea: custhelp has a JS onclick that opens the SMC form.
        # Strategy: load custhelp fully (networkidle), check for embedded frames or SMC links,
        # then try click-to-new-window; fall back to direct SMC URL with retry.
        try:
            page.goto(parent_url, wait_until="networkidle", timeout=60_000)
        except PlaywrightTimeout:
            pass  # Continue even if networkidle times out

        # Check if custhelp embedded an SMC frame already
        for frame in page.frames:
            if "appl.smc.cl" in frame.url or "JuzgadoDoc" in frame.url.lower():
                log(f"[DEBUG lb] Found embedded SMC frame: {frame.url}")
                return frame  # type: ignore[return-value]

        # Try to extract the SMC URL from any links or onclick attributes on the page
        smc_href = page.evaluate("""() => {
            const selectors = [
                'a[href*="appl.smc.cl"]',
                'a[href*="JuzgadoDoc"]',
                'a[onclick*="appl.smc.cl"]',
                'a[onclick*="JuzgadoDoc"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) return el.href || el.getAttribute('onclick');
            }
            return null;
        }""")

        # Navigate directly to the SMC URL found in the custhelp page, or fall back to constant.
        target_smc = smc_href if smc_href else SMC_LB_URL
        log(f"[DEBUG lb] Navigating to SMC: {target_smc}")
        try:
            page.goto(target_smc, wait_until="domcontentloaded", timeout=45_000)
        except PlaywrightTimeout:
            write_status("crashed")
            raise RuntimeError(f"Lo Barnechea SMC form timed out: {target_smc}")

        # Dump whatever page we landed on so we can see what SMC is showing.
        dump_page(page, "lb-landed")
        return page

    # Standard path (Vitacura and others): parent page → click Consulta de Causas link
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

    # Try expect_page first — handles target="_blank" and window.open() JS onclick.
    try:
        with context.expect_page(timeout=8_000) as info:
            page.click(SEL_ENTRY_LINK)
        p = info.value
        p.wait_for_load_state("domcontentloaded", timeout=30_000)
        return p
    except Exception:
        # No new window — link navigated in the current page
        page.wait_for_load_state("domcontentloaded", timeout=30_000)
        return page


def fill_login_selects(page, year):
    """Fill year+court dropdowns on Lo Barnechea's Login.aspx via JavaScript.

    The selects have disabled="disabled" in the initial HTML so Playwright's
    select_option() waits forever for them to become enabled. We bypass the
    disabled attribute entirely using evaluate(), remove it, set the value,
    and fire a change event so any onchange handlers still run.
    """
    # Known IDs from diagnostic run — set year and court directly via JS
    year_values = ["2026", "2025", "2024", "2023", "2022", "2021"]
    target_year = year if year in year_values else year_values[0]

    result = page.evaluate("""
        (targetYear) => {
            var out = {};
            var yearSel = document.getElementById('ctl00_ContentPlaceHolder1_Cmbyear');
            if (yearSel) {
                yearSel.removeAttribute('disabled');
                yearSel.value = targetYear;
                yearSel.dispatchEvent(new Event('change', {bubbles: true}));
                out.year = yearSel.value;
            } else {
                out.year = 'not found';
            }
            var courtSel = document.getElementById('ctl00_ContentPlaceHolder1_CmbJuz');
            if (courtSel) {
                courtSel.removeAttribute('disabled');
                courtSel.value = '1';
                courtSel.dispatchEvent(new Event('change', {bubbles: true}));
                out.court = courtSel.value;
            } else {
                out.court = 'not found';
            }
            return out;
        }
    """, target_year)
    log(f"[INFO] lb-selects set via JS: {result}")


def search_rut(page, rut, year="", juzgado=""):
    """Select RUT search type, fill RUT, submit — arrives at Level 2 (results list).

    The form REQUIRES selecting the RdBoRut radio first; submitting without a
    search type just re-renders the form (no results).
    Lo Barnechea's Login.aspx also needs year + court dropdowns filled first.
    """
    # Fill extra dropdowns if present (Lo Barnechea Login.aspx)
    if page.query_selector("select"):
        fill_login_selects(page, year)

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
    url_before = page.url
    page.click(SEL_SEARCH_BTN)
    # Wait for navigation (full postback) or UpdatePanel response (URL stays same).
    navigated = False
    try:
        page.wait_for_url(lambda u: u != url_before, timeout=20_000)
        log(f"[INFO] Click navigated: {page.url}")
        navigated = True
    except PlaywrightTimeout:
        log(f"[WARN] Click did not navigate (url={page.url}). Trying form.submit() fallback")
        try:
            # Bypass __doPostBack (which calls ASP.NET Ajax's _doPostBack that uses
            # `arguments` — banned in Playwright's strict-mode evaluate context).
            # Instead, set the hidden event fields and call form.submit() directly.
            page.evaluate("""
                () => {
                    var f = document.getElementById('aspnetForm') || document.forms[0];
                    if (!f) return;
                    var et = document.getElementById('__EVENTTARGET');
                    var ea = document.getElementById('__EVENTARGUMENT');
                    if (et) et.value = 'ctl00$ContentPlaceHolder1$btnAceptar';
                    if (ea) ea.value = '';
                    f.submit();
                }
            """)
            page.wait_for_url(lambda u: u != url_before, timeout=20_000)
            log(f"[INFO] form.submit() navigated: {page.url}")
            navigated = True
        except Exception as e:
            log(f"[WARN] Still not navigated after fallback (url={page.url}): {e}")
            dump_page(page, "after-submit-stuck")

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
            const parts = s.trim().split(/\\s+/).filter(Boolean);
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


# ── Normalization: one causa's JSON -> relational rows for the Sheet ───────────
# Ported from the old export_sheets.build_tables, applied per-causa as we scrape.

_PLATE_RE = re.compile(r"^[A-Z]{2,4}\d{2,4}$")

JUZGADO_NAMES = {"vitacura": "Vitacura", "lobarnechea": "Lo Barnechea"}
JUZGADOS_SEED = [
    {"juzgado_id": "vitacura", "nombre": "Vitacura",
     "url": "https://vitacura.cl/municipalidad/juzgado/juzgado-policia-local/"},
    {"juzgado_id": "lobarnechea", "nombre": "Lo Barnechea",
     "url": "https://mlobarnechea.custhelp.com/app/answers/detail/a_id/83/incidents.c$tipo_atencion/221"},
]


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _first(d, *keys):
    for k in keys:
        if d.get(k):
            return d[k]
    return ""


def _domicilio(party):
    return ", ".join(p for p in (party.get("direccion", ""), party.get("comuna", "")) if p)


def _plates(*fields):
    out, seen = [], set()
    for field in fields:
        for tok in re.split(r"[\n,;/]+", field or ""):
            p = re.sub(r"[\s\-.]", "", tok).strip().upper()
            if p and _PLATE_RE.match(p) and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _split_name(nombre):
    """Split "APELLIDO1 APELLIDO2, NOMBRE1 NOMBRE2" (or positional) → 4 parts."""
    if not nombre:
        return "", "", "", ""
    nombre = nombre.strip()
    if "," in nombre:
        apellidos_str, nombres_str = nombre.split(",", 1)
        apellidos = apellidos_str.strip().split()
        nombres = nombres_str.strip().split()
        ap_paterno = apellidos[0].title() if len(apellidos) >= 1 else ""
        ap_materno = apellidos[1].title() if len(apellidos) >= 2 else ""
        nombre1 = nombres[0].title() if len(nombres) >= 1 else ""
        segundo = " ".join(p.title() for p in nombres[1:])
        return nombre1, segundo, ap_paterno, ap_materno
    parts = nombre.split()
    n = len(parts)
    if n == 0:
        return "", "", "", ""
    if n == 1:
        return parts[0].title(), "", "", ""
    if n == 2:
        return parts[1].title(), "", parts[0].title(), ""
    if n == 3:
        return parts[2].title(), "", parts[0].title(), parts[1].title()
    return (parts[2].title(), " ".join(p.title() for p in parts[3:]),
            parts[0].title(), parts[1].title())


def normalize_causa(juzgado_id, search_code, case_data):
    """One causa's scraped JSON -> ({tab: [row dicts]}, caso_id).

    Enrichment-bearing tabs (Ruts email/phone, Patentes marca/...) are written
    rut/plate-only here; the caller skips ones already in the Sheet so prior
    enrichment is never clobbered by a re-scrape.
    """
    if juzgado_id not in JUZGADO_NAMES:
        juzgado_id = ""
    rol = case_data.get("rol") or ""
    cid = f"{juzgado_id or 'jpl'}/{rol}"
    causa = case_data.get("causa") or {}
    now = _now()
    out = {t: [] for t in ("Ruts", "Causas", "Tramites", "Documentos",
                           "Patentes", "CausaXRut", "CausaXPatente")}

    out["Causas"].append({
        "caso_id": cid, "rol": rol, "juzgado_id": juzgado_id,
        "materia": case_data.get("descripcion", "") or _first(
            causa, "descripcion", "descripción", "materia", "materia_causa",
            "materia_de_la_causa"),
        "fecha_causa": _first(causa, "fecha_causa"),
        "fecha_citacion": _first(causa, "fecha_citacion", "fecha_citación"),
        "fecha_estado": _first(causa, "fecha_estado"),
        "estado": causa.get("estado", ""),
        "boleta_numero": causa.get("boleta_numero", ""),
        "boleta_fecha": causa.get("boleta_fecha", ""),
        "monto_demandado": _first(causa, "monto", "monto_demandado", "cuantia",
                                  "cuantía", "monto_multa"),
    })

    # Demandante = the searched RUT (empresa)
    if search_code:
        out["Ruts"].append({"rut": search_code, "tipo": "empresa",
                            "razon_social": _first(causa, "remisor"), "updated_at": now})
        out["CausaXRut"].append({"vinculo_id": f"{cid}::{search_code}", "caso_id": cid,
                                 "rut": search_code, "rol_parte": "demandante",
                                 "updated_at": now})

    # Demandados (persona) + plates
    causa_plates = _plates(causa.get("placa_patente"), case_data.get("placa_patente"))
    plate_set, cp = set(causa_plates), set()
    dem_list = case_data.get("demandados") or []
    if not dem_list:
        cp.update(causa_plates)
    else:
        for dem in dem_list:
            rut = dem.get("rut", "")
            nom, seg, apat, amat = _split_name(dem.get("nombre", ""))
            if rut:
                out["Ruts"].append({
                    "rut": rut, "tipo": "persona", "nombre": nom, "segundo_nombre": seg,
                    "ap_paterno": apat, "ap_materno": amat, "email": dem.get("email", ""),
                    "telefono": dem.get("telefono", ""), "domicilio": _domicilio(dem),
                    "updated_at": now})
                out["CausaXRut"].append({"vinculo_id": f"{cid}::{rut}", "caso_id": cid,
                                         "rut": rut, "rol_parte": "demandado",
                                         "updated_at": now})
            plates = _plates(dem.get("patente"), dem.get("placa_patente")) or causa_plates
            plate_set.update(plates)
            cp.update(plates)

    for p in sorted(plate_set):
        out["Patentes"].append({"patente": p})        # enrichment filled later
    for p in sorted(cp):
        out["CausaXPatente"].append({"vinculo_id": f"{cid}::{p}", "caso_id": cid,
                                     "patente": p, "updated_at": now})

    for ti, t in enumerate(case_data.get("tramites") or [], 1):
        out["Tramites"].append({"tramite_id": f"{cid}/t{ti}", "caso_id": cid,
                                "fecha": t.get("fecha", ""),
                                "descripcion": t.get("descripcion", ""),
                                "pdf_url": t.get("pdf_url", "")})
    for xi, a in enumerate(case_data.get("adjuntos") or [], 1):
        out["Documentos"].append({"documento_id": f"{cid}/x{xi}", "caso_id": cid,
                                  "descripcion": a.get("descripcion", ""),
                                  "pdf_url": a.get("pdf_url", "")})
    return out, cid


def download_pdfs(context, docs, store, juzgado, rol):
    """Download each Sección C/D 'Abrir' document via its captured MostrarPDF.aspx
    href (authenticated session) → upload to Drive; tag each doc with its pdf_url."""
    pdf_urls = []
    doc_list = [d for d in docs
                if d.get("href") and not d["href"].startswith("javascript")]
    log(f"[INFO] ROL {rol}: {len(doc_list)} document href(s)")

    for i, doc in enumerate(doc_list):
        try:
            body = _fetch_pdf(context, doc["href"])
            if not body:
                log(f"[WARN] ROL {rol} doc {i+1}: no PDF resolved from {doc['href']}")
                continue
            obj = f"{juzgado or 'jpl'}/{rol}/doc{i}.pdf"
            url = store.upload_pdf(obj, body)
            # Tag the trámite/adjunto with its Drive link so the page links to the
            # downloaded PDF, not the login-gated source viewer.
            doc["pdf_url"] = url
            pdf_urls.append(url)
            log(f"[INFO] PDF {i+1} uploaded for ROL {rol} ({len(body)} bytes)")
        except Exception as e:
            log(f"[WARN] PDF {i+1} failed for ROL {rol}: {e}")

    return pdf_urls


# ── Scrape one (juzgado, RUT) into the Sheet/Drive ─────────────────────────────

def scrape_target(ctx, store, juzgado_id, target_url, search_code, deadline,
                  year="", from_year=None):
    """Scrape every causa for one RUT at one court. Reuses the shared browser
    context `ctx`; caller owns launch/close and completion/status.

    Returns (target_rols, done_rols, hit_limit).
    """
    page   = ctx.new_page()
    active = enter_via_parent(page, ctx, target_url)
    active = search_rut(active, search_code, year=year, juzgado=juzgado_id)
    records = get_results_list(active)
    records = (filter_min_year(records, from_year) if from_year is not None
               else filter_by_year(records, year))

    # Dedupe by ROL: the results list can repeat a ROL.
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

    target_rols = {r["rol"] for r in records if r.get("rol")}
    done_rols = set()
    hit_limit = False
    for rec in records:
        rol = rec["rol"]
        if not rol:
            continue

        caso_id = f"{juzgado_id or 'jpl'}/{rol}"
        # Resume off the Sheet: a caso_id already present means fully written
        # (Causas is upserted last, after its trámites/docs/links).
        if store.has("Causas", caso_id):
            log(f"[INFO] Skip (already in Sheet): ROL {rol}")
            done_rols.add(rol)
            continue

        if time.monotonic() >= deadline:
            log("[INFO] Time limit — stopping for re-dispatch")
            hit_limit = True
            break

        log(f"[INFO] Processing ROL {rol} — {rec.get('descripcion', '')}")
        try:
            # Level 2 → Level 3
            open_causa(active, rec, results_url)
            detail = extract_level3(active)

            # Remove the demandante (search RUT) from demandados — some JPL
            # layouts include the plaintiff in Section A.1 alongside defendants.
            search_norm = norm_rut(search_code)
            detail['demandados'] = [
                d for d in detail.get('demandados', [])
                if norm_rut(d.get('rut', '')) != search_norm
            ]

            log(f"[INFO] Extracted: {len(detail.get('tramites', []))} trámites, "
                f"{len(detail.get('demandados', []))} demandados")

            case_data = {**rec, **detail}

            # Download PDFs (Sección C + D) via the captured MostrarPDF.aspx
            # hrefs, using the authenticated session → upload to Drive.
            all_docs = detail.get("tramites", []) + detail.get("adjuntos", [])
            pdf_urls = download_pdfs(ctx, all_docs, store, juzgado_id, rol)

            # Drop adjuntos with no downloaded PDF before persisting
            case_data['adjuntos'] = [
                a for a in case_data.get('adjuntos', []) if a.get('pdf_url')
            ]

            tabs, cid = normalize_causa(juzgado_id, search_code, case_data)
            # Insert-only for enrichment-bearing tabs so a re-scrape never
            # clobbers email (Ruts) / vehicle data (Patentes) added later.
            tabs["Ruts"] = [r for r in tabs["Ruts"]
                            if not store.has("Ruts", r["rut"])]
            tabs["Patentes"] = [r for r in tabs["Patentes"]
                                if not store.has("Patentes", r["patente"])]
            # Causas LAST — its presence is the resume "done" sentinel.
            for tab in ("Ruts", "Patentes", "Tramites", "Documentos",
                        "CausaXRut", "CausaXPatente", "Causas"):
                store.upsert(tab, tabs[tab])

            done_rols.add(rol)
            log(f"[INFO] Done ROL {rol} — {len(pdf_urls)} PDFs saved")

            # Back to Level 2
            try:
                active.goto(results_url, wait_until="domcontentloaded", timeout=45_000)
                active.wait_for_selector(SEL_RESULTS, timeout=15_000)
            except PlaywrightTimeout:
                # Site is slow — re-enter via parent to recover session
                log(f"[WARN] Return to results timed out — re-entering via parent")
                active = enter_via_parent(active, ctx, target_url)
                active = search_rut(active, search_code, year=year, juzgado=juzgado_id)
                active.wait_for_selector(SEL_RESULTS, timeout=20_000)
                results_url = active.url

        except PlaywrightTimeout as e:
            log(f"[WARN] Timeout on ROL {rol}: {e}")
            write_status("incomplete")
        except Exception as e:
            log(f"[WARN] Error on ROL {rol}: {e}")

    try:
        page.close()
    except Exception:
        pass
    return target_rols, done_rols, hit_limit


# ── Single-RUT mode (scrape.yml) ──────────────────────────────────────────────

def scrape(args, store):
    deadline = time.monotonic() + args.max_seconds
    store.upsert("Juzgados", JUZGADOS_SEED)   # court registry (Causas.juzgado_id FK)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx     = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        try:
            target_rols, done_rols, hit_limit = scrape_target(
                ctx, store, args.juzgado, args.target_url, args.search_code,
                deadline, year=args.year)
        finally:
            ctx.close()
            browser.close()

    all_done = not hit_limit and target_rols.issubset(done_rols)
    if all_done:
        write_status("complete")
        log(f"[INFO] Job complete — {len(done_rols)}/{len(target_rols)} causas in the Sheet")
    else:
        write_status("incomplete")
        log(f"[INFO] Job incomplete — {len(done_rols)}/{len(target_rols)} done, will re-dispatch")


# ── Batch mode (scrape-all.yml): every active RUT of every juzgado ─────────────

def scrape_all(args, store):
    """Scrape the whole RutsConsulta matrix (one click, no input), causas >= from_year."""
    deadline = time.monotonic() + args.max_seconds
    store.upsert("Juzgados", JUZGADOS_SEED)
    store.ensure_search_tab()
    url_map = {j["juzgado_id"]: j["url"] for j in JUZGADOS_SEED}
    combos = [c for c in store.read_search_ruts() if c["activo"]]
    log(f"[INFO] Batch: {len(combos)} active (juzgado, rut) combos; causas >= {args.from_year}")

    incomplete = False
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx     = browser.new_context(accept_downloads=True, ignore_https_errors=True)
        try:
            for c in combos:
                if time.monotonic() >= deadline:
                    log("[INFO] Global time limit reached — will re-dispatch")
                    incomplete = True
                    break
                url = url_map.get(c["juzgado_id"])
                if not url:
                    log(f"[WARN] Unknown juzgado {c['juzgado_id']!r} — skipping")
                    continue
                log(f"[INFO] ===== {c['juzgado_id']} | {c['rut']} =====")
                try:
                    target, done, hit = scrape_target(
                        ctx, store, c["juzgado_id"], url, c["rut"],
                        deadline, from_year=args.from_year)
                    if hit or not target.issubset(done):
                        incomplete = True
                except Exception as e:
                    log(f"[WARN] Combo {c['juzgado_id']}|{c['rut']} failed: {e}")
                    incomplete = True
        finally:
            ctx.close()
            browser.close()

    if incomplete:
        write_status("incomplete")
        log("[INFO] Batch incomplete — will re-dispatch")
    else:
        write_status("complete")
        log("[INFO] Batch complete — all active RUTs scraped")


def main():
    args = parse_args()

    if args.setup:
        gstore.provision()
        log("[SETUP] done. Batch: python run.py --all  (or single: --search-code <RUT> "
            "--target-url <URL> --juzgado <vitacura|lobarnechea>)")
        return

    if args.wipe:
        gstore.Store().clear_data()
        log("[WIPE] cleared all data rows from the Sheet (headers kept)")
        return

    try:
        store = gstore.Store()
        if args.all:
            scrape_all(args, store)
        else:
            if not (args.search_code and args.target_url):
                sys.exit("ERROR: --search-code and --target-url are required "
                         "(or use --all for batch, or --setup).")
            scrape(args, store)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
