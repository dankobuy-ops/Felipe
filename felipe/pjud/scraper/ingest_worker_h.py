"""INGEST WORKER H — put the JSON on disk into Neon.

    python ingest_worker_h.py --dry               # count what would land, write nothing
    python ingest_worker_h.py                     # ingest every data/worker_h/h-*.json
    python ingest_worker_h.py --file h-x.json     # just one

⚠️ WHY THIS EXISTS AT ALL, AND IT IS NOT A GOOD REASON. `worker_h.py` was built as a behavioural
prototype and wrote its records to JSON so a run could be inspected without touching the database.
That was fine for one test. Then it harvested 2,228 causas across an evening — 1,659 of them
carrying the cuaderno-2 historia the entire exercise existed to collect — while Neon went on
showing THIRTEEN causas with a second cuaderno, and I quoted delivery estimates twice without
noticing. Every run report was full of healthy numbers.

⇒ **A run's own tally is not evidence that the data landed. Count it where it is meant to END UP.**

⚠️ IT REUSES `ingest_worker_a.as_causa` AND `ingest_cdp.build` VERBATIM. A second row-builder is
exactly how the duplicated block detectors in this repo drifted apart and went blind together, and
the row ids matter more here than anywhere: `<causa>-c<n>-<folio>-<k>` is derived from the CUADERNO
LABEL, so a book-2 historia filed under book 1's label would stamp it `-c1-` and silently overwrite
worker B's rows. as_causa already carries each historia's own label; do not reimplement it.

⚠️ Records the gates rejected are NOT ingested. A causa closed for `etapa='8 Terminada'` has no
harvest to store, and writing a shell for it would put a row in front of the operator that looks
like a causa we hold. They are counted and reported instead.
"""
import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))
import dbstore
import gstore
import ingest_cdp
import run
from ingest_worker_a import as_causa

HERE = Path(__file__).parent
DATA = HERE.parent / "data" / "worker_h"
PDFS = DATA / "pdfs"

# ⚠️⚠️ NOT `ingest_worker_a.ORDER`. That list is ["Ruts","Causas","Litigantes","Cuadernos",
# "Escritos"] — correct for worker A, which is metadata-only and produces no documents. Worker H
# with --docs-c2 DOES, and importing A's list meant `ingest_cdp.build` built the Documentos rows
# and this file silently dropped them: the smoke run uploaded 7 PDFs to Drive, printed "7 link(s)
# returned", upserted five tables, and finished green with the document count UNCHANGED at 12.
# Every counter looked healthy and the thing the run existed to collect was thrown away — the
# same failure as worker H having no ingest at all, one layer further in.
# ⇒ Take the canonical order from ingest_cdp, which owns the row builders, and subtract only
# Tribunales (insert-if-absent below, because worker H sweeps Corte=Todos and knows no corte).
# The order matters: Documentos references a Cuadernos row, so it must be written after it.
ORDER = [t for t in ingest_cdp.ORDER if t != "Tribunales"]


def load(paths):
    """Every record from every file, newest file winning on a duplicate causa_id."""
    causas, dupes, gated, headerless = {}, 0, 0, 0
    regated = {}
    for f in paths:
        try:
            recs = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [skip] {f.name}: {str(e)[:60]}")
            continue
        for rec in recs:
            cid = rec.get("causa_id")
            if not cid:
                continue
            if rec.get("skipped_etapa") or rec.get("skipped_proc"):
                gated += 1
                # ⚠️ RECORD THE ETAPA THAT REJECTED IT, or we pay for this open again every pass.
                # The stored etapa is whatever the causa had when first discovered; the header we
                # just read says otherwise. fill_targets() gates on the STORED value, so skipping
                # these records entirely means the work-list keeps handing them back — measured
                # 2026-08-17: 32 of 40 opens in some courts were causas already opened and
                # rejected on an earlier pass. The open is the scarcest thing we spend.
                et = (rec.get("header") or {}).get("etapa", "")
                if et and rec.get("skipped_etapa"):
                    regated[cid] = et
                continue
            if not (rec.get("header") or {}):
                headerless += 1
                continue
            # ⚠️ AND THE GATE AGAIN, FROM THE HEADER WE STORED. A record harvested before the
            # gate's keyword list last changed can carry an etapa we now reject; the cheapest
            # place to catch that is here, not after it is in the table.
            if run.etapa_rejected((rec.get("header") or {}).get("etapa", "")):
                gated += 1
                continue
            # ⚠️ BACKFILL WHAT THE EARLY RECORDS LACK. 1,154 causas were written before worker H
            # stored tribunal_id, and the row builder reads it directly. causa_id is "<tid>-<rol>",
            # so the id is recoverable; the tribunal NAME is not, and an empty name must never be
            # written into Tribunales (see the insert-if-absent guard below).
            if not rec.get("tribunal_id"):
                rol = rec.get("rol") or ""
                rec["tribunal_id"] = cid[:-(len(rol) + 1)] if rol and cid.endswith(rol) else ""
            if not rec["tribunal_id"]:
                headerless += 1        # unusable: cannot say which court it belongs to
                continue
            if cid in causas:
                dupes += 1
            causas[cid] = rec
    return causas, dupes, gated, headerless, regated


