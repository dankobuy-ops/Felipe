"""Local patente enrichment — drives a real Google Chrome to beat Cloudflare.

patentechile.com gates its results behind a Cloudflare Turnstile that loops
forever on an automation-launched browser. The trick (see patente_browser.py):
launch a NORMAL Chrome, let a human solve the challenge once with nothing
attached, then attach over CDP to scrape. The solved cookie persists, so most
runs need no manual click at all.

Usage (run in YOUR terminal so the Chrome window is visible):
  python enrich_patentes_local.py                       # enrich un-filled plates in the Sheet
  python enrich_patentes_local.py --dry-run
  python enrich_patentes_local.py --plates BBXB68,KK6929 --dry-run   # ad-hoc

Requires: pip install playwright ; and Google Chrome installed.
"""
import argparse
import os
import random
import time
from datetime import date

import gstore
from enrich_patentes import _extract_html
from patente_browser import Session, CFChallenge, find_chrome as _find_chrome, HOME

CHALLENGE_MARKERS = ("verificación de seguridad", "just a moment",
                     "un momento", "checking your browser", "verify you are human",
                     "performing security verification")
DATA_MARKERS = ("propietario", "marca", "modelo", "n° motor", "nro motor",
                "combustible", "año", "chasis")
# The site's genuine "no data" page reads "No SE encontraron resultados" — the old
# "no encontr" marker missed it (the "se" breaks the match), so unknown plates hung
# the full timeout instead of being skipped quickly.
NORESULT_MARKERS = ("no se encontraron resultados", "no se encontr", "no encontr",
                    "sin resultado", "no existe", "no hay resultado")

# Adaptive pacing between plates. It starts brisk and self-tunes: every clean
# request nudges the wait DOWN toward DELAY_MIN; every Cloudflare block bumps it
# UP toward DELAY_MAX. Override via env vars (e.g. PATENTE_DELAY_MIN=6).
DELAY_MIN   = float(os.environ.get("PATENTE_DELAY_MIN",   "5"))
DELAY_MAX   = float(os.environ.get("PATENTE_DELAY_MAX",   "15"))
DELAY_START = float(os.environ.get("PATENTE_DELAY_START", "6"))


def _is_challenge(txt: str) -> bool:
    return any(m in txt for m in CHALLENGE_MARKERS)


def _has_data(txt: str) -> bool:
    return sum(m in txt for m in DATA_MARKERS) >= 2


def _no_result(txt: str) -> bool:
    return any(m in txt for m in NORESULT_MARKERS)


def _fill(page, sel, value):
    """Fill a field, falling back to a JS value-set if an ad overlay blocks it."""
    try:
        page.fill(sel, value, timeout=8_000)
    except Exception:
        page.eval_on_selector(
            sel, "(el, v) => { el.value = v; "
                 "el.dispatchEvent(new Event('input', {bubbles: true})); }", value)


def _click_search(page):
    """Trigger the search by invoking the button's own click() in JS.

    The site wires its search to #searchBtn via addEventListener('click', …).
    Playwright's coordinate-based page.click() frequently lands on nothing (the
    button sits under an ad or just off-viewport) yet returns WITHOUT error, so the
    search silently never fires and the plate looks like "no aceptó". Calling the
    element's own .click() invokes the handler directly and reliably — and, being a
    scripted call, it isn't swallowed by the ad's click interceptor. A real click is
    only a last resort."""
    try:
        page.eval_on_selector("#searchBtn", "el => el.click()")
    except Exception:
        try:
            page.click("#searchBtn", timeout=4_000)
        except Exception:
            pass


