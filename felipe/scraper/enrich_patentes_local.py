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
DELAY_MIN   = float(os.environ.get("PATENTE_DELAY_MIN",   "4"))
DELAY_MAX   = float(os.environ.get("PATENTE_DELAY_MAX",   "14"))
DELAY_START = float(os.environ.get("PATENTE_DELAY_START", "5"))


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
    """Trigger the search. Normal click first; if an ad overlay intercepts it,
    fire the button's own click() via JS so the search still runs."""
    try:
        page.click("#searchBtn", timeout=5_000)
    except Exception:
        page.eval_on_selector("#searchBtn", "el => el.click()")


def scrape_patente(session, patente: str, diag: bool = False) -> dict | None:
    """Search one plate on an already-past-Cloudflare session. Returns the parsed
    fields, None if the site has no data, or raises CFChallenge if the wall
    reappeared (so the caller retries after a re-solve)."""
    page = session.goto_home()
    session.dismiss_popups()                 # clear any ad tab/overlay first
    _fill(page, "#inputTerm", patente)
    session.dismiss_popups()
    _click_search(page)

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
            wait = random.uniform(delay * 0.8, delay * 1.2)   # jitter — stay human
            print(f"  (esperando {wait:.0f}s antes de la siguiente patente…)")
            time.sleep(wait)
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