def upload_c2_docs(causas, dry=False, upload=True):
    """Push the cuaderno-2 PDFs worker H fetched to Drive, and stamp `doc_url` on their rows.

    ⚠️ NO NEW ROW-BUILDER. `ingest_cdp.build` ALREADY emits a Documentos row for any historia row
    carrying `doc_url` — id `<causa>-c<n>-<folio>-<k>-doc`, keyed on the cuaderno row, not on the
    causa. All this has to do is put the URL there. Writing a second builder is precisely how book
    2's historia once came within an inch of being stamped `-c1-` over worker B's data.

    ⚠️ CONSULT THE DRIVE CACHE BEFORE READING ANY BYTES. Worker A's ingest once loaded the entire
    PDF corpus into memory on every hourly run only to discard it, because it read the files first
    and asked Drive second. At ~3.5 documents per causa this corpus is several times that one.

    ⚠️ NEVER PUBLISH A CHALLENGE PAGE AS A DOCUMENT. The bytes are re-checked for %PDF here even
    though the worker already checked: a file on disk is not the file the worker verified if
    anything else has since written to that name.

    Drive traffic goes to Google, not to the OJV, so it costs nothing against the WAF and is
    parallel. A causa whose documents are already in Drive is skipped without a read.
    """
    todo = [(cid, rec) for cid, rec in sorted(causas.items())
            if any(h.get("_doc_file") for h in (rec.get("historia_c2") or []))]
    if not todo:
        return
    n_files = sum(1 for _, r in todo for h in r["historia_c2"] if h.get("_doc_file"))
    print(f"  {n_files} cuaderno-2 pdf(s) on disk across {len(todo)} causa(s)")
    if dry or not upload:
        print("  (not uploading: --dry or --no-upload)")
        return
    store = dbstore.Store()
    cache = store._load_doc_cache()
    items, known, missing, notpdf = [], 0, 0, 0
    for cid, rec in todo:
        for k, h in enumerate(rec["historia_c2"]):
            fname = (h.get("_doc_file") or "").strip()
            if not fname:
                continue
            obj = f"{cid}/c2-{k:02d}.pdf"
            hit = cache.get(gstore._flatten_name(obj))
            if hit:
                h["doc_url"] = dbstore.direct_link(hit)
                known += 1
                continue
            f = PDFS / fname
            if not f.is_file():
                missing += 1
                continue
            body = f.read_bytes()
            if body[:4] != b"%PDF":
                print(f"  [warn] {f.name} is not a pdf — skipped")
                notpdf += 1
                continue
            items.append((obj, body))
    print(f"  {known} already in Drive; uploading {len(items)} new"
          + (f"; {missing} recorded but not on disk" if missing else "")
          + (f"; {notpdf} not a pdf" if notpdf else "") + "...")
    links = store.upload_pdfs_parallel(items) if items else {}
    for cid, rec in todo:
        for k, h in enumerate(rec["historia_c2"]):
            url = links.get(f"{cid}/c2-{k:02d}.pdf")
            if url:
                h["doc_url"] = url
    if items:
        print(f"  {len(links)} link(s) returned")