def _clear_vignette(page, timeout=10):
    """Dismiss Google AdSense's full-page 'vignette' interstitial.

    With ads allowed, AdSense drops a vignette on navigation: the URL gets a
    '#google_vignette' hash and an aswift ad iframe covers the search button,
    swallowing the click — so the site looks like it 'no aceptó la patente' even
    though the plate was typed in fine. The vignette is a fake history state, so
    history.back() closes it (exactly what a human does by dismissing the ad).
    Returns once the search button is actually clickable (not under an ad), or
    False after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = page.evaluate("""() => {
            const btn = document.querySelector('#searchBtn');
            let covered = true;
            if (btn) {
                const b = btn.getBoundingClientRect();
                if (b.width) {
                    const el = document.elementFromPoint(b.left + b.width/2, b.top + b.height/2);
                    covered = !el || (el !== btn && !btn.contains(el));
                }
            }
            return {covered, vignette: location.hash.includes('google_vignette')};
        }""")
        if not state["covered"]:
            return True
        try:
            if state["vignette"]:
                page.evaluate("() => window.history.back()")   # pop the vignette state
            else:
                page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(700)
    return False


def _submit_search(session, page, patente, tries=3):
    """Fill + submit, defeating the vignette ad that eats the first click.

    Order matters: the vignette *ablates* (removes) the search box from the DOM
    while it's showing, so we must clear it BEFORE filling, or #inputTerm isn't
    there yet. Clear → fill → click; if we haven't reached /resultados, clear and
    retry (the search click itself can spawn a fresh vignette). Returns True once
    the results page loads."""
    for _ in range(tries):
        _clear_vignette(page)                 # dismiss the ad first so the form re-appears
        try:
            page.wait_for_selector("#inputTerm", state="visible", timeout=8_000)
        except Exception:
            # form still missing — the ad likely navigated the page; reload home.
            page = session.goto_home()
            _clear_vignette(page)
        _fill(page, "#inputTerm", patente)
        session.dismiss_popups()
        _clear_vignette(page)                 # a fresh vignette may have popped on fill
        _click_search(page)
        for _ in range(8):                    # ~4s grace for the navigation
            page.wait_for_timeout(500)
            if "/resultados" in (page.url or ""):
                return True
        _clear_vignette(page)                 # the click may have popped a new vignette
    return "/resultados" in (page.url or "")


def scrape_patente(session, patente: str, diag: bool = False) -> dict | None:
    """Search one plate on an already-past-Cloudflare session. Returns the parsed
    fields, None if the site has no data, or raises CFChallenge if the wall
    reappeared (so the caller retries after a re-solve)."""
    # Fresh navigation to the homepage every time — never the results page's
    # "Buscar otra" button. A full (re)load re-triggers the site's pop-up ad, which
    # a real, ad-accepting browser is expected to open. Let it render and THEN close
    # it; that's what stops patentechile.com from flagging us as a bot and serving a
    # bogus "sin resultados" page for plates that actually have data.
    page = session.goto_home()
    session.let_ad_settle()                   # let the pop-up ad open + load, then close it
    # Fill + submit, clearing Google's #google_vignette interstitial (an ad iframe
    # that covers the search button and swallows the click). Retries until the
    # results page loads, so the site stops looking like it "no aceptó la patente".
    _submit_search(session, page, patente)

    start = time.monotonic()
    deadline = start + 45
    saw_challenge = False
    nores_since = None
    while time.monotonic() < deadline:
        page.wait_for_timeout(700)
        try:
            txt = (page.inner_text("body") or "").lower()
        except Exception:
            txt = ""
        if _has_data(txt):
            break
        if _is_challenge(txt):
            saw_challenge = True
            continue
        if _no_result(txt):
            # "No se encontraron resultados. Vuelve a consultar en unos segundos…"
            # can be a brief loading placeholder, so allow a short grace for data
            # to appear before concluding the plate has no record.
            if nores_since is None:
                nores_since = time.monotonic()
            elif time.monotonic() - nores_since > 12:
                print(f"  [{patente}] sin datos en el sitio")
                return None
            continue
        # The search never left the homepage — the site rejected the input.
        if "/resultados" not in (page.url or "") and time.monotonic() - start > 12:
            print(f"  [{patente}] el sitio no aceptó la patente (sin datos)")
            return None
    else:
        if nores_since is not None:
            print(f"  [{patente}] sin datos en el sitio")
            return None
        if saw_challenge:
            raise CFChallenge("el desafío de Cloudflare reapareció en los resultados")
        raise CFChallenge("tiempo agotado esperando resultados")

    html = page.content()
    if diag:
        print(f"  [DIAG] url={page.url}")

    result = _extract_html(html, patente)
    useful = {"rut_propietario", "marca", "modelo", "tipo", "color", "combustible"}
    if not any(k in result for k in useful):
        print(f"  [{patente}] la página cargó pero no se extrajeron campos")
        return None
    return result


def enrich_plates(store, session, plates, dry_run=False, _is_retry=False):
    """Scrape (and unless dry_run, upsert) each plate. Adaptive pacing; plates
    blocked by a re-challenge are retried once. Returns (found, total)."""
    plates = list(plates)
    found = 0
    challenged = []
    delay = max(DELAY_MIN, min(DELAY_MAX, DELAY_START))
    for i, patente in enumerate(plates):
        if i:
            gap = random.uniform(delay * 0.8, delay * 1.2)    # target human gap between searches
            # Fresh window per plate: close Chrome and reopen it so each plate starts
            # from a clean page with no leftover ad/vignette state (the profile
            # persists, so the solved Cloudflare cookie carries over — no re-solve).
            # Opening/closing a window IS part of a human's gap between searches, so we
            # time the restart and only sleep the leftover, instead of adding it on top.
            t0 = time.monotonic()
            try:
                print("  (reabriendo ventana de Chrome para la siguiente patente…)")
                session.restart()
            except Exception as e:
                print(f"  [aviso] no se pudo reabrir la ventana ({e}); sigo con la actual")
            leftover = gap - (time.monotonic() - t0)
            if leftover > 0:
                print(f"  (pausa {leftover:.0f}s para parecer humano…)")
                time.sleep(leftover)
        if not session.alive():
            print("[patentes] la ventana de Chrome se cerró — deteniendo")
            break
        print(f"[patentes] {patente} ({i+1}/{len(plates)})")
        try:
            result = scrape_patente(session, patente, diag=(i == 0 and not _is_retry))
        except CFChallenge as e:
            delay = min(DELAY_MAX, delay * 1.8)               # tripped — back off
            print(f"  [{patente}] Cloudflare ({e}); reintento luego")
            challenged.append(patente)
            continue
        except Exception as e:
            print(f"  [{patente}] error ({e}); reintento luego")
            challenged.append(patente)
            continue
        # clean request (data or a real 'no results') — ease the pace back down
        delay = max(DELAY_MIN, delay * 0.85)
        if not result:
            print("  -> sin datos")
            # Mark it checked so it isn't re-searched every run (site has no record).
            if not dry_run and store is not None:
                try:
                    store.upsert("Patentes", [{"patente": patente,
                                               "estado": f"sin datos {date.today().isoformat()}"}])
                except Exception as e:
                    print(f"  -> (no se pudo marcar sin datos: {e})")
            continue
        if dry_run:
            found += 1
            print(f"  -> DRY RUN: {result}")
            continue
        try:
            # result keys (patente, rut_propietario, marca, ...) match the Patentes
            # tab columns, so the dict upserts straight into that plate's row.
            result["estado"] = "con datos"
            store.upsert("Patentes", [result])
            found += 1
            print(f"  -> guardado: {result}")
        except Exception as e:
            print(f"  -> ERROR guardando: {e}")

    if challenged and not _is_retry:
        print(f"\n[patentes] reintentando {len(challenged)} patente(s) bloqueada(s)…")
        time.sleep(random.uniform(8, 15))
        f2, _ = enrich_plates(store, session, challenged, dry_run=dry_run, _is_retry=True)
        found += f2
    elif challenged:
        print(f"[patentes] {len(challenged)} sin resolver tras reintento: {challenged}")

    return found, len(plates)


def plates_to_enrich(store):
    """Plates in the Patentes tab that still lack vehicle data."""
    rows = store.read_tab("Patentes")
    to_enrich = sorted(
        r["patente"] for r in rows
        if r.get("patente") and not (r.get("marca") or r.get("modelo")
                                     or r.get("rut_propietario"))
        and not r.get("estado"))          # skip plates already checked (no data)
    print(f"[patentes] {len(rows)} en la planilla, {len(to_enrich)} por enriquecer")
    return to_enrich


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plates", help="Patentes separadas por coma (ad-hoc; omite la planilla)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # The Sheet is only needed to pick targets and/or save. Pure --plates --dry-run
    # needs neither.
    store = None if (args.dry_run and args.plates) else gstore.Store()
    if store is not None:
        store.ensure_headers("Patentes")          # make sure the 'estado' column exists
    if args.plates:
        to_enrich = sorted({p.strip().upper() for p in args.plates.split(",") if p.strip()})
    else:
        to_enrich = plates_to_enrich(store)

    if not to_enrich:
        print("[patentes] Nada que hacer")
        return

    session = Session().start()
    try:
        found, total = enrich_plates(store, session, to_enrich, dry_run=args.dry_run)
    finally:
        session.close()
    print(f"\n[patentes] Listo — {found}/{total} enriquecidas")


if __name__ == "__main__":
    main()
