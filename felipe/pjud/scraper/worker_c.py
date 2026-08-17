"""WORKER C — KEEP a finished causa CURRENT. Only what changed since we last looked.

The three workers divide the same expensive act — the causa OPEN — by how much of the causa they
intend to take:

    A  discovers        sweeps tribunales, takes what the modal makes free + the ebook
    B  finishes         every document, every georreferencia, every cuaderno, receptor
    C  refreshes        re-opens a FINISHED causa and takes ONLY what is new

⚠️ C IS NOT "B AGAIN". A finished causa costs 40+ document fetches to re-harvest, and a runner
session is small. Re-buying documents we already hold would spend an entire session learning
nothing — the single most expensive mistake available here. C therefore loads what Neon already
has for the causa (`cdp_scrape.KNOWN_DOCS` / `KNOWN_GEO` / `KNOWN_HEADER`) and the shared harvest
skips exactly those. A causa with nothing new costs ONE open and no document fetches at all.

⚠️ IT STILL DELEGATES TO C.scrape_causa(full=True). The temptation is to write a lean "just read
the historia" routine, and that is how the duplicated block detectors drifted — silently, in the
direction of collecting less. The skip lists are the only difference, and they live in the shared
harvest where both callers see them.

⚠️ SKIPPING WORK MUST NOT MEAN FORGETTING THE ANSWER. Every historia row is written back as a
Cuadernos row by an upsert, georref column included. A row whose geo lookup we skipped would go
back with georref='' and blank a coordinate we already own. KNOWN_GEO therefore carries the stored
value into the harvest rather than merely suppressing the lookup. Same trap as the upsert that
nearly wiped tribunales.corte for all 180 rows.

WHAT COUNTS AS "NEW"
    historia rows      a folio/tramite the stored Cuadernos rows do not have  -> its doc + anexo
    georreferencias    a row with a geo link and no stored coordinate
    escritos           a new filing
    header docs        only if a stored one is missing (normally none — B took them)

`updated_at` IS "WHEN WE LAST LOOKED", not "when it last changed". C moves it on every successful
visit, including a visit that found nothing, because that is what makes `ORDER BY updated_at` a
work queue instead of an infinite loop over the same stalest causa. What actually changed is in
the run's own output, and in the child rows' own timestamps.

    python worker_c.py --desde 01/07/2026 --hasta 31/07/2026 --dry
    python worker_c.py --port 9350 --desde 01/07/2026 --hasta 31/07/2026 --min-age-h 24
"""
import sys, time, argparse, re, random, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import psycopg2
import cdp_scrape as C
import dbstore
import ojv
import run
from ojv import note
import live_view
import worker_a as A
import worker_b as B
from playwright.sync_api import sync_playwright

PDFS = Path(__file__).parent.parent / "data" / "worker_c" / "pdfs"
net = []


def work_list(desde, hasta, where="", ids_file="", limit=0, min_age_h=24):
    """{tribunal_id: {rol: (causa_id, updated_at)}} — FINISHED causas, stalest first.

    Only `fill_status='full'` is eligible: C's whole premise is that B already took everything, so
    "what is missing" is a question C never has to ask. A causa that is not full belongs to B.

    --min-age-h is the guard against burning a session re-checking causas somebody looked at an
    hour ago. Court records do not move that fast, and the stalest-first ordering means the queue
    drains evenly instead of favouring whatever sorts first.
    """
    d = f"{desde[6:]}-{desde[3:5]}-{desde[:2]}"
    h = f"{hasta[6:]}-{hasta[3:5]}-{hasta[:2]}"
    sql = ["SELECT tribunal_id, rol, causa_id, updated_at FROM causas "
           "WHERE f_ingreso >= %s::date AND f_ingreso <= %s::date "
           "AND fill_status = 'full' "
           "AND rol LIKE 'C-%%'"]
    args = [d, h]
    if min_age_h:
        sql.append(f"AND (updated_at IS NULL OR updated_at < now() - interval '{int(min_age_h)} hours')")
    if where:
        # ⚠️ Escape the percents — this is interpolated into a query psycopg2 then parameter-
        # substitutes, so a bare % is read as a placeholder. Cost worker B a documented example
        # that had never once worked.
        sql.append(f"AND ({where.replace('%', '%%')})")
    if ids_file:
        ids = [x.strip() for x in Path(ids_file).read_text(encoding="utf-8").splitlines()
               if x.strip() and not x.startswith("#")]
        if not ids:
            raise SystemExit(f"{ids_file} has no causa_ids")
        sql.append("AND causa_id = ANY(%s)")
        args.append(ids)
    sql.append("ORDER BY updated_at NULLS FIRST, tribunal_id, rol")
    if limit:
        sql.append(f"LIMIT {int(limit)}")
    conn = psycopg2.connect(**dbstore._conn_kwargs())
    with conn.cursor() as cur:
        cur.execute(" ".join(sql), args)
        rows = cur.fetchall()
    conn.close()
    out = {}
    for tid, rol, cid, upd in rows:
        out.setdefault(str(tid), {})[rol] = (cid, upd)
    return out


