"""Attach to an ALREADY-RUNNING Chrome (debug port) and scrape OJV with REAL clicks (CDP).

The operator has, in that Chrome: passed the CAPTCHA, opened "Busqueda por Fecha", and set
Competencia=Civil + Corte + Fechas (Tribunales list showing). This connects over CDP and,
using trusted clicks (page.click -> isTrusted=true), walks every tribunal of the corte,
paginates the results, and opens each bank C-causa to scrape the full detail:
header, litigantes, all cuadernos + historia rows (incl. doc/anexo links + georref text),
escritos, and receptor. Writes ONE JSON to Downloads. Human, randomized pacing throughout.

Run:  python cdp_scrape.py [--port 9333] [--max-tribs 0] [--max-causas 0] [--proc ""]
      (0 = no limit)  --proc "Ejecutivo Obligación de Dar" filters by procedimiento.
"""

import argparse
import base64
import json
import math
import os
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

DOWNLOADS = Path(os.environ.get("USERPROFILE", ".")) / "Downloads"
OJV = "https://oficinajudicialvirtual.pjud.cl"

DOCS = False    # --docs: download historia doc/anexo PDFs and upload to Drive
DOCS_INPAGE = False  # --docs-inpage: fetch those PDFs from INSIDE the page (see fetch_doc)
GPS = False     # --gps: resolve georreferencia sub-modals to lat/lng
RESUME = False  # --resume: skip causas already scraped (fill_status='scraped') in Neon
COUNT_ONLY = False  # --count-only: count bank C-causas per tribunal, no detail opens
_STORE = None   # dbstore.Store (Drive uploads + Neon), lazy-initialised

BANK = ['SANTANDER', 'ESTADO DE CHILE', 'BANCOESTADO', 'BANCO DEL ESTADO', 'ITAU',
        'SCOTIABANK', 'BANCO INTERNACIONAL', 'CREDITO E INVERSIONES', 'BCI',
        'BANCO DE CHILE', 'FALABELLA', 'COOPEUCH', 'BICE', 'CONSORCIO', 'RIPLEY', 'BTG']

# ── pacing (human, randomized) — GENTLE: OJV rate-throttles even trusted CDP traffic,
#    so keep it slow (in the ballpark of run.py's gentle discovery mode). ────────────
P_CAUSA = (5.0, 10.0)   # before opening each causa
P_PAGE  = (4.0, 8.0)    # between result pages
P_TRIB  = (6.0, 12.0)   # between tribunales
P_STEP  = (0.6, 1.6)    # small pauses inside a causa (cuaderno switches, receptor)


def pace(rng):
    time.sleep(random.uniform(*rng))


def _human_pointer(page, x, y):
    """Drive the pointer to (x,y) along an ARC with easing and jitter, dwell, then press."""
    sx, sy = x - random.uniform(180, 320), y + random.uniform(90, 200)
    page.mouse.move(sx, sy)
    page.wait_for_timeout(random.randint(60, 140))
    steps = random.randint(18, 28)
    bow = random.uniform(-38, 38)                        # perpendicular bulge -> a curve
    for i in range(1, steps + 1):
        t = i / steps
        ease = t * t * (3 - 2 * t)                       # slow start, fast middle, slow end
        arc = math.sin(math.pi * t) * bow
        page.mouse.move(sx + (x - sx) * ease + arc + random.uniform(-1.2, 1.2),
                        sy + (y - sy) * ease + random.uniform(-1.2, 1.2))
        page.wait_for_timeout(random.randint(8, 22))
    page.mouse.move(x + random.uniform(-1.5, 1.5), y + random.uniform(-1.5, 1.5))
    page.wait_for_timeout(random.randint(140, 380))      # hover dwell before committing
    page.mouse.down()
    page.wait_for_timeout(random.randint(55, 130))       # press duration
    page.mouse.up()


def page_busy(page):
    """True while the site is mid-request. It injects a spinner into #loadPre* (empty when
    idle) — the loading icon the operator watches on screen. Judging 'ready' by the results
    table is useless: it keeps showing the PREVIOUS search's rows while the new one runs."""
    try:
        return bool(page.evaluate(
            "()=>['loadPre','loadPreFecha','loadPreNombre','loadPreJuridica']"
            " .some(id=>{const e=document.getElementById(id);"
            "  return e && e.offsetParent!==null && e.innerHTML.trim().length>0;})"))
    except Exception:
        return False


def wait_idle(page, secs=20):
    """Block until the site stops loading. Acting while it is busy is what got workers 2 and 3
    F5-blocked on 2026-07-22: under three-worker latency the script clicked before the page was
    ready, the click landed on a backdrop or a stale row, and Shape scored the impossible
    interaction. Cheap insurance — returns as soon as the spinner clears."""
    for _ in range(secs * 4):
        if not page_busy(page):
            return True
        page.wait_for_timeout(250)
    return False


def human_click(page, target, timeout=8000):
    """THE click. `target` is a selector, Locator or ElementHandle.

    NEVER use page.click()/locator.click() on this site. Both are isTrusted=true, but they
    TELEPORT the pointer onto the element and fire down+up with no approach path and no hover
    dwell — and F5 Shape scores the motion, not the trust bit. Validated 2026-07-22 on one
    healthy session, same button, same POST params, minutes apart:
        page.click  -> 250 B rejection page in 0.1s
        human arc   -> 109,234 B of real results
    Reading the DOM over CDP (Runtime.evaluate) was tested in the same session and is INNOCENT,
    so parse_*/eval_on_selector everywhere else are fine — it is only the pointer that matters.
    Falls back to a plain click if the element has no measurable box (better than not clicking).
    """
    el = page.locator(target) if isinstance(target, str) else target
    box = None
    try:
        el.scroll_into_view_if_needed(timeout=timeout)
    except Exception:
        pass
    try:
        box = el.bounding_box()
    except Exception:
        box = None
    if not box or box.get("width", 0) < 1 or box.get("height", 0) < 1:
        try:
            el.click(timeout=timeout)                    # last resort — may be scored
            return True
        except Exception:
            return False

    # We drive raw mouse coordinates, so we lose Playwright's actionability check: if a
    # backdrop or sticky header covers the point, the press lands on the overlay instead.
    # Hit-test it ourselves (Runtime.evaluate is proven safe here) and re-measure if it misses.
    wait_idle(page)                                      # never act while the site is loading

    # NEVER click a covered target. The old fallback ("click anyway") sent a real click to
    # whatever sat underneath — a backdrop, a stale row — at coordinates where the intended
    # element was not. On 2026-07-22 that correlated perfectly with getting F5-blocked:
    # 0 covered clicks -> survived 50 causas; 1 -> blocked at 23; 2 -> blocked at 4.
    x = y = None
    covered = False
    for attempt in range(8):
        x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        try:
            hit = el.evaluate(
                "(e, pt) => {const top = document.elementFromPoint(pt[0], pt[1]);"
                " return !!top && (top === e || e.contains(top) || top.contains(e));}", [x, y])
        except Exception:
            break                                        # can't hit-test (iframe etc.) — go
        if hit:
            covered = False
            break
        covered = True
        page.wait_for_timeout(1000)                      # give slow renders time to settle
        if attempt == 2:
            clear_stuck_modal(page)                      # usually a left-open modal's backdrop
        wait_idle(page)
        try:
            el.scroll_into_view_if_needed(timeout=timeout)
            box = el.bounding_box() or box
        except Exception:
            pass
    if covered:
        print("    [warn] human_click: objetivo tapado tras 8s — NO hago clic (evita el bloqueo)")
        return False

    try:
        _human_pointer(page, x, y)
        return True
    except Exception as e:
        print(f"    [warn] human_click: {str(e)[:60]}")
        return False


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).upper().strip()


