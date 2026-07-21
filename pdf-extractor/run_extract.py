"""End-to-end: OCR each demanda PDF for its plate(s), then join Rol / Tribunal /
RUT-demandado from the JPL scraper's Google Sheet, and emit the 4-column result.

Columns (as requested): Patente | RUT demandado | Rol causa | Tribunal
One row per (case, plate) — a case with N plates yields N rows, so each plate is
its own row ready for the downstream patente->owner enrichment.

Output: out/patentes_extraidas.csv  (paste-ready for the Google Sheet).
Rol/Tribunal/RUT come from authoritative scraped data; only Patente is OCR'd.
"""
import csv
import os
import sys
import glob

import extract  # OCR + plate parsing (validated)

SAMPLES = r"C:\Claude\pdf-extractor\samples"
OUT_DIR = r"C:\Claude\pdf-extractor\out"
SCRAPER = r"C:\Claude\felipe\scraper"

TRIBUNAL_NAMES = {
    "lobarnechea": "Juzgado de Policía Local de Lo Barnechea",
    "vitacura":    "Juzgado de Policía Local de Vitacura",
}

def load_join():
    """Read the scraper Sheet once: caso_id -> {rol, tribunal, demandado_ruts}."""
    sys.path.insert(0, SCRAPER)
    import gstore
    store = gstore.Store()
    juz_name = {j["juzgado_id"]: j.get("nombre", "") for j in store.read_tab("Juzgados")}
    ruts = {r["rut"]: r for r in store.read_tab("Ruts")}
    ddo = {}   # caso_id -> [ (rut, nombre) ]
    for v in store.read_tab("CausaXRut"):
        if v.get("rol_parte") == "demandado" and v.get("caso_id"):
            rr = ruts.get(v["rut"], {})
            nom = " ".join(x for x in (rr.get("nombre",""), rr.get("ap_paterno",""),
                                       rr.get("ap_materno","")) if x).strip() \
                  or rr.get("razon_social","")
            ddo.setdefault(v["caso_id"], []).append((v["rut"], nom))
    join = {}
    for c in store.read_tab("Causas"):
        cid = c.get("caso_id")
        if not cid:
            continue
        juz = c.get("juzgado_id", "")
        trib = TRIBUNAL_NAMES.get(juz) or juz_name.get(juz) or juz
        join[cid] = {"rol": c.get("rol", ""), "tribunal": trib,
                     "demandados": ddo.get(cid, [])}
    return join

def main():
    args = sys.argv[1:]
    cap = int(args[args.index("--max")+1]) if "--max" in args else None
    folder = next((a for a in args if not a.startswith("--") and os.path.isdir(a)), SAMPLES)

    print("[1/3] Reading join data from the JPL scraper Sheet…")
    join = load_join()
    print(f"      {len(join)} causas available to join.")

    os.makedirs(OUT_DIR, exist_ok=True)
    rows = []
    pdfs = sorted(glob.glob(os.path.join(folder, "*.pdf")))
    print(f"[2/3] OCR-reading {len(pdfs)} PDF(s) for plates…")
    for path in pdfs:
        juz, rol, _ = extract.parse_name(path)
        cid = f"{juz}/{rol}" if juz and rol else None
        plates, npg = extract.extract_pdf(path, max_pages=cap)
        info = join.get(cid, {})
        rol_v = info.get("rol", rol or "")
        trib = info.get("tribunal", "")
        dem = info.get("demandados", [])
        dem_ruts = "; ".join(r for r, _ in dem)
        print(f"      {os.path.basename(path)} -> plates={plates}  DDO={dem_ruts or '(none)'}")
        if not plates:
            rows.append({"Patente": "", "RUT demandado": dem_ruts,
                         "Rol causa": rol_v, "Tribunal": trib,
                         "_archivo": os.path.basename(path), "_nota": "sin patente OCR"})
            continue
        for p in plates:
            rows.append({"Patente": p, "RUT demandado": dem_ruts,
                         "Rol causa": rol_v, "Tribunal": trib,
                         "_archivo": os.path.basename(path), "_nota": ""})

    out = os.path.join(OUT_DIR, "patentes_extraidas.csv")
    cols = ["Patente", "RUT demandado", "Rol causa", "Tribunal", "_archivo", "_nota"]
    print(f"[3/3] Writing {len(rows)} row(s) -> {out}")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("Done.")

if __name__ == "__main__":
    main()
