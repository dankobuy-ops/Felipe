"""WORKER B — FINISH a causa. Everything the site holds about it, in one open.

Worker A discovers causas and takes what an open makes free plus the ebook. B completes them:
EVERY document and EVERY georreferencia, not a fixed list of four. Worker C (not built) then only
keeps a finished causa current — new movements, new documents, new georef.

WHAT "EVERYTHING" MEANS, per causa (this is C.scrape_causa(full=True), which already did it):
    header, litigantes, escritos                    free once the modal is open
    texto demanda / certificado / ebook             3 header documents
    EVERY cuaderno, not just the first              switching costs one AJAX request each
      -> every historia row's `doc` AND `anexo`     the bulk of the work
      -> every row's georreferencia -> lat/lng      one sub-modal each
    receptor / notificaciones                       one modal

⚠️ THAT IS MANY REQUESTS PER CAUSA, not one. A causa with 3 cuadernos and 40 historia rows can
cost 40+ document fetches and as many geo lookups. On a runner, where a session is cut at roughly
70 requests-with-documents, expect to FINISH ONLY A HANDFUL of causas per session — which is
fine, because B works a SELECTION, and each open is spent entirely on something asked for.

WHY THIS RUNS ON RUNNERS (operator, 2026-08-13). Bulk sweeping belongs local: a residential
session does 730+ opens a day against a runner's ~70. But B's work is bounded by construction —
"here is a list of causas, finish them" — which fits a small session budget exactly, needs no
discovery, wastes nothing on empty courts, and never spends the residential IP that worker A
depends on.

(Original note: backfill the REMAINING documents for causas already in Neon.)

Worker A discovers causas by sweeping tribunales. Worker B does the opposite: it asks Neon which
causas are missing a document, and goes and gets exactly those. Nothing is discovered here, so it
never competes with A for the same work.

    python worker_b.py --port 9350 --desde 01/01/2026 --hasta 28/02/2026 --dry
    python worker_b.py --port 9350 --desde 01/01/2026 --hasta 28/02/2026

WHAT IT FETCHES (worker A takes only the ebook, deliberately):
    texto_demanda        header form, docu.php                  -> causas.texto_demanda
    certificado          header form, docCertificadoDemanda.php -> causas.certificado
    ingreso_demanda_c1   cuaderno-1 historia row                -> documentos
    mandamiento_c2       cuaderno-2 historia row                -> documentos  (--cuaderno2)

The work-list is causas that HAVE an ebook but are missing a header document — i.e. the ones
worker A already paid a causa open for. Four documents now cost ONE open instead of four, because
they are all reachable from the same modal.

⚠️ Cuaderno 2 is opt-in (`--cuaderno2`). Switching cuaderno fires a server request per causa,
which is a real cost against the binding constraint; the other three are free of that.

SELECTION IS STILL AVAILABLE. `--select fill` (default) honours the causas.fill checkbox,
`--select where "<sql>"` and `--select ids <file>` take a filter made anywhere else, and
`--select all` does every eligible causa. Always `--dry` first — it prints the work-list, the
tribunal spread and an ETA, and stops.

WHY IT IS SAFE TO RUN AT THE SAME TIME AS WORKER A
    Different PC, different IP. The WAF limit is a per-IP request RATE, so two machines are the
    one honest way to double throughput — two workers doing documents on ONE IP was measured
    blocking both within 1-2 minutes (2026-07-23).
    They also touch different rows: A works the recent window, B an older one. B writes with a
    targeted UPDATE of the document columns only — never an upsert, which would blank every
    column B does not know about.

WHAT IT COSTS
    One causa open per causa, exactly like A, because the ebook's JWT only exists inside the
    modal. There is no cheaper route. At the measured safe pacing that is ~2 min per causa, so
    size the job before starting it: `--dry` prints the work-list and stops.

THE FREE HALF
    Most Jan/Feb causas are SHELLS from a --list-only ingest: a rol and a date, no header, no
    litigantes. The open we are already paying for renders all of that, so B harvests it too and
    writes it back. Skipping it would mean paying the expensive part twice.
"""
import sys, time, argparse, re, random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import psycopg2
import cdp_scrape as C
import dbstore
import gstore
import ojv
import run
import ingest_cdp
from ojv import note
import live_view
import worker_a as A
from playwright.sync_api import sync_playwright