def is_bank(caratulado):
    return any(f in norm(caratulado) for f in BANK)


def grab(blob, pat):
    m = re.search(pat + r"\s*([^\t\n]+)", blob, re.I)
    return m.group(1).strip() if m else ""


# ── parsers (ported from run.py) ─────────────────────────────────────────────

def parse_header(page):
    b = page.inner_text("#modalDetalleCivil")
    return {
        "f_ingreso":    grab(b, r"F\.\s*Ing\.?:"),
        "estado_adm":   grab(b, r"Est\.\s*Adm\.?:"),
        "procedimiento": grab(b, r"(?<!Estado )Proc\.?:"),
        "ubicacion":    grab(b, r"Ubicaci[oó]n:"),
        "estado_proc":  grab(b, r"Estado\s*Proc\.?:"),
        "etapa":        grab(b, r"Etapa:"),
    }


def parse_litigantes(page):
    return page.eval_on_selector_all(
        "#litigantesCiv table tbody tr",
        r"""els => els.map(tr => { const td = Array.from(tr.querySelectorAll('td'));
              const c = i => td[i] ? td[i].innerText.trim() : '';
              return {participante:c(0), rut:c(1), persona:c(2), nombre:c(3)}; })
            .filter(r => r.rut || r.nombre)""")


def parse_escritos(page):
    return page.eval_on_selector_all(
        "#escritosCiv table tbody tr",
        r"""els => els.map(tr => { const td = Array.from(tr.querySelectorAll('td'));
              const c = i => td[i] ? td[i].innerText.trim() : '';
              return {fecha_ingreso:c(2), tipo_escrito:c(3), solicitante:c(4)}; })
            .filter(r => r.tipo_escrito || r.solicitante)""")


def cuaderno_options(page):
    try:
        return page.eval_on_selector_all(
            "#selCuaderno option",
            "els=>els.map(e=>({txt:(e.textContent||'').trim(), val:e.value}))")
    except Exception:
        return []


def select_cuaderno(page, index):
    try:
        page.select_option("#selCuaderno", index=index)
        page.wait_for_timeout(1600)   # historia reloads via AJAX
    except Exception as e:
        print(f"      [warn] selCuaderno {index}: {e}")


def parse_historia(page):
    return page.eval_on_selector_all(
        "#historiaCiv table tbody tr",
        r"""els => els.map(tr => {
              const td = Array.from(tr.querySelectorAll('td'));
              const cell = i => td[i] ? td[i].innerText.trim() : '';
              const formInfo = f => { if(!f) return null;
                  const inp = f.querySelector("input[name='dtaDoc'], input");
                  return { action: f.getAttribute('action')||'', val: inp?inp.value:'' }; };
              const docForm  = td[1] ? td[1].querySelector('form') : null;
              const anexForm = td[2] ? td[2].querySelector('form') : null;
              const geoA = td[8] ? td[8].querySelector("a[onclick*='geoReferencia']") : null;
              const gm = geoA ? (geoA.getAttribute('onclick')||'')
                                  .match(/geoReferencia\(['"]([^'"]+)['"]\)/) : null;
              return { folio: cell(0), doc: formInfo(docForm), anexo: formInfo(anexForm),
                  etapa: cell(3), tramite: cell(4), desc: cell(5), fecha: cell(6),
                  foja: cell(7), georref: cell(8), geo: gm ? gm[1] : '' }; })""")


# ── modals (open/close with REAL clicks) ─────────────────────────────────────

def modal_open(page, sel):
    try:
        return bool(page.eval_on_selector(
            sel, "e => e && (e.classList.contains('show')||e.classList.contains('in')"
                 " || getComputedStyle(e).display!=='none')"))
    except Exception:
        return False


def close_modal(page, sel):
    for s in (f"{sel} .modal-header .close", f"{sel} button.close",
              f"{sel} [data-dismiss='modal']"):
        try:
            if page.query_selector(s):
                human_click(page, s, timeout=2000)     # human arc — never page.click()
                page.wait_for_timeout(500)
                if not modal_open(page, sel):
                    return
        except Exception:
            pass
    page.wait_for_timeout(300)


def clear_stuck_modal(page):
    """Make sure no detail/receptor modal is left open. Returns True if the page is clean.

    THE failure mode of 2026-07-22: one causa open goes wrong (slow response, or F5 renders a
    rejection page INTO the modal iframe) and the modal never closes. Every later open then
    times out at 30 s, because the script waits for a NEW modal to show the next ROL while the
    dead one is still sitting there — so a single hiccup looked exactly like a burned profile
    for the rest of the run, and waf_check read the trapped rejection page and said
    BLOCKED-DETAIL. The operator proved it by hand: close the modal (or reload) and everything
    works again. Escape first — it is a trusted keystroke and costs nothing."""
    for sel in ("#modalReceptorCivil", "#modalDetalleCivil"):
        if not modal_open(page, sel):
            continue
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        except Exception:
            pass
        if modal_open(page, sel):
            close_modal(page, sel)
        if modal_open(page, sel):
            try:                      # last resort: the site's own hide, then Escape again
                page.evaluate("s=>{const m=document.querySelector(s);"
                              " if(m&&window.jQuery) window.jQuery(m).modal('hide');}", sel)
                page.wait_for_timeout(500)
            except Exception:
                pass
        if modal_open(page, sel):
            print(f"      [warn] {sel} sigue abierto — la pagina esta atascada")
            return False
    return True


