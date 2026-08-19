"""Attach to an ALREADY-RUNNING Chrome (debug port) and scrape OJV with REAL clicks (CDP).

The operator has, in that Chrome: passed the CAPTCHA, opened "Busqueda por Fecha", and set
Competencia=Civil + Corte + Fechas (Tribunales list showing). This connects over CDP and,
using trusted clicks (page.click -> isTrusted=true), walks every tribunal of the corte,
paginates the results, and opens each bank C-causa to scrape the full detail:
header, litigantes, all cuadernos + historia rows (incl. doc/anexo links + georref text),
escritos, and receptor. Writes ONE JSON to Downloads. Human, randomized pacing throughout.

Run:  python cdp_scrape.py [--port 9333] [--max-tribs 0] [--max-causas 0] [--proc ""]
      (0 = no limit)  --proc "Ejecutivo Obligación de Dar" filters by procedimiento.
"""

import argparse
import base64
import contextlib
import json
import math
import os
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

DOWNLOADS = Path(os.environ.get("USERPROFILE", ".")) / "Downloads"
OJV = "https://oficinajudicialvirtual.pjud.cl"

DOCS = False    # --docs: download historia doc/anexo PDFs and upload to Drive
DOCS_INPAGE = False  # --docs-inpage: fetch those PDFs from INSIDE the page (see fetch_doc)
GPS = False     # --gps: resolve georreferencia sub-modals to lat/lng
RESUME = False  # --resume: skip causas already scraped (fill_status='scraped') in Neon
COUNT_ONLY = False  # --count-only: count bank C-causas per tribunal, no detail opens
_STORE = None   # dbstore.Store (Drive uploads + Neon), lazy-initialised

# ── what we ALREADY have (worker C only) ─────────────────────────────────────
# A refresh must not re-buy a document it already stored: on a finished causa that would be 40+
# needless fetches, which is the whole session budget spent learning nothing. Worker C fills these
# from Neon before each open; worker A and worker B leave them None and behave exactly as before.
#
# ⚠️ KNOWN_GEO CARRIES THE STORED VALUE, it does not merely suppress the lookup. ingest_cdp emits a
# Cuadernos row for EVERY historia row, georref included, and that write is an upsert — so a row
# whose geo we skipped would go back with georref='' and BLANK a coordinate we already own. The
# same shape as the upsert that nearly wiped tribunales.corte. Skipping work must never mean
# forgetting the answer.
KNOWN_DOCS = None    # set of "<causa>-c<n>-<folio>-<k>-doc" / "-anexo" ids already in Neon
KNOWN_GEO = None     # {"<causa>-c<n>-<folio>-<k>": stored georref} — carried through untouched
KNOWN_HEADER = None  # set of header keys ("texto_demanda"/"certificado"/"ebook") already stored

BANK = ['SANTANDER', 'ESTADO DE CHILE', 'BANCOESTADO', 'BANCO DEL ESTADO', 'ITAU',
        'SCOTIABANK', 'BANCO INTERNACIONAL', 'CREDITO E INVERSIONES', 'BCI',
        'BANCO DE CHILE', 'FALABELLA', 'COOPEUCH', 'BICE', 'CONSORCIO', 'RIPLEY', 'BTG']

# ── pacing (human, randomized) — GENTLE: OJV rate-throttles even trusted CDP traffic,
#    so keep it slow (in the ballpark of run.py's gentle discovery mode). ────────────
P_CAUSA = (5.0, 10.0)   # before opening each causa
P_PAGE  = (4.0, 8.0)    # between result pages
P_TRIB  = (6.0, 12.0)   # between tribunales
P_STEP  = (0.6, 1.6)    # small pauses inside a causa (cuaderno switches, receptor)


PACE_MULT = 1.0  # --pace: scales every pause below. See the note in main()'s --pace help.


def pace(rng):
    time.sleep(random.uniform(*rng) * PACE_MULT)


def _human_pointer(page, x, y, press=True):
    """Drive the pointer to (x,y) along an ARC with easing and jitter, dwell, then (optionally)
    press. press=False is a MOVE only — use it for warm-up/hover, never for clicking. (A warm-up
    that left press=True clicked at random coordinates all over the page and opened stray tabs,
    2026-07-23.)"""
    sx, sy = x - random.uniform(180, 320), y + random.uniform(90, 200)
    page.mouse.move(sx, sy)
    page.wait_for_timeout(random.randint(60, 140))
    steps = random.randint(18, 28)
    bow = random.uniform(-38, 38)                        # perpendicular bulge -> a curve
    for i in range(1, steps + 1):
        t = i / steps
        ease = t * t * (3 - 2 * t)                       # slow start, fast middle, slow end
        arc = math.sin(math.pi * t) * bow
        page.mouse.move(sx + (x - sx) * ease + arc + random.uniform(-1.2, 1.2),
                        sy + (y - sy) * ease + random.uniform(-1.2, 1.2))
        page.wait_for_timeout(random.randint(8, 22))
    page.mouse.move(x + random.uniform(-1.5, 1.5), y + random.uniform(-1.5, 1.5))
    page.wait_for_timeout(random.randint(140, 380))      # hover dwell before committing
    if not press:
        return
    page.mouse.down()
    page.wait_for_timeout(random.randint(55, 130))       # press duration
    page.mouse.up()


def page_busy(page):
    """True while the site is mid-request. It injects a spinner into #loadPre* (empty when
    idle) — the loading icon the operator watches on screen. Judging 'ready' by the results
    table is useless: it keeps showing the PREVIOUS search's rows while the new one runs.

    ⚠️ The #loadPre* spinner is NOT the only overlay. The site also throws a
    `.jquery-loading-modal__bg` sheet across the page, and page_busy knew nothing about it — so
    while it was up this returned "idle", the code went ahead and clicked, and human_click
    correctly refused every target as covered. That cascade ("objetivo tapado" over and over,
    causas never opening, searches never proving fresh) is the SILENT THROTTLE of 2026-08-07/08:
    not the WAF at all, our own blindness to one div.
    """
    try:
        return bool(page.evaluate(
            "()=>{const pre=['loadPre','loadPreFecha','loadPreNombre','loadPreJuridica']"
            "  .some(id=>{const e=document.getElementById(id);"
            "   return e && e.offsetParent!==null && e.innerHTML.trim().length>0;});"
            # offsetParent is NULL for position:fixed, and this overlay IS fixed — testing
            # visibility that way is why the first attempt at this fix saw nothing at all.
            " const vis=e=>{const r=e.getBoundingClientRect();const s=getComputedStyle(e);"
            "   return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';};"
            " const ov=[...document.querySelectorAll("
            "   '.jquery-loading-modal__bg,.jquery-loading-modal')].some(vis);"
            " return pre||ov;}"))
    except Exception:
        return False


def clear_stuck_spinner(page):
    """Empty the site's own #loadPre* spinner when it has been abandoned. Returns what it cleared.

    ⚠️ ONLY call this with nothing in flight. The spinner is how the site says "I am working", so
    clearing it while a request really is running would fake readiness — the exact mistake this
    codebase has made in three other forms. `ojv.wait_results` guards it on S.inflight == 0 plus a
    dwell, so by the time we get here the div is orphaned, not busy.

    Observed 2026-08-09: #loadPreFecha left visible with 67 bytes of spinner markup after a search
    that never completed. page_busy stayed True for ever, every search burned the full 3x hard cap
    and came back STALE, and six recoveries were spent on a session that was in fact fine.
    """
    try:
        return page.evaluate(
            "()=>{const ids=['loadPre','loadPreFecha','loadPreNombre','loadPreJuridica'];"
            " const hit=[];"
            " ids.forEach(id=>{const e=document.getElementById(id);"
            "   if(e && e.innerHTML.trim().length){hit.push(id); e.innerHTML='';}});"
            " return hit;}") or []
    except Exception:
        return []


def wait_idle(page, secs=20):
    """Block until the site stops loading. Acting while it is busy is what got workers 2 and 3
    F5-blocked on 2026-07-22: under three-worker latency the script clicked before the page was
    ready, the click landed on a backdrop or a stale row, and Shape scored the impossible
    interaction. Cheap insurance — returns as soon as the spinner clears."""
    for _ in range(secs * 4):
        if not page_busy(page):
            return True
        page.wait_for_timeout(250)
    return False


def human_scroll(page, notches=None, down=True, settle=True):
    """Scroll the page the way a person reads it: a few wheel notches, uneven, with pauses.

    ⚠️ WE NEVER SCROLLED. Not once, in any worker. The DOM is read directly, so a results table of
    179 rows was parsed without a single wheel event — and F5 Shape collects wheel telemetry
    exactly as it collects pointer motion and keystroke timing. Uniform input is suspicious;
    input that is entirely ABSENT is worse, because no human can read a long table without it.
    Operator's observation 2026-08-10, and the same class of gap as the metronome keyboard.

    Deltas vary, the gaps vary, and roughly a third of the time there is a small correction
    upwards — the overshoot people make when they scroll past what they wanted.

    ⚠️ PARK THE POINTER OVER THE CONTENT FIRST, or the wheel telemetry is only half the story.
    Operator's observation 2026-08-14: a person scrolling a results list holds the pointer still
    in SCREEN space while the page moves underneath, so row after row passes beneath the cursor
    and fires mouseover/mouseout. Playwright's virtual mouse starts at (0,0), so wheeling without
    positioning scrolls from the top-left corner — a place no hand ever rests — and touches
    nothing. MEASURED on a live causa, same wheel events both ways:

        pointer not positioned   ->   0 mouseover,  0 mouseout,  0 rows
        pointer over the table   ->  12 mouseover, 12 mouseout,  2 rows

    An empty channel is the same class of tell as never scrolling at all, which is the bug this
    function was written to fix. One mouse.move() closes it, and it costs nothing.
    """
    try:
        n = notches if notches is not None else random.randint(3, 7)
        # Somewhere a reader's pointer would plausibly be: over the main table, off-centre.
        try:
            # ⚠️ CLAMP TO THE VIEWPORT. A physical pointer cannot leave the window — the OS stops
            # it at the edge — so a mouse.move() to a negative or past-the-edge coordinate is
            # something no human can produce, on a site that scores exactly this. A table scrolled
            # above the fold has a NEGATIVE getBoundingClientRect().top, and the first version of
            # this code fed that straight to mouse.move(). Clamp with a margin so the pointer
            # always sits somewhere a hand could actually put it.
            spot = page.evaluate(
                """() => {
                    const el = document.querySelector('#historiaCiv table')
                           || document.querySelector('#dtaTableDetalleFecha')
                           || document.querySelector('table');
                    const r = el ? el.getBoundingClientRect() : null;
                    const cl = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
                    if (!r || r.width < 40 || r.height < 40) {
                        return {x: innerWidth * (0.35 + Math.random() * 0.3),
                                y: innerHeight * (0.35 + Math.random() * 0.3)};
                    }
                    return {x: cl(r.left + r.width * (0.25 + Math.random() * 0.5), 8, innerWidth - 8),
                            y: cl(r.top + Math.min(r.height * 0.5, 120 + Math.random() * 220),
                                  8, innerHeight - 8)};
                }""")
            vw, vh = page.evaluate("() => [innerWidth, innerHeight]")
            if spot:
                page.mouse.move(spot["x"], spot["y"])
                page.wait_for_timeout(random.randint(80, 200))
        except Exception:
            spot, vw, vh = None, 1440, 900
        for i in range(n):
            dy = random.uniform(90, 340) * (1 if down else -1)
            page.mouse.wheel(0, dy)
            page.wait_for_timeout(random.uniform(70, 260))
            # A hand resting on a mouse is never perfectly still between notches.
            if spot and random.random() < 0.5:
                # Drift, but never off the window: unbounded accumulation over many notches walks
                # the pointer out of the viewport for the same impossible-position reason.
                spot["x"] = min(max(spot["x"] + random.uniform(-9, 9), 8), vw - 8)
                spot["y"] = min(max(spot["y"] + random.uniform(-7, 7), 8), vh - 8)
                page.mouse.move(spot["x"], spot["y"])
            if random.random() < 0.3:                 # overshoot, then correct
                page.mouse.wheel(0, -dy * random.uniform(0.15, 0.4))
                page.wait_for_timeout(random.uniform(90, 300))
        if settle:
            page.wait_for_timeout(random.uniform(150, 500))
    except Exception:
        pass                                          # scrolling must never break a run


IDLE_MOTION = False      # --idle-motion: hand-jitter during the waits. TESTED, BOUGHT NOTHING.
# Called as HOOK(page) roughly once a second during the pacing waits. live_view installs its
# frame grabber here, because the waits are most of a worker's wall clock and are where a hang
# looks identical to healthy patience. Left None the idling below is byte-for-byte what it was —
# deliberately, so nobody watching a run changes its timing without meaning to.
IDLE_HOOK = None


