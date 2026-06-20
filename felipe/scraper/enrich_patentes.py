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
from playwright_stealth import stealth_sync

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

def scrape_patente(page, patente: str, diag: bool = False) -> dict | None:
    url = f"https://www.patentechile.com/patente/{patente}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for Cloudflare challenge to resolve (if any)
        try:
            page.wait_for_function(
                "() => !document.title.includes('Just a moment')",
                timeout=20_000,
            )
        except PWTimeout:
            print(f"  [{patente}] Cloudflare challenge timed out")
            return None

        # Wait for content to load
        page.wait_for_timeout(2_000)

        final_url = page.url
        print(f"  [{patente}] url={final_url}")

        # If still on homepage, the plate wasn't found
        if "patente" not in final_url.lower() and patente.upper() not in page.content().upper():
            print(f"  [{patente}] redirected away — plate not found on site")
            return None

        html = page.content()

        if diag:
            print(f"  [DIAG] html={html[:3000]}")

        result = _extract_html(html, patente)
        useful = {"rut", "marca", "modelo", "tipo", "color", "combustible"}
        if not any(k in result for k in useful):
            print(f"  [{patente}] no data extracted")
            if not diag:
                print(f"  HTML: {html[:800]}")
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

    SESSION_FILE = "/tmp/patente_session.json"

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
        stealth_sync(page)

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
