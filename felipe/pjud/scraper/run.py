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
import random
import re
import subprocess
import sys
import unicodedata
import time
import unicodedata
import urllib.request
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

# Storage backend: Supabase/Postgres (default) or the legacy Google Sheets layer.
# Both expose the same surface; set PJUD_BACKEND=sheets to use the old one.
if os.environ.get("PJUD_BACKEND", "supabase").lower() == "sheets":
    import gstore
else:
    import dbstore as gstore

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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

SCRATCH = Path(os.environ.get("TEMP", "/tmp")) / "pjud_pdfs"

STORE = None       # gstore.Store, set in main() (None under --dry-run)
DRY = False        # --dry-run: verify live nav/parse without any writes
SKIP_DOCS = False  # --skip-docs: scrape metadata only, no PDF download/upload
PROC_FILTER = "Ejecutivo Obligación de Dar"  # only scrape causas whose Proc. == this
SKIP_GEO = False   # --skip-geo: don't resolve georref sub-modals (defer to a 2nd pass)
BANK_RUTS = set()  # normalized RUTs of target banks; demandante must be one of these
_BUFFER = {}       # tab -> {keyval: row}; bulk-flushed per tribunal (see flush_buffer)


def log(msg):
    print(msg, flush=True)


# ── Write layer: Google Sheet upsert + Drive PDF upload (via gstore) ──────────

def upsert(table, rows):
    """Buffer dict rows (keyed on column A) for a bulk flush. Turns ~9 Sheets API
    calls/causa into a few bulk writes per tribunal (see flush_buffer)."""
    if not rows:
        return 0
    if DRY or STORE is None:
        log(f"[DRY] upsert {table}: {len(rows)} row(s); sample={rows[0]}")
        return len(rows)
    tab = gstore.TABLE_TO_TAB.get(table, table)
    keycol = gstore.TABS[tab][0]
    buf = _BUFFER.setdefault(tab, {})
    for r in rows:
        k = str(r.get(keycol, "")).strip()
        if k:
            buf[k] = r            # last write wins (dedup within the buffer)
    return len(rows)


def flush_buffer():
    """Bulk-write everything buffered so far — one STORE.upsert per tab — then clear.
    STORE.upsert still does append-or-update keyed on column A, so this stays correct
    for re-runs; on a freshly-cleared DB it's pure bulk append."""
    if STORE is None or not _BUFFER:
        return
    total = 0
    for tab, d in list(_BUFFER.items()):
        if d:
            try:
                STORE.upsert(tab, list(d.values()))
                total += len(d)
            except Exception as e:
                log(f"[WARN] flush {tab}: {e}")
    _BUFFER.clear()
    if total:
        log(f"[FLUSH] {total} buffered rows written")


def upload_pdf(object_path, data):
    """Upload PDF bytes to the Drive Documentos folder, return its link.
    Guards against tiny/corrupt downloads."""
    if len(data) < 1024:
        raise RuntimeError(f"download too small ({len(data)}B) for {object_path}")
    if DRY or STORE is None:
        log(f"[DRY] upload {object_path} ({len(data)}B)")
        return f"DRY://{object_path}"
    return STORE.upload_pdf(object_path, data)


def upload_pdfs_parallel(items):
    """items: [(object_path, data)]. Returns {object_path: link}. Drive uploads run in
    parallel (the OJV fetch upstream stays sequential). Tiny/corrupt bytes are skipped."""
    if DRY or STORE is None:
        for p, d in items:
            log(f"[DRY] upload {p} ({len(d)}B)")
        return {p: f"DRY://{p}" for p, d in items}
    return STORE.upload_pdfs_parallel(items)


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


def establish_gentle(page, context, widx=0, captcha_wait_ms=300_000):
    """Headed, CAPTCHA-tolerant establish for gentle discovery. Navigates to the guest
    consulta; if the intermittent distorted-text CAPTCHA appears, WAITS (up to
    captcha_wait_ms) for the operator to solve it in the visible window, then opens the
    date tab. One manual solve per worker session; the session is then reused."""
    page.goto(HOME, wait_until="load", timeout=45_000)
    page.wait_for_timeout(2000)
    if page.evaluate("typeof accesoConsultaCausas === 'function'"):
        page.evaluate("accesoConsultaCausas()")
    log(f"[W{widx}] reaching guest form — if a CAPTCHA appears, SOLVE IT in this window…")
    waited, step = 0, 2000
    while waited < captcha_wait_ms:
        try:
            if page.query_selector("a[href='#BusFecha']"):
                break
        except Exception:
            pass
        page.wait_for_timeout(step)
        waited += step
    else:
        raise RuntimeError("date form never appeared (CAPTCHA left unsolved?)")
    open_date_tab(page)
    log(f"[W{widx}] guest form ready.")


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


# Distinctive Caratulado fragments keyed by bank RUT (stable, unlike the names).
# This is only a permissive PRE-FILTER to decide which causas to open; the precise
# filter is the demandante-RUT gate. Both Falabella entities share "FALABELLA" —
# the RUT gate separates them.
BANK_FRAGMENTS = {
    "97036000-k": ["SANTANDER"],
    "97030000-7": ["ESTADO DE CHILE", "BANCOESTADO", "BANCO DEL ESTADO"],
    "97023000-9": ["ITAU"],
    "97018000-1": ["SCOTIABANK"],
    "97011000-3": ["BANCO INTERNACIONAL"],
    "97006000-6": ["CREDITO E INVERSIONES", "BCI"],
    "97004000-5": ["BANCO DE CHILE"],
    "96509660-4": ["FALABELLA"],
    "90743000-6": ["FALABELLA"],
    "82878900-7": ["COOPEUCH"],
}
_GENERIC = {"BANCO", "DE", "DEL", "LA", "EL", "CHILE", "S.A", "S.A.", "SA",
            "LTDA", "CIA", "Y", "E"}


def bank_fragments(banks):
    """Normalized caratulado fragments for the active banks (keyed by RUT; derives a
    distinctive token for any bank not in BANK_FRAGMENTS)."""
    frags = []
    for b in banks:
        cand = BANK_FRAGMENTS.get(norm_rut(f"{b['rut']}-{b['dv']}"))
        if not cand:
            toks = [t for t in _norm(b.get("nombre", "")).split()
                    if t not in _GENERIC and len(t) > 2 and t.isalpha()]
            cand = [max(toks, key=len)] if toks else [_norm(b.get("nombre", ""))]
        frags.extend(_norm(c) for c in cand)
    return sorted({f for f in frags if f})


