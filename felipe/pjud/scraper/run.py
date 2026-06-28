"""Scraper for Poder Judicial Virtual — Oficina Judicial Virtual (OJV).

Public guest access, no captcha, no login. Scope (see pjud/HANDOFF.md):
  - Civil competencia. Per bank, sweep EVERY corte × tribunal in Chile (~230)
    via "Búsqueda por Rut Persona Jurídica" — the banks come from the Bancos tab.
  - Keep only causas whose ROL starts with 'C' AND ingresadas on/after start_date
    (the go-live anchor in pjud_config.json; "from today onwards").
  - Download docs/anexos/ebook PDFs to a Google Drive "Documentos" folder.

Flow (verified via live recon):
  1. home/index.php → accesoConsultaCausas() → indexN.php (guest session).
  2. tab "Búsqueda por Rut Persona Jurídica"; competencia(Civil=3) once; then for
     each corte select #corteJur (repopulates #jurTribunal) and for each tribunal
     fill rut/dv/era + Buscar. NB: a realistic UA is required, and the FIRST
     search after load always returns 0 (warm_up() absorbs it).
  3. results table → keep Rol 'C' + fecha ≥ start_date → each 🔍 =
     detalleCausaCivil('<JWT>').
  4. #modalDetalleCivil → header + iterate #selCuaderno → historia / litigantes /
     escritos panes; receptor + georref sub-modals; download docs per row.

The daily GitHub Actions workflow runs ONE bank per parallel job (matrix from the
Bancos tab). IDs are plain deterministic codes (causa_id = "<tribunal_id>-<rol>";
rol isn't unique nationwide). Writes incrementally to a Google Sheet + Drive via gstore.
Run `python run.py --setup` once, then `python run.py --rut 97004000 --dv 5`.
"""

import argparse
import calendar
import json
import os
import re
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

import gstore

# ── Constants ─────────────────────────────────────────────────────────────────

OJV       = "https://oficinajudicialvirtual.pjud.cl"
HOME      = f"{OJV}/home/index.php"

VAL_COMPETENCIA = "3"   # Civil (#jurCompetencia) — Rol starts with 'C'

# The 17 Cortes de Apelaciones (#corteJur values, mapped during recon). Selecting
# a corte repopulates #jurTribunal with that corte's tribunales; iterating all of
# them covers every civil tribunal in Chile (~230).
CORTES = [
    ("10", "C.A. de Arica"),       ("11", "C.A. de Iquique"),
    ("15", "C.A. de Antofagasta"), ("20", "C.A. de Copiapó"),
    ("25", "C.A. de La Serena"),   ("30", "C.A. de Valparaíso"),
    ("35", "C.A. de Rancagua"),    ("40", "C.A. de Talca"),
    ("45", "C.A. de Chillan"),     ("46", "C.A. de Concepción"),
    ("50", "C.A. de Temuco"),      ("55", "C.A. de Valdivia"),
    ("56", "C.A. de Puerto Montt"),("60", "C.A. de Coyhaique"),
    ("61", "C.A. de Punta Arenas"),("90", "C.A. de Santiago"),
    ("91", "C.A. de San Miguel"),
]

# How long to wait for a search's results to render before treating the tribunal
# as empty for this bank (most tribunals return nothing for a given bank).
SEARCH_WAIT_MS = 8000
# Small delay between searches — OJV captcha-gates by IP under rapid guest traffic;
# pacing keeps a long single-session sweep under the radar.
PACE_MS = 500

SCRATCH = Path(os.environ.get("TEMP", "/tmp")) / "pjud_pdfs"

STORE = None       # gstore.Store, set in main() (None under --dry-run)
DRY = False        # --dry-run: verify live nav/parse without any writes
SKIP_DOCS = False  # --skip-docs: scrape metadata only, no PDF download/upload
PROC_FILTER = "Ejecutivo Obligación de Dar"  # only scrape causas whose Proc. == this


def log(msg):
    print(msg, flush=True)


# ── Write layer: Google Sheet upsert + Drive PDF upload (via gstore) ──────────

def upsert(table, rows):
    """Upsert dict rows into the Sheet tab for `table`, keyed on column A."""
    if not rows:
        return 0
    if DRY or STORE is None:
        log(f"[DRY] upsert {table}: {len(rows)} row(s); sample={rows[0]}")
        return len(rows)
    return STORE.upsert(table, rows)


def upload_pdf(object_path, data):
    """Upload PDF bytes to the Drive Documentos folder, return its link.
    Guards against tiny/corrupt downloads."""
    if len(data) < 1024:
        raise RuntimeError(f"download too small ({len(data)}B) for {object_path}")
    if DRY or STORE is None:
        log(f"[DRY] upload {object_path} ({len(data)}B)")
        return f"DRY://{object_path}"
    return STORE.upload_pdf(object_path, data)


# ── RUT / name parsing ────────────────────────────────────────────────────────

def norm_rut(rut):
    """'12.345.678-9' -> '12345678-9' (strip dots/spaces, lower the dv)."""
    r = re.sub(r"[.\s]", "", (rut or "")).lower()
    return r


def split_persona(nombre):
    """Persona NATURAL, name-first order 'NOMBRE [SEGUNDO] APAT [AMAT]'.
    Heuristic: first token = nombre, last two = ap_paterno/ap_materno, middle =
    segundo_nombre. Strips '(Poder Amplio/Simple)'. Refine against live data."""
    n = re.sub(r"\(poder[^)]*\)", "", nombre, flags=re.I).strip()
    toks = [t for t in re.split(r"\s+", n) if t]
    nombre = seg = apat = amat = ""
    if len(toks) == 1:
        nombre = toks[0]
    elif len(toks) == 2:
        nombre, apat = toks
    elif len(toks) == 3:
        nombre, apat, amat = toks
    else:  # 4+: first=nombre, second=segundo_nombre, last two=apellidos
        nombre, seg, apat, amat = toks[0], toks[1], toks[-2], toks[-1]
    return nombre, seg, apat, amat


# ── Navigation: home → search form ────────────────────────────────────────────