def human_idle(page, secs):
    """Wait `secs`, emitting the small pointer drift a resting hand cannot help producing.

    ★ TESTED 2026-08-14, AND IT MADE NO DIFFERENCE. Two runner arms, same window, same range, same
    pacing, one variable: with and without --idle-motion. Both blocked at EXACTLY 10 causa opens,
    on the SAME causa (2-C-1251-2026), with the same rejF=2 hardRej=1 signature and the same failed
    recovery. Whatever ends those sessions, idle pointer motion does not touch it.

    Kept, off by default, because a negative result that is deleted gets rebuilt — and this one is
    worth remembering next to its sibling, which WAS real: scrolling from (0,0) produced 0
    mouseover events where a positioned pointer produced 12, measured directly rather than inferred
    from an outcome. The difference between the two is the lesson. Hover-on-scroll was a channel
    proven empty by counting events; idle jitter was a plausible story about a channel, and
    plausible stories about this site have been wrong more often than right.

    Do NOT re-run this experiment without a reason the 08-14 pair does not already cover.

    The reasoning it is testing: `mouse.wheel()` dispatches NO mousemove, and we never move the
    pointer except to click. So between actions our pointer is perfectly, inhumanly still for
    20-25 s at a stretch, while a real hand resting on a mouse emits continuous low-amplitude
    motion. Hover-on-scroll was the same shape of gap and was real (measured 0 vs 12 events).

    Falls back to a plain sleep on any error: idling must never break a run.
    """
    if not IDLE_MOTION or secs <= 0:
        _plain_idle(page, max(0.0, secs))
        return
    end = time.time() + secs
    try:
        pos = page.evaluate("() => ({x: innerWidth * 0.45, y: innerHeight * 0.5})")
        x, y = pos["x"], pos["y"]
        while time.time() < end:
            time.sleep(min(random.uniform(0.8, 2.6), max(0.0, end - time.time())))
            _idle_hook(page)
            if time.time() >= end:
                break
            # A few pixels, a couple of steps — this is a hand resting, not a hand travelling.
            for _ in range(random.randint(1, 3)):
                x += random.uniform(-6, 6)
                y += random.uniform(-5, 5)
                page.mouse.move(x, y)
                page.wait_for_timeout(random.randint(15, 60))
    except Exception:
        left = end - time.time()
        if left > 0:
            _plain_idle(page, left)


def _idle_hook(page):
    """Run the watcher's hook, and never let it cost the caller anything. A live view that could
    raise would be a spectator able to stop the game."""
    if IDLE_HOOK is None:
        return
    try:
        IDLE_HOOK(page)
    except Exception:
        pass


def _plain_idle(page, secs):
    """Wait, in slices, so a watcher gets a look in. With no hook installed this is one sleep —
    the same single call it has always been."""
    if secs <= 0:
        return
    if IDLE_HOOK is None:
        time.sleep(secs)
        return
    end = time.time() + secs
    while True:
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(1.0, left))
        _idle_hook(page)


SHOTS = None            # directory for failure screenshots; set by a worker via --shots
_shot_n = [0]