def matches_bank(caratulado, frags):
    c = _norm(caratulado)
    return any(f in c for f in frags)


def demandante_matches_bank(caratulado, frags):
    """True if a bank fragment appears in the DEMANDANTE slot — the part of the
    caratulado BEFORE the first '/' (caratulados are 'DEMANDANTE / DEMANDADO'). This
    keeps only causas where a bank is the plaintiff, cheaply, at the list level."""
    dte = (caratulado or "").split("/", 1)[0]
    return matches_bank(dte, frags)


# Gentle Pass-1 (guest-entry) pacing (randomized, human-like) vs the WAF's bot defense.
DISC_SEARCH_PACE = (4000, 10000)   # ms between tribunal/month searches
DISC_OPEN_PACE   = (2000, 6000)    # ms between detail-modal (header) opens
# Fill (Pass 2) runs inside the operator's established human session. Moderate pacing:
# lighter than guest-entry discovery, but NOT aggressive — the WAF re-flagged this IP
# under 3 concurrent windows, so single-window + this pacing is the safe envelope.
FILL_SEARCH_PACE = (2500, 6000)
FILL_OPEN_PACE   = (1200, 3500)


def _pace(lo_ms, hi_ms):
    time.sleep(random.uniform(lo_ms, hi_ms) / 1000.0)


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


def _fec_tribunal_opts(page):
    return page.eval_on_selector_all(
        "#fecTribunal option",
        "els=>els.map(e=>({v:e.value,t:(e.textContent||'').trim()}))")


def select_corte_fecha(page, corte_val, corte_name):
    """Select a corte and return its #fecTribunal options, WAITING for the AJAX
    cascade to actually populate. Under heavy parallel load the cascade is slow, so
    we poll until the option count is stable AND plausibly one corte (<100) — never
    the unfiltered ~230 national list (which caused cross-worker over-scan)."""
    for attempt in range(3):
        _select(page, "#corteFec", corte_val, f"corte {corte_name}")
        prev, stable = None, 0
        for _ in range(40):                       # up to ~20s
            page.wait_for_timeout(500)
            opts = _fec_tribunal_opts(page)
            n = len([o for o in opts if o["v"] not in ("", "0")])
            stable = stable + 1 if (n and n == prev) else 0
            prev = n
            if stable >= 2 and 0 < n < 100:       # settled to a single corte
                return opts
        log(f"[WARN] corte {corte_name}: tribunal list unsettled (n={prev}); "
            f"re-selecting (attempt {attempt + 1}/3)")
    return _fec_tribunal_opts(page)


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


_DEAD_SIGNS = ("Target crashed", "Connection closed", "Browser closed",
               "has been closed", "Target page, context or browser has been closed")


def _browser_dead(e):
    """True if the exception means the browser/driver died (not just a bad causa) —
    pointless to keep going in this process; let it exit so the tribunal is retried."""
    s = str(e)
    return any(sig in s for sig in _DEAD_SIGNS)


def _do_fecha_search(page, trib_val, year, month):
    """One search attempt for a (tribunal, month). Verifies the tribunal actually
    got selected (else searches the wrong one), fires, and collects all pages.
    Raises on a transient failure worth retrying; returns [] only for a real empty."""
    _select(page, "#fecTribunal", trib_val, "tribunal(fecha)")
    if page.eval_on_selector("#fecTribunal", "e => e.value") != trib_val:
        raise RuntimeError(f"tribunal {trib_val} not selected (cascade not ready)")
    last = calendar.monthrange(year, month)[1]
    # #fecDesde/#fecHasta are readonly jQuery datepickers — set value via JS.
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
    page.eval_on_selector("#btnConConsultaFec", "e=>e.click()")   # JS click (load-resilient)
    if not _wait_fecha_results(page):
        return []                                  # search fired, genuinely no rows
    by_rol, pages = {}, 0
    while pages < 60:
        for r in _collect_fecha_page(page):
            if r["rol"]:
                by_rol.setdefault(r["rol"], r)
        pages += 1
        if not _next_fecha_page(page):
            break
    return list(by_rol.values())


def search_month_paginated(page, trib_val, year, month):
    """Search one tribunal for one month, retrying transient failures so a flaky
    search (timeout / unsettled cascade) doesn't silently drop the tribunal."""
    for attempt in range(3):
        try:
            rows = _do_fecha_search(page, trib_val, year, month)
            page.wait_for_timeout(PACE_MS)
            return rows
        except Exception as e:
            if _browser_dead(e):
                raise               # dead browser → abort so this tribunal is retried
            log(f"[WARN] search trib {trib_val} {year}-{month:02d} "
                f"attempt {attempt + 1}/3: {e}")
            page.wait_for_timeout(1500)
    log(f"[WARN] search trib {trib_val} {year}-{month:02d}: gave up after 3 tries")
    return []


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

def open_detail(page, jwt, rol):
    # Capture the modal's current content; require it to CHANGE before reading, so a
    # stale modal is never parsed — even when consecutive causas share the same rol
    # (e.g. across a tribunal boundary), waiting for the rol alone wouldn't catch it.
    before = page.eval_on_selector("#modalDetalleCivil", "e => e ? e.innerText : ''")
    page.evaluate("j => detalleCausaCivil(j)", jwt)
    page.wait_for_function(
        "([rol, before]) => { const m = document.querySelector('#modalDetalleCivil');"
        " return m && m.innerText !== before && m.innerText.includes('ROL:')"
        " && m.innerText.includes(rol); }",
        arg=[rol, before], timeout=15_000)
    page.wait_for_timeout(800)


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
    """Close a nested sub-modal (receptor / geo) and VERIFY it's gone, without disturbing
    #modalDetalleCivil. Escalates until the modal is actually hidden: Bootstrap hide →
    close buttons → Escape → force-hide + clear the backdrop."""
    def is_open():
        try:
            return page.eval_on_selector(
                sel,
                "e => !!e && (e.classList.contains('show') || e.classList.contains('in')"
                " || getComputedStyle(e).display !== 'none')") or False
        except Exception:
            return False

    # 1) Bootstrap's own dismiss (most reliable — a stray .close click often doesn't take)
    try:
        page.evaluate("s => { if (window.jQuery) jQuery(s).modal('hide'); }", sel)
        page.wait_for_timeout(300)
    except Exception:
        pass
    # 2) close buttons — but keep going until it's actually gone
    if is_open():
        for s in (f"{sel} button.close", f"{sel} .close",
                  f"{sel} button[data-dismiss='modal']", f"{sel} [data-dismiss='modal']"):
            try:
                page.click(s, timeout=1000)
                page.wait_for_timeout(300)
                if not is_open():
                    break
            except Exception:
                pass
    # 3) Escape key
    if is_open():
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass
    # 4) last resort: force-hide this modal + clear any leftover backdrop
    if is_open():
        try:
            page.evaluate(
                "s => { const m = document.querySelector(s);"
                " if (m) { m.classList.remove('show','in'); m.style.display='none';"
                "          m.setAttribute('aria-hidden','true'); }"
                " document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());"
                " document.body.classList.remove('modal-open'); }", sel)
        except Exception:
            pass
    page.wait_for_timeout(250)


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