PDFS = Path(__file__).parent.parent / "data" / "worker_b" / "pdfs"
net = []


def work_list(desde, hasta, selector, where="", ids_file="", limit=0):
    """{tribunal_id: {rol: (causa_id, fill_status)}} — the causas THIS run should fetch.

    The point of worker B is that somebody decides which causas are worth a document. Fetching
    every Jan/Feb causa without an ebook would be 3,779 opens, about five days of continuous
    running, most of it on causas nobody asked for. So the work-list is a SELECTION:

        (every mode also requires: HAS an ebook, MISSING a header document — so a re-run never
         re-buys a document already stored, and causas worker A has not reached yet are skipped)

        fill    (default) causas.fill = true — the manual "I want this one" checkbox that
                already exists for exactly this purpose and is set from AppSheet
        where   an arbitrary SQL predicate, for a filter expressed in the query itself
        ids     an explicit causa_id per line, for a filter done anywhere else at all
        all     everything in the window without an ebook — the unfiltered sweep

    Every mode still excludes causas that already HAVE an ebook, so a re-run never re-buys one.

    Driven off the DATE columns the 2026-08-07 migration created: this query was impossible while
    f_ingreso was TEXT, because '15/07/2026' does not compare as a date.
    """
    d = f"{desde[6:]}-{desde[3:5]}-{desde[:2]}"
    h = f"{hasta[6:]}-{hasta[3:5]}-{hasta[:2]}"
    sql = ["SELECT tribunal_id, rol, causa_id, fill_status FROM causas "
           "WHERE f_ingreso >= %s::date AND f_ingreso <= %s::date "
           "AND ebook <> '' "
           "AND (COALESCE(texto_demanda,'')='' OR COALESCE(certificado,'')='') "
           "AND rol LIKE 'C-%%'"]
    args = [d, h]
    if selector == "fill":
        sql.append("AND fill = true")
    elif selector == "where":
        if not where:
            raise SystemExit("--select where needs --where '<sql predicate>'")
        # ⚠️ ESCAPE THE PERCENTS. This clause is interpolated into a query that psycopg2 then
        # parameter-substitutes, so every % in it is read as a placeholder marker. The example
        # HANDOFF_PC2 documents — ILIKE '%Obligaci%Dar%' — therefore died with
        # "IndexError: list index out of range" inside cur.execute, i.e. the documented usage had
        # never worked. Doubling them makes psycopg2 emit a literal %.
        sql.append(f"AND ({where.replace('%', '%%')})")   # operator-supplied; their own database
    elif selector == "ids":
        ids = [x.strip() for x in Path(ids_file).read_text(encoding="utf-8").splitlines()
               if x.strip() and not x.startswith("#")]
        if not ids:
            raise SystemExit(f"{ids_file} has no causa_ids")
        sql.append("AND causa_id = ANY(%s)")
        args.append(ids)
    sql.append("ORDER BY tribunal_id, rol")
    if limit:
        sql.append(f"LIMIT {int(limit)}")
    conn = psycopg2.connect(**dbstore._conn_kwargs())
    with conn.cursor() as cur:
        cur.execute(" ".join(sql), args)
        rows = cur.fetchall()
    conn.close()
    out = {}
    for tid, rol, cid, status in rows:
        out.setdefault(str(tid), {})[rol] = (cid, status or "")
    return out


