"""Supabase (Postgres) metadata layer + Drive file store for the PJUD scraper.

Drop-in replacement for gstore.py: exposes the same surface (`provision`, `Store`
with `.upsert`/`.read_tab`/`.upload_pdf`/`.dedup`/`.hard_clear`, plus the module
constants `TABS`/`TAB_ORDER`/`TABLE_TO_TAB`/`load_config`/`save_config`/`log`), so
`run.py` only swaps `import gstore` → `import dbstore as gstore`.

  - Metadata → Postgres (one table per entity, TEXT columns, PK = the entity's
    deterministic id). Writes are idempotent UPSERTs (INSERT … ON CONFLICT DO
    UPDATE) keyed on that id — no append/grid bloat, no dedup pass.
  - Files/PDFs → Google Drive, reusing gstore's Drive provisioning + upload. The DB
    only stores the Drive link.

The Postgres connection string is a SECRET and this repo is PUBLIC — it is read from
the `SUPABASE_DB_URL` env var or the gitignored `pjud_config.json` ("supabase_db_url")
and is never committed.
"""

import datetime
import io
import os
import queue
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import psycopg2
import psycopg2.extras
from googleapiclient.http import MediaIoBaseUpload

import gauth
import gstore

# Reuse gstore's schema + config + Drive helpers so the two backends never diverge.
TABS = gstore.TABS
TAB_ORDER = gstore.TAB_ORDER
TABLE_TO_TAB = gstore.TABLE_TO_TAB
load_config = gstore.load_config
save_config = gstore.save_config
log = gstore.log

# DB-managed columns beyond the scrape schema (TABS). They are NEVER written by
# upsert(), so re-running Pass-1 discovery never resets a user's `fill` flag or the
# scraper's `fill_status`. `fill` is the manual "I want this one" checkbox (set in
# AppSheet); `fill_status` is Pass-2's progress ('' | 'done' | 'error').
EXTRA_COLS = {
    "Causas": [("fill", "BOOLEAN NOT NULL DEFAULT false"),
               ("fill_status", "TEXT NOT NULL DEFAULT ''")],
}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# Short (10-char base62) unique-id generator — a compact, stable, AppSheet-friendly key
# (~5.8e17 space → collision-free at our scale). Used as the DEFAULT for every `uid`.
_SHORT_UID_FN = """
CREATE OR REPLACE FUNCTION short_uid(len int DEFAULT 10) RETURNS text AS $fn$
  SELECT string_agg(
      substr('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
             (floor(random() * 62)::int) + 1, 1), '')
  FROM generate_series(1, len)
$fn$ LANGUAGE sql VOLATILE;
"""


def _sqlcol(name):
    """'Causa ID' -> 'causa_id'  (a tab header → a Postgres column name)."""
    return re.sub(r"\s+", "_", name.strip().lower())


def _sql_table(tab):
    """'Notificaciones Receptor' -> 'notificaciones_receptor'."""
    return re.sub(r"\s+", "_", tab.strip().lower())


def _conn_kwargs(cfg=None):
    """Connection params for psycopg2.connect(**kwargs). Any Postgres (Neon,
    Supabase, self-hosted). Prefers the component dict `pg_conn` in config (password
    used literally — safe for chars that would break a URL), then PG_CONN_URL env,
    then a 'pg_conn_url' string. All are gitignored secrets — repo is PUBLIC, never
    commit them."""
    cfg = cfg or load_config() or {}
    db = cfg.get("pg_conn") or cfg.get("supabase_db")   # supabase_db kept for back-compat
    if isinstance(db, dict) and db.get("host"):
        kw = dict(db)
        kw.setdefault("sslmode", "require")
        return kw
    url = os.environ.get("PG_CONN_URL") or cfg.get("pg_conn_url")
    if url:
        return {"dsn": url}
    raise SystemExit(
        "[FATAL] no Postgres connection. Add 'pg_conn' (host/port/user/password/"
        "dbname) to pjud_config.json, or set PG_CONN_URL (gitignored — repo is "
        "PUBLIC, never commit it).")


# ── schema ──────────────────────────────────────────────────────────────────────