# ── the header ETAPA gate (operator, 2026-08-14) ─────────────────────────────
# Causas at these stages are not wanted at all: discard them the moment the modal renders its
# caratulado, BEFORE opening any cuaderno or buying any document. About 11% of what we already
# hold (505 of 4,460) is Terminada alone.
ETAPA_SKIP = (
    "terminada",
    "incidentes",
    "tengase por no presentada",
)


def etapa_rejected(etapa):
    """True if this header Etapa means 'do not bother with this causa'.

    ⚠️ MATCH THE LABEL, NOT THE STRING. Header etapas carry a leading ordinal — '1 Notificación
    demanda y su proveído', '8 Terminada' — and the numbering is BOTH sparse and unstable: the ten
    values in Neon run 0,1,2,3,4,5,6,7,8,12, and dbstore.FILL_SKIP_ETAPAS hardcodes '6 Terminada',
    which does not exist (6 is 'Impugnación de Sentencia'; Terminada is 8). That entry has been
    matching nothing since it was written. Stripping the ordinal fixes it and makes the rule work
    for 'Incidentes' whatever number it turns out to carry -- we have no example of it yet.

    ⚠️ FOLD ACCENTS AND CASE. The site mixes them freely ('NOTIFICACIÓN' vs 'Notificación'), and
    it abbreviates: the one instance in our data reads 'Téngase por no presentada la dda por
    apercibimiento' -- 'dda', not 'demanda'. An exact match on the full phrase finds nothing and
    reports the filter working perfectly, which is the worst possible failure.
    """
    if not etapa:
        return False
    s = unicodedata.normalize("NFKD", str(etapa)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^\s*\d+\s*", "", s).strip()
    return any(k in s for k in ETAPA_SKIP)


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


def scrape_causa(page, api, causa, tribunal, enforce_gates=True):
    rol = causa["rol"]
    causa_id = f'{tribunal["id"]}-{rol}'
    log(f"\n[CAUSA] {tribunal['tribunal']} · {rol} — {causa['caratulado'][:50]}")
    open_detail(page, causa["jwt"], rol)
    header = parse_header(page)

    # Discovery gates (Pass 1 only). In fill/Pass 2 (enforce_gates=False) we re-scrape
    # KNOWN causas regardless of current state — else a causa that concluded/was archived
    # since discovery would be skipped and never marked done (infinite retry).
    if enforce_gates:
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

    # Demandante gate: keep ONLY if a target-bank RUT is the demandante (DTE.).
    litigantes = parse_litigantes(page)
    if BANK_RUTS and not any(
            norm_rut(L["rut"]) in BANK_RUTS and "DTE" in (L["participante"] or "").upper()
            for L in litigantes):
        log(f"[SKIP] {rol}: demandante not a target bank")
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

    # Litigantes -> ruts + junction (already parsed for the demandante gate above)
    rut_rows, lit_rows = [], []
    for L in litigantes:
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
    pending_uploads = []          # (object_path, bytes, row) — Drive uploads batched below
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
            if h.get("geo") and not SKIP_GEO:   # resolve coords (skip in fast pass)
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
            # documents on this row attach to THIS trámite row (cuaderno_id = cid).
            # Fetch bytes from the OJV sequentially (gentle); the Drive upload is deferred
            # to a parallel batch after the loop (row["url"] filled in then).
            for kind, form, sink in (("doc", h["doc"], doc_rows),
                                     ("anexo", h["anexo"], anex_rows)):
                if not form or SKIP_DOCS:
                    continue
                body = download_form(api, form)
                if not body or len(body) < 1024:
                    continue
                obj = f"{causa_id}/c{cnum}/{folio}-{n}-{kind}.pdf".replace(" ", "_")
                if kind == "doc":
                    row = {"id": f"{cid}-doc", "cuaderno_id": cid,
                           "origen": form["action"], "folio": folio,
                           "descripcion": h["desc"], "url": ""}
                else:
                    row = {"id": f"{cid}-anexo", "cuaderno_id": cid,
                           "origen": form["action"], "folio": folio,
                           "fecha": h["fecha"], "referencia": h["desc"], "url": ""}
                sink.append(row)
                pending_uploads.append((obj, body, row))
        # escritos are cuaderno-level → FK the causa, keep cuaderno NAME as text
        for ei, e in enumerate(parse_escritos(page), 1):
            esc_rows.append({"id": f"{causa_id}-c{cnum}-e{ei}",
                             "causa_id": causa_id, "cuaderno": cuaderno, **e})

    # Parallel Drive upload of everything fetched for this causa, then fill in the URLs.
    if pending_uploads:
        urls = upload_pdfs_parallel([(obj, body) for obj, body, _ in pending_uploads])
        for obj, _, row in pending_uploads:
            row["url"] = urls.get(obj, "")

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


def _bank_ruts(banks):
    """Normalized RUTs ('digits-dv', lowercased) of the target banks."""
    return {norm_rut(f"{b['rut']}-{b['dv']}") for b in banks if b.get("rut")}


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
                   help="Restrict to corte value(s), comma-separated (e.g. 10 or 10,11,90). "
                        "Default = all 17.")
    p.add_argument("--workers", type=int, default=1,
                   help="Parallel worker subprocesses kept running by the dynamic pool "
                        "(default 1). They pull tribunal batches until the job is done.")
    p.add_argument("--batch", type=int, default=1,
                   help="(legacy) tribunals per --tasks job.")
    p.add_argument("--tasks", default="",
                   help="Internal: a worker's tribunal list 'corte:trib,corte:trib,…'.")
    p.add_argument("--pool-claim", default="",
                   help="Internal: long-lived worker — claim tribunals from this queue file.")
    p.add_argument("--worker-id", type=int, default=0, help="Internal: worker index.")
    p.add_argument("--discover", action="store_true",
                   help="Pass 1: gentle discovery (list + header filter) → DB (fill=false).")
    p.add_argument("--discover-worker", default="",
                   help="Internal: a discovery worker claiming (corte,month) units from this queue.")
    p.add_argument("--year", type=int, default=None,
                   help="Target year for --discover / --fill (default: current year).")
    p.add_argument("--fill", action="store_true",
                   help="Pass 2 (collaborative): full-scrape causas needing far data "
                        "(metadata refresh → docs + GPS) via date search per tribunal.")
    p.add_argument("--month", type=int, default=None,
                   help="Restrict --fill to a single month (1-12); default: all so far.")
    p.add_argument("--selected", action="store_true",
                   help="With --fill: only causas the user marked fill=true (else all).")
    p.add_argument("--skip-geo", action="store_true",
                   help="Don't resolve georref sub-modals (defer to a later pass) — big speed-up.")
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
            flush_buffer()          # bulk-write this tribunal's rows
    flush_buffer()
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
            flush_buffer()          # bulk-write this tribunal's rows
    flush_buffer()
    log(f"\n[DONE rut] {ok}/{total} causas. banks={len(banks)} cortes={len(cortes)}.")


