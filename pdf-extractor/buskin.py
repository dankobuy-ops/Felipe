"""Buskin — fill missing vehicle plates for JPL cases, straight from Google Drive.

Links to the JPL scraper's Drive 'Documentos' folder (owned by danko.buy — same
login the scraper uses), OCRs ONLY the cases that don't yet have a plate, stops at
the first plate found per case, and upserts the result to the output sheet.
Resumable: every attempted rol is checkpointed locally, so a re-run continues where
it left off (and never re-OCRs a case already handled).

Usage:
  python buskin.py --pilot 20         # process 20 gap-cases (measure throughput)
  python buskin.py --rols 1096,1097   # process specific rols (testing)
  python buskin.py                    # process ALL remaining gap-cases
  python buskin.py --dry-run ...      # OCR + print, don't write the sheet
"""
import io
import json
import os
import re
import sys
import time

import fitz
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

SCRAPER = r"C:\Claude\felipe\scraper"
sys.path.insert(0, SCRAPER)
import gauth      # noqa: E402
import gstore     # noqa: E402
import patente    # noqa: E402
import sheet as outsheet  # noqa: E402  (output-sheet writer)

HERE = r"C:\Claude\pdf-extractor"
CKPT = os.path.join(HERE, "buskin_checkpoint.json")
JUZGADO = "lobarnechea"
PAGE_CAP = int(os.environ.get("BUSKIN_PAGE_CAP", "4"))    # max SCANNED pages OCR'd per case
# (plates live on template pages [0,4,15], probed first; 8 covers them + a margin,
# so 'no plate' concludes fast instead of OCR-ing a whole scanned bundle)
# Investigation showed the plate lives in doc0, on one of these pages by template:
#   0 = old Procobro, 4 = new Costanera/ACOFK, 15 = long bundle. Probe them first.
PROBE_FIRST = (0, 4, 15)
TRIBUNAL = {"lobarnechea": "Juzgado de Policía Local de Lo Barnechea",
            "vitacura": "Juzgado de Policía Local de Vitacura"}

_OCR = None
def _ocr():
    global _OCR
    if _OCR is None:
        _OCR = RapidOCR()
    return _OCR

def _page_text(page, zoom=2.6):
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
    res, _ = _ocr()(img)
    return "\n".join(l[1] for l in res) if res else ""

# ── checkpoint ────────────────────────────────────────────────────────────────
def load_ckpt():
    if os.path.exists(CKPT):
        return json.load(open(CKPT, encoding="utf-8"))
    return {"done": {}}      # rol -> {plates, status, pages}
