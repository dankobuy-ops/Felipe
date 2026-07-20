"""Ingest a cdp_scrape.py JSON into the Neon `pjud_` tables via dbstore (idempotent
UPSERTs). Deterministic ids mirror run.py exactly, so re-loading updates in place and
ids stay consistent with existing data:
  causa_id      = <tribunal_id>-<rol>
  litigante id  = <causa_id>-<rut>
  cuaderno id   = <causa_id>-c<n>-<folio>-<k>
  escrito id    = <causa_id>-e<i>
  receptor id   = <causa_id>-r<i>
Docs/anexos (PDFs) are deferred (the doc JWTs are session-ephemeral).

Each causa needs `tribunalId` (the OJV #fecTribunal value). New cdp_scrape runs write
it; older JSONs can be patched, or pass --tribunal-map '<name>=<value>,...'.

Usage: python ingest_cdp.py <pjud_cdp_*.json> [--dry] [--tribunal-map "1º Juzgado Civil de Santiago=259"]
"""

import argparse
import json
import sys

sys.path.insert(0, r"C:\Claude\felipe\pjud\scraper")
import run          # helpers: norm_rut, split_persona, _cuaderno_num, _first_date, _paren_date, _now
import dbstore

ORDER = ["Tribunales", "Ruts", "Causas", "Litigantes", "Cuadernos",
         "Escritos", "Notificaciones Receptor", "Documentos", "Anexos"]


def resolve_tid(causa, name_map):
    tid = str(causa.get("tribunalId", "") or "").strip()
    if tid:
        return tid
    for key in (causa.get("tribunalSel", ""), causa.get("tribunal", "")):
        if key in name_map:
            return str(name_map[key])
    return ""


