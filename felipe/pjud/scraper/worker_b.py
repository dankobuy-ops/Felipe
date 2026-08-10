"""WORKER B — backfill the REMAINING documents for causas already in Neon. For the second PC.

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
import sys, time, argparse, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import psycopg2
import cdp_scrape as C
import dbstore
import gstore
import ojv
import run
from ojv import note
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
        sql.append(f"AND ({where})")          # operator-supplied; this is their own database
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


def store_result(store, causa_id, rec, ebook_url):
    """Write back ONE causa: the ebook link, plus whatever metadata the open gave us for free.

    ⚠️ A targeted UPDATE, never store.upsert(). upsert writes EVERY column from EXCLUDED, so it
    would blank texto_demanda, certificado, fill and anything else this worker has no opinion
    about. Worker B knows about the ebook and (for shells) the header — nothing else.
    """
    sets, vals = [], []
    if ebook_url:
        sets.append("ebook=%s")
        vals.append(ebook_url)
    h = rec.get("header") or {}
    if h:
        for col in ("f_ingreso", "estado_adm", "procedimiento", "ubicacion", "estado_proc", "etapa"):
            if h.get(col):
                v = h[col]
                if col == "f_ingreso":
                    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", v)
                    v = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else v
                sets.append(f'"{col}"=%s')
                vals.append(v)
    if not sets:
        return
    sets.append("updated_at=%s")
    vals.append(run._now())
    vals.append(causa_id)
    with store.conn.cursor() as cur:
        cur.execute(f"UPDATE causas SET {', '.join(sets)} WHERE causa_id=%s", vals)

    # Litigantes come free with the open and most of these causas are shells without any.
    lits, ruts = [], []
    for L in rec.get("litigantes") or []:
        rut = run.norm_rut(L.get("rut", ""))
        if not rut:
            continue
        if "JUR" in (L.get("persona", "") or "").upper():
            ruts.append({"rut": rut, "tipo": "empresa", "razon_social": L.get("nombre", ""),
                         "updated_at": run._now()})
        else:
            n, sg, ap, am = run.split_persona(L.get("nombre", ""))
            ruts.append({"rut": rut, "tipo": "persona", "nombre": n, "segundo_nombre": sg,
                         "ap_paterno": ap, "ap_materno": am, "updated_at": run._now()})
        lits.append({"id": f"{causa_id}-{rut}", "causa_id": causa_id, "rut": rut,
                     "participante": L.get("participante", ""), "updated_at": run._now()})
    if ruts:
        store.upsert("pjud_ruts", ruts)
        store.upsert("pjud_litigantes", lits)


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
    a = ap.parse_args()

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
                    time.sleep(gap)
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
                    time.sleep(A.CAUSA_GAP)
                    try:
                        rec = A.harvest_causa(ctx, p, tid, by_id[tid], c, want_ebook=True)
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
                    url = ""
                    eb = rec.get("ebook") or {}
                    if eb.get("bytes"):
                        f = PDFS / eb["file"]
                        body = f.read_bytes()
                        if body[:4] == b"%PDF":
                            url = dbstore.direct_link(
                                store.upload_pdf(f"{cid}/ebook.pdf", body))
                    store_result(store, cid, rec, url)
                    done += 1
                    note(f"      -> {cid} ebook={'yes' if url else 'NO'} "
                         f"(done {done}/{n}, failed {failed})")
                    time.sleep(A.POST_CAUSA)
                if consec_fail >= A.MODAL_FAIL_LIMIT:
                    break
                gap = A.SEARCH_GAP - (time.time() - last_search)   # pages share the budget
                if gap > 0:
                    time.sleep(gap)
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