def shot(page, tag, extra=None):
    """Screenshot + page state at a failure, so a RUNNER can be looked at afterwards.

    ⚠️ A CLOUD RUNNER HAS NO SCREEN, and today every remote diagnosis was made by reading log text
    and guessing at the picture behind it. `entry button covered (top: TSBrPFrame_cs_chlg...)` is
    a good line, but a screenshot of that page settles in one look what the words argue about —
    exactly as the operator's screenshot of the AVISO did, after three of my DOM probes had
    reported the wrong thing.

    Cheap and bounded: only called on failure paths. Writes <NNN>-<tag>.png beside a .json of the
    page's own account of itself. Never raises — a diagnostic must not become the incident.
    """
    if not SHOTS:
        return
    try:
        from pathlib import Path as _P
        _shot_n[0] += 1
        base = _P(SHOTS) / f"{_shot_n[0]:03d}-{tag}"
        base.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(base) + ".png", full_page=False, timeout=8000)
        st = page.evaluate(
            "()=>({url:location.href, title:document.title,"
            " vw:innerWidth, vh:innerHeight, sx:Math.round(scrollX), sy:Math.round(scrollY),"
            " body:(document.body?document.body.innerText:'').slice(0,1500),"
            " frames:[...document.querySelectorAll('iframe')].map(f=>f.id||f.name||''),"
            " modals:[...document.querySelectorAll('.modal.show,.modal.in')].map(m=>m.id),"
            " sheets:document.querySelectorAll('.modal-backdrop,.jquery-loading-modal').length})")
        if extra:
            st["extra"] = extra
        import json as _j
        _P(str(base) + ".json").write_text(_j.dumps(st, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
        print(f"      [shot] {base.name}.png  url={st['url'][:60]} frames={st['frames'][:3]}")
    except Exception as e:
        print(f"      [warn] shot {tag}: {str(e)[:60]}")


# ── STEP TRACE ─────────────────────────────────────────────────────────────────────────────
# A frame before and after every action, for a session nobody can watch.
#
# ⚠️ `shot()` above fires on FAILURE, which tells you where a run ended and nothing about how it
# got there. Both August runners died with `click delivered: True`, forty-five silent seconds, and
# then a rejection page — and no way to tell whether the block arrived at second 1 or second 40.
# The interesting frame is never the last one.
#
# JPEG at quality 50, not PNG: ninety frames of an entry sequence is ~6 MB this way and ~34 MB the
# other, and the whole point is that it comes back from a runner as an artifact somebody opens.
# One trace.jsonl beats one sidecar per frame for the same reason.
TRACE = 0               # frame budget; 0 = off
TRACE_SCOPE = "entry"   # "entry" = arrival only, "all" = every click, whole run
STEPPER = None          # stepgate.Stepper — set by a worker with --step; blocks before each action
# Which part of the run we are in, so `--trace entry` can mean the arrival and nothing else. The
# arrival is where every remote run has died, and it is ~30 frames; a whole shift is thousands.
PHASE = "entry"
_trace_n = [0]
_trace_t0 = [0.0]
_trace_last = [0.0]


def tracing(scope="entry"):
    """Is the trace on for this scope, and is there budget left? 'all' subsumes 'entry'."""
    return bool(SHOTS and TRACE and _trace_n[0] < TRACE
                and (TRACE_SCOPE == "all" or TRACE_SCOPE == scope))


def trace(page, tag, extra=None, scope="entry"):
    """One frame of the step trace. Never raises, never blocks for long, stops at the budget —
    a diagnostic that can end the run it is diagnosing is worse than no diagnostic."""
    if not tracing(scope):
        return
    try:
        from pathlib import Path as _P
        d = _P(SHOTS) / "trace"
        d.mkdir(parents=True, exist_ok=True)
        if not _trace_t0[0]:
            _trace_t0[0] = time.time()
        _trace_n[0] += 1
        n = _trace_n[0]
        name = f"{n:04d}-{re.sub(r'[^A-Za-z0-9._-]+', '-', tag)[:60]}.jpg"
        page.screenshot(path=str(d / name), full_page=False, timeout=6000,
                        type="jpeg", quality=50)
        st = page.evaluate(
            "()=>({url:location.href, title:document.title,"
            " sx:Math.round(scrollX), sy:Math.round(scrollY),"
            " text:(document.body?document.body.innerText:'').slice(0,300),"
            " frames:[...document.querySelectorAll('iframe')].map(f=>f.id||f.name||''),"
            " modals:[...document.querySelectorAll('.modal.show,.modal.in')].map(m=>m.id),"
            " sheets:document.querySelectorAll('.modal-backdrop,.jquery-loading-modal').length})")
        st.update(n=n, tag=tag, img=name, t=round(time.time() - _trace_t0[0], 2))
        if extra:
            st["extra"] = str(extra)[:400]
        with (d / "trace.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(st, ensure_ascii=False) + "\n")
        if n == TRACE:
            print(f"      [trace] frame budget {TRACE} reached — tracing stops here")
    except Exception as e:
        print(f"      [warn] trace {tag}: {str(e)[:60]}")


def trace_tick(page, tag, every=3.0, scope="entry"):
    """A frame at most every `every` seconds, for a polling loop that must keep polling.

    ⚠️ THE BLIND SPOT WAS FORTY-FIVE SECONDS LONG — ojv.walk_in polls find_form() that long after
    the guest-entry click, and on 2026-08-18 both runners spent the whole window unobserved. This
    puts a timestamp on the refusal without touching the loop's own cadence.
    """
    if not tracing(scope):
        return
    now = time.time()
    if now - _trace_last[0] < every:
        return
    _trace_last[0] = now
    trace(page, tag, scope=scope)


@contextlib.contextmanager
def step(page, label, extra=None, scope="entry"):
    """Frame before, ask permission, do it, frame after.

    The `after` frame is written from a `finally`, so an action that THREW still leaves a picture
    of what it left behind — which is the one frame you always want and never have.
    """
    trace(page, f"{label}--before", extra, scope)
    if STEPPER is not None and (TRACE_SCOPE == "all" or TRACE_SCOPE == scope):
        STEPPER.ask(page, label, extra)
    try:
        yield
    finally:
        trace(page, f"{label}--after", extra, scope)
        if STEPPER is not None and (TRACE_SCOPE == "all" or TRACE_SCOPE == scope):
            STEPPER.report(page, label, extra)


def human_scroll_x(page, dx, notches=None):
    """Scroll SIDEWAYS by roughly `dx` px, the way a person does it — a trackpad swipe or
    shift+wheel, in a few uneven notches with the pointer parked over the content.

    ⚠️ WE HAD NEVER SCROLLED HORIZONTALLY. Not once, in any worker. `mouse.wheel(0, dy)` — deltaX
    hard-zero everywhere — which meant anything past the right edge of the window was unreachable
    no matter how long we waited, and human_click refused it with "objetivo tapado" and no overlay
    to name. That is how a 1,115 px table in a 958 px viewport cost 1,224 causas: the magnifier
    column simply lived outside, and we treated a horizontal-scroll problem as a WAF verdict.
    It is also one more empty telemetry channel, the same family as never wheeling at all.

    ⇒ This is why the fix does NOT require a big window. A person with a narrow window scrolls
    across; so can we. Window size is then a preference (small windows are watchable), not a
    correctness requirement.
    """
    try:
        if abs(dx) < 8:
            return
        n = notches if notches is not None else random.randint(2, 4)
        try:
            spot = page.evaluate(
                """() => {const el = document.querySelector('#dtaTableDetalleFecha')
                        || document.querySelector('table') || document.body;
                   const r = el.getBoundingClientRect();
                   const cx = Math.min(Math.max(r.left + r.width * 0.4, 30), innerWidth - 30);
                   const cy = Math.min(Math.max(r.top + r.height * 0.35, 30), innerHeight - 30);
                   return {x: cx, y: cy};}""")
            page.mouse.move(spot["x"], spot["y"])
        except Exception:
            pass
        step = dx / n
        for i in range(n):
            page.mouse.wheel(step * random.uniform(0.8, 1.2), 0)
            page.wait_for_timeout(random.randint(90, 260))
        # the small correction back that a hand makes after overshooting
        if random.random() < 0.3:
            page.mouse.wheel(-step * random.uniform(0.1, 0.3), 0)
            page.wait_for_timeout(random.randint(80, 180))
    except Exception:
        pass


def human_scroll_to(page, el, timeout=8000):
    """Bring `el` into view the way a person does — with the WHEEL — and only fall back to the
    instant jump if the wheel could not get there.

    ⚠️ scroll_into_view_if_needed() IS A TELEPORT FOR THE PAGE. It fires a `scroll` event and
    NOTHING else: no wheel events, no pointer motion, no hover changes on the rows it passes. It
    ran before EVERY click, so filling the search form — click a field, jump, click the next,
    jump — produced a page that moved repeatedly with an entirely empty input channel. The
    operator spotted it watching the browser: a person does not scroll between filling one input
    and the next, and when they do scroll it is with the wheel.

    Same family as the two gaps already fixed here: "we never scrolled at all" and "we scrolled
    from (0,0)". This is the third — we scrolled without touching an input device. The form is
    also where the reCAPTCHA token is minted, so it is the worst place to look synthetic.
    """
    try:
        if el.is_visible() and page.evaluate(
                """(b) => b && b.y >= 0 && b.y + b.height <= innerHeight""", el.bounding_box()):
            return                                  # already in view: a person would not scroll
    except Exception:
        pass
    for _ in range(6):
        try:
            box = el.bounding_box()
            if not box:
                break
            vh = page.evaluate("() => innerHeight")
            centre = box["y"] + box["height"] / 2
            delta = centre - vh / 2
            if abs(delta) < vh * 0.35:              # close enough that a reader would stop
                break
            # One notch at a time, in the direction a hand would turn it.
            human_scroll(page, notches=1, down=delta > 0, settle=False)
        except Exception:
            break
    # ⚠️ ONLY AS A FALLBACK, WHICH IS WHAT THE COMMENT ALWAYS CLAIMED IT WAS. This ran
    # UNCONDITIONALLY, so after the wheel had placed the target comfortably mid-viewport,
    # scroll_into_view_if_needed re-scrolled it to MINIMUM visibility — flush against the top
    # edge, i.e. underneath the site's sticky navbar (`NAV#mainNav`, z-index 1030). human_click
    # then hit-tested the target, found the navbar on top, and refused to click. Intermittent by
    # nature: whether it lands under the header depends on where the page was already scrolled,
    # which is why one worker sailed through the same link another could not reach.
    # It is also a teleport for the page (see the docstring above), so not running it is a bonus.
    # ⚠️ AND SIDEWAYS. Vertical-only scrolling leaves anything past the right edge permanently
    # unreachable — which is exactly what happened to the results table's magnifier column in a
    # narrow window. Bring the target inside the viewport WIDTH the way a person does, then the
    # window can be any size the operator likes.
    try:
        b = el.bounding_box()
        vw = page.evaluate("() => innerWidth")
        if b and (b["x"] < 4 or b["x"] + b["width"] > vw - 4):
            # positive dx scrolls right (content moves left); aim the target at mid-viewport
            human_scroll_x(page, b["x"] + b["width"] / 2 - vw / 2)
    except Exception:
        pass
    try:
        b = el.bounding_box()
        vh = page.evaluate("() => innerHeight")
        vw = page.evaluate("() => innerWidth")
        if (b and 0 <= b["y"] and b["y"] + b["height"] <= vh
                and 0 <= b["x"] and b["x"] + b["width"] <= vw):
            return                                  # already fully in view; leave the page alone
    except Exception:
        pass
    try:
        el.scroll_into_view_if_needed(timeout=timeout)
        # ⚠️ ONLY NUDGE IF THE TARGET LANDED UNDER THE HEADER. This nudge exists because
        # scroll_into_view parks an element flush against the TOP edge, beneath the site's sticky
        # navbar. Applying it unconditionally is a regression in the other direction: an element
        # that landed at the BOTTOM edge gets pushed straight back out of the viewport, and
        # human_click then reports "covered_by=None" -- unhittable with nothing covering it,
        # because every candidate point is off-screen. That killed a worker at the datepicker
        # (2026-08-17), two hours after this nudge was added to fix the navbar.
        b = el.bounding_box()
        if b and b["y"] < 120:
            human_scroll(page, notches=1, down=False, settle=False)
    except Exception:
        pass


def _click_label(target):
    """A short, filesystem-safe name for whatever we are about to click."""
    try:
        s = target if isinstance(target, str) else (getattr(target, "_selector", None) or repr(target))
    except Exception:
        s = "element"
    s = re.sub(r"\s+", " ", str(s))
    # ⚠️ A Locator's repr is `<Locator frame=<Frame name= url='...'> selector='...'>`, so anything
    # anchored with [^>]* stops inside the FRAME and names the step after the URL we are on rather
    # than the thing we are clicking. Reach for the selector wherever it is.
    m = re.search(r"selector=['\"](.+?)['\"]\s*>?\s*$", s)
    if m:
        s = m.group(1)
    return re.sub(r"[^A-Za-z0-9._#\[\]=*-]+", "-", s).strip("-")[:48] or "element"


def human_click(page, target, timeout=8000, label=None):
    """THE click, with a picture either side of it when a trace is running.

    ⚠️ EVERY ACTION THIS SCRAPER TAKES COMES THROUGH HERE, which is why the trace hooks the
    wrapper rather than each of the forty call sites: one place to instrument, and no call site
    can be forgotten. The real work is `_human_click` below, unchanged.
    """
    if TRACE or STEPPER is not None:
        with step(page, f"click-{label or _click_label(target)}", scope=PHASE):
            return _human_click(page, target, timeout)
    return _human_click(page, target, timeout)


def _human_click(page, target, timeout=8000):
    """THE click. `target` is a selector, Locator or ElementHandle.

    NEVER use page.click()/locator.click() on this site. Both are isTrusted=true, but they
    TELEPORT the pointer onto the element and fire down+up with no approach path and no hover
    dwell — and F5 Shape scores the motion, not the trust bit. Validated 2026-07-22 on one
    healthy session, same button, same POST params, minutes apart:
        page.click  -> 250 B rejection page in 0.1s
        human arc   -> 109,234 B of real results
    Reading the DOM over CDP (Runtime.evaluate) was tested in the same session and is INNOCENT,
    so parse_*/eval_on_selector everywhere else are fine — it is only the pointer that matters.
    Falls back to a plain click if the element has no measurable box (better than not clicking).
    """
    el = page.locator(target) if isinstance(target, str) else target
    box = None
    # ⚠️ Wheel, not teleport — and it does NOTHING when the target is already in view, which is
    # the common case on the search form. See human_scroll_to.
    human_scroll_to(page, el, timeout=timeout)
    try:
        box = el.bounding_box()
    except Exception:
        box = None
    if not box or box.get("width", 0) < 1 or box.get("height", 0) < 1:
        try:
            el.click(timeout=timeout)                    # last resort — may be scored
            return True
        except Exception:
            return False

    # We drive raw mouse coordinates, so we lose Playwright's actionability check: if a
    # backdrop or sticky header covers the point, the press lands on the overlay instead.
    # Hit-test it ourselves (Runtime.evaluate is proven safe here) and re-measure if it misses.
    wait_idle(page)                                      # never act while the site is loading

    # NEVER click a covered target. The old fallback ("click anyway") sent a real click to
    # whatever sat underneath — a backdrop, a stale row — at coordinates where the intended
    # element was not. On 2026-07-22 that correlated perfectly with getting F5-blocked:
    # 0 covered clicks -> survived 50 causas; 1 -> blocked at 23; 2 -> blocked at 4.
    # ⚠️ LOOK FOR A POINT THAT WORKS; DO NOT SAMPLE ONE AND GIVE UP. This used to pick a single
    # random point in the middle 40% of the element and, if that point was covered, wait a second
    # and pick another from the same range — eight times. An element covered over PART of itself
    # then failed at random: on 2026-08-17 the OJV entry tile refused three whole entry attempts
    # because `.gallery-item-info`, the caption sitting over the lower half of the tile as a
    # SIBLING of the link, kept winning the coin toss. Partial cover is not cover.
    #
    # A person looking at that tile sees the caption over half of it and clicks the other half.
    # So: offer the browser a spread of candidate points and take the first one where OUR element
    # is genuinely on top. The rule that matters — never click where something else would receive
    # the click — is unchanged and is still decided by the hit-test, not by hope.
    CANDIDATES = [(0.5, 0.5), (0.5, 0.28), (0.3, 0.4), (0.7, 0.4), (0.5, 0.72),
                  (0.22, 0.5), (0.78, 0.5), (0.35, 0.7), (0.65, 0.7), (0.5, 0.15)]
    # ⚠️ AND ACCEPT A COVER THAT LEADS TO THE SAME PLACE. On www.pjud.cl each entry tile carries a
    # `.gallery-item-info` caption laid over it PERMANENTLY — "Sección que permite la revisión de
    # causas" is a panel on top of the tile, with the tile's own label faint beneath it. A person
    # looking at that page clicks the caption, because the caption is the thing they can see, and
    # it navigates. Our hit-test refused it for not being the anchor, and burned entry attempts on
    # a link that was never actually unreachable.
    #
    # This does NOT weaken the no-covered-click rule. That rule exists because clicking a covered
    # target sends a real click to something ELSE at coordinates where the intended element is not
    # — measured 2026-07-22: 0 covered clicks survived 50 causas, 1 blocked at 23, 2 at 4. If the
    # element on top resolves to the SAME destination (same anchor href/onclick), then clicking it
    # IS clicking us, and the objection does not apply. Anything else is still refused.
    HIT_JS = """(e, pts) => {
        const dest = (n) => {
            const a = n && n.closest ? n.closest('a') : null;
            if (!a) return null;
            return (a.getAttribute('href') || '') + '|' + (a.getAttribute('onclick') || '');
        };
        const mine = dest(e);
        const r = e.getBoundingClientRect();
        for (const pt of pts) {
            const x = r.left + r.width * pt[0], y = r.top + r.height * pt[1];
            if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
            const top = document.elementFromPoint(x, y);
            if (!top) continue;
            if (top === e || e.contains(top) || top.contains(e)) return [x, y];
            if (mine && mine !== '|' && dest(top) === mine) return [x, y];
        }
        return null;
    }"""
    x = y = None
    covered = False
    for attempt in range(8):
        # Centre first (what a person aims at), then a scatter, shuffled so we do not hammer the
        # same pixel of the same control on every visit.
        pts = [CANDIDATES[0]] + random.sample(CANDIDATES[1:], len(CANDIDATES) - 1)
        pts = [(fx + random.uniform(-0.04, 0.04), fy + random.uniform(-0.04, 0.04))
               for fx, fy in pts]
        try:
            hit = el.evaluate(HIT_JS, pts)
        except Exception:
            x = box["x"] + box["width"] * 0.5            # can't hit-test (iframe etc.) — go
            y = box["y"] + box["height"] * 0.5
            break
        if hit:
            x, y = hit
            covered = False
            break
        covered = True
        page.wait_for_timeout(1000)                      # give slow renders time to settle
        if attempt == 2:
            clear_stuck_modal(page)                      # usually a left-open modal's backdrop
            # ⚠️ AND ASK WHAT IS ACTUALLY ON TOP. ojv.clear_overlay() was written for exactly this
            # and then only wired into the entry button, so every OTHER covered target still
            # reported the bare word "covered" — which is the situation it was built to end.
            # Caught on 2026-08-14 by the paginator: two refusals, a court flagged INCOMPLETE at
            # 100/251 rows, and no idea what the Siguiente button was under.
            # Imported lazily: ojv imports this module, so a top-level import would be circular.
            try:
                import ojv as _ojv
                ok, why = _ojv.clear_overlay(page)
                if not ok and "nothing covering" not in why:
                    print(f"    [warn] human_click: {why}")
            except Exception:
                pass
        wait_idle(page)
        try:
            # ⚠️ NUDGE THE PAGE, or a target under a STICKY HEADER is unreachable for ever.
            # human_scroll_to now leaves an already-in-view element alone (correctly — it used to
            # teleport it under the navbar), which means a retry that only re-centres changes
            # nothing and all eight attempts see the identical covered pixel. One notch UP moves
            # the content DOWN, out from under a top-fixed bar: what a person does when a header
            # hides what they are reaching for. `NAV#mainNav` at z-index 1030 cost a whole entry.
            human_scroll(page, notches=1, down=False, settle=False)
            human_scroll_to(page, el, timeout=timeout)   # wheel here too — same reason
            box = el.bounding_box() or box
        except Exception:
            pass
    if covered:
        # ⚠️ SAY WHERE IT WAS. "objetivo tapado" is the single most expensive message in this
        # project: it refuses row clicks (3% of causas) AND Siguiente clicks (39% of courts, 1,224
        # causas unreached in one afternoon), and for months it named no cause. blocking_overlay
        # keeps reporting nothing on top, which means the target is not COVERED at all — it is
        # somewhere we cannot aim. Geometry answers that; the word never will.
        try:
            g = el.evaluate(
                "(e)=>{const r=e.getBoundingClientRect();"
                " const top=document.elementFromPoint("
                "   Math.min(Math.max(r.left+r.width/2,0),innerWidth-1),"
                "   Math.min(Math.max(r.top+r.height/2,0),innerHeight-1));"
                " return {x:Math.round(r.left), y:Math.round(r.top),"
                "  w:Math.round(r.width), h:Math.round(r.height),"
                "  vw:innerWidth, vh:innerHeight, sy:Math.round(scrollY),"
                "  inView: r.top>=0 && r.bottom<=innerHeight && r.left>=0 && r.right<=innerWidth,"
                "  zero: r.width===0||r.height===0,"
                "  top: top ? top.tagName+'.'+((top.className||'')+'').slice(0,24) : null};}")
        except Exception as e:
            g = f"(probe failed: {str(e)[:40]})"
        print(f"    [warn] human_click: objetivo tapado tras 8s — NO hago clic (evita el bloqueo)")
        print(f"      [geo] {g}")
        shot(page, "click-refused", {"geo": g})
        return False

    # ⚠️ DO NOT PRESS WHILE THE PAGE IS STILL MOVING. _human_pointer moves, then presses, then
    # releases. If the page is mid-scroll — and we now scroll on BOTH axes before clicking — the
    # element slides out from under the point between mousedown and mouseup, the click registers
    # on nothing, and no request is made. That is indistinguishable from the site ignoring us and
    # it is how `modal never opened` survives every other fix: right row, no refusal, zero
    # responses. Two reads of the box, 150 ms apart, cost nothing and remove the race.
    try:
        for _ in range(6):
            b1 = el.bounding_box()
            page.wait_for_timeout(150)
            b2 = el.bounding_box()
            if b1 and b2 and abs(b1["x"] - b2["x"]) < 2 and abs(b1["y"] - b2["y"]) < 2:
                if b2 != box:                      # it moved while we waited: re-aim
                    x = b2["x"] + b2["width"] * random.uniform(0.35, 0.65)
                    y = b2["y"] + b2["height"] * random.uniform(0.35, 0.65)
                break
    except Exception:
        pass
    try:
        _human_pointer(page, x, y)
        return True
    except Exception as e:
        print(f"    [warn] human_click: {str(e)[:60]}")
        return False


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).upper().strip()


def is_bank(caratulado):
    return any(f in norm(caratulado) for f in BANK)


def grab(blob, pat):
    m = re.search(pat + r"\s*([^\t\n]+)", blob, re.I)
    return m.group(1).strip() if m else ""


# ── parsers (ported from run.py) ─────────────────────────────────────────────

def parse_header(page):
    b = page.inner_text("#modalDetalleCivil")
    return {
        "f_ingreso":    grab(b, r"F\.\s*Ing\.?:"),
        "estado_adm":   grab(b, r"Est\.\s*Adm\.?:"),
        "procedimiento": grab(b, r"(?<!Estado )Proc\.?:"),
        "ubicacion":    grab(b, r"Ubicaci[oó]n:"),
        "estado_proc":  grab(b, r"Estado\s*Proc\.?:"),
        "etapa":        grab(b, r"Etapa:"),
    }


def parse_litigantes(page):
    return page.eval_on_selector_all(
        "#litigantesCiv table tbody tr",
        r"""els => els.map(tr => { const td = Array.from(tr.querySelectorAll('td'));
              const c = i => td[i] ? td[i].innerText.trim() : '';
              return {participante:c(0), rut:c(1), persona:c(2), nombre:c(3)}; })
            .filter(r => r.rut || r.nombre)""")


def parse_escritos(page):
    return page.eval_on_selector_all(
        "#escritosCiv table tbody tr",
        r"""els => els.map(tr => { const td = Array.from(tr.querySelectorAll('td'));
              const c = i => td[i] ? td[i].innerText.trim() : '';
              return {fecha_ingreso:c(2), tipo_escrito:c(3), solicitante:c(4)}; })
            .filter(r => r.tipo_escrito || r.solicitante)""")


def cuaderno_options(page):
    try:
        return page.eval_on_selector_all(
            "#selCuaderno option",
            "els=>els.map(e=>({txt:(e.textContent||'').trim(), val:e.value}))")
    except Exception:
        return []


def select_cuaderno(page, index):
    """Switch cuaderno with the TRUSTED keyboard, never select_option.

    ⚠️ This used `page.select_option`, which is the synthetic-change path that
    `select_tribunal_kbd` exists to avoid — its own docstring says that event trips the F5 WAF,
    and `establish_form_kbd` drives every other control by keyboard for exactly that reason. The
    cuaderno switch was the one select left doing it, and it went unnoticed because worker A only
    ever reads cuaderno 1 and never switches. Worker B switches on EVERY causa, so this would
    have fired on every single one.

    Returns True if the selection took. The caller should treat False as "do not trust the
    historia now on screen" — it still belongs to the previous cuaderno.

    ⚠️⚠️ THIS FUNCTION IS THE PRIME SUSPECT FOR THE ONLY BLOCK LEFT (2026-08-18). Two remote runs
    hours apart were refused on the SAME causa (C-936-2026), at the same point, with the same
    counters — after 19 causas in the same session had made this identical switch successfully.
    The click landed on the right row, the modal opened on the right causa, cuaderno 1 parsed 28
    rows, and only the cuaderno-2 POST was refused. A rate verdict is a function of HOW MUCH you
    have done; that one is a function of WHICH causa. Two things here are what a human does not do:

      1. hover -> .focus() -> arrow keys is a <select> receiving keystrokes it was NEVER CLICKED
         into. The pointer approach below was added because teleported focus is a genuine tell, and
         it did not lift the old 10-open wall — but the shape survives: no mousedown, then keydowns.
      2. the wait_for_timeout(1600) below (and worker A's 900) are FLAT SLEEPS, not conditions.
         They were measured residentially and inherited unchanged by a datacenter runner whose
         round-trip is 17-23 s against a local 12-26 s. Wait for the historia to CHANGE instead.

    ⚠️ And this action is INVISIBLE TO THE TRACE: cdp_scrape.step() wraps human_click, and this is
    not a click, so the whole failure sits in a 9-second hole between two frames. Route it through
    step() before the next attempt at reproducing it.

    Detail and frames: felipe/pjud/HANDOFF_WORKERS.md -> THE 2026-08-18 SESSION.
    """
    try:
        opts = page.eval_on_selector_all(
            "#selCuaderno option", "els=>els.map((o,i)=>({i:i,sel:o.selected}))")
        if index >= len(opts):
            return False
        cur = next((o["i"] for o in opts if o["sel"]), 0)
        if cur == index:
            return True
        # ⚠️ REACH THE CONTROL WITH THE POINTER FIRST. `.focus()` alone is a TELEPORT for the
        # caret: focus materialises inside a dropdown the mouse never approached, and keystrokes
        # start arriving from nowhere. The keys themselves are trusted and humanly paced — it is
        # the ARRIVAL that is synthetic, which is the exact finding this file is built on
        # ("it is the pointer's MOTION, not isTrusted", human_click).
        #
        # It went unseen because worker A never switched cuadernos. The metadata-only worker A
        # switches on EVERY causa, and three runner sessions then died at the same point — the
        # causa where the switch had fired often enough to matter — while the identical code and
        # the identical causas ran clean residentially (166 opens). Operator's question: "could it
        # be something about HOW the runner is fetching the second book?" Yes.
        #
        # Hover, do not click: clicking a <select> opens Chrome's native popup, which is an OS
        # surface the arrow keys below cannot be trusted to drive. press=False gives the approach
        # path and the dwell without that risk — the helper exists for precisely this.
        try:
            b = page.locator("#selCuaderno").bounding_box()
            if b:
                _human_pointer(page, b["x"] + b["width"] * random.uniform(0.3, 0.7),
                               b["y"] + b["height"] / 2, press=False)
        except Exception:
            pass
        page.locator("#selCuaderno").focus()
        key = "ArrowDown" if index > cur else "ArrowUp"
        for _ in range(abs(index - cur)):
            page.keyboard.press(key)
            _kbd_pause(page, base=85, spread=60)
        page.wait_for_timeout(1600)          # historia reloads via AJAX
        now = page.eval_on_selector_all(
            "#selCuaderno option", "els=>els.findIndex(o=>o.selected)")
        return now == index
    except Exception as e:
        print(f"      [warn] selCuaderno {index}: {e}")
        return False


def parse_historia(page):
    return page.eval_on_selector_all(
        "#historiaCiv table tbody tr",
        r"""els => els.map(tr => {
              const td = Array.from(tr.querySelectorAll('td'));
              const cell = i => td[i] ? td[i].innerText.trim() : '';
              const formInfo = f => { if(!f) return null;
                  const inp = f.querySelector("input[name='dtaDoc'], input");
                  return { action: f.getAttribute('action')||'', val: inp?inp.value:'' }; };
              const docForm  = td[1] ? td[1].querySelector('form') : null;
              const anexForm = td[2] ? td[2].querySelector('form') : null;
              const geoA = td[8] ? td[8].querySelector("a[onclick*='geoReferencia']") : null;
              const gm = geoA ? (geoA.getAttribute('onclick')||'')
                                  .match(/geoReferencia\(['"]([^'"]+)['"]\)/) : null;
              return { folio: cell(0), doc: formInfo(docForm), anexo: formInfo(anexForm),
                  etapa: cell(3), tramite: cell(4), desc: cell(5), fecha: cell(6),
                  foja: cell(7), georref: cell(8), geo: gm ? gm[1] : '' }; })""")


# ── modals (open/close with REAL clicks) ─────────────────────────────────────

def modal_open(page, sel):
    try:
        return bool(page.eval_on_selector(
            sel, "e => e && (e.classList.contains('show')||e.classList.contains('in')"
                 " || getComputedStyle(e).display!=='none')"))
    except Exception:
        return False


def close_modal(page, sel):
    for s in (f"{sel} .modal-header .close", f"{sel} button.close",
              f"{sel} [data-dismiss='modal']"):
        try:
            if page.query_selector(s):
                human_click(page, s, timeout=2000)     # human arc — never page.click()
                page.wait_for_timeout(500)
                if not modal_open(page, sel):
                    return
        except Exception:
            pass
    page.wait_for_timeout(300)


def clear_stuck_modal(page):
    """Make sure no detail/receptor modal is left open. Returns True if the page is clean.

    THE failure mode of 2026-07-22: one causa open goes wrong (slow response, or F5 renders a
    rejection page INTO the modal iframe) and the modal never closes. Every later open then
    times out at 30 s, because the script waits for a NEW modal to show the next ROL while the
    dead one is still sitting there — so a single hiccup looked exactly like a burned profile
    for the rest of the run, and waf_check read the trapped rejection page and said
    BLOCKED-DETAIL. The operator proved it by hand: close the modal (or reload) and everything
    works again. Escape first — it is a trusted keystroke and costs nothing."""
    for sel in ("#modalReceptorCivil", "#modalDetalleCivil"):
        if not modal_open(page, sel):
            continue
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        except Exception:
            pass
        if modal_open(page, sel):
            close_modal(page, sel)
        if modal_open(page, sel):
            try:                      # last resort: the site's own hide, then Escape again
                page.evaluate("s=>{const m=document.querySelector(s);"
                              " if(m&&window.jQuery) window.jQuery(m).modal('hide');}", sel)
                page.wait_for_timeout(500)
            except Exception:
                pass
        if modal_open(page, sel):
            print(f"      [warn] {sel} sigue abierto — la pagina esta atascada")
            return False
    # ⚠️ A modal that FAILED to open still leaves Bootstrap's backdrop behind, and the backdrop
    # covers Buscar and every causa link. human_click then refuses each target as "tapado" and the
    # run degrades with no block, no rejection page and nothing in any detector — the silent
    # throttle of 2026-08-07/08 looked exactly like this. Removing the orphan backdrop is a DOM
    # cleanup, not a click: it costs no request.
    try:
        n = page.evaluate("""()=>{
          let k=0;
          document.querySelectorAll('.jquery-loading-modal__bg,.jquery-loading-modal')
              .forEach(e=>{ const r=e.getBoundingClientRect();
                            if(r.width>0 && r.height>0){ e.remove(); k++; } });
          return k;}""")
        if n:
            print(f"      [fix] removed {n} stuck loading overlay(s) covering the page")
    except Exception:
        pass
    try:
        page.evaluate("""()=>{
          const anyOpen=[...document.querySelectorAll('.modal')]
              .some(m=>m.classList.contains('show')||m.classList.contains('in')
                       ||getComputedStyle(m).display!=='none');
          if(anyOpen) return 0;
          let n=0;
          document.querySelectorAll('.modal-backdrop').forEach(b=>{b.remove();n++;});
          document.body.classList.remove('modal-open');
          document.body.style.removeProperty('padding-right');
          document.body.style.removeProperty('overflow');
          return n;}""")
    except Exception:
        pass
    return True


def parse_receptor(page):
    a = page.query_selector("#modalDetalleCivil a[onclick*='receptorCivil']")
    if not a:
        return []
    try:
        human_click(page, a, timeout=5000)             # human arc — never .click()
        page.wait_for_function(
            "()=>{const m=document.querySelector('#modalReceptorCivil');"
            " return m && (m.querySelector('table tbody tr')||/Receptor/i.test(m.innerText));}",
            timeout=10000)
        page.wait_for_timeout(400)
        rows = page.eval_on_selector_all(
            "#modalReceptorCivil table tbody tr",
            r"""els=>els.map(tr=>{const td=Array.from(tr.querySelectorAll('td'));
                  const c=i=>td[i]?td[i].innerText.trim():'';
                  return {cuaderno:c(0), nombre:c(1), fecha:c(2), estado:c(3)};})
                .filter(r=>r.nombre||r.cuaderno)""")
        close_modal(page, "#modalReceptorCivil")
        return rows
    except Exception:
        try:
            close_modal(page, "#modalReceptorCivil")
        except Exception:
            pass
        return []


def _cuaderno_num(txt):
    m = re.match(r"\s*(\d+)\s*-", txt or "")
    return m.group(1) if m else "1"


def get_store():
    """Lazy dbstore.Store() for Drive uploads (built only when --docs). Reuses the
    proven Drive upload_pdf path (documentos folder + flattened names)."""
    global _STORE
    if _STORE is None:
        import dbstore
        _STORE = dbstore.Store()
    return _STORE


def resolve_geo(page, jwt):
    """Open the georreferencia sub-modal for `jwt`, read lat/lng, close. Returns a
    =HYPERLINK(...) cell or ''. Uses the site's own geoReferencia() (in-session)."""
    try:
        page.evaluate("j => geoReferencia(j)", jwt)
        page.wait_for_function(
            "()=>{const m=document.querySelector('#modalGeoReferenciaCivil');"
            " const i=m&&m.querySelector(\"input[name='latitud']\"); return i&&i.value;}",
            timeout=8000)
        page.wait_for_timeout(200)
        vals = page.eval_on_selector_all(
            "#modalGeoReferenciaCivil input[name='latitud'],"
            " #modalGeoReferenciaCivil input[name='longitud']",
            "els=>els.map(e=>({n:e.getAttribute('name'), v:e.value||''}))")
        d = {x["n"]: x["v"] for x in vals}
        lat, lng = d.get("latitud", ""), d.get("longitud", "")
        close_modal(page, "#modalGeoReferenciaCivil")
        if lat and lng:
            return (f'=HYPERLINK("https://maps.google.com/maps?ll={lat},{lng}&z=16",'
                    f'"{lat[:10]}, {lng[:10]}")')
    except Exception:
        try:
            close_modal(page, "#modalGeoReferenciaCivil")
        except Exception:
            pass
    return ""


def download_doc(api, action, val, param="dtaDoc"):
    """GET OJV/<action>?<param>=<val> in-session (shares cookies) -> PDF bytes or None.

    NB this goes out through Playwright's APIRequestContext — it shares cookies but is issued
    OUTSIDE the page, so it carries none of the browser's request context and produces no F5
    Shape telemetry. Suspected (not proven) of burning the profile in the detail regime; see
    `download_doc_inpage` for the alternative and `--docs-inpage` to A/B them."""
    if not action or not val:
        return None
    try:
        resp = api.get(f"{OJV}/{action.lstrip('/')}", params={param: val}, timeout=60000)
        body = resp.body()
        ct = (resp.headers or {}).get("content-type", "")
        if "pdf" not in ct.lower() and body[:4] != b"%PDF":
            return None
        return body
    except Exception:
        return None


# In-page fetch: same URL, but issued BY the page, so it inherits the document's origin,
# referer and cookie handling and lands inside Shape's instrumented XHR path instead of
# beside it. Bytes come back base64 (chunked so a big ebook doesn't blow the argument stack).
def classify(body):
    """'pdf' | 'apm' | 'other' — what did the document endpoint actually return?

    ⚠️ "It is over 1000 bytes" is NOT a document. That test is why three files sat on disk named
    *.pdf for a day while every one of them was really F5's <APM_DO_NOT_TOUCH> anti-bot
    interstitial: ~8-14 KB of obfuscated JavaScript, comfortably over any size threshold, with a
    perfectly ordinary 200 status. Check the magic bytes; nothing else is evidence.

    ⚠️ Lives HERE, not in worker_a, since 2026-08-19 — `fetch_doc_detail` needs it and a second
    copy of a "what did we actually get" test is the exact shape of the duplicated rejection
    matchers that went blind together. worker_a imports it from this module.
    """
    if not body:
        return "other"
    if body[:4] == b"%PDF":
        return "pdf"
    head = body[:400].lstrip()
    if b"APM_DO_NOT_TOUCH" in head or b"TSPD" in body[:2000]:
        return "apm"
    return "other"


_JS_FETCH_DOC = """
async ([url, param, val]) => {
  const u = url + '?' + param + '=' + encodeURIComponent(val);
  const t0 = performance.now();
  const r = await fetch(u, {credentials: 'include'});
  const bytes = new Uint8Array(await r.arrayBuffer());
  let s = '', CH = 0x8000;
  for (let i = 0; i < bytes.length; i += CH)
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  return {status: r.status, ok: r.ok, ct: r.headers.get('content-type'), n: bytes.length,
          ms: Math.round(performance.now() - t0), b64: btoa(s)};
}
"""


def fetch_doc_detail(page, action, val, param="dtaDoc"):
    """The in-page document fetch, reporting WHY it failed. -> dict, never raises.

    ⚠️ A DOCUMENT FETCH HAS THREE FAILURE MODES AND THEY NEED DIFFERENT ANSWERS. The old
    `download_doc_inpage` returned None for all of them, and that cost a session on 2026-08-10:
    "TypeError: Failed to fetch" is the request being REFUSED at the network layer, which carries
    no rejection frame and no challenge iframe, so `blocked()` sees nothing — slot 1 went on
    buying causa opens whose every document was being denied while its sibling had already taken
    a visible block. A missing document and a refused one look identical from a None.

      {"bytes": n, "b64": ...}                 got it, and it starts %PDF
      {"bytes": 0, "refused": True}            denied at the network layer — this is TROUBLE
      {"bytes": 0, "not_pdf": True, ...}       answered with something else (rejection HTML, apm)
      {"bytes": 0, "missing": True}            no action/val to fetch with

    ⚠️ NEVER JUDGE A DOCUMENT BY SIZE OR STATUS — check for %PDF. A clicked PDF hands back
    Chrome's viewer wrapper, ~14 KB of HTML with status 200; that one fact produced two opposite
    wrong calls in a single day (see grab_doc in worker_a.py).
    """
    if not action or not val:
        return {"bytes": 0, "missing": True, "why": "no action/val"}
    try:
        res = page.evaluate(_JS_FETCH_DOC, [f"{OJV}/{action.lstrip('/')}", param, val])
    except Exception as e:
        msg = str(e)
        refused = "Failed to fetch" in msg or "ERR_" in msg
        return {"bytes": 0, "refused": refused, "threw": not refused, "why": msg[:90]}
    if not res:
        return {"bytes": 0, "missing": True, "why": "no response object"}
    body = base64.b64decode(res.get("b64") or "")
    if body[:4] != b"%PDF":
        return {"bytes": 0, "not_pdf": True, "status": res.get("status"),
                "ct": res.get("ct"), "n": res.get("n"), "ms": res.get("ms"),
                "why": classify(body) if body else "empty body"}
    return {"bytes": len(body), "body": body, "status": res.get("status"),
            "ct": res.get("ct"), "ms": res.get("ms")}


def download_doc_inpage(page, action, val, param="dtaDoc"):
    """Same fetch as download_doc but performed BY THE PAGE. -> PDF bytes or None.

    Kept as the simple form for callers that only want the bytes; there is exactly ONE
    implementation underneath (`fetch_doc_detail`), because two copies of a facility is how the
    block detectors in this repo drifted apart and went blind together."""
    d = fetch_doc_detail(page, action, val, param)
    return d.get("body") if d.get("bytes") else None


def fetch_doc(page, api, action, val, param="dtaDoc"):
    """Dispatch to the in-page or the out-of-page downloader (`--docs-inpage`)."""
    if DOCS_INPAGE:
        return download_doc_inpage(page, action, val, param)
    return download_doc(api, action, val, param)


# Causa-level header docs (in the detalle modal header, not the historia table). Each:
# (key, action-substring, hidden-input param). Always fetched when --docs (reduced set).
HEADER_DOCS = [
    ("texto_demanda", "docu.php", "valorEncTxtDmda"),
    ("certificado", "docCertificadoDemanda", "dtaCert"),
    ("ebook", "newebookcivil", "dtaEbook"),
]


def grab_header_docs(page):
    """[{key, action, param, val}] for the Texto Demanda / Certificado / Ebook forms."""
    return page.evaluate(
        r"""(want)=>{
          const m=document.querySelector('#modalDetalleCivil'); if(!m) return [];
          const out=[];
          m.querySelectorAll('form').forEach(f=>{
            const a=f.getAttribute('action')||'';
            const hit=want.find(w=>a.includes(w[1]));
            if(!hit) return;
            const inp=f.querySelector('input');
            out.push({key:hit[0], action:a, param:inp?inp.getAttribute('name'):'',
                      val:inp?inp.value:''});
          });
          return out;
        }""", HEADER_DOCS)


def causa_state(tribunal_id):
    """{rol: (fill_status, detalles_bool)} for a tribunal — for --resume + the Detalles flag.

    Retries once through dbstore._reconnect(). A multi-hour sweep outlives Neon's idle
    timeout, and the connection dies somewhere around the second tribunal; returning {} on
    that error SILENTLY DISABLES --resume, so the run happily re-scrapes causas it already
    has (observed 2026-07-22: 'SSL connection has been closed unexpectedly' at tribunal 260,
    then 'connection already closed' for every tribunal after it)."""
    for attempt in (1, 2):
        try:
            store = get_store()
            with store.conn.cursor() as cur:
                cur.execute("SELECT rol, fill_status, detalles FROM causas WHERE tribunal_id=%s",
                            (str(tribunal_id),))
                return {r[0]: (r[1] or "", bool(r[2])) for r in cur.fetchall()}
        except Exception as e:
            if attempt == 1:
                print(f"    [warn] causa_state {tribunal_id}: {str(e)[:50]} — reconectando")
                try:
                    get_store()._reconnect()
                    continue
                except Exception as e2:
                    print(f"    [warn] reconexion fallida: {str(e2)[:50]}")
            print(f"    [warn] causa_state {tribunal_id}: sin DB — "
                  f"--resume NO puede saltar nada en este tribunal")
            return {}


def _kbd_pause(page, base=95, spread=70, long_every=9):
    """Sleep a human-ish interval between keystrokes.

    ⚠️ THE KEYBOARD WAS PERFECTLY UNIFORM. select_by_kbd waited exactly 70 ms between every
    arrow press and type_date_kbd typed at exactly 60 ms per character — for dozens of keys in a
    row. That is the keyboard equivalent of the teleporting pointer that page.click() used to do,
    and F5 Shape scores keystroke timing just as it scores pointer motion. Measured 2026-08-10 on
    a session a HUMAN had just walked into: the Competencia cascade, the date typing and the
    tribunal select all passed, and the very FIRST scripted search drew a tier-3 CAPTCHA. One
    request, no rate involved — so it was never pacing, it was what the input stream looked like.

    Real typing is noisy: most gaps cluster in a range, with an occasional long one where a
    person glances away. Both are reproduced here.
    """
    d = random.gauss(base, spread / 3.0)
    d = max(35.0, min(base + spread, d))
    if long_every and random.randint(1, long_every) == 1:
        d += random.uniform(180, 520)          # the occasional glance-away
    page.wait_for_timeout(d)


def select_by_kbd(page, sel, value):
    """Change a <select> to `value` via TRUSTED keyboard (focus + arrows). True on success."""
    try:
        opts = page.eval_on_selector_all(
            f"{sel} option", "els=>els.map((o,i)=>({i:i,v:o.value,sel:o.selected}))")
        cur = next((o["i"] for o in opts if o["sel"]), 0)
        tgt = next((o["i"] for o in opts if o["v"] == value), None)
        if tgt is None:
            return False
        page.locator(sel).focus()
        key = "ArrowDown" if tgt > cur else "ArrowUp"
        for _ in range(abs(tgt - cur)):
            page.keyboard.press(key)
            _kbd_pause(page, base=85, spread=60)
        return page.eval_on_selector(sel, "e=>e.value") == value
    except Exception:
        return False


def _wait_opts(page, sel, secs):
    """Poll for a <select>'s options to populate (AJAX cascade). True when >0 real options."""
    for _ in range(secs * 2):
        page.wait_for_timeout(500)
        try:
            if page.eval_on_selector_all(f"{sel} option",
                                         "e=>e.filter(o=>o.value&&o.value!=='0').length"):
                return True
        except Exception:
            pass
    return False


def type_date_kbd(page, sel, value):
    """⚠️⚠️ SUPERSEDED 2026-08-19 — USE `human_engine.pick_date_mouse`. NO USER CAN DO THIS.

    Every worker was moved off this on 2026-08-19. It is kept because three probes still call it
    and because the isTrusted reasoning below is correct and worth preserving — but it is correct
    about the WRONG QUESTION. The keystrokes are genuine; the problem is that `#fecDesde` and
    `#fecHasta` are `readonly` with `hasDatepicker`, so **a person physically cannot type into
    them** — the operator found it by simply trying. Clearing `readOnly` and typing is a sequence
    no user can produce, performed on the form where the session token is minted, in every run
    this project made until worker H. The site ships a jQuery UI datepicker; drive it with the
    mouse.

    ⚠️ A probe that calls this is not measuring the worker any more. Fix the probe before trusting
    a comparison against a run that used the picker.

    ── the original note, still true about isTrusted ──
    Set a readonly datepicker input with TRUSTED keystrokes. `readOnly` is cleared as a DOM
    PROPERTY — a mutation, not an event, so nothing untrusted is ever dispatched — and then the
    value is TYPED for real, so the browser itself emits genuine isTrusted=true input/change
    events. Do NOT go back to `e.value=...` + `dispatchEvent(new Event('change'))`: that fires
    isTrusted=false and F5 flags the session (the search still succeeds once, then the NEXT
    request comes back as the rejection page — it burned a profile on 2026-07-21)."""
    for attempt, closer in enumerate(("Escape", "Tab")):
        try:
            page.eval_on_selector(sel, "e=>{e.readOnly=false;e.removeAttribute('readonly');}")
            human_click(page, sel)                    # human arc — also opens the datepicker
            page.keyboard.press("Control+a")
            for ch in value:                          # TRUSTED keystrokes, human cadence
                page.keyboard.type(ch)
                _kbd_pause(page, base=110, spread=90)
            page.keyboard.press(closer)               # close the datepicker / blur to fire change
            page.wait_for_timeout(400)
            if page.eval_on_selector(sel, "e=>e.value") == value:
                return True
        except Exception as e:
            print(f"      [date {sel}] {str(e)[:50]}")
    return False


def fecha_form_visible(page):
    """True if the Busqueda-por-Fecha panel is actually OPEN. Presence is not enough: on
    indexN.php the selects exist in the DOM even while the accordion is collapsed."""
    try:
        return bool(page.eval_on_selector("#fecCompetencia", "e=>!!(e&&e.offsetParent!==null)"))
    except Exception:
        return False


def ensure_window(page, w=1440, h=900):
    """Make the real browser window at least w x h. (ok, {vw,vh}) — never raises.

    ⚠️ WHY NOT JUST --window-size. Measured 2026-08-17: six workers launched with
    `--window-size=1440,900` came up at 958x428, 673x483 and 726x434 — the flag was not honoured,
    the windows differed from each other, and none matched the request. The consequence is not
    cosmetic: the results table is ~1115 px wide, so a 958 px viewport scrolls HORIZONTALLY, and
    the magnifier column lands at x=-441 — outside the window, unreachable, refused. That cost
    1,224 causas in one afternoon and was read as the site refusing us.

    ⚠️ THIS IS A REAL WINDOW RESIZE (Browser.setWindowBounds), NOT device emulation. A person's
    browser has a genuine size; Emulation.setDeviceMetricsOverride would fake one, which is
    exactly the class of thing this project refuses to do. Resizing your own window is ordinary.
    """
    try:
        sess = page.context.new_cdp_session(page)
        wid = sess.send("Browser.getWindowForTarget")["windowId"]
        sess.send("Browser.setWindowBounds",
                  {"windowId": wid,
                   "bounds": {"windowState": "normal", "left": 0, "top": 0,
                              "width": w, "height": h}})
        page.wait_for_timeout(400)
        vp = page.evaluate("()=>({vw:innerWidth, vh:innerHeight})")
        return (vp["vw"] >= w - 120 and vp["vh"] >= h - 220), vp
    except Exception as e:
        try:
            vp = page.evaluate("()=>({vw:innerWidth, vh:innerHeight})")
        except Exception:
            vp = None
        print(f"    [warn] ensure_window: {str(e)[:70]}")
        return False, vp


def open_fecha_panel(page):
    """Expand 'Busqueda por Fecha'.

    After a reload, indexN.php comes back as the Consulta Unificada page with every search panel
    COLLAPSED. #fecCompetencia and #fecTribunal are still in the DOM, so `query_selector` happily
    reports the form as present while every keyboard select fails on an invisible element. The
    old code tried `a[href='#BusFecha']`, but the real accordion link is `#BusFecha-collapse`, so
    the expand silently did nothing: worker 3 skipped 9 tribunales printing '[establish]
    competencia select failed' and still exited 0 / LISTO (2026-07-23)."""
    if fecha_form_visible(page):
        return True
    for sel in ("a[href='#BusFecha-collapse']", "a[href='#BusFecha']",
                "a[data-target='#BusFecha-collapse']"):
        if not page.query_selector(sel):
            continue
        if not human_click(page, sel, timeout=6000):
            continue
        for _ in range(20):
            page.wait_for_timeout(300)
            if fecha_form_visible(page):
                return True
    if fecha_form_visible(page):
        return True

    # ⚠️⚠️ THE NAV AND THE PANES CAN DISAGREE, AND THEN THE TAB CANNOT BE CLICKED BACK.
    # Diagnosed live 2026-08-17 after it had cost the whole afternoon under the label "the form is
    # wedged". #BusFecha is a Bootstrap TAB PANE, not an accordion collapse. On a wedged page the
    # nav item for "Busqueda por Fecha" carries `active` while the PANE has lost `in active` and
    # sits at display:none, with #busRit shown instead. Bootstrap will not switch to a tab it
    # already believes is current, so clicking the Fecha link delivers a real click that does
    # nothing at all — human_click correctly returns True and the form stays hidden.
    #
    # The symptom was every #fecTribunal select_option timing out at 8 s on an element that was
    # populated (232 options), enabled, uncovered, on an idle page — because it was INVISIBLE.
    # Re-entry appeared to fix it only because rebuilding the form re-selects the tab; the desync
    # returned within a couple of searches and the worker burned its recovery budget.
    #
    # The fix is what a person does when a tab looks selected but shows the wrong panel: click a
    # DIFFERENT tab, then click back. That forces Bootstrap to actually move the `in active`.
    other = next((s for s in ("a[href='#busRit']", "a[href='#BusNombre']",
                              "a[href='#BusJuridica']") if page.query_selector(s)), None)
    if other and human_click(page, other, timeout=6000):
        page.wait_for_timeout(700)
        if human_click(page, "a[href='#BusFecha']", timeout=6000):
            for _ in range(20):
                page.wait_for_timeout(300)
                if fecha_form_visible(page):
                    print("      [fix] tab state was desynced — clicked away and back")
                    return True
    return fecha_form_visible(page)


def establish_form_kbd(page, corte_val, desde, hasta):
    """Establish the Busqueda por Fecha form BASE with TRUSTED keyboard only — no manual search
    needed, and this is also the session-expiry recovery. Sets: Fecha tab, Civil competencia,
    corte, dates. Tribunals are iterated by the caller. Returns True on success."""
    try:
        if not open_fecha_panel(page):
            print("      [establish] no puedo abrir el panel 'Busqueda por Fecha'")
            return False
        if not select_by_kbd(page, "#fecCompetencia", "3"):     # Civil
            print("      [establish] competencia select failed")
            return False
        _wait_opts(page, "#corteFec", 6)
        if not select_by_kbd(page, "#corteFec", corte_val):
            print(f"      [establish] corte {corte_val} select failed")
            return False
        page.wait_for_timeout(5000)                             # 5s settle (operator's tip)
        _wait_opts(page, "#fecTribunal", 10)
        for sel, val in (("#fecDesde", desde), ("#fecHasta", hasta)):
            if not type_date_kbd(page, sel, val):               # TRUSTED typing, never JS .value
                print(f"      [establish] date {sel} = {val} failed")
                return False
        return True
    except Exception as e:
        print(f"      [establish] {str(e)[:60]}")
        return False


class Blocked(Exception):
    """The F5 WAF is rejecting detail opens — abort the run, the profile is spent."""


def waf_blocked(page):
    """True if the F5 WAF is rejecting us. Same signal as waf_check.py, read only when a causa
    fails or a streak of searches comes back empty, so it costs nothing on the happy path.

    ⚠️ 2026-08-05: this used to test the ENGLISH rejection text only. Our browser gets the page
    in SPANISH ("Su numero de soporte es : <...>"), so a real block returned False, the
    --max-empty/--max-fails watchdogs never fired, and the sweep marched on recording tribunal
    after tribunal as "sin resultados" — heading for a silent exit 0 / [LISTO] with most of the
    corte missing. Caught only because the operator was watching the browser. Match BOTH
    languages, and also the structural tell below, which does not depend on wording at all.
    """
    for fr in page.frames:
        try:
            txt = fr.evaluate("document.body?document.body.innerText.slice(0,400):''") or ""
        except Exception:
            continue
        low = txt.lower()
        if ("requested url was rejected" in low or "support id" in low
                or "numero de soporte" in low or "número de soporte" in low):
            return True
    # Structural tell: Shape injects a TSBrPFrame_cs_chlg_* iframe and parks it ON the Buscar
    # button, which is left disabled. Locale-proof — if F5 rewords the page again, this holds.
    try:
        if page.evaluate(
                """()=>{
                  const rx = /TSBrPFrame|cs_chlg/;
                  if ([...document.querySelectorAll('iframe,div')].some(e=>rx.test(e.id||'')))
                      return true;
                  const b = document.querySelector('#btnConConsultaFec');
                  if (!b || !b.disabled) return false;
                  const r = b.getBoundingClientRect();
                  const t = document.elementFromPoint(r.x+r.width/2, r.y+r.height/2);
                  return !!t && rx.test(t.id || t.className || '');
                }"""):
            return True
    except Exception:
        pass
    return False


def form_ok(page):
    """True if the date form is still established AND usable: panel open (a collapsed accordion
    hides a perfectly valid-looking form), competencia=Civil, tribunal select enabled. False
    after a session-expiry popup resets it, or after a reload collapses the panel."""
    try:
        return (fecha_form_visible(page)
                and page.eval_on_selector("#fecCompetencia", "e=>e.value") == "3"
                and not page.eval_on_selector("#fecTribunal", "e=>e.disabled"))
    except Exception:
        return False


def scrape_causa(page, api, meta, full=False):
    """Modal opened by the caller. Parse header/litigantes/cuadernos(historia)/escritos/
    receptor. With GPS: resolve each geo row's lat/lng. With DOCS: download the causa-level
    header docs (Texto Demanda / Certificado / Ebook) + a FILTERED set of historia docs to
    Drive. Reduced set (default): cuaderno 1 (Principal) only the 'Ingreso demanda' row, other
    cuadernos all rows. `full=True` (Detalles flag): every historia doc. Close the modal."""
    header = parse_header(page)
    litigantes = parse_litigantes(page)
    causa_id = f"{meta.get('tribunalId','')}-{meta['rol']}"

    # causa-level header docs — always downloaded (part of the reduced set)
    header_urls = {}
    if DOCS:
        for hd in grab_header_docs(page):
            if KNOWN_HEADER and hd["key"] in KNOWN_HEADER:
                continue                      # worker C: already on the causa row
            body = fetch_doc(page, api, hd["action"], hd["val"], param=hd["param"])
            if body and len(body) >= 1024:
                obj = f"{causa_id}/{hd['key']}.pdf".replace(" ", "_")
                try:
                    header_urls[hd["key"]] = get_store().upload_pdf(obj, body)
                except Exception as e:
                    print(f"      [warn] upload {hd['key']}: {str(e)[:50]}")

    cuads = cuaderno_options(page) or [{"txt": "1 - Principal", "val": ""}]
    cuadernos = []
    for ci, opt in enumerate(cuads):
        if ci > 0:
            select_cuaderno(page, ci)
            pace(P_STEP)
        cuaderno = opt["txt"]
        cnum = _cuaderno_num(cuaderno)
        is_principal = cnum == "1"
        rows = parse_historia(page)
        seen = {}
        for hh in rows:
            folio = hh.get("folio", "")
            n = seen.get(folio, 0) + 1
            seen[folio] = n
            row_id = f"{causa_id}-c{cnum}-{folio}-{n}"
            if GPS and hh.get("geo"):
                if KNOWN_GEO is not None and KNOWN_GEO.get(row_id):
                    hh["georref"] = KNOWN_GEO[row_id]   # carry it forward; never re-resolve
                else:
                    g = resolve_geo(page, hh["geo"])
                    if g:
                        hh["georref"] = g
                    pace(P_STEP)
            # reduced filter: cuaderno-1 keep only 'Ingreso demanda'; other cuadernos keep all
            want_doc = full or (not is_principal) \
                or ("ingreso demanda" in (hh.get("desc", "") or "").lower())
            if DOCS and want_doc:
                for kind in ("doc", "anexo"):
                    form = hh.get(kind)
                    if not (form and form.get("action") and form.get("val")):
                        continue
                    if KNOWN_DOCS is not None and f"{row_id}-{kind}" in KNOWN_DOCS:
                        continue              # worker C: already in Drive and in Neon
                    body = fetch_doc(page, api, form["action"], form["val"])
                    if body and len(body) >= 1024:
                        obj = f"{causa_id}/c{cnum}/{folio}-{n}-{kind}.pdf".replace(" ", "_")
                        try:
                            hh[f"{kind}_url"] = get_store().upload_pdf(obj, body)
                        except Exception as e:
                            print(f"      [warn] upload {kind} {folio}: {str(e)[:50]}")
        cuadernos.append({"cuaderno": cuaderno, "historia": rows})
    escritos = parse_escritos(page)
    pace(P_STEP)
    receptor = parse_receptor(page)
    close_modal(page, "#modalDetalleCivil")
    n_hist = sum(len(c["historia"]) for c in cuadernos)
    ndoc = len(header_urls) + sum(
        1 for c in cuadernos for r in c["historia"] if r.get("doc_url") or r.get("anexo_url"))
    ngeo = sum(1 for c in cuadernos for r in c["historia"] if str(r.get("georref", "")).startswith("="))
    return {**meta, "header": header, "litigantes": litigantes, "cuadernos": cuadernos,
            "escritos": escritos, "receptor": receptor, "n_historia": n_hist,
            "n_docs": ndoc, "n_geo": ngeo, "scrape_level": "full" if full else "scraped",
            "texto_demanda": header_urls.get("texto_demanda", ""),
            "certificado": header_urls.get("certificado", ""),
            "ebook": header_urls.get("ebook", "")}


# ── search / pagination ──────────────────────────────────────────────────────

def fire_search(page):
    """Wait for Buscar to be enabled (form settles after a tribunal change), CLEAR the stale
    results (so old rows aren't mistaken for a fresh search), click Buscar ONCE (TRUSTED), and
    poll up to ~45s for rows. Returns True if rows rendered, False on 'sin resultados'/disabled."""
    for _ in range(24):   # up to ~12s for the button to enable
        try:
            if not page.eval_on_selector("#btnConConsultaFec", "e=>e.disabled"):
                break
        except Exception:
            pass
        page.wait_for_timeout(500)
    try:   # clear stale results so a disabled/failed search can't look successful
        page.evaluate("()=>{const t=document.querySelector('#dtaTableDetalleFecha tbody');"
                      " if(t) t.innerHTML='';}")
    except Exception:
        pass
    if not human_click(page, "#btnConConsultaFec", timeout=5000):
        print("    [warn] buscar not clickable")
        return False
    waited = 0
    while waited < 45000:
        n = page.eval_on_selector_all(
            "#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']", "e=>e.length")
        if n:
            page.wait_for_timeout(700)
            return True
        try:
            txt = page.inner_text("#dtaTableDetalleFecha")
        except Exception:
            txt = ""
        if re.search(r"no se (han )?encontrad|sin resultados", txt or "", re.I):
            return False
        page.wait_for_timeout(1000)
        waited += 1000
    return False


def select_tribunal_kbd(page, value):
    """Change #fecTribunal to `value` via TRUSTED keyboard (focus + arrow keys) — NOT
    select_option (whose synthetic change event trips the F5 WAF). Returns True on success."""
    try:
        opts = page.eval_on_selector_all(
            "#fecTribunal option", "els=>els.map((o,i)=>({i:i,v:o.value,sel:o.selected}))")
        cur = next((o["i"] for o in opts if o["sel"]), 0)
        tgt = next((o["i"] for o in opts if o["v"] == value), None)
        if tgt is None:
            return False
        page.locator("#fecTribunal").focus()
        delta = tgt - cur
        key = "ArrowDown" if delta > 0 else "ArrowUp"
        for _ in range(abs(delta)):
            page.keyboard.press(key)
            _kbd_pause(page, base=85, spread=60)
        return page.eval_on_selector("#fecTribunal", "e=>e.value") == value
    except Exception as e:
        print(f"    [warn] kbd tribunal {value}: {str(e)[:50]}")
        return False


def scraped_rols(tribunal_id):
    """Set of rols at this tribunal already fully scraped (fill_status='scraped') in Neon.
    Used by --resume to skip them. Retries once through _reconnect() — see causa_state()."""
    for attempt in (1, 2):
        try:
            store = get_store()
            with store.conn.cursor() as cur:
                cur.execute("SELECT rol FROM causas WHERE tribunal_id=%s "
                            "AND fill_status='scraped'", (str(tribunal_id),))
                return {r[0] for r in cur.fetchall()}
        except Exception as e:
            if attempt == 1:
                print(f"    [warn] resume lookup {tribunal_id}: {str(e)[:50]} — reconectando")
                try:
                    get_store()._reconnect()
                    continue
                except Exception:
                    pass
            print(f"    [warn] resume lookup {tribunal_id}: sin DB — no se salta nada")
            return set()


def page_rows(page):
    """Every row of the current results page (bank or not). Kept separate from the bank filter
    so pagination can be audited against `.loadTotalFec`: the site's total counts ALL rows, so
    comparing it to the bank subset would be meaningless."""
    return page.eval_on_selector_all(
        "#dtaTableDetalleFecha tbody tr",
        r"""els=>els.map((tr,i)=>{var td=tr.querySelectorAll('td');
              var a=tr.querySelector("a[onclick*='detalleCausaCivil']");
              return {i:i, rol:td[1]?td[1].innerText.trim():'', car:td[3]?td[3].innerText.trim():'',
                      fecha:td[2]?td[2].innerText.trim():'', trib:td[4]?td[4].innerText.trim():'',
                      has:!!a};})""")


def page_bank_causas(page):
    return [r for r in page_rows(page) if r["has"]
            and r["rol"].upper().startswith("C") and is_bank(r["car"])]


def total_registros(page):
    """The search's TRUE row count, from the site's own `Total de registros: N` label.

    This is the only ground truth for "did pagination reach the end?". Without it the loop can
    only ask "did the table change?", and a slow paginator AJAX then looks exactly like the last
    page — which is how tribunal 260 was recorded as 91 bank causas when it really has 135
    (2026-07-22). Returns None if the label is missing or unparseable: never guess a total."""
    for sel in (".loadTotalFec", "#loadTotalFec", "[class*='loadTotal']"):
        try:
            txt = page.eval_on_selector(sel, "e=>e?e.innerText:''") or ""
        except Exception:
            continue
        m = re.search(r"([\d.,]+)\s*$", txt.strip())
        if m:
            try:
                return int(re.sub(r"[.,]", "", m.group(1)))
            except ValueError:
                pass
    return None


def paginator_state(page):
    """(current, last) page numbers from the paginator, or (None, None) if unreadable.
    Advisory only — used to log progress and to confirm a 'stuck' verdict."""
    try:
        got = page.evaluate(
            """()=>{const s=document.querySelector('#sigId'); if(!s) return null;
                 const ul=s.closest('ul'); if(!ul) return null;
                 const nums=[...ul.querySelectorAll('li')].map(li=>({
                   n:parseInt((li.innerText||'').trim(),10),
                   act:li.classList.contains('active')})).filter(o=>!isNaN(o.n));
                 const cur=nums.find(o=>o.act);
                 return {cur:cur?cur.n:null, last:nums.length?Math.max(...nums.map(o=>o.n)):null};}""")
    except Exception:
        return (None, None)
    if not got:
        return (None, None)
    return (got.get("cur"), got.get("last"))


def first_sig(page):
    """Fingerprint of the first causa link, or '' if the table has none.

    ⚠️ eval_on_selector THROWS when nothing matches the selector, and an EMPTY results table is
    a perfectly ordinary state — a throttled session clears it. Unguarded, that exception
    propagated out of next_page and killed a 10-hour sweep at tribunal 73 of 230 (2026-08-07),
    which then sat dead for 19 hours. Use the _all form: no match is a value, not an error.
    """
    try:
        return page.eval_on_selector_all(
            "#dtaTableDetalleFecha tbody tr a[onclick*='detalleCausaCivil']",
            "els=>els.length?els[0].getAttribute('onclick'):''") or ""
    except Exception:
        return ""


def sig_disabled(page):
    """True when 'Siguiente' is greyed out = we are genuinely on the last page."""
    try:
        return bool(page.eval_on_selector(
            "#sigId",
            "e=>{const li=e.closest('li');return !!(li&&li.classList.contains('disabled'));}"))
    except Exception:
        return True     # no paginator at all -> nothing to advance to


def next_page(page, tries=2):
    """Advance the results paginator one page. Returns a REASON, not a bool:

        "advanced"  the table really swapped — keep harvesting
        "last"      Siguiente is disabled — the tribunal is genuinely finished
        "stuck"     we clicked and the table never changed — pages were LOST

    The old version returned False for both "last" and "stuck", and every caller read that as
    "no more pages" and moved on with exit code 0. That is the whole `--count-only` undercount:
    tribunal 260 reported 91 bank causas in January against 135 real ones (~one page dropped),
    because a paginator AJAX that took longer than the 10 s poll is indistinguishable from the
    end of the list. Now a timeout retries the click once and, if it still will not move, says
    so out loud so the caller can flag the tribunal instead of silently truncating it."""
    if sig_disabled(page):
        return "last"
    for attempt in range(1, tries + 1):
        wait_idle(page)                       # never click while the site is mid-request
        before = first_sig(page)
        if not human_click(page, "#sigId", timeout=4000):   # human arc — never page.click()
            page.wait_for_timeout(1500)
            continue
        for _ in range(40):                   # poll up to ~20s for the AJAX swap (was 10s)
            page.wait_for_timeout(500)
            if first_sig(page) not in ("", before):
                return "advanced"
        # No swap. Two innocent explanations before calling it stuck: the click landed on the
        # last page (Siguiente just became disabled), or the request is still in flight.
        if sig_disabled(page):
            return "last"
        if page_busy(page) and wait_idle(page, secs=25):
            if first_sig(page) not in ("", before):
                return "advanced"
        if attempt < tries:
            print(f"    [warn] paginador no avanzo — reintento {attempt + 1}/{tries}")
    return "stuck"


# ── main ─────────────────────────────────────────────────────────────────────

def find_ojv_page(ctx):
    for p in ctx.pages:
        try:
            if p.query_selector("#fecCompetencia"):
                return p
        except Exception:
            pass
    for p in ctx.pages:
        if "pjud" in (p.url or ""):
            return p
    return ctx.pages[0] if ctx.pages else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--max-tribs", type=int, default=0, help="0 = all tribunales")
    ap.add_argument("--skip-tribs", type=int, default=0,
                    help="skip the first N tribunales of the corte. With --max-tribs this cuts "
                         "a disjoint slice per worker (0/8, 8/8, 16/8) so several workers can "
                         "share ONE corte without scraping the same tribunal twice.")
    ap.add_argument("--max-causas", type=int, default=0, help="0 = no limit")
    ap.add_argument("--proc", default="", help="only keep causas whose Proc. matches (e.g. 'Ejecutivo Obligación de Dar')")
    ap.add_argument("--docs", action="store_true", help="download historia doc/anexo PDFs -> Drive")
    ap.add_argument("--docs-inpage", action="store_true",
                    help="fetch those PDFs from INSIDE the page (in-page fetch) instead of "
                         "context.request.get() — carries the page's request context and shows "
                         "up in Shape's telemetry. Use with --docs.")
    ap.add_argument("--gps", action="store_true", help="resolve georreferencia sub-modals -> lat/lng")
    ap.add_argument("--no-search", action="store_true",
                    help="WAF-safe: do NOT select_option/search; harvest the CURRENT results "
                         "table (operator already searched). Only the displayed tribunal.")
    ap.add_argument("--resume", action="store_true",
                    help="skip causas already scraped (fill_status='scraped') in Neon")
    ap.add_argument("--count-only", action="store_true",
                    help="count bank C-causas per tribunal from the results table; NO detail "
                         "opens/docs (safe on a burned profile — sizes the job)")
    ap.add_argument("--corte", default="",
                    help="establish the form via keyboard for this corte VALUE (90=Santiago) -> "
                         "NO manual search needed; the script sets competencia/corte/dates itself "
                         "and re-establishes if the session-expiry popup resets the form")
    ap.add_argument("--max-empty", type=int, default=4,
                    help="consecutive 'sin resultados' tribunales before checking for the F5 "
                         "rejection page; small rural tribunales really are empty, so only a "
                         "STREAK is suspicious")
    ap.add_argument("--max-fails", type=int, default=3,
                    help="consecutive causa failures before checking for the F5 rejection page; "
                         "if it is there the run STOPS (exit 3) instead of grinding out "
                         "timeouts on a spent profile")
    ap.add_argument("--pace", type=float, default=1.0,
                    help="multiply every pause (P_CAUSA/P_PAGE/P_TRIB/P_STEP). 1.0 = the gentle "
                         "defaults. THIS IS AN EXPERIMENT KNOB: as of 2026-08-05 a profile dies "
                         "after ~11-14 actions AND ~2 minutes, and those two are confounded "
                         "because pacing has always been ~10 s/action. Run count-only at "
                         "--pace 0.2 to separate them: ~11 tribunales => the budget counts "
                         "ACTIONS (pacing is irrelevant); ~30 tribunales => it is WALL-CLOCK "
                         "(gentle pacing is spending the budget, go faster); fewer than 11 => "
                         "it is REQUEST-RATE (the July model, slow down).")
    ap.add_argument("--desde", default="01/01/2026", help="date Desde DD/MM/YYYY (with --corte)")
    ap.add_argument("--hasta", default="31/01/2026", help="date Hasta DD/MM/YYYY (with --corte)")
    args = ap.parse_args()
    global DOCS, GPS, RESUME, COUNT_ONLY, DOCS_INPAGE, PACE_MULT
    DOCS, GPS, RESUME, COUNT_ONLY = args.docs, args.gps, args.resume, args.count_only
    DOCS_INPAGE = args.docs_inpage
    PACE_MULT = args.pace
    if PACE_MULT != 1.0:
        print(f"[PACE] x{PACE_MULT} — causa {P_CAUSA[0]*PACE_MULT:.1f}-{P_CAUSA[1]*PACE_MULT:.1f}s, "
              f"pag {P_PAGE[0]*PACE_MULT:.1f}-{P_PAGE[1]*PACE_MULT:.1f}s, "
              f"trib {P_TRIB[0]*PACE_MULT:.1f}-{P_TRIB[1]*PACE_MULT:.1f}s")

    print(f"Conectando a Chrome (puerto CDP {args.port})...")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.port}")
        ctx = browser.contexts[0]
        api = ctx.request
        page = find_ojv_page(ctx)
        if not page:
            sys.exit("[ERROR] No encuentro ninguna pestana. Abre OJV en esa ventana.")

        # OJV pops a session keep-alive/expiry dialog every so often. A native dialog PAUSES
        # all page JS while open, so detalleCausaCivil never resolves -> the causa-open hangs.
        # Auto-ACCEPT it (Aceptar) the instant it appears so the scrape rides straight through,
        # session intact, results intact — no reload (which would reset the whole form).
        def _accept_dialog(d):
            try:
                print(f"    [dialog] auto-accept: {d.type} {d.message[:50]!r}")
                d.accept()
            except Exception:
                pass
        for _p in ctx.pages:
            _p.on("dialog", _accept_dialog)
        ctx.on("page", lambda p: p.on("dialog", _accept_dialog))

        # --corte: the script establishes the whole form via keyboard (no manual search).
        if args.corte:
            print(f"[KBD] establishing form: corte {args.corte}, {args.desde}..{args.hasta} "
                  f"(trusted keyboard — no manual search needed)")
            if not establish_form_kbd(page, args.corte, args.desde, args.hasta):
                sys.exit("[ALTO] keyboard establish failed — reach the 'Busqueda por Fecha' tab first.")

        if (not page.query_selector("#fecCompetencia")
                or page.eval_on_selector("#fecCompetencia", "e=>e.value") != "3"):
            sys.exit("[ALTO] La Competencia no es CIVIL (o no veo 'Busqueda por Fecha').")
        tribs = page.eval_on_selector_all(
            "#fecTribunal option",
            "els=>els.filter(o=>o.value&&o.value!=='0').map(o=>({v:o.value,t:(o.textContent||'').trim()}))")
        if not tribs:
            sys.exit("[ALTO] No hay Tribunales cargados. Elige la Corte primero.")
        if args.no_search:
            # Harvest only the tribunal the operator already selected + searched (trusted).
            tv = page.eval_on_selector("#fecTribunal", "e=>e.value") or ""
            tn = page.eval_on_selector(
                "#fecTribunal", "e=>e.options[e.selectedIndex]?e.options[e.selectedIndex].text.trim():''") or ""
            if not tv:
                sys.exit("[ALTO] --no-search: elige un Tribunal y haz la busqueda manual primero.")
            tribs = [{"v": tv, "t": tn}]
        desde = page.eval_on_selector("#fecDesde", "e=>e.value")
        hasta = page.eval_on_selector("#fecHasta", "e=>e.value")
        if not desde or not hasta:
            sys.exit("[ALTO] Faltan las FECHAS (Desde / Hasta).")
        corte = page.eval_on_selector(
            "#corteFec", "e=>e.options[e.selectedIndex]?e.options[e.selectedIndex].text.trim():''")
        if args.skip_tribs:
            if args.skip_tribs >= len(tribs):
                sys.exit(f"[ALTO] --skip-tribs {args.skip_tribs} deja 0 tribunales "
                         f"(esta corte tiene {len(tribs)}).")
            tribs = tribs[args.skip_tribs:]
        if args.max_tribs:
            tribs = tribs[:args.max_tribs]
        print(f"[OK] Corte: {corte} · {len(tribs)} tribunales · fechas {desde}..{hasta}"
              + (f" · proc={args.proc!r}" if args.proc else "") + "\n")

        # recover from any modal left open by a previous (killed) run
        for sel in ("#modalReceptorCivil", "#modalDetalleCivil"):
            if modal_open(page, sel):
                close_modal(page, sel)

        DOWNLOADS.mkdir(parents=True, exist_ok=True)
        out = DOWNLOADS / f"pjud_cdp_{int(time.time())}.json"
        details, t0, count_total = [], time.time(), 0
        fails = 0        # consecutive causa failures -> WAF watchdog (see --max-fails)
        empties = 0      # consecutive empty searches -> soft-block watchdog (--max-empty)
        incomplete = []  # tribunales whose pagination did not reach the end -> .incomplete.json
        lost_form = 0    # consecutive tribunales skipped because the form is gone (exit 5)

        def flush():
            out.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
            # Sidecar, rewritten on every flush so it survives a kill or a Blocked exit: the
            # tribunales that must be re-run. Without it a truncated tribunal is invisible.
            if incomplete:
                out.with_suffix(".incomplete.json").write_text(
                    json.dumps(incomplete, ensure_ascii=False, indent=2), encoding="utf-8")
        for ti, tb in enumerate(tribs, 1):
            if args.max_causas and len(details) >= args.max_causas:
                break
            if not args.no_search:
                if args.corte and not form_ok(page):          # session-expiry popup reset the form
                    print(f"[{ti}/{len(tribs)}] {tb['t'][:40]}  [recover: form reset -> re-establish]")
                    establish_form_kbd(page, args.corte, args.desde, args.hasta)
                if not select_tribunal_kbd(page, tb["v"]):    # TRUSTED keyboard (not select_option)
                    print(f"[{ti}/{len(tribs)}] {tb['t'][:40]}  [skip: could not select tribunal]")
                    # A skip is normally a one-off (cascade not settled). A STREAK means the form
                    # is gone and every remaining tribunal will be skipped too — worker 3 burned
                    # through 9 that way and exited 0 with a cheerful LISTO (2026-07-23). Losing
                    # the form is not a WAF block, so it gets its own exit code: 5 = re-open the
                    # OJV tab, do not rotate the profile.
                    lost_form += 1
                    if lost_form >= 3:
                        flush()
                        print(f"\n[SIN FORMULARIO] {lost_form} tribunales seguidos sin poder "
                              f"seleccionar. El formulario se perdio (recarga -> panel 'Busqueda "
                              f"por Fecha' colapsado, o sesion caida).")
                        print(f"  {len(details)} causas guardadas en {out}")
                        print("  El perfil NO esta necesariamente quemado: cierra la pestana de "
                              "la OJV, reabrela desde www.pjud.cl y reanuda con --resume.")
                        sys.exit(5)
                    pace(P_STEP)
                    continue
                lost_form = 0
                pace(P_STEP)
            print(f"[{ti}/{len(tribs)}] {tb['t'][:40]}"
                  + ("  (harvest current results)" if args.no_search else ""))
            if not args.no_search and not fire_search(page):
                # "sin resultados" is ALSO how a burned profile fails: the searches come back
                # empty instead of showing a rejection page. On 2026-07-22 worker 2 burned
                # after tribunal 4 and then reported 20 consecutive empty tribunales — exit 0,
                # as if the corte were genuinely empty. Small rural tribunales really are
                # empty, so only a STREAK is suspicious; check the WAF before believing it.
                empties += 1
                print(f"      sin resultados{f'  [{empties} seguidos]' if empties > 1 else ''}")
                if empties >= args.max_empty:
                    if waf_blocked(page):
                        flush()
                        raise Blocked(
                            f"{empties} busquedas vacias seguidas + pagina de rechazo F5 · "
                            f"{len(details)} causas guardadas en {out}")
                    print(f"      [warn] {empties} tribunales vacios seguidos, pero sin pagina "
                          f"de rechazo — parecen vacios de verdad")
                    empties = 0
                pace(P_TRIB)
                continue
            empties = 0                                  # a real result set clears the streak
            if COUNT_ONLY:
                cnt, cpages, why = set(), 0, "last"
                expected = total_registros(page)      # ground truth: ALL rows, not just banks
                rows_seen = set()
                while cpages < 80:
                    # Skip blank-rol filler rows: every page carries one, and counting them
                    # inflated 654 real rows to 661 — enough to hide a short page.
                    rows_seen.update(r["rol"] for r in page_rows(page) if r["rol"])
                    for c in page_bank_causas(page):
                        if c["rol"] in cnt:
                            continue
                        cnt.add(c["rol"])
                        details.append({"rol": c["rol"], "caratulado": c["car"],
                                        "fecha": c["fecha"], "tribunal": c["trib"],
                                        "tribunalSel": tb["t"], "tribunalId": tb["v"],
                                        "corte": corte, "rango": f"{desde} a {hasta}"})
                    cpages += 1
                    why = next_page(page)
                    if why != "advanced":
                        break
                    pace(P_PAGE)
                count_total += len(cnt)
                short = expected is not None and len(rows_seen) < expected
                print(f"      -> {len(cnt)} bank C-causas  (running total {count_total})"
                      f"  [{cpages} pag · {len(rows_seen)}"
                      f"{'/' + str(expected) if expected is not None else ''} filas]")
                if short or why == "stuck":
                    note = {"tribunalId": tb["v"], "tribunal": tb["t"],
                            "rango": f"{desde} a {hasta}", "esperadas": expected,
                            "vistas": len(rows_seen), "paginas": cpages, "motivo": why}
                    incomplete.append(note)
                    print(f"      [INCOMPLETO] faltan filas ({note['vistas']} de "
                          f"{note['esperadas']}) · paginador: {why} — este tribunal hay que "
                          f"repetirlo")
                flush()                                  # save the list incrementally
                pace(P_TRIB)
                continue
            seen, pages, kept_trib = set(), 0, 0
            why, rows_seen = "last", set()
            expected = total_registros(page)
            # DB state per tribunal: {rol: (fill_status, detalles)}. Needed for --resume AND to
            # decide full vs reduced doc set per causa (Detalles flag).
            state = causa_state(tb["v"]) if (RESUME or DOCS) else {}
            if RESUME:
                nskip = sum(1 for fs, det in state.values()
                            if fs == "full" or (fs == "scraped" and not det))
                if nskip:
                    print(f"      (resume: {nskip} already done here — skipping)")
            while pages < 80:
                if args.max_causas and len(details) >= args.max_causas:
                    break
                rows_seen.update(r["rol"] for r in page_rows(page) if r["rol"])
                causas = page_bank_causas(page)
                for c in causas:
                    if c["rol"] in seen:
                        continue
                    seen.add(c["rol"])
                    fs, det = state.get(c["rol"], ("", False))
                    if RESUME and (fs == "full" or (fs == "scraped" and not det)):
                        continue                       # already done at the required level
                    if args.max_causas and len(details) >= args.max_causas:
                        break
                    pace(P_CAUSA)
                    try:
                        human_click(page, page.locator("#dtaTableDetalleFecha tbody tr")
                                    .nth(c["i"]).locator("a[onclick*='detalleCausaCivil']").first,
                                    timeout=8000)      # human arc — never .click()
                        page.wait_for_function(
                            "rol=>{var m=document.querySelector('#modalDetalleCivil');"
                            " return m && m.innerText.indexOf('ROL')>=0 && m.innerText.indexOf(rol)>=0;}",
                            arg=c["rol"], timeout=30000)   # detail modal can be slow
                        page.wait_for_timeout(600)
                        rec = scrape_causa(page, api, {
                            "rol": c["rol"], "caratulado": c["car"], "fecha": c["fecha"],
                            "tribunal": c["trib"], "tribunalSel": tb["t"], "tribunalId": tb["v"],
                            "corte": corte, "rango": f"{desde} a {hasta}"}, full=det)
                        if args.proc and norm(rec["header"].get("procedimiento", "")) != norm(args.proc):
                            continue     # scraped but doesn't match the proc filter -> drop
                        details.append(rec)
                        kept_trib += 1
                        flush()                          # incremental save (survives interrupts)
                        print(f"      OK {c['rol']:<13} lit={len(rec['litigantes'])} "
                              f"cuad={len(rec['cuadernos'])} hist={rec['n_historia']} "
                              f"esc={len(rec['escritos'])} rec={len(rec['receptor'])} "
                              f"docs={rec['n_docs']} geo={rec['n_geo']}"
                              f"{' [FULL]' if det else ''}  (tot {len(details)})")
                        fails = 0                        # a success clears the streak
                    except Exception as e:
                        print(f"      ERR {c['rol']}: {str(e)[:70]}")
                        # Clear the modal properly before the next causa, and only count this
                        # as a WAF failure if the page came back clean — a stuck modal makes
                        # every following open fail for reasons that have nothing to do with
                        # the WAF (see clear_stuck_modal).
                        if not clear_stuck_modal(page):
                            print("      [recover] recargando la pagina para desatascarla")
                            try:
                                page.reload(wait_until="domcontentloaded", timeout=30000)
                                page.wait_for_timeout(2500)
                                clear_stuck_modal(page)
                                # The reload returns indexN.php with every search panel COLLAPSED.
                                # Re-open it here so the next tribunal's form_ok/establish has
                                # something usable; without --corte the form itself is gone and
                                # the run cannot rebuild it, so say so plainly.
                                open_fecha_panel(page)
                                if not args.corte:
                                    print("      [recover] sin --corte no puedo reconstruir el "
                                          "formulario tras una recarga — relanza con --corte")
                            except Exception as e2:
                                print(f"      [recover] recarga fallida: {str(e2)[:50]}")
                            break        # results are gone after a reload -> next tribunal
                        # Unattended runs must NOT grind out 30s timeouts for hours after the
                        # profile is spent (that is exactly what happened on 2026-07-22 until
                        # it was killed by hand). A streak of failures -> check for the F5
                        # rejection page, and if it is there, stop while the JSON is intact.
                        fails += 1
                        if fails >= args.max_fails:
                            if waf_blocked(page):
                                flush()
                                raise Blocked(
                                    f"pagina de rechazo F5 tras {fails} fallos seguidos · "
                                    f"{len(details)} causas guardadas en {out}")
                            print(f"      [warn] {fails} fallos seguidos, pero sin pagina de "
                                  f"rechazo — sigo")
                            fails = 0
                pages += 1
                if args.max_causas and len(details) >= args.max_causas:
                    break
                why = next_page(page)
                if why != "advanced":
                    break
                pace(P_PAGE)
            print(f"      -> {kept_trib} causas de banco en este tribunal"
                  f"  [{pages} pag · {len(rows_seen)}"
                  f"{'/' + str(expected) if expected is not None else ''} filas]")
            # Only trust "finished" when the paginator said so AND we saw every row the site
            # claims. A page lost here is a hole nobody notices: the tribunal looks done.
            if why == "stuck" or (expected is not None and len(rows_seen) < expected
                                  and not args.max_causas):
                incomplete.append({"tribunalId": tb["v"], "tribunal": tb["t"],
                                   "rango": f"{desde} a {hasta}", "esperadas": expected,
                                   "vistas": len(rows_seen), "paginas": pages, "motivo": why})
                print(f"      [INCOMPLETO] {len(rows_seen)} de {expected} filas · "
                      f"paginador: {why} — este tribunal hay que repetirlo")
            pace(P_TRIB)

        mins = (time.time() - t0) / 60.0
        flush()
        if COUNT_ONLY:
            print(f"\n[COUNT] {count_total} bank C-causas across {len(tribs)} tribunal(s) "
                  f"in {mins:.1f} min -> {out}")
        else:
            print(f"\n[LISTO] {len(details)} causas en {mins:.1f} min -> {out}")
        if incomplete:
            print(f"\n[INCOMPLETO] {len(incomplete)} tribunal(es) sin paginar hasta el final — "
                  f"NO son un censo:")
            for n in incomplete:
                print(f"    {n['tribunalId']:>4} {n['tribunal'][:34]:36} "
                      f"{n['vistas']}/{n['esperadas']} filas · {n['paginas']} pag · {n['motivo']}")
            print(f"    -> {out.with_suffix('.incomplete.json')}")


if __name__ == "__main__":
    try:
        main()
    except Blocked as e:
        # Exit code 3 = "profile spent", so an unattended wrapper can tell this apart from a
        # crash and rotate the profile instead of retrying. The JSON was flushed before we got
        # here; ingest it, then rename %LOCALAPPDATA%\pjud_cdp aside and re-pass the CAPTCHA.
        print(f"\n[BLOQUEADO] {e}")
        print("  Ingesta ese JSON, luego renombra %LOCALAPPDATA%\\pjud_cdp y pasa el CAPTCHA "
              "de nuevo (una IP nueva NO sirve).")
        sys.exit(3)