def parse_receptor(page):
    a = page.query_selector("#modalDetalleCivil a[onclick*='receptorCivil']")
    if not a:
        return []
    try:
        human_click(page, a, timeout=5000)             # human arc — never .click()
        page.wait_for_function(
            "()=>{const m=document.querySelector('#modalReceptorCivil');"
            " return m && (m.querySelector('table tbody tr')||/Receptor/i.test(m.innerText));}",
            timeout=10000)
        page.wait_for_timeout(400)
        rows = page.eval_on_selector_all(
            "#modalReceptorCivil table tbody tr",
            r"""els=>els.map(tr=>{const td=Array.from(tr.querySelectorAll('td'));
                  const c=i=>td[i]?td[i].innerText.trim():'';
                  return {cuaderno:c(0), nombre:c(1), fecha:c(2), estado:c(3)};})
                .filter(r=>r.nombre||r.cuaderno)""")
        close_modal(page, "#modalReceptorCivil")
        return rows
    except Exception:
        try:
            close_modal(page, "#modalReceptorCivil")
        except Exception:
            pass
        return []


def _cuaderno_num(txt):
    m = re.match(r"\s*(\d+)\s*-", txt or "")
    return m.group(1) if m else "1"


def get_store():
    """Lazy dbstore.Store() for Drive uploads (built only when --docs). Reuses the
    proven Drive upload_pdf path (documentos folder + flattened names)."""
    global _STORE
    if _STORE is None:
        import dbstore
        _STORE = dbstore.Store()
    return _STORE


def resolve_geo(page, jwt):
    """Open the georreferencia sub-modal for `jwt`, read lat/lng, close. Returns a
    =HYPERLINK(...) cell or ''. Uses the site's own geoReferencia() (in-session)."""
    try:
        page.evaluate("j => geoReferencia(j)", jwt)
        page.wait_for_function(
            "()=>{const m=document.querySelector('#modalGeoReferenciaCivil');"
            " const i=m&&m.querySelector(\"input[name='latitud']\"); return i&&i.value;}",
            timeout=8000)
        page.wait_for_timeout(200)
        vals = page.eval_on_selector_all(
            "#modalGeoReferenciaCivil input[name='latitud'],"
            " #modalGeoReferenciaCivil input[name='longitud']",
            "els=>els.map(e=>({n:e.getAttribute('name'), v:e.value||''}))")
        d = {x["n"]: x["v"] for x in vals}
        lat, lng = d.get("latitud", ""), d.get("longitud", "")
        close_modal(page, "#modalGeoReferenciaCivil")
        if lat and lng:
            return (f'=HYPERLINK("https://maps.google.com/maps?ll={lat},{lng}&z=16",'
                    f'"{lat[:10]}, {lng[:10]}")')
    except Exception:
        try:
            close_modal(page, "#modalGeoReferenciaCivil")
        except Exception:
            pass
    return ""


def download_doc(api, action, val, param="dtaDoc"):
    """GET OJV/<action>?<param>=<val> in-session (shares cookies) -> PDF bytes or None.

    NB this goes out through Playwright's APIRequestContext — it shares cookies but is issued
    OUTSIDE the page, so it carries none of the browser's request context and produces no F5
    Shape telemetry. Suspected (not proven) of burning the profile in the detail regime; see
    `download_doc_inpage` for the alternative and `--docs-inpage` to A/B them."""
    if not action or not val:
        return None
    try:
        resp = api.get(f"{OJV}/{action.lstrip('/')}", params={param: val}, timeout=60000)
        body = resp.body()
        ct = (resp.headers or {}).get("content-type", "")
        if "pdf" not in ct.lower() and body[:4] != b"%PDF":
            return None
        return body
    except Exception:
        return None


# In-page fetch: same URL, but issued BY the page, so it inherits the document's origin,
# referer and cookie handling and lands inside Shape's instrumented XHR path instead of
# beside it. Bytes come back base64 (chunked so a big ebook doesn't blow the argument stack).
_JS_FETCH_DOC = """
async ([url, param, val]) => {
  const u = url + '?' + param + '=' + encodeURIComponent(val);
  const r = await fetch(u, {credentials: 'include'});
  if (!r.ok) return null;
  const bytes = new Uint8Array(await r.arrayBuffer());
  let s = '', CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH)
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  return btoa(s);
}
"""


def download_doc_inpage(page, action, val, param="dtaDoc"):
    """Same fetch as download_doc but performed BY THE PAGE. -> PDF bytes or None."""
    if not action or not val:
        return None
    try:
        b64 = page.evaluate(_JS_FETCH_DOC, [f"{OJV}/{action.lstrip('/')}", param, val])
        if not b64:
            return None
        body = base64.b64decode(b64)
        return body if body[:4] == b"%PDF" else None
    except Exception:
        return None


def fetch_doc(page, api, action, val, param="dtaDoc"):
    """Dispatch to the in-page or the out-of-page downloader (`--docs-inpage`)."""
    if DOCS_INPAGE:
        return download_doc_inpage(page, action, val, param)
    return download_doc(api, action, val, param)


# Causa-level header docs (in the detalle modal header, not the historia table). Each:
# (key, action-substring, hidden-input param). Always fetched when --docs (reduced set).
HEADER_DOCS = [
    ("texto_demanda", "docu.php", "valorEncTxtDmda"),
    ("certificado", "docCertificadoDemanda", "dtaCert"),
    ("ebook", "newebookcivil", "dtaEbook"),
]


def grab_header_docs(page):
    """[{key, action, param, val}] for the Texto Demanda / Certificado / Ebook forms."""
    return page.evaluate(
        r"""(want)=>{
          const m=document.querySelector('#modalDetalleCivil'); if(!m) return [];
          const out=[];
          m.querySelectorAll('form').forEach(f=>{
            const a=f.getAttribute('action')||'';
            const hit=want.find(w=>a.includes(w[1]));
            if(!hit) return;
            const inp=f.querySelector('input');
            out.push({key:hit[0], action:a, param:inp?inp.getAttribute('name'):'',
                      val:inp?inp.value:''});
          });
          return out;
        }""", HEADER_DOCS)


def causa_state(tribunal_id):
    """{rol: (fill_status, detalles_bool)} for a tribunal — for --resume + the Detalles flag.

    Retries once through dbstore._reconnect(). A multi-hour sweep outlives Neon's idle
    timeout, and the connection dies somewhere around the second tribunal; returning {} on
    that error SILENTLY DISABLES --resume, so the run happily re-scrapes causas it already
    has (observed 2026-07-22: 'SSL connection has been closed unexpectedly' at tribunal 260,
    then 'connection already closed' for every tribunal after it)."""
    for attempt in (1, 2):
        try:
            store = get_store()
            with store.conn.cursor() as cur:
                cur.execute("SELECT rol, fill_status, detalles FROM causas WHERE tribunal_id=%s",
                            (str(tribunal_id),))
                return {r[0]: (r[1] or "", bool(r[2])) for r in cur.fetchall()}
        except Exception as e:
            if attempt == 1:
                print(f"    [warn] causa_state {tribunal_id}: {str(e)[:50]} — reconectando")
                try:
                    get_store()._reconnect()
                    continue
                except Exception as e2:
                    print(f"    [warn] reconexion fallida: {str(e2)[:50]}")
            print(f"    [warn] causa_state {tribunal_id}: sin DB — "
                  f"--resume NO puede saltar nada en este tribunal")
            return {}


