"""Google Sheets + Drive data layer for the PJUD scraper.

Replaces the old Supabase write layer (see HANDOFF.md "Architecture pivot"):
  - The "database" is a Google Sheet with 8 tabs (one per entity), provisioned
    once inside a Drive folder "Poder Judicial Virtual".
  - PDFs (documentos / anexos / ebook) go to a "Documentos" subfolder; the Sheet
    stores the Drive link.
  - Writes are an incremental UPSERT keyed on column A (the entity ID): existing
    rows are overwritten in place, new IDs are appended.

`run.py --setup` calls `provision()` once and saves the created IDs to
`.pjud_config.json` (gitignored). Every later run loads that config and the
`Store` reads each tab's column A to know which IDs already exist.
"""

import io
import json
import re
from pathlib import Path

from googleapiclient.http import MediaIoBaseUpload

import gauth

# ── Tab layout — column A is the entity key; order matches schema.sql ──────────
TABS = {
    # Work-list: the banks whose causas the daily sweep pulls. Column A (nombre)
    # is the key; `rut`+`dv` feed the OJV search; `activo` ("si"/"no") toggles a
    # bank without deleting its row.
    "Bancos": ["nombre", "rut", "dv", "razon_social", "activo"],
    "Tribunales": ["id", "corte", "tribunal"],
    "Ruts": ["rut", "tipo", "nombre", "segundo_nombre", "ap_paterno",
             "ap_materno", "razon_social", "email", "telefono", "domicilio",
             "updated_at"],
    # IDs are plain deterministic codes (parallel-safe + idempotent on re-runs).
    # causa_id = "<tribunal_id>-<rol>"  (rol alone isn't unique nationwide).
    "Causas": ["causa_id", "rol", "f_ingreso", "estado_adm", "procedimiento",
               "ubicacion", "estado_proc", "etapa", "tribunal_id", "competencia",
               "ebook", "texto_demanda", "certificado", "updated_at"],
    # Receptor + Escritos are cuaderno-level but no cuaderno entity exists, so they
    # FK to the causa (causa_id) and carry the cuaderno NAME as plain text.
    "Notificaciones Receptor": ["id", "Causa ID", "Cuaderno", "Nombre", "Fecha",
                                "Estado"],
    "Litigantes": ["id", "causa_id", "rut", "participante", "updated_at"],
    # One row per historia trámite. id = "<causa_id>-c<n>-<folio>-<k>".
    # fecha_tramite = leading date; fecha_diligencia = the parenthetical date.
    "Cuadernos": ["id", "causa_id", "cuaderno", "folio", "etapa", "tramite",
                  "descripcion_tramite", "fecha_tramite", "fecha_diligencia",
                  "foja", "georref"],
    "Escritos": ["id", "causa_id", "cuaderno", "fecha_ingreso", "tipo_escrito",
                 "solicitante"],
    # Docs/anexos attach to ONE trámite row → cuaderno_id = that Cuadernos.id.
    "Documentos": ["id", "cuaderno_id", "origen", "folio", "descripcion", "url"],
    "Anexos": ["id", "cuaderno_id", "origen", "folio", "fecha", "referencia", "url"],
}
TAB_ORDER = list(TABS)

# run.py uses the old pjud_* table names; map them to the tabs.
TABLE_TO_TAB = {
    "pjud_tribunales": "Tribunales",
    "pjud_ruts": "Ruts",
    "pjud_causas": "Causas",
    "pjud_notificaciones": "Notificaciones Receptor",
    "pjud_litigantes": "Litigantes",
    "pjud_cuadernos": "Cuadernos",
    "pjud_escritos": "Escritos",
    "pjud_documentos": "Documentos",
    "pjud_anexos": "Anexos",
}

FOLDER_NAME = "Poder Judicial Virtual"
DOCS_SUBFOLDER = "Documentos"
SHEET_NAME = "PJUD — Base de datos"
CONFIG_PATH = Path(__file__).resolve().parent / "pjud_config.json"

_FOLDER_MIME = "application/vnd.google-apps.folder"
_SHEET_MIME = "application/vnd.google-apps.spreadsheet"


# ── Drive links ────────────────────────────────────────────────────────────────
# Drive's webViewLink is /file/d/<id>/view — its own UI wrapper page, NOT the document. A link
# stored in the database exists to be followed to the file, so every Drive URL is normalised to
# the direct form. This lives here, in the module BOTH backends import, because there are two
# uploaders (gstore for Sheets, dbstore for Postgres) and two doc caches: a second copy is how
# the WAF rejection matcher ended up fixed in one file and blind in another.
_DRIVE_ID = re.compile(r"/file/d/([\w-]+)|[?&]id=([\w-]+)")


