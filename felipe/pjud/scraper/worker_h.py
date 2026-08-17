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

# ── what the operator actually did, per causa ────────────────────────────────
# ⚠️ THESE ARE READING TIMES, NOT WAITS, and the difference is the whole design. Stripping the
# invented intervals (operator: "no padding at all — just mimic me") was right, but I then
# implemented "no padding" as travel-only: the worker moved its pointer solely while going from
# one control to the next, finished 20 causas in 3 minutes, and emitted 324 pointer events in the
# whole run — 1.8/s against the human's 25.8/s. Removing the padding had removed the presence.
#
# The resolution is the operator's own: "mimic the actions at the same pace as me." READING IS AN
# ACTION. They spent ~13 s per causa with the pointer moving continuously over the content, and
# reproducing that is mimicry, not padding. What made the first version padding was that the time
# was spent DRIFTING NOWHERE; this time is spent moving over the thing being read.
#
# Measured from data/human/session-20260816-212249.jsonl:
READ_BOOK1 = (1.8, 2.6)      # modal open -> switch to book 2 (median 2.0, max 5.0)
READ_BOOK2 = (2.0, 3.2)      # switch -> close (observed 2-3)
READ_LIST = (6.5, 9.0)       # close -> next open (13.1 total, less ~5 spent inside the modal)

# ⚠️ Run-level, NOT per-court. A throttle that costs one court simply moves on to the next and
# degrades for hours without a single detector firing — worker A learned that on 2026-08-08.
SELECT_FAIL_LIMIT = 5        # consecutive #fecTribunal selects that fail => the form is wedged
BAD_SEARCH_LIMIT = 3         # consecutive searches that never prove fresh => the session is spent


def jitter(lo, hi):
    return random.uniform(lo, hi)


# ── the speed ramp (step 2 of the operator's plan) ───────────────────────────
# ⚠️ RAMP ONE THING: the READING TIMES. Everything else stays exactly as measured — same acts,
# same order, same pointer rate, same zero keystrokes. So a trip during the ramp is attributable
# to pace and nothing else, which is the only reason to run a ramp at all.
#
# ⚠️ AND IT MUST FLOOR ITSELF. Worker A's ramps found that below ~15 s the cycle stops shrinking
# because the SITE's own response time is what remains — 8 s and 6 s were no better than 10 s.
# Expect the same here: at some level the reading times stop being what costs the time, and any
# further "speed" is measuring the site, not us. Report the achieved opens/min, never the level.
SPEED = 1.0            # divides every reading span; 1.0 = exactly what the operator did
RAMP_EVERY = 0         # causas per rung (0 = no ramp)
RAMP_STEP = 0.75       # multiply the spans by this at each rung


def read(pres, target, span, selector=None):
    """Spend `span` seconds READING something, the way a person does: pointer over it, moving.

    This is the only kind of wait in this worker other than waiting for the site. It is not a
    delay with motion bolted on — the aim comes first, so every second of it lands on the content
    and produces the `mouseover` stream that a hand produces and a timer never will.
    """
    pres.aim(target, selector)
    lo, hi = span
    pres.run(jitter(lo * SPEED, hi * SPEED))


def close_modal_human(page, pres):
    """Move the hand to the close control, close it, and WAIT FOR IT TO ACTUALLY BE GONE.

    ⚠️ THE THIRD TIME I CUT A WAIT-FOR-THE-SITE AS IF IT WERE PADDING. Worker A sleeps 1.2-1.5 s
    between close_modal and clear_stuck_modal; stripping every fixed wait took that with it, and
    the modal's fade plus its `.modal-backdrop` outlive the close call. The next row click then
    lands on the backdrop, nothing opens, and the worker sits in its 90 s modal-wait loop — the
    exact "modal did not open" signature we have been chasing REMOTELY, manufactured locally by
    our own impatience. The operator spotted the stall and refreshed the page.
    ⇒ "No padding" means no interval invented to look human. It never meant "do not wait for the
    browser to finish what you asked it to do". A condition, not a duration.
    """
    pres.travel_to(page, "#modalDetalleCivil .close, #modalDetalleCivil button.close")
    C.close_modal(page, "#modalDetalleCivil")
    pres.aim(page, "#dtaTableDetalleFecha")
    gone = pres.run(6.0, poll=lambda: page.evaluate(
        "()=>{const m=document.querySelector('#modalDetalleCivil');"
        " const shown = !!m && (m.offsetWidth||m.offsetHeight||m.getClientRects().length);"
        " return !shown && !document.querySelector('.modal-backdrop');}"), poll_every=0.2)
    if not gone:
        note("      [warn] modal/backdrop still up 6s after closing — clearing it")
    C.clear_stuck_modal(page)