def select_by_kbd(page, sel, value):
    """Change a <select> to `value` via TRUSTED keyboard (focus + arrows). True on success."""
    try:
        opts = page.eval_on_selector_all(
            f"{sel} option", "els=>els.map((o,i)=>({i:i,v:o.value,sel:o.selected}))")
        cur = next((o["i"] for o in opts if o["sel"]), 0)
        tgt = next((o["i"] for o in opts if o["v"] == value), None)
        if tgt is None:
            return False
        page.locator(sel).focus()
        key = "ArrowDown" if tgt > cur else "ArrowUp"
        for _ in range(abs(tgt - cur)):
            page.keyboard.press(key)
            page.wait_for_timeout(70)
        return page.eval_on_selector(sel, "e=>e.value") == value
    except Exception:
        return False


def _wait_opts(page, sel, secs):
    """Poll for a <select>'s options to populate (AJAX cascade). True when >0 real options."""
    for _ in range(secs * 2):
        page.wait_for_timeout(500)
        try:
            if page.eval_on_selector_all(f"{sel} option",
                                         "e=>e.filter(o=>o.value&&o.value!=='0').length"):
                return True
        except Exception:
            pass
    return False


def type_date_kbd(page, sel, value):
    """Set a readonly datepicker input with TRUSTED keystrokes. `readOnly` is cleared as a DOM
    PROPERTY — a mutation, not an event, so nothing untrusted is ever dispatched — and then the
    value is TYPED for real, so the browser itself emits genuine isTrusted=true input/change
    events. Do NOT go back to `e.value=...` + `dispatchEvent(new Event('change'))`: that fires
    isTrusted=false and F5 flags the session (the search still succeeds once, then the NEXT
    request comes back as the rejection page — it burned a profile on 2026-07-21)."""
    for attempt, closer in enumerate(("Escape", "Tab")):
        try:
            page.eval_on_selector(sel, "e=>{e.readOnly=false;e.removeAttribute('readonly');}")
            human_click(page, sel)                    # human arc — also opens the datepicker
            page.keyboard.press("Control+a")
            page.keyboard.type(value, delay=60)       # TRUSTED keystrokes
            page.keyboard.press(closer)               # close the datepicker / blur to fire change
            page.wait_for_timeout(400)
            if page.eval_on_selector(sel, "e=>e.value") == value:
                return True
        except Exception as e:
            print(f"      [date {sel}] {str(e)[:50]}")
    return False


def establish_form_kbd(page, corte_val, desde, hasta):
    """Establish the Busqueda por Fecha form BASE with TRUSTED keyboard only — no manual search
    needed, and this is also the session-expiry recovery. Sets: Fecha tab, Civil competencia,
    corte, dates. Tribunals are iterated by the caller. Returns True on success."""
    try:
        if page.query_selector("a[href='#BusFecha']"):
            page.locator("a[href='#BusFecha']").focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(1000)
        if not select_by_kbd(page, "#fecCompetencia", "3"):     # Civil
            print("      [establish] competencia select failed")
            return False
        _wait_opts(page, "#corteFec", 6)
        if not select_by_kbd(page, "#corteFec", corte_val):
            print(f"      [establish] corte {corte_val} select failed")
            return False
        page.wait_for_timeout(5000)                             # 5s settle (operator's tip)
        _wait_opts(page, "#fecTribunal", 10)
        for sel, val in (("#fecDesde", desde), ("#fecHasta", hasta)):
            if not type_date_kbd(page, sel, val):               # TRUSTED typing, never JS .value
                print(f"      [establish] date {sel} = {val} failed")
                return False
        return True
    except Exception as e:
        print(f"      [establish] {str(e)[:60]}")
        return False


class Blocked(Exception):
    """The F5 WAF is rejecting detail opens — abort the run, the profile is spent."""


def waf_blocked(page):
    """True if any frame is showing the F5 rejection page. Same signal as waf_check.py, read
    only when a causa fails, so it costs nothing on the happy path."""
    for fr in page.frames:
        try:
            txt = fr.evaluate("document.body?document.body.innerText.slice(0,400):''") or ""
        except Exception:
            continue
        if "requested URL was rejected" in txt or "Support ID" in txt:
            return True
    return False


def form_ok(page):
    """True if the date form is still established (competencia=Civil, tribunal select enabled).
    False after a session-expiry popup resets it (corte/tribunal go disabled)."""
    try:
        return (page.eval_on_selector("#fecCompetencia", "e=>e.value") == "3"
                and not page.eval_on_selector("#fecTribunal", "e=>e.disabled"))
    except Exception:
        return False


def scrape_causa(page, api, meta, full=False):
    """Modal opened by the caller. Parse header/litigantes/cuadernos(historia)/escritos/
    receptor. With GPS: resolve each geo row's lat/lng. With DOCS: download the causa-level
    header docs (Texto Demanda / Certificado / Ebook) + a FILTERED set of historia docs to
    Drive. Reduced set (default): cuaderno 1 (Principal) only the 'Ingreso demanda' row, other
    cuadernos all rows. `full=True` (Detalles flag): every historia doc. Close the modal."""
    header = parse_header(page)
    litigantes = parse_litigantes(page)
    causa_id = f"{meta.get('tribunalId','')}-{meta['rol']}"

    # causa-level header docs — always downloaded (part of the reduced set)
    header_urls = {}
    if DOCS:
        for hd in grab_header_docs(page):
            body = fetch_doc(page, api, hd["action"], hd["val"], param=hd["param"])
            if body and len(body) >= 1024:
                obj = f"{causa_id}/{hd['key']}.pdf".replace(" ", "_")
                try:
                    header_urls[hd["key"]] = get_store().upload_pdf(obj, body)
                except Exception as e:
                    print(f"      [warn] upload {hd['key']}: {str(e)[:50]}")

    cuads = cuaderno_options(page) or [{"txt": "1 - Principal", "val": ""}]
    cuadernos = []
    for ci, opt in enumerate(cuads):
        if ci > 0:
            select_cuaderno(page, ci)
            pace(P_STEP)
        cuaderno = opt["txt"]
        cnum = _cuaderno_num(cuaderno)
        is_principal = cnum == "1"
        rows = parse_historia(page)
        seen = {}
        for hh in rows:
            folio = hh.get("folio", "")
            n = seen.get(folio, 0) + 1
            seen[folio] = n
            if GPS and hh.get("geo"):
                g = resolve_geo(page, hh["geo"])
                if g:
                    hh["georref"] = g
                pace(P_STEP)
            # reduced filter: cuaderno-1 keep only 'Ingreso demanda'; other cuadernos keep all
            want_doc = full or (not is_principal) \
                or ("ingreso demanda" in (hh.get("desc", "") or "").lower())
            if DOCS and want_doc:
                for kind in ("doc", "anexo"):
                    form = hh.get(kind)
                    if not (form and form.get("action") and form.get("val")):
                        continue
                    body = fetch_doc(page, api, form["action"], form["val"])
                    if body and len(body) >= 1024:
                        obj = f"{causa_id}/c{cnum}/{folio}-{n}-{kind}.pdf".replace(" ", "_")
                        try:
                            hh[f"{kind}_url"] = get_store().upload_pdf(obj, body)
                        except Exception as e:
                            print(f"      [warn] upload {kind} {folio}: {str(e)[:50]}")
        cuadernos.append({"cuaderno": cuaderno, "historia": rows})
    escritos = parse_escritos(page)
    pace(P_STEP)
    receptor = parse_receptor(page)
    close_modal(page, "#modalDetalleCivil")
    n_hist = sum(len(c["historia"]) for c in cuadernos)
    ndoc = len(header_urls) + sum(
        1 for c in cuadernos for r in c["historia"] if r.get("doc_url") or r.get("anexo_url"))
    ngeo = sum(1 for c in cuadernos for r in c["historia"] if str(r.get("georref", "")).startswith("="))
    return {**meta, "header": header, "litigantes": litigantes, "cuadernos": cuadernos,
            "escritos": escritos, "receptor": receptor, "n_historia": n_hist,
            "n_docs": ndoc, "n_geo": ngeo, "scrape_level": "full" if full else "scraped",
            "texto_demanda": header_urls.get("texto_demanda", ""),
            "certificado": header_urls.get("certificado", ""),
            "ebook": header_urls.get("ebook", "")}


