"""WORKER H — the mimic. A prototype that does what the operator did, at the rate they did it.

Built 2026-08-16 from a recorded 6.5-minute human session (`human_record.py`,
`data/human/session-20260816-212249.jsonl`, 15 causas). Everything here is a MEASUREMENT copied
from that file, not a guess about what looks human:

    what                       the operator        worker A            worker H
    open -> switch to book 2   2.0 s (median)      ~4 s                2.0 s
    open -> next open          13.1 s (4.6/min)    25 s (2.0/min)      13 s
    causaCivil.php             8.0 POST/min        ~4/min              ~8/min
    mousemove                  25.8 /s, 98% of s   0 between clicks    25.8 /s, always
    mouseover                  6.4 /s in the modal only on click paths  from the same motion
    keydown                    ZERO, all session   ~54 per tribunal    ZERO
    wheel inside the modal     ZERO                2-5 notches/causa   ZERO

⚠️ THE THREE THINGS THIS TESTS ARE NOT "POLITENESS". Every one of them makes us FASTER:
    * the pacing is halved, because the person we are imitating is twice as quick as our worker
    * the book-2 switch happens sooner, not later
    * the only thing ADDED is pointer motion, which costs nothing on the wire
This is the project's rule paying out again: ask what a person would not do, and the fix speeds
you up. The dwell-before-switching test I was about to run would have made us slower for nothing
— the recording shows a person switches books in two seconds.

⚠️ ZERO KEYSTROKES, and it contradicts our own code on purpose (operator, 2026-08-16).
`select_cuaderno`/`select_tribunal_kbd` drive selects with arrow keys to avoid `select_option`'s
synthetic change event. But the evidence for that rule is thinner than the code implies:
`HANDOFF_CDP.md` records "never select_option the TRIBUNAL" as *"Untested since the 07-22 fix — it
may well be innocent too"*, and in the same list records `select_option('#selCuaderno')` as
"TOLERATED — validated". Meanwhile the human emitted ZERO keydowns in a whole session and still
changed both selects, because a native dropdown pick is a real gesture the page sees as a trusted
change. Arrow keys are the thing WE invented. So: hover the select with a real pointer approach
(never click it — that opens Chrome's native popup, an OS surface we cannot drive) and then set
it. If that trips the WAF we will know on the first causa, which is the point of a prototype.

⚠️ Dates are picked with the MOUSE, from the jQuery UI datepicker the site actually ships
(`hasDatepicker`, `#ui-datepicker-div`) — verified live rather than assumed. `type_date_kbd`
types them, which is ~20 keystrokes we now know a person does not spend.

WHAT IT IS NOT: not an ingest path, not a replacement for worker A. It harvests the same
metadata with the same parsers and writes JSON; if the behaviour survives a runner, the behaviour
folds back into A and this file goes away.

    python worker_h.py --launch --tribunal 54 --desde 01/06/2026 --hasta 30/06/2026
    python worker_h.py --port 9400 --max-causas 12 --measure
"""
import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cdp_scrape as C
import human_motion
import human_record                 # reuse ITS counters -- a second copy is how detectors drift
import ojv
import run
import worker_a as A
from ojv import note
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE.parent / "data" / "worker_h"

# ⚠️⚠️ THE BEHAVIOUR LIVES IN human_engine, NOT HERE (2026-08-19). Everything about HOW this
# worker moves, types, waits and clicks was moved into one shared module so that no worker can
# ever again be the only one carrying a fidelity fix — which is exactly what had happened: worker
# H drove the datepicker with the mouse while A, B and C still deleted `readOnly` and typed into
# the field, on the form where the session token is minted.
#
#      SPECS    (human_engine.py)  how human it is.  ALWAYS THE BEST WE HAVE.
#      SETTINGS (this file)        what to collect, where, over what window, how fast.
#
# Imported by name rather than as `E.read(...)` so every call site below reads exactly as it did
# when it was measured — the diff that moved them is a pure move, and a smoke test proved it.
from human_engine import (READ_BOOK1, READ_BOOK2, READ_LIST, SELECT_FAIL_LIMIT, BAD_SEARCH_LIMIT,
                          MONTHS, jitter, read, close_modal_human, hover, set_select_mouse,
                          pick_date_mouse, build_form_mouse)
import human_engine as E


def page_row(page, row):
    """The locator for one result row — what the hand should be heading toward next."""
    return page.locator("#dtaTableDetalleFecha tbody tr").nth(row["i"])


def fill_targets(desde, hasta, limit=0, corte="", mode="cuaderno2"):
    """Causas we ALREADY hold that still owe us something. (todo, n) where todo is
    {tribunal_id: {rol: causa_id}}.

    Two modes, because "what is missing" is not one question:

      cuaderno2   causas with NO cuaderno-2 rows at all — the metadata backfill (the original)
      docs-c2     causas that HAVE a cuaderno 2 but no DOCUMENTO for any of its rows

    `corte` restricts the work-list to one Corte de Apelaciones by name (e.g. 'C.A. de Santiago').
    ⚠️ It matches `tribunales.corte` EXACTLY, and that column is populated from the site's own
    spelling — 25 tribunales carry an empty corte and would silently vanish from any filtered
    work-list. The caller prints the count it got; a count of zero means the name is wrong, not
    that the work is done.

    ⚠️ THE DATE WINDOW IS NOT OPTIONAL, even in fill. A fill run still finds its causa by SEARCHING
    the tribunal over a date range and clicking the row — so a causa whose f_ingreso falls outside
    [desde, hasta] can never be reached, however much it owes. And the OJV refuses a range longer
    than one month. Filling a corte that spans June to August is therefore three dispatches, not
    one; the launcher does exactly that.

    ⚠️ SWEEPING TO FILL IS MOSTLY RE-DISCOVERY. There are ~4,500 banked causas for June+July and
    13 of them have a second cuaderno, so the work is "open this known list", not "find causas".
    A sweep would spend most of its opens re-finding records we have had for weeks — and a causa
    open is the scarcest thing this project spends.

    The date column is `f_ingreso` (not `fecha_ing`, which does not exist — checked, not assumed).
    """
    import psycopg2
    import dbstore
    conn = psycopg2.connect(**dbstore._conn_kwargs())
    conn.autocommit = True
    # ⚠️ THE TWO MODES ASK OPPOSITE QUESTIONS OF THE SAME TABLE. cuaderno2 wants causas with NO
    # book-2 rows; docs-c2 wants causas WITH book-2 rows but no document behind them. Getting
    # these the wrong way round produces a work-list that is silently empty, or one that re-opens
    # everything — and both look like a healthy run.
    if mode == "docs-c2":
        want = """exists (select 1 from cuadernos q
                          where q.causa_id = c.causa_id and q.id like '%%-c2-%%')
                  and not exists (select 1 from documentos d join cuadernos q2
                                    on d.cuaderno_id = q2.id
                                  where q2.causa_id = c.causa_id and q2.id like '%%-c2-%%')"""
    else:
        want = """not exists (select 1 from cuadernos q
                              where q.causa_id = c.causa_id and q.cuaderno ilike '2%%')"""
    corte_join = "join tribunales t on t.id = c.tribunal_id" if corte else ""
    corte_where = "and t.corte = %s" if corte else ""
    sql = f"""select c.causa_id, c.rol, c.tribunal_id, c.etapa
              from causas c {corte_join}
              where c.f_ingreso between %s and %s
                and c.rol like 'C-%%'
                {corte_where}
                and {want}
              order by c.tribunal_id, c.rol"""
    params = [desde, hasta] + ([corte] if corte else [])
    todo, n = {}, 0
    with conn.cursor() as k:
        k.execute(sql, params)
        for causa_id, rol, tid, etapa in k.fetchall():
            # The header gate, applied from what we already know — an open we can skip entirely
            # is worth more than a fast one. Causas banked before the gate existed have no etapa
            # and are visited; the gate then fires on the header, as it does in a sweep.
            if run.etapa_rejected(etapa):
                continue
            todo.setdefault(str(tid), {})[rol] = causa_id
            n += 1
            if limit and n >= limit:
                break
    conn.close()
    return todo, n


def counters(page):
    """This worker's OWN telemetry, read with the instrument used on the human. Measuring
    ourselves with a different ruler is how you end up comparing two numbers that were never
    comparable — which is exactly the mistake that produced the burst theory."""
    try:
        return page.evaluate(human_record.READ)
    except Exception:
        return None


DOCS_C2 = False              # --docs-c2: fetch the PDF behind every cuaderno-2 historia row
DOC_READ = (1.4, 2.4)        # a person opens documents one at a time; this is the look at each
PDFS = OUT / "pdfs"