def build(causa, name_map):
    tid = resolve_tid(causa, name_map)
    rol = causa["rol"]
    if not tid:
        raise ValueError(f"{rol}: no tribunalId (tribunal={causa.get('tribunalSel')!r})")
    causa_id = f"{tid}-{rol}"
    out = {}

    def add(tab, rows):
        if rows:
            out.setdefault(tab, []).extend(rows)

    add("Tribunales", [{"id": tid, "corte": causa.get("corte", ""),
                        "tribunal": causa.get("tribunalSel") or causa.get("tribunal", "")}])

    h = causa.get("header", {})
    add("Causas", [{"causa_id": causa_id, "rol": rol, "f_ingreso": h.get("f_ingreso", ""),
                    "estado_adm": h.get("estado_adm", ""), "procedimiento": h.get("procedimiento", ""),
                    "ubicacion": h.get("ubicacion", ""), "estado_proc": h.get("estado_proc", ""),
                    "etapa": h.get("etapa", ""), "tribunal_id": tid, "competencia": "Civil",
                    "ebook": "", "updated_at": run._now()}])

    rut_rows, lit_rows = [], []
    for L in causa.get("litigantes", []):
        rut = run.norm_rut(L.get("rut", ""))
        if not rut:
            continue
        if "JUR" in (L.get("persona", "") or "").upper():
            rut_rows.append({"rut": rut, "tipo": "empresa", "razon_social": L.get("nombre", ""),
                             "updated_at": run._now()})
        else:
            nom, seg, apat, amat = run.split_persona(L.get("nombre", ""))
            rut_rows.append({"rut": rut, "tipo": "persona", "nombre": nom, "segundo_nombre": seg,
                             "ap_paterno": apat, "ap_materno": amat, "updated_at": run._now()})
        lit_rows.append({"id": f"{causa_id}-{rut}", "causa_id": causa_id, "rut": rut,
                         "participante": L.get("participante", ""), "updated_at": run._now()})
    add("Ruts", rut_rows)
    add("Litigantes", lit_rows)

    bare2full = {}
    for cu in causa.get("cuadernos", []):
        t = cu.get("cuaderno", "")
        bare = t.split(" - ", 1)[1].strip() if " - " in t else t
        bare2full[bare] = t

    cuad_rows = []
    for cu in causa.get("cuadernos", []):
        cuaderno = cu.get("cuaderno", "")
        cnum = run._cuaderno_num(cuaderno, 1)
        seen = {}
        for hh in cu.get("historia", []):
            folio = hh.get("folio", "")
            n = seen.get(folio, 0) + 1
            seen[folio] = n
            cuad_rows.append({"id": f"{causa_id}-c{cnum}-{folio}-{n}", "causa_id": causa_id,
                              "cuaderno": cuaderno, "folio": folio, "etapa": hh.get("etapa", ""),
                              "tramite": hh.get("tramite", ""), "descripcion_tramite": hh.get("desc", ""),
                              "fecha_tramite": run._first_date(hh.get("fecha", "")),
                              "fecha_diligencia": run._paren_date(hh.get("fecha", "")),
                              "foja": hh.get("foja", ""), "georref": hh.get("georref", "")})
    add("Cuadernos", cuad_rows)

    # Documentos + Anexos — only historia rows where a Drive url was captured (--docs).
    doc_rows, anex_rows = [], []
    for cu in causa.get("cuadernos", []):
        cnum = run._cuaderno_num(cu.get("cuaderno", ""), 1)
        seen = {}
        for hh in cu.get("historia", []):
            folio = hh.get("folio", "")
            n = seen.get(folio, 0) + 1
            seen[folio] = n
            cid = f"{causa_id}-c{cnum}-{folio}-{n}"
            if hh.get("doc_url"):
                doc_rows.append({"id": f"{cid}-doc", "cuaderno_id": cid,
                                 "origen": (hh.get("doc") or {}).get("action", ""),
                                 "folio": folio, "descripcion": hh.get("desc", ""),
                                 "url": hh["doc_url"]})
            if hh.get("anexo_url"):
                anex_rows.append({"id": f"{cid}-anexo", "cuaderno_id": cid,
                                  "origen": (hh.get("anexo") or {}).get("action", ""),
                                  "folio": folio, "fecha": hh.get("fecha", ""),
                                  "referencia": hh.get("desc", ""), "url": hh["anexo_url"]})
    add("Documentos", doc_rows)
    add("Anexos", anex_rows)

    esc_rows = []
    for ei, e in enumerate(causa.get("escritos", []), 1):
        esc_rows.append({"id": f"{causa_id}-e{ei}", "causa_id": causa_id, "cuaderno": "",
                         "fecha_ingreso": e.get("fecha_ingreso", ""), "tipo_escrito": e.get("tipo_escrito", ""),
                         "solicitante": e.get("solicitante", "")})
    add("Escritos", esc_rows)

    notif = []
    for i, rr in enumerate(causa.get("receptor", []), 1):
        full = bare2full.get(rr.get("cuaderno", ""), rr.get("cuaderno", ""))
        notif.append({"id": f"{causa_id}-r{i}", "Causa ID": causa_id, "Cuaderno": full,
                      "Nombre": rr.get("nombre", ""), "Fecha": rr.get("fecha", ""),
                      "Estado": rr.get("estado", "")})
    add("Notificaciones Receptor", notif)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--tribunal-map", default="",
                    help='fallback name=value pairs, e.g. "1º Juzgado Civil de Santiago=259"')
    args = ap.parse_args()

    name_map = {}
    for pair in args.tribunal_map.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            name_map[k.strip()] = v.strip()

    data = json.load(open(args.json, encoding="utf-8"))
    merged = {}
    for c in data:
        for tab, rows in build(c, name_map).items():
            merged.setdefault(tab, []).extend(rows)

    print(f"Ingest {len(data)} causa(s) from {args.json}")
    for tab in ORDER:
        print(f"  {tab:26} {len(merged.get(tab, [])):5} rows")
    print("  sample causa_id:", merged["Causas"][0]["causa_id"])

    if args.dry:
        print("[DRY] no writes.")
        return

    store = dbstore.Store()
    for tab in ORDER:
        rows = merged.get(tab, [])
        if rows:
            n = store.upsert(tab, rows)
            print(f"  upserted {tab:26} {n}")
    # mark these causas fully-scraped so cdp_scrape --resume skips them next time
    causa_ids = [r["causa_id"] for r in merged.get("Causas", [])]
    if causa_ids:
        with store.conn.cursor() as cur:
            cur.execute("UPDATE causas SET fill_status='scraped' WHERE causa_id = ANY(%s)",
                        (causa_ids,))
        print(f"  marked {len(causa_ids)} causas fill_status='scraped'")
    print("DONE")


if __name__ == "__main__":
    main()