def load_known(conn, causa_id):
    """What Neon already holds for this causa -> the three skip lists, plus the stored historia
    row ids so we can name what is new after the harvest.

    One round trip per causa, three small indexed reads. Cheap next to a single document fetch,
    and it is what turns a 40-request re-harvest into a 1-request check.
    """
    docs, geo, header, rows = set(), {}, set(), set()
    with conn.cursor() as cur:
        cur.execute('SELECT id FROM documentos WHERE cuaderno_id LIKE %s', (causa_id + "-c%",))
        docs |= {r[0] for r in cur.fetchall()}
        cur.execute('SELECT id FROM anexos WHERE cuaderno_id LIKE %s', (causa_id + "-c%",))
        docs |= {r[0] for r in cur.fetchall()}
        cur.execute('SELECT id, georref FROM cuadernos WHERE causa_id=%s', (causa_id,))
        for rid, g in cur.fetchall():
            rows.add(rid)
            if g:
                geo[rid] = g
        cur.execute('SELECT COALESCE(texto_demanda,\'\'), COALESCE(certificado,\'\'), '
                    'COALESCE(ebook,\'\') FROM causas WHERE causa_id=%s', (causa_id,))
        got = cur.fetchone() or ("", "", "")
        for key, val in zip(("texto_demanda", "certificado", "ebook"), got):
            if val:
                header.add(key)
    return docs, geo, header, rows