def fetch_row_docs(page, pres, causa_id, historia):
    """Fetch the PDF behind every row of the historia CURRENTLY ON SCREEN.

    Writes each file to data/worker_h/pdfs/ and stamps its historia row with `_doc_file`. The
    ingest uploads that file and sets `doc_url`, and ingest_cdp's EXISTING Documentos builder
    turns it into a row keyed `<causa>-c<n>-<folio>-<k>-doc`. ⚠️ No second row-builder here: that
    id is derived in exactly one place and a private copy of the derivation is how book 2's
    historia once came within an inch of being stamped `-c1-` over worker B's data.

    ⚠️ READ THE FORMS FROM THE DOM, NOT FROM THE PARSED HISTORIA. `parse_historia` captures the
    action and value but assumes the input is named `dtaDoc`, and the row documents are served by
    two different endpoints (docuN.php 60%, docuS.php 40%, measured over 23,286 banked rows). One
    evaluate costs nothing and gives the live truth including the real input name.

    ⚠️ STOP AT THE FIRST NETWORK-LEVEL REFUSAL. "TypeError: Failed to fetch" carries no rejection
    page and no challenge iframe, so `blocked()` sees nothing — on 2026-08-10 a worker went on
    buying causa opens whose every document was being denied. If one is refused, the rest of this
    causa's documents are being refused too; spending three more requests to confirm it is how a
    session gets spent proving something we already know.
    """
    out = {"n": 0, "bytes": 0, "refused": 0, "not_pdf": 0, "missing": 0, "rows": len(historia)}
    try:
        forms = page.evaluate(
            r"""()=>[...document.querySelectorAll('#historiaCiv table tbody tr')].map((tr,i)=>{
                  const td=tr.querySelectorAll('td');
                  const f=td[1] ? td[1].querySelector('form') : null;
                  if(!f) return {i:i, none:true};
                  const inp=f.querySelector("input[name='dtaDoc'], input");
                  return {i:i, action:f.getAttribute('action')||'',
                          param: inp ? (inp.name||'dtaDoc') : 'dtaDoc',
                          val: inp ? inp.value : ''};})""")
    except Exception as e:
        note(f"      [warn] could not read the book-2 document forms: {str(e)[:60]}")
        return out
    # ⚠️ IF THE TWO READINGS DISAGREE, DO NOT GUESS. The stamp back onto the historia is BY INDEX,
    # so a table that re-rendered between parse_historia and this read would attach every document
    # to the wrong trámite — silently, and in a column nobody re-checks. A mismatch is rare and
    # cheap to skip; a mis-filed document is permanent.
    if len(forms) != len(historia):
        note(f"      [warn] historia has {len(historia)} rows but the DOM shows {len(forms)} — "
             f"not fetching documents for this causa")
        return out
    PDFS.mkdir(parents=True, exist_ok=True)
    for k, f in enumerate(forms):
        if f.get("none") or not f.get("val"):
            out["missing"] += 1
            continue
        if out["n"] or out["not_pdf"]:
            read(pres, page, DOC_READ, "#modalDetalleCivil")   # the look between two documents
        d = C.fetch_doc_detail(page, f["action"], f["val"], f.get("param") or "dtaDoc")
        if d.get("refused"):
            out["refused"] += 1
            note(f"      [!] document {k + 1}/{len(forms)} REFUSED at the network layer "
                 f"({d.get('why', '')[:50]}) — abandoning this causa's documents")
            C.shot(page, f"doc-refused-{causa_id}", {"row": k, "detail": d.get("why", "")})
            break
        if d.get("bytes"):
            fn = PDFS / f"{causa_id}__c2-{k:02d}.pdf"
            fn.write_bytes(d["body"])
            historia[k]["_doc_file"] = fn.name
            historia[k]["_doc_bytes"] = d["bytes"]
            out["n"] += 1
            out["bytes"] += d["bytes"]
        elif d.get("not_pdf"):
            out["not_pdf"] += 1
            # An answer, not a failure — unless it is the anti-bot interstitial, which is one.
            note(f"      [warn] document {k + 1}: {d.get('status')} {d.get('ct')} "
                 f"{d.get('n')} B is not a pdf ({d.get('why')})")
            if d.get("why") == "apm":
                out["refused"] += 1
                note("      that was F5's APM interstitial — abandoning this causa's documents")
                break
        else:
            out["missing"] += 1
    note(f"      docs c2: {out['n']} pdf ({out['bytes'] / 1024:.0f} KB)"
         f"{f' · {out['refused']} REFUSED' if out['refused'] else ''}"
         f"{f' · {out['not_pdf']} not-pdf' if out['not_pdf'] else ''}"
         f"{f' · {out['missing']} without a form' if out['missing'] else ''}")
    return out


