"""Load worker A's state.json into Neon. Safe to run WHILE the sweep is running.

The sweep and this script share nothing but a file. The sweep writes state.json and PDFs to
disk; this reads them and writes to Postgres. No CDP, no request to pjud.cl, so ingesting costs
nothing against the WAF budget and cannot disturb a run in progress.

The one real hazard is the file itself: state.json is rewritten after every causa with a plain
write_text, which is not atomic, so a read can land mid-write and see truncated JSON. We snapshot
it to a temp copy and retry a few times rather than ever parse the live file.

Mapping is delegated to ingest_cdp.build() — the same deterministic ids the rest of the data
already uses (causa_id = <tribunal_id>-<rol>, litigante = <causa_id>-<rut>, cuaderno =
<causa_id>-c<n>-<folio>-<k>). Re-running updates in place.

Worker A collects only cuaderno 1 and no receptor rows, so it writes exactly what it saw and
nothing it did not: no empty Notificaciones rows, no phantom cuaderno-2 shells.

Usage
    python ingest_worker_a.py --dry        # counts only, no writes
    python ingest_worker_a.py              # upload ebooks to Drive + upsert everything
    python ingest_worker_a.py --no-upload  # metadata only, leave causas.ebook alone
"""
import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import psycopg2.extras

sys.path.insert(0, str(Path(__file__).parent))
import re
import unicodedata

import run
import dbstore
import ingest_cdp
import gstore

DATA = Path(__file__).parent.parent / "data" / "worker_a"
STATE = DATA / "state.json"
PDFS = DATA / "pdfs"

# Tribunales is handled separately — see ingest() for why it must never be a plain upsert.
ORDER = ["Ruts", "Causas", "Litigantes", "Cuadernos", "Escritos"]


def snapshot(path, tries=6):
    """Read a file that another process is actively rewriting."""
    last = None
    for i in range(tries):
        tmp = Path(tempfile.gettempdir()) / f"wa_state_{i}.json"
        try:
            shutil.copy2(path, tmp)
            return json.loads(tmp.read_text(encoding="utf-8"))
        except Exception as e:            # torn write — the sweep is mid-save
            last = e
            time.sleep(1.5)
    raise SystemExit(f"could not read a consistent {path.name}: {str(last)[:90]}")