def reach_search_form(page, context):
    """home → accesoConsultaCausas() (POSTs a guest session, then same-tab
    redirects to indexN.php) → return the page holding the search form."""
    seen = []
    page.on("request", lambda r: seen.append(("REQ", r.method, r.url[:110]))
            if "sesion-invitado" in r.url else None)
    page.on("requestfailed", lambda r: seen.append(("FAIL", str(r.failure), r.url[:110]))
            if "sesion-invitado" in r.url else None)
    page.on("response", lambda r: seen.append(("RESP", r.status, r.url[:110]))
            if ("sesion-invitado" in r.url or "indexN.php" in r.url or r.status >= 400)
            else None)

    page.goto(HOME, wait_until="load", timeout=45_000)
    page.wait_for_timeout(3000)

    has_fn = page.evaluate("typeof accesoConsultaCausas === 'function'")
    log(f"[NAV] accesoConsultaCausas defined={has_fn}; calling → indexN.php…")
    if has_fn:
        page.evaluate("accesoConsultaCausas()")
    try:
        page.wait_for_url("**/indexN.php**", timeout=30_000)
    except PlaywrightTimeout:
        # Diagnose: WAF/IP block vs timing. Dump what the runner actually got.
        try:
            title = page.title()
            body = (page.inner_text("body") or "")[:400].replace("\n", " ")
        except Exception:
            title, body = "?", "?"
        log(f"[NAV][FAIL] still at {page.url} | defined={has_fn} | title={title!r}")
        log(f"[NAV][FAIL] responses={seen}")
        log(f"[NAV][FAIL] body[:400]={body!r}")
        raise
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2500)
    log(f"[NAV] search page -> {page.url}")
    return page


def establish_form(page, context, kind, retries=5):
    """Reach the consulta form and open the search tab for `kind` ('rut'|'date'),
    retrying through the OJV's intermittent failures to render (guest session or
    the tab-strip AJAX sometimes 'crushes' — a re-navigation usually fixes it)."""
    opener = open_search_tab if kind == "rut" else open_date_tab
    last = None
    for i in range(retries):
        try:
            reach_search_form(page, context)
            opener(page)
            return
        except Exception as e:
            last = e
            log(f"[NAV] establish({kind}) attempt {i + 1}/{retries} failed: {e}")
            page.wait_for_timeout(3000)
    raise RuntimeError(f"could not establish the {kind} search form: {last}")


def open_search_tab(page):
    """Activate the 'Rut Persona Jurídica' tab and lock competencia = Civil.
    Done once per page; corte/tribunal are then iterated by the sweep. The consulta
    form renders via AJAX after indexN.php, so wait for the tab anchor first."""
    page.wait_for_selector("a[href='#BusJuridica']", timeout=30_000)
    page.wait_for_timeout(500)
    page.click("a[href='#BusJuridica']")
    page.wait_for_timeout(800)
    _select(page, "#jurCompetencia", VAL_COMPETENCIA, "competencia")
    page.wait_for_timeout(1500)   # corte list populates via AJAX


def select_corte(page, corte_val, corte_name):
    """Select a corte and return its tribunal options [{v,t}] (AJAX-populated)."""
    _select(page, "#corteJur", corte_val, f"corte {corte_name}")
    page.wait_for_timeout(1800)   # #jurTribunal repopulates via AJAX
    return page.eval_on_selector_all(
        "#jurTribunal option",
        "els=>els.map(e=>({v:e.value,t:(e.textContent||'').trim()}))")


def _wait_results(page, max_ms=SEARCH_WAIT_MS):
    """Poll the results table: return True as soon as a row appears, else False
    once max_ms elapses (the tribunal has no causas for this bank)."""
    waited, step = 0, 600
    while waited < max_ms:
        n = page.eval_on_selector_all(
            "#dtaTableDetalleJuridica tbody tr", "e=>e.length")
        if n:
            page.wait_for_timeout(700)   # let the rest of the rows render
            return True
        page.wait_for_timeout(step)
        waited += step
    return False


def search_tribunal(page, trib_val, rut_sin_dv, dv, era):
    """Pick a tribunal (corte already selected), fill rut/dv/era, Buscar.
    Returns True if any results rendered."""
    _select(page, "#jurTribunal", trib_val, "tribunal")
    page.fill("#rutJur", str(rut_sin_dv))
    page.fill("#dvJur", str(dv))
    page.fill("#eraJur", str(era))
    # Clear any prior results so _wait_results doesn't see a stale table.
    page.evaluate("() => { const t = document.querySelector('#dtaTableDetalleJuridica tbody');"
                  " if (t) t.innerHTML=''; }")
    page.click("#btnConConsultaJur")
    found = _wait_results(page)
    page.wait_for_timeout(PACE_MS)
    return found


def form_alive(page):
    """True while the Jurídica search form is present (i.e. the guest session
    hasn't expired or been captcha-gated mid-sweep)."""
    try:
        return page.eval_on_selector_all("#jurCompetencia", "e=>e.length") > 0
    except Exception:
        return False


def reopen_form(page, context):
    """Re-establish the guest session + search tab after a soft block/timeout."""
    log("[NAV] search form missing — re-establishing guest session…")
    reach_search_form(page, context)
    open_search_tab(page)
    warm_up(page)


def warm_up(page):
    """The FIRST search after the form loads always returns 0 rows (a site quirk).
    Burn one throwaway search so the first real query isn't silently lost."""
    try:
        tribs = select_corte(page, CORTES[0][0], CORTES[0][1])
        first = next((o["v"] for o in tribs if o["v"] not in ("", "0")), None)
        if first:
            search_tribunal(page, first, "97004000", "5", time.strftime("%Y"))
            log("[NAV] warm-up search done (discarded)")
    except Exception as e:
        log(f"[WARN] warm-up: {e}")


def _select(page, sel, value, label):
    """select_option by value; on failure log the available options so a live run
    reveals the right mapping."""
    try:
        page.select_option(sel, value=value)
        return
    except Exception:
        opts = page.eval_on_selector_all(
            f"{sel} option",
            "els=>els.map(e=>({v:e.value,t:(e.textContent||'').trim()}))")
        log(f"[WARN] {label} ({sel}) value={value!r} failed. Options: {opts}")


# ── Results → causa rows (ROL starts with 'C') ────────────────────────────────

def collect_causas(page):
    """Return [{rol, fecha, caratulado, tribunal, jwt}] from #dtaTableDetalleJuridica
    (cols: 🔍 | Rol | Fecha | Caratulado | Tribunal), keeping only Rol starting 'C'."""
    rows = page.eval_on_selector_all(
        "#dtaTableDetalleJuridica tbody tr",
        r"""els => els.map(tr => {
          const td = Array.from(tr.querySelectorAll('td'));
          const a = tr.querySelector("a[onclick*='detalleCausaCivil']");
          const oc = a ? a.getAttribute('onclick') : '';
          const m = oc.match(/detalleCausaCivil\(['"]([^'"]+)['"]\)/);
          return {
            rol:        td[1] ? td[1].innerText.trim() : '',
            fecha:      td[2] ? td[2].innerText.trim() : '',
            caratulado: td[3] ? td[3].innerText.trim() : '',
            tribunal:   td[4] ? td[4].innerText.trim() : '',
            jwt:        m ? m[1] : '',
          };
        }).filter(r => r.rol)""")
    kept = [r for r in rows if r["rol"].upper().startswith("C") and r["jwt"]]
    log(f"[INFO] results: {len(rows)} rows, {len(kept)} kept (Rol starts 'C')")
    return kept


