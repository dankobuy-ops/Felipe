"""Look up vehicle info for patentes found in job checkpoints.

Uses Playwright + stealth mode to bypass Cloudflare on patentechile.com.

Usage:
  python enrich_patentes.py --job-id <UUID>
  python enrich_patentes.py --job-id <UUID> --dry-run
"""
import argparse
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# playwright-stealth API differs across versions (v1: stealth_sync(page);
# v2: Stealth().apply_stealth_sync(page)). Stay resilient so an unpinned
# install can't hard-fail the run before any plate is scraped.
def _apply_stealth(page):
    try:
        from playwright_stealth import stealth_sync  # v1
        stealth_sync(page)
        return
    except Exception:
        pass
    try:
        from playwright_stealth import Stealth  # v2
        Stealth().apply_stealth_sync(page)
    except Exception as e:
        print(f"[patentes] stealth unavailable ({e}); continuing without it")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

PLATE_RE = re.compile(r'^[A-Z]{2,4}\d{2,4}$')

_FIELDS = {
    "rut":         ["rut propietario", "rut del propietario", "propietario", "rut"],
    "tipo":        ["tipo vehículo", "tipo vehiculo", "tipo"],
    "marca":       ["marca"],
    "modelo":      ["modelo"],
    "anio":        ["año fabricación", "año del vehículo", "año modelo", "año", "ano"],
    "color":       ["color"],
    "num_motor":   ["n° motor", "nro motor", "numero motor", "número motor", "motor"],
    "num_chasis":  ["n° chasis", "nro chasis", "numero chasis", "número chasis", "chasis"],
    "combustible": ["combustible"],
}


# ── Supabase helpers ───────────────────────────────────────────────────────────

def _sb():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def fetch_checkpoints(job_id):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/checkpoints",
        headers=_sb(),
        params={"select": "record_id,text", "job_id": f"eq.{job_id}"},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()


def fetch_existing(plates: set) -> set:
    if not plates:
        return set()
    in_val = ",".join(sorted(plates))
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/patentes",
        headers=_sb(),
        params={"select": "patente", "patente": f"in.({in_val})"},
        timeout=30,
    )
    r.raise_for_status()
    return {row["patente"] for row in r.json()}


def upsert(data: dict):
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/patentes",
        headers={**_sb(), "Content-Type": "application/json",
                 "Prefer": "resolution=merge-duplicates"},
        json=data,
        timeout=30,
    )
    r.raise_for_status()


# ── Plate extraction ───────────────────────────────────────────────────────────

def extract_plates(field: str) -> list[str]:
    out = []
    for line in (field or "").split("\n"):
        p = re.sub(r"[\s\-]", "", line).strip().upper()
        if p and PLATE_RE.match(p):
            out.append(p)
    return out


def collect_plates(rows) -> set:
    plates = set()
    for row in rows:
        rid = row.get("record_id", "")
        if rid.startswith("__"):
            continue
        try:
            d = json.loads(row.get("text") or "{}")
        except Exception:
            continue
        causa = d.get("causa") or {}
        for p in extract_plates(causa.get("placa_patente") or d.get("placa_patente") or ""):
            plates.add(p)
        for dem in d.get("demandados") or []:
            for p in extract_plates(dem.get("patente") or dem.get("placa_patente") or ""):
                plates.add(p)
    return plates


# ── HTML data extraction ───────────────────────────────────────────────────────

def _classify(raw: str) -> str | None:
    label = re.sub(r"[:\-°]", "", (raw or "")).lower().strip()
    for key, candidates in _FIELDS.items():
        for c in candidates:
            if label == c or label.startswith(c):
                return key
    return None


def _extract_html(html: str, patente: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out = {"patente": patente}

    def set_val(key, val):
        if key and key not in out and val:
            v = val.strip()
            if v and len(v) < 200:
                out[key] = v

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) >= 2:
            key = _classify(cells[0].get_text())
            if key:
                set_val(key, cells[-1].get_text())

    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            set_val(_classify(dt.get_text()), dd.get_text())

    for el in soup.find_all(["strong", "b", "span", "label", "th", "td"]):
        key = _classify(el.get_text())
        if not key or key in out:
            continue
        sib = el.find_next_sibling()
        if sib:
            set_val(key, sib.get_text())

    return out


# ── Playwright stealth scraper ─────────────────────────────────────────────────

