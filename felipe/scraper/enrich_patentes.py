"""Look up vehicle info for patentes found in job checkpoints.

For each unique placa_patente (newline-separated) extracted from the
checkpoints of a job, query patentechile.com and write the result to
the `patentes` table in Supabase. Already-enriched plates are skipped.

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
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Chilean plate formats: 2-letter+4-digit (old) or 4-letter+2-digit (new)
PLATE_RE = re.compile(r'^[A-Z]{2,4}\d{2,4}$')


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
    """Split a placa_patente field (newline-separated) into individual plates."""
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


# ── Scraper ────────────────────────────────────────────────────────────────────

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

_EXTRACT_JS = """
(patente) => {
    const out = { patente };
    const FIELDS = %s;

    function classify(raw) {
        const l = (raw || '').toLowerCase().replace(/[:\\-°]/g, '').trim();
        for (const [key, labels] of Object.entries(FIELDS)) {
            for (const lbl of labels) {
                if (l === lbl || l.startsWith(lbl)) return key;
            }
        }
        return null;
    }

    function set(key, val) {
        if (key && !out[key] && val && val.length < 200) out[key] = val.trim();
    }

    // Strategy 1: table rows
    for (const tr of document.querySelectorAll('tr')) {
        const cells = [...tr.querySelectorAll('td, th')];
        if (cells.length >= 2) {
            const key = classify(cells[0].innerText);
            if (key) set(key, cells[cells.length - 1].innerText);
        }
    }

    // Strategy 2: definition lists
    for (const dt of document.querySelectorAll('dt')) {
        const dd = dt.nextElementSibling;
        if (dd && dd.tagName === 'DD') set(classify(dt.innerText), dd.innerText);
    }

    // Strategy 3: label + sibling value
    for (const el of document.querySelectorAll('.label, [class*="label"], strong, b')) {
        const key = classify(el.innerText);
        if (!key || out[key]) continue;
        const sib = el.nextElementSibling || el.parentElement?.nextElementSibling;
        if (sib) set(key, sib.innerText);
    }

    return out;
}
""" % json.dumps(_FIELDS)


def scrape_patente(page, patente: str, diag: bool = False) -> dict | None:
    try:
        # Try direct URL first, fall back to homepage + form
        for url in [
            f"https://www.patentechile.com/patente/{patente}",
            "https://www.patentechile.com/",
        ]:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                break
            except PlaywrightTimeout:
                continue

        page.wait_for_timeout(1_500)

        # If plate not in URL, find the search form and submit
        if patente.upper() not in page.url.upper():
            filled = False
            for sel in [
                "input[type=search]", "input[type=text]",
                "input[placeholder*='patente' i]", "input[name*='patente' i]",
                "input[id*='patente' i]", "#patente", "form input",
            ]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.fill("")
                        el.type(patente)
                        page.keyboard.press("Enter")
                        filled = True
                        break
                except Exception:
                    continue

            if not filled:
                print(f"  [{patente}] search input not found")
                if diag:
                    print(f"  HTML: {page.content()[:2000]}")
                return None

            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeout:
                pass
            page.wait_for_timeout(1_500)

        if diag:
            print(f"  [DIAG] url={page.url}")
            print(f"  [DIAG] html={page.content()[:3000]}")

        result = page.evaluate(_EXTRACT_JS, patente)
        if not result:
            result = {"patente": patente}

        useful = {"rut", "marca", "modelo", "tipo", "color", "combustible"}
        if not any(k in result for k in useful):
            print(f"  [{patente}] no data extracted (url={page.url})")
            if not diag:
                print(f"  HTML: {page.content()[:1500]}")
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

    found = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page = ctx.new_page()

        for i, patente in enumerate(sorted(to_enrich)):
            print(f"\n[patentes] {patente} ({i+1}/{len(to_enrich)})")
            result = scrape_patente(page, patente, diag=(i == 0))

            if not result:
                print("  → not found")
                continue

            found += 1
            if args.dry_run:
                print(f"  → DRY RUN: {result}")
                continue

            try:
                upsert(result)
                print(f"  → saved: {result}")
            except Exception as e:
                print(f"  → ERROR saving: {e}")

            time.sleep(0.5)

        browser.close()

    print(f"\n[patentes] Done — {found}/{len(to_enrich)} enriched")


if __name__ == "__main__":
    main()
