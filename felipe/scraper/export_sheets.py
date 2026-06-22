"""Export scraped JPL data from Supabase to a Google Sheet (standalone command).

Produces linked tabs and POSTs them to a Google Apps Script web app bound
to the target sheet (see sheets_webapp.gs for the script + setup):

  Causas          — one row per causa (case header + remisor info)
  Demandados      — one row per UNIQUE party, keyed by RUT (clean entity table,
                    deduped across every causa/job; enrichment fields merged)
  Causa-Demandado — junction: one row per (causa, party) link, carrying the
                    case-specific vehicle details (marca/modelo/año/patente/uso)
  Trámites        — one row per trámite from Sección C (linked by Caso ID)
  Documentos      — one row per adjunto from Sección D (linked by Caso ID)

A party who is a defendant in several causas appears once in Demandados and
once per causa in Causa-Demandado, so personal data is never duplicated.

The same normalized entities are also mirrored into Supabase relational tables
(demandados, causa_demandado, patente_demandado — see export_tables.sql) on each
run, unless --no-db is passed. The checkpoints JSON store remains the scrape
source of truth; these tables are a derived, queryable layer.

Usage:
  python export_sheets.py --webhook <APPS_SCRIPT_EXEC_URL> --all
  python export_sheets.py --webhook <URL> --job-id <JOB_UUID>

Env fallbacks: SHEETS_WEBHOOK_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY
"""
import argparse
import json
import os
import re
import sys

import requests

# A plate field may list several plates (newline / comma / slash separated).
_PLATE_RE = re.compile(r"^[A-Z]{2,4}\d{2,4}$")

JUZGADOS_HEADER = ["Juzgado ID", "Nombre", "URL"]
JUZGADOS_ROWS = [
    ["vitacura",    "Vitacura",     "https://vitacura.cl/municipalidad/juzgado/juzgado-policia-local/"],
    ["lobarnechea", "Lo Barnechea", "https://mlobarnechea.custhelp.com/app/answers/detail/a_id/83/incidents.c$tipo_atencion/221"],
]
JUZGADO_NAMES = {
    "vitacura":    "Vitacura",
    "lobarnechea": "Lo Barnechea",
}

CAUSAS_HEADER = [
    "Caso ID", "ROL",
    "Juzgado",
    "Demandante", "Razón Social Demandante",
    "Materia",
    "Fecha Causa", "Fecha Citación", "Fecha Estado", "Estado",
    "Boleta N°", "Fecha Boleta",
    "Monto Demandado",
]

# Clean entity table — one row per unique party, keyed by RUT (col A).
DEMANDADOS_HEADER = [
    "RUT",
    "Nombre", "Segundo Nombre", "Ap. Paterno", "Ap. Materno",
    "Email", "Fuente Email", "Teléfono", "Domicilio",
]

# Junction — links a causa to a party. Col A ("Vínculo ID") is the unique
# upsert key: "<Caso ID>::<RUT>".
CAUSA_DEMANDADO_HEADER = [
    "Vínculo ID", "Caso ID", "ROL", "RUT",
]

# Junction — links a plate to the demandado's RUT within a causa. A ROL may
# carry several plates, so there can be many rows per Caso ID. Col A
# ("Vínculo ID") is the unique upsert key: "<Caso ID>::<RUT>::<Patente>".
# Plate attributes (marca/modelo/año…) live in the Patentes entity tab.
PATENTE_DEMANDADO_HEADER = [
    "Vínculo ID", "Caso ID", "ROL", "RUT", "Patente",
]

# Supabase column names, positionally parallel to the *_HEADER lists above.
# Used to mirror the reshaped rows into the relational tables (export_tables.sql).
DEMANDADOS_COLS        = ["rut", "nombre", "segundo_nombre", "ap_paterno",
                          "ap_materno", "email", "email_source", "telefono", "domicilio"]
