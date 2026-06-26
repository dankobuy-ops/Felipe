"""Semi-manual patente enrichment — runs LOCALLY in a visible browser.

patentechile.com gates POST /resultados behind a Cloudflare *managed challenge*
that headless/automated browsers (and GitHub Actions datacenter IPs) cannot pass.
This script opens a real visible Chromium with a persistent profile: you solve
the Cloudflare challenge once, and it scrapes every plate behind the resulting
cf_clearance cookie. The cookie + profile persist, so most later runs need no
manual solving at all.

Usage (run in YOUR terminal so the browser window is visible):
  python enrich_patentes_local.py --job-id <UUID>
  python enrich_patentes_local.py --job-id <UUID> --dry-run
  python enrich_patentes_local.py --plates BBXB68,KK6929 --dry-run   # ad-hoc

Requires: pip install playwright ; playwright install chromium
"""
import argparse
import os
import random
import sys
import time

# Prefer patchright (patched Playwright that hides the CDP/automation fingerprint
# Cloudflare uses to loop its managed challenge). Falls back to plain Playwright.
try:
    from patchright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _DRIVER = "patchright"
except ImportError:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    _DRIVER = "playwright"

# Reuse the HTML field-extraction helper; the data store is the Google Sheet.
import gstore
from enrich_patentes import _extract_html

PROFILE_DIR = os.path.expanduser("~/.cache/patente-profile")
CHALLENGE_MARKERS = ("verificación de seguridad", "just a moment",
                     "un momento", "checking your browser")
DATA_MARKERS = ("propietario", "marca", "modelo", "n° motor", "nro motor",
                "combustible", "año", "chasis")


def _is_challenge(txt: str) -> bool:
    return any(m in txt for m in CHALLENGE_MARKERS)


def _has_data(txt: str) -> bool:
    return sum(m in txt for m in DATA_MARKERS) >= 2


class CFChallenge(Exception):
    """A Cloudflare challenge blocked this lookup — retryable, NOT a real 'no data'.
    Critically distinct from a genuine 'no encontramos' so the caller retries
    instead of silently recording the plate as missing."""


def _wait_for_form(page, patente, timeout=150):
    """Wait for the homepage search box, tolerating a Cloudflare captcha.

    When CF challenges the homepage, #inputTerm doesn't exist — the old code
    failed fill() in 10s and recorded the plate as not-found. Now we wait for the
    box (auto-clear or you solve the captcha once). Returns False if it never came."""
    deadline = time.monotonic() + timeout
    warned = False
    while time.monotonic() < deadline:
        if page.locator("#inputTerm").count():
            return True
        if not warned:
            txt = (page.inner_text("body") or "").lower()
            if _is_challenge(txt):
                print(f"  [{patente}] ⚠ Cloudflare captcha on the homepage — solve it "
                      f"in the browser window; I'll continue once it clears…")
                warned = True
        page.wait_for_timeout(1_500)
    return False


def scrape_patente(page, patente: str, diag: bool = False) -> dict | None:
    page.goto("https://www.patentechile.com/", wait_until="domcontentloaded",
              timeout=30_000)
    if not _wait_for_form(page, patente):
        raise CFChallenge("homepage search form never appeared")

    page.fill("#inputTerm", patente, timeout=10_000)
    page.click("#searchBtn", timeout=8_000)

    # Wait for results. A challenge here is retryable; "no encontramos" is final.
    deadline = time.monotonic() + 120
    warned = saw_challenge = False
    while time.monotonic() < deadline:
        page.wait_for_timeout(1_500)
        txt = (page.inner_text("body") or "").lower()
        if "no encontr" in txt or "sin resultado" in txt:
            print(f"  [{patente}] no results on site")
            return None
        if _has_data(txt):
            break
        if _is_challenge(txt):
            saw_challenge = True
            if not warned:
                print(f"  [{patente}] ⚠ Cloudflare challenge on results — solve it…")
                warned = True
    else:
        if saw_challenge:
            raise CFChallenge("results challenge did not clear")
        raise CFChallenge(f"timed out waiting for results")

    html = page.content()
    if diag:
        print(f"  [DIAG] url={page.url}")
        print(f"  [DIAG] html[:4000]={html[:4000]}")

    result = _extract_html(html, patente)
    useful = {"rut_propietario", "marca", "modelo", "tipo", "color", "combustible"}
    if not any(k in result for k in useful):
        print(f"  [{patente}] data page loaded but no fields extracted")
        if not diag:
            print(f"  html[:1200]={html[:1200]}")
        return None
    return result