def harvest(page, pres, causa_id, row, trib_id="", trib_name="", only_proc="",
            net=None):
    """Open, take the metadata, switch books, close — at the human's cadence, moving throughout.

    ⚠️ NO WHEEL INSIDE THE MODAL (operator, 2026-08-16). Worker A scrolls 2-5 notches after every
    open on the reasoning that "nobody reads it static". The recording says otherwise: the person
    wheeled 0.0/s while a modal was open and 0.6/s on the results list. They read by MOVING THE
    POINTER, not by scrolling. So the reading is pointer presence, and the wheel stays outside.
    """
    # ⚠️ tribunal_id AND tribunal BELONG IN THE RECORD. They were left out because causa_id is
    # "<tid>-<rol>" and the id is therefore recoverable — but the ingest builder reads
    # rec["tribunal_id"] directly and died on a KeyError over 1,154 records already on disk, and
    # the tribunal NAME was not recoverable at all. A record should carry what its consumer needs,
    # not what a later script could reconstruct.
    rec = {"causa_id": causa_id, "tribunal_id": trib_id, "tribunal": trib_name,
           "rol": row["rol"], "caratulado": row["car"],
           "fecha_ing": row.get("fecha", ""), "opened_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    note(f"    open {causa_id}  {row['car'][:52]}")
    # ⚠️ DID OUR CLICK PRODUCE A REQUEST? That is the one question the modal probe cannot answer
    # from the DOM, and it separates the two remaining explanations: either the click never
    # reached the magnifier (a stale row index after a table redraw, say) and NO causaCivil.php
    # was ever asked for, or the click landed and the site did not answer. We already tap every
    # response; all this needs is a mark before the click.
    n0 = len(net) if net is not None else 0
    # ⚠️ VERIFY THE ROW BEFORE CLICKING IT. We click `.nth(i)` from a list read earlier, and the
    # handbook's oldest pagination warning is that "a row index belongs to the page it was read
    # from". If the table redrew between the read and the click, index i is a DIFFERENT causa —
    # and a click on a row whose handler has been rebound produces no request at all, which is
    # indistinguishable from the site ignoring us. Measured: `[net] 0 responses` with the click
    # NOT refused. One cheap comparison rules it in or out.
    try:
        at_i = page.evaluate(
            "(i)=>{const tr=document.querySelectorAll('#dtaTableDetalleFecha tbody tr')[i];"
            " if(!tr) return null; const td=tr.querySelectorAll('td');"
            " return td[1] ? td[1].innerText.trim() : null;}", row["i"])
    except Exception:
        at_i = None
    if at_i is not None and at_i != row["rol"]:
        note(f"    [!] row {row['i']} now holds {at_i!r}, not {row['rol']!r} — the table redrew; "
             f"re-reading instead of clicking the wrong causa")
        return "stale-row"
    t_open = time.time()
    # ⚠️⚠️ CHECK THE CLICK. This return value was ignored, and that single omission produced the
    # failure this project has chased longest. human_click REFUSES an unreachable target on
    # purpose — a covered click correlated with getting blocked (0 covered -> 50 causas, 1 ->
    # blocked at 23, 2 -> at 4, measured 07-22) — and it says so plainly: "objetivo tapado tras
    # 8s — NO hago clic". We then waited 90-106 s for a modal nobody had requested, reported
    # "modal did not open", and blamed the site. The network tap settles it: `0 responses since
    # the click, causaCivil.php=0`. THE SITE WAS NEVER ASKED.
    # A refused click costs one causa. It is not a spent session, it is not a block, and it must
    # never again spend a recovery.
    if not C.human_click(page, page.locator("#dtaTableDetalleFecha tbody tr").nth(row["i"])
                         .locator("a[onclick*='detalleCausaCivil']").first, timeout=8000):
        # ⚠️ AND SAY WHERE THE ROW WAS. A refusal is now cheap, but 10% of rows refusing is a
        # tenth of the backlog we would never fill — and "unreachable" is another label, not an
        # observation. human_click already reports "objetivo tapado" with no overlay found, which
        # means the row is not where we can click it; the only way to know why is to ask for its
        # geometry against the viewport at the moment we gave up.
        try:
            geo = page.evaluate(
                "(i)=>{const tr=document.querySelectorAll('#dtaTableDetalleFecha tbody tr')[i];"
                " if(!tr) return {noRow:true, rows:document.querySelectorAll("
                "   '#dtaTableDetalleFecha tbody tr').length};"
                " const a=tr.querySelector(\"a[onclick*='detalleCausaCivil']\");"
                " const r=(a||tr).getBoundingClientRect();"
                " const top=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);"
                " return {hasLink:!!a, x:Math.round(r.left), y:Math.round(r.top),"
                "  w:Math.round(r.width), h:Math.round(r.height),"
                "  vw:innerWidth, vh:innerHeight, scrollY:Math.round(scrollY),"
                "  inView: r.top>=0 && r.bottom<=innerHeight,"
                "  topEl: top ? top.tagName+'.'+(top.className||'').toString().slice(0,26) : null};}",
                row["i"])
        except Exception as e:
            geo = f"(probe failed: {str(e)[:40]})"
        note(f"    click on row {row['i']} was REFUSED (unreachable) — skipping this causa")
        note(f"      [geo] {geo}")
        return "click-refused"

    # The two seconds a causa takes to load are spent MOVING, like a person waiting for it.
    pres.aim(page, "#dtaTableDetalleFecha")     # where the hand is while the causa loads
    got = pres.run(90.0, poll=lambda: page.evaluate(
        "(rol)=>{const m=document.querySelector('#modalDetalleCivil');"
        "return !!m && m.innerText.indexOf(rol)>=0;}", row["rol"]), poll_every=0.35)
    if not got:
        # ⚠️ ASK THE PAGE WHY, BEFORE RECOVERING. This is the failure that has ended more sessions
        # today than every other cause combined, and all we have ever written down is that it
        # happened. `blocked=(False,'')` already tells us there is no rejection page; what we have
        # never established is whether OUR CLICK went anywhere, whether the site answered, or
        # whether a modal exists but never became visible. Each has a different fix and we have
        # been choosing between them by intuition.
        try:
            d = page.evaluate(
                "(rol)=>{const m=document.querySelector('#modalDetalleCivil');"
                " const rows=document.querySelectorAll('#dtaTableDetalleFecha tbody tr');"
                " const links=document.querySelectorAll("
                "   \"#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']\");"
                " return {modal: !!m,"
                "  modalShown: !!m && !!(m.offsetWidth||m.offsetHeight||m.getClientRects().length),"
                "  modalHasRol: !!m && (m.innerText||'').indexOf(rol) >= 0,"
                "  modalClass: m ? (m.className||'').slice(0,40) : null,"
                "  rows: rows.length, links: links.length,"
                "  spinners: [...document.querySelectorAll('[id^=loadPre]')]"
                "    .filter(e=>e.innerHTML.trim()).map(e=>e.id),"
                "  sheets: document.querySelectorAll('.jquery-loading-modal,.modal-backdrop').length,"
                "  bodyLen: (document.body.innerText||'').length};}", row["rol"])
        except Exception as e:
            d = f"(probe failed: {str(e)[:40]})"
        seen = [r["u"] for r in (net[n0:] if net is not None else [])]
        causa_posts = sum(1 for u in seen if "causaCivil" in u)
        note(f"    modal did not open after {time.time()-t_open:.0f}s")
        note(f"      [why] busy={C.page_busy(page)} {d}")
        note(f"      [net] {len(seen)} responses since the click, "
             f"causaCivil.php={causa_posts} :: {seen[:8]}")
        C.shot(page, f"modal-never-opened-{row['rol']}",
               {"dom": d, "responses": seen[:8], "causa_posts": causa_posts})
        # ⚠️ COST IT WHERE IT BELONGS. If our click produced NO causa request, the site was never
        # asked and there is nothing wrong with the session — spending a 3-9 minute recovery on it
        # is the same error as spending one on a refused click, which cost us an entire fleet
        # earlier today. Only a modal that failed AFTER we actually asked for it is evidence the
        # session is unwell.
        if causa_posts == 0:
            note("      our click produced no causa request — one causa lost, session untouched")
            return "click-refused"
        return None

    # ⚠️ THE HAND FOLLOWS THE READING. Without this the pointer keeps wandering wherever it
    # happened to be -- the operator watched the first version move only over the left-hand menu
    # while the modal it was supposedly reading sat untouched. Motion with no destination
    # produces no `mouseover`, which is the entire channel this is here to fill.
    pres.aim(page, "#modalDetalleCivil")
    try:
        rec["header"] = C.parse_header(page)
    except Exception as e:
        rec["header"] = None
        note(f"      [warn] header: {str(e)[:60]}")
    etapa = (rec.get("header") or {}).get("etapa", "")
    if run.etapa_rejected(etapa):
        rec["skipped_etapa"] = etapa
        note(f"      etapa {etapa[:44]!r} is not wanted — closing without opening its books")
        read(pres, page, (0.8, 1.5), "#modalDetalleCivil")   # long enough to have read the etapa
        close_modal_human(page, pres)
        return rec

    for key, fn in (("litigantes", C.parse_litigantes),
                    ("escritos", C.parse_escritos), ("historia_c1", C.parse_historia)):
        try:
            rec[key] = fn(page)
        except Exception:
            rec[key] = None
    try:
        rec["cuadernos"] = [c["txt"] for c in (C.cuaderno_options(page) or [])]
    except Exception:
        rec["cuadernos"] = []
    proc = (rec.get("header") or {}).get("procedimiento", "")
    if only_proc and not re.search(only_proc, C.norm(proc), re.I):
        rec["skipped_proc"] = True
        note(f"      procedimiento {proc[:40]!r} does not match — not stored")
        close_modal_human(page, pres)
        return rec

    # ── the act under test: book 2, at the human's two seconds, with zero keystrokes ──
    rec["historia_c2"], rec["cuaderno_c2"] = None, ""
    if len(rec["cuadernos"]) > 1:
        read(pres, page, READ_BOOK1, "#modalDetalleCivil")   # a person looks at book 1 first
        pres.travel_to(page, "#selCuaderno")
        # A signature of book 1's historia, so we can tell when book 2 has actually arrived.
        before = page.evaluate("()=>{const t=document.querySelector('#historiaCiv table tbody');"
                               " return t ? t.rows.length + '|' + (t.innerText||'').slice(0,120)"
                               "          : '';}")
        n_opts = page.eval_on_selector("#selCuaderno", "e=>e.options.length")
        if n_opts > 1 and set_select_mouse(page, "#selCuaderno", index=1):
            # ⚠️ WAITING FOR THE SITE IS NOT PADDING, and I deleted it as if it were. Stripping
            # every fixed wait (correctly) also removed the pause after the cuaderno switch —
            # so the historia was parsed before the AJAX had re-rendered it, and causas with two
            # books were banked with "0 hist c2" while the switch itself had succeeded. Silent
            # data loss, from an over-applied rule.
            # The distinction: a wait that exists to hit an INTERVAL is padding; a wait for the
            # site to answer is the work. And it should be a CONDITION, never a duration —
            # here, "the historia is no longer the one book 1 showed".
            pres.run(6.0, poll=lambda: page.evaluate(
                "(b)=>{const t=document.querySelector('#historiaCiv table tbody');"
                " if(!t) return false;"
                " return (t.rows.length + '|' + (t.innerText||'').slice(0,120)) !== b;}", before),
                poll_every=0.25)
            try:
                rec["historia_c2"] = C.parse_historia(page)
                rec["cuaderno_c2"] = rec["cuadernos"][1]
                rec["header_c2"] = C.parse_header(page)
            except Exception as e:
                note(f"      [warn] historia_c2: {str(e)[:60]}")
        else:
            note("      [warn] could not switch to cuaderno 2")

        # ── the documents of book 2, while book 2 is the one on screen ──
        # ⚠️ THIS IS THE ONLY MOMENT THEY CAN BE TAKEN. Each row's form carries a fresh HS256 JWT
        # with `iat`/`exp` ONE HOUR APART (decoded from banked records, 2026-08-19), minted when
        # the modal renders. So a document URL cannot be banked and fetched later, and it cannot
        # be fetched while book 1 is displayed — the historia in the DOM is book 1's. Every
        # document costs the causa open it is attached to, which is why this rides along with the
        # book-2 switch instead of being its own worker.
        if DOCS_C2 and rec.get("historia_c2"):
            rec["docs_c2"] = fetch_row_docs(page, pres, causa_id, rec["historia_c2"])

    note(f"      {len(rec.get('litigantes') or [])} litigantes · "
         f"{len(rec.get('historia_c1') or [])} hist c1 · "
         f"{len(rec.get('historia_c2') or [])} hist c2 · "
         f"{len(rec['cuadernos'])} cuadernos · {proc[:34]}")
    read(pres, page, READ_BOOK2, "#modalDetalleCivil")
    close_modal_human(page, pres)
    rec["open_seconds"] = round(time.time() - t_open, 1)
    return rec


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="Prototype worker that reproduces a recorded human session: continuous "
                    "pointer presence, zero keystrokes, no wheel inside the modal, and the "
                    "human's cadence (which is twice our worker's speed).")
    ap.add_argument("--port", type=int, default=9400)
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--profile", default="")
    ap.add_argument("--tribunal", default="",
                    help="tribunal VALUE to sweep (default: the first with results)")
    ap.add_argument("--desde", default="01/06/2026")
    ap.add_argument("--hasta", default="30/06/2026")
    ap.add_argument("--probe-picker", action="store_true",
                    help="click a date field once and log what the widget did, so the next attempt to drive it is aimed. Non-fatal.")
    ap.add_argument("--use-form-dates", action="store_true",
                    help="do not touch the dates -- sweep whatever window the form already "
                         "shows. The point of this prototype is the CAUSA LOOP, and leaving a "
                         "readonly field alone is zero keystrokes by definition.")
    ap.add_argument("--fill", action="store_true",
                    help="TARGETED MODE: open the causas already banked for this window that "
                         "still have no cuaderno-2 rows, instead of sweeping to re-find them. "
                         "~4,500 of June+July are in that state and 13 are not. Paginates, "
                         "because a wanted rol can sit past row 100.")
    ap.add_argument("--docs-c2", action="store_true",
                    help="with --fill: fetch the PDF behind EVERY cuaderno-2 historia row, and "
                         "select causas that have a cuaderno 2 but no document for it. "
                         "⚠️ 3.5 documents per causa (measured over 23,286 banked rows), so this "
                         "is ~2.7x the requests per open that a metadata fill makes. It also "
                         "hits docuN.php/docuS.php, the endpoint worker A was redefined in "
                         "August to stay clear of. Hold the AGGREGATE rate, not the worker count "
                         "— see --speed and HANDOFF_WORKERS.md section 0.")
    ap.add_argument("--corte", default="",
                    help="with --fill: only causas whose tribunal belongs to this Corte de "
                         "Apelaciones, spelled as the site spells it (e.g. 'C.A. de Santiago'). "
                         "An exact match on tribunales.corte; a wrong name yields an EMPTY "
                         "work-list, which is reported rather than run as if finished.")
    ap.add_argument("--shard", type=int, default=1,
                    help="which slice of the work this worker takes (1-based), used with --of")
    ap.add_argument("--of", type=int, default=1,
                    help="how many workers are sharing the work. In --fill the COURT LIST is "
                         "sliced round-robin, because which courts still owe a cuaderno 2 changes "
                         "after every ingest and --start/--end index the national list instead.")
    ap.add_argument("--max-pages", type=int, default=6,
                    help="pagination cap per court in --fill (a page advance is a result "
                         "request and draws on the same budget as a search)")
    ap.add_argument("--start", type=int, default=0, help="first tribunal index to sweep")
    ap.add_argument("--end", type=int, default=None, help="last tribunal index (inclusive)")
    ap.add_argument("--max-minutes", type=float, default=0.0,
                    help="stop cleanly after this many minutes. A long run is how we learn "
                         "whether this behaviour blocks at all -- 21 opens in one court proves "
                         "nothing when the remote wall is at 10 and worker A does 375 locally.")
    ap.add_argument("--max-causas", type=int, default=0,
                    help="stop after N causa opens (0 = no limit)")
    ap.add_argument("--only-proc", default="")
    ap.add_argument("--gate-release", choices=("entry", "form", "search"), default="form",
                    help="WHEN the arrival gate is handed to the next worker. Measured 2026-08-17, "
                         "median of six: walk-in 100s, form build 28s, first search 30s = ~145s "
                         "held. 'search' is the original rule and the slowest. 'form' releases "
                         "once 230 tribunales are loaded -- proof the session works, without "
                         "making the queue wait for a search. 'entry' releases the moment we are "
                         "on the form. The gate exists to space ARRIVALS, and neither building a "
                         "form nor running a search is an arrival -- a reading only defensible "
                         "since the aggregate-RATE finding replaced the concurrency one.")
    ap.add_argument("--max-recover", type=int, default=3,
                    help="how many times a wedged form or a spent session may be cleared by "
                         "re-entering before giving up. Worker A has had this since 08-07; worker "
                         "H shipped without it and one worker spent its whole hour skipping 38 "
                         "courts with a dead session.")
    ap.add_argument("--shots", default="",
                    help="directory for failure screenshots + page state. A runner has no screen: "
                         "capture what it was actually looking at when a click was refused, a "
                         "modal never opened, or entry was blocked, and upload it as an artifact.")
    ap.add_argument("--window", default="1440x900",
                    help="browser window size, WxH. The correctness fix is horizontal scrolling "
                         "(human_scroll_x), not size -- a 744x345 window reaches an off-screen "
                         "target once we scroll across, verified. So this is a PREFERENCE: small "
                         "tiled windows stay watchable. Use 760x440 to reproduce the geometry "
                         "that refused 3.5%% of rows and truncated 39%% of courts.")
    ap.add_argument("--gate", choices=("file", "db", "none"), default="file",
                    help="serialise ARRIVALS so concurrent workers never open fresh browsers in "
                         "the same instant. 'file' for workers on ONE machine; 'db' for cloud "
                         "runners, which have no shared filesystem and so cannot use a lock file. "
                         "Released at --gate-release, never on merely reaching the form.")
    ap.add_argument("--no-search-presence", action="store_true",
                    help="leave the pointer FROZEN during searches, as every worker before this "
                         "one did. The control arm for the search-presence fix, and the escape "
                         "hatch if pointer motion ever stops searches settling (wait_results "
                         "needs 10 s of DOM silence to classify one).")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="multiplier on the READING times. 1.0 = exactly the operator's measured "
                         "pace; 0 = top speed, where the only waits left are the site answering "
                         "and the pointer travelling. Set it directly for a controlled arm -- "
                         "ramping INTO a level and holding one are different experiments.")
    ap.add_argument("--ramp-every", type=int, default=0,
                    help="SPEED TEST: after every N causa opens, cut the reading times by "
                         "--ramp-step. Ramps ONE variable -- the acts, their order, the pointer "
                         "rate and the zero keystrokes all stay as measured -- so a trip is "
                         "attributable to pace and nothing else.")
    ap.add_argument("--ramp-step", type=float, default=0.75,
                    help="multiplier applied to the reading spans at each rung (default 0.75)")
    ap.add_argument("--rate", type=float, default=26.0,
                    help="pointer events per second (the human measured 25.8)")
    ap.add_argument("--measure", action="store_true",
                    help="print our own input telemetry beside the human's numbers")
    ap.add_argument("--entry-route", choices=("auto", "home", "direct"), default="auto",
                    help="which door from www.pjud.cl. Runners need 'home'; residential takes the direct link. Measured per environment 2026-08-14.")
    ap.add_argument("--live", action="store_true", help="publish frames to Neon (watch_live.py)")
    ap.add_argument("--trace", choices=("off", "entry", "all"), default="off",
                    help="a JPEG before and after EVERY action, into <shots>/trace, with one "
                         "trace.jsonl of the page's own account of itself per frame. 'entry' is "
                         "the arrival only (~30 frames) and is where every remote run has died; "
                         "'all' is the whole shift and runs to thousands. Requires --shots.")
    ap.add_argument("--trace-max", type=int, default=400,
                    help="frame budget. A diagnostic that fills a runner's disk is an incident.")
    ap.add_argument("--step", choices=("off", "entry", "all"), default="off",
                    help="STOP before each action and wait for an instruction from the operator, "
                         "over Neon (see stepgate.py, step_console.py). The runner posts the frame "
                         "it is looking at and blocks until told go / run / abort. Implies --trace "
                         "at the same scope.")
    ap.add_argument("--step-timeout", type=float, default=900.0,
                    help="seconds to wait for an instruction before giving up on one step")
    ap.add_argument("--step-on-timeout", choices=("abort", "go"), default="abort",
                    help="what an unanswered step does. 'abort' by default: a runner nobody is "
                         "watching should stop, not quietly finish the hour on its own.")
    a = ap.parse_args()

    if not a.use_form_dates:
        for label, val in (("--desde", a.desde), ("--hasta", a.hasta)):
            if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", val):
                raise SystemExit(f"{label}={val!r} is not dd/mm/yyyy")
        # ⚠️ THE SITE REFUSES A RANGE LONGER THAN ONE MONTH. Discovered 2026-08-17 the expensive
        # way: six workers were launched on 01/06..31/07, every search was rejected by a
        # sweet-alert reading "El rango de fecha no puede ser superior a un Mes ! Not valid",
        # wait_results reported `empty`, and the fleet concluded its sessions were spent and began
        # burning recoveries. Nothing in the logs said "invalid range" -- an empty result and a
        # refused one look identical from the outside. Worker A never met this because its windows
        # were always a month or less.
        # Refuse at the door, like the dd/mm/yyyy check: a window the site will not accept must
        # never reach the form.
        import datetime as _dt
        d0 = _dt.datetime.strptime(a.desde, "%d/%m/%Y")
        d1 = _dt.datetime.strptime(a.hasta, "%d/%m/%Y")
        value_was = a.hasta
        # ⚠️ THE PICKER WILL NOT ACCEPT TOMORROW. Every day after today is drawn greyed out with
        # no link, so asking for the end of the current month clicks a dead cell and leaves
        # #fecHasta empty -- which the worker can only report as "reads ''". Clamp it, loudly:
        # a person standing at that calendar on the 18th clicks the 18th, because the 31st is not
        # offered. This is the one rule, not a workaround.
        _today = _dt.datetime.combine(_dt.date.today(), _dt.time())
        if d0 > _today:
            raise SystemExit(f"--desde {a.desde} is in the future; there is nothing filed yet")
        if d1 > _today:
            a.hasta = _today.strftime("%d/%m/%Y")
            print(f"[{time.strftime('%H:%M:%S')}] --hasta was {value_was} (in the future); the "
                  f"OJV picker disables every day after today -- using {a.hasta}", flush=True)
            d1 = _today
        if d1 < d0:
            raise SystemExit(f"--hasta {a.hasta} is before --desde {a.desde}")
        if (d1 - d0).days > 31:
            raise SystemExit(
                f"{a.desde}..{a.hasta} spans {(d1 - d0).days} days. The OJV refuses any range "
                f"longer than ONE MONTH ('El rango de fecha no puede ser superior a un Mes') and "
                f"the rejection arrives as a sweet-alert that reads like an empty result. "
                f"Run one month per pass.")

    ojv.ENTRY_ROUTE = a.entry_route
    C.SHOTS = a.shots or None
    # ⚠️ --step IMPLIES --trace at the same scope. Being asked "may I click this?" without the
    # picture of what "this" is would be the same blind log line the trace exists to replace.
    scope = a.step if a.step != "off" else a.trace
    if scope != "off":
        if not C.SHOTS:
            raise SystemExit("--trace/--step need --shots DIR to write frames into")
        C.TRACE, C.TRACE_SCOPE, C.PHASE = a.trace_max, scope, "entry"
        note(f"step trace ON, scope={scope}, budget={a.trace_max} frames -> {C.SHOTS}\\trace")
    if a.step != "off":
        import stepgate
        C.STEPPER = stepgate.Stepper(
            run_id=f"{os.environ.get('GITHUB_RUN_ID', 'local')}-s{a.shard}",
            timeout=a.step_timeout, on_timeout=a.step_on_timeout,
            # A hand on the page while it waits: a browser frozen stone dead for minutes is a
            # louder empty channel than anything this project has fixed.
            idle=lambda pg, s: C.human_idle(pg, s))
        note(f"STEP MODE: waiting for an instruction before each action "
             f"(run_id={C.STEPPER.run_id}, {a.step_timeout:.0f}s -> {a.step_on_timeout})")
    global DOCS_C2
    # ⚠️⚠️ SET THEM ON THE ENGINE, NOT ON THIS MODULE. `read()` now lives in human_engine and
    # divides by human_engine.SPEED; a worker-local SPEED would be set, printed, ramped and
    # reported while every reading span went on using 1.0. That is precisely the "two copies of
    # one facility, one wired and one blind" failure this whole refactor exists to end — and it
    # would have been invisible, because the log line reporting the speed reads the wrong copy.
    E.RAMP_EVERY, E.RAMP_STEP = a.ramp_every, a.ramp_step
    E.SPEED = a.speed
    DOCS_C2 = a.docs_c2
    if DOCS_C2:
        if not a.fill:
            raise SystemExit("--docs-c2 needs --fill: it opens a work-list of causas that already "
                             "have a cuaderno 2, which a sweep cannot know")
        # ⚠️ SAY WHAT THIS COSTS, BEFORE IT COSTS IT. The one law this project has measured is
        # that the binding limit is the AGGREGATE REQUEST RATE PER ADDRESS (2026-08-17: four
        # workers at ~56 POST/min were all dead by minute 5; the same four at ~23/min ran the
        # hour and produced ten times the output). A metadata open is 2 requests. This is 2 + ~3.5.
        note("DOCS MODE: every cuaderno-2 row's PDF as well — about 5.5 requests per causa "
             "against 2 for a metadata fill. Watch the aggregate with rate_watch.py, and add "
             "workers rather than speed if it is too slow.")
    if E.SPEED != 1.0:
        note(f"reading times fixed at x{E.SPEED} of the operator's"
             + ("  (TOP SPEED: only the site and the pointer are left)" if E.SPEED <= 0.01 else ""))
    if E.RAMP_EVERY:
        note(f"SPEED RAMP: x{E.RAMP_STEP} on the reading times every {E.RAMP_EVERY} opens")
    OUT.mkdir(parents=True, exist_ok=True)
    # ⚠️ THE PORT IS IN THE NAME. Timestamped to the second, two workers launched together
    # write to the SAME file and silently overwrite each other's records — and a parallelism test
    # whose output is half-missing looks like a scraping failure.
    out_file = OUT / f"h-{time.strftime('%Y%m%d-%H%M%S')}-p{a.port}.json"
    got = []
    net = []
    t_start = time.time()

    with sync_playwright() as pw:
        # ⚠️ ONE WORKER WALKS IN AT A TIME. Six fresh browsers launched together and only ONE got
        # in; the same happens locally when two load pjud.cl in the same second. A burst of
        # brand-new sessions is itself the trigger, independently of request rate — so the gate is
        # held across launching Chrome, walking in, AND the first confirmed search. Being on the
        # form proves nothing: four workers once reached a page and not one could search.
        gate = None
        if a.gate == "db":
            # ⚠️ SEPARATE MACHINES HAVE NO SHARED FILESYSTEM. Cloud runners gate through Neon,
            # which they all reach anyway. The holder name carries the run id so a corpse left by
            # a cancelled run is distinguishable from a live neighbour.
            gate = ojv.PgEntryLock(f"h{a.shard}-{os.environ.get('GITHUB_RUN_ID', 'local')}")
            note("waiting for the entry gate (db)")
            gate.acquire()
        elif a.gate == "file":
            gate = ojv.EntryLock(HERE.parent / "data" / "h-entry.lock")
            note("waiting for the entry gate")
            gate.acquire()
        if a.launch:
            # ⚠️ ONE PROFILE PER PORT. Chrome treats a --user-data-dir as a SINGLETON: launch a
            # second browser on a dir another Chrome still holds and the two fight — ours came up,
            # entered, searched, and was closed under us 75 s later (TargetClosedError), which
            # reads exactly like a site problem and is not one. The profile dir is the lock, not
            # the port, so the port has to be in the dir name.
            prof = a.profile or str(Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
                                    / f"pjud_wH{a.port}")
            if not A.launch_chrome(a.port, prof, 1, exe=A.chrome_executable(pw)):
                raise SystemExit(f"could not start Chrome on {a.port}")
        b = None
        for attempt in (1, 2, 3, 4):
            try:
                b = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{a.port}", timeout=45000)
                break
            except Exception as e:
                note(f"CDP attempt {attempt}/4: {str(e)[:70]}")
                time.sleep(10)
        if b is None:
            raise SystemExit(f"no CDP on {a.port}")
        ctx = b.contexts[0]
        # Our own telemetry, injected the same way it was injected to measure the human.
        try:
            ctx.add_init_script(f"({human_record.INJECT})()")
        except Exception:
            pass

        live = None
        if a.live:
            import live_view
            live = live_view.Live("H", every=6.0)
            C.IDLE_HOOK = live.tick

        p = ojv.walk_in(ctx)
        if p is None:
            if gate is not None:
                gate.release()    # nothing to confirm; holding it would strand the queue
            raise SystemExit("could not reach the OJV")
        if gate is not None and a.gate_release == "entry":
            note("  on the form — releasing the entry gate (arrival done)")
            gate.release()
        note(f"in: {p.url[:70]}")
        # ⚠️ SIZE THE WINDOW BEFORE TOUCHING THE FORM. The results table is ~1115 px wide; a
        # narrower viewport scrolls horizontally and puts the magnifier column outside the window,
        # where human_click correctly refuses it and we spend the afternoon blaming the site.
        try:
            _ww, _wh = (int(x) for x in a.window.lower().split("x"))
        except Exception:
            _ww, _wh = 1440, 900
        ok_w, vp = C.ensure_window(p, _ww, _wh)
        note(f"window: {vp} {'ok' if ok_w else '*** TOO SMALL — clicks will be refused ***'}")
        p.on("response", ojv.make_tap(net))
        settler = A.Settler(p)
        try:
            p.evaluate(human_record.INJECT)
        except Exception:
            pass

        pres = human_motion.Presence(p, rate=a.rate)
        # ⚠️ A HAND ON THE PAGE WHILE THE SITE ANSWERS. Without this the worker is motionless for
        # the ~20 s of every search — 15% of a 150-minute session with an empty input channel,
        # measured on the 1,046-open run. See ojv.WAIT_PRESENCE for the risk this carries.
        if not a.no_search_presence:
            ojv.WAIT_PRESENCE = lambda page, secs: pres.run(secs)
        lst = build_form_mouse(p, settler,
                               None if a.use_form_dates else a.desde,
                               None if a.use_form_dates else a.hasta)
        if not lst or len(lst) < 50:
            if gate is not None:
                gate.release()
            raise SystemExit("not the national tribunal list — aborting")
        if gate is not None and a.gate_release == "form":
            note(f"  form built with {len(lst)} tribunales — releasing the entry gate")
            gate.release()
        # The arrival is over. `--trace entry` / `--step entry` stop here; `all` carries on.
        C.PHASE = "work"

        if a.probe_picker:
            # One click on a date field -- which is a thing a person does constantly -- purely to
            # learn why the widget did not open last time. Never fatal: it runs after the form is
            # ready and its failure cannot stop the behaviour test it is riding along with.
            note("probing the datepicker (non-fatal)")
            try:
                C.human_click(p, "#fecDesde", timeout=6000)
                p.wait_for_timeout(700)
                note("  picker: " + json.dumps(p.evaluate(
                    "()=>{const i=document.querySelector('#fecDesde');"
                    " const divs=[...document.querySelectorAll('div')]"
                    "   .filter(d=>/datepicker|calendar/i.test(d.id+' '+d.className));"
                    " return {focused: document.activeElement && document.activeElement.id,"
                    "  divs: divs.slice(0,6).map(d=>({id:d.id, cls:(d.className||'').slice(0,44),"
                    "   disp:getComputedStyle(d).display, offP:d.offsetParent!==null,"
                    "   days:d.querySelectorAll('td a').length}))};}"), ensure_ascii=False))
            except Exception as e:
                note(f"  picker probe failed: {str(e)[:70]}")
            ojv.click_away(p)

        # ── what this run will visit ─────────────────────────────────────────────────
        # SWEEP: walk the courts and open every bank causa on page 1. Page 1 only, deliberately —
        # the recorded session read one page of one court, so that is the only list-reading
        # behaviour we have measured, and paginating would be inventing one.
        #
        # FILL: open a KNOWN list instead. There are ~4,500 banked June+July causas and 13 of
        # them have a second cuaderno, so that work is not discovery — and a sweep would spend
        # most of its opens re-finding records we have held for weeks, which is the scarcest
        # thing this project spends. Fill DOES paginate, because a wanted rol can sit past row
        # 100; that paging is not measured human behaviour and is marked as such.
        if a.fill:
            def iso(v):
                return "-".join(reversed(v.split("/")))
            mode = "docs-c2" if a.docs_c2 else "cuaderno2"
            todo, n_todo = fill_targets(iso(a.desde), iso(a.hasta), a.max_causas,
                                        corte=a.corte, mode=mode)
            targets = [t for t in lst if t["v"] in todo]
            owed = ("the documents of cuaderno 2" if mode == "docs-c2" else "cuaderno 2")
            note(f"fill[{mode}]: {n_todo} causas need {owed}"
                 f"{f' in {a.corte}' if a.corte else ''}, across {len(todo)} tribunales "
                 f"({len(targets)} of them selectable in this form)")
            # ⚠️ AN EMPTY WORK-LIST IS NOT A BLOCK, AND IT IS NOT NECESSARILY SUCCESS EITHER.
            # `--fill` re-opens causas the database already holds; pointed at a window nothing was
            # ever swept for it searches NOTHING and reports `nothing-searched`, which reads
            # exactly like a refusal (measured 2026-08-18, the May dispatch). Say which it is.
            if not n_todo:
                note("  nothing owed for this window — either it is finished, or it was never "
                     "swept (a --corte name that does not match spells itself the same way)")
            # ⚠️ SHARD THE COURT LIST, NOT THE DATE WINDOW. --start/--end are indices into the
            # NATIONAL list and mean nothing here: fill's targets are only the courts that still
            # owe us a cuaderno 2, and which those are changes after every ingest. Six workers
            # given the same target list would open the same causas six times — and a causa open
            # is the scarcest thing this project spends.
            if a.of > 1:
                targets = [t for i, t in enumerate(targets) if i % a.of == (a.shard - 1)]
                mine = sum(len(todo[t["v"]]) for t in targets)
                note(f"  shard {a.shard}/{a.of}: {len(targets)} courts, {mine} causas to fill")
        else:
            todo = None
            targets = ([t for t in lst if t["v"] == a.tribunal] if a.tribunal
                       else lst[a.start:(a.end + 1 if a.end is not None else None)])
            note(f"sweeping {len(targets)} tribunal(es), page 1 of each")
        tally = {"opens": 0, "kept": 0, "gated": 0, "searches": 0, "courts": 0}
        state = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "courts": [], "verdict": ""}
        state_file = OUT / f"h-{time.strftime('%Y%m%d-%H%M%S')}-p{a.port}-state.json"

        def save_state(verdict=""):
            state["verdict"] = verdict or state["verdict"]
            state["minutes"] = round((time.time() - t_start) / 60.0, 1)
            state["tally"] = dict(tally)
            state_file.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                                  encoding="utf-8")

        def over():
            return bool(a.max_minutes) and (time.time() - t_start) / 60.0 >= a.max_minutes

        # ── recovery ─────────────────────────────────────────────────────────────────
        # ⚠️ WHY THIS EXISTS. Worker 9451 of the six-worker run had its first search come back
        # `stale` after 75 s — a dead session — and then spent THIRTY MINUTES failing to select
        # tribunal after tribunal, skipping 38 courts, before reporting a verdict. Worker A has
        # re-entered after a block since 2026-08-07: it costs ~18 s, it works because a block
        # parks challenge frames on a session that is otherwise healthy, and NOTHING about the
        # profile is burned. Worker H shipped without any of it.
        recoveries = [0]

        def recover(why):
            """Re-enter and rebuild the form. (ok, page, settler). Never raises."""
            if recoveries[0] >= a.max_recover:
                note(f"  *** {recoveries[0]} recoveries already used — not trying again")
                return False, None, None
            recoveries[0] += 1
            # ⚠️ CONNECTIVITY FIRST. An outage produces exactly the symptoms of a wedged session —
            # searches that never prove fresh, selects that time out — but none of the remedies
            # apply, and charging it to the recovery budget spends a life on the site's behalf
            # for a fault that was never the site's.
            if not ojv.internet_up():
                back, waited = ojv.wait_for_internet()
                if not back:
                    note("  *** offline and not coming back")
                    return False, None, None
                note(f"  back online after {waited / 60:.1f} min — re-entering, budget untouched")
                recoveries[0] -= 1
            cool = A.COOL_OFF * recoveries[0]
            note(f"  recovery {recoveries[0]}/{a.max_recover} ({why}): cooling off {cool:.0f}s")
            # ⚠️ COOL OFF UNGATED, AND RE-ENTER GATED. Sleeping while holding the arrival gate
            # makes every other worker wait out OUR penalty; but the re-entry itself IS an
            # arrival, so it takes a fresh gate of its own.
            time.sleep(cool)
            rg = (ojv.PgEntryLock(f"h{a.shard}r-{os.environ.get('GITHUB_RUN_ID', 'local')}")
                  if a.gate == "db" else
                  ojv.EntryLock(HERE.parent / "data" / "h-entry.lock") if a.gate == "file" else None)
            if rg is not None:
                rg.acquire()
            try:
                q = ojv.walk_in(ctx)
                if q is None:
                    note("  *** could not re-enter")
                    return False, None, None
                q.on("response", ojv.make_tap(net))
                st2 = A.Settler(q)
                try:
                    q.evaluate(human_record.INJECT)
                except Exception:
                    pass
                # The hand moves to the new page, and the search-wait presence follows it.
                pres.page = q
                pres._sync_bounds()
                lst2 = build_form_mouse(q, st2, None if a.use_form_dates else a.desde,
                                        None if a.use_form_dates else a.hasta)
                if not lst2 or len(lst2) < 50:
                    note("  *** re-entered but the tribunal list is not the national one")
                    return False, None, None
                note(f"  recovered — form rebuilt with {len(lst2)} tribunales")
                return True, q, st2
            finally:
                if rg is not None:
                    rg.release()

        stop = ""
        consec_select_fail = consec_bad_search = 0
        skipped = []
        # ⚠️ AN INDEX LOOP, NOT `for ... in enumerate`, SO A RECOVERED WORKER CAN RETRY THE COURT
        # IT WAS ON. Worker A does the same thing (`idx -= 1; continue`) for the same reason: the
        # court that exposed the wedged form has not been searched, and dropping it would leave a
        # silent hole exactly where the trouble was.
        ti = -1
        while True:
            ti += 1
            if ti >= len(targets):
                break
            t = targets[ti]
            if over():
                stop = "lifespan"
                break
            if a.max_causas and tally["opens"] >= a.max_causas:
                stop = "max-causas"
                break
            tid, tname = t["v"], t["t"]
            note(f"[{ti + 1}/{len(targets)}] tribunal {tid} — {tname}")
            if not set_select_mouse(p, "#fecTribunal", tid):
                # ⚠️ A RUN OF THESE MEANS THE FORM IS WEDGED, NOT THAT THE COURTS ARE MISSING.
                # Measured 2026-08-17: a worker's first search came back `stale` after 75 s (a dead
                # session), every #fecTribunal select then timed out, and it skipped all 38
                # remaining courts over thirty minutes and reported **finished** — which to any
                # resume logic means "this range is swept". Worker A has carried a select-fail
                # limit and a `skipped` list since 08-12 for exactly this; worker H had neither.
                consec_select_fail += 1
                skipped.append({"idx": ti, "id": tid, "name": tname})
                note(f"  could not select it with the mouse — skipping "
                     f"({consec_select_fail} in a row)")
                if consec_select_fail >= SELECT_FAIL_LIMIT:
                    note(f"  *** {consec_select_fail} tribunal selects failed in a row — the form "
                         f"is wedged, not the courts.")
                    ok, q, st2 = recover("wedged form")
                    if not ok:
                        note(f"  *** {len(targets) - ti} courts in this range were never searched")
                        stop = "select-failures (form wedged, recovery failed)"
                        break
                    p, settler = q, st2
                    consec_select_fail = 0
                    skipped = [x for x in skipped if x["idx"] != ti]
                    ti -= 1                     # retry the court the wedged form cost us
                    continue
                continue
            consec_select_fail = 0
            ojv.click_away(p)
            pres.travel_to(p, "#btnConConsultaFec")
            # Where the hand waits while the results come back: over the table they will appear
            # in, which is where a person looks.
            pres.aim(p, "#dtaTableDetalleFecha")

            # ⚠️ NO hasattr FALLBACKS. The first version guessed at three function names and hid
            # the guesses behind `hasattr(...) else (...)`. `C.result_rows` does not exist, so it
            # returned [] and the verdict tuple defaulted to ("results", 0, "") — the run then
            # reported "search -> results in 0s, 0 rows" and exited clean while the page in front
            # of it held 117 registros and 21 bank causas. A fallback for a name you invented is
            # not robustness, it manufactures a success. Call the real function and let a wrong
            # name raise at once.
            net.clear()
            C.human_click(p, "#btnConConsultaFec")
            kind, el = ojv.wait_results(p, settler, net)
            hit, why = ojv.blocked(p, net)
            tally["searches"] += 1
            if gate is not None and gate.held:
                # ⚠️ RELEASED ON A VERDICT, GOOD OR BAD — and on a SEARCH, not on reaching the
                # form. Four workers once all reached a page and not one could search, so
                # releasing on the form would have opened the gate on the strength of nothing.
                # And a worker that cannot search must not hold the others behind it all night.
                note(f"  first search {'CONFIRMED' if kind == 'results' and not hit else 'did NOT confirm'}"
                     f" — releasing the entry gate, next worker may come in")
                gate.release()
            if hit:
                note(f"  *** BLOCKED ON SEARCH after {tally['opens']} opens / "
                     f"{tally['searches']} searches — {why}")
                stop = f"blocked-on-search: {why}"
                break
            if kind != "results":
                # ⚠️ AND A RUN OF UNCONFIRMED SEARCHES IS A DEAD SESSION. `stale` means the search
                # never proved fresh; recording court after court that way is how a degrading
                # session files live tribunales as empty. Worker A treats this as a throttle and
                # re-enters; worker H does not recover yet, so it must at least stop and SAY so.
                consec_bad_search += 1
                note(f"  search -> {kind} in {el:.0f}s — not recording this court "
                     f"({consec_bad_search} unconfirmed in a row)")
                state["courts"].append({"id": tid, "name": tname, "kind": kind})
                save_state()
                if consec_bad_search >= BAD_SEARCH_LIMIT:
                    note(f"  *** {consec_bad_search} searches never proved fresh — this session is "
                         f"spent.")
                    ok, q, st2 = recover(f"searches {kind}")
                    if not ok:
                        stop = f"searches-not-confirming ({kind}, recovery failed)"
                        break
                    p, settler = q, st2
                    consec_bad_search = 0
                    ti -= 1                     # retry this court on the fresh session
                    continue
                continue
            consec_bad_search = 0

            total = C.total_registros(p)
            tally["courts"] += 1
            want = dict(todo[tid]) if todo else None
            if want is None:
                rows = C.page_bank_causas(p)
                note(f"  {total} registros, {len(rows)} bank causas on page 1 ({el:.0f}s)")
            else:
                rows = [r for r in C.page_rows(p) if r["has"] and r["rol"] in want]
                note(f"  {total} registros, want {len(want)} here, {len(rows)} on page 1 "
                     f"({el:.0f}s)")
            court = {"id": tid, "name": tname, "kind": kind, "total": total,
                     "banks": len(rows), "opens": 0, "wanted": len(want) if want else None}
            state["courts"].append(court)

            page = 1
            for row in rows:
                if over():
                    stop = "lifespan"
                    break
                if a.max_causas and tally["opens"] >= a.max_causas:
                    stop = "max-causas"
                    break
                hit, why = ojv.blocked(p, net)
                if hit:
                    note(f"  *** BLOCKED after {tally['opens']} opens — {why}")
                    stop = f"blocked: {why}"
                    break
                counters(p)                    # read-and-clear, so [me] below is THIS causa
                t_open = time.time()
                rec = harvest(p, pres, f"{tid}-{row['rol']}", row, tid, tname,
                                  only_proc=a.only_proc, net=net)
                tally["opens"] += 1
                court["opens"] += 1
                if rec in ("click-refused", "stale-row"):
                    # our click never reached the row: one causa lost, session untouched
                    tally["refused"] = tally.get("refused", 0) + 1
                    read(pres, p, READ_LIST, "#dtaTableDetalleFecha")
                    continue
                if rec is None:
                    # ⚠️ NOT automatically the wall. A local session produced this exact signature
                    # on 2026-08-16 because WE clicked the next row while the previous modal's
                    # backdrop was still up. Say what the page is before concluding anything.
                    note(f"  modal never opened — where={ojv.locate(p)} "
                         f"blocked={ojv.blocked(p, net)}")
                    # ⚠️ AND RECOVER FROM IT. I wired recovery into the wedged-form and
                    # unconfirmed-search paths and left out the symptom that has ended more
                    # sessions than both: a modal that never renders. It is the same illness —
                    # the session is spent or the page is wedged — and re-entry is the same
                    # remedy. A worker died on it 5.6 minutes into the very run meant to prove
                    # recovery worked, which is as clear a demonstration of the gap as I could
                    # have asked for.
                    ok, q, st2 = recover("modal never opened")
                    if not ok:
                        stop = "modal-never-opened (recovery failed)"
                        break
                    p, settler = q, st2
                    consec_bad_search = consec_select_fail = 0
                    ti -= 1                     # this court still has causas we have not opened
                    break
                got.append(rec)
                tally["gated" if rec.get("skipped_etapa") or rec.get("skipped_proc")
                      else "kept"] += 1
                if a.measure:
                    c1 = counters(p)
                    if c1:
                        secs = max(0.1, time.time() - t_open)
                        c = c1["c"]
                        note(f"      [me] {c.get('mousemove', 0) / secs:5.1f} mousemove/s  "
                             f"{c.get('mouseover', 0) / secs:4.1f} mouseover/s  "
                             f"keydown={c.get('keydown', 0)}  wheel={c.get('wheel', 0)}  "
                             f"(human: 25.8 / 6.4 / 0 / 0)")
                out_file.write_text(json.dumps(got, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
                save_state()
                if E.RAMP_EVERY and tally["opens"] % E.RAMP_EVERY == 0:
                    E.SPEED = E.SPEED * E.RAMP_STEP
                    rung = {"opens": tally["opens"], "speed": round(E.SPEED, 3),
                           "opens_per_min": round(tally["opens"] / max(0.01, (time.time() - t_start) / 60), 2)}
                    state.setdefault("rungs", []).append(rung)
                    note(f"  === RAMP: reading times now x{E.SPEED:.2f} of the operator's "
                         f"(after {tally['opens']} opens, {rung['opens_per_min']} opens/min so far)")
                # ⚠️ GO TO THE NEXT CAUSA, DO NOT LOITER (operator: "why not just directly go to
                # the next causa?"). Copying the aggregate 13 s open-to-open and spending the
                # surplus wandering reproduces an INTERVAL, not a behaviour — a person travels to
                # the next row and clicks it. The reading below is over the list, as theirs was.
                read(pres, p, READ_LIST, "#dtaTableDetalleFecha")
                nxt = rows[rows.index(row) + 1] if row is not rows[-1] else None
                if nxt is not None:
                    pres.travel_to(page_row(p, nxt))
                if random.random() < 0.35:
                    C.human_scroll(p, notches=random.randint(1, 3))
            save_state()
            if stop:
                break
            # ⚠️ FILL PAGINATES; THE SWEEP DOES NOT. A wanted rol can sit anywhere in a court with
            # 250 registros, so stopping at page 1 would silently leave most of the list unfilled
            # — the same under-collection page-1-only census produced. Harvest the page, THEN
            # advance: a row index belongs to the page it was read from, and clicking page-1
            # indices with the last page on screen opens the WRONG causas.
            recovered_here = False
            while want and not stop and page < a.max_pages:
                found = {r["rol"] for r in rows}
                for r in found:
                    want.pop(r, None)
                if not want:
                    break
                why = A.advance(p, page)
                if why != "more":
                    if why == "stuck":
                        note(f"  [warn] paginator stuck on page {page}, {len(want)} not reached")
                    break
                page += 1
                # ⚠️⚠️ WAIT FOR THE NETWORK TO GO QUIET, NOT JUST THE DOM. wait_idle plus a fixed
                # settle was not enough: the probe caught a click whose only following response
                # was `consultaFechaCivil.php` — the PAGINATION request still arriving AFTER we
                # clicked. The row was correct at click time (the rol check passed, stale-rows=0,
                # which refutes the stale-index theory) and was then replaced by the response
                # landing, discarding our click. No causa request is ever made, and it reads as
                # the site ignoring us.
                # So: wait until that endpoint stops answering, then settle, then read indices.
                _n = len(net)
                _t0 = time.time()
                _quiet = time.time()
                while time.time() - _t0 < 12.0:
                    p.wait_for_timeout(250)
                    if len(net) != _n:
                        _n = len(net)
                        _quiet = time.time()          # something arrived; restart the quiet clock
                    elif time.time() - _quiet > 1.5:
                        break
                # ⚠️ LET THE REDRAW FINISH BEFORE READING ROW INDICES. advance() returns as soon
                # as the FIRST row changes, which proves a swap started, not that it ended. Read
                # too early and the indices belong to a table that is still being rebuilt — then
                # `.nth(i)` clicks a row whose handler has been replaced, no request is made at
                # all, and it looks exactly like the site ignoring us. MEASURED 2026-08-17: every
                # one of these failures (4/4) happened after a page advance, none on page 1.
                C.wait_idle(p)
                p.wait_for_timeout(700)
                rows = [r for r in C.page_rows(p) if r["has"] and r["rol"] in want]
                note(f"  page {page}: {len(rows)} wanted rows here ({len(want)} still missing)")
                for row in rows:
                    if over() or (a.max_causas and tally["opens"] >= a.max_causas):
                        stop = "lifespan" if over() else "max-causas"
                        break
                    hit, why2 = ojv.blocked(p, net)
                    if hit:
                        note(f"  *** BLOCKED after {tally['opens']} opens — {why2}")
                        stop = f"blocked: {why2}"
                        break
                    counters(p)
                    t_open = time.time()
                    rec = harvest(p, pres, f"{tid}-{row['rol']}", row, tid, tname,
                                  only_proc=a.only_proc, net=net)
                    tally["opens"] += 1
                    court["opens"] += 1
                    if rec in ("click-refused", "stale-row"):
                        # our click never reached the row: one causa lost, session untouched
                        tally["refused"] = tally.get("refused", 0) + 1
                        read(pres, p, READ_LIST, "#dtaTableDetalleFecha")
                        continue
                    if rec is None:
                        # ⚠️ THE SAME FAILURE HAS TWO CALL SITES AND I FIXED ONE. Recovery was
                        # wired into the main causa loop and NOT into this pagination loop, so a
                        # worker that hit a dead modal while paging through a court died on the
                        # spot — 107 opens in, with three recoveries unused. A failure path
                        # duplicated is a failure path half-repaired; the giveaway was a worker
                        # reporting `modal-never-opened` one second after the symptom, with no
                        # cool-off in between.
                        note(f"  modal never opened — where={ojv.locate(p)} "
                             f"blocked={ojv.blocked(p, net)}")
                        ok, q, st2 = recover("modal never opened (paging)")
                        if not ok:
                            stop = "modal-never-opened (recovery failed)"
                            break
                        p, settler = q, st2
                        consec_bad_search = consec_select_fail = 0
                        # ⚠️ ESCAPE BOTH LOOPS. After a re-entry the paginator state belongs to a
                        # page that no longer exists, so advancing it would ask a fresh session for
                        # "page 3" of a search it never ran. Re-search the court instead; `want`
                        # still lists exactly what it owes us.
                        ti -= 1
                        recovered_here = True
                        break
                    got.append(rec)
                    tally["gated" if rec.get("skipped_etapa") or rec.get("skipped_proc")
                          else "kept"] += 1
                    want.pop(row["rol"], None)
                    out_file.write_text(json.dumps(got, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
                    save_state()
                    read(pres, p, READ_LIST, "#dtaTableDetalleFecha")
                if stop or recovered_here:
                    break
            if recovered_here:
                continue
            if want:
                court["unreached"] = len(want)
            save_state()
            if stop:
                break

        # ⚠️ NEVER REPORT "finished" FOR A RANGE NOTHING WAS SEARCHED IN. That is the verdict a
        # resume reads to decide there is no work left here.
        if not stop and tally["courts"] == 0:
            stop = "nothing-searched"
        state["skipped"] = skipped
        save_state(stop or "finished")
        el = (time.time() - t_start) / 60.0
        s = pres.stats()
        note(f"DONE in {el:.1f} min — {stop or 'finished'} | refused={tally.get('refused', 0)} "
             f"searches={tally['searches']} opens={tally['opens']} kept={tally['kept']} "
             f"gated={tally['gated']}  ({tally['opens']/max(0.01, el):.1f} opens/min, "
             f"human did 4.6)")
        note(f"state -> {state_file}")
        note(f"pointer: {s['moves']} moves, legs rest={s['rest']} drift={s['drift']} "
             f"traverse={s['traverse']}  = {s['moves']/max(1.0, el*60):.1f}/s (human 25.8)")
        note(f"records -> {out_file}")
        if live:
            live.close(f"opens={tally['opens']}")


if __name__ == "__main__":
    # ⚠️ AN OPERATOR SAYING STOP IS NOT A CRASH. --step lets a human end a run mid-action; that
    # must exit cleanly and say so, not print a traceback that reads like the site did something.
    try:
        main()
    except Exception as e:
        if type(e).__name__ != "Aborted":
            raise
        note(f"STOPPED BY THE OPERATOR: {e}")
        sys.exit(0)
