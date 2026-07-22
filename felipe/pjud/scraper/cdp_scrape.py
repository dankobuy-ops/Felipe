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
    x = y = None
    for attempt in range(3):
        x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        try:
            hit = el.evaluate(
                "(e, pt) => {const top = document.elementFromPoint(pt[0], pt[1]);"
                " return !!top && (top === e || e.contains(top) || top.contains(e));}", [x, y])
        except Exception:
            break                                        # can't hit-test (iframe etc.) — go
        if hit:
            break
        if attempt < 2:                                  # covered: settle, re-measure, retry
            page.wait_for_timeout(400)
            try:
                el.scroll_into_view_if_needed(timeout=timeout)
                box = el.bounding_box() or box
            except Exception:
                pass
    else:
        print("    [warn] human_click: target still covered — clicking anyway")

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
    Empty if the DB isn't reachable."""
    try:
        store = get_store()
        with store.conn.cursor() as cur:
            cur.execute("SELECT rol, fill_status, detalles FROM causas WHERE tribunal_id=%s",
                        (str(tribunal_id),))
            return {r[0]: (r[1] or "", bool(r[2])) for r in cur.fetchall()}
    except Exception as e:
        print(f"    [warn] causa_state {tribunal_id}: {str(e)[:50]}")
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
    Used by --resume to skip them. Empty set if the store/DB isn't reachable."""
    try:
        store = get_store()
        with store.conn.cursor() as cur:
            cur.execute("SELECT rol FROM causas WHERE tribunal_id=%s AND fill_status='scraped'",
                        (str(tribunal_id),))
            return {r[0] for r in cur.fetchall()}
    except Exception as e:
        print(f"    [warn] resume lookup {tribunal_id}: {str(e)[:50]}")
        return set()


def page_bank_causas(page):
    rows = page.eval_on_selector_all(
        "#dtaTableDetalleFecha tbody tr",
        r"""els=>els.map((tr,i)=>{var td=tr.querySelectorAll('td');
              var a=tr.querySelector("a[onclick*='detalleCausaCivil']");
              return {i:i, rol:td[1]?td[1].innerText.trim():'', car:td[3]?td[3].innerText.trim():'',
                      fecha:td[2]?td[2].innerText.trim():'', trib:td[4]?td[4].innerText.trim():'',
                      has:!!a};})""")
    return [r for r in rows if r["has"]
            and r["rol"].upper().startswith("C") and is_bank(r["car"])]


def first_sig(page):
    return page.eval_on_selector(
        "#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']",
        "e=>e?e.getAttribute('onclick'):''") or ""


def next_page(page):
    """Click 'Siguiente' (TRUSTED). True only once the table actually changes."""
    try:
        disabled = page.eval_on_selector(
            "#sigId", "e=>{const li=e.closest('li');return !!(li&&li.classList.contains('disabled'));}")
    except Exception:
        return False
    if disabled:
        return False
    before = first_sig(page)
    if not human_click(page, "#sigId", timeout=4000):  # human arc — never page.click()
        return False
    for _ in range(20):
        page.wait_for_timeout(500)
        if first_sig(page) not in ("", before):
            return True
    return False


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

        def flush():
            out.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
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
                print("      sin resultados")
                pace(P_TRIB)
                continue
            if COUNT_ONLY:
                cnt, cpages = set(), 0
                while cpages < 80:
                    for c in page_bank_causas(page):
                        if c["rol"] in cnt:
                            continue
                        cnt.add(c["rol"])
                        details.append({"rol": c["rol"], "caratulado": c["car"],
                                        "fecha": c["fecha"], "tribunal": c["trib"],
                                        "tribunalSel": tb["t"], "tribunalId": tb["v"],
                                        "corte": corte, "rango": f"{desde} a {hasta}"})
                    cpages += 1
                    if not next_page(page):
                        break
                    pace(P_PAGE)
                count_total += len(cnt)
                print(f"      -> {len(cnt)} bank C-causas  (running total {count_total})")
                flush()                                  # save the list incrementally
                pace(P_TRIB)
                continue
            seen, pages, kept_trib = set(), 0, 0
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
                    except Exception as e:
                        print(f"      ERR {c['rol']}: {str(e)[:70]}")
                        try:
                            close_modal(page, "#modalReceptorCivil")
                            close_modal(page, "#modalDetalleCivil")
                        except Exception:
                            pass
                pages += 1
                if args.max_causas and len(details) >= args.max_causas:
                    break
                if not next_page(page):
                    break
                pace(P_PAGE)
            print(f"      -> {kept_trib} causas de banco en este tribunal")
            pace(P_TRIB)

        mins = (time.time() - t0) / 60.0
        if COUNT_ONLY:
            flush()
            print(f"\n[COUNT] {count_total} bank C-causas across {len(tribs)} tribunal(s) "
                  f"in {mins:.1f} min -> {out}")
        else:
            flush()
            print(f"\n[LISTO] {len(details)} causas en {mins:.1f} min -> {out}")


if __name__ == "__main__":
    main()