def as_causa(rec):
    """worker A record -> the shape ingest_cdp.build() consumes."""
    cuads = rec.get("cuadernos") or ["1 - Principal"]
    return {
        "rol": rec["rol"],
        "tribunalId": rec["tribunal_id"],
        "tribunalSel": rec.get("tribunal", ""),
        "corte": "",                     # Corte=Todos: worker A genuinely does not know it
        "header": rec.get("header") or {},
        "litigantes": rec.get("litigantes") or [],
        # Only cuaderno 1 was read. Claiming the others exist with empty historia would look
        # like "we checked and there was nothing", which is the opposite of the truth.
        "cuadernos": [{"cuaderno": cuads[0], "historia": rec.get("historia_c1") or []}],
        "escritos": rec.get("escritos") or [],
        "receptor": [],
        "ebook": rec.get("_ebook_url", ""),
        "scrape_level": "scraped",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-proc", default="obligaci.*dar",
                    help="regex on procedimiento; non-matching causas are not stored. Judged "
                         "from the harvested header, NOT from a flag in state.json.")
    ap.add_argument("--dry", action="store_true")
    # Uploading is ON by default. It was opt-in at first, on the reasoning that a long network
    # job should not fire as a side effect — but that left PDFs sitting on disk with causas.ebook
    # empty, which reads as "the documents were never captured". A stored document nobody can
    # find is not stored. The Drive traffic never touches the OJV, so there is no scrape cost to
    # protect against here.
    ap.add_argument("--no-upload", dest="upload_pdfs", action="store_false",
                    help="skip pushing ebooks to Drive (leaves causas.ebook untouched)")
    a = ap.parse_args()

    st = snapshot(STATE)
    causas = st.get("causas") or {}
    if not causas:
        return print("no causas in state.json yet")

    store = None if a.dry else dbstore.Store()

    if a.upload_pdfs and not a.dry:
        # upload_pdfs_parallel runs 5 Drive uploads at once and skips names already in the
        # folder, so re-running is cheap. Parallelism here is safe in a way it never is upstream:
        # these requests go to Google, not to the OJV, so they cost nothing against the WAF.
        # ⚠️ Consult the Drive cache BEFORE reading any bytes. upload_pdfs_parallel skips files
        # already in the folder, but only after being handed them — so reading every pdf first
        # meant this job loaded the ENTIRE corpus into memory on every run just to discard it.
        # Fine at 70 MB, not fine at the several hundred a full national sweep produces, and it
        # runs hourly.
        cache = store._load_doc_cache()
        items, known = [], 0
        for cid, rec in sorted(causas.items()):
            obj = f"{cid}/ebook.pdf"
            hit = cache.get(gstore._flatten_name(obj))
            if hit:
                rec["_ebook_url"] = dbstore.direct_link(hit)
                known += 1
                continue
            # ⚠️ Guard the EMPTY filename. A causa whose ebook was skipped or missing has no
            # "file", and PDFS / "" resolves to the pdfs DIRECTORY — whose .name is truthy and
            # .exists() is True, so this read a folder as bytes and threw PermissionError. That
            # killed the hourly job for hours, and with it the supervision that shares its run.
            fname = ((rec.get("ebook") or {}).get("file") or "").strip()
            if not fname:
                continue
            f = PDFS / fname
            if f.is_file():
                body = f.read_bytes()
                if body[:4] != b"%PDF":         # never publish a challenge page as a document
                    print(f"  [warn] {f.name} is not a pdf — skipped")
                    continue
                items.append((obj, body))
        print(f"  {known} ebook(s) already in Drive; uploading {len(items)} new...")
        links = store.upload_pdfs_parallel(items) if items else {}
        for cid, rec in causas.items():
            url = links.get(f"{cid}/ebook.pdf")
            if url:
                rec["_ebook_url"] = url
        if items:
            print(f"  {len(links)} link(s) returned")

    merged, tribs, ids = {}, {}, []
    def wanted(rec):
        """⚠️ Judge the PROCEDIMIENTO ITSELF, never a flag written into state.json.

        The flag alone was not enough: state.json is held in memory by the running worker and
        rewritten whole after every causa, so marks edited into the file from outside were
        silently overwritten on the next save — 49 of them, 2026-08-10 — and the ingest happily
        put 35 non-matching causas straight back into Neon after they had just been deleted. A
        rule evaluated from the data cannot be lost that way.
        """
        if rec.get("skipped_proc"):
            return False
        if not a.only_proc:
            return True
        pr = (rec.get("header") or {}).get("procedimiento", "")
        if not pr:
            return True                  # no header yet — let the shell through, judge it later
        flat = "".join(ch for ch in unicodedata.normalize("NFD", pr)
                       if unicodedata.category(ch) != "Mn")
        return re.search(a.only_proc, flat, re.I) is not None

    skipped_proc = 0
    for cid, rec in sorted(causas.items()):
        if not wanted(rec):
            skipped_proc += 1
            continue
        if not (rec.get("header") or {}):
            print(f"  skip {cid}: no header (metadata never harvested)")
            continue
        parts = ingest_cdp.build(as_causa(rec), {})
        for tab, rows in parts.items():
            if tab == "Tribunales":
                for t in rows:
                    tribs[t["id"]] = t["tribunal"]
                continue
            merged.setdefault(tab, []).extend(rows)
        ids.append(cid)

    print(f"worker A state: {len(causas)} causas, {len(ids)} with detail "
          f"({skipped_proc} skipped: procedimiento does not match {a.only_proc!r})")
    for tab in ORDER:
        print(f"  {tab:14} {len(merged.get(tab, [])):6} rows")
    print(f"  {'Tribunales':14} {len(tribs):6} (insert-if-absent only)")
    eb = sum(1 for r in causas.values() if (r.get('ebook') or {}).get('bytes'))
    print(f"  ebooks on disk {eb} — "
          f"{'uploaded to Drive' if a.upload_pdfs else 'NOT uploaded; causas.ebook left empty'}")
    if a.dry:
        return print("[DRY] no writes.")

    # ⚠️ Tribunales must NOT go through upsert. Worker A sweeps with Corte='Todos' and so has no
    # corte value; upsert writes every column from EXCLUDED, which would overwrite the corte of
    # every tribunal already in the table with ''. Insert the ones we do not have, touch nothing
    # that exists.
    with store.conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur, 'INSERT INTO "tribunales" ("id","corte","tribunal") VALUES %s '
                 'ON CONFLICT ("id") DO NOTHING',
            [(tid, "", name) for tid, name in tribs.items()])
        print(f"  tribunales: {cur.rowcount} new (existing rows untouched)")

    # ⚠️ Same trap as tribunales.corte, one table over. upsert writes EVERY column from
    # EXCLUDED, and worker A has no value for the document URLs — so ingesting a causa that was
    # already scraped with documents would blank ebook/texto_demanda/certificado. Harmless in the
    # north, where nothing overlaps; quietly destructive the moment this sweep reaches Santiago,
    # where 74 causas already carry those URLs. Carry the existing values forward.
    keep = ("ebook", "texto_demanda", "certificado")
    with store.conn.cursor() as cur:
        cur.execute(f'SELECT causa_id, {", ".join(keep)} FROM causas WHERE causa_id = ANY(%s)',
                    (ids,))
        prior = {r[0]: dict(zip(keep, r[1:])) for r in cur.fetchall()}
    kept = 0
    for row in merged.get("Causas", []):
        was = prior.get(row["causa_id"])
        if not was:
            continue
        for col in keep:
            if was.get(col) and not row.get(col):
                row[col] = was[col]
                kept += 1
    if kept:
        print(f"  preserved {kept} existing document URL(s) on {len(prior)} known causa(s)")

    for tab in ORDER:
        rows = merged.get(tab, [])
        if rows:
            print(f"  upserted {tab:14} {store.upsert(tab, rows)}")

    # 'scraped' = header/litigantes/historia collected. detalles stays false: the other documents
    # are still outstanding, and that flag is what tells a later pass there is work left here.
    with store.conn.cursor() as cur:
        cur.execute("UPDATE causas SET fill_status='scraped' WHERE causa_id = ANY(%s)", (ids,))
        print(f"  marked {cur.rowcount} causas fill_status='scraped'")
    print("DONE")


if __name__ == "__main__":
    main()