def main():
    ap = argparse.ArgumentParser(
        description="Ingest worker H's JSON records into Neon. Reuses worker A's row builders.")
    ap.add_argument("--file", default="", help="one file instead of every h-*.json")
    ap.add_argument("--dry", action="store_true", help="count and report, write nothing")
    ap.add_argument("--no-upload", dest="upload_pdfs", action="store_false",
                    help="skip pushing cuaderno-2 PDFs to Drive (leaves documentos untouched). "
                         "The Drive traffic never touches the OJV, so there is no scrape cost to "
                         "saving — this exists for a metadata-only re-ingest.")
    a = ap.parse_args()

    if a.file:
        paths = [Path(a.file) if Path(a.file).exists() else DATA / a.file]
    else:
        paths = sorted(p for p in DATA.glob("h-*.json") if "state" not in p.name)
    if not paths:
        raise SystemExit(f"no worker H records under {DATA}")
    print(f"{len(paths)} file(s) from {DATA}")

    causas, dupes, gated, headerless, regated = load(paths)
    print(f"  {len(causas)} distinct causas to ingest "
          f"({dupes} duplicate records collapsed, {gated} gate-rejected skipped, "
          f"{headerless} with no header)")
    with_c2 = sum(1 for r in causas.values() if r.get("historia_c2"))
    print(f"  of those, {with_c2} carry a cuaderno-2 historia")

    upload_c2_docs(causas, dry=a.dry, upload=a.upload_pdfs)

    merged, tribs, ids = {}, {}, []
    for cid, rec in sorted(causas.items()):
        parts = ingest_cdp.build(as_causa(rec), {})
        for tab, rows in parts.items():
            if tab == "Tribunales":
                for t in rows:
                    tribs[t["id"]] = t["tribunal"]
                continue
            merged.setdefault(tab, []).extend(rows)
        ids.append(cid)

    for tab in ORDER:
        print(f"  {tab:14} {len(merged.get(tab, [])):6} rows")
    print(f"  {'Tribunales':14} {len(tribs):6} (insert-if-absent only)")

    if a.dry:
        print("\n--dry: nothing written")
        return

    store = dbstore.Store()

    # ⚠️⚠️ CARRY FORWARD EVERY COLUMN WE DO NOT PRODUCE, NOT A HARDCODED THREE. `upsert` writes
    # every column from EXCLUDED, so any field this worker lacks becomes ''. `ingest_worker_a`
    # protects ebook/texto_demanda/certificado by name — but the table also holds `fill`,
    # `detalles` and `Gestion`, and worker H produces none of them either. Naming the columns you
    # remember is a list that rots; the rule "if the stored value is non-empty and mine is empty,
    # keep theirs" cannot rot.
    ids_present = [c for c in ids]
    with store.conn.cursor() as cur:
        cur.execute("select column_name from information_schema.columns "
                    "where table_name='causas'")
        cols = [r[0] for r in cur.fetchall()]
        q = ", ".join(f'"{c}"' for c in cols)
        cur.execute(f"SELECT {q} FROM causas WHERE causa_id = ANY(%s)", (ids_present,))
        prior = {}
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            prior[d["causa_id"]] = d
    kept = 0
    for row in merged.get("Causas", []):
        was = prior.get(row["causa_id"])
        if not was:
            continue
        for col, val in was.items():
            if col in ("causa_id", "updated_at"):
                continue
            if val not in (None, "") and not row.get(col):
                row[col] = val
                kept += 1
    if kept:
        print(f"  preserved {kept} existing value(s) across {len(prior)} causa(s) already in Neon")

    for tab in ORDER:
        rows = merged.get(tab, [])
        if rows:
            print(f"  upserted {tab:14} {store.upsert(tab, rows)}")

    # ⚠️ NEVER DOWNGRADE fill_status. worker A's ingest does a blanket
    # `SET fill_status='scraped'`, which would demote the causas worker B marked 'full' — and
    # 'full' is precisely what tells worker C to ask "what changed" instead of "what is missing".
    with store.conn.cursor() as cur:
        cur.execute("UPDATE causas SET fill_status='scraped' WHERE causa_id = ANY(%s) "
                    "AND coalesce(fill_status,'') NOT IN ('full','done','scraped')",
                    (ids_present,))
        print(f"  marked {cur.rowcount} causas fill_status='scraped' "
              f"(existing 'full'/'done' left alone)")
    # ⚠️ Tribunales is INSERT-IF-ABSENT, never upsert: worker H sweeps Corte=Todos and does not
    # know the corte, so an upsert would blank `tribunales.corte` for every court it touches.
    # That nearly happened to all 180 of them once already.
    if tribs:
        have = {r["id"] for r in store.read_tab("Tribunales")}
        # ⚠️ AND ONLY WITH A REAL NAME. Records written before worker H stored the tribunal name
        # yield an empty one, and inserting that creates a court row that reads as "we know this
        # court and it has no name" — worse than absent.
        fresh = [{"id": i, "tribunal": t, "corte": "", "corte_name": ""}
                 for i, t in tribs.items() if i not in have and t]
        if fresh:
            print(f"  inserted {'Tribunales':14} {store.upsert('Tribunales', fresh)} new")

    # ⚠️ ONLY THE ETAPA COLUMN. These causas have no harvest to store — we closed them at the
    # gate — so a full upsert would blank everything else they carry. One targeted UPDATE.
    if regated:
        with store.conn.cursor() as cur:
            for cid, et in regated.items():
                cur.execute("UPDATE causas SET etapa=%s WHERE causa_id=%s", (et, cid))
        print(f"  updated etapa on {len(regated)} gate-rejected causas "
              f"(they will not be re-opened next pass)")

    # Count it where it LANDED, which is the whole point of this file.
    with store.conn.cursor() as k:
        k.execute("""select count(distinct c.causa_id) from causas c join cuadernos q
                     on q.causa_id = c.causa_id where q.cuaderno ilike '2%%'""")
        n2 = k.fetchone()[0]
        k.execute("select count(*) from causas")
        tot = k.fetchone()[0]
        k.execute("""select count(*) from documentos d join cuadernos q on q.id = d.cuaderno_id
                     where q.id like '%%-c2-%%'""")
        nd = k.fetchone()[0]
    print(f"\nNEON NOW: {tot} causas, {n2} of them with a cuaderno-2 historia, "
          f"{nd} cuaderno-2 documents")


if __name__ == "__main__":
    main()