def _new_context(browser, stealth=False):
    ctx = browser.new_context(user_agent=UA, locale="es-CL", accept_downloads=True,
                              viewport={"width": 1400, "height": 1000})
    if stealth:
        # Hide the most obvious automation tell so the WAF sees a normal browser.
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    return ctx


def enumerate_tribunals(cortes):
    """One browser session: list every (corte_val, trib_val) across the cortes.
    Run by the parent (no concurrency → the cascade is reliable) to build the task
    list that worker processes then split."""
    pairs = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = _new_context(browser)
        page = context.new_page()
        establish_form(page, context, "date")
        for cv, cname in cortes:
            opts = select_corte_fecha(page, cv, cname)
            tribs = [o["v"] for o in opts if o["v"] not in ("", "0")]
            log(f"[PLAN] {cname}: {len(tribs)} tribunales")
            pairs.extend((cv, tv) for tv in tribs)
        context.close()
        browser.close()
    return pairs


def sweep_tasks(page, api, context, banks, pairs, args):
    """Mode 'month', task-based: scrape an explicit list of (corte, tribunal) pairs
    (a worker's slice). Pairs are corte-grouped so the corte is reselected rarely."""
    frags = bank_fragments(banks)
    months = months_to_scan(args)
    cortemap = dict(CORTES)
    establish_form(page, context, "date")
    ok = total = 0
    cur_corte, trib_names = None, {}
    for cv, tv in pairs:
        if not date_form_alive(page):
            reopen_date(page, context)
            cur_corte = None
        if cv != cur_corte:
            opts = select_corte_fecha(page, cv, cortemap.get(cv, cv))
            trib_names = {o["v"]: o["t"] for o in opts}
            cur_corte = cv
        tribunal = {"id": tv, "corte": cortemap.get(cv, cv),
                    "tribunal": trib_names.get(tv, tv)}
        seeded = False
        for (y, m) in months:
            try:
                rows = search_month_paginated(page, tv, y, m)
            except Exception as e:
                log(f"[WARN] trib {tv} {y}-{m:02d}: {e}")
                continue
            keep = [r for r in rows
                    if r["rol"].upper().startswith("C") and r["jwt"]
                    and _in_month(r["fecha"], y, m)
                    and matches_bank(r["caratulado"], frags)]
            log(f"[TASK] corte {cv}/trib {tv} {y}-{m:02d}: {len(rows)} rows, {len(keep)} kept")
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
                    if _browser_dead(e):
                        raise           # browser died → exit non-zero so the pool retries
                    log(f"[ERR] trib {tv} {c['rol']}: {e}")
        flush_buffer()
    log(f"\n[DONE tasks] {ok}/{total} causas over {len(pairs)} tribunals.")


def _claim_next(queue_path):
    """Atomically pop the next tribunal from the shared queue file (lock-file spin).
    Returns (corte, trib) or None when empty."""
    lock = str(queue_path) + ".lock"
    qp = Path(queue_path)
    for _ in range(600):                       # spin up to ~60s for the lock
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            time.sleep(0.1)
            continue
        try:
            items = json.loads(qp.read_text(encoding="utf-8")) if qp.exists() else []
            if not items:
                return None
            item = items.pop(0)
            qp.write_text(json.dumps(items), encoding="utf-8")
            return tuple(item)
        finally:
            os.close(fd)
            os.unlink(lock)
    return None


def _requeue(queue_path, item):
    """Push a tribunal back (e.g. after a browser death) so it gets retried."""
    lock = str(queue_path) + ".lock"
    qp = Path(queue_path)
    for _ in range(600):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            time.sleep(0.1)
            continue
        try:
            items = json.loads(qp.read_text(encoding="utf-8")) if qp.exists() else []
            items.append(list(item))
            qp.write_text(json.dumps(items), encoding="utf-8")
            return
        finally:
            os.close(fd)
            os.unlink(lock)


def sweep_claim(args, banks, queue_path, widx):
    """Long-lived work-stealing worker: establish the session ONCE, then keep claiming
    tribunals from the shared queue and scraping each until the queue is empty. Setup
    is paid once per worker (not per tribunal). Self-heals: on a browser death it
    re-queues the current tribunal, relaunches a fresh browser, and continues."""
    frags = bank_fragments(banks)
    months = months_to_scan(args)
    cortemap = dict(CORTES)
    with sync_playwright() as pw:
        def fresh():
            b = pw.chromium.launch(headless=not args.headed)
            ctx = _new_context(b)
            pg = ctx.new_page()
            establish_form(pg, ctx, "date")
            return b, ctx, pg, ctx.request

        browser, context, page, api = fresh()
        cur_corte, trib_names, deaths = None, {}, 0
        while True:
            item = _claim_next(queue_path)
            if item is None:
                break
            cv, tv = item
            try:
                if not date_form_alive(page):
                    reopen_date(page, context)
                    cur_corte = None
                if cv != cur_corte:
                    trib_names = {o["v"]: o["t"]
                                  for o in select_corte_fecha(page, cv, cortemap.get(cv, cv))}
                    cur_corte = cv
                tribunal = {"id": tv, "corte": cortemap.get(cv, cv),
                            "tribunal": trib_names.get(tv, tv)}
                seeded = False
                for (y, m) in months:
                    rows = search_month_paginated(page, tv, y, m)
                    keep = [r for r in rows
                            if r["rol"].upper().startswith("C") and r["jwt"]
                            and _in_month(r["fecha"], y, m)
                            and matches_bank(r["caratulado"], frags)]
                    log(f"[W{widx}] corte {cv}/trib {tv} {y}-{m:02d}: "
                        f"{len(rows)} rows, {len(keep)} kept")
                    if args.limit:
                        keep = keep[:args.limit]
                    if keep and not seeded:
                        upsert("pjud_tribunales", [tribunal])
                        seeded = True
                    for c in keep:
                        try:
                            scrape_causa(page, api, c, tribunal)
                        except Exception as e:
                            if _browser_dead(e):
                                raise
                            log(f"[ERR] trib {tv} {c['rol']}: {e}")
                flush_buffer()
            except Exception as e:
                if _browser_dead(e):
                    deaths += 1
                    log(f"[W{widx}] browser died on trib {tv} (death {deaths}) — "
                        f"re-queue + relaunch")
                    _BUFFER.clear()                 # drop partial buffer for this tribunal
                    _requeue(queue_path, item)
                    try:
                        context.close()
                        browser.close()
                    except Exception:
                        pass
                    if deaths > 60:
                        log(f"[W{widx}] too many browser deaths — exiting")
                        break
                    browser, context, page, api = fresh()
                    cur_corte = None
                else:
                    log(f"[W{widx}] trib {tv} failed: {e}")
                    flush_buffer()
        try:
            context.close()
            browser.close()
        except Exception:
            pass
        log(f"[W{widx}] queue empty — done")