# ── Search by month (Búsqueda por Fecha) — DEFAULT mode ───────────────────────
#
# One date-range search per (corte, tribunal) returns ALL parties' causas in the
# window, so a single pass covers every bank (vs. the per-bank RUT sweep). We keep
# Rol-'C' rows whose Caratulado wildcard-matches a bank name and scrape them all
# (no procedure/RUT filter — that's done downstream in AppSheet). This also reveals
# each bank entity's real RUT (via its litigantes), to later fix the RUT search.

def _norm(s):
    """Uppercase + strip accents + collapse spaces (for caratulado/bank matching)."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).upper().strip()


# Distinctive Caratulado fragments per bank (curated; bare "CHILE" avoided).
BANK_FRAGMENTS = {
    "Banco de Chile":          ["BANCO DE CHILE"],
    "BCI":                     ["BANCO DE CREDITO E INVERSIONES", "BCI"],
    "Banco Santander-Chile":   ["SANTANDER"],
    "Scotiabank Chile":        ["SCOTIABANK"],
    "Banco Itaú Chile":        ["ITAU"],
    "Banco BICE":              ["BICE"],
    "Banco Internacional":     ["BANCO INTERNACIONAL"],
    "Banco Consorcio":         ["CONSORCIO"],
    "Banco Falabella":         ["FALABELLA"],
    "Banco Ripley":            ["RIPLEY"],
    "Banco BTG Pactual Chile": ["BTG PACTUAL"],
    "Coopeuch":                ["COOPEUCH"],
    "BancoEstado":             ["BANCOESTADO", "BANCO DEL ESTADO", "BANCO ESTADO"],
}
_GENERIC = {"BANCO", "DE", "DEL", "LA", "EL", "CHILE", "S.A.", "SA", "LTDA"}


def bank_fragments(banks):
    """Normalized fragment list from the active Bancos work-list; derives a
    distinctive token for any bank not in BANK_FRAGMENTS."""
    frags = []
    for b in banks:
        cand = BANK_FRAGMENTS.get(b["nombre"])
        if not cand:
            toks = [t for t in _norm(b["nombre"]).split() if t not in _GENERIC]
            cand = [" ".join(toks)] if toks else [_norm(b["nombre"])]
        frags.extend(_norm(c) for c in cand)
    return sorted({f for f in frags if f})


def matches_bank(caratulado, frags):
    c = _norm(caratulado)
    return any(f in c for f in frags)


def open_date_tab(page):
    """Activate 'Búsqueda por Fecha' and lock competencia = Civil."""
    try:
        page.wait_for_selector("a[href='#BusFecha']", timeout=30_000)
    except PlaywrightTimeout:
        try:
            title = page.title()
            anchors = page.eval_on_selector_all(
                "a[href^='#']", "els=>els.map(e=>e.getAttribute('href')).slice(0,20)")
            frames = [f.url[:70] for f in page.frames]
            body = (page.inner_text("body") or "")[:300].replace("\n", " ")
        except Exception:
            title = anchors = frames = body = "?"
        log(f"[DATE][FAIL] url={page.url} title={title!r}")
        log(f"[DATE][FAIL] tab-anchors={anchors}")
        log(f"[DATE][FAIL] frames={frames}")
        log(f"[DATE][FAIL] body[:300]={body!r}")
        raise
    page.wait_for_timeout(500)
    page.click("a[href='#BusFecha']")
    page.wait_for_timeout(800)
    _select(page, "#fecCompetencia", VAL_COMPETENCIA, "competencia(fecha)")
    page.wait_for_timeout(1500)   # corte list populates via AJAX


def date_form_alive(page):
    try:
        return page.eval_on_selector_all("#fecCompetencia", "e=>e.length") > 0
    except Exception:
        return False


def reopen_date(page, context):
    log("[NAV] date form missing — re-establishing guest session…")
    reach_search_form(page, context)
    open_date_tab(page)


def select_corte_fecha(page, corte_val, corte_name):
    _select(page, "#corteFec", corte_val, f"corte {corte_name}")
    page.wait_for_timeout(1800)   # #fecTribunal repopulates via AJAX
    return page.eval_on_selector_all(
        "#fecTribunal option",
        "els=>els.map(e=>({v:e.value,t:(e.textContent||'').trim()}))")


def _wait_fecha_results(page, max_ms=SEARCH_WAIT_MS):
    waited, step = 0, 600
    while waited < max_ms:
        n = page.eval_on_selector_all("#dtaTableDetalleFecha tbody tr", "e=>e.length")
        if n:
            page.wait_for_timeout(700)
            return True
        page.wait_for_timeout(step)
        waited += step
    return False


def _collect_fecha_page(page):
    return page.eval_on_selector_all(
        "#dtaTableDetalleFecha tbody tr",
        r"""els => els.map(tr => {
          const td = Array.from(tr.querySelectorAll('td'));
          const a = tr.querySelector("a[onclick*='detalleCausaCivil']");
          const oc = a ? a.getAttribute('onclick') : '';
          const m = oc.match(/detalleCausaCivil\(['"]([^'"]+)['"]\)/);
          return { rol: td[1]?td[1].innerText.trim():'',
                   fecha: td[2]?td[2].innerText.trim():'',
                   caratulado: td[3]?td[3].innerText.trim():'',
                   tribunal: td[4]?td[4].innerText.trim():'',
                   jwt: m?m[1]:'' };
        }).filter(r=>r.rol)""")


def _page_sig(page):
    """Signature of the current results page = first row's detail JWT (changes per
    page). Used to detect when the paginator AJAX has actually swapped the table."""
    return page.eval_on_selector(
        "#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']",
        "e=>e?e.getAttribute('onclick'):''") or ""


def _next_fecha_page(page):
    """Advance the paginator via 'Siguiente' (#sigId → paginaFecSig(JWT) AJAX).
    Returns True only once the table actually changes; False at the last page."""
    try:
        disabled = page.eval_on_selector(
            "#sigId",
            "e=>{const li=e.closest('li');return !!(li&&li.classList.contains('disabled'));}")
    except Exception:
        return False
    if disabled:
        return False
    before = _page_sig(page)
    try:
        page.eval_on_selector("#sigId", "e=>e.click()")
    except Exception as e:
        log(f"[WARN] pagination next: {e}")
        return False
    for _ in range(16):                 # poll up to ~8s for the AJAX swap
        page.wait_for_timeout(500)
        if _page_sig(page) not in ("", before):
            return True
    return False                        # no change → treat as last page


def search_month_paginated(page, trib_val, year, month):
    """Search one tribunal for one calendar month; return ALL rows across pages."""
    _select(page, "#fecTribunal", trib_val, "tribunal(fecha)")
    last = calendar.monthrange(year, month)[1]
    # #fecDesde/#fecHasta are readonly jQuery datepickers — page.fill() can't type
    # into them, so set the value via JS (strip readonly + dispatch change).
    page.evaluate(
        """([desde, hasta]) => {
            const set = (id, v) => { const e = document.getElementById(id);
                if (e) { e.removeAttribute('readonly'); e.value = v;
                         e.dispatchEvent(new Event('change', {bubbles: true})); } };
            set('fecDesde', desde); set('fecHasta', hasta);
        }""",
        [f"01/{month:02d}/{year}", f"{last:02d}/{month:02d}/{year}"])
    page.evaluate("() => { const t=document.querySelector('#dtaTableDetalleFecha tbody');"
                  " if(t)t.innerHTML=''; }")
    page.click("#btnConConsultaFec")
    if not _wait_fecha_results(page):
        page.wait_for_timeout(PACE_MS)
        return []
    by_rol, pages = {}, 0
    while pages < 60:
        for r in _collect_fecha_page(page):
            if r["rol"]:
                by_rol.setdefault(r["rol"], r)
        pages += 1
        if not _next_fecha_page(page):
            break
    page.wait_for_timeout(PACE_MS)
    return list(by_rol.values())


def _in_month(fecha, year, month):
    """True if results-row 'dd/mm/yyyy' falls in the requested year/month — a guard
    so we never store wrong-month causas even if the date search misbehaves."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", fecha or "")
    return bool(m) and int(m.group(3)) == year and int(m.group(2)) == month