# ── search / pagination ──────────────────────────────────────────────────────

def fire_search(page):
    """Wait for Buscar to be enabled (form settles after a tribunal change), CLEAR the stale
    results (so old rows aren't mistaken for a fresh search), click Buscar ONCE (TRUSTED), and
    poll up to ~45s for rows. Returns True if rows rendered, False on 'sin resultados'/disabled."""
    for _ in range(24):   # up to ~12s for the button to enable
        try:
            if not page.eval_on_selector("#btnConConsultaFec", "e=>e.disabled"):
                break
        except Exception:
            pass
        page.wait_for_timeout(500)
    try:   # clear stale results so a disabled/failed search can't look successful
        page.evaluate("()=>{const t=document.querySelector('#dtaTableDetalleFecha tbody');"
                      " if(t) t.innerHTML='';}")
    except Exception:
        pass
    if not human_click(page, "#btnConConsultaFec", timeout=5000):
        print("    [warn] buscar not clickable")
        return False
    waited = 0
    while waited < 45000:
        n = page.eval_on_selector_all(
            "#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']", "e=>e.length")
        if n:
            page.wait_for_timeout(700)
            return True
        try:
            txt = page.inner_text("#dtaTableDetalleFecha")
        except Exception:
            txt = ""
        if re.search(r"no se (han )?encontrad|sin resultados", txt or "", re.I):
            return False
        page.wait_for_timeout(1000)
        waited += 1000
    return False


def select_tribunal_kbd(page, value):
    """Change #fecTribunal to `value` via TRUSTED keyboard (focus + arrow keys) — NOT
    select_option (whose synthetic change event trips the F5 WAF). Returns True on success."""
    try:
        opts = page.eval_on_selector_all(
            "#fecTribunal option", "els=>els.map((o,i)=>({i:i,v:o.value,sel:o.selected}))")
        cur = next((o["i"] for o in opts if o["sel"]), 0)
        tgt = next((o["i"] for o in opts if o["v"] == value), None)
        if tgt is None:
            return False
        page.locator("#fecTribunal").focus()
        delta = tgt - cur
        key = "ArrowDown" if delta > 0 else "ArrowUp"
        for _ in range(abs(delta)):
            page.keyboard.press(key)
            page.wait_for_timeout(70)
        return page.eval_on_selector("#fecTribunal", "e=>e.value") == value
    except Exception as e:
        print(f"    [warn] kbd tribunal {value}: {str(e)[:50]}")
        return False


def scraped_rols(tribunal_id):
    """Set of rols at this tribunal already fully scraped (fill_status='scraped') in Neon.
    Used by --resume to skip them. Retries once through _reconnect() — see causa_state()."""
    for attempt in (1, 2):
        try:
            store = get_store()
            with store.conn.cursor() as cur:
                cur.execute("SELECT rol FROM causas WHERE tribunal_id=%s "
                            "AND fill_status='scraped'", (str(tribunal_id),))
                return {r[0] for r in cur.fetchall()}
        except Exception as e:
            if attempt == 1:
                print(f"    [warn] resume lookup {tribunal_id}: {str(e)[:50]} — reconectando")
                try:
                    get_store()._reconnect()
                    continue
                except Exception:
                    pass
            print(f"    [warn] resume lookup {tribunal_id}: sin DB — no se salta nada")
            return set()


def page_rows(page):
    """Every row of the current results page (bank or not). Kept separate from the bank filter
    so pagination can be audited against `.loadTotalFec`: the site's total counts ALL rows, so
    comparing it to the bank subset would be meaningless."""
    return page.eval_on_selector_all(
        "#dtaTableDetalleFecha tbody tr",
        r"""els=>els.map((tr,i)=>{var td=tr.querySelectorAll('td');
              var a=tr.querySelector("a[onclick*='detalleCausaCivil']");
              return {i:i, rol:td[1]?td[1].innerText.trim():'', car:td[3]?td[3].innerText.trim():'',
                      fecha:td[2]?td[2].innerText.trim():'', trib:td[4]?td[4].innerText.trim():'',
                      has:!!a};})""")


def page_bank_causas(page):
    return [r for r in page_rows(page) if r["has"]
            and r["rol"].upper().startswith("C") and is_bank(r["car"])]


def total_registros(page):
    """The search's TRUE row count, from the site's own `Total de registros: N` label.

    This is the only ground truth for "did pagination reach the end?". Without it the loop can
    only ask "did the table change?", and a slow paginator AJAX then looks exactly like the last
    page — which is how tribunal 260 was recorded as 91 bank causas when it really has 135
    (2026-07-22). Returns None if the label is missing or unparseable: never guess a total."""
    for sel in (".loadTotalFec", "#loadTotalFec", "[class*='loadTotal']"):
        try:
            txt = page.eval_on_selector(sel, "e=>e?e.innerText:''") or ""
        except Exception:
            continue
        m = re.search(r"([\d.,]+)\s*$", txt.strip())
        if m:
            try:
                return int(re.sub(r"[.,]", "", m.group(1)))
            except ValueError:
                pass
    return None


