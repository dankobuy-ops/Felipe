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
import json
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
GPS = False     # --gps: resolve georreferencia sub-modals to lat/lng
RESUME = False  # --resume: skip causas already scraped (fill_status='scraped') in Neon
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
                page.click(s, timeout=2000)            # TRUSTED click
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
        a.click(timeout=5000)                          # TRUSTED open
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


def download_doc(api, action, val):
    """GET OJV/<action>?dtaDoc=<val> in-session (shares cookies) -> PDF bytes or None."""
    if not action or not val:
        return None
    try:
        resp = api.get(f"{OJV}/{action.lstrip('/')}", params={"dtaDoc": val}, timeout=60000)
        body = resp.body()
        ct = (resp.headers or {}).get("content-type", "")
        if "pdf" not in ct.lower() and body[:4] != b"%PDF":
            return None
        return body
    except Exception:
        return None


def scrape_causa(page, api, meta):
    """Modal opened by the caller. Parse header/litigantes/cuadernos(historia)/escritos/
    receptor. With GPS: resolve each geo row's lat/lng. With DOCS: download each doc/anexo
    -> Drive and stash the link on the historia row. Close the modal when done."""
    header = parse_header(page)
    litigantes = parse_litigantes(page)
    causa_id = f"{meta.get('tribunalId','')}-{meta['rol']}"
    cuads = cuaderno_options(page) or [{"txt": "1 - Principal", "val": ""}]
    cuadernos = []
    for ci, opt in enumerate(cuads):
        if ci > 0:
            select_cuaderno(page, ci)
            pace(P_STEP)
        cuaderno = opt["txt"]
        cnum = _cuaderno_num(cuaderno)
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
            if DOCS:
                for kind in ("doc", "anexo"):
                    form = hh.get(kind)
                    if not (form and form.get("action") and form.get("val")):
                        continue
                    body = download_doc(api, form["action"], form["val"])
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
    ndoc = sum(1 for c in cuadernos for r in c["historia"] if r.get("doc_url") or r.get("anexo_url"))
    ngeo = sum(1 for c in cuadernos for r in c["historia"] if str(r.get("georref", "")).startswith("="))
    return {**meta, "header": header, "litigantes": litigantes, "cuadernos": cuadernos,
            "escritos": escritos, "receptor": receptor, "n_historia": n_hist,
            "n_docs": ndoc, "n_geo": ngeo}


# ── search / pagination ──────────────────────────────────────────────────────

def fire_search(page):
    """Click Buscar ONCE (TRUSTED) and poll up to ~45s for rows — the results AJAX is slow.
    Returns True if rows rendered, False on a genuine 'sin resultados'."""
    try:
        page.click("#btnConConsultaFec", timeout=5000)   # TRUSTED
    except Exception as e:
        print(f"    [warn] buscar: {e}")
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
    try:
        page.click("#sigId", timeout=4000)             # TRUSTED
    except Exception:
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
    ap.add_argument("--gps", action="store_true", help="resolve georreferencia sub-modals -> lat/lng")
    ap.add_argument("--no-search", action="store_true",
                    help="WAF-safe: do NOT select_option/search; harvest the CURRENT results "
                         "table (operator already searched). Only the displayed tribunal.")
    ap.add_argument("--resume", action="store_true",
                    help="skip causas already scraped (fill_status='scraped') in Neon")
    args = ap.parse_args()
    global DOCS, GPS, RESUME
    DOCS, GPS, RESUME = args.docs, args.gps, args.resume

    print(f"Conectando a Chrome (puerto CDP {args.port})...")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        ctx = browser.contexts[0]
        api = ctx.request
        page = find_ojv_page(ctx)
        if not page:
            sys.exit("[ERROR] No encuentro ninguna pestana. Abre OJV en esa ventana.")
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
        details, t0 = [], time.time()

        def flush():
            out.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
        for ti, tb in enumerate(tribs, 1):
            if args.max_causas and len(details) >= args.max_causas:
                break
            if not args.no_search:
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
            seen, pages, kept_trib = set(), 0, 0
            done = scraped_rols(tb["v"]) if RESUME else set()
            if done:
                print(f"      (resume: {len(done)} already scraped here — skipping them)")
            while pages < 80:
                if args.max_causas and len(details) >= args.max_causas:
                    break
                causas = page_bank_causas(page)
                for c in causas:
                    if c["rol"] in seen or c["rol"] in done:
                        seen.add(c["rol"])
                        continue
                    if args.max_causas and len(details) >= args.max_causas:
                        break
                    seen.add(c["rol"])
                    pace(P_CAUSA)
                    try:
                        page.locator("#dtaTableDetalleFecha tbody tr").nth(c["i"]).locator(
                            "a[onclick*='detalleCausaCivil']").first.click(timeout=8000)  # TRUSTED open
                        page.wait_for_function(
                            "rol=>{var m=document.querySelector('#modalDetalleCivil');"
                            " return m && m.innerText.indexOf('ROL')>=0 && m.innerText.indexOf(rol)>=0;}",
                            arg=c["rol"], timeout=30000)   # detail modal can be slow
                        page.wait_for_timeout(600)
                        rec = scrape_causa(page, api, {
                            "rol": c["rol"], "caratulado": c["car"], "fecha": c["fecha"],
                            "tribunal": c["trib"], "tribunalSel": tb["t"], "tribunalId": tb["v"],
                            "corte": corte, "rango": f"{desde} a {hasta}"})
                        if args.proc and norm(rec["header"].get("procedimiento", "")) != norm(args.proc):
                            continue     # scraped but doesn't match the proc filter -> drop
                        details.append(rec)
                        kept_trib += 1
                        flush()                          # incremental save (survives interrupts)
                        print(f"      OK {c['rol']:<13} lit={len(rec['litigantes'])} "
                              f"cuad={len(rec['cuadernos'])} hist={rec['n_historia']} "
                              f"esc={len(rec['escritos'])} rec={len(rec['receptor'])} "
                              f"docs={rec['n_docs']} geo={rec['n_geo']}  (tot {len(details)})")
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

        flush()
        mins = (time.time() - t0) / 60.0
        print(f"\n[LISTO] {len(details)} causas en {mins:.1f} min -> {out}")


if __name__ == "__main__":
    main()
