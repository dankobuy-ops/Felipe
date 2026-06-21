"""Shared helpers for patente enrichment (Supabase I/O + HTML field extraction).

NOTE: patentechile.com gates its results endpoint behind a Cloudflare *managed
challenge* that automated/headless browsers and datacenter IPs (GitHub Actions)
cannot pass. The actual scraping therefore runs locally in a real browser —
see enrich_patentes_local.py. This module only holds the reusable pieces it
imports; running it directly just points you there.
"""
import argparse
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

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


# ── Entry point ─────────────────────────────────────────────────────────────────
# Scraping moved to enrich_patentes_local.py (real browser, run locally) because
# patentechile.com's results endpoint is behind a Cloudflare managed challenge
# that headless/CI cannot pass. This module is now import-only helpers.

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job-id")
    ap.add_argument("--dry-run", action="store_true")
    ap.parse_args()
    sys.exit(
        "patente enrichment runs locally now — patentechile.com is behind a "
        "Cloudflare managed challenge that CI/headless can't pass.\n"
        "Run on your own machine:\n"
        "  python enrich_patentes_local.py --job-id <UUID>"
    )


if __name__ == "__main__":
    main()