def store_result(store, causa_id, rec, _unused=None):
    """Write EVERYTHING this causa gave up: documents, anexos, cuadernos, georref, receptor,
    litigantes — and the three header document URLs on the causa row itself.

    ⚠️ THE CHILD TABLES GO THROUGH ingest_cdp.build(), NOT a hand-rolled mapping. build() already
    produces the deterministic ids the rest of the data uses (cuaderno = <causa>-c<n>-<folio>-<k>,
    litigante = <causa>-<rut>), so re-running updates in place instead of duplicating. A second
    mapping here would drift from it, and the drift would look like missing data.

    ⚠️ THE CAUSA ROW IS STILL A TARGETED UPDATE, never store.upsert(). upsert writes EVERY column
    from EXCLUDED, so it would blank `fill`, `fill_status` and anything else B has no opinion
    about — the same trap that nearly wiped tribunales.corte for all 180 rows. B knows the header
    and the three document URLs; it says nothing about the rest.
    """
    parts = ingest_cdp.build({
        "rol": rec["rol"], "tribunalId": rec["tribunalId"],
        "tribunalSel": rec.get("tribunalSel", ""), "corte": "",
        "header": rec.get("header") or {}, "litigantes": rec.get("litigantes") or [],
        "cuadernos": rec.get("cuadernos") or [], "escritos": rec.get("escritos") or [],
        "receptor": rec.get("receptor") or [],
        "ebook": rec.get("ebook", ""), "scrape_level": "full",
    }, {})

    # Child tables: upsert is correct here — every row is fully specified by this harvest.
    for tab in ("Ruts", "Litigantes", "Cuadernos", "Escritos",
                "Documentos", "Anexos", "Notificaciones Receptor"):
        rows = parts.get(tab)
        if rows:
            store.upsert(tab, rows)

    # The causa row: only the columns B actually learned.
    sets, vals = [], []
    for col in ("ebook", "texto_demanda", "certificado"):
        if rec.get(col):
            sets.append(f'"{col}"=%s'); vals.append(rec[col])
    h = rec.get("header") or {}
    for col in ("f_ingreso", "estado_adm", "procedimiento", "ubicacion", "estado_proc", "etapa"):
        if h.get(col):
            v = h[col]
            if col == "f_ingreso":
                m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", v)
                v = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else v
            sets.append(f'"{col}"=%s'); vals.append(v)
    # 'full' is the whole point of worker B: it marks a causa as FINISHED, which is what lets
    # worker C later ask "what changed" instead of "what is missing".
    sets.append("fill_status=%s"); vals.append("full")
    sets.append("updated_at=%s"); vals.append(run._now())
    vals.append(causa_id)
    with store.conn.cursor() as cur:
        cur.execute(f"UPDATE causas SET {', '.join(sets)} WHERE causa_id=%s", vals)


