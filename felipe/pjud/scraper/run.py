"""Scraper for Poder Judicial Virtual — Oficina Judicial Virtual (OJV).

Public guest access, no captcha, no login. Locked scope (see pjud/HANDOFF.md):
  - Civil, C.A. de Arica, 1º Juzgado de Letras de Arica (tribunal id 'arica-1').
  - Search by Rut Persona Jurídica (test bank: Banco de Chile 97004000-5).
  - Keep only causas whose ROL starts with 'C'.
  - Download docs/anexos/ebook PDFs to a Google Drive "Documentos" folder.

Flow (verified via CDP recon):
  1. home/index.php → close AVISO modal → "Consulta causas"
  2. indexN.php → tab "Búsqueda por Rut Persona Jurídica" → fill rut/dv/era +
     competencia(Civil=3) → corte(Arica=10) → tribunal(Letras 1=2) → "Buscar"
  3. results table (has "Caratulado") → each 🔍 = detalleCausaCivil('<JWT>')
  4. #modalDetalleCivil → header + iterate #selCuaderno → historia / litigantes /
     escritos panes; download docs per historia row; anexos sub-modal.

Writes incrementally into a Google Sheet (8 tabs) + Drive folder via gstore. Run
setup once (`python run.py --setup`), then run LOCALLY (`python run.py --headed
--limit 1`), verify against live, then CI.
"""

import argparse
import os
import re
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

import gstore

# ── Constants ─────────────────────────────────────────────────────────────────

OJV       = "https://oficinajudicialvirtual.pjud.cl"
HOME      = f"{OJV}/home/index.php"
TRIBUNAL  = {"id": "arica-1", "corte": "C.A. de Arica",
             "tribunal": "1º Juzgado de Letras de Arica"}
# Select values mapped during recon (may shift — logged on mismatch).
VAL_COMPETENCIA = "3"   # Civil
VAL_CORTE       = "10"  # C.A. de Arica
VAL_TRIBUNAL    = "2"   # 1º Juzgado de Letras de Arica

SCRATCH = Path(os.environ.get("TEMP", "/tmp")) / "pjud_pdfs"

STORE = None       # gstore.Store, set in main() (None under --dry-run)
DRY = False        # --dry-run: verify live nav/parse without any writes
SKIP_DOCS = False  # --skip-docs: scrape metadata only, no PDF download/upload


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
    page.goto(HOME, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(2000)

    log("[NAV] accesoConsultaCausas() → indexN.php…")
    page.evaluate("accesoConsultaCausas()")
    page.wait_for_url("**/indexN.php**", timeout=25_000)
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2500)
    log(f"[NAV] search page -> {page.url}")
    return page


def run_search(page, rut_sin_dv, dv, era):
    """Select the Rut Persona Jurídica tab, fill fields + cascading selects, Buscar.
    Returns True if the results table rendered."""
    page.click("a:has-text('Rut Persona Jurídica')")
    page.wait_for_timeout(800)

    _select(page, "#jurCompetencia", VAL_COMPETENCIA, "competencia")
    page.wait_for_timeout(1500)   # corte populates via AJAX
    _select(page, "#corteJur", VAL_CORTE, "corte")
    page.wait_for_timeout(1500)   # tribunal populates via AJAX
    _select(page, "#jurTribunal", VAL_TRIBUNAL, "tribunal")

    page.fill("#rutJur", str(rut_sin_dv))
    page.fill("#dvJur", str(dv))
    page.fill("#eraJur", str(era))

    log(f"[NAV] Buscar (rut {rut_sin_dv}-{dv}, era {era})…")
    # Clear any prior results so wait_for_selector waits for the fresh table.
    page.evaluate("() => { const t = document.querySelector('#dtaTableDetalleJuridica tbody');"
                  " if (t) t.innerHTML=''; }")
    page.click("#btnConConsultaJur")
    try:
        page.wait_for_selector("#dtaTableDetalleJuridica tbody tr", timeout=20_000)
        page.wait_for_timeout(1200)
        return True
    except PlaywrightTimeout:
        log(f"[INFO] no results for era {era} (table never populated)")
        return False


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