def page_row(page, row):
    """The locator for one result row — what the hand should be heading toward next."""
    return page.locator("#dtaTableDetalleFecha tbody tr").nth(row["i"])


def hover(page, sel):
    """Reach a control with the pointer and stop there. NEVER click a <select>: that opens
    Chrome's native popup, an OS surface no CDP event can reach, and everything after it is
    delivered into a dropdown nobody can see."""
    try:
        b = page.locator(sel).bounding_box()
        if not b:
            return False
        C._human_pointer(page, b["x"] + b["width"] * random.uniform(0.3, 0.7),
                         b["y"] + b["height"] / 2, press=False)
        return True
    except Exception:
        return False


def set_select_mouse(page, sel, value=None, index=None, settle=4.0):
    """Change a select with a real pointer arrival and ZERO keystrokes.

    ⚠️ POLL THE VALUE BACK; DO NOT READ IT ONCE. Measured 2026-08-16 on the cuaderno select: two
    of the first three switches "failed" while `select_option` itself raised nothing. Changing
    the cuaderno fires an AJAX that RE-RENDERS the modal, select included, so a read 120-320 ms
    later can land on a control that is being replaced. The switch had usually taken; the check
    had not waited for it. Reading a value back is the right rule — reading it too early is how
    the rule gets a bad name.
    """
    # ⚠️ NEVER VERIFY AGAINST A VALUE THAT ROTATES. The cuaderno options' values are JWTs with
    # `iat`/`exp` inside, and the site MINTS FRESH ONES when the modal re-renders — so comparing
    # the value we asked for against the value now present reported failure on a switch that had
    # plainly worked (the diagnostic printed the selected option as "2 - Apremio Ejecutivo
    # Obligación de Dar" while the check said no). Two causas' worth of book 2 was thrown away
    # for it. Verify by INDEX, which is what we actually meant.
    # ⚠️ A SHORT TIMEOUT AND ONE RECOVERY. select_option's default is 30 s of waiting for the
    # element to be actionable, and it spent every one of them on a #fecCompetencia sitting inside
    # a COLLAPSED accordion — then the run aborted with "not the national tribunal list". Thirty
    # seconds of silence followed by a misleading verdict, for a panel that needed reopening.
    hover(page, sel)
    for attempt in (1, 2):
        try:
            if index is not None:
                page.select_option(sel, index=index, timeout=8000)
            else:
                page.select_option(sel, value, timeout=8000)
            break
        except Exception as e:
            note(f"    [warn] select {sel}="
                 f"{index if index is not None else str(value)[:16]}: {str(e)[:60]}")
            if attempt == 2:
                return False
            try:
                C.open_fecha_panel(page)      # the usual reason: the panel closed under us
            except Exception:
                pass
            page.wait_for_timeout(800)
    t0 = time.time()
    while time.time() - t0 < settle:
        page.wait_for_timeout(200)
        try:
            if index is not None:
                if page.eval_on_selector(sel, "e=>e.selectedIndex") == index:
                    return True
            elif page.eval_on_selector(sel, "e=>e.value") == str(value):
                return True
        except Exception:
            pass                      # mid-re-render the node can vanish; that is not a failure
    try:
        st = page.evaluate("(s)=>{const e=document.querySelector(s);"
                           " return e ? {i:e.selectedIndex, n:e.options.length,"
                           "  sel:(e.options[e.selectedIndex]||{}).text} : null;}", sel)
    except Exception:
        st = None
    want = f"index {index}" if index is not None else f"{str(value)[:18]}..."
    note(f"    [warn] {sel} did not settle on {want} after {settle:.0f}s — now {st!r}")
    return False


MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]