def finish_causa(p, tid, tname, row):
    """Open ONE causa and take everything: all cuadernos, every doc and anexo, every georref,
    receptor. Returns the record C.scrape_causa produces, or None if the modal never opened.

    ⚠️ This deliberately delegates to C.scrape_causa(full=True) rather than reimplementing the
    harvest. That routine already walks every cuaderno, fetches each historia row's doc and anexo,
    resolves each geo sub-modal and reads the receptor — and a second implementation would drift
    from it exactly the way the duplicated block detectors drifted, silently and in the direction
    of collecting less.

    ⚠️ DOCS_INPAGE is forced ON. fetch_doc() dispatches on that module flag, and with it off it
    uses the OUT-OF-PROCESS downloader that fetches from outside the browser with copied cookies —
    the one thing in this codebase that looks nothing like a user. In-page fetching makes the same
    single request the click would have made, from the session that already holds it, and verifies
    %PDF before believing it.
    """
    C.DOCS, C.DOCS_INPAGE, C.GPS = True, True, True
    causa_id = f"{tid}-{row['rol']}"
    note(f"    open {causa_id}  {row['car'][:52]}")
    C.human_click(p, p.locator("#dtaTableDetalleFecha tbody tr").nth(row["i"])
                  .locator("a[onclick*='detalleCausaCivil']").first, timeout=8000)
    t0 = time.time()
    while time.time() - t0 < 90:
        p.wait_for_timeout(400)
        try:
            if p.evaluate("(rol)=>{const m=document.querySelector('#modalDetalleCivil');"
                          "return !!m && m.innerText.indexOf(rol)>=0;}", row["rol"]):
                break
        except Exception:
            pass
    else:
        note(f"    modal did not open after {time.time()-t0:.0f}s")
        return None
    p.wait_for_timeout(1500)
    C.human_scroll(p, notches=random.randint(2, 5))
    meta = {"rol": row["rol"], "tribunalId": tid, "tribunalSel": tname, "corte": "",
            "fecha": row.get("fecha", "")}
    # scrape_causa closes the modal itself, on every path.
    rec = C.scrape_causa(p, None, meta, full=True)
    C.clear_stuck_modal(p)
    note(f"      {rec.get('n_historia', 0)} historia rows | {rec.get('n_docs', 0)} documents "
         f"| {rec.get('n_geo', 0)} georref | {len(rec.get('receptor') or [])} receptor")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9350)
    ap.add_argument("--desde", default="01/01/2026")
    ap.add_argument("--hasta", default="28/02/2026")
    ap.add_argument("--select", choices=("fill", "where", "ids", "all"), default="fill",
                    help="which causas to fetch. fill (default) = causas.fill is true, the "
                         "manual checkbox set from AppSheet; where = your own SQL predicate; "
                         "ids = a file of causa_ids; all = everything missing an ebook.")
    ap.add_argument("--where", default="", help="SQL predicate for --select where")
    ap.add_argument("--ids-file", default="", help="causa_id per line, for --select ids")
    ap.add_argument("--dry", action="store_true", help="print the work-list and stop")
    ap.add_argument("--limit", type=int, default=0, help="cap the work-list (for a first probe)")
    ap.add_argument("--max-causas", type=int, default=0)
    ap.add_argument("--max-recover", type=int, default=6)
    # B paces itself off worker A's module constants, so without these it silently inherits A's
    # LOCAL defaults (20 s / 25 s) on a runner. That is the exact habit that had the remote sweep
    # running at half speed for days: a number measured in one environment is not measured in the
    # other. Measured remotely 2026-08-13: search 13 s, and causa 8 s ran 221 opens clean.
    # ASCII only in help strings - a non-ASCII character here crashes --help on Windows cp1252.
    ap.add_argument("--search-gap", type=float, default=0.0,
                    help="override SEARCH_GAP (every result request: searches AND page advances)")
    ap.add_argument("--causa-gap", type=float, default=0.0, help="override CAUSA_GAP")
    # ASCII only in help strings - a non-ASCII char here crashes --help on Windows cp1252.
    ap.add_argument("--live", action="store_true",
                    help="publish what this worker sees to Neon every few seconds so it can be "
                         "WATCHED while it runs: python watch_live.py. See live_view.py.")
    ap.add_argument("--live-every", type=float, default=6.0,
                    help="seconds between live frames (only sent when the picture changed)")
    ap.add_argument("--post-causa", type=float, default=0.0, help="override POST_CAUSA")
    a = ap.parse_args()

    if a.search_gap:
        A.SEARCH_GAP = a.search_gap
    if a.causa_gap:
        A.CAUSA_GAP = a.causa_gap
    if a.post_causa:
        A.POST_CAUSA = a.post_causa
    note(f"pacing: search {A.SEARCH_GAP}s  causa {A.CAUSA_GAP}s  post {A.POST_CAUSA}s")

    for label, val in (("--desde", a.desde), ("--hasta", a.hasta)):
        if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", val):
            raise SystemExit(f"{label}={val!r} is not dd/mm/yyyy — refusing to search with it")

    todo = work_list(a.desde, a.hasta, a.select, a.where, a.ids_file, a.limit)
    n = sum(len(v) for v in todo.values())
    sel = {"fill": "causas.fill = true", "where": f"where: {a.where}",
           "ids": f"ids from {a.ids_file}", "all": "ALL missing an ebook"}[a.select]
    note(f"work-list [{sel}]: {n} causa(s) across {len(todo)} tribunal(es), "
         f"{a.desde}..{a.hasta}")
    for tid, rols in list(todo.items())[:8]:
        note(f"    {tid:>5}  {len(rols)} causa(s)")
    if n:
        note(f"    ~{n * 2 / 60:.0f} h at the measured safe pacing (~2 min per causa open)")
    if a.dry or not n:
        return 0

    PDFS.mkdir(parents=True, exist_ok=True)
    A.PDFS = PDFS                       # reuse A's doc fetcher, but keep B's files separate
    store = dbstore.Store()
    done = failed = 0

    with sync_playwright() as pw:
        # Do not even try to attach if the machine is offline: every symptom downstream would
        # be misread as the site refusing us.
        if not ojv.internet_up():
            if not ojv.wait_for_internet()[0]:
                raise SystemExit("offline at startup — nothing to do")
        try:
            b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=60000)
        except Exception as e:
            raise SystemExit(f"CDP handshake failed on {a.port}: {str(e)[:80]}\n"
                             f"Restart Chrome on the SAME --user-data-dir and retry.")
        ctx = b.contexts[0]
        # Installed BEFORE the walk-in: entry is where a remote run has failed in the most
        # different ways, and it is over before the first log line that would say which.
        # It is set on A, not here: A owns the entry walk-in and the pacing constants this
        # worker borrows, and A.live() reads that global. The causa itself goes through
        # C.scrape_causa, so what a watcher sees here is the sweep and the waits, not A's
        # modal-wait ticks.
        if a.live:
            A.LIVE = live_view.Live("B", every=a.live_every)
            C.IDLE_HOOK = A.LIVE.tick
        p, S, tl = A.enter_and_setup(ctx, net, a.desde, a.hasta)
        if p is None:
            raise SystemExit("could not reach the form")
        by_id = {t["v"]: t["t"] for t in tl}

        recoveries = 0
        last_search = 0.0
        for tid in sorted(todo, key=lambda k: -len(todo[k])):
            want = todo[tid]
            if tid not in by_id:
                note(f"  [{tid}] not in the tribunal list — skipping {len(want)} causa(s)")
                continue
            if a.max_causas and done >= a.max_causas:
                note(f"  --max-causas {a.max_causas} reached — stopping cleanly")
                break
            if not C.select_tribunal_kbd(p, tid):
                note(f"  [{tid}] could not select — skip")
                continue
            ojv.click_away(p)
            if last_search:
                gap = A.SEARCH_GAP - (time.time() - last_search)
                if gap > 0:
                    C.human_idle(p, gap)
            net.clear()
            C.human_click(p, "#btnConConsultaFec")
            last_search = time.time()
            kind, el = ojv.wait_results(p, S, net)
            hit, why = ojv.blocked(p, net)
            if hit:
                note(f"  *** BLOCKED at tribunal {tid} — {why}")
                recoveries += 1
                if recoveries > a.max_recover:
                    note("  *** recovery budget spent — stopping"); break
                cool = A.COOL_OFF * recoveries
                note(f"  cooling off {cool:.0f}s, then re-entry")
                time.sleep(cool)
                p, S, tl = A.enter_and_setup(ctx, net, a.desde, a.hasta)
                if p is None:
                    note("  *** re-entry failed — stopping"); break
                last_search = 0.0
                continue
            if kind != "results":
                note(f"  [{tid}] {by_id[tid][:34]:36} {kind} after {el:.0f}s — "
                     f"{len(want)} causa(s) not reachable in this window")
                continue

            total = C.total_registros(p)
            note(f"  [{tid}] {by_id[tid][:34]:36} {total} registros, want {len(want)}")
            page, consec_fail = 1, 0
            while True:
                rows = C.page_rows(p)
                targets = [r for r in rows if r["has"] and r["rol"] in want]
                for c in targets:
                    cid, status = want[c["rol"]]
                    if a.max_causas and done >= a.max_causas:
                        break
                    C.human_idle(p, A.CAUSA_GAP)
                    try:
                        rec = finish_causa(p, tid, by_id[tid], c)
                    except Exception as e:
                        note(f"    [warn] harvest threw: {str(e)[:80]}")
                        rec = None
                    hit, why = ojv.blocked(p, net)
                    if hit:
                        note(f"  *** BLOCKED on detail ({c['rol']}) — {why}")
                        consec_fail = A.MODAL_FAIL_LIMIT
                        break
                    if rec is None:
                        C.clear_stuck_modal(p)
                        consec_fail += 1
                        failed += 1
                        if consec_fail >= A.MODAL_FAIL_LIMIT:
                            note(f"  *** {consec_fail} opens in a row failed with no rejection "
                                 f"page — that is the SILENT THROTTLE. Stopping this tribunal.")
                            break
                        continue
                    consec_fail = 0
                    store_result(store, cid, rec)
                    done += 1
                    note(f"      -> {cid} FINISHED: {rec.get('n_docs',0)} docs, "
                         f"{rec.get('n_geo',0)} georref (done {done}/{n}, failed {failed})")
                    C.human_idle(p, A.POST_CAUSA)
                if consec_fail >= A.MODAL_FAIL_LIMIT:
                    break
                gap = A.SEARCH_GAP - (time.time() - last_search)   # pages share the budget
                if gap > 0:
                    C.human_idle(p, gap)
                try:
                    why = A.advance(p, page)
                    last_search = time.time()
                except Exception as e:
                    note(f"    [warn] paginator threw: {str(e)[:80]}"); break
                if why != "more":
                    break
                page += 1

        note(f"DONE. {done} causa(s) backfilled, {failed} open(s) failed, "
             f"{n - done} still outstanding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