def months_to_scan(args):
    """List of (year, month). --desde/--hasta (YYYY-MM) override; default = current
    year, January through the current month."""
    ny, nm = int(time.strftime("%Y")), int(time.strftime("%m"))

    def parse_ym(s):
        y, m = s.split("-")
        return int(y), int(m)

    if args.desde and args.hasta:
        y1, m1 = parse_ym(args.desde)
        y2, m2 = parse_ym(args.hasta)
    else:
        y1, m1, y2, m2 = ny, 1, ny, nm
    out, y, m = [], y1, m1
    while (y, m) <= (y2, m2):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# ── Detalle modal ─────────────────────────────────────────────────────────────

def open_detail(page, jwt):
    page.evaluate("j => detalleCausaCivil(j)", jwt)
    # Bootstrap modal is position:fixed (offsetParent null), so wait on its
    # content rather than visibility: the header ROL text appears after AJAX.
    page.wait_for_function(
        "() => { const m = document.querySelector('#modalDetalleCivil');"
        " return m && /ROL:/.test(m.innerText); }", timeout=15_000)
    page.wait_for_timeout(1200)


def parse_header(page):
    """Header fields from the (tab/newline-delimited) modal header text.
    Format: 'ROL: … F. Ing.: … <caratulado>' / 'Est. Adm.: … Proc.: … Ubicación: …'
            / 'Estado Proc.: … Etapa: … Tribunal: …'."""
    blob = page.inner_text("#modalDetalleCivil")

    def grab(pattern):
        m = re.search(pattern + r"\s*([^\t\n]+)", blob, re.I)
        return m.group(1).strip() if m else ""

    return {
        "f_ingreso":     grab(r"F\.\s*Ing\.?:"),
        "estado_adm":    grab(r"Est\.\s*Adm\.?:"),
        "procedimiento": grab(r"(?<!Estado )Proc\.?:"),
        "ubicacion":     grab(r"Ubicaci[oó]n:"),
        "estado_proc":   grab(r"Estado\s*Proc\.?:"),
        "etapa":         grab(r"Etapa:"),
    }


def grab_ebook(page):
    """Header ebook form (newebookcivil.php / input dtaEbook) → {action, val} or None."""
    info = page.eval_on_selector_all(
        "#modalDetalleCivil form[action*='newebookcivil']",
        "els=>els.slice(0,1).map(f=>({action:f.getAttribute('action')||'',"
        " val:(f.querySelector('input')||{}).value||''}))")
    return info[0] if info else None


def cuaderno_options(page):
    """[{txt, val}] of #selCuaderno; [] if absent."""
    try:
        return page.eval_on_selector_all(
            "#selCuaderno option",
            "els=>els.map(e=>({txt:(e.textContent||'').trim(), val:e.value}))")
    except Exception:
        return []


def select_cuaderno(page, index):
    """Switch cuaderno by option INDEX. The option `value` JWTs are regenerated
    per AJAX load, so selecting by stale value fails — index is stable."""
    try:
        page.select_option("#selCuaderno", index=index)
        page.wait_for_timeout(2200)  # historia AJAX-reloads
    except Exception as e:
        log(f"[WARN] selCuaderno idx {index}: {e}")


def parse_historia(page):
    """Rows of #historiaCiv: folio, doc form, anexo form, etapa, tramite, desc,
    fecha, foja, georref + the doc/anexo download descriptors."""
    return page.eval_on_selector_all(
        "#historiaCiv table tbody tr",
        r"""els => els.map(tr => {
          const td = Array.from(tr.querySelectorAll('td'));
          const cell = i => td[i] ? td[i].innerText.trim() : '';
          // doc form (Doc. cell, idx 1): action + dtaDoc value
          const docForm = td[1] ? td[1].querySelector('form') : null;
          const anexForm = td[2] ? td[2].querySelector('form') : null;
          const formInfo = f => {
            if (!f) return null;
            const inp = f.querySelector("input[name='dtaDoc'], input");
            return { action: f.getAttribute('action') || '',
                     val: inp ? inp.value : '' };
          };
          // Georref cell (idx 8): an <a onclick="geoReferencia('<JWT>')"> when present
          const geoA = td[8] ? td[8].querySelector("a[onclick*='geoReferencia']") : null;
          const gm = geoA ? (geoA.getAttribute('onclick') || '')
                              .match(/geoReferencia\(['"]([^'"]+)['"]\)/) : null;
          return {
            folio:   cell(0),
            doc:     formInfo(docForm),
            anexo:   formInfo(anexForm),
            etapa:   cell(3),
            tramite: cell(4),
            desc:    cell(5),
            fecha:   cell(6),
            foja:    cell(7),
            georref: cell(8),
            geo:     gm ? gm[1] : '',
          };
        })""")