def pick_date_mouse(page, sel, value, max_hops=36):
    """Set a date by DRIVING THE DATEPICKER WITH THE MOUSE — the widget the site ships, and the
    only control a person has, because the field itself is `readonly`. dd/mm/yyyy.

    jQuery UI: one shared `#ui-datepicker-div`, `a.ui-datepicker-prev/next` to change month, day
    links in `table.ui-datepicker-calendar`. Verified live rather than guessed from the page's
    library list — and then verified twice more, because two obvious ways to read it are wrong.
    """
    d, m, y = (int(x) for x in value.split("/"))
    if page.eval_on_selector(sel, "e=>e.value") == value:
        return True
    div = "#ui-datepicker-div"

    def picker_ready():
        """Visible, with a rendered calendar.

        ⚠️ DO NOT THRESHOLD ON THE DAY COUNT. I first required >=20 day links, reasoning that the
        16 I had seen meant a half-drawn month, and the widget then "failed" twice in a row while
        being open the entire time. The real month shows 31. Whatever the 16 was, inventing a
        rule from one observation cost two live sessions — ask only whether a calendar is there.
        """
        try:
            return page.evaluate(
                "(s)=>{const d=document.querySelector(s);"
                " return !!d && d.offsetParent!==null"
                "        && !!d.querySelector('td[data-month][data-year]');}", div)
        except Exception:
            return False

    def open_picker():
        """Make sure the calendar is on screen right now, clicking the field if it is not.

        ⚠️ OPENNESS IS NOT A STATE YOU CHECK ONCE. The previous version proved the picker was
        ready, broke out of its retry loop, and then read `None` from the very next evaluate —
        the widget had closed in between. Anything that can close on its own must be re-checked
        at the point of use, not confirmed at the top and assumed thereafter.
        """
        if picker_ready():
            return True
        if not C.human_click(page, sel, timeout=6000):
            cov = None
            try:
                cov = ojv.blocking_overlay(page, sel)
            except Exception:
                pass
            # ⚠️ NEVER RETURN FALSE IN SILENCE — an earlier version did, and the run died saying
            # "could not set #fecDesde" without ever mentioning that the CLICK was what failed.
            note(f"    [warn] could not click {sel} — where={ojv.locate(page)} covered_by={cov}")
            if cov:
                try:
                    ojv.clear_overlay(page, sel)
                except Exception:
                    pass
            return False
        t0 = time.time()
        while time.time() - t0 < 4.0 and not picker_ready():
            page.wait_for_timeout(150)
        return picker_ready()

    for hop in range(max_hops):
        if not open_picker():
            if hop >= 2:
                note(f"    [warn] datepicker for {sel} would not stay open")
                return False
            continue
        # ⚠️ READ MONTH AND YEAR OFF THE DAY CELLS, NEVER THE HEADER. Measured live 2026-08-16,
        # and BOTH header reads are traps. `.ui-datepicker-month` is a SPAN here while
        # `.ui-datepicker-year` is a SELECT, so `textContent` returns every option glued together
        # ("2010201120122013...") — and the select's `.value` is no better: it read 2020 while
        # the header plainly displayed Agosto 2026. Either way "have we reached the target month?"
        # is answered with nonsense and the widget marches through months until it runs out of
        # hops. That is what the operator saw as the datepicker "going haywire" — and I fixed the
        # first read, re-ran, and walked straight into the second.
        # jQuery UI stamps data-month (0-based) and data-year on every day <td>: the calendar
        # saying what it is actually showing, in a form that cannot disagree with itself.
        try:
            st = page.evaluate(
                "(s)=>{const d=document.querySelector(s);"
                " if(!d||d.offsetParent===null) return null;"
                " const td=d.querySelector('td[data-month][data-year]');"
                " if(!td) return null;"
                " return {mi: parseInt(td.getAttribute('data-month'),10)+1,"
                "         y:  parseInt(td.getAttribute('data-year'),10)};}", div)
        except Exception:
            st = None
        if not st:
            continue                      # it closed again; open_picker() will reopen it
        if (st["y"], st["mi"]) == (y, m):
            break
        arrow = f"{div} a.ui-datepicker-{'prev' if (st['y'], st['mi']) > (y, m) else 'next'}"
        if not C.human_click(page, arrow, timeout=4000):
            note(f"    [warn] datepicker arrow did not take (showing {st['mi']:02d}/{st['y']})")
            return False
        page.wait_for_timeout(random.randint(180, 380))
    else:
        note(f"    [warn] {max_hops} hops and never reached {m:02d}/{y}")
        return False

    # Scope the day to ITS OWN month cell. Filtering day links by text alone would happily match
    # a day from an adjacent month's trailing week.
    C.human_click(page, page.locator(f"{div} td[data-month='{m - 1}'][data-year='{y}'] a")
                  .filter(has_text=re.compile(rf"^{d}$")).first, timeout=5000)
    page.wait_for_timeout(500)
    got = page.eval_on_selector(sel, "e=>e.value")
    if got != value:
        note(f"    [warn] {sel} reads {got!r}, wanted {value!r}")
        return False
    return True