def refresh_causa(p, conn, tid, tname, row, causa_id):
    """Open ONE finished causa and take only what is new. Returns (rec, delta) or (None, None).

    `delta` is what actually changed — new historia rows, new documents, new georref, new escritos
    — because "C ran and wrote something" is not the same as "the causa moved", and a refresh
    worker that cannot tell you which is which is not worth its session budget.
    """
    docs, geo, header, known_rows = load_known(conn, causa_id)
    C.DOCS, C.DOCS_INPAGE, C.GPS = True, True, True
    C.KNOWN_DOCS, C.KNOWN_GEO, C.KNOWN_HEADER = docs, geo, header
    try:
        note(f"    open {causa_id}  {row['car'][:46]}  "
             f"(hold {len(known_rows)} rows, {len(docs)} docs, {len(geo)} geo)")
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
            return None, None
        p.wait_for_timeout(1500)
        C.human_scroll(p, notches=random.randint(2, 5))
        meta = {"rol": row["rol"], "tribunalId": tid, "tribunalSel": tname, "corte": "",
                "fecha": row.get("fecha", "")}
        rec = C.scrape_causa(p, None, meta, full=True)
        C.clear_stuck_modal(p)
    finally:
        # ⚠️ ALWAYS clear the skip lists. They are module state on a shared harvest; leaving one
        # set would make the NEXT causa silently skip documents belonging to a different causa.
        C.KNOWN_DOCS = C.KNOWN_GEO = C.KNOWN_HEADER = None

    seen_now, on_known = set(), 0
    for cu in rec.get("cuadernos") or []:
        cnum = run._cuaderno_num(cu.get("cuaderno", ""), 1)
        cnt = {}
        for hh in cu.get("historia") or []:
            folio = hh.get("folio", "")
            k = cnt.get(folio, 0) + 1
            cnt[folio] = k
            rid = f"{causa_id}-c{cnum}-{folio}-{k}"
            seen_now.add(rid)
            # ⚠️ THE DRIFT DETECTOR, and the only reason worker C can be trusted. A document
            # fetched for a row we ALREADY KNEW means one of two things: the court published it
            # since our last visit (real, and rare), or our row ids no longer match the ones in
            # Neon — in which case KNOWN_DOCS matches nothing, every skip list is empty, and C is
            # silently re-buying the entire causa while reporting success. The second failure is
            # invisible from outside: same rows written, same green tick, a whole session spent.
            # Minutes after worker B finished a causa, this number must be 0.
            if rid in known_rows and (hh.get("doc_url") or hh.get("anexo_url")):
                on_known += 1
    delta = {
        "rows": sorted(seen_now - known_rows),
        "docs": rec.get("n_docs", 0),          # KNOWN_DOCS was set, so these are NEW only
        "geo": rec.get("n_geo", 0),
        "escritos": len(rec.get("escritos") or []),
        "gone": sorted(known_rows - seen_now),
        "on_known": on_known,
    }
    return rec, delta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9350)
    ap.add_argument("--desde", default="01/07/2026")
    ap.add_argument("--hasta", default="31/07/2026")
    ap.add_argument("--where", default="", help="extra SQL predicate on causas")
    ap.add_argument("--ids-file", default="", help="causa_id per line")
    ap.add_argument("--min-age-h", type=int, default=24,
                    help="only causas not looked at for this many hours (0 = no guard)")
    ap.add_argument("--dry", action="store_true", help="print the work-list and stop")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-causas", type=int, default=0)
    ap.add_argument("--max-recover", type=int, default=6)
    # Same reason as worker B: without these, C inherits worker A's LOCAL defaults on a runner.
    # ASCII only in help strings.
    ap.add_argument("--search-gap", type=float, default=0.0, help="override SEARCH_GAP")
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

    todo = work_list(a.desde, a.hasta, a.where, a.ids_file, a.limit, a.min_age_h)
    n = sum(len(v) for v in todo.values())
    note(f"work-list [fill_status='full', idle >{a.min_age_h}h"
         f"{', ' + a.where if a.where else ''}]: {n} causa(s) across {len(todo)} tribunal(es), "
         f"{a.desde}..{a.hasta}")
    for tid, rols in list(todo.items())[:8]:
        note(f"    {tid:>5}  {len(rols)} causa(s)")
    if n:
        # A refresh that finds nothing costs one open, not one harvest — the whole point of C.
        note(f"    ~{n * 0.6 / 60:.1f} h if nothing changed (~35 s per open, no document fetches)")
    if a.dry or not n:
        return 0

    PDFS.mkdir(parents=True, exist_ok=True)
    A.PDFS = PDFS
    store = dbstore.Store()
    checked = moved = failed = refetched = new_rows = 0

    with sync_playwright() as pw:
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
            A.LIVE = live_view.Live("C", every=a.live_every)
            C.IDLE_HOOK = A.LIVE.tick
        p, S, tl = A.enter_and_setup(ctx, net, a.desde, a.hasta)
        if p is None:
            raise SystemExit("could not reach the form")
        by_id = {t["v"]: t["t"] for t in tl}

        recoveries, last_search = 0, 0.0
        for tid in sorted(todo, key=lambda k: -len(todo[k])):
            want = todo[tid]
            if tid not in by_id:
                note(f"  [{tid}] not in the tribunal list — skipping {len(want)} causa(s)")
                continue
            if a.max_causas and checked >= a.max_causas:
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

            note(f"  [{tid}] {by_id[tid][:34]:36} {C.total_registros(p)} registros, "
                 f"re-checking {len(want)}")
            page, consec_fail = 1, 0
            while True:
                rows = C.page_rows(p)
                targets = [r for r in rows if r["has"] and r["rol"] in want]
                for c in targets:
                    cid, _upd = want[c["rol"]]
                    if a.max_causas and checked >= a.max_causas:
                        break
                    C.human_idle(p, A.CAUSA_GAP)
                    try:
                        rec, delta = refresh_causa(p, store.conn, tid, by_id[tid], c, cid)
                    except Exception as e:
                        note(f"    [warn] refresh threw: {str(e)[:80]}")
                        rec, delta = None, None
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
                    # B's writer, deliberately: same deterministic ids, same targeted UPDATE that
                    # refuses to blank a column it has no opinion about. A second mapping here is
                    # exactly the drift this codebase keeps paying for.
                    B.store_result(store, cid, rec)
                    checked += 1
                    changed = delta["rows"] or delta["docs"] or delta["geo"]
                    new_rows += len(delta["rows"])
                    if changed:
                        moved += 1
                        note(f"      -> {cid} MOVED: +{len(delta['rows'])} historia row(s), "
                             f"+{delta['docs']} doc(s), +{delta['geo']} georref")
                        for rid in delta["rows"][:6]:
                            note(f"           new {rid}")
                    else:
                        note(f"      -> {cid} unchanged (1 open, 0 fetches)")
                    if delta["on_known"]:
                        refetched += delta["on_known"]
                        note(f"      [!!] {delta['on_known']} document(s) fetched for rows we "
                             f"ALREADY HELD — either the court just published them, or the row "
                             f"ids have drifted and C is re-buying the causa. See --stage after-c.")
                    if delta["gone"]:
                        # Not an error to fix silently: rows do not normally vanish, so this is
                        # either the site reorganising folios or our row-id scheme drifting.
                        note(f"      [!] {len(delta['gone'])} stored row(s) not on the page now — "
                             f"first: {delta['gone'][0]}")
                    C.human_idle(p, A.POST_CAUSA)
                if consec_fail >= A.MODAL_FAIL_LIMIT:
                    break
                gap = A.SEARCH_GAP - (time.time() - last_search)
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

        note(f"DONE. {checked} causa(s) re-checked, {moved} had changes, {failed} open(s) failed, "
             f"{n - checked} still outstanding.")
        # ⚠️ The run's verdict goes in a FILE, not only in stdout. A later step cannot read the
        # previous step's output, and deciding green/red on "the process exited 0" is how two
        # probe runs were reported as measurements when both had crashed in setup.
        (PDFS.parent / "last_run.json").write_text(json.dumps({
            "checked": checked, "moved": moved, "failed": failed,
            "new_rows": new_rows, "refetched_on_known_rows": refetched,
            "outstanding": n - checked, "at": run._now(),
        }, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