SEARCH_URL = "https://www.patentechile.com/web-app/"
# The plate lookup is a JS app: it encrypts the term (crypto-js) and POSTs to
# admin-ajax.php, then renders results into the DOM. There is no static URL
# (/patente/<plate> 301s to home; ?s=<plate> is WP search with no plate data).
# So we drive the real form and read the rendered results.


def scrape_patente(page, patente: str, diag: bool = False) -> dict | None:
    try:
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=30_000)

        # Wait for Cloudflare challenge to resolve (if any)
        try:
            page.wait_for_function(
                "() => !document.title.includes('Just a moment')",
                timeout=20_000,
            )
        except PWTimeout:
            print(f"  [{patente}] Cloudflare challenge timed out")
            return None

        # Fill the search input and submit. The "Buscar vehículos" tab (#btnVehiculo)
        # is active by default; the actual submit button is #btnConsultar.
        try:
            page.fill("#txtTerm", patente, timeout=8_000)
            page.click("#btnConsultar", timeout=5_000)
        except PWTimeout:
            page.fill("#inputTerm", patente, timeout=8_000)
            page.press("#inputTerm", "Enter")

        # Wait for the encrypted AJAX round-trip + DOM render. The bare form body
        # is ~45 chars; results (or a "no encontramos" message) grow it past that.
        try:
            page.wait_for_function(
                "() => { const t = document.body.innerText.toLowerCase();"
                " return t.length > 120 || t.includes('no encontr')"
                " || t.includes('sin resultado'); }",
                timeout=20_000,
            )
        except PWTimeout:
            pass
        page.wait_for_timeout(1_500)

        html = page.content()
        body_txt = (page.inner_text("body") or "").lower()

        if diag:
            print(f"  [DIAG] url={page.url}")
            print(f"  [DIAG] body_txt[:2000]={body_txt[:2000]}")
            print(f"  [DIAG] html[:4000]={html[:4000]}")

        # Explicit "not found" message from the app.
        if "no encontr" in body_txt or "sin resultado" in body_txt:
            print(f"  [{patente}] app reports no results")
            return None

        result = _extract_html(html, patente)
        useful = {"rut", "marca", "modelo", "tipo", "color", "combustible"}
        if not any(k in result for k in useful):
            print(f"  [{patente}] no data extracted from rendered results")
            if not diag:
                print(f"  body_txt[:800]={body_txt[:800]}")
            return None

        return result

    except Exception as e:
        print(f"  [{patente}] ERROR: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-id", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (SUPABASE_URL and SUPABASE_KEY):
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    rows = fetch_checkpoints(args.job_id)
    all_plates = collect_plates(rows)
    existing   = fetch_existing(all_plates)
    to_enrich  = all_plates - existing

    print(f"[patentes] {len(all_plates)} plates in job, "
          f"{len(existing)} already in DB, {len(to_enrich)} to enrich")

    if not to_enrich:
        print("[patentes] Nothing to do")
        return

    SESSION_FILE = os.path.expanduser("~/.cache/patente-session/session.json")
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)

    found = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx_kwargs = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="es-CL",
            timezone_id="America/Santiago",
            viewport={"width": 1280, "height": 800},
        )
        # Reuse saved session cookies if available (skips re-solving CF challenge)
        if os.path.exists(SESSION_FILE):
            ctx_kwargs["storage_state"] = SESSION_FILE
            print(f"[patentes] reusing saved session from {SESSION_FILE}")
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()
        _apply_stealth(page)

        for i, patente in enumerate(sorted(to_enrich)):
            print(f"\n[patentes] {patente} ({i+1}/{len(to_enrich)})")
            result = scrape_patente(page, patente, diag=(i == 0))

            if not result:
                print("  -> not found")
                continue

            found += 1
            if args.dry_run:
                print(f"  -> DRY RUN: {result}")
                continue

            try:
                upsert(result)
                print(f"  -> saved: {result}")
            except Exception as e:
                print(f"  -> ERROR saving: {e}")

            time.sleep(1)

        # Save session cookies so retries skip the CF challenge
        try:
            ctx.storage_state(path=SESSION_FILE)
            print(f"[patentes] session saved to {SESSION_FILE}")
        except Exception as e:
            print(f"[patentes] could not save session: {e}")

        browser.close()

    print(f"\n[patentes] Done -- {found}/{len(to_enrich)} enriched")


if __name__ == "__main__":
    main()