def direct_link(url):
    """Any Drive URL -> the one that returns the PDF itself. Non-Drive URLs pass through."""
    if not url or "drive.google.com" not in url:
        return url
    m = _DRIVE_ID.search(url)
    if not m:
        return url
    return f"https://drive.google.com/uc?export=download&id={m.group(1) or m.group(2)}"


def log(msg):
    print(msg, flush=True)


# ── config persistence ─────────────────────────────────────────────────────────

def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return None


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ── provisioning (run once via --setup; idempotent) ────────────────────────────

def _find(drive, name, mime, parent=None):
    """Return the id of the first file named `name` of `mime` the app can see."""
    q = [f"name = '{name}'", f"mimeType = '{mime}'", "trashed = false"]
    if parent:
        q.append(f"'{parent}' in parents")
    resp = drive.files().list(q=" and ".join(q), spaces="drive",
                              fields="files(id, name)", pageSize=10).execute()
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def _make_public_reader(drive, file_id):
    """Anyone-with-link can read — so the SPA (public) can fetch the CSV / PDFs."""
    try:
        drive.permissions().create(
            fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
    except Exception as e:
        log(f"[WARN] could not set public-read on {file_id}: {e}")


def provision(creds=None):
    """Create (or reuse) the Drive folder, Sheet (8 tabs + headers) and Documentos
    subfolder. Idempotent: re-running never duplicates. Returns + saves the config.
    """
    creds = creds or gauth.credentials(allow_login=True)
    drive = gauth.drive_client(creds)
    sheets = gauth.sheets_client(creds)
    cfg = load_config() or {}

    # 1) main folder
    folder_id = cfg.get("folder_id") or _find(drive, FOLDER_NAME, _FOLDER_MIME)
    if not folder_id:
        folder_id = drive.files().create(
            body={"name": FOLDER_NAME, "mimeType": _FOLDER_MIME},
            fields="id").execute()["id"]
        log(f"[SETUP] created folder '{FOLDER_NAME}' ({folder_id})")
    else:
        log(f"[SETUP] folder exists ({folder_id})")

    # 2) Documentos subfolder
    docs_id = cfg.get("documentos_folder_id") or _find(
        drive, DOCS_SUBFOLDER, _FOLDER_MIME, parent=folder_id)
    if not docs_id:
        docs_id = drive.files().create(
            body={"name": DOCS_SUBFOLDER, "mimeType": _FOLDER_MIME,
                  "parents": [folder_id]}, fields="id").execute()["id"]
        log(f"[SETUP] created subfolder '{DOCS_SUBFOLDER}' ({docs_id})")
    _make_public_reader(drive, docs_id)

    # 3) the spreadsheet (8 tabs)
    sheet_id = cfg.get("spreadsheet_id") or _find(
        drive, SHEET_NAME, _SHEET_MIME, parent=folder_id)
    if not sheet_id:
        body = {"properties": {"title": SHEET_NAME},
                "sheets": [{"properties": {"title": t}} for t in TAB_ORDER]}
        sheet_id = sheets.spreadsheets().create(
            body=body, fields="spreadsheetId").execute()["spreadsheetId"]
        # move it into the folder (created in My Drive root by default)
        parents = drive.files().get(fileId=sheet_id, fields="parents").execute()
        drive.files().update(
            fileId=sheet_id, addParents=folder_id,
            removeParents=",".join(parents.get("parents", [])),
            fields="id").execute()
        log(f"[SETUP] created Sheet '{SHEET_NAME}' ({sheet_id})")
        _write_headers(sheets, sheet_id)
    else:
        log(f"[SETUP] Sheet exists ({sheet_id})")
        _ensure_tabs(sheets, sheet_id)    # add any tabs missing from TAB_ORDER
        _write_headers(sheets, sheet_id)  # ensure headers present/correct
    _make_public_reader(drive, sheet_id)

    cfg.update({"folder_id": folder_id, "documentos_folder_id": docs_id,
                "spreadsheet_id": sheet_id})
    save_config(cfg)
    log(f"[SETUP] config saved -> {CONFIG_PATH.name}")
    log(f"[SETUP] Sheet: https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
    return cfg


def _ensure_tabs(sheets, sheet_id):
    """Add any tab in TAB_ORDER that the existing spreadsheet is missing."""
    meta = sheets.spreadsheets().get(
        spreadsheetId=sheet_id, fields="sheets.properties.title").execute()
    have = {s["properties"]["title"] for s in meta.get("sheets", [])}
    missing = [t for t in TAB_ORDER if t not in have]
    if not missing:
        return
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": t}}}
                           for t in missing]}).execute()
    for t in missing:
        log(f"[SETUP] added missing tab '{t}'")


