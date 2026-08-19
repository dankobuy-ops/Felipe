"""HUMAN ENGINE — the SPECS. One implementation, shared by every worker.

⚠️⚠️ THE SPLIT THIS FILE EXISTS TO ENFORCE (operator, 2026-08-19):

      SPECS    how human the worker is.  ALWAYS THE BEST WE HAVE.  <- this file
      SETTINGS what job it does, over what window, at what speed.  <- the workers

There is exactly one reason this file exists: for months there were four workers and therefore
FOUR behavioural engines, and they were not equal. Worker H was rebuilt in August from a RECORDED
human session; A, B and C were not. On 2026-08-19 the difference was still this stark:

    | worker | dates                  | selects  | pointer presence | sideways scroll |
    | A      | types into `readonly`  | keyboard | NONE             | NONE            |
    | B      | types into `readonly`  | keyboard | NONE             | NONE            |
    | C      | types into `readonly`  | keyboard | NONE             | NONE            |
    | H      | mouse picker           | mouse    | 19 call sites    | yes             |

`type_date_kbd` deletes the `readOnly` property, types, and presses Escape — a sequence NO USER
CAN PRODUCE — on the form where the session token is minted. Three of four workers still did that
while the fourth was documented as the reason we stopped getting blocked. And the August catch-up
ran its DISCOVERY pass on the least human worker we owned.

⇒ Nothing behavioural may live in a worker again. A worker chooses WHAT to collect and WHERE; how
it moves, types, waits and clicks comes from here.

⚠️ THE OPTIMUM IS NOT THE MAXIMUM. The target is the recorded human's DISTRIBUTION, not more of
everything: a pointer emitting 40 moves/s is as anomalous as one emitting 0, just in the other
direction. The measured human is 25.8 mousemove/s and 6.4 mouseover/s inside the modal; we reach
~16/s, capped by CDP round-trip cost on a heavy page (raising the target from 34 to 52 moved the
achieved rate not at all). Under is the direction to fix — but there is a ceiling above which
more is worse, and no spec here should be "turned up" without a recording to justify it.

⚠️ EVERY NUMBER IN THIS FILE RESTS ON n=1. One operator, one 6.5-minute session, 15 causas
(`data/human/session-20260816-212249.jsonl`). It is the best evidence this project has and it is
still one person on one evening. The search wait is literally unmeasurable from it — they searched
exactly once. Treat these as the best current estimate, not as settled constants.

⚠️ TWO KINDS OF WAIT, AND CONFLATING THEM COST REAL DATA:

      wait for the SITE to answer   driven by the server   -> a CONDITION, never a duration
      wait because a HUMAN is slow  driven by the person   -> a DURATION, from a distribution

Stripping "padding" once removed the pause after the cuaderno switch, so the historia was parsed
before the AJAX had re-rendered it and causas were banked with an empty book 2 while the switch
itself had succeeded. Silent data loss, from an over-applied rule. `read()` is the second kind;
`Presence.run(..., poll=...)` is the first; both keep the pointer alive throughout.
"""
import random
import re
import time

import cdp_scrape as C
import ojv
from ojv import note

# ⚠️ NOT `import worker_a`. The engine must not depend on a worker — that is the whole
# point of the split, and the import would be circular the moment worker A uses the
# engine. CIVIL is a property of the SITE (competencia 3), so it lives with the site.
CIVIL = "3"

# ────────────────────────────────────────────────────────────────────────────
# Measured reading times, and the speed ramp
# ────────────────────────────────────────────────────────────────────────────
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
    # ⚠️ WAIT FOR THE PAGE TO BE IDLE FIRST. select_option waits for the control to be
    # ACTIONABLE, and a select the site has disabled while a request is in flight is not — so a
    # busy page turns into "8000ms exceeded" and then into "the form is wedged". Asking page_busy
    # first costs nothing and removes the commonest cause of that verdict.
    try:
        t0 = time.time()
        while C.page_busy(page) and time.time() - t0 < 15.0:
            page.wait_for_timeout(400)
    except Exception:
        pass
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
                # ⚠️ SAY WHY, NOT JUST THAT. "wedged form" was my LABEL for "select_option timed
                # out", and a worker burned all three recoveries against it while I could not name
                # the cause — each re-entry rebuilt the form perfectly and it re-wedged inside two
                # minutes, which already tells us the session was never the problem. Ask the page.
                try:
                    d = page.evaluate(
                        "(s)=>{const e=document.querySelector(s);"
                        " return e ? {opts:e.options.length, disabled:e.disabled,"
                        "  ro:e.hasAttribute('readonly'), vis:!!(e.offsetWidth||e.offsetHeight),"
                        "  pe:getComputedStyle(e).pointerEvents,"
                        "  spinners:[...document.querySelectorAll('[id^=loadPre]')]"
                        "    .filter(x=>x.innerHTML.trim()).map(x=>x.id),"
                        "  sheets:document.querySelectorAll('.jquery-loading-modal,"
                        "    .modal-backdrop').length} : null;}", sel)
                except Exception:
                    d = None
                cov = None
                try:
                    cov = ojv.blocking_overlay(page, sel)
                except Exception:
                    pass
                note(f"      [why] busy={C.page_busy(page)} select={d} covered_by={cov} "
                     f"where={ojv.locate(page)}")
                C.shot(page, f"select-stuck-{sel.strip('#')}", {"select": d, "covered_by": str(cov)})
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

    # ⚠️ DRAWN IS NOT SELECTABLE. jQuery UI still renders every day of the month; the ones the
    # site refuses become <td class="ui-datepicker-unselectable ui-state-disabled"> holding a
    # SPAN instead of an <a>. The OJV disables every day AFTER TODAY, so `--hasta 31/08/2026`
    # asked on the 18th clicks nothing whatsoever: the locator resolves to zero elements,
    # human_click falls through, and the field is left empty. A cloud runner and a local worker
    # died at exactly this cell on 2026-08-18, minutes apart, and the only log line either
    # produced was `#fecHasta reads ''`.
    # ⚠️ AND IT OVERTURNS AN EARLIER NOTE. "16 day links means the site blocks future dates" was
    # struck once because the picker plainly renders all 31 — it renders 31 and DISABLES the
    # future ones. Count the anchors, not the cells.
    cell = page.evaluate(
        "(a)=>{const [s,mm,yy,dd]=a; const d=document.querySelector(s); if(!d) return null;"
        " const td=[...d.querySelectorAll(`td[data-month='${mm}'][data-year='${yy}']`)]"
        "   .find(t=>t.textContent.trim()===String(dd));"
        " const en=[...d.querySelectorAll('td[data-month] a')].map(x=>x.textContent.trim());"
        " if(!td) return {missing:true, last: en.length?en[en.length-1]:null};"
        " const cl=td.className||'';"
        " return {disabled: cl.includes('disabled')||cl.includes('unselectable')"
        "                   || !td.querySelector('a'),"
        "         last: en.length?en[en.length-1]:null};}",
        [div, m - 1, y, d])
    if cell and cell.get("missing"):
        note(f"    [warn] {m:02d}/{y} has no cell for day {d}")
        return False
    if cell and cell.get("disabled"):
        note(f"    [warn] the OJV DISABLES {d:02d}/{m:02d}/{y} in the picker — the cell is drawn "
             f"but has no link. Last selectable day shown: {cell.get('last')}. "
             f"The site does not accept a date in the future.")
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
    if page.eval_on_selector("#fecCompetencia", "e=>e.value") != CIVIL:
        note("Competencia = Civil (mouse)")
        if not set_select_mouse(page, "#fecCompetencia", CIVIL):
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
