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

import cloudscraper
import requests
from bs4 import BeautifulSoup

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Chilean plate formats: 2-letter+4-digit (old) or 4-letter+2-digit (new)
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


# ── HTML extraction ────────────────────────────────────────────────────────────

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

    # Strategy 1: table rows (td/th pairs)
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) >= 2:
            key = _classify(cells[0].get_text())
            if key:
                set_val(key, cells[-1].get_text())

    # Strategy 2: definition lists
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            set_val(_classify(dt.get_text()), dd.get_text())

    # Strategy 3: label-like elements + sibling
    for el in soup.find_all(["strong", "b", "span", "label"]):
        classes = " ".join(el.get("class", []))
        if "label" not in classes and el.name not in ("strong", "b"):
            continue
        key = _classify(el.get_text())
        if not key or key in out:
            continue
        sib = el.find_next_sibling()
        if sib:
            set_val(key, sib.get_text())

    return out


# ── Scraper ────────────────────────────────────────────────────────────────────

_BASE = "https://www.patentechile.com"


def _is_cf_challenge(r) -> bool:
    return "Just a moment" in r.text and "challenge-platform" in r.text


def _try_wp_rest(session, patente: str) -> dict | None:
    """Try the WordPress REST API for a custom post type named 'patente'."""
    for endpoint in [
        f"{_BASE}/wp-json/wp/v2/patente?slug={patente.lower()}",
        f"{_BASE}/wp-json/wp/v2/search?search={patente}&type=post&subtype=patente",
        f"{_BASE}/wp-json/wp/v2/posts?search={patente}&per_page=1",
    ]:
        try:
            r = session.get(endpoint, timeout=15)
            print(f"  [REST] {endpoint} -> {r.status_code}")
            if r.status_code != 200:
                continue
            data = r.json()
            if not data:
                continue
            # data is a list; grab first item content
            item = data[0] if isinstance(data, list) else data
            content_html = (
                item.get("content", {}).get("rendered", "")
                or item.get("excerpt", {}).get("rendered", "")
            )
            if content_html:
                result = _extract_html(content_html, patente)
                useful = {"rut", "marca", "modelo", "tipo", "color", "combustible"}
                if any(k in result for k in useful):
                    print(f"  [REST] got data from {endpoint}")
                    return result
        except Exception as e:
            print(f"  [REST] {endpoint} error: {e}")
    return None


def _try_rss(session, patente: str) -> dict | None:
    """Try the WordPress RSS feed for the search — often has post content."""
    url = f"{_BASE}/search/{patente}/feed/rss2/"
    try:
        r = session.get(url, timeout=15)
        print(f"  [RSS] {url} -> {r.status_code}")
        if r.status_code != 200:
            return None
        # Parse RSS content:encoded or description
        soup = BeautifulSoup(r.text, "xml")
        for tag in ["content:encoded", "description"]:
            content = soup.find(tag)
            if content and content.text.strip():
                result = _extract_html(content.text, patente)
                useful = {"rut", "marca", "modelo", "tipo", "color", "combustible"}
                if any(k in result for k in useful):
                    print(f"  [RSS] got data")
                    return result
    except Exception as e:
        print(f"  [RSS] error: {e}")
    return None


def scrape_patente(session, patente: str, diag: bool = False) -> dict | None:
    try:
        # 1. Try WP REST API (structured JSON)
        result = _try_wp_rest(session, patente)
        if result:
            return result

        # 2. Try RSS feed for search results
        result = _try_rss(session, patente)
        if result:
            return result

        # 3. Try search page and look for a link to the actual plate post
        r = session.get(f"{_BASE}/?s={patente}", timeout=30)
        print(f"  [{patente}] search page HTTP {r.status_code}")
        if r.status_code == 200 and not _is_cf_challenge(r):
            if diag:
                print(f"  [DIAG] search html={r.text[:2000]}")
            # Look for a link to the plate article
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if patente.lower() in href.lower() and _BASE in href:
                    print(f"  [{patente}] following link: {href}")
                    r2 = session.get(href, timeout=30)
                    if r2.status_code == 200 and "/patente" not in str(r2.url).replace(_BASE, ""):
                        result = _extract_html(r2.text, patente)
                        useful = {"rut", "marca", "modelo", "tipo", "color", "combustible"}
                        if any(k in result for k in useful):
                            return result

            # Try extracting directly from search page (data might be inline)
            result = _extract_html(r.text, patente)
            useful = {"rut", "marca", "modelo", "tipo", "color", "combustible"}
            if any(k in result for k in useful):
                return result

        print(f"  [{patente}] no data found across all strategies")
        return None

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

    session = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "linux", "desktop": True}
    )

    found = 0
    for i, patente in enumerate(sorted(to_enrich)):
        print(f"\n[patentes] {patente} ({i+1}/{len(to_enrich)})")
        result = scrape_patente(session, patente, diag=(i == 0))

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

    print(f"\n[patentes] Done -- {found}/{len(to_enrich)} enriched")


if __name__ == "__main__":
    main()