def scrape_causa(page, api, causa):
    rol = causa["rol"]
    log(f"\n[CAUSA] {rol} — {causa['caratulado'][:60]}")
    open_detail(page, causa["jwt"])
    header = parse_header(page)

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
                ebook_url = upload_pdf(f"{rol}/ebook.pdf".replace(" ", "_"), body)
            except Exception as e:
                log(f"[WARN] ebook upload {rol}: {e}")

    upsert("pjud_causas", [{
        "rol": rol,
        **header,
        "tribunal": TRIBUNAL["id"],
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
        lit_rows.append({"id": f"{rol}::{rut}", "causa": rol, "rut": rut,
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
                    "ID": f"{rol}::receptor::{i}",
                    "Cuaderno ID": f"{rol}::{full}",
                    "Nombre": rr["nombre"], "Fecha": rr["fecha"],
                    "Estado": rr["estado"],
                })
            close_overlay(page, "#modalReceptorCivil")
        except Exception as e:
            log(f"[WARN] receptor {rol}: {e}")
    upsert("pjud_notificaciones", notif_rows)

    # Cuadernos (iterate selCuaderno) -> historia rows + docs/anexos
    cuad_rows, esc_rows, doc_rows, anex_rows = [], [], [], []
    for i, opt in enumerate(cuads):
        cuaderno = opt["txt"]
        if i > 0:                       # cuaderno 0 is already loaded on open
            select_cuaderno(page, i)
        seen = {}
        for h in parse_historia(page):
            folio = h["folio"]
            n = seen.get(folio, 0) + 1
            seen[folio] = n
            cid = f"{rol}::{cuaderno}::{folio}::{n}"
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
                "id": cid, "causa": rol, "cuaderno": cuaderno, "folio": folio,
                "etapa": h["etapa"], "tramite": h["tramite"],
                "descripcion_tramite": h["desc"], "fecha_tramite": h["fecha"],
                "foja": h["foja"], "georref": georref,
            })
            # documents on this row
            for kind, form, sink in (("doc", h["doc"], doc_rows),
                                     ("anexo", h["anexo"], anex_rows)):
                if not form or SKIP_DOCS:
                    continue
                body = download_form(api, form)
                if not body:
                    continue
                obj = f"{rol}/{cuaderno}/{folio}-{n}-{kind}.pdf".replace(" ", "_")
                try:
                    url = upload_pdf(obj, body)
                except Exception as e:
                    log(f"[WARN] upload {obj}: {e}")
                    continue
                if kind == "doc":
                    sink.append({"id": cid + "::doc", "cuaderno": cid,
                                 "origen": form["action"], "folio": folio,
                                 "descripcion": h["desc"], "url": url})
                else:
                    sink.append({"id": cid + "::anexo", "cuaderno": cid,
                                 "origen": form["action"], "folio": folio,
                                 "fecha": h["fecha"], "referencia": h["desc"],
                                 "url": url})
        # escritos belong to the cuaderno; attach to the first historia id of it
        anchor = cuad_rows[-1]["id"] if cuad_rows else f"{rol}::{cuaderno}::::1"
        for i, e in enumerate(parse_escritos(page), 1):
            esc_rows.append({"id": f"{rol}::{cuaderno}::esc::{i}",
                             "cuaderno": anchor, **e})

    upsert("pjud_cuadernos", cuad_rows)
    upsert("pjud_escritos", esc_rows)
    upsert("pjud_documentos", doc_rows)
    upsert("pjud_anexos", anex_rows)
    geo_n = sum(1 for c in cuad_rows if str(c.get("georref", "")).startswith("="))
    log(f"[CAUSA] {rol}: {len(cuad_rows)} historia, {len(lit_rows)} litigantes, "
        f"{len(notif_rows)} receptor, {geo_n} georref, {len(doc_rows)} docs, "
        f"{len(anex_rows)} anexos, {len(esc_rows)} escritos")

    # close modal for the next causa
    for sel in ("#modalDetalleCivil button.close", "#modalDetalleCivil .close",
                "body"):
        try:
            page.click(sel, timeout=1500)
            break
        except Exception:
            pass
    page.wait_for_timeout(600)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
    p = argparse.ArgumentParser(description="PJUD OJV scraper (Arica/Civil/Tribunal-1).")
    p.add_argument("--setup", action="store_true",
                   help="One-time: OAuth login + provision the Drive folder/Sheet, then exit.")
    p.add_argument("--rut", default="97004000", help="RUT sin dígito verificador (default: Banco de Chile).")
    p.add_argument("--dv", default="5", help="Dígito verificador.")
    p.add_argument("--era", default="2026",
                   help="Año (#eraJur). Single '2024' or range '2018-2026'.")
    p.add_argument("--limit", type=int, default=0, help="Max causas per year (0 = all).")
    p.add_argument("--headed", action="store_true", help="Show the browser.")
    p.add_argument("--dry-run", action="store_true",
                   help="Verify live nav/parse without any Supabase reads/writes.")
    p.add_argument("--skip-docs", action="store_true",
                   help="Scrape metadata only — no PDF download/upload (fast).")
    return p.parse_args()


def main():
    global STORE, DRY, SKIP_DOCS
    args = parse_args()

    if args.setup:
        gstore.provision()
        log("[SETUP] done. Now run: python run.py --headed --limit 1")
        return

    DRY = args.dry_run
    SKIP_DOCS = args.skip_docs
    if not DRY:
        STORE = gstore.Store()
    SCRATCH.mkdir(parents=True, exist_ok=True)

    # seed the single tribunal (referenced by Causas.tribunal)
    upsert("pjud_tribunales", [TRIBUNAL])

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
            locale="es-CL", accept_downloads=True,
            viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        search_page = reach_search_form(page, context)
        # APIRequestContext shares this context's cookies → in-session downloads.
        api = context.request

        eras = expand_eras(args.era)
        log(f"[INFO] eras: {eras}")
        ok = total = 0
        for era in eras:
            if not run_search(search_page, args.rut, args.dv, era):
                continue
            causas = collect_causas(search_page)
            if args.limit:
                causas = causas[:args.limit]
                log(f"[INFO] era {era}: limited to {len(causas)} causa(s)")
            for c in causas:
                total += 1
                try:
                    scrape_causa(search_page, api, c)
                    ok += 1
                except Exception as e:
                    log(f"[ERR] causa {c['rol']}: {e}")
        log(f"\n[DONE] {ok}/{total} causas scraped across {len(eras)} year(s).")
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
