"""WORKER A — census + ebook. The discovery worker.

One pass over every civil tribunal in the country (Corte = "Todos") for a date window. For each
tribunal it records the census, and for each BANK causa it finds it opens the causa once and takes
everything that open can give:

    free  (already in the DOM once the modal renders — costs no extra request)
          header, litigantes, escritos, cuaderno list, cuaderno-1 historia
    1 req the EBOOK pdf

Nothing else. Not the other four PDFs, not the receptor modal, not a cuaderno switch — those are
worker B's job, because each is an extra request against the scarce budget.

WHY THIS SHAPE
    Measured 2026-08-06: the search budget and the detail budget are separate, and detail is far
    scarcer. One session ran 19 searches with no search-block, then died on its third causa open.
    So the expensive, fragile act is OPENING A CAUSA — and if we are going to pay for it, we
    should walk away with everything that open makes free, plus the one document that matters
    most. That is the whole thesis this run is testing.

    It also means the modal is where we harvest, not where we shop. Every extra click inside an
    open causa is a separate withdrawal from the budget that is already the binding constraint.

NEVER touches #corteFec. It is the only control that fires a request on change, and walking it
with arrow keys fires one per step (ten in under a second to reach Concepción) — which produced
both the desynced tribunal lists and the blocks of 2026-08-05.

PAGINATION — new here, and it matters. The 2026-08-06 census read only page 1 of each result set,
so its 207 causas are a FLOOR: 33 tribunales reported totals over 100 and 103 reported over 50.
This worker walks the paginator to the end and flags any tribunal where it could not.

Usage
    python worker_a.py --port 9337                    # full national sweep
    python worker_a.py --port 9337 --start 42         # resume at tribunal index 42
    python worker_a.py --port 9337 --max-causas 12    # bounded probe of the detail budget
"""
import sys, json, time, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cdp_scrape as C
import ojv
from ojv import note
from settle import Settler
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
DATA = HERE.parent / "data" / "worker_a"          # gitignored: scraped data lives in Neon
PDFS = DATA / "pdfs"

# ── pacing ───────────────────────────────────────────────────────────────────
# Operator's standing rule 2026-08-06: "waiting more is the right choice. i'd rather wait a few
# seconds more, than to get blocked." Search spacing at 60 s is the one number with evidence
# behind it — it is what let a single profile run 208 searches in an evening. The detail numbers
# are deliberately far more generous than the 20 s that preceded three-to-ten-open deaths, and
# this run is the experiment that will tell us whether spacing was ever the variable.
SEARCH_GAP = 60.0      # from one search CLICK to the next
PAGE_GAP = 20.0        # between paginator clicks (same request class as a search)
CAUSA_GAP = 45.0       # between causa opens — the scarce resource
EBOOK_GAP = 8.0        # after the modal renders, before asking for the pdf
POST_CAUSA = 15.0      # after closing a causa, before anything else

CIVIL = "3"
net = []
pdf_hits = []


# ── pdf capture ──────────────────────────────────────────────────────────────

def attach_pdf_tap(ctx):
    """Capture document bodies at CONTEXT level — registered once, before any click.

    ⚠️ Do NOT do this per page. The document click opens a POPUP, and that popup's main-document
    response routinely lands before a per-page listener can be attached, so the capture silently
    saw nothing at all (an empty hit list, which reads exactly like "the click did nothing").
    A context-level listener is registered ahead of every popup that will ever exist, so there is
    no attach race. Reading the body here also means we never use APIRequestContext — the
    out-of-page fetch the handoff flags as the prime block suspect.
    """
    def h(r):
        u = r.url or ""
        if "/documentos/" not in u and "ebook" not in u.lower():
            return
        body, ct = None, ""
        try:
            body = r.body()
            ct = (r.headers or {}).get("content-type", "")
        except Exception:
            pass
        pdf_hits.append({"ep": u.split("/")[-1].split("?")[0], "status": r.status,
                         "n": len(body) if body else 0, "ct": ct, "body": body})
    ctx.on("response", h)


def classify(body):
    """'pdf' | 'apm' | 'other' — what did the document endpoint actually return?

    ⚠️ "It is over 1000 bytes" is NOT a document. That test is why three files sat on disk named
    *.pdf for a day while every one of them was really F5's <APM_DO_NOT_TOUCH> anti-bot
    interstitial: ~8-14 KB of obfuscated JavaScript, comfortably over any size threshold, with a
    perfectly ordinary 200 status. Check the magic bytes; nothing else is evidence.
    """
    if not body:
        return "other"
    if body[:4] == b"%PDF":
        return "pdf"
    head = body[:400].lstrip()
    if b"APM_DO_NOT_TOUCH" in head or b"TSPD" in body[:2000]:
        return "apm"
    return "other"


