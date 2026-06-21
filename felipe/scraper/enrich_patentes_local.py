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

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Reuse the Supabase + extraction helpers from the CI module.
from enrich_patentes import (
    fetch_checkpoints, collect_plates, fetch_existing, upsert,
    _extract_html, SUPABASE_URL, SUPABASE_KEY,
)

PROFILE_DIR = os.path.expanduser("~/.cache/patente-profile")
CHALLENGE_MARKERS = ("verificación de seguridad", "just a moment",
                     "un momento", "checking your browser")
DATA_MARKERS = ("propietario", "marca", "modelo", "n° motor", "nro motor",
                "combustible", "año", "chasis")


def _is_challenge(txt: str) -> bool:
    return any(m in txt for m in CHALLENGE_MARKERS)


def _has_data(txt: str) -> bool:
    return sum(m in txt for m in DATA_MARKERS) >= 2


def scrape_patente(page, patente: str, diag: bool = False) -> dict | None:
    try:
        page.goto("https://www.patentechile.com/", wait_until="domcontentloaded",
                  timeout=30_000)
        page.fill("#inputTerm", patente, timeout=10_000)
        page.click("#searchBtn", timeout=8_000)

        # Wait up to 2 min for results — long enough for you to solve a Cloudflare
        # challenge the first time. Polls until real data appears or "no results".
        deadline = time.monotonic() + 120
        warned = False
        while time.monotonic() < deadline:
            page.wait_for_timeout(1_500)
            txt = (page.inner_text("body") or "").lower()
            if "no encontr" in txt or "sin resultado" in txt:
                print(f"  [{patente}] no results on site")
                return None
            if _has_data(txt):
                break
            if _is_challenge(txt) and not warned:
                print(f"  [{patente}] ⚠ Cloudflare challenge — solve it in the "
                      f"browser window; I'll continue automatically once it clears…")
                warned = True
        else:
            print(f"  [{patente}] timed out waiting for results/challenge")
            return None

        html = page.content()
        if diag:
            print(f"  [DIAG] url={page.url}")
            print(f"  [DIAG] html[:4000]={html[:4000]}")

        result = _extract_html(html, patente)
        useful = {"rut", "marca", "modelo", "tipo", "color", "combustible"}
        if not any(k in result for k in useful):
            print(f"  [{patente}] data page loaded but no fields extracted")
            if not diag:
                print(f"  html[:1200]={html[:1200]}")
            return None
        return result

    except Exception as e:
        print(f"  [{patente}] ERROR: {e}")
        return None


def open_context(pw):
    """Open the persistent, visible browser context used for scraping."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    kwargs = dict(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
        locale="es-CL", timezone_id="America/Santiago",
        viewport={"width": 1280, "height": 900},
    )
    try:
        # Real Chrome has the best chance against Cloudflare's fingerprinting.
        return pw.chromium.launch_persistent_context(PROFILE_DIR, channel="chrome", **kwargs)
    except Exception:
        print("[patentes] real Chrome not found; using bundled Chromium")
        return pw.chromium.launch_persistent_context(PROFILE_DIR, **kwargs)


def enrich_plates(page, plates, dry_run=False):
    """Scrape (and unless dry_run, upsert) each plate on an already-open page.

    Paces between plates to avoid Cloudflare's rate limiter. Stops early if the
    browser is closed or a session error hits (usually a rate-limit ban).
    Returns (found, total)."""
    plates = list(plates)
    found = 0
    for i, patente in enumerate(plates):
        if i:
            delay = random.uniform(5, 11)
            print(f"  (waiting {delay:.0f}s before next plate…)")
            time.sleep(delay)
        if page.is_closed():
            print("[patentes] browser/page closed — stopping early")
            break
        print(f"[patentes] {patente} ({i+1}/{len(plates)})")
        try:
            result = scrape_patente(page, patente, diag=(i == 0))
        except Exception as e:
            print(f"  [{patente}] session error ({e}); stopping — likely rate-limited.")
            break
        if not result:
            print("  -> not found")
            continue
        found += 1
        if dry_run:
            print(f"  -> DRY RUN: {result}")
            continue
        try:
            upsert(result)
            print(f"  -> saved: {result}")
        except Exception as e:
            print(f"  -> ERROR saving: {e}")
    return found, len(plates)


def job_to_enrich(job_id):
    """Return the sorted list of plates in a job that aren't yet in the DB."""
    rows = fetch_checkpoints(job_id)
    all_plates = collect_plates(rows)
    existing = fetch_existing(all_plates)
    to_enrich = sorted(all_plates - existing)
    print(f"[patentes] {len(all_plates)} in job, {len(existing)} in DB, "
          f"{len(to_enrich)} to enrich")
    return to_enrich


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-id")
    ap.add_argument("--plates", help="Comma-separated plates (skips Supabase read)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.plates:
        to_enrich = sorted({p.strip().upper() for p in args.plates.split(",") if p.strip()})
    else:
        if not args.job_id:
            sys.exit("ERROR: pass --job-id or --plates")
        if not (SUPABASE_URL and SUPABASE_KEY):
            sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY")
        to_enrich = job_to_enrich(args.job_id)

    if not to_enrich:
        print("[patentes] Nothing to do")
        return

    with sync_playwright() as pw:
        ctx = open_context(pw)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        found, total = enrich_plates(page, to_enrich, dry_run=args.dry_run)
        try:
            ctx.close()
        except Exception:
            pass
    print(f"\n[patentes] Done -- {found}/{total} enriched")


if __name__ == "__main__":
    main()
