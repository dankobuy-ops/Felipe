"""Shared helpers for patente enrichment (plate + HTML field extraction).

NOTE: patentechile.com gates its results endpoint behind a Cloudflare *managed
challenge* that automated/headless browsers and datacenter IPs (GitHub Actions)
cannot pass. The actual scraping runs locally in a real browser — see
enrich_patentes_local.py. This module is import-only parsing helpers; the data
store is the Google Sheet (Patentes tab), handled via gstore.
"""
import re
import sys

from bs4 import BeautifulSoup

PLATE_RE = re.compile(r'^[A-Z]{2,4}\d{2,4}$')

_FIELDS = {
    "rut_propietario":    ["rut propietario", "rut del propietario", "propietario", "rut"],
    "nombre_propietario": ["nombre propietario", "nombre del propietario", "nombre"],
    "tipo":        ["tipo vehículo", "tipo vehiculo", "tipo"],
    "marca":       ["marca"],
    "modelo":      ["modelo"],
    "anio":        ["año fabricación", "año del vehículo", "año modelo", "año", "ano"],
    "color":       ["color"],
    "num_motor":   ["n° motor", "nro motor", "numero motor", "número motor", "motor"],
    "num_chasis":  ["n° chasis", "nro chasis", "numero chasis", "número chasis", "chasis"],
    "combustible": ["combustible"],
}


# ── Plate extraction ───────────────────────────────────────────────────────────

def extract_plates(field: str) -> list[str]:
    out = []
    for line in (field or "").split("\n"):
        p = re.sub(r"[\s\-]", "", line).strip().upper()
        if p and PLATE_RE.match(p):
            out.append(p)
    return out


# ── HTML data extraction ───────────────────────────────────────────────────────

def _norm(s: str) -> str:
    # Drop punctuation that varies between label and candidate (e.g. "N° Motor"),
    # collapse whitespace, lowercase. Both label and candidates go through this so
    # "N° Motor" and "n° motor" both become "n motor" and match.
    return re.sub(r"\s+", " ", re.sub(r"[:\-°.]", "", (s or "")).lower()).strip()


def _classify(raw: str) -> str | None:
    label = _norm(raw)
    if not label:
        return None
    for key, candidates in _FIELDS.items():
        for c in candidates:
            cn = _norm(c)
            if label == cn or label.startswith(cn):
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
    sys.exit(
        "This module is import-only parsing helpers now. Patente enrichment runs\n"
        "locally (patentechile.com is behind a Cloudflare challenge CI can't pass):\n"
        "  python enrich_patentes_local.py                      # enrich un-filled plates in the Sheet\n"
        "  python enrich_patentes_local.py --plates AA1111,BB2222 --dry-run"
    )


if __name__ == "__main__":
    main()