def open_context(pw):
    """Open the persistent, visible browser context used for scraping.

    Under patchright we follow its stealth guidance: real Chrome channel, persistent
    context, no_viewport, and NO --disable-blink-features flag (patchright handles
    the automation-detection surface itself; that flag is itself a tell)."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    print(f"[patentes] browser driver: {_DRIVER}")
    kwargs = dict(
        headless=False,
        no_viewport=True,
        locale="es-CL", timezone_id="America/Santiago",
    )
    try:
        # Real Chrome + patchright is the strongest combo against CF fingerprinting.
        return pw.chromium.launch_persistent_context(PROFILE_DIR, channel="chrome", **kwargs)
    except Exception:
        print("[patentes] real Chrome not found; using bundled Chromium")
        return pw.chromium.launch_persistent_context(PROFILE_DIR, **kwargs)


def enrich_plates(store, page, plates, dry_run=False, _is_retry=False):
    """Scrape (and unless dry_run, upsert) each plate on an already-open page.

    Paces between plates to avoid Cloudflare. Plates blocked by a CF challenge are
    collected and retried in a second pass (the captcha usually clears after one
    solve / a wait), so an intermittent challenge no longer drops a plate as
    'not found'. Returns (found, total)."""
    plates = list(plates)
    found = 0
    challenged = []
    for i, patente in enumerate(plates):
        if i:
            delay = random.uniform(7, 14)  # slower than before — fewer CF challenges
            print(f"  (waiting {delay:.0f}s before next plate…)")
            time.sleep(delay)
        if page.is_closed():
            print("[patentes] browser/page closed — stopping early")
            break
        print(f"[patentes] {patente} ({i+1}/{len(plates)})")
        try:
            result = scrape_patente(page, patente, diag=(i == 0 and not _is_retry))
        except CFChallenge as e:
            print(f"  [{patente}] cloudflare blocked ({e}); will retry")
            challenged.append(patente)
            continue
        except Exception as e:
            print(f"  [{patente}] error ({e}); will retry")
            challenged.append(patente)
            continue
        if not result:
            print("  -> not found")
            continue
        if dry_run:
            found += 1
            print(f"  -> DRY RUN: {result}")
            continue
        try:
            # result keys (patente, rut_propietario, marca, ...) match the Patentes
            # tab columns, so the dict upserts straight into that plate's row.
            store.upsert("Patentes", [result])
            found += 1                       # count only after a successful save
            print(f"  -> saved: {result}")
        except Exception as e:
            print(f"  -> ERROR saving: {e}")  # do NOT count — surfaces real failures

    # Second pass for plates the CF challenge blocked (only once).
    if challenged and not _is_retry:
        print(f"\n[patentes] retrying {len(challenged)} plate(s) blocked by Cloudflare…")
        time.sleep(random.uniform(10, 20))
        f2, _ = enrich_plates(store, page, challenged, dry_run=dry_run, _is_retry=True)
        found += f2
    elif challenged:
        print(f"[patentes] {len(challenged)} still blocked after retry: {challenged}")

    return found, len(plates)


def plates_to_enrich(store):
    """Plates in the Patentes tab that still lack vehicle data."""
    rows = store.read_tab("Patentes")
    to_enrich = sorted(
        r["patente"] for r in rows
        if r.get("patente") and not (r.get("marca") or r.get("modelo")
                                     or r.get("rut_propietario")))
    print(f"[patentes] {len(rows)} in Sheet, {len(to_enrich)} to enrich")
    return to_enrich


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plates", help="Comma-separated plates (ad-hoc; skips the Sheet read)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # The Sheet is only needed to pick targets and/or save. Pure --plates --dry-run
    # needs neither.
    store = None if (args.dry_run and args.plates) else gstore.Store()
    if args.plates:
        to_enrich = sorted({p.strip().upper() for p in args.plates.split(",") if p.strip()})
    else:
        to_enrich = plates_to_enrich(store)

    if not to_enrich:
        print("[patentes] Nothing to do")
        return

    with sync_playwright() as pw:
        ctx = open_context(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        found, total = enrich_plates(store, page, to_enrich, dry_run=args.dry_run)
        try:
            ctx.close()
        except Exception:
            pass
    print(f"\n[patentes] Done -- {found}/{total} enriched")


if __name__ == "__main__":
    main()
