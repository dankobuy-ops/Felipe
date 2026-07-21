"""Push extracted plates to a standalone Google Sheet under danko.buy@gmail.com.

Reuses the JPL scraper's saved OAuth token (felipe/scraper), so it authenticates
as the SAME account that owns the scraper data — no new login. Creates the sheet
once (id saved in pdf_config.json) and thereafter upserts: a (Patente, Rol) pair
already present is skipped, so re-running never duplicates rows.

Exactly 4 columns, as requested: Patente | RUT demandado | Rol causa | Tribunal.
"""
import csv
import json
import os
import sys
from pathlib import Path

SCRAPER = r"C:\Claude\felipe\scraper"
sys.path.insert(0, SCRAPER)
import gauth  # noqa: E402  (scraper's Google auth -> danko.buy)

HERE = Path(r"C:\Claude\pdf-extractor")
CFG = HERE / "pdf_config.json"
CSV_PATH = HERE / "out" / "patentes_extraidas.csv"
SHEET_TITLE = "Patentes extraídas — JPL (demandas)"
TAB = "Patentes"
COLS = ["Patente", "RUT demandado", "Rol causa", "Tribunal"]


def _cfg():
    return json.loads(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}

def _save_cfg(c):
    CFG.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")

def _clients():
    creds = gauth.credentials()                 # danko.buy; silent refresh
    return gauth.sheets_client(creds), gauth.drive_client(creds)

def get_or_create_sheet(sheets):
    cfg = _cfg()
    if cfg.get("spreadsheet_id"):
        return cfg["spreadsheet_id"]
    sid = sheets.spreadsheets().create(
        body={"properties": {"title": SHEET_TITLE},
              "sheets": [{"properties": {"title": TAB}}]},
        fields="spreadsheetId").execute()["spreadsheetId"]
    sheets.spreadsheets().values().update(
        spreadsheetId=sid, range=f"{TAB}!A1", valueInputOption="RAW",
        body={"values": [COLS]}).execute()
    cfg["spreadsheet_id"] = sid
    _save_cfg(cfg)
    print(f"[sheet] created new spreadsheet: {sid}")
    return sid

def _existing_keys(sheets, sid):
    resp = sheets.spreadsheets().values().get(
        spreadsheetId=sid, range=f"{TAB}!A2:D").execute()
    keys = set()
    for r in resp.get("values", []):
        pat = (r[0] if len(r) > 0 else "").strip()
        rol = (r[2] if len(r) > 2 else "").strip()
        if pat:
            keys.add((pat, rol))
    return keys

def push(rows):
    """rows: iterable of dicts with the 4 COLS. Returns (url, appended, skipped)."""
    sheets, _ = _clients()
    sid = get_or_create_sheet(sheets)
    existing = _existing_keys(sheets, sid)
    new, skipped = [], 0
    for r in rows:
        pat = (r.get("Patente") or "").strip()
        rol = (r.get("Rol causa") or "").strip()
        if not pat:
            continue                                  # plate sheet: skip plate-less rows
        if (pat, rol) in existing:
            skipped += 1
            continue
        existing.add((pat, rol))
        new.append([r.get(c, "") for c in COLS])
    if new:
        sheets.spreadsheets().values().append(
            spreadsheetId=sid, range=f"{TAB}!A1", valueInputOption="RAW",
            insertDataOption="INSERT_ROWS", body={"values": new}).execute()
    url = f"https://docs.google.com/spreadsheets/d/{sid}/edit"
    return url, len(new), skipped

def push_csv(path=CSV_PATH):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return push(rows)

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else CSV_PATH
    url, added, skipped = push_csv(p)
    print(f"[sheet] appended {added} new plate row(s), skipped {skipped} existing.")
    print(f"[sheet] {url}")