CAUSA_DEMANDADO_COLS   = ["vinculo_id", "caso_id", "rol", "rut"]
PATENTE_DEMANDADO_COLS = ["vinculo_id", "caso_id", "rol", "rut", "patente"]

TRAMITES_HEADER = [
    "Caso ID", "ROL", "Fecha", "Descripción", "Link PDF",
]

DOCUMENTOS_HEADER = [
    "Caso ID", "ROL", "Descripción", "Link PDF",
]


def _caso_id(job, rol):
    return f"{(job or '')[:8]}/{rol}"


def fetch_rows(sb_url, sb_key, job_id=None):
    params = {"select": "job_id,record_id,status,text", "order": "job_id"}
    if job_id:
        params["job_id"] = f"eq.{job_id}"
    r = requests.get(
        f"{sb_url}/rest/v1/checkpoints",
        headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"},
        params=params, timeout=90,
    )
    r.raise_for_status()
    return r.json()


def upsert_table(sb_url, sb_key, table, conflict_col, cols, rows, batch_size=200):
    """Upsert reshaped rows into a Supabase relational table (export_tables.sql).

    `rows` are positional lists parallel to `cols`. Uses the service key, which
    bypasses RLS. Returns the number of rows written.
    """
    if not rows:
        return 0
    url = f"{sb_url}/rest/v1/{table}?on_conflict={conflict_col}"
    headers = {
        "apikey": sb_key,
        "Authorization": f"Bearer {sb_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    written = 0
    for i in range(0, len(rows), batch_size):
        chunk = [dict(zip(cols, r)) for r in rows[i : i + batch_size]]
        r = requests.post(url, headers=headers, json=chunk, timeout=60)
        r.raise_for_status()
        written += len(chunk)
    return written


def _split_name(nombre):
    """Split a full name into (nombre, segundo_nombre, ap_paterno, ap_materno).

    Chilean court systems often format as "APELLIDO1 APELLIDO2, NOMBRE1 NOMBRE2".
    If a comma is present: before = apellidos, after = nombres.
    Without a comma, split by position (best-effort heuristic).
    """
    if not nombre:
        return "", "", "", ""
    nombre = nombre.strip()
    if "," in nombre:
        apellidos_str, nombres_str = nombre.split(",", 1)
        apellidos = apellidos_str.strip().split()
        nombres   = nombres_str.strip().split()
        ap_paterno = apellidos[0].title() if len(apellidos) >= 1 else ""
        ap_materno = apellidos[1].title() if len(apellidos) >= 2 else ""
        nombre1    = nombres[0].title()   if len(nombres)   >= 1 else ""
        segundo    = " ".join(p.title() for p in nombres[1:])
        return nombre1, segundo, ap_paterno, ap_materno
    # No comma — Chilean courts use PATERNO MATERNO NOMBRE [SEGUNDO] order
    parts = nombre.split()
    n = len(parts)
    if n == 0:
        return "", "", "", ""
    if n == 1:
        return parts[0].title(), "", "", ""
    if n == 2:
        return parts[1].title(), "", parts[0].title(), ""
    if n == 3:
        return parts[2].title(), "", parts[0].title(), parts[1].title()
    # 4+ words: first two = apellidos, rest = nombres
    ap_paterno = parts[0].title()
    ap_materno = parts[1].title()
    nombre1    = parts[2].title()
    segundo    = " ".join(p.title() for p in parts[3:])
    return nombre1, segundo, ap_paterno, ap_materno


def _plates(*fields):
    """Extract distinct, normalized plates from one or more raw fields.

    Each field may list several plates separated by newlines/commas/slashes.
    Falls back to keeping a cleaned single token when nothing matches the
    canonical plate shape, so unusual formats are not silently dropped.
    """
    out, seen = [], set()
    for field in fields:
        for tok in re.split(r"[\n,;/]+", field or ""):
            p = re.sub(r"[\s\-.]", "", tok).strip().upper()
            if not p:
                continue
            if _PLATE_RE.match(p) and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _merge_person(existing, new):
    """Merge two person rows field-by-field: existing wins, new fills blanks.

    Lets enrichment captured in one causa (e.g. an email) populate a party
    even when another appearance left that field empty.
    """
    return [e or n for e, n in zip(existing, new)]


def _domicilio(party):
    parts = [party.get("direccion", ""), party.get("comuna", "")]
    return ", ".join(p for p in parts if p)


def _first_match(d, *keys):
    for k in keys:
        v = d.get(k, "")
        if v:
            return v
    return ""


def build_tables(rows):
    # Collect job meta (rut, etc.) keyed by job_id
    job_meta = {}
    for row in rows:
        if row.get("record_id") == "__meta__":
            try:
                job_meta[row["job_id"]] = json.loads(row.get("text") or "{}")
            except Exception:
                pass

    causas, tramites, documentos = [], [], []
    causa_demandado, patente_demandado = [], []
    # Demandados is deduped by party key (RUT) while preserving first-seen order.
    person_index = {}
    person_order = []

    for row in rows:
        rid = row.get("record_id", "")
        if rid in ("__job__", "__meta__"):
            continue
        try:
            d = json.loads(row.get("text") or "{}")
        except Exception:
            d = {}

        rol   = d.get("rol") or rid
        job   = row.get("job_id", "")
        cid   = _caso_id(job, rol)
        causa = d.get("causa") or {}
        meta  = job_meta.get(job, {})

        # ── Table 1: Causas ───────────────────────────────────────────────────
        juzgado_id   = meta.get("juzgado", "")
        juzgado_name = JUZGADO_NAMES.get(juzgado_id, juzgado_id)
        causas.append([
            cid,
            rol,
            juzgado_name,
            meta.get("rut", ""),
            _first_match(causa, "remisor"),
            d.get("descripcion", "") or _first_match(causa, "descripcion", "descripción", "materia", "materia_causa", "materia_de_la_causa"),
            _first_match(causa, "fecha_causa"),
            _first_match(causa, "fecha_citacion", "fecha_citación"),
            _first_match(causa, "fecha_estado"),
            causa.get("estado", ""),
            causa.get("boleta_numero", ""),
            causa.get("boleta_fecha", ""),
            _first_match(causa, "monto", "monto_demandado", "cuantia", "cuantía", "monto_multa"),
        ])

        # ── Demandados (clean) + Causa-Demandado + Patente-Demandado ──────────
        # Causa-level plates are the fallback when a party lists none of its own.
        causa_plates = _plates(causa.get("placa_patente"), d.get("placa_patente"))
        dem_list = d.get("demandados") or []

        if not dem_list:
            # No identified party — preserve any causa plates with a blank RUT
            # so the plate↔causa link is not lost.
            for plate in causa_plates:
                patente_demandado.append([f"{cid}::::{plate}", cid, rol, "", plate])
        else:
            for dem in dem_list:
                rut = dem.get("rut", "")
                nombre, segundo, ap_paterno, ap_materno = _split_name(dem.get("nombre", ""))
                person = [
                    rut, nombre, segundo, ap_paterno, ap_materno,
                    dem.get("email", ""), dem.get("email_source", ""),
                    dem.get("telefono", ""), _domicilio(dem),
                ]
                # Dedup people by RUT (name fallback guards a rare empty RUT).
                pkey = rut or f"sinrut::{(nombre + ap_paterno + ap_materno).lower()}"
                if pkey in person_index:
                    person_index[pkey] = _merge_person(person_index[pkey], person)
                else:
                    person_index[pkey] = person
                    person_order.append(pkey)

                # Causa ↔ party link.
                causa_demandado.append([f"{cid}::{rut}", cid, rol, rut])

                # Plate ↔ party links (a party may list several plates).
                plates = _plates(dem.get("patente"), dem.get("placa_patente")) or causa_plates
                for plate in plates:
                    patente_demandado.append([f"{cid}::{rut}::{plate}", cid, rol, rut, plate])

        # ── Table 3: Trámites (Sección C) ─────────────────────────────────────
        for ti, t in enumerate(d.get("tramites") or [], 1):
            tramites.append([
                f"{cid}/t{ti}", rol,
                t.get("fecha", ""),
                t.get("descripcion", ""),
                t.get("pdf_url", ""),
            ])

        # ── Table 4: Documentos (Sección D adjuntos) ──────────────────────────
        for xi, a in enumerate(d.get("adjuntos") or [], 1):
            documentos.append([
                f"{cid}/x{xi}", rol,
                a.get("descripcion", ""),
                a.get("pdf_url", ""),
            ])

    demandados = [person_index[k] for k in person_order]
    return causas, demandados, causa_demandado, patente_demandado, tramites, documentos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook", default=os.environ.get("SHEETS_WEBHOOK_URL", ""))
    ap.add_argument("--job-id", help="Export a single job. Omit with --all for everything.")
    ap.add_argument("--all", action="store_true", help="Export every job in the table.")
    ap.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", ""))
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SERVICE_KEY", ""))
    ap.add_argument("--no-db", action="store_true",
                    help="Skip mirroring into the Supabase relational tables (export_tables.sql).")
    args = ap.parse_args()

    if not args.webhook:
        sys.exit("ERROR: provide --webhook or set SHEETS_WEBHOOK_URL")
    if not (args.job_id or args.all):
        sys.exit("ERROR: pass --job-id <JOB> or --all")
    if not (args.supabase_url and args.supabase_key):
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    rows = fetch_rows(args.supabase_url, args.supabase_key,
                      None if args.all else args.job_id)
    causas, demandados, causa_demandado, patente_demandado, tramites, documentos = \
        build_tables(rows)

    payload = {
        "juzgados":          {"header": JUZGADOS_HEADER,           "rows": JUZGADOS_ROWS},
        "causas":            {"header": CAUSAS_HEADER,             "rows": causas},
        "demandados":        {"header": DEMANDADOS_HEADER,         "rows": demandados},
        "causa_demandado":   {"header": CAUSA_DEMANDADO_HEADER,    "rows": causa_demandado},
        "patente_demandado": {"header": PATENTE_DEMANDADO_HEADER,  "rows": patente_demandado},
        "tramites":          {"header": TRAMITES_HEADER,           "rows": tramites},
        "documentos":        {"header": DOCUMENTOS_HEADER,         "rows": documentos},
    }
    r = requests.post(args.webhook, json=payload, timeout=120)
    r.raise_for_status()
    print(
        f"Exported {len(causas)} causas, {len(demandados)} demandados, "
        f"{len(causa_demandado)} causa-demandado, {len(patente_demandado)} patente-demandado, "
        f"{len(tramites)} trámites, {len(documentos)} documentos → {r.text[:300]}"
    )

    # Mirror the normalized entities into Supabase relational tables. Demandados
    # are upserted first so causa_demandado.rut always references an existing
    # party. Rows without a usable key are skipped (rut for the entity/causa link).
    if not args.no_db:
        nd = upsert_table(args.supabase_url, args.supabase_key,
                          "demandados", "rut", DEMANDADOS_COLS,
                          [row for row in demandados if row[0]])
        ncd = upsert_table(args.supabase_url, args.supabase_key,
                           "causa_demandado", "vinculo_id", CAUSA_DEMANDADO_COLS,
                           [row for row in causa_demandado if row[3]])
        npd = upsert_table(args.supabase_url, args.supabase_key,
                           "patente_demandado", "vinculo_id", PATENTE_DEMANDADO_COLS,
                           patente_demandado)
        print(f"Supabase sync: {nd} demandados, {ncd} causa_demandado, {npd} patente_demandado")


if __name__ == "__main__":
    main()
