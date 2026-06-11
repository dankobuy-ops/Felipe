"""Export scraped JPL data from Supabase to a Google Sheet (standalone command).

Produces two linked tabs and POSTs them to a Google Apps Script web app bound
to the target sheet (see sheets_webapp.gs for the script + setup):

  Causas      — one row per causa with demandado details, case info, vehicle + PDF links
  Documentos  — one row per PDF (trámite / adjunto)

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

CAUSAS_HEADER = [
    "Caso ID", "ROL", "Fecha proceso", "Juzgado",
    # Case
    "Materia", "Monto demandado",
    # Demandado (primary)
    "Nombres", "Apellidos", "RUT", "Domicilio", "Email", "Teléfono",
    # Vehicle
    "Marca", "Modelo", "Año", "Patente",
    # PDFs
    "N° PDFs", "Links PDFs",
]

DOCS_HEADER = ["Caso ID", "ROL", "Sección", "Fecha", "Descripción", "PDF URL"]


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
    """Split a full-name string into (nombres, apellidos).

    Chilean official systems often use "APELLIDO1 APELLIDO2, NOMBRE1 NOMBRE2".
    If a comma is present: before comma = apellidos, after = nombres.
    Otherwise return the whole string as nombres with empty apellidos.
    """
    if not nombre:
        return "", ""
    if "," in nombre:
        apellidos, nombres = nombre.split(",", 1)
        return nombres.strip().title(), apellidos.strip().title()
    return nombre.strip().title(), ""


def _domicilio(party):
    parts = [party.get("direccion", ""), party.get("comuna", "")]
    return ", ".join(p for p in parts if p)


def _first_match(causa, *keys):
    """Return the first non-empty value from causa dict for the given keys."""
    for k in keys:
        v = causa.get(k, "")
        if v:
            return v
    return ""


def build_tables(rows):
    causas, documentos = [], []
    for row in rows:
        rid = row.get("record_id", "")
        if rid in ("__job__", "__meta__"):
            continue
        try:
            d = json.loads(row.get("text") or "{}")
        except Exception:
            d = {}
        rol  = d.get("rol") or rid
        job  = row.get("job_id", "")
        cid  = _caso_id(job, rol)
        causa = d.get("causa") or {}

        # Primary demandado
        demandados = d.get("demandados") or []
        dem = demandados[0] if demandados else {}
        nombres, apellidos = _split_name(dem.get("nombre", ""))

        # Vehicle fields — may live in causa section or demandado section
        marca   = _first_match(causa, "marca", "marca_vehiculo", "marca_vehículo")
        modelo  = _first_match(causa, "modelo", "modelo_vehiculo", "modelo_vehículo")
        año     = _first_match(causa, "año", "ano", "año_vehiculo", "año_vehículo")
        patente = _first_match(causa, "placa_patente")

        # Monto demandado — try several possible key names
        monto = _first_match(causa, "monto", "monto_demandado", "cuantia", "cuantía", "monto_multa")

        # PDF links
        tramites = d.get("tramites") or []
        adjuntos = d.get("adjuntos") or []
        all_docs = tramites + adjuntos
        pdf_links = [x["pdf_url"] for x in all_docs if x.get("pdf_url")]

        causas.append([
            cid,
            rol,
            d.get("fecha_proceso", ""),
            d.get("juzgado", ""),
            # Case
            d.get("descripcion", "") or causa.get("descripcion", "") or causa.get("descripción", ""),
            monto,
            # Demandado
            nombres,
            apellidos,
            dem.get("rut", ""),
            _domicilio(dem),
            dem.get("email", ""),
            dem.get("telefono", ""),
            # Vehicle
            marca,
            modelo,
            año,
            patente,
            # PDFs
            len(pdf_links),
            "\n".join(pdf_links),
        ])

        for t in tramites:
            if t.get("pdf_url"):
                documentos.append([cid, rol, "Trámite", t.get("fecha", ""),
                                   t.get("descripcion", ""), t["pdf_url"]])
        for a in adjuntos:
            if a.get("pdf_url"):
                documentos.append([cid, rol, "Adjunto", "",
                                   a.get("descripcion", ""), a["pdf_url"]])

    return causas, documentos


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
    causas, documentos = build_tables(rows)

    payload = {
        "causas":     {"header": CAUSAS_HEADER, "rows": causas},
        "documentos": {"header": DOCS_HEADER,   "rows": documentos},
    }
    r = requests.post(args.webhook, json=payload, timeout=120)
    r.raise_for_status()
    print(f"Exported {len(causas)} causas, {len(documentos)} documentos -> {r.text[:300]}")


if __name__ == "__main__":
    main()