def paginator_state(page):
    """(current, last) page numbers from the paginator, or (None, None) if unreadable.
    Advisory only — used to log progress and to confirm a 'stuck' verdict."""
    try:
        got = page.evaluate(
            """()=>{const s=document.querySelector('#sigId'); if(!s) return null;
                 const ul=s.closest('ul'); if(!ul) return null;
                 const nums=[...ul.querySelectorAll('li')].map(li=>({
                   n:parseInt((li.innerText||'').trim(),10),
                   act:li.classList.contains('active')})).filter(o=>!isNaN(o.n));
                 const cur=nums.find(o=>o.act);
                 return {cur:cur?cur.n:null, last:nums.length?Math.max(...nums.map(o=>o.n)):null};}""")
    except Exception:
        return (None, None)
    if not got:
        return (None, None)
    return (got.get("cur"), got.get("last"))


def first_sig(page):
    return page.eval_on_selector(
        "#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']",
        "e=>e?e.getAttribute('onclick'):''") or ""


def sig_disabled(page):
    """True when 'Siguiente' is greyed out = we are genuinely on the last page."""
    try:
        return bool(page.eval_on_selector(
            "#sigId",
            "e=>{const li=e.closest('li');return !!(li&&li.classList.contains('disabled'));}"))
    except Exception:
        return True     # no paginator at all -> nothing to advance to


def next_page(page, tries=2):
    """Advance the results paginator one page. Returns a REASON, not a bool:

        "advanced"  the table really swapped — keep harvesting
        "last"      Siguiente is disabled — the tribunal is genuinely finished
        "stuck"     we clicked and the table never changed — pages were LOST

    The old version returned False for both "last" and "stuck", and every caller read that as
    "no more pages" and moved on with exit code 0. That is the whole `--count-only` undercount:
    tribunal 260 reported 91 bank causas in January against 135 real ones (~one page dropped),
    because a paginator AJAX that took longer than the 10 s poll is indistinguishable from the
    end of the list. Now a timeout retries the click once and, if it still will not move, says
    so out loud so the caller can flag the tribunal instead of silently truncating it."""
    if sig_disabled(page):
        return "last"
    for attempt in range(1, tries + 1):
        wait_idle(page)                       # never click while the site is mid-request
        before = first_sig(page)
        if not human_click(page, "#sigId", timeout=4000):   # human arc — never page.click()
            page.wait_for_timeout(1500)
            continue
        for _ in range(40):                   # poll up to ~20s for the AJAX swap (was 10s)
            page.wait_for_timeout(500)
            if first_sig(page) not in ("", before):
                return "advanced"
        # No swap. Two innocent explanations before calling it stuck: the click landed on the
        # last page (Siguiente just became disabled), or the request is still in flight.
        if sig_disabled(page):
            return "last"
        if page_busy(page) and wait_idle(page, secs=25):
            if first_sig(page) not in ("", before):
                return "advanced"
        if attempt < tries:
            print(f"    [warn] paginador no avanzo — reintento {attempt + 1}/{tries}")
    return "stuck"


# ── main ─────────────────────────────────────────────────────────────────────