def _ddl():
    """One CREATE TABLE per entity: TEXT columns, PK = the first (id) column.
    v1 has no enforced foreign keys — referential integrity is carried by the
    deterministic ids (causa_id, cuaderno_id, …); FKs can be layered on later."""
    stmts = []
    for tab in TAB_ORDER:
        sqlcols = [_sqlcol(c) for c in TABS[tab]]
        lines = [f'"{sqlcols[0]}" TEXT PRIMARY KEY']
        lines += [f'"{c}" TEXT' for c in sqlcols[1:]]
        lines += [f'"{name}" {decl}' for name, decl in EXTRA_COLS.get(tab, [])]
        # Short (10-char) stable unique key for every row — AppSheet-friendly. Auto-
        # generated; never written by upsert (stays stable).
        lines.append('"uid" TEXT NOT NULL DEFAULT short_uid(10)')
        stmts.append(f'CREATE TABLE IF NOT EXISTS "{_sql_table(tab)}" (\n  '
                     + ",\n  ".join(lines) + "\n);")
    # Pass-1 resumability: which (corte, tribunal, month) have been swept.
    stmts.append(
        'CREATE TABLE IF NOT EXISTS "sweep_progress" (\n'
        '  "key" TEXT PRIMARY KEY,\n  "corte" TEXT,\n  "tribunal" TEXT,\n'
        '  "month" TEXT,\n  "status" TEXT,\n  "updated_at" TEXT\n);')
    return stmts


def _create_schema(conn_kwargs):
    conn = psycopg2.connect(**conn_kwargs)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(_SHORT_UID_FN)          # short_uid() must exist before the DDL
            for stmt in _ddl():
                cur.execute(stmt)
            # Migrate already-created tables: add any EXTRA_COLS that are missing.
            for tab, cols in EXTRA_COLS.items():
                t = _sql_table(tab)
                for name, decl in cols:
                    cur.execute(
                        f'ALTER TABLE "{t}" ADD COLUMN IF NOT EXISTS "{name}" {decl}')
            # Every table gets a stable UUID key column `uid` (backfilled per-row on add)
            # + a unique index, so AppSheet has a clean single-column key everywhere.
            for tab in TAB_ORDER:
                t = _sql_table(tab)
                cur.execute(f'ALTER TABLE "{t}" ADD COLUMN IF NOT EXISTS "uid" '
                            f'TEXT NOT NULL DEFAULT short_uid(10)')
                cur.execute(f'ALTER TABLE "{t}" ALTER COLUMN "uid" '
                            f'SET DEFAULT short_uid(10)')
                cur.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{t}_uid_uk" '
                            f'ON "{t}" ("uid")')
    finally:
        conn.close()


# ── provisioning (run once via --setup; idempotent) ────────────────────────────

def provision(creds=None):
    """Create (or reuse) the Drive folder + Documentos subfolder and the Postgres
    tables. Idempotent. Returns + saves the config (Drive ids; the DSN must already
    be in env/config)."""
    creds = creds or gauth.credentials(allow_login=True)
    drive = gauth.drive_client(creds)
    cfg = load_config() or {}

    folder_id = cfg.get("folder_id") or gstore._find(
        drive, gstore.FOLDER_NAME, gstore._FOLDER_MIME)
    if not folder_id:
        folder_id = drive.files().create(
            body={"name": gstore.FOLDER_NAME, "mimeType": gstore._FOLDER_MIME},
            fields="id").execute()["id"]
        log(f"[SETUP] created folder '{gstore.FOLDER_NAME}' ({folder_id})")
    else:
        log(f"[SETUP] folder exists ({folder_id})")

    docs_id = cfg.get("documentos_folder_id") or gstore._find(
        drive, gstore.DOCS_SUBFOLDER, gstore._FOLDER_MIME, parent=folder_id)
    if not docs_id:
        docs_id = drive.files().create(
            body={"name": gstore.DOCS_SUBFOLDER, "mimeType": gstore._FOLDER_MIME,
                  "parents": [folder_id]}, fields="id").execute()["id"]
        log(f"[SETUP] created subfolder '{gstore.DOCS_SUBFOLDER}' ({docs_id})")
    gstore._make_public_reader(drive, docs_id)

    cfg.update({"folder_id": folder_id, "documentos_folder_id": docs_id})
    save_config(cfg)

    _create_schema(_conn_kwargs(cfg))
    log(f"[SETUP] Postgres tables ready ({len(TAB_ORDER)} tables)")
    log("[SETUP] config saved -> pjud_config.json")
    return cfg