def _run_pool(args, cortes):
    """Parent: enumerate tribunals into a shared queue file, then spawn N long-lived
    work-stealing worker subprocesses (each establishes once, pulls tribunals until the
    queue drains). No re-establish per tribunal, no idle workers, crash-free model."""
    pairs = enumerate_tribunals(cortes)
    if not pairs:
        raise SystemExit("[FATAL] enumerated 0 tribunals")
    n = max(1, args.workers)
    SCRATCH.mkdir(parents=True, exist_ok=True)
    qpath = SCRATCH / "pjud_queue.json"
    qpath.write_text(json.dumps([list(p) for p in pairs]), encoding="utf-8")
    lock = str(qpath) + ".lock"
    if os.path.exists(lock):
        os.unlink(lock)
    for slot in range(n):
        (SCRATCH / f"pjud_worker_{slot}.log").write_text("", encoding="utf-8")
    log(f"[POOL] {len(pairs)} tribunals; {n} long-lived work-stealing workers")
    procs = []
    for i in range(n):
        cmd = [sys.executable, os.path.abspath(__file__), "--mode", args.mode,
               "--pool-claim", str(qpath), "--worker-id", str(i),
               "--workers", "1", "--proc", args.proc]
        if args.desde:
            cmd += ["--desde", args.desde]
        if args.hasta:
            cmd += ["--hasta", args.hasta]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        if args.skip_docs:
            cmd.append("--skip-docs")
        if args.skip_geo:
            cmd.append("--skip-geo")
        lf = open(SCRATCH / f"pjud_worker_{i}.log", "a", encoding="utf-8")
        procs.append((i, subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT), lf))
        time.sleep(3)               # stagger startup so N sessions don't hit OJV at once
    for i, p, lf in procs:
        p.wait()
        lf.close()
        log(f"[POOL] worker {i} exited {p.returncode}")
    log("[POOL] all workers done")
    try:
        removed = gstore.Store().dedup("Ruts")
        log(f"[DEDUP] Ruts: removed {removed} duplicate rows")
    except Exception as e:
        log(f"[WARN] dedup Ruts: {e}")


# ── Pass 1: gentle discovery (list + header filter; no far data) ───────────────

def _selected_cortes(args):
    if args.corte:
        want = {c.strip() for c in args.corte.split(",") if c.strip()}
        return [(v, n) for (v, n) in CORTES if v in want]
    return list(CORTES)


def discover_months(args, year):
    """Months of `year` to sweep: 1..12, but never past the current month."""
    now = time.localtime()
    last = now.tm_mon if year >= now.tm_year else 12
    return list(range(1, last + 1))


_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def _find_chrome():
    for p in _CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("Google Chrome not found (install it or fix _CHROME_CANDIDATES)")


