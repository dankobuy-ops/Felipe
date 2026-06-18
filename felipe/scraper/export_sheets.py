"""Export scraped JPL data from Supabase to a Google Sheet (standalone command).

Produces four linked tabs and POSTs them to a Google Apps Script web app bound
to the target sheet (see sheets_webapp.gs for the script + setup):

  Causas      — one row per causa (case header + remisor info)
  Demandados  — one row per demandado per causa (party + vehicle details)
  Trámites    — one row per trámite from Sección C (linked by Caso ID)
  Documentos  — one row per adjunto from Sección D (linked by Caso ID)

Usage:
  python export_sheets.py --webhook <APPS_SCRIPT_EXEC_URL> --all
  python export_sheets.py --webhook <URL> --job-id <JOB_UUID>

Env fallbacks: SHEETS_WEBHOOK_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY
"""
import argparse
import json
import os
import sys

import requests

JUZGADOS_HEADER = ["Juzgado ID", "Nombre", "URL"]
JUZGADOS_ROWS = [
    ["vitacura",    "Vitacura",     "https://vitacura.cl/municipalidad/juzgado/juzgado-policia-local/"],
    ["lobarnechea", "Lo Barnechea", "https://appl.smc.cl/JuzgadoDoc/frmBusqueda.aspx"],
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

DEMANDADOS_HEADER = [
    "Caso ID", "ROL",
    "Nombre", "Segundo Nombre", "Ap. Paterno", "Ap. Materno",
    "RUT", "Email", "Teléfono", "Domicilio",
    "Marca", "Modelo", "Año", "Patente", "Uso",
]

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

    causas, demandados, tramites, documentos = [], [], [], []

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

        # ── Table 2: Demandados ───────────────────────────────────────────────
        # Vehicle fallback from Section B if not captured per demandado
        veh = {
            "marca":   _first_match(causa, "marca", "marca_vehiculo", "marca_vehículo"),
            "modelo":  _first_match(causa, "modelo", "modelo_vehiculo", "modelo_vehículo"),
            "año":     _first_match(causa, "año", "ano", "año_vehiculo", "año_vehículo"),
            "patente": _first_match(causa, "placa_patente"),
            "uso":     _first_match(causa, "uso", "uso_vehiculo", "uso_vehículo"),
        }
        dem_list = d.get("demandados") or []
        if not dem_list:
            demandados.append([f"{cid}/d1", rol, "", "", "", "", "", "", "", "",
                               veh["marca"], veh["modelo"], veh["año"], veh["patente"], veh["uso"]])
        else:
            for di, dem in enumerate(dem_list, 1):
                nombre, segundo, ap_paterno, ap_materno = _split_name(dem.get("nombre", ""))
                demandados.append([
                    f"{cid}/d{di}", rol,
                    nombre, segundo, ap_paterno, ap_materno,
                    dem.get("rut", ""),
                    dem.get("email", ""),
                    dem.get("telefono", ""),
                    _domicilio(dem),
                    dem.get("marca") or veh["marca"],
                    dem.get("modelo") or veh["modelo"],
                    dem.get("año") or veh["año"],
                    dem.get("patente") or veh["patente"],
                    dem.get("uso") or veh["uso"],
                ])

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

    return causas, demandados, tramites, documentos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook", default=os.environ.get("SHEETS_WEBHOOK_URL", ""))
    ap.add_argument("--job-id", help="Export a single job. Omit with --all for everything.")
    ap.add_argument("--all", action="store_true", help="Export every job in the table.")
    ap.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", ""))
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SERVICE_KEY", ""))
    args = ap.parse_args()

    if not args.webhook:
        sys.exit("ERROR: provide --webhook or set SHEETS_WEBHOOK_URL")
    if not (args.job_id or args.all):
        sys.exit("ERROR: pass --job-id <JOB> or --all")
    if not (args.supabase_url and args.supabase_key):
        sys.exit("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_KEY")

    rows = fetch_rows(args.supabase_url, args.supabase_key,
                      None if args.all else args.job_id)
    causas, demandados, tramites, documentos = build_tables(rows)

    payload = {
        "juzgados":   {"header": JUZGADOS_HEADER,    "rows": JUZGADOS_ROWS},
        "causas":     {"header": CAUSAS_HEADER,       "rows": causas},
        "demandados": {"header": DEMANDADOS_HEADER,   "rows": demandados},
        "tramites":   {"header": TRAMITES_HEADER,     "rows": tramites},
        "documentos": {"header": DOCUMENTOS_HEADER,   "rows": documentos},
    }
    r = requests.post(args.webhook, json=payload, timeout=120)
    r.raise_for_status()
    print(
        f"Exported {len(causas)} causas, {len(demandados)} demandados, "
        f"{len(tramites)} trámites, {len(documentos)} documentos → {r.text[:300]}"
    )


if __name__ == "__main__":
    main()