def close_doc_tabs(ctx):
    for q in list(ctx.pages):
        u = q.url or ""
        if "/documentos/" in u or "ebook" in u.lower():
            try:
                q.close()
            except Exception:
                pass


def ebook_control(p):
    """The Ebook control, identified by the ENDPOINT its form posts to — never by index.

    Header doc controls share an ancestor div and differ only by x-position, and Anexos has no
    form at all when unavailable, so positional selection silently grabs the wrong document.
    """
    idx = p.evaluate("""()=>{
      const forms=[...document.querySelectorAll('#modalDetalleCivil form')];
      for (let i=0;i<forms.length;i++){
        const act=(forms[i].getAttribute('action')||'').toLowerCase();
        if (act.indexOf('newebook')<0) continue;
        const a=forms[i].querySelector("a[onclick*='submit']")||forms[i].querySelector('a,button');
        if (!a) continue;
        const r=a.getBoundingClientRect();
        if (r.width>0 && r.height>0) return i;
      }
      return -1; }""")
    if idx < 0:
        return None
    return (p.locator("#modalDetalleCivil form").nth(idx)
            .locator("a[onclick*='submit'], a, button").first)


def grab_ebook(ctx, p, causa_id):
    """One click, one tab, one pdf. Returns a record — never raises."""
    loc = ebook_control(p)
    if loc is None:
        note("      ebook: no control on this causa")
        return {"bytes": 0, "missing": True}
    pdf_hits.clear()
    t0 = time.time()
    if not C.human_click(p, loc, timeout=8000):
        note("      ebook: click REFUSED (covered?)")
        return {"bytes": 0, "click_refused": True}
    # Wait for an ACTUAL pdf, not merely for something big. F5 answers the first document request
    # in a new browsing context with its JS challenge; if that challenge is going to clear, it
    # clears by the popup re-requesting, so keep listening past the interstitial.
    pdf = None
    for _ in range(75):                       # up to ~30 s
        p.wait_for_timeout(400)
        pdf = next((h for h in pdf_hits if classify(h["body"]) == "pdf"), None)
        if pdf:
            break
    el = round(time.time() - t0, 1)
    if pdf:
        fn = PDFS / f"{causa_id}__ebook.pdf"
        fn.write_bytes(pdf["body"])
        note(f"      ebook: {pdf['n']:,} B via {pdf['ep']} in {el}s -> {fn.name}")
        rec = {"bytes": pdf["n"], "endpoint": pdf["ep"], "file": fn.name, "secs": el}
    elif any(classify(h["body"]) == "apm" for h in pdf_hits):
        note(f"      ebook: F5 APM CHALLENGE on the document endpoint after {el}s "
             f"(no pdf served) — {[(h['ep'], h['n']) for h in pdf_hits]}")
        rec = {"bytes": 0, "apm_challenge": True, "secs": el}
    else:
        note(f"      ebook: no response captured after {el}s "
             f"{[(h['ep'], h['status'], h['n']) for h in pdf_hits]}")
        rec = {"bytes": 0, "failed": True, "secs": el}
    close_doc_tabs(ctx)
    p.wait_for_timeout(400)
    return rec


# ── one causa ────────────────────────────────────────────────────────────────