def _launch_cdp_chrome(widx):
    """Launch a REAL Chrome (no automation flags → navigator.webdriver stays false, no
    WAF fingerprint) with a debug port + its own profile, opened on the OJV home. Returns
    (proc, port). We then drive it over CDP — exactly the manual setup that passes."""
    exe = _find_chrome()
    port = 9330 + widx
    profile = str(SCRATCH / f"chrome_disc_{widx}")
    proc = subprocess.Popen(
        [exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--no-first-run", "--no-default-browser-check", "--start-maximized", HOME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2)
            return proc, port
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"Chrome CDP endpoint never came up on :{port}")


def discover_unit(page, cv, cname, tv, tname, year, month, frags):
    """Sweep ONE (corte,tribunal,month): date-search → keep C- rows where a bank is the
    DEMANDANTE → open each modal for the HEADER ONLY → store if Ejecutivo OD & live.
    Returns (rows_seen, stored)."""
    rows = search_month_paginated(page, tv, year, month)
    tribunal = {"id": tv, "corte": cname, "tribunal": tname}
    stored, seeded = 0, False
    for r in rows:
        if not r["rol"].upper().startswith("C") or not r["jwt"]:
            continue
        if not _in_month(r["fecha"], year, month):
            continue
        if not demandante_matches_bank(r["caratulado"], frags):
            continue
        _pace(*DISC_OPEN_PACE)
        try:
            open_detail(page, r["jwt"], r["rol"])
            h = parse_header(page)
            _close_detail(page)
        except Exception as e:
            if _browser_dead(e):
                raise
            log(f"[ERR] header {tv} {r['rol']}: {e}")
            continue
        if _norm(h.get("procedimiento", "")) != _norm(PROC_FILTER):
            continue
        if _norm(h.get("estado_adm", "")) == _norm("Archivada"):
            continue
        if _norm(h.get("estado_proc", "")) == _norm("Concluido"):
            continue
        if not seeded:
            upsert("pjud_tribunales", [tribunal])
            seeded = True
        upsert("pjud_causas", [{
            "causa_id": f"{tv}-{r['rol']}", "rol": r["rol"], **h,
            "tribunal_id": tv, "competencia": "Civil", "ebook": "",
            "updated_at": _now(),
        }])
        stored += 1
    flush_buffer()
    return len(rows), stored


def discover_worker(args, banks, queue_path, widx):
    """One gentle, CAPTCHA-solved-once session that claims (corte,month) units and
    sweeps every tribunal it hasn't done yet (skips via sweep_progress). Self-heals on
    browser death (re-queue the unit + relaunch)."""
    frags = bank_fragments(banks)
    with sync_playwright() as pw:
        def fresh():
            # Real Chrome over CDP (no automation flags) — the setup proven to pass the
            # WAF. We attach to its existing tab (opened on HOME) and drive it.
            proc, port = _launch_cdp_chrome(widx)
            b = pw.chromium.connect_over_cdp(f"http://localhost:{port}")
            ctx = b.contexts[0]
            try:
                ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
            except Exception:
                pass
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            establish_gentle(pg, ctx, widx)
            return proc, b, ctx, pg

        def shutdown(proc, b):
            try:
                b.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass

        chrome_proc, browser, context, page = fresh()
        swept = STORE.swept_keys()
        cur_corte, tribmap, deaths = None, {}, 0
        while True:
            item = _claim_next(queue_path)
            if item is None:
                break
            cv, cname, yr, m = item
            try:
                if not date_form_alive(page):
                    reopen_date(page, context)
                    cur_corte = None
                if cv != cur_corte:
                    opts = select_corte_fecha(page, cv, cname)
                    tribmap = {o["v"]: o["t"] for o in opts if o["v"] not in ("", "0")}
                    cur_corte = cv
                for tv, tname in tribmap.items():
                    key = f"{cv}-{tv}-{yr}-{m:02d}"
                    if key in swept:
                        continue
                    n_rows, stored = discover_unit(page, cv, cname, tv, tname, yr, m, frags)
                    STORE.mark_swept(cv, tv, f"{yr}-{m:02d}")
                    swept.add(key)
                    log(f"[W{widx}] corte {cv}/trib {tv} {yr}-{m:02d}: "
                        f"{n_rows} rows, {stored} stored")
                    _pace(*DISC_SEARCH_PACE)
            except Exception as e:
                if _browser_dead(e):
                    deaths += 1
                    log(f"[W{widx}] browser died on corte {cv} {yr}-{m:02d} "
                        f"(death {deaths}) — re-queue + relaunch")
                    _BUFFER.clear()
                    _requeue(queue_path, item)
                    shutdown(chrome_proc, browser)
                    if deaths > 20:
                        log(f"[W{widx}] too many browser deaths — exiting")
                        break
                    chrome_proc, browser, context, page = fresh()
                    cur_corte = None
                    swept = STORE.swept_keys()
                else:
                    log(f"[W{widx}] corte {cv} {yr}-{m:02d} failed: {e}")
                    flush_buffer()
        shutdown(chrome_proc, browser)
        log(f"[W{widx}] queue empty — done")


def wait_for_consulta_form(page, timeout_ms=900_000):
    """Block until the OPERATOR has navigated past entry/CAPTCHA to the Consulta Causas
    page (the search tabs are present). This is the manual, human-in-the-loop step — we
    never auto-navigate the guest entry (that's what the WAF blocks)."""
    log("[COLLAB] >>> In the Chrome window: reach 'Consulta Causas' (solve any CAPTCHA). "
        "Waiting for the search form…")
    waited, step = 0, 2500
    while waited < timeout_ms:
        try:
            if page.query_selector("a[href='#BusFecha']"):
                log("[COLLAB] search form detected — taking over.")
                return
        except Exception:
            pass
        page.wait_for_timeout(step)
        waited += step
    raise RuntimeError("consulta form never appeared (operator step not completed)")


def try_recover_form(page, attempts=3, per_wait_ms=60_000):
    """On a dropped session, try to re-reach the consulta form automatically (re-run the
    guest entry). Returns True if the search form comes back within `attempts`. A CAPTCHA
    can't be auto-solved, so those attempts fail → the caller then waits for the operator."""
    for i in range(1, attempts + 1):
        log(f"[COLLAB] session dropped — auto-recover attempt {i}/{attempts}…")
        try:
            page.goto(HOME, wait_until="load", timeout=45_000)
            page.wait_for_timeout(2000)
            if page.evaluate("typeof accesoConsultaCausas === 'function'"):
                page.evaluate("accesoConsultaCausas()")
        except Exception as e:
            if _browser_dead(e):
                raise
            log(f"[COLLAB] recover nav failed: {e}")
        waited, step = 0, 2000
        while waited < per_wait_ms:
            try:
                if page.query_selector("a[href='#BusFecha']"):
                    log(f"[COLLAB] auto-recovered on attempt {i}.")
                    return True
            except Exception as e:
                if _browser_dead(e):
                    raise
            page.wait_for_timeout(step)
            waited += step
        log(f"[COLLAB] auto-recover attempt {i} did not reach the form (CAPTCHA/block?).")
    return False


def ensure_form_ready(page, cv, cname):
    """Make sure the date form is live and the given corte is selected. If the session
    dropped mid-sweep, first try to auto-recover (up to 3 re-navigations); only if that
    fails (a CAPTCHA/block it can't self-clear) do we wait for the operator. Returns the
    corte's {trib_val: trib_name} map."""
    if not date_form_alive(page):
        if not try_recover_form(page, attempts=3):
            log("[COLLAB] auto-recover exhausted — RESTORE Consulta Causas in the window "
                "(solve the CAPTCHA). Waiting for you…")
            wait_for_consulta_form(page)
        open_date_tab(page)
    opts = select_corte_fecha(page, cv, cname)
    return {o["v"]: o["t"] for o in opts if o["v"] not in ("", "0")}


def _collab_sweep(page, api, targets, cortemap, args):
    """Run the corte→tribunal→month→causa fill sweep on an established form. Raises on
    browser-death so the caller can relaunch; transient errors are handled inline."""
    filled, stop = 0, False
    for cv, tribmap in targets.items():
        if stop:
            break
        # Corte setup is transient-error-prone (a stray navigation destroys the execution
        # context). Retry up to 3×; skip the corte if it still fails (its causas stay
        # not-done → picked up on a re-run) — never crash over one blip.
        trib_names = None
        for setup_try in (1, 2, 3):
            try:
                trib_names = ensure_form_ready(page, cv, cortemap.get(cv, cv))
                break
            except Exception as e:
                if _browser_dead(e):
                    raise
                log(f"[COLLAB][ERR] corte {cv} setup try {setup_try}/3: {e}")
                page.wait_for_timeout(3000)
        if trib_names is None:
            log(f"[COLLAB] corte {cv} skipped after 3 setup failures.")
            continue
        for tv, permonth in tribmap.items():
            if stop:
                break
            tribunal = {"id": tv, "corte": cortemap.get(cv, cv),
                        "tribunal": trib_names.get(tv, tv)}
            for (yy, mm), rols in permonth.items():
                if stop:
                    break
                # Search; a tribunal we KNOW has targets that returns 0 (cascade hiccup)
                # → re-select the corte and retry (up to 2×).
                want, tries = {}, 0
                while True:
                    try:
                        if not date_form_alive(page):
                            trib_names = ensure_form_ready(page, cv, cortemap.get(cv, cv))
                            tribunal["tribunal"] = trib_names.get(tv, tv)
                        rows = search_month_paginated(page, tv, yy, mm)
                    except Exception as e:
                        if _browser_dead(e):
                            raise
                        log(f"[COLLAB][ERR] search {tv} {yy}-{mm:02d}: {e}")
                        rows = []
                    want = {r["rol"]: r for r in rows if r["rol"] in rols and r["jwt"]}
                    if want or tries >= 2:
                        break
                    tries += 1
                    log(f"[COLLAB] trib {tv} {yy}-{mm:02d}: 0/{len(rols)} matched — "
                        f"retry {tries} (re-select corte)")
                    trib_names = ensure_form_ready(page, cv, cortemap.get(cv, cv))
                    tribunal["tribunal"] = trib_names.get(tv, tv)
                log(f"[COLLAB] corte {cv}/trib {tv} {yy}-{mm:02d}: "
                    f"matched {len(want)}/{len(rols)}"
                    + ("  (!! still 0 after retries)" if rols and not want else ""))
                for rol, r in want.items():
                    _pace(*FILL_OPEN_PACE)
                    try:
                        scrape_causa(page, api, r, tribunal, enforce_gates=False)
                        STORE.mark_filled(f"{tv}-{rol}", "done")
                        filled += 1
                    except Exception as e:
                        if _browser_dead(e):
                            raise
                        log(f"[COLLAB][ERR] fill {tv}-{rol}: {e}")
                        STORE.mark_filled(f"{tv}-{rol}", "error")
                        _close_detail(page)
                    if args.limit and filled >= args.limit:
                        log(f"[COLLAB] --limit {args.limit} reached — stopping.")
                        stop = True
                        break
                flush_buffer()
                if stop:
                    break
                _pace(*FILL_SEARCH_PACE)


def scrape_collab(args):
    """Collaborative full scrape/fill over a REAL Chrome the operator drives past the
    entry/CAPTCHA. Targets causas that still need their far data (all not-'done', or only
    fill=true with --selected), grouped by corte→tribunal; for each we re-run the date
    search (fresh tokens), open ONLY the target rols, and full-scrape (metadata refresh →
    docs + GPS). Resumable via causas.fill_status; gentle randomized pacing."""
    global STORE, BANK_RUTS
    STORE = gstore.Store()
    banks = resolve_banks(args, STORE)
    BANK_RUTS = set()            # targeting known causas → skip the litigante demandante gate
    cortemap = dict(CORTES)
    name2corte = {n: v for (v, n) in CORTES}
    trib_corte = {r["id"]: r.get("corte", "") for r in STORE.read_tab("Tribunales")}

    # Targets grouped by corte → tribunal → (year, month) from each causa's f_ingreso, so
    # we only re-search months that contain causas. Re-built on each (re)launch, so a
    # relaunch after a window-close naturally skips whatever already got filled.
    want_cortes = {c.strip() for c in (args.corte or "").split(",") if c.strip()}

    def build_targets():
        tg, unmapped = {}, 0
        for causa_id, tv, rol, fing in STORE.fill_targets(only_selected=args.selected):
            iso = parse_fecha(fing)
            cv = name2corte.get(trib_corte.get(tv, ""), "")
            if not iso or not cv:
                unmapped += 1
                continue
            if want_cortes and cv not in want_cortes:
                continue
            yy, mm = int(iso[:4]), int(iso[5:7])
            if (args.year and yy != args.year) or (args.month and mm != args.month):
                continue
            tg.setdefault(cv, {}).setdefault(tv, {}).setdefault((yy, mm), set()).add(rol)
        return tg, unmapped

    with sync_playwright() as pw:
        deaths = 0
        while True:
            targets, unmapped = build_targets()
            n_causas = sum(len(rs) for tm in targets.values()
                           for pm in tm.values() for rs in pm.values())
            n_tribs = sum(len(tm) for tm in targets.values())
            log(f"[COLLAB] fill{'(selected)' if args.selected else ''}: {n_causas} causas · "
                f"{n_tribs} tribunals · {len(targets)} cortes"
                + (f" · {unmapped} unmapped(skipped)" if unmapped else ""))
            if not n_causas:
                log("[COLLAB] nothing to fill.")
                break

            proc, port = _launch_cdp_chrome(args.worker_id)
            b = pw.chromium.connect_over_cdp(f"http://localhost:{port}")
            ctx = b.contexts[0]
            page = next((p for p in ctx.pages if "pjud" in (p.url or "")),
                        ctx.pages[0] if ctx.pages else ctx.new_page())
            api = ctx.request
            try:
                wait_for_consulta_form(page)
                open_date_tab(page)
                _collab_sweep(page, api, targets, cortemap, args)
                log("[COLLAB] fill complete.")
                break
            except Exception as e:
                if not _browser_dead(e):
                    raise
                deaths += 1
                log(f"[COLLAB] window closed/crashed (death {deaths}) — relaunching; "
                    f"RE-NAVIGATE the new window to Consulta Causas.")
                if deaths > 8:
                    log("[COLLAB] too many window deaths — giving up.")
                    raise
            finally:
                try:
                    b.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                except Exception:
                    pass


def _run_fill_pool(args):
    """Parent for a multi-window fill: split the target cortes across N (≤3) worker
    windows (balanced by causa count), each a separate --fill child (own Chrome window +
    port) that the operator drives past entry/CAPTCHA. Runs when --fill --workers>1 with
    no explicit --corte."""
    from collections import Counter
    store = gstore.Store()
    name2corte = {n: v for (v, n) in CORTES}
    trib_corte = {r["id"]: r.get("corte", "") for r in store.read_tab("Tribunales")}
    counts = Counter()
    for causa_id, tv, rol, fing in store.fill_targets(only_selected=args.selected):
        iso = parse_fecha(fing)
        cv = name2corte.get(trib_corte.get(tv, ""), "")
        if not iso or not cv:
            continue
        yy, mm = int(iso[:4]), int(iso[5:7])
        if (args.year and yy != args.year) or (args.month and mm != args.month):
            continue
        counts[cv] += 1
    if not counts:
        log("[FILL-POOL] nothing to fill.")
        return
    n = max(1, min(args.workers, 3))
    bins, load = [[] for _ in range(n)], [0] * n
    for cv, _ in counts.most_common():          # greedy balance by causa count
        i = load.index(min(load))
        bins[i].append(cv)
        load[i] += counts[cv]
    bins = [(b, load[i]) for i, b in enumerate(bins) if b]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for i in range(len(bins)):
        (SCRATCH / f"pjud_fill_{i}.log").write_text("", encoding="utf-8")
    log(f"[FILL-POOL] {sum(counts.values())} causas / {len(counts)} cortes → {len(bins)} "
        f"windows: " + "; ".join(f"W{i}={load}" for i, (_, load) in enumerate(bins)))
    log("[FILL-POOL] each worker opens a Chrome window — navigate EACH past entry/CAPTCHA.")
    procs = []
    for i, (b, _) in enumerate(bins):
        cmd = [sys.executable, os.path.abspath(__file__), "--fill",
               "--corte", ",".join(b), "--worker-id", str(i), "--proc", args.proc]
        if args.year:
            cmd += ["--year", str(args.year)]
        if args.month:
            cmd += ["--month", str(args.month)]
        if args.selected:
            cmd.append("--selected")
        if args.skip_geo:
            cmd.append("--skip-geo")
        if args.skip_docs:
            cmd.append("--skip-docs")
        lf = open(SCRATCH / f"pjud_fill_{i}.log", "a", encoding="utf-8")
        procs.append((i, subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT), lf))
        time.sleep(8)          # stagger so the operator can navigate each window in turn
    for i, p, lf in procs:
        p.wait()
        lf.close()
        log(f"[FILL-POOL] worker {i} exited {p.returncode}")
    log("[FILL-POOL] all fill workers done")