def parse_litigantes(page):
    return page.eval_on_selector_all(
        "#litigantesCiv table tbody tr",
        r"""els => els.map(tr => {
          const td = Array.from(tr.querySelectorAll('td'));
          const c = i => td[i] ? td[i].innerText.trim() : '';
          return { participante: c(0), rut: c(1), persona: c(2), nombre: c(3) };
        }).filter(r => r.rut || r.nombre)""")


def parse_escritos(page):
    return page.eval_on_selector_all(
        "#escritosCiv table tbody tr",
        r"""els => els.map(tr => {
          const td = Array.from(tr.querySelectorAll('td'));
          const c = i => td[i] ? td[i].innerText.trim() : '';
          return { fecha_ingreso: c(2), tipo_escrito: c(3), solicitante: c(4) };
        }).filter(r => r.tipo_escrito || r.solicitante)""")


def close_overlay(page, sel):
    """Close a nested sub-modal (receptor / geo) without disturbing #modalDetalleCivil."""
    for s in (f"{sel} button.close", f"{sel} .close",
              f"{sel} button[data-dismiss='modal']"):
        try:
            page.click(s, timeout=1500)
            page.wait_for_timeout(400)
            return
        except Exception:
            pass
    try:                                # fallback: hide via the page's jQuery
        page.evaluate("s => { if (window.jQuery) jQuery(s).modal('hide'); }", sel)
    except Exception:
        pass
    page.wait_for_timeout(300)


# ── Notificaciones Receptor (causa-level sub-modal #modalReceptorCivil) ────────

def grab_receptor_jwt(page):
    """JWT from the header <a onclick="receptorCivil('<JWT>')">; '' if absent."""
    info = page.eval_on_selector_all(
        "#modalDetalleCivil a[onclick*='receptorCivil']",
        r"""els => els.slice(0,1).map(a => {
          const m = (a.getAttribute('onclick') || '')
                      .match(/receptorCivil\(['"]([^'"]+)['"]\)/);
          return m ? m[1] : '';
        })""")
    return info[0] if info and info[0] else ""


