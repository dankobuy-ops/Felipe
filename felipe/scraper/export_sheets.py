"""Export scraped JPL data from Supabase to a Google Sheet (standalone command).

Produces two linked tables and POSTs them to a Google Apps Script web app bound
to the target sheet (see sheets_webapp.gs for the script + setup):

  Causas      — one row per causa  (Level 2 + summary detail)
  Documentos  — one row per trámite/adjunto PDF (Level 3)

The two tables are linked by the ROL column.

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
    "Caso ID", "ROL", "Job ID", "Descripción", "Fecha proceso", "Juzgado", "Estado",
    "Demandados", "Demandantes", "Rol inicio", "Actuario", "Placa patente",
    "Status", "N° docs", "N° PDFs",
]
DOCS_HEADER = ["Caso ID", "ROL", "Job ID", "Sección", "Fecha", "Descripción", "PDF URL"]


def _caso_id(job, rol):
    """Unique per-case key: short job prefix + ROL. Distinguishes the same ROL
    scraped across different jobs, and links the Causas/Documentos tabs."""
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


def _join_parties(parties):
    out = []
    for p in parties or []:
        nombre = (p.get("nombre") or "").strip()
        rut = (p.get("rut") or "").strip()
        if nombre:
            out.append(f"{nombre} ({rut})" if rut else nombre)
    return "; ".join(out)


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
        rol = d.get("rol") or rid
        job = row.get("job_id", "")
        causa = d.get("causa") or {}
        tramites = d.get("tramites") or []
        adjuntos = d.get("adjuntos") or []
        docs = tramites + adjuntos
        n_pdf = sum(1 for x in docs if x.get("pdf_url"))
        cid = _caso_id(job, rol)

        causas.append([
            cid, rol, job, d.get("descripcion", ""), d.get("fecha_proceso", ""),
            d.get("juzgado", ""), causa.get("estado", ""),
            _join_parties(d.get("demandados")), _join_parties(d.get("demandantes")),
            causa.get("rol_inicio", ""), causa.get("actuario", ""),
            causa.get("placa_patente", ""), row.get("status", ""),
            len(docs), n_pdf,
        ])
        for t in tramites:
            documentos.append([cid, rol, job, "Trámite", t.get("fecha", ""),
                               t.get("descripcion", ""), t.get("pdf_url", "")])
        for a in adjuntos:
            documentos.append([cid, rol, job, "Adjunto", a.get("fecha", ""),
                               a.get("descripcion", ""), a.get("pdf_url", "")])
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
        "documentos": {"header": DOCS_HEADER, "rows": documentos},
    }
    r = requests.post(args.webhook, json=payload, timeout=120)
    r.raise_for_status()
    print(f"Exported {len(causas)} causas, {len(documentos)} documentos -> {r.text[:300]}")


if __name__ == "__main__":
    main()