def harvest_causa(ctx, p, trib_id, trib_name, row, want_ebook=True):
    """Open the causa, take everything free, take the ebook, close. Returns the record or None
    if the modal never opened (which is NOT by itself a block — the caller checks that)."""
    causa_id = f"{trib_id}-{row['rol']}"
    note(f"    open {causa_id}  {row['car'][:52]}")
    C.human_click(p, p.locator("#dtaTableDetalleFecha tbody tr").nth(row["i"])
                  .locator("a[onclick*='detalleCausaCivil']").first, timeout=8000)
    t0 = time.time()
    opened = False
    while time.time() - t0 < 90:
        p.wait_for_timeout(400)
        try:
            if p.evaluate("(rol)=>{const m=document.querySelector('#modalDetalleCivil');"
                          "return !!m && m.innerText.indexOf(rol)>=0;}", row["rol"]):
                opened = True
                break
        except Exception:
            pass
    if not opened:
        note(f"    modal did not open after {time.time()-t0:.0f}s")
        return None
    p.wait_for_timeout(1500)                  # let the tabs inside the modal finish rendering

    # ---- free harvest: all of this is already in the DOM, none of it costs a request ----
    rec = {"causa_id": causa_id, "tribunal_id": trib_id, "tribunal": trib_name,
           "rol": row["rol"], "caratulado": row["car"], "fecha_ing": row.get("fecha", ""),
           "opened_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    for key, fn in (("header", C.parse_header), ("litigantes", C.parse_litigantes),
                    ("escritos", C.parse_escritos), ("historia_c1", C.parse_historia)):
        try:
            rec[key] = fn(p)
        except Exception as e:
            rec[key] = None
            note(f"      [warn] {key}: {str(e)[:60]}")
    try:
        rec["cuadernos"] = [c["txt"] for c in (C.cuaderno_options(p) or [])]
    except Exception:
        rec["cuadernos"] = []
    proc = (rec.get("header") or {}).get("procedimiento", "")
    note(f"      {len(rec.get('litigantes') or [])} litigantes · "
         f"{len(rec.get('historia_c1') or [])} historia c1 · "
         f"{len(rec['cuadernos'])} cuadernos · {proc[:40]}")

    if want_ebook:
        time.sleep(EBOOK_GAP)
        rec["ebook"] = grab_ebook(ctx, p, causa_id)
    else:
        rec["ebook"] = {"bytes": 0, "skipped": True}
    # worker B's queue: what we deliberately did NOT take while we were in here
    rec["docs_pending"] = ["texto_demanda", "certificado", "ingreso_demanda_c1"] + \
                          (["mandamiento_c2"] if len(rec["cuadernos"]) > 1 else []) + \
                          ([] if rec["ebook"].get("bytes") else ["ebook"])
    C.close_modal(p, "#modalDetalleCivil")
    p.wait_for_timeout(1500)
    C.clear_stuck_modal(p)
    return rec


# ── results harvesting, with pagination ──────────────────────────────────────

def page_banks(p, page_no):
    return [dict(r, page=page_no) for r in C.page_rows(p)
            if r["has"] and r["rol"].upper().startswith("C") and C.is_bank(r["car"])]