def save_ckpt(ck):
    json.dump(ck, open(CKPT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

# ── join + targets (from the scraper Sheet) ──────────────────────────────────
def build_context(store):
    """Returns (targets_missing_rol_list, join_by_rol)."""
    causas = [c for c in store.read_tab("Causas") if c.get("juzgado_id") == JUZGADO]
    cxp = store.read_tab("CausaXPatente")
    have = {v["caso_id"] for v in cxp if v.get("caso_id") and v.get("patente")}
    ruts = {r["rut"]: r for r in store.read_tab("Ruts")}
    ddo = {}
    for v in store.read_tab("CausaXRut"):
        if v.get("rol_parte") == "demandado" and v.get("caso_id"):
            ddo.setdefault(v["caso_id"], []).append(v["rut"])
    join = {}
    missing = []
    for c in causas:
        cid = c.get("caso_id"); rol = c.get("rol")
        if not cid or not rol:
            continue
        join[rol] = {"rol": rol, "tribunal": TRIBUNAL.get(JUZGADO, JUZGADO),
                     "demandado": "; ".join(ddo.get(cid, []))}
        if cid not in have:
            missing.append(rol)
    return missing, join

# ── Drive: index docs per rol ────────────────────────────────────────────────
_DOCNAME = re.compile(r"^lobarnechea__(?P<rol>[^_]+)__doc(?P<n>\d+)\.pdf$", re.I)
DRIVE_IDX_CACHE = os.path.join(HERE, "drive_index.json")

def drive_index(drive, folder, use_cache=True):
    """rol -> sorted list of [docn, file_id]. Cached to disk (15k+ files) so a
    resume doesn't re-page the whole folder on every startup."""
    if use_cache and os.path.exists(DRIVE_IDX_CACHE):
        return json.load(open(DRIVE_IDX_CACHE, encoding="utf-8"))
    idx = {}
    tok = None
    q = f"'{folder}' in parents and trashed = false and mimeType='application/pdf'"
    while True:
        resp = drive.files().list(q=q, fields="nextPageToken, files(id,name)",
                                  pageSize=1000, pageToken=tok).execute()
        for f in resp.get("files", []):
            m = _DOCNAME.match(f["name"])
            if m:
                idx.setdefault(m.group("rol"), []).append([int(m.group("n")), f["id"]])
        tok = resp.get("nextPageToken")
        if not tok:
            break
    for rol in idx:
        idx[rol].sort()
    json.dump(idx, open(DRIVE_IDX_CACHE, "w", encoding="utf-8"))
    return idx

def process_case(drive, docs, page_cap=PAGE_CAP):
    """Read only doc0 (where the plate lives). HYBRID: use each page's real text
    layer when present (instant, exact) and OCR only the pages that are scanned
    images. Probe the likely template pages first, stop at the first plate.
    Returns (plates, status, ocr_pages). status:
      ok-text | ok-ocr | none-text | none-ocr | cap | err | no-docs."""
    if not docs:
        return [], "no-docs", 0
    _docn, fid = docs[0]                        # doc0 only
    try:
        data = drive.files().get_media(fileId=fid).execute()
        d = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return [], "err", 0
    total = d.page_count
    order = [p for p in PROBE_FIRST if p < total]
    order += [p for p in range(total) if p not in order]   # template pages first

    # Phase 1 — text layer (free). Also record which pages are scanned (no text).
    scanned = []
    for i in order:
        t = d[i].get_text("text")
        if t.strip():
            found = patente.plates_in_text(t)
            if found:
                return _uniq(found), "ok-text", 0
        else:
            scanned.append(i)
    if not scanned:
        return [], "none-text", 0              # fully digital, no new-format plate

    # Phase 2 — OCR only the scanned pages (smart order preserved), capped.
    # ANCHOR-ONLY here: the page-wide fallback mines boilerplate (law citations)
    # when OCR text is garbled, so it must not run on noisy OCR output.
    capped = len(scanned) > page_cap
    pages = 0
    for i in scanned[:page_cap]:
        txt = _page_text(d[i])
        pages += 1
        found = patente.plates_after_anchor(txt)
        if found:
            return _uniq(found), "ok-ocr", pages
    return [], ("cap" if capped else "none-ocr"), pages

def _uniq(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out

def _ok_rows(ck, join):
    """All 4-column rows for every 'ok' case currently in the checkpoint."""
    rows = []
    for r, v in ck["done"].items():
        if str(v.get("status", "")).startswith("ok"):
            j = join.get(r, {"rol": r, "tribunal": TRIBUNAL[JUZGADO], "demandado": ""})
            for p in v.get("plates", []):
                rows.append({"Patente": p, "RUT demandado": j["demandado"],
                             "Rol causa": j["rol"], "Tribunal": j["tribunal"]})
    return rows

def reconcile_push(ck, join, dry):
    """Idempotent upsert of every resolved plate to the sheet (safe to call often;
    the upsert only appends rows that aren't there yet)."""
    rows = _ok_rows(ck, join)
    if rows and not dry:
        url, added, skipped = outsheet.push(rows)
        return len(rows), added
    return len(rows), 0

def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    limit = int(args[args.index("--pilot")+1]) if "--pilot" in args else None
    maxn = int(args[args.index("--max")+1]) if "--max" in args else None
    only = None
    if "--rols" in args:
        only = [r.strip() for r in args[args.index("--rols")+1].split(",") if r.strip()]

    store = gstore.Store()
    print("[buskin] building targets from the scraper Sheet…")
    missing, join = build_context(store)
    drive = gauth.drive_client(gauth.credentials())
    cfg = json.load(open(os.path.join(SCRAPER, "jpl_config.json"), encoding="utf-8"))
    print("[buskin] indexing Drive documents…")
    idx = drive_index(drive, cfg["documentos_folder_id"])

    ck = load_ckpt()
    if only:
        todo = only
    else:
        # Only cases never processed yet (their status is already final under the
        # hybrid logic). Use --rols to force a re-attempt of specific cases.
        remaining = [r for r in missing if r not in ck["done"]]
        if limit:                      # --pilot: spread the sample across the range
            nums = sorted((r for r in remaining if r.isdigit()), key=int)
            step = max(1, len(nums) // limit)
            todo = nums[::step][:limit]
        else:
            todo = remaining
        if maxn:                       # --max: bound this batch (foreground chunks)
            todo = todo[:maxn]
    print(f"[buskin] gap cases missing a plate: {len(missing)}; "
          f"to process now: {len(todo)} (page cap/case={PAGE_CAP})")

    rows, t0, done_now = [], time.monotonic(), 0
    for k, rol in enumerate(todo, 1):
        docs = idx.get(rol, [])
        if not docs:
            ck["done"][rol] = {"status": "no-docs", "plates": [], "pages": 0}
            print(f"  [{k}/{len(todo)}] rol {rol}: no Drive docs")
            continue
        plates, status, pages = process_case(drive, docs)
        ck["done"][rol] = {"status": status, "plates": plates, "pages": pages}
        done_now += 1
        j = join.get(rol, {"rol": rol, "tribunal": TRIBUNAL[JUZGADO], "demandado": ""})
        for p in plates:
            rows.append({"Patente": p, "RUT demandado": j["demandado"],
                         "Rol causa": j["rol"], "Tribunal": j["tribunal"]})
        print(f"  [{k}/{len(todo)}] rol {rol}: {status} {plates} ({pages}p, {len(docs)} docs)")
        if k % 5 == 0:
            save_ckpt(ck)
        if k % 20 == 0 and not dry:          # incremental push so a kill can't lose progress
            n, added = reconcile_push(ck, join, dry)
            print(f"       …pushed to sheet (+{added} new; {n} ok rows total)")
    save_ckpt(ck)

    dt = time.monotonic() - t0
    print(f"\n[buskin] processed {done_now} case(s) in {dt:.0f}s "
          f"({dt/max(done_now,1):.1f}s/case).")

    from collections import Counter
    tally = Counter(str(v.get("status", "")) for v in ck["done"].values())
    print(f"[buskin] checkpoint status tally: {dict(tally)}")
    n, added = reconcile_push(ck, join, dry)
    if dry:
        print(f"[buskin] --dry-run: {n} ok rows (not written).")
    else:
        url = f"https://docs.google.com/spreadsheets/d/{outsheet._cfg().get('spreadsheet_id','')}/edit"
        print(f"[buskin] sheet reconciled: {n} ok rows total (+{added} new this pass) -> {url}")

if __name__ == "__main__":
    main()