def _write_headers(sheets, sheet_id):
    data = [{"range": f"{tab}!A1", "values": [cols]}
            for tab, cols in TABS.items()]
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={"valueInputOption": "RAW", "data": data}).execute()


# ── Store: incremental upsert + PDF upload ─────────────────────────────────────

class Store:
    """Live handle to the provisioned Sheet + Documentos folder."""

    def __init__(self, config=None, creds=None):
        cfg = config or load_config()
        if not cfg or not cfg.get("spreadsheet_id"):
            raise SystemExit("[FATAL] not provisioned. Run: python run.py --setup")
        self.cfg = cfg
        self.creds = creds or gauth.credentials()
        self.sheets = gauth.sheets_client(self.creds)
        self.drive = gauth.drive_client(self.creds)
        self.sheet_id = cfg["spreadsheet_id"]
        self.docs_folder = cfg["documentos_folder_id"]
        self._index = {}      # tab -> {id: 1-based row number}
        self._doc_cache = None  # name -> webViewLink

    # -- sheet upsert --
    def _load_index(self, tab):
        if tab in self._index:
            return self._index[tab]
        resp = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range=f"{tab}!A2:A",
            majorDimension="COLUMNS").execute()
        col = (resp.get("values") or [[]])
        ids = col[0] if col else []
        # +2: row 1 is the header, sheet rows are 1-based
        self._index[tab] = {v: i + 2 for i, v in enumerate(ids) if v}
        return self._index[tab]

    def read_tab(self, table):
        """Return all data rows of `table` as dicts keyed by the tab's headers."""
        tab = TABLE_TO_TAB.get(table, table)
        cols = TABS[tab]
        resp = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.sheet_id,
            range=f"{tab}!A2:{_col_letter(len(cols) - 1)}").execute()
        out = []
        for row in resp.get("values", []):
            out.append({c: (row[i] if i < len(row) else "")
                        for i, c in enumerate(cols)})
        return out

    def hard_clear(self, keep=("Bancos",)):
        """Delete ALL data rows (shrink each tab's grid → reclaim the workbook's cell
        quota) from every tab except `keep`, then rewrite headers. Clearing values
        alone does NOT reclaim cells — append/INSERT_ROWS grows the grid forever and
        eventually hits the 10M-cell limit. Deleting rows is the only real reset."""
        meta = self.sheets.spreadsheets().get(
            spreadsheetId=self.sheet_id,
            fields="sheets(properties(sheetId,title,gridProperties(rowCount)))").execute()
        reqs = []
        for sh in meta.get("sheets", []):
            p = sh["properties"]
            if p["title"] in keep or p["title"] not in TABS:
                continue
            if p.get("gridProperties", {}).get("rowCount", 1) > 2:
                # Shrink the grid to 2 rows (header + 1) — truncates + reclaims cells.
                reqs.append({"updateSheetProperties": {
                    "properties": {"sheetId": p["sheetId"],
                                   "gridProperties": {"rowCount": 2}},
                    "fields": "gridProperties.rowCount"}})
        if reqs:
            self.sheets.spreadsheets().batchUpdate(
                spreadsheetId=self.sheet_id, body={"requests": reqs}).execute()
        self._index.clear()
        _write_headers(self.sheets, self.sheet_id)
        log(f"[RESET] hard-cleared {len(reqs)} tabs (grid shrunk to 2 rows, cells reclaimed)")

    def dedup(self, table):
        """Remove duplicate rows keyed on column A (keep last). Used after a parallel
        run where multiple workers appended the same key (e.g. a rut) without seeing
        each other's index. Rewrites the tab's data rows; returns rows removed."""
        tab = TABLE_TO_TAB.get(table, table)
        cols = TABS[tab]
        rows = self.read_tab(tab)
        seen = {}
        for r in rows:
            k = str(r.get(cols[0], "")).strip()
            if k:
                seen[k] = r
        if len(seen) == len(rows):
            return 0
        self.sheets.spreadsheets().values().batchClear(
            spreadsheetId=self.sheet_id, body={"ranges": [f"{tab}!A2:ZZ"]}).execute()
        self._index.pop(tab, None)
        self.upsert(tab, list(seen.values()))
        return len(rows) - len(seen)

    def upsert(self, table, rows):
        """Upsert dict rows by column A. Existing IDs overwrite in place; new IDs
        append. `rows` may repeat an ID within the batch — last one wins."""
        if not rows:
            return 0
        tab = TABLE_TO_TAB.get(table, table)
        cols = TABS[tab]
        keycol = cols[0]
        index = self._load_index(tab)

        # de-dupe within the batch (last wins), preserving first-seen order
        merged = {}
        for r in rows:
            key = str(r.get(keycol, "")).strip()
            if key:
                merged[key] = r
        if not merged:
            return 0

        def to_values(r):
            return [str(r.get(c, "") or "") for c in cols]

        updates, appends, written = [], [], []  # written: (row_number, values)
        for key, r in merged.items():
            vals = to_values(r)
            if key in index:
                row = index[key]
                updates.append({"range": f"{tab}!A{row}", "values": [vals]})
                written.append((row, vals))
            else:
                appends.append((key, vals))

        if updates:
            self.sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheet_id,
                body={"valueInputOption": "RAW", "data": updates}).execute()

        if appends:
            resp = self.sheets.spreadsheets().values().append(
                spreadsheetId=self.sheet_id, range=f"{tab}!A1",
                valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={"values": [v for _, v in appends]}).execute()
            # keep the in-memory index current for later upserts this run
            start = _range_start_row(resp.get("updates", {}).get("updatedRange"))
            if start:
                for offset, (key, vals) in enumerate(appends):
                    row = start + offset
                    index[key] = row
                    written.append((row, vals))

        # Formula cells (e.g. the georref =HYPERLINK) were just written RAW, so
        # they're literal text. Re-write only those cells USER_ENTERED so Sheets
        # evaluates them — while everything else (dates, ruts) stays RAW text.
        formulas = [{"range": f"{tab}!{_col_letter(ci)}{row}", "values": [[v]]}
                    for row, vals in written
                    for ci, v in enumerate(vals)
                    if isinstance(v, str) and v.startswith("=")]
        if formulas:
            self.sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=self.sheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": formulas}).execute()

        return len(merged)

    # -- pdf upload --
    def _load_doc_cache(self):
        if self._doc_cache is not None:
            return self._doc_cache
        cache, page_token = {}, None
        while True:
            resp = self.drive.files().list(
                q=f"'{self.docs_folder}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, webViewLink)",
                pageSize=1000, pageToken=page_token).execute()
            for f in resp.get("files", []):
                cache[f["name"]] = direct_link(f.get("webViewLink", ""))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        self._doc_cache = cache
        return cache

    def upload_pdfs_parallel(self, items, workers=5):
        """Sequential fallback (Sheets backend) matching dbstore's parallel API."""
        out = {}
        for p, d in items:
            if not d or len(d) < 1024:
                continue
            try:
                out[p] = self.upload_pdf(p, d)
            except Exception as e:
                log(f"[WARN] upload {p}: {e}")
        return out

    def upload_pdf(self, object_path, data):
        """Upload PDF bytes to the Documentos folder; return its Drive link.
        Skips re-upload if a file with the same flattened name already exists."""
        if len(data) < 1024:
            raise RuntimeError(f"download too small ({len(data)}B) for {object_path}")
        name = _flatten_name(object_path)
        cache = self._load_doc_cache()
        if name in cache and cache[name]:
            return direct_link(cache[name])
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/pdf",
                                  resumable=False)
        f = self.drive.files().create(
            body={"name": name, "parents": [self.docs_folder]},
            media_body=media, fields="id, webViewLink, webContentLink").execute()
        _make_public_reader(self.drive, f["id"])
        link = direct_link(f.get("webContentLink") or f.get("webViewLink", ""))
        cache[name] = link
        return link


def _flatten_name(object_path):
    """'C-996-2026/1 - Principal/12-1-doc.pdf' -> a single safe Drive filename
    (Drive has no path-based folders here, so the path becomes the name)."""
    name = object_path.replace("/", "__").replace("\\", "__")
    name = re.sub(r"\s+", "_", name.strip())
    return name


def _range_start_row(rng):
    """'Causas!A123:K140' -> 123 (the first data row of an append)."""
    if not rng:
        return None
    m = re.search(r"![A-Z]+(\d+)", rng)
    return int(m.group(1)) if m else None


def _col_letter(i):
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA'."""
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s