def advance(p, page):
    """'more' | 'done' | 'stuck' — walk the paginator one step.

    Detail is harvested PAGE BY PAGE, never after paginating to the end: a row's index is an
    index into the page it was read from, so clicking page-1 indices while the last page is on
    screen opens the WRONG causas. Harvest here, then advance.

    The end signal is the site's own greyed-out Siguiente, NOT "rows seen >= total". Counting
    rows is off by the blank filler row the table always carries, and an accumulated overcount
    stops the walk one page early — a silent truncation of exactly the biggest tribunales, which
    is the failure this pagination was added to fix in the first place. `next_page` also returns
    a REASON rather than a bool so a slow paginator AJAX cannot be mistaken for the last page;
    that confusion once turned 135 causas into 91.
    """
    if C.sig_disabled(p):
        return "done"
    time.sleep(PAGE_GAP)
    why = C.next_page(p)
    if why == "last":
        return "done"
    if why == "stuck":
        note(f"      [!] paginator stuck after page {page} — flagging tribunal INCOMPLETE")
        return "stuck"
    return "more"


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9337)
    ap.add_argument("--start", type=int, default=0, help="tribunal index to resume at")
    ap.add_argument("--desde", default="15/07/2026")
    ap.add_argument("--hasta", default="07/08/2026")
    ap.add_argument("--max-causas", type=int, default=0,
                    help="stop after N causa opens (0 = no limit). For probing the budget.")
    ap.add_argument("--no-detail", action="store_true", help="census only, open nothing")
    ap.add_argument("--no-ebook", action="store_true",
                    help="open causas and take the FREE metadata, but request no document. "
                         "Use while the F5 APM challenge on /documentos/ is unresolved — the "
                         "causa open is the scarce act and its metadata is worth having on its "
                         "own, so there is no reason to idle the profile waiting on that answer.")
    a = ap.parse_args()

    PDFS.mkdir(parents=True, exist_ok=True)
    STATE = DATA / "state.json"
    st = {"meta": {}, "tribunales": {}, "causas": {}}
    if STATE.exists() and STATE.stat().st_size:
        try:
            st = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception as e:
            # A crash mid-write leaves a truncated file. Refusing to start on it would block every
            # future resume, so keep the wreck for inspection and begin a fresh state.
            bad = STATE.with_suffix(f".bad.{int(time.time())}.json")
            STATE.rename(bad)
            note(f"[!] unreadable state ({str(e)[:50]}) — moved to {bad.name}, starting fresh")
    st["meta"].update({"desde": a.desde, "hasta": a.hasta, "port": a.port,
                       "last_run": time.strftime("%Y-%m-%d %H:%M:%S")})

    def save():
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    tally = {"searches": 0, "pages": 0, "opens": 0, "ebooks": 0, "bytes": 0, "apm": 0}

    def tally_line(tag):
        note(f"{tag}  searches={tally['searches']} extra_pages={tally['pages']} "
             f"causa_opens={tally['opens']} ebooks={tally['ebooks']} "
             f"apm_challenged={tally['apm']} pdf_bytes={tally['bytes']:,}")

    with sync_playwright() as pw:
        try:
            b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=60000)
        except Exception as e:
            # The wedge seen three times on 2026-08-06: the socket listens but the handshake
            # never completes, always after heavy document traffic. Restarting Chrome on the SAME
            # profile dir fixes it — cookies and TSPD_101_DID survive, nothing is burned.
            raise SystemExit(f"CDP handshake failed on {a.port}: {str(e)[:80]}\n"
                             f"Restart Chrome on the SAME --user-data-dir and retry.")
        ctx = b.contexts[0]
        close_doc_tabs(ctx)
        p = ojv.walk_in(ctx)
        if p is None:
            raise SystemExit("could not reach the form")
        note(f"in: {p.url[:60]}")
        p.on("response", ojv.make_tap(net))
        attach_pdf_tap(ctx)
        S = Settler(p)
        C.open_fecha_panel(p)

        # ---- form: Competencia is the ONLY cascade we trigger; corte stays on "Todos" ----
        if p.eval_on_selector("#fecCompetencia", "e=>e.value") != CIVIL:
            note("Competencia = Civil")
            C.select_by_kbd(p, "#fecCompetencia", CIVIL)
            ojv.click_away(p)
            S.wait(need="document.querySelectorAll('#fecTribunal option').length>50",
                   quiet_ms=1200, timeout=60, label="all-tribunales")
        corte = p.eval_on_selector("#corteFec", "e=>e.value")
        if corte not in ("", "0"):
            note(f"[!] corte={corte}, expected Todos — refusing to change it (that is the burst)")
            raise SystemExit(2)
        for sel, val in (("#fecDesde", a.desde), ("#fecHasta", a.hasta)):
            if p.eval_on_selector(sel, "e=>e.value") != val:
                C.type_date_kbd(p, sel, val)
                ojv.click_away(p)

        tl = p.eval_on_selector_all("#fecTribunal option",
                                    "e=>e.filter(o=>o.value&&o.value!=='0')"
                                    ".map(o=>({v:o.value,t:(o.textContent||'').trim()}))")
        note(f"tribunales={len(tl)} corte=Todos dates "
             f"{p.eval_on_selector('#fecDesde','e=>e.value')}.."
             f"{p.eval_on_selector('#fecHasta','e=>e.value')}")
        if len(tl) < 50:
            raise SystemExit("not the national list — aborting")

        last_search = 0.0
        for idx in range(a.start, len(tl)):
            tgt = tl[idx]
            done = st["tribunales"].get(tgt["v"])
            if done and done.get("complete") and not done.get("undercount"):
                # A tribunal is only finished when its census is complete AND every bank causa it
                # listed has a detail record. Otherwise re-search it and pick up the stragglers —
                # this is what makes a blocked run resumable without re-doing the whole country.
                missing = [c for c in done.get("causas", [])
                           if f"{tgt['v']}-{c['rol']}" not in st["causas"]]
                if a.no_detail or not missing:
                    continue
                note(f"  [{idx}] {tgt['v']} re-search: {len(missing)} causa(s) lack detail")
            if not C.select_tribunal_kbd(p, tgt["v"]):
                note(f"  [{idx}] {tgt['v']} could not select — skip")
                continue
            ojv.click_away(p)
            if last_search:
                gap = SEARCH_GAP - (time.time() - last_search)
                if gap > 0:
                    time.sleep(gap)

            net.clear()
            C.human_click(p, "#btnConConsultaFec")
            last_search = time.time()
            tally["searches"] += 1
            kind, el = ojv.wait_results(p, S, net)

            hit, why = ojv.blocked(p, net)
            if hit:
                note(f"  *** BLOCKED at idx {idx} ({tgt['v']} {tgt['t'][:28]}) {why}")
                note(f"  *** resume with --start {idx}")
                save()
                tally_line("TALLY at block:")
                return 3
            if kind in ("stale", "timeout"):
                note(f"  [{idx}/{len(tl)}] {tgt['v']:>5} {tgt['t'][:34]:36} {kind.upper()} "
                     f"after {el:.1f}s — never proved fresh, NOT recording")
                continue

            total = C.total_registros(p) if kind == "results" else None
            ent = {"idx": idx, "name": tgt["t"], "kind": kind, "elapsed": round(el, 1),
                   "total": total, "pages": 0, "rows_seen": 0, "complete": False,
                   "banks": 0, "causas": []}
            st["tribunales"][tgt["v"]] = ent
            if kind != "results" or total is None:
                ent["complete"] = True
                note(f"  [{idx}/{len(tl)}] {tgt['v']:>5} {tgt['t'][:34]:36} {kind:7} {el:5.1f}s "
                     f"total={total}")
                save()
                continue

            # ---- walk the result pages, harvesting detail from each BEFORE advancing ----
            page, seen, stuck = 1, 0, False
            while True:
                rows = C.page_rows(p)
                banks = [dict(r, page=page) for r in rows if r["has"]
                         and r["rol"].upper().startswith("C") and C.is_bank(r["car"])]
                seen += sum(1 for r in rows if r["rol"].strip())   # skip the blank filler row
                ent.update(pages=page, rows_seen=seen, banks=ent["banks"] + len(banks))
                ent["causas"] += [{"rol": c["rol"], "car": c["car"], "fecha": c["fecha"],
                                   "page": page} for c in banks]
                note(f"  [{idx}/{len(tl)}] {tgt['v']:>5} {tgt['t'][:34]:36} {kind:7} {el:5.1f}s "
                     f"total={total} page={page} rows={seen} banks+{len(banks)}")
                save()

                if not a.no_detail:
                    for c in banks:
                        if f"{tgt['v']}-{c['rol']}" in st["causas"]:
                            continue
                        if a.max_causas and tally["opens"] >= a.max_causas:
                            note(f"  --max-causas {a.max_causas} reached — stopping cleanly")
                            save()
                            tally_line("TALLY at cap:")
                            return 0
                        time.sleep(CAUSA_GAP)
                        tally["opens"] += 1
                        try:
                            rec = harvest_causa(ctx, p, tgt["v"], tgt["t"], c,
                                                want_ebook=not a.no_ebook)
                        except Exception as e:
                            note(f"    [warn] harvest threw: {str(e)[:90]}")
                            rec = None
                        hit, why = ojv.blocked(p, net)
                        if hit:
                            note(f"  *** BLOCKED on detail, idx {idx} causa {c['rol']} — {why}")
                            note(f"  *** resume with --start {idx}")
                            save()
                            tally_line("TALLY at block:")
                            return 3
                        if rec is None:
                            # Not a block (just checked). A stuck modal poisons every LATER open,
                            # so clear it — one hiccup used to look exactly like a burned profile
                            # for the whole rest of the run.
                            C.clear_stuck_modal(p)
                            continue
                        st["causas"][rec["causa_id"]] = rec
                        if rec["ebook"].get("bytes"):
                            tally["ebooks"] += 1
                            tally["bytes"] += rec["ebook"]["bytes"]
                        elif rec["ebook"].get("apm_challenge"):
                            tally["apm"] += 1
                        save()
                        tally_line("      running:")
                        time.sleep(POST_CAUSA)

                why = advance(p, page)
                if why != "more":
                    stuck = why == "stuck"
                    break
                page += 1
                tally["pages"] += 1

            ent["complete"] = not stuck
            ent["undercount"] = total is not None and seen < total
            save()
            if stuck or ent["undercount"]:
                note(f"    [!] {tgt['t'][:40]} INCOMPLETE — {seen}/{total} rows over {page} pages")

        res = [v for v in st["tribunales"].values() if v["kind"] == "results"]
        emp = [v for v in st["tribunales"].values() if v["kind"] == "empty"]
        note(f"DONE. tribunales={len(st['tribunales'])} withResults={len(res)} empty={len(emp)} "
             f"causas_found={sum(v['banks'] for v in st['tribunales'].values())}")
        inc = [v["name"] for v in st["tribunales"].values() if not v.get("complete", True)]
        if inc:
            note(f"  INCOMPLETE (paginator stuck): {inc}")
        tally_line("TALLY final:")
        return 0


if __name__ == "__main__":
    sys.exit(main())
