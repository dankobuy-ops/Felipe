"""Export scraped JPL data from Supabase to a Google Sheet + relational tables.

Source of truth stays the `checkpoints` JSON store. This builds the derived
relational model (see schema.sql) and writes it to BOTH a Google Sheet (via the
Apps Script web app, sheets_webapp.gs) and the Supabase relational tables.

Model — 6 entity tables + 2 junctions:
  juzgados        — static list of courts
  ruts            — every RUT-identified party (demandantes, demandados, owners),
                    deduped by RUT; personal/enrichment fields merged across causas
  causas          — one row per case header
  tramites        — Sección C movements, linked by caso_id
  documentos      — Sección D adjuntos, linked by caso_id
  patentes        — master plate list; enrichment fields filled where available
  causa_rut       — junction: party ↔ causa, with rol_parte (demandante/demandado)
  causa_patente   — junction: plate ↔ causa (and the party who had it)

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

_PLATE_RE = re.compile(r"^[A-Z]{2,4}\d{2,4}$")

JUZGADO_NAMES = {"vitacura": "Vitacura", "lobarnechea": "Lo Barnechea"}
JUZGADOS_HEADER = ["Juzgado ID", "Nombre", "URL"]
JUZGADOS_COLS   = ["juzgado_id", "nombre", "url"]
JUZGADOS_ROWS = [
    ["vitacura",    "Vitacura",     "https://vitacura.cl/municipalidad/juzgado/juzgado-policia-local/"],
    ["lobarnechea", "Lo Barnechea", "https://mlobarnechea.custhelp.com/app/answers/detail/a_id/83/incidents.c$tipo_atencion/221"],
]

RUTS_HEADER = ["RUT", "Tipo", "Nombre", "Segundo Nombre", "Ap. Paterno",
               "Ap. Materno", "Razón Social", "Email", "Teléfono", "Domicilio"]
RUTS_COLS   = ["rut", "tipo", "nombre", "segundo_nombre", "ap_paterno",
               "ap_materno", "razon_social", "email", "telefono", "domicilio"]

CAUSAS_HEADER = ["Caso ID", "ROL", "Juzgado ID", "Materia", "Fecha Causa",
                 "Fecha Citación", "Fecha Estado", "Estado", "Boleta N°",
                 "Fecha Boleta", "Monto Demandado"]
CAUSAS_COLS   = ["caso_id", "rol", "juzgado_id", "materia", "fecha_causa",
                 "fecha_citacion", "fecha_estado", "estado", "boleta_numero",
                 "boleta_fecha", "monto_demandado"]

TRAMITES_HEADER = ["Trámite ID", "Caso ID", "Fecha", "Descripción", "Link PDF"]
TRAMITES_COLS   = ["tramite_id", "caso_id", "fecha", "descripcion", "pdf_url"]

DOCUMENTOS_HEADER = ["Documento ID", "Caso ID", "Descripción", "Link PDF"]
DOCUMENTOS_COLS   = ["documento_id", "caso_id", "descripcion", "pdf_url"]

PATENTES_HEADER = ["Patente", "RUT Propietario", "Tipo", "Marca", "Modelo",
                   "Año", "Color", "N° Motor", "N° Chasis", "Combustible"]
PATENTES_COLS   = ["patente", "rut_propietario", "tipo", "marca", "modelo",
                   "anio", "color", "num_motor", "num_chasis", "combustible"]

CAUSA_RUT_HEADER = ["Vínculo ID", "Caso ID", "RUT", "Rol Parte"]
CAUSA_RUT_COLS   = ["vinculo_id", "caso_id", "rut", "rol_parte"]

CAUSA_PATENTE_HEADER = ["Vínculo ID", "Caso ID", "RUT", "Patente"]
CAUSA_PATENTE_COLS   = ["vinculo_id", "caso_id", "rut", "patente"]


# ── Supabase I/O ──────────────────────────────────────────────────────────────

def _hdr(key):
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def fetch_rows(sb_url, sb_key, job_id=None):
    params = {"select": "job_id,record_id,status,text", "order": "job_id"}
    if job_id:
        params["job_id"] = f"eq.{job_id}"
    r = requests.get(f"{sb_url}/rest/v1/checkpoints", headers=_hdr(sb_key),
                     params=params, timeout=90)
    r.raise_for_status()
    return r.json()


def fetch_patentes(sb_url, sb_key):
    """Existing enriched plate rows, keyed by patente."""
    r = requests.get(f"{sb_url}/rest/v1/patentes", headers=_hdr(sb_key),
                     params={"select": ",".join(PATENTES_COLS)}, timeout=60)
    r.raise_for_status()
    return {row["patente"]: row for row in r.json()}


def upsert_table(sb_url, sb_key, table, conflict_col, cols, rows,
                 null_cols=(), batch_size=200):
    """Upsert positional rows (parallel to `cols`) with the service key.

    `null_cols` are columns where an empty string is sent as NULL — needed for
    nullable foreign keys (an FK can't reference ''). Returns rows written.
    """
    if not rows:
        return 0
    url = f"{sb_url}/rest/v1/{table}?on_conflict={conflict_col}"
    headers = {**_hdr(sb_key), "Content-Type": "application/json",
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    written = 0
    for i in range(0, len(rows), batch_size):
        chunk = []
        for r in rows[i:i + batch_size]:
            d = dict(zip(cols, r))
            for c in null_cols:
                if d.get(c) in ("", None):
                    d[c] = None
            chunk.append(d)
        resp = requests.post(url, headers=headers, json=chunk, timeout=60)
        resp.raise_for_status()
        written += len(chunk)
    return written


# ── Helpers ───────────────────────────────────────────────────────────────────

def _caso_id(job, rol):
    return f"{(job or '')[:8]}/{rol}"


def _rut_num(rut):
    digits = re.sub(r"[^0-9]", "", (rut or "").split("-")[0])
    return int(digits) if digits else 0


def _tipo_for(rut, razon_social="", nombre=""):
    if razon_social and not nombre:
        return "empresa"
    if nombre:
        return "persona"
    return "empresa" if _rut_num(rut) >= 50_000_000 else "persona"


def _split_name(nombre):
    """Split "APELLIDO1 APELLIDO2, NOMBRE1 NOMBRE2" (or positional) → 4 parts."""
    if not nombre:
        return "", "", "", ""
    nombre = nombre.strip()
    if "," in nombre:
        apellidos_str, nombres_str = nombre.split(",", 1)
        apellidos = apellidos_str.strip().split()
        nombres = nombres_str.strip().split()
        ap_paterno = apellidos[0].title() if len(apellidos) >= 1 else ""
        ap_materno = apellidos[1].title() if len(apellidos) >= 2 else ""
        nombre1 = nombres[0].title() if len(nombres) >= 1 else ""
        segundo = " ".join(p.title() for p in nombres[1:])
        return nombre1, segundo, ap_paterno, ap_materno
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
    return (parts[2].title(), " ".join(p.title() for p in parts[3:]),
            parts[0].title(), parts[1].title())


def _plates(*fields):
    out, seen = [], set()
    for field in fields:
        for tok in re.split(r"[\n,;/]+", field or ""):
            p = re.sub(r"[\s\-.]", "", tok).strip().upper()
            if p and _PLATE_RE.match(p) and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _merge(existing, new):
    """Field-by-field merge: existing wins, new fills blanks."""
    return [e or n for e, n in zip(existing, new)]


def _domicilio(party):
    return ", ".join(p for p in (party.get("direccion", ""), party.get("comuna", "")) if p)


def _first(d, *keys):
    for k in keys:
        if d.get(k):
            return d[k]
    return ""


# ── Build ─────────────────────────────────────────────────────────────────────

def build_tables(rows, patentes_by_plate):
    job_meta = {}
    for row in rows:
        if row.get("record_id") == "__meta__":
            try:
                job_meta[row["job_id"]] = json.loads(row.get("text") or "{}")
            except Exception:
                pass

    causas, tramites, documentos = [], [], []
    causa_rut, causa_patente = [], []
    ruts_index, ruts_order = {}, []          # rut -> positional row
    all_plates = set()

    def add_rut(row):
        rut = row[0]
        if not rut:
            return
        if rut in ruts_index:
            ruts_index[rut] = _merge(ruts_index[rut], row)
        else:
            ruts_index[rut] = row
            ruts_order.append(rut)

    for row in rows:
        rid = row.get("record_id", "")
        if rid in ("__job__", "__meta__"):
            continue
        try:
            d = json.loads(row.get("text") or "{}")
        except Exception:
            d = {}

        rol = d.get("rol") or rid
        job = row.get("job_id", "")
        cid = _caso_id(job, rol)
        causa = d.get("causa") or {}
        meta = job_meta.get(job, {})
        juzgado_id = meta.get("juzgado", "")
        if juzgado_id not in JUZGADO_NAMES:
            juzgado_id = ""  # -> NULL FK

        # Causas
        causas.append([
            cid, rol, juzgado_id,
            d.get("descripcion", "") or _first(causa, "descripcion", "descripción",
                                                "materia", "materia_causa", "materia_de_la_causa"),
            _first(causa, "fecha_causa"),
            _first(causa, "fecha_citacion", "fecha_citación"),
            _first(causa, "fecha_estado"),
            causa.get("estado", ""),
            causa.get("boleta_numero", ""),
            causa.get("boleta_fecha", ""),
            _first(causa, "monto", "monto_demandado", "cuantia", "cuantía", "monto_multa"),
        ])

        # Demandante → ruts (empresa) + causa_rut
        drut = meta.get("rut", "")
        if drut:
            razon = _first(causa, "remisor") or meta.get("razon_social", "")
            add_rut([drut, "empresa", "", "", "", "", razon, "", "", ""])
            causa_rut.append([f"{cid}::{drut}", cid, drut, "demandante"])

        # Demandados → ruts (persona) + causa_rut + causa_patente
        causa_plates = _plates(causa.get("placa_patente"), d.get("placa_patente"))
        all_plates.update(causa_plates)
        dem_list = d.get("demandados") or []

        if not dem_list:
            for plate in causa_plates:
                causa_patente.append([f"{cid}::::{plate}", cid, "", plate])
        else:
            for dem in dem_list:
                rut = dem.get("rut", "")
                nombre, segundo, ap_pat, ap_mat = _split_name(dem.get("nombre", ""))
                if rut:  # entities require a key; skip blank-RUT parties
                    add_rut([rut, "persona", nombre, segundo, ap_pat, ap_mat, "",
                             dem.get("email", ""), dem.get("telefono", ""), _domicilio(dem)])
                    causa_rut.append([f"{cid}::{rut}", cid, rut, "demandado"])
                plates = _plates(dem.get("patente"), dem.get("placa_patente")) or causa_plates
                all_plates.update(plates)
                for plate in plates:
                    causa_patente.append([f"{cid}::{rut}::{plate}", cid, rut, plate])

        # Trámites / Documentos
        for ti, t in enumerate(d.get("tramites") or [], 1):
            tramites.append([f"{cid}/t{ti}", cid, t.get("fecha", ""),
                             t.get("descripcion", ""), t.get("pdf_url", "")])
        for xi, a in enumerate(d.get("adjuntos") or [], 1):
            documentos.append([f"{cid}/x{xi}", cid, a.get("descripcion", ""),
                               a.get("pdf_url", "")])

    # Vehicle owners (from enriched patentes) → ruts
    for plate, prow in patentes_by_plate.items():
        owner = prow.get("rut_propietario") or ""
        if owner:
            add_rut([owner, _tipo_for(owner), "", "", "", "", "", "", "", ""])

    # Patentes for the sheet: every plate, enriched where available
    all_plates.update(patentes_by_plate.keys())
    patentes = []
    for plate in sorted(all_plates):
        p = patentes_by_plate.get(plate, {})
        patentes.append([plate] + [p.get(c, "") or "" for c in PATENTES_COLS[1:]])

    ruts = [ruts_index[k] for k in ruts_order]
    return {
        "juzgados":      JUZGADOS_ROWS,
        "ruts":          ruts,
        "causas":        causas,
        "tramites":      tramites,
        "documentos":    documentos,
        "patentes":      patentes,
        "causa_rut":     causa_rut,
        "causa_patente": causa_patente,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook", default=os.environ.get("SHEETS_WEBHOOK_URL", ""))
    ap.add_argument("--job-id", help="Export a single job. Omit with --all for everything.")
    ap.add_argument("--all", action="store_true", help="Export every job in the table.")
    ap.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", ""))
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SERVICE_KEY", ""))
    ap.add_argument("--no-db", action="store_true", help="Skip the Supabase relational mirror.")
    ap.add_argument("--no-sheet", action="store_true", help="Skip the Google Sheet push.")
    args = ap.parse_args()

    if not (args.supabase_url and args.supabase_key):
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY")
    if not args.no_sheet and not args.webhook:
        sys.exit("ERROR: provide --webhook / SHEETS_WEBHOOK_URL (or pass --no-sheet)")
    if not (args.job_id or args.all):
        sys.exit("ERROR: pass --job-id <JOB> or --all")

    rows = fetch_rows(args.supabase_url, args.supabase_key,
                      None if args.all else args.job_id)
    patentes_by_plate = fetch_patentes(args.supabase_url, args.supabase_key)
    t = build_tables(rows, patentes_by_plate)

    if not args.no_sheet:
        payload = {
            "juzgados":      {"header": JUZGADOS_HEADER,      "rows": t["juzgados"]},
            "ruts":          {"header": RUTS_HEADER,          "rows": t["ruts"]},
            "causas":        {"header": CAUSAS_HEADER,        "rows": t["causas"]},
            "tramites":      {"header": TRAMITES_HEADER,      "rows": t["tramites"]},
            "documentos":    {"header": DOCUMENTOS_HEADER,    "rows": t["documentos"]},
            "patentes":      {"header": PATENTES_HEADER,      "rows": t["patentes"]},
            "causa_rut":     {"header": CAUSA_RUT_HEADER,     "rows": t["causa_rut"]},
            "causa_patente": {"header": CAUSA_PATENTE_HEADER, "rows": t["causa_patente"]},
        }
        r = requests.post(args.webhook, json=payload, timeout=120)
        r.raise_for_status()
        print(f"Sheet: {r.text[:200]}")

    if not args.no_db:
        u, k = args.supabase_url, args.supabase_key
        # FK-safe order: entities before junctions; ruts/causas/patentes before links.
        n = {}
        n["juzgados"] = upsert_table(u, k, "juzgados", "juzgado_id", JUZGADOS_COLS, t["juzgados"])
        n["ruts"]     = upsert_table(u, k, "ruts", "rut", RUTS_COLS, t["ruts"])
        n["causas"]   = upsert_table(u, k, "causas", "caso_id", CAUSAS_COLS, t["causas"],
                                     null_cols={"juzgado_id"})
        # Ensure every referenced plate exists (patente-only, so enrichment is kept).
        plate_rows = [[p[0]] for p in t["patentes"]]
        n["patentes"] = upsert_table(u, k, "patentes", "patente", ["patente"], plate_rows)
        n["tramites"]   = upsert_table(u, k, "tramites", "tramite_id", TRAMITES_COLS, t["tramites"])
        n["documentos"] = upsert_table(u, k, "documentos", "documento_id", DOCUMENTOS_COLS, t["documentos"])
        n["causa_rut"]  = upsert_table(u, k, "causa_rut", "vinculo_id", CAUSA_RUT_COLS, t["causa_rut"])
        n["causa_patente"] = upsert_table(u, k, "causa_patente", "vinculo_id",
                                          CAUSA_PATENTE_COLS, t["causa_patente"], null_cols={"rut"})
        print("Supabase:", ", ".join(f"{v} {kk}" for kk, v in n.items()))

    print("Totals:", ", ".join(f"{len(v)} {kk}" for kk, v in t.items()))


if __name__ == "__main__":
    main()