def build_form_mouse(page, settler, desde, hasta):
    """The search form, with no keyboard at all."""
    C.open_fecha_panel(page)
    if page.eval_on_selector("#fecCompetencia", "e=>e.value") != A.CIVIL:
        note("Competencia = Civil (mouse)")
        if not set_select_mouse(page, "#fecCompetencia", A.CIVIL):
            return None
        ojv.click_away(page)
        settler.wait(need="document.querySelectorAll('#fecTribunal option').length>50",
                     quiet_ms=1200, timeout=60, label="all-tribunales")
    corte = page.eval_on_selector("#corteFec", "e=>e.value")
    if corte not in ("", "0"):
        raise SystemExit(f"corte={corte}, expected Todos — refusing to touch it")
    for sel, val in (("#fecDesde", desde), ("#fecHasta", hasta)):
        if val is None:
            continue                  # --use-form-dates: whatever it already shows, untouched
        if page.eval_on_selector(sel, "e=>e.value") != val:
            if not pick_date_mouse(page, sel, val):
                raise SystemExit(f"could not set {sel} with the mouse — refusing to type it, "
                                 f"zero keystrokes is what this prototype is testing")
            ojv.click_away(page)
        got = page.eval_on_selector(sel, "e=>e.value")
        if got != val:
            raise SystemExit(f"{sel} reads {got!r}, expected {val!r} — refusing to search")
    for sel in ("#fecDesde", "#fecHasta"):
        # ⚠️ THE FORM STARTS EMPTY. Measured 2026-08-16: a fresh session shows NO dates at all,
        # and worker A never noticed because it types them every time. An empty window searches
        # instantly, returns zero rows, and reports 'results' — a clean-looking answer to a
        # question nobody asked.
        if not page.eval_on_selector(sel, "e=>e.value"):
            raise SystemExit(f"{sel} is EMPTY — refusing to search a window that was never set")
    lst = page.eval_on_selector_all("#fecTribunal option",
                                    "e=>e.filter(o=>o.value&&o.value!=='0')"
                                    ".map(o=>({v:o.value,t:(o.textContent||'').trim()}))")
    note(f"form ready, zero keystrokes: {len(lst)} tribunales, "
         f"{page.eval_on_selector('#fecDesde','e=>e.value')}.."
         f"{page.eval_on_selector('#fecHasta','e=>e.value')}")
    return lst