def _run_discover(args):
    """Pass-1 parent: build (corte×month) units, spawn ≤3 gentle worker windows (each
    solves its CAPTCHA once), and let them claim units until the queue drains. Resumable
    via sweep_progress — re-running skips already-swept (corte,tribunal,month)."""
    year = args.year or time.localtime().tm_year
    cortes = _selected_cortes(args)
    months = discover_months(args, year)
    units = [[cv, cname, year, m] for (cv, cname) in cortes for m in months]
    n = max(1, min(args.workers, 3))
    SCRATCH.mkdir(parents=True, exist_ok=True)
    qpath = SCRATCH / "pjud_discover_queue.json"
    qpath.write_text(json.dumps(units), encoding="utf-8")
    lock = str(qpath) + ".lock"
    if os.path.exists(lock):
        os.unlink(lock)
    for slot in range(n):
        (SCRATCH / f"pjud_disc_{slot}.log").write_text("", encoding="utf-8")
    log(f"[DISCOVER] year {year}: {len(cortes)} cortes × {len(months)} months "
        f"= {len(units)} units; {n} gentle worker window(s)")
    log("[DISCOVER] each worker opens a Chrome window — SOLVE ITS CAPTCHA if one appears.")
    procs = []
    for i in range(n):
        cmd = [sys.executable, os.path.abspath(__file__),
               "--discover-worker", str(qpath), "--worker-id", str(i),
               "--year", str(year), "--proc", args.proc]
        if args.corte:
            cmd += ["--corte", args.corte]
        lf = open(SCRATCH / f"pjud_disc_{i}.log", "a", encoding="utf-8")
        procs.append((i, subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT), lf))
        time.sleep(6)      # stagger so the operator can solve each window's CAPTCHA
    for i, p, lf in procs:
        p.wait()
        lf.close()
        log(f"[DISCOVER] worker {i} exited {p.returncode}")
    log("[DISCOVER] all workers done")