# ── Store: Postgres upsert + Drive PDF upload ──────────────────────────────────

class Store:
    """Live handle to the Postgres DB + Drive Documentos folder."""

    def __init__(self, config=None, creds=None):
        cfg = config or load_config()
        if not cfg:
            raise SystemExit("[FATAL] not provisioned. Run: python run.py --setup")
        self.cfg = cfg
        self._ck = _conn_kwargs(cfg)
        self.conn = psycopg2.connect(**self._ck)
        self.conn.autocommit = True
        # Drive (PDFs) — lazily set up only if upload_pdf is called.
        self._creds = creds
        self._drive = None
        self.docs_folder = cfg.get("documentos_folder_id")
        self._doc_cache = None
        self._upool = None          # ThreadPoolExecutor for Drive uploads (built once)
        self._uclients = None       # queue of per-worker Drive clients (built once)

    def _reconnect(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self.conn = psycopg2.connect(**self._ck)
        self.conn.autocommit = True

    # -- metadata upsert --
    def upsert(self, table, rows):
        """Idempotent UPSERT of dict rows keyed on the table's id column (first
        column). Rows may repeat an id within the batch — last one wins."""
        if not rows:
            return 0
        tab = TABLE_TO_TAB.get(table, table)
        headers = TABS[tab]
        sqlcols = [_sqlcol(c) for c in headers]
        pk = sqlcols[0]
        sqltab = _sql_table(tab)

        merged = {}
        for r in rows:
            k = str(r.get(headers[0], "")).strip()
            if k:
                merged[k] = r
        if not merged:
            return 0
        tuples = [tuple(str(r.get(h, "") or "") for h in headers)
                  for r in merged.values()]

        collist = ", ".join(f'"{c}"' for c in sqlcols)
        setcols = [c for c in sqlcols if c != pk]
        if setcols:
            upd = ", ".join(f'"{c}"=EXCLUDED."{c}"' for c in setcols)
            sql = (f'INSERT INTO "{sqltab}" ({collist}) VALUES %s '
                   f'ON CONFLICT ("{pk}") DO UPDATE SET {upd}')
        else:
            sql = (f'INSERT INTO "{sqltab}" ({collist}) VALUES %s '
                   f'ON CONFLICT ("{pk}") DO NOTHING')

        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    psycopg2.extras.execute_values(cur, sql, tuples)
                return len(merged)
            except psycopg2.OperationalError:
                if attempt == 1:
                    self._reconnect()
                    continue
                raise

    def read_tab(self, table):
        """Return all rows of `table` as dicts keyed by the tab's headers."""
        tab = TABLE_TO_TAB.get(table, table)
        headers = TABS[tab]
        sqlcols = [_sqlcol(c) for c in headers]
        sqltab = _sql_table(tab)
        sel = ", ".join(f'"{c}"' for c in sqlcols)
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute(f'SELECT {sel} FROM "{sqltab}"')
                    data = cur.fetchall()
                break
            except psycopg2.OperationalError:
                if attempt == 1:
                    self._reconnect()
                    continue
                raise
        return [{h: ("" if v is None else str(v)) for h, v in zip(headers, row)}
                for row in data]

    def dedup(self, table):
        """No-op: UPSERT on the PK is already idempotent (kept for surface parity)."""
        return 0

    # -- Pass-1 resumability (sweep_progress) --
    def swept_keys(self):
        """Set of '<corte>-<tribunal>-<month>' already fully swept in Pass 1."""
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT key FROM sweep_progress WHERE status='done'")
                    return {r[0] for r in cur.fetchall()}
            except psycopg2.OperationalError:
                if attempt == 1:
                    self._reconnect()
                    continue
                raise

    # -- Pass-2 fill targeting/progress (causas.fill / fill_status) --
    def fill_targets(self, only_selected=False):
        """[(causa_id, tribunal_id, rol, f_ingreso)] of causas still needing their far
        data. only_selected=True restricts to the user's fill=true picks; otherwise every
        not-yet-'done' causa (used for the January baseline fill)."""
        where = ("fill = true AND fill_status <> 'done'" if only_selected
                 else "fill_status <> 'done'")
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute(f"SELECT causa_id, tribunal_id, rol, f_ingreso FROM causas "
                                f"WHERE {where}")
                    return cur.fetchall()
            except psycopg2.OperationalError:
                if attempt == 1:
                    self._reconnect()
                    continue
                raise

    def mark_filled(self, causa_id, status="done"):
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute("UPDATE causas SET fill_status=%s WHERE causa_id=%s",
                                (status, causa_id))
                return
            except psycopg2.OperationalError:
                if attempt == 1:
                    self._reconnect()
                    continue
                raise

    def mark_swept(self, corte, tribunal, month, status="done"):
        key = f"{corte}-{tribunal}-{month}"
        sql = ('INSERT INTO sweep_progress (key,corte,tribunal,month,status,updated_at) '
               'VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (key) DO UPDATE SET '
               'status=EXCLUDED.status, updated_at=EXCLUDED.updated_at')
        for attempt in (1, 2):
            try:
                with self.conn.cursor() as cur:
                    cur.execute(sql, (key, str(corte), str(tribunal), str(month),
                                      status, _now()))
                return
            except psycopg2.OperationalError:
                if attempt == 1:
                    self._reconnect()
                    continue
                raise

    def hard_clear(self, keep=("Bancos",)):
        """Empty every table except `keep` (the DB equivalent of the Sheets reset)."""
        tabs = [t for t in TAB_ORDER if t not in keep]
        sqltabs = ", ".join(f'"{_sql_table(t)}"' for t in tabs)
        with self.conn.cursor() as cur:
            cur.execute(f"TRUNCATE {sqltabs}")
        log(f"[RESET] truncated {len(tabs)} tables")

    # -- pdf upload (Drive, reused from gstore) --
    @property
    def drive(self):
        if self._drive is None:
            self._creds = self._creds or gauth.credentials()
            self._drive = gauth.drive_client(self._creds)
        return self._drive

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
                cache[f["name"]] = f.get("webViewLink", "")
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        self._doc_cache = cache
        return cache

    def upload_pdfs_parallel(self, items, workers=5):
        """Upload many PDFs to Drive concurrently and return {object_path: link}. The
        OJV FETCH stays sequential upstream (gentle on the WAF) — only these Drive
        uploads run in parallel. Reuses one thread pool + a fixed set of Drive clients
        (built once, borrowed per task) so there's no per-causa client-build overhead.
        Skips re-upload of names already in the Documentos folder (locked cache)."""
        items = [(p, d) for p, d in items if d and len(d) >= 1024]
        if not items:
            return {}
        if self._upool is None:
            self._creds = self._creds or gauth.credentials()
            self._uclients = queue.Queue()
            for _ in range(workers):
                self._uclients.put(gauth.drive_client(self._creds))
            self._upool = ThreadPoolExecutor(max_workers=workers)
        cache = self._load_doc_cache()
        lock = threading.Lock()

        def _one(path, data):
            name = gstore._flatten_name(path)
            with lock:
                hit = cache.get(name)
            if hit:
                return path, hit
            drive = self._uclients.get()
            try:
                media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/pdf",
                                          resumable=False)
                f = drive.files().create(
                    body={"name": name, "parents": [self.docs_folder]},
                    media_body=media, fields="id, webViewLink").execute()
                gstore._make_public_reader(drive, f["id"])
            finally:
                self._uclients.put(drive)
            link = f.get("webViewLink", "")
            with lock:
                cache[name] = link
            return path, link

        out = {}
        futs = {self._upool.submit(_one, p, d): p for p, d in items}
        for fu in futs:
            try:
                p, link = fu.result()
                out[p] = link
            except Exception as e:
                log(f"[WARN] parallel upload {futs[fu]}: {e}")
        return out

    def upload_pdf(self, object_path, data):
        """Upload PDF bytes to the Drive Documentos folder; return its link.
        Skips re-upload if a file with the same flattened name already exists."""
        if len(data) < 1024:
            raise RuntimeError(f"download too small ({len(data)}B) for {object_path}")
        name = gstore._flatten_name(object_path)
        cache = self._load_doc_cache()
        if name in cache and cache[name]:
            return cache[name]
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/pdf",
                                  resumable=False)
        f = self.drive.files().create(
            body={"name": name, "parents": [self.docs_folder]},
            media_body=media, fields="id, webViewLink").execute()
        gstore._make_public_reader(self.drive, f["id"])
        link = f.get("webViewLink", "")
        cache[name] = link
        return link