def fill_targets(desde, hasta, limit=0):
    """Causas we ALREADY hold that still have no cuaderno-2 rows. (todo, n) where todo is
    {tribunal_id: {rol: causa_id}}.

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
    sql = """select c.causa_id, c.rol, c.tribunal_id, c.etapa
             from causas c
             where c.f_ingreso between %s and %s
               and c.rol like 'C-%%'
               and not exists (select 1 from cuadernos q
                               where q.causa_id = c.causa_id and q.cuaderno ilike '2%%')
             order by c.tribunal_id, c.rol"""
    todo, n = {}, 0
    with conn.cursor() as k:
        k.execute(sql, (desde, hasta))
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


def harvest(page, pres, causa_id, row, trib_id="", trib_name="", only_proc=""):
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
    t_open = time.time()
    C.human_click(page, page.locator("#dtaTableDetalleFecha tbody tr").nth(row["i"])
                  .locator("a[onclick*='detalleCausaCivil']").first, timeout=8000)

    # The two seconds a causa takes to load are spent MOVING, like a person waiting for it.
    pres.aim(page, "#dtaTableDetalleFecha")     # where the hand is while the causa loads
    got = pres.run(90.0, poll=lambda: page.evaluate(
        "(rol)=>{const m=document.querySelector('#modalDetalleCivil');"
        "return !!m && m.innerText.indexOf(rol)>=0;}", row["rol"]), poll_every=0.35)
    if not got:
        note(f"    modal did not open after {time.time()-t_open:.0f}s")
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
    ap.add_argument("--gate", choices=("file", "none"), default="file",
                    help="serialise ARRIVALS through a lock file so concurrent workers never open "
                         "fresh browsers in the same instant. Released on the first confirmed "
                         "search, never on merely reaching the form.")
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
    a = ap.parse_args()

    if not a.use_form_dates:
        for label, val in (("--desde", a.desde), ("--hasta", a.hasta)):
            if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", val):
                raise SystemExit(f"{label}={val!r} is not dd/mm/yyyy")

    ojv.ENTRY_ROUTE = a.entry_route
    global RAMP_EVERY, RAMP_STEP, SPEED
    RAMP_EVERY, RAMP_STEP = a.ramp_every, a.ramp_step
    SPEED = a.speed
    if SPEED != 1.0:
        note(f"reading times fixed at x{SPEED} of the operator's"
             + ("  (TOP SPEED: only the site and the pointer are left)" if SPEED <= 0.01 else ""))
    if RAMP_EVERY:
        note(f"SPEED RAMP: x{RAMP_STEP} on the reading times every {RAMP_EVERY} opens")
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
        if a.gate != "none":
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
        note(f"in: {p.url[:70]}")
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
            raise SystemExit("not the national tribunal list — aborting")

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
            todo, n_todo = fill_targets(iso(a.desde), iso(a.hasta), a.max_causas)
            targets = [t for t in lst if t["v"] in todo]
            note(f"fill: {n_todo} causas need cuaderno 2, across {len(todo)} tribunales "
                 f"({len(targets)} of them selectable in this form)")
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

        stop = ""
        consec_select_fail = consec_bad_search = 0
        skipped = []
        for ti, t in enumerate(targets):
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
                         f"is wedged, not the courts. Stopping; {len(targets) - ti - 1} courts "
                         f"in this range were never searched.")
                    stop = "select-failures (form wedged)"
                    break
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
                         f"spent. Stopping rather than walking the range recording empties.")
                    stop = f"searches-not-confirming ({kind})"
                    break
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
                                  only_proc=a.only_proc)
                tally["opens"] += 1
                court["opens"] += 1
                if rec is None:
                    # ⚠️ NOT automatically the wall. A local session produced this exact signature
                    # on 2026-08-16 because WE clicked the next row while the previous modal's
                    # backdrop was still up. Say what the page is before concluding anything.
                    note(f"  modal never opened — where={ojv.locate(p)} "
                         f"blocked={ojv.blocked(p, net)}")
                    stop = "modal-never-opened"
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
                if RAMP_EVERY and tally["opens"] % RAMP_EVERY == 0:
                    globals()["SPEED"] = SPEED * RAMP_STEP
                    rung = {"opens": tally["opens"], "speed": round(SPEED, 3),
                           "opens_per_min": round(tally["opens"] / max(0.01, (time.time() - t_start) / 60), 2)}
                    state.setdefault("rungs", []).append(rung)
                    note(f"  === RAMP: reading times now x{SPEED:.2f} of the operator's "
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
                                  only_proc=a.only_proc)
                    tally["opens"] += 1
                    court["opens"] += 1
                    if rec is None:
                        note(f"  modal never opened — where={ojv.locate(p)} "
                             f"blocked={ojv.blocked(p, net)}")
                        stop = "modal-never-opened"
                        break
                    got.append(rec)
                    tally["gated" if rec.get("skipped_etapa") or rec.get("skipped_proc")
                          else "kept"] += 1
                    want.pop(row["rol"], None)
                    out_file.write_text(json.dumps(got, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
                    save_state()
                    read(pres, p, READ_LIST, "#dtaTableDetalleFecha")
                if stop:
                    break
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
        note(f"DONE in {el:.1f} min — {stop or 'finished'} | courts={tally['courts']} "
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
    main()