def main():
    global STORE, DRY, SKIP_DOCS, PROC_FILTER, SKIP_GEO, BANK_RUTS
    args = parse_args()
    PROC_FILTER = args.proc
    SKIP_GEO = args.skip_geo

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

    # Pass-1 discovery worker (gentle, CAPTCHA-once): claim (corte,month) units.
    if args.discover_worker:
        STORE = gstore.Store()
        banks = resolve_banks(args, STORE)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        discover_worker(args, banks, args.discover_worker, args.worker_id)
        return

    # Pass-1 discovery parent: spawn the gentle worker window(s).
    if args.discover:
        _run_discover(args)
        return

    # Pass-2 collaborative fill (operator drives a real Chrome past entry/CAPTCHA).
    # --workers>1 with no explicit --corte → split cortes across N worker windows.
    if args.fill:
        if args.workers > 1 and not args.corte:
            _run_fill_pool(args)
        else:
            scrape_collab(args)
        return

    # Long-lived work-stealing worker: claim tribunals from the shared queue.
    if args.pool_claim:
        STORE = gstore.Store()
        banks = resolve_banks(args, STORE)
        BANK_RUTS = _bank_ruts(banks)
        SCRATCH.mkdir(parents=True, exist_ok=True)
        sweep_claim(args, banks, args.pool_claim, args.worker_id)
        return

    # Task worker: scrape an explicit list of (corte:trib) pairs (month mode).
    if args.tasks:
        pairs = [tuple(p.split(":", 1)) for p in args.tasks.split(",") if ":" in p]
        if not DRY:
            STORE = gstore.Store()
        SCRATCH.mkdir(parents=True, exist_ok=True)
        banks = resolve_banks(args, STORE)
        BANK_RUTS = _bank_ruts(banks)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed)
            context = _new_context(browser)
            page = context.new_page()
            api = context.request
            sweep_tasks(page, api, context, banks, pairs, args)
            context.close()
            browser.close()
        return

    sel = [x.strip() for x in (args.corte or "").split(",") if x.strip()]
    cortes = [c for c in CORTES if (not sel or c[0] in sel)]

    # Parent: work-stealing pool over all tribunals (self-heal on browser death).
    # Used for month mode at any worker count (≥1) so even a single worker gets the
    # re-queue/relaunch safety net for unattended runs.
    if args.mode == "month" and args.workers >= 1 and len(cortes) >= 1:
        _run_pool(args, cortes)
        return

    if not DRY:
        STORE = gstore.Store()
    SCRATCH.mkdir(parents=True, exist_ok=True)

    start_date = resolve_start_date(args, STORE)
    banks = resolve_banks(args, STORE)
    BANK_RUTS = _bank_ruts(banks)
    order = {"month": ["month"], "rut": ["rut"], "auto": ["month", "rut"]}[args.mode]
    log(f"[INFO] mode={args.mode} -> {order}; banks={len(banks)} cortes={len(cortes)}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = _new_context(browser)
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