def open_receptor(page, jwt):
    page.evaluate("j => receptorCivil(j)", jwt)
    try:
        page.wait_for_function(
            "() => { const m = document.querySelector('#modalReceptorCivil');"
            " return m && (m.querySelector('table tbody tr') ||"
            " /Receptor/i.test(m.innerText)); }", timeout=10_000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(500)


def parse_receptor(page):
    """Rows of #modalReceptorCivil: Cuaderno | Datos del Retiro | Fecha Retiro | Estado."""
    return page.eval_on_selector_all(
        "#modalReceptorCivil table tbody tr",
        r"""els => els.map(tr => {
          const td = Array.from(tr.querySelectorAll('td'));
          const c = i => td[i] ? td[i].innerText.trim() : '';
          return { cuaderno: c(0), nombre: c(1), fecha: c(2), estado: c(3) };
        }).filter(r => r.nombre || r.cuaderno)""")


# ── Georreferencia (per-historia-row sub-modal #modalGeoReferenciaCivil) ───────

def open_geo(page, jwt):
    page.evaluate("j => geoReferencia(j)", jwt)
    page.wait_for_function(
        "() => { const m = document.querySelector('#modalGeoReferenciaCivil');"
        " const i = m && m.querySelector(\"input[name='latitud']\");"
        " return i && i.value; }", timeout=10_000)
    page.wait_for_timeout(300)


def grab_geo(page):
    """(latitud, longitud) from the geo modal's hidden inputs."""
    vals = page.eval_on_selector_all(
        "#modalGeoReferenciaCivil input[name='latitud'],"
        " #modalGeoReferenciaCivil input[name='longitud']",
        "els => els.map(e => ({ n: e.getAttribute('name'), v: e.value || '' }))")
    d = {x["n"]: x["v"] for x in vals}
    return d.get("latitud", ""), d.get("longitud", "")


def georref_hyperlink(lat, lng):
    """A simple clickable map cell: =HYPERLINK("…maps…", "lat, lng")."""
    if not lat or not lng:
        return ""
    label = f"{lat[:10]}, {lng[:10]}"
    url = f"https://maps.google.com/maps?ll={lat},{lng}&z=16"
    return f'=HYPERLINK("{url}","{label}")'


# ── Document download (GET in-session, share browser cookies) ─────────────────

def download_form(api, form, param="dtaDoc", quiet=False):
    """form = {action, val}. GET OJV/<action>?<param>=<val> with session cookies.
    Returns PDF bytes or None. `quiet` suppresses the non-PDF warning (ebook)."""
    if not form or not form.get("action") or not form.get("val"):
        return None
    action = form["action"].lstrip("/")
    url = f"{OJV}/{action}"
    try:
        resp = api.get(url, params={param: form["val"]}, timeout=60_000)
        body = resp.body()
        ct = (resp.headers or {}).get("content-type", "")
        if "pdf" not in ct.lower() and not body[:4] == b"%PDF":
            if not quiet:
                log(f"[WARN] {url} returned non-PDF (ct={ct!r}, {len(body)}B)")
            return None
        return body
    except Exception as e:
        log(f"[WARN] download {url}: {e}")
        return None


# ── Per-causa scrape ──────────────────────────────────────────────────────────

def _cuaderno_num(cuaderno_txt, fallback):
    """'1 - Principal' -> '1', '2 - Apremio…' -> '2'; else the 1-based fallback."""
    m = re.match(r"\s*(\d+)\s*-", cuaderno_txt or "")
    return m.group(1) if m else str(fallback)


def _first_date(s):
    """OJV 'Fec. Trámite' can carry two dates: '04/06/2026 (03/06/2026)'. Keep only
    the leading DD/MM/YYYY so the cell parses as a date downstream; else leave as-is."""
    m = re.match(r"\s*(\d{1,2}/\d{1,2}/\d{4})", s or "")
    return m.group(1) if m else (s or "")


def _paren_date(s):
    """The parenthetical diligencia date: '04/06/2026 (03/06/2026)' -> '03/06/2026'."""
    m = re.search(r"\((\d{1,2}/\d{1,2}/\d{4})\)", s or "")
    return m.group(1) if m else ""


def _close_detail(page):
    """Close #modalDetalleCivil so the next causa opens cleanly."""
    for sel in ("#modalDetalleCivil button.close", "#modalDetalleCivil .close", "body"):
        try:
            page.click(sel, timeout=1500)
            break
        except Exception:
            pass
    page.wait_for_timeout(600)


def scrape_causa(page, api, causa, tribunal):
    rol = causa["rol"]
    causa_id = f'{tribunal["id"]}-{rol}'
    log(f"\n[CAUSA] {tribunal['tribunal']} · {rol} — {causa['caratulado'][:50]}")
    open_detail(page, causa["jwt"])
    header = parse_header(page)

    # Procedure gate: only scrape causas whose Proc. matches PROC_FILTER exactly.
    if PROC_FILTER and _norm(header.get("procedimiento", "")) != _norm(PROC_FILTER):
        log(f"[SKIP] {rol}: proc={header.get('procedimiento', '')!r} ≠ {PROC_FILTER!r}")
        _close_detail(page)
        return
    # Skip administratively archived causas.
    if _norm(header.get("estado_adm", "")) == _norm("Archivada"):
        log(f"[SKIP] {rol}: estado_adm = Archivada")
        _close_detail(page)
        return
    # Skip concluded causas.
    if _norm(header.get("estado_proc", "")) == _norm("Concluido"):
        log(f"[SKIP] {rol}: estado_proc = Concluido")
        _close_detail(page)
        return

    # Ebook: header form newebookcivil.php (input dtaEbook). TODO: a plain
    # in-session GET returns HTML/0B — the ebook is generated server-side on form
    # submit (opens a target window). Left best-effort/empty until mapped; every
    # individual Historia doc is already downloaded, so the ebook is redundant.
    ebook_url = ""
    eb = None if SKIP_DOCS else grab_ebook(page)
    if eb and eb.get("val"):
        body = download_form(api, {"action": eb["action"], "val": eb["val"]}, quiet=True)
        if body:
            try:
                ebook_url = upload_pdf(
                    f"{causa_id}/ebook.pdf".replace(" ", "_"), body)
            except Exception as e:
                log(f"[WARN] ebook upload {rol}: {e}")

    upsert("pjud_causas", [{
        "causa_id": causa_id,
        "rol": rol,
        **header,
        "tribunal_id": tribunal["id"],
        "competencia": "Civil",
        "ebook": ebook_url,
        "updated_at": _now(),
    }])

    # Litigantes -> ruts + junction
    rut_rows, lit_rows = [], []
    for L in parse_litigantes(page):
        rut = norm_rut(L["rut"])
        if not rut:
            continue
        es_emp = "JUR" in (L["persona"] or "").upper()
        if es_emp:
            rut_rows.append({"rut": rut, "tipo": "empresa",
                             "razon_social": L["nombre"], "updated_at": _now()})
        else:
            nom, seg, apat, amat = split_persona(L["nombre"])
            rut_rows.append({"rut": rut, "tipo": "persona", "nombre": nom,
                             "segundo_nombre": seg, "ap_paterno": apat,
                             "ap_materno": amat, "updated_at": _now()})
        lit_rows.append({"id": f"{causa_id}-{rut}", "causa_id": causa_id, "rut": rut,
                         "participante": L["participante"], "updated_at": _now()})
    upsert("pjud_ruts", rut_rows)
    upsert("pjud_litigantes", lit_rows)

    cuads = cuaderno_options(page) or [{"txt": "1 - Principal", "val": ""}]
    # map a bare cuaderno name back to our numbered id ('Principal' -> '1 - Principal')
    bare2full = {}
    for opt in cuads:
        txt = opt["txt"]
        bare = txt.split(" - ", 1)[1].strip() if " - " in txt else txt
        bare2full[bare] = txt

    # Notificaciones Receptor — causa-level sub-modal #modalReceptorCivil
    notif_rows = []
    rjwt = grab_receptor_jwt(page)
    if rjwt:
        try:
            open_receptor(page, rjwt)
            for i, rr in enumerate(parse_receptor(page), 1):
                full = bare2full.get(rr["cuaderno"], rr["cuaderno"])
                notif_rows.append({
                    "id": f"{causa_id}-r{i}",
                    "Causa ID": causa_id,
                    "Cuaderno": full,
                    "Nombre": rr["nombre"], "Fecha": rr["fecha"],
                    "Estado": rr["estado"],
                })
            close_overlay(page, "#modalReceptorCivil")
        except Exception as e:
            log(f"[WARN] receptor {rol}: {e}")
    upsert("pjud_notificaciones", notif_rows)

    # Cuadernos (iterate selCuaderno) -> historia rows + docs/anexos
    cuad_rows, esc_rows, doc_rows, anex_rows = [], [], [], []
    for ci, opt in enumerate(cuads):
        cuaderno = opt["txt"]                       # readable name, e.g. "1 - Principal"
        cnum = _cuaderno_num(cuaderno, ci + 1)      # plain number for IDs, e.g. "1"
        if ci > 0:                      # cuaderno 0 is already loaded on open
            select_cuaderno(page, ci)
        seen = {}
        for h in parse_historia(page):
            folio = h["folio"]
            n = seen.get(folio, 0) + 1
            seen[folio] = n
            cid = f"{causa_id}-c{cnum}-{folio}-{n}"
            georref = h["georref"]
            if h.get("geo"):            # row has a map reference -> resolve coords
                try:
                    open_geo(page, h["geo"])
                    lat, lng = grab_geo(page)
                    close_overlay(page, "#modalGeoReferenciaCivil")
                    georref = georref_hyperlink(lat, lng) or georref
                except Exception as e:
                    log(f"[WARN] geo {rol} {cuaderno} folio {folio}: {e}")
            cuad_rows.append({
                "id": cid, "causa_id": causa_id, "cuaderno": cuaderno, "folio": folio,
                "etapa": h["etapa"], "tramite": h["tramite"],
                "descripcion_tramite": h["desc"],
                "fecha_tramite": _first_date(h["fecha"]),
                "fecha_diligencia": _paren_date(h["fecha"]),
                "foja": h["foja"], "georref": georref,
            })
            # documents on this row attach to THIS trámite row (cuaderno_id = cid)
            for kind, form, sink in (("doc", h["doc"], doc_rows),
                                     ("anexo", h["anexo"], anex_rows)):
                if not form or SKIP_DOCS:
                    continue
                body = download_form(api, form)
                if not body:
                    continue
                obj = f"{causa_id}/c{cnum}/{folio}-{n}-{kind}.pdf".replace(" ", "_")
                try:
                    url = upload_pdf(obj, body)
                except Exception as e:
                    log(f"[WARN] upload {obj}: {e}")
                    continue
                if kind == "doc":
                    sink.append({"id": f"{cid}-doc", "cuaderno_id": cid,
                                 "origen": form["action"], "folio": folio,
                                 "descripcion": h["desc"], "url": url})
                else:
                    sink.append({"id": f"{cid}-anexo", "cuaderno_id": cid,
                                 "origen": form["action"], "folio": folio,
                                 "fecha": h["fecha"], "referencia": h["desc"],
                                 "url": url})
        # escritos are cuaderno-level → FK the causa, keep cuaderno NAME as text
        for ei, e in enumerate(parse_escritos(page), 1):
            esc_rows.append({"id": f"{causa_id}-c{cnum}-e{ei}",
                             "causa_id": causa_id, "cuaderno": cuaderno, **e})

    upsert("pjud_cuadernos", cuad_rows)
    upsert("pjud_escritos", esc_rows)
    upsert("pjud_documentos", doc_rows)
    upsert("pjud_anexos", anex_rows)
    geo_n = sum(1 for c in cuad_rows if str(c.get("georref", "")).startswith("="))
    log(f"[CAUSA] {rol}: {len(cuad_rows)} historia, {len(lit_rows)} litigantes, "
        f"{len(notif_rows)} receptor, {geo_n} georref, {len(doc_rows)} docs, "
        f"{len(anex_rows)} anexos, {len(esc_rows)} escritos")

    _close_detail(page)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Date filter + work-list resolution ────────────────────────────────────────

def parse_fecha(f):
    """OJV results 'dd/mm/yyyy' (ingreso) -> ISO 'yyyy-mm-dd', or '' if unparseable."""
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", f or "")
    if not m:
        return ""
    d, mo, y = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def keep_causa(causa, start_date):
    """Causas are already C-rol filtered upstream. Keep only those ingresadas on or
    after start_date. Unparseable dates are kept (never silently drop a row)."""
    iso = parse_fecha(causa.get("fecha", ""))
    return (not iso) or (iso >= start_date)


def resolve_start_date(args, store):
    """The go-live anchor: only causas ingresadas on/after this date are stored.
    --since overrides; otherwise read (and on first run, set) config.start_date."""
    if args.since:
        return args.since
    cfg = (store.cfg if store else gstore.load_config()) or {}
    sd = cfg.get("start_date")
    if not sd:
        sd = time.strftime("%Y-%m-%d")
        if store:
            cfg["start_date"] = sd
            gstore.save_config(cfg)
            log(f"[INFO] start_date anchored to {sd} (saved to config)")
    return sd


def resolve_banks(args, store):
    """One bank from --rut, or every active row of the Bancos tab."""
    if args.rut:
        rut = re.sub(r"[.\-\s]", "", args.rut).strip()
        return [{"nombre": args.bank or rut, "rut": rut, "dv": args.dv.strip()}]
    if not store:
        raise SystemExit("[FATAL] no --rut and no Sheet (use --rut, or drop --dry-run).")
    banks = []
    for row in store.read_tab("Bancos"):
        activo = (row.get("activo", "") or "").strip().lower()
        if activo not in ("", "si", "sí", "yes", "true", "1"):
            continue
        rut = re.sub(r"[.\-\s]", "", row.get("rut", "")).strip()
        if rut:
            banks.append({"nombre": row.get("nombre") or rut, "rut": rut,
                          "dv": (row.get("dv", "") or "").strip()})
    if not banks:
        raise SystemExit("[FATAL] Bancos tab has no active rows.")
    return banks


# ── Main ──────────────────────────────────────────────────────────────────────

def expand_eras(spec):
    """'2024' -> ['2024']; '2018-2026' -> ['2018',...,'2026'] (the form requires a
    year, so a multi-year scrape is one search per year)."""
    spec = (spec or "").strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        return [str(y) for y in range(int(a), int(b) + 1)]
    return [spec] if spec else []


def parse_args():
    p = argparse.ArgumentParser(
        description="PJUD OJV civil scraper — finds Rol-'C' causas for the bank "
                    "entities in the Bancos tab. Default mode: search by month.")
    p.add_argument("--setup", action="store_true",
                   help="One-time: OAuth login + provision Drive/Sheet (+ Bancos tab), then exit.")
    p.add_argument("--list-banks", action="store_true",
                   help="Print active banks from the Bancos tab as JSON (for the CI matrix), then exit.")
    p.add_argument("--mode", choices=["month", "rut", "auto"], default="month",
                   help="Search strategy. 'month' (default) = Búsqueda por Fecha per "
                        "calendar month (all banks at once); 'rut' = per-bank RUT sweep; "
                        "'auto' = month, then rut on failure.")
    # month-mode range (default: Jan of current year → current month)
    p.add_argument("--desde", default="", help="Month mode: first month YYYY-MM.")
    p.add_argument("--hasta", default="", help="Month mode: last month YYYY-MM.")
    # rut-mode (single bank) options
    p.add_argument("--rut", default=None,
                   help="RUT sin dígito verificador for ONE bank. Omit to use all "
                        "active banks in the Bancos tab.")
    p.add_argument("--dv", default="", help="Dígito verificador (used with --rut).")
    p.add_argument("--bank", default="", help="Display name for --rut (logging only).")
    p.add_argument("--era", default="",
                   help="rut mode: año (#eraJur). Default = current year. '2026' or '2024-2026'.")
    p.add_argument("--since", default="",
                   help="rut mode: override start_date (ISO). Keep causas ingresadas on/after it.")
    # shared
    p.add_argument("--corte", default="",
                   help="Restrict sweep to one corte value (e.g. 10=Arica). Default = all 17.")
    p.add_argument("--max-tribunals", type=int, default=0,
                   help="Cap tribunals per corte (testing).")
    p.add_argument("--max-seconds", type=int, default=0,
                   help="Stop the sweep after N seconds (0 = no limit).")
    p.add_argument("--limit", type=int, default=0,
                   help="Max causas per tribunal/month (or /bank/era in rut mode); 0 = all.")
    p.add_argument("--headed", action="store_true", help="Show the browser.")
    p.add_argument("--dry-run", action="store_true",
                   help="Verify live nav/parse without any writes.")
    p.add_argument("--skip-docs", action="store_true",
                   help="Scrape metadata only — no PDF download/upload (fast).")
    p.add_argument("--proc", default="Ejecutivo Obligación de Dar",
                   help="Only scrape causas whose Proc. matches this exactly. "
                        "Pass '' to disable the filter.")
    return p.parse_args()


def sweep_month(page, api, context, banks, cortes, args):
    """Mode 'month' (default): per (corte, tribunal) run one Búsqueda por Fecha per
    calendar month, paginate fully, keep Rol-'C' rows whose Caratulado wildcard-
    matches a bank, and scrape every one (no procedure/RUT filter)."""
    frags = bank_fragments(banks)
    months = months_to_scan(args)
    deadline = (time.time() + args.max_seconds) if args.max_seconds else None
    log(f"[MONTH] frags={frags} months={months[0]}..{months[-1]} cortes={len(cortes)}")
    establish_form(page, context, "date")
    ok = total = 0
    for corte_val, corte_name in cortes:
        if deadline and time.time() > deadline:
            break
        if not date_form_alive(page):
            reopen_date(page, context)
        tribs = [(o["v"], o["t"]) for o in select_corte_fecha(page, corte_val, corte_name)
                 if o["v"] not in ("", "0")]
        if args.max_tribunals:
            tribs = tribs[:args.max_tribunals]
        log(f"[CORTE] {corte_name}: {len(tribs)} tribunales")
        for trib_val, trib_name in tribs:
            if deadline and time.time() > deadline:
                log("[INFO] max-seconds reached — stopping.")
                break
            tribunal = {"id": trib_val, "corte": corte_name, "tribunal": trib_name}
            seeded = False
            for (y, m) in months:
                try:
                    rows = search_month_paginated(page, trib_val, y, m)
                except Exception as e:
                    log(f"[WARN] month {trib_name} {y}-{m:02d}: {e}")
                    continue
                keep = [r for r in rows
                        if r["rol"].upper().startswith("C") and r["jwt"]
                        and _in_month(r["fecha"], y, m)
                        and matches_bank(r["caratulado"], frags)]
                log(f"[MONTH] {corte_name}/{trib_name} {y}-{m:02d}: "
                    f"{len(rows)} rows, {len(keep)} bank C-causas")
                if args.limit:
                    keep = keep[:args.limit]
                if keep and not seeded:
                    upsert("pjud_tribunales", [tribunal])
                    seeded = True
                for c in keep:
                    total += 1
                    try:
                        scrape_causa(page, api, c, tribunal)
                        ok += 1
                    except Exception as e:
                        log(f"[ERR] {trib_name} {c['rol']}: {e}")
    log(f"\n[DONE month] {ok}/{total} causas. cortes={len(cortes)} months={len(months)}.")


def sweep_rut(page, api, context, banks, cortes, args, start_date):
    """Mode 'rut': per (corte, tribunal) search each bank's RUT (Persona Jurídica),
    keep Rol-'C' causas ingresadas ≥ start_date. (Currently broken site-side.)"""
    eras = expand_eras(args.era or time.strftime("%Y"))
    deadline = (time.time() + args.max_seconds) if args.max_seconds else None
    log(f"[RUT] banks={[b['nombre'] for b in banks]} cortes={len(cortes)} "
        f"eras={eras} since={start_date}")
    establish_form(page, context, "rut")
    warm_up(page)
    ok = total = 0
    for corte_val, corte_name in cortes:
        if deadline and time.time() > deadline:
            break
        if not form_alive(page):
            reopen_form(page, context)
        tribs = [(o["v"], o["t"]) for o in select_corte(page, corte_val, corte_name)
                 if o["v"] not in ("", "0")]
        if args.max_tribunals:
            tribs = tribs[:args.max_tribunals]
        log(f"[CORTE] {corte_name}: {len(tribs)} tribunales")
        for trib_val, trib_name in tribs:
            if deadline and time.time() > deadline:
                log("[INFO] max-seconds reached — stopping.")
                break
            tribunal = {"id": trib_val, "corte": corte_name, "tribunal": trib_name}
            seeded = False
            for bank in banks:
                for era in eras:
                    try:
                        if not search_tribunal(page, trib_val, bank["rut"], bank["dv"], era):
                            continue
                        causas = [c for c in collect_causas(page)
                                  if keep_causa(c, start_date)]
                    except Exception as e:
                        log(f"[WARN] search {trib_name} {bank['nombre']} era {era}: {e}")
                        continue
                    if args.limit:
                        causas = causas[:args.limit]
                    if causas and not seeded:
                        upsert("pjud_tribunales", [tribunal])
                        seeded = True
                    for c in causas:
                        total += 1
                        try:
                            scrape_causa(page, api, c, tribunal)
                            ok += 1
                        except Exception as e:
                            log(f"[ERR] {trib_name} {c['rol']}: {e}")
    log(f"\n[DONE rut] {ok}/{total} causas. banks={len(banks)} cortes={len(cortes)}.")


def main():
    global STORE, DRY, SKIP_DOCS, PROC_FILTER
    args = parse_args()
    PROC_FILTER = args.proc

    if args.setup:
        cfg = gstore.provision()
        if not cfg.get("start_date"):
            cfg["start_date"] = time.strftime("%Y-%m-%d")
            gstore.save_config(cfg)
        log(f"[SETUP] start_date = {cfg['start_date']}. Run: python run.py")
        return

    if args.list_banks:
        print(json.dumps(resolve_banks(argparse.Namespace(rut=None, dv="", bank=""),
                                        gstore.Store()), ensure_ascii=False))
        return

    DRY = args.dry_run
    SKIP_DOCS = args.skip_docs
    if not DRY:
        STORE = gstore.Store()
    SCRATCH.mkdir(parents=True, exist_ok=True)

    start_date = resolve_start_date(args, STORE)
    banks = resolve_banks(args, STORE)
    cortes = [c for c in CORTES if (not args.corte or c[0] == args.corte)]
    order = {"month": ["month"], "rut": ["rut"], "auto": ["month", "rut"]}[args.mode]
    log(f"[INFO] mode={args.mode} -> {order}; banks={len(banks)} cortes={len(cortes)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
            locale="es-CL", accept_downloads=True,
            viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        api = context.request   # shares cookies → in-session PDF downloads

        for i, mname in enumerate(order):
            try:
                if mname == "month":
                    sweep_month(page, api, context, banks, cortes, args)
                else:
                    sweep_rut(page, api, context, banks, cortes, args, start_date)
                break
            except Exception as e:
                log(f"[MODE] '{mname}' failed: {e}")
                if i + 1 < len(order):
                    log(f"[MODE] falling back to '{order[i + 1]}'…")
                else:
                    raise
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