def find_ojv_page(ctx):
    for p in ctx.pages:
        try:
            if p.query_selector("#fecCompetencia"):
                return p
        except Exception:
            pass
    for p in ctx.pages:
        if "pjud" in (p.url or ""):
            return p
    return ctx.pages[0] if ctx.pages else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--max-tribs", type=int, default=0, help="0 = all tribunales")
    ap.add_argument("--max-causas", type=int, default=0, help="0 = no limit")
    ap.add_argument("--proc", default="", help="only keep causas whose Proc. matches (e.g. 'Ejecutivo Obligación de Dar')")
    ap.add_argument("--docs", action="store_true", help="download historia doc/anexo PDFs -> Drive")
    ap.add_argument("--docs-inpage", action="store_true",
                    help="fetch those PDFs from INSIDE the page (in-page fetch) instead of "
                         "context.request.get() — carries the page's request context and shows "
                         "up in Shape's telemetry. Use with --docs.")
    ap.add_argument("--gps", action="store_true", help="resolve georreferencia sub-modals -> lat/lng")
    ap.add_argument("--no-search", action="store_true",
                    help="WAF-safe: do NOT select_option/search; harvest the CURRENT results "
                         "table (operator already searched). Only the displayed tribunal.")
    ap.add_argument("--resume", action="store_true",
                    help="skip causas already scraped (fill_status='scraped') in Neon")
    ap.add_argument("--count-only", action="store_true",
                    help="count bank C-causas per tribunal from the results table; NO detail "
                         "opens/docs (safe on a burned profile — sizes the job)")
    ap.add_argument("--corte", default="",
                    help="establish the form via keyboard for this corte VALUE (90=Santiago) -> "
                         "NO manual search needed; the script sets competencia/corte/dates itself "
                         "and re-establishes if the session-expiry popup resets the form")
    ap.add_argument("--max-empty", type=int, default=4,
                    help="consecutive 'sin resultados' tribunales before checking for the F5 "
                         "rejection page; small rural tribunales really are empty, so only a "
                         "STREAK is suspicious")
    ap.add_argument("--max-fails", type=int, default=3,
                    help="consecutive causa failures before checking for the F5 rejection page; "
                         "if it is there the run STOPS (exit 3) instead of grinding out "
                         "timeouts on a spent profile")
    ap.add_argument("--desde", default="01/01/2026", help="date Desde DD/MM/YYYY (with --corte)")
    ap.add_argument("--hasta", default="31/01/2026", help="date Hasta DD/MM/YYYY (with --corte)")
    args = ap.parse_args()
    global DOCS, GPS, RESUME, COUNT_ONLY, DOCS_INPAGE
    DOCS, GPS, RESUME, COUNT_ONLY = args.docs, args.gps, args.resume, args.count_only
    DOCS_INPAGE = args.docs_inpage

    print(f"Conectando a Chrome (puerto CDP {args.port})...")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        ctx = browser.contexts[0]
        api = ctx.request
        page = find_ojv_page(ctx)
        if not page:
            sys.exit("[ERROR] No encuentro ninguna pestana. Abre OJV en esa ventana.")

        # OJV pops a session keep-alive/expiry dialog every so often. A native dialog PAUSES
        # all page JS while open, so detalleCausaCivil never resolves -> the causa-open hangs.
        # Auto-ACCEPT it (Aceptar) the instant it appears so the scrape rides straight through,
        # session intact, results intact — no reload (which would reset the whole form).
        def _accept_dialog(d):
            try:
                print(f"    [dialog] auto-accept: {d.type} {d.message[:50]!r}")
                d.accept()
            except Exception:
                pass
        for _p in ctx.pages:
            _p.on("dialog", _accept_dialog)
        ctx.on("page", lambda p: p.on("dialog", _accept_dialog))

        # --corte: the script establishes the whole form via keyboard (no manual search).
        if args.corte:
            print(f"[KBD] establishing form: corte {args.corte}, {args.desde}..{args.hasta} "
                  f"(trusted keyboard — no manual search needed)")
            if not establish_form_kbd(page, args.corte, args.desde, args.hasta):
                sys.exit("[ALTO] keyboard establish failed — reach the 'Busqueda por Fecha' tab first.")

        if (not page.query_selector("#fecCompetencia")
                or page.eval_on_selector("#fecCompetencia", "e=>e.value") != "3"):
            sys.exit("[ALTO] La Competencia no es CIVIL (o no veo 'Busqueda por Fecha').")
        tribs = page.eval_on_selector_all(
            "#fecTribunal option",
            "els=>els.filter(o=>o.value&&o.value!=='0').map(o=>({v:o.value,t:(o.textContent||'').trim()}))")
        if not tribs:
            sys.exit("[ALTO] No hay Tribunales cargados. Elige la Corte primero.")
        if args.no_search:
            # Harvest only the tribunal the operator already selected + searched (trusted).
            tv = page.eval_on_selector("#fecTribunal", "e=>e.value") or ""
            tn = page.eval_on_selector(
                "#fecTribunal", "e=>e.options[e.selectedIndex]?e.options[e.selectedIndex].text.trim():''") or ""
            if not tv:
                sys.exit("[ALTO] --no-search: elige un Tribunal y haz la busqueda manual primero.")
            tribs = [{"v": tv, "t": tn}]
        desde = page.eval_on_selector("#fecDesde", "e=>e.value")
        hasta = page.eval_on_selector("#fecHasta", "e=>e.value")
        if not desde or not hasta:
            sys.exit("[ALTO] Faltan las FECHAS (Desde / Hasta).")
        corte = page.eval_on_selector(
            "#corteFec", "e=>e.options[e.selectedIndex]?e.options[e.selectedIndex].text.trim():''")
        if args.max_tribs:
            tribs = tribs[:args.max_tribs]
        print(f"[OK] Corte: {corte} · {len(tribs)} tribunales · fechas {desde}..{hasta}"
              + (f" · proc={args.proc!r}" if args.proc else "") + "\n")

        # recover from any modal left open by a previous (killed) run
        for sel in ("#modalReceptorCivil", "#modalDetalleCivil"):
            if modal_open(page, sel):
                close_modal(page, sel)

        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        out = DOWNLOADS / f"pjud_cdp_{int(time.time())}.json"
        details, t0, count_total = [], time.time(), 0
        fails = 0        # consecutive causa failures -> WAF watchdog (see --max-fails)
        empties = 0      # consecutive empty searches -> soft-block watchdog (--max-empty)
        incomplete = []  # tribunales whose pagination did not reach the end -> .incomplete.json

        def flush():
            out.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
            # Sidecar, rewritten on every flush so it survives a kill or a Blocked exit: the
            # tribunales that must be re-run. Without it a truncated tribunal is invisible.
            if incomplete:
                out.with_suffix(".incomplete.json").write_text(
                    json.dumps(incomplete, ensure_ascii=False, indent=2), encoding="utf-8")
        for ti, tb in enumerate(tribs, 1):
            if args.max_causas and len(details) >= args.max_causas:
                break
            if not args.no_search:
                if args.corte and not form_ok(page):          # session-expiry popup reset the form
                    print(f"[{ti}/{len(tribs)}] {tb['t'][:40]}  [recover: form reset -> re-establish]")
                    establish_form_kbd(page, args.corte, args.desde, args.hasta)
                if not select_tribunal_kbd(page, tb["v"]):    # TRUSTED keyboard (not select_option)
                    print(f"[{ti}/{len(tribs)}] {tb['t'][:40]}  [skip: could not select tribunal]")
                    pace(P_STEP)
                    continue
                pace(P_STEP)
            print(f"[{ti}/{len(tribs)}] {tb['t'][:40]}"
                  + ("  (harvest current results)" if args.no_search else ""))
            if not args.no_search and not fire_search(page):
                # "sin resultados" is ALSO how a burned profile fails: the searches come back
                # empty instead of showing a rejection page. On 2026-07-22 worker 2 burned
                # after tribunal 4 and then reported 20 consecutive empty tribunales — exit 0,
                # as if the corte were genuinely empty. Small rural tribunales really are
                # empty, so only a STREAK is suspicious; check the WAF before believing it.
                empties += 1
                print(f"      sin resultados{f'  [{empties} seguidos]' if empties > 1 else ''}")
                if empties >= args.max_empty:
                    if waf_blocked(page):
                        flush()
                        raise Blocked(
                            f"{empties} busquedas vacias seguidas + pagina de rechazo F5 · "
                            f"{len(details)} causas guardadas en {out}")
                    print(f"      [warn] {empties} tribunales vacios seguidos, pero sin pagina "
                          f"de rechazo — parecen vacios de verdad")
                    empties = 0
                pace(P_TRIB)
                continue
            empties = 0                                  # a real result set clears the streak
            if COUNT_ONLY:
                cnt, cpages, why = set(), 0, "last"
                expected = total_registros(page)      # ground truth: ALL rows, not just banks
                rows_seen = set()
                while cpages < 80:
                    for r in page_rows(page):
                        rows_seen.add(r["rol"] or f"?{cpages}.{r['i']}")
                    for c in page_bank_causas(page):
                        if c["rol"] in cnt:
                            continue
                        cnt.add(c["rol"])
                        details.append({"rol": c["rol"], "caratulado": c["car"],
                                        "fecha": c["fecha"], "tribunal": c["trib"],
                                        "tribunalSel": tb["t"], "tribunalId": tb["v"],
                                        "corte": corte, "rango": f"{desde} a {hasta}"})
                    cpages += 1
                    why = next_page(page)
                    if why != "advanced":
                        break
                    pace(P_PAGE)
                count_total += len(cnt)
                short = expected is not None and len(rows_seen) < expected
                print(f"      -> {len(cnt)} bank C-causas  (running total {count_total})"
                      f"  [{cpages} pag · {len(rows_seen)}"
                      f"{'/' + str(expected) if expected is not None else ''} filas]")
                if short or why == "stuck":
                    note = {"tribunalId": tb["v"], "tribunal": tb["t"],
                            "rango": f"{desde} a {hasta}", "esperadas": expected,
                            "vistas": len(rows_seen), "paginas": cpages, "motivo": why}
                    incomplete.append(note)
                    print(f"      [INCOMPLETO] faltan filas ({note['vistas']} de "
                          f"{note['esperadas']}) · paginador: {why} — este tribunal hay que "
                          f"repetirlo")
                flush()                                  # save the list incrementally
                pace(P_TRIB)
                continue
            seen, pages, kept_trib = set(), 0, 0
            why, rows_seen = "last", set()
            expected = total_registros(page)
            # DB state per tribunal: {rol: (fill_status, detalles)}. Needed for --resume AND to
            # decide full vs reduced doc set per causa (Detalles flag).
            state = causa_state(tb["v"]) if (RESUME or DOCS) else {}
            if RESUME:
                nskip = sum(1 for fs, det in state.values()
                            if fs == "full" or (fs == "scraped" and not det))
                if nskip:
                    print(f"      (resume: {nskip} already done here — skipping)")
            while pages < 80:
                if args.max_causas and len(details) >= args.max_causas:
                    break
                for r in page_rows(page):
                    rows_seen.add(r["rol"] or f"?{pages}.{r['i']}")
                causas = page_bank_causas(page)
                for c in causas:
                    if c["rol"] in seen:
                        continue
                    seen.add(c["rol"])
                    fs, det = state.get(c["rol"], ("", False))
                    if RESUME and (fs == "full" or (fs == "scraped" and not det)):
                        continue                       # already done at the required level
                    if args.max_causas and len(details) >= args.max_causas:
                        break
                    pace(P_CAUSA)
                    try:
                        human_click(page, page.locator("#dtaTableDetalleFecha tbody tr")
                                    .nth(c["i"]).locator("a[onclick*='detalleCausaCivil']").first,
                                    timeout=8000)      # human arc — never .click()
                        page.wait_for_function(
                            "rol=>{var m=document.querySelector('#modalDetalleCivil');"
                            " return m && m.innerText.indexOf('ROL')>=0 && m.innerText.indexOf(rol)>=0;}",
                            arg=c["rol"], timeout=30000)   # detail modal can be slow
                        page.wait_for_timeout(600)
                        rec = scrape_causa(page, api, {
                            "rol": c["rol"], "caratulado": c["car"], "fecha": c["fecha"],
                            "tribunal": c["trib"], "tribunalSel": tb["t"], "tribunalId": tb["v"],
                            "corte": corte, "rango": f"{desde} a {hasta}"}, full=det)
                        if args.proc and norm(rec["header"].get("procedimiento", "")) != norm(args.proc):
                            continue     # scraped but doesn't match the proc filter -> drop
                        details.append(rec)
                        kept_trib += 1
                        flush()                          # incremental save (survives interrupts)
                        print(f"      OK {c['rol']:<13} lit={len(rec['litigantes'])} "
                              f"cuad={len(rec['cuadernos'])} hist={rec['n_historia']} "
                              f"esc={len(rec['escritos'])} rec={len(rec['receptor'])} "
                              f"docs={rec['n_docs']} geo={rec['n_geo']}"
                              f"{' [FULL]' if det else ''}  (tot {len(details)})")
                        fails = 0                        # a success clears the streak
                    except Exception as e:
                        print(f"      ERR {c['rol']}: {str(e)[:70]}")
                        # Clear the modal properly before the next causa, and only count this
                        # as a WAF failure if the page came back clean — a stuck modal makes
                        # every following open fail for reasons that have nothing to do with
                        # the WAF (see clear_stuck_modal).
                        if not clear_stuck_modal(page):
                            print("      [recover] recargando la pagina para desatascarla")
                            try:
                                page.reload(wait_until="domcontentloaded", timeout=30000)
                                page.wait_for_timeout(2500)
                                clear_stuck_modal(page)
                            except Exception as e2:
                                print(f"      [recover] recarga fallida: {str(e2)[:50]}")
                            break        # results are gone after a reload -> next tribunal
                        # Unattended runs must NOT grind out 30s timeouts for hours after the
                        # profile is spent (that is exactly what happened on 2026-07-22 until
                        # it was killed by hand). A streak of failures -> check for the F5
                        # rejection page, and if it is there, stop while the JSON is intact.
                        fails += 1
                        if fails >= args.max_fails:
                            if waf_blocked(page):
                                flush()
                                raise Blocked(
                                    f"pagina de rechazo F5 tras {fails} fallos seguidos · "
                                    f"{len(details)} causas guardadas en {out}")
                            print(f"      [warn] {fails} fallos seguidos, pero sin pagina de "
                                  f"rechazo — sigo")
                            fails = 0
                pages += 1
                if args.max_causas and len(details) >= args.max_causas:
                    break
                why = next_page(page)
                if why != "advanced":
                    break
                pace(P_PAGE)
            print(f"      -> {kept_trib} causas de banco en este tribunal"
                  f"  [{pages} pag · {len(rows_seen)}"
                  f"{'/' + str(expected) if expected is not None else ''} filas]")
            # Only trust "finished" when the paginator said so AND we saw every row the site
            # claims. A page lost here is a hole nobody notices: the tribunal looks done.
            if why == "stuck" or (expected is not None and len(rows_seen) < expected
                                  and not args.max_causas):
                incomplete.append({"tribunalId": tb["v"], "tribunal": tb["t"],
                                   "rango": f"{desde} a {hasta}", "esperadas": expected,
                                   "vistas": len(rows_seen), "paginas": pages, "motivo": why})
                print(f"      [INCOMPLETO] {len(rows_seen)} de {expected} filas · "
                      f"paginador: {why} — este tribunal hay que repetirlo")
            pace(P_TRIB)

        mins = (time.time() - t0) / 60.0
        flush()
        if COUNT_ONLY:
            print(f"\n[COUNT] {count_total} bank C-causas across {len(tribs)} tribunal(s) "
                  f"in {mins:.1f} min -> {out}")
        else:
            print(f"\n[LISTO] {len(details)} causas en {mins:.1f} min -> {out}")
        if incomplete:
            print(f"\n[INCOMPLETO] {len(incomplete)} tribunal(es) sin paginar hasta el final — "
                  f"NO son un censo:")
            for n in incomplete:
                print(f"    {n['tribunalId']:>4} {n['tribunal'][:34]:36} "
                      f"{n['vistas']}/{n['esperadas']} filas · {n['paginas']} pag · {n['motivo']}")
            print(f"    -> {out.with_suffix('.incomplete.json')}")


if __name__ == "__main__":
    try:
        main()
    except Blocked as e:
        # Exit code 3 = "profile spent", so an unattended wrapper can tell this apart from a
        # crash and rotate the profile instead of retrying. The JSON was flushed before we got
        # here; ingest it, then rename %LOCALAPPDATA%\pjud_cdp aside and re-pass the CAPTCHA.
        print(f"\n[BLOQUEADO] {e}")
        print("  Ingesta ese JSON, luego renombra %LOCALAPPDATA%\\pjud_cdp y pasa el CAPTCHA "
              "de nuevo (una IP nueva NO sirve).")
        sys.exit(3)
