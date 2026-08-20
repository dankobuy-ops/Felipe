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


# ⚠️⚠️ THE HAND IS ALIVE WHILE WORKING AND HALF-DEAD WHILE WAITING. Measured 2026-08-19 from the
# worker's own telemetry, taken with the SAME instrument as the human recording:
#
#     inside a causa        20-22 mousemove/s     (human 25.1)   — essentially on target
#     whole run             16.1-16.7/s
#     a 1-causa run          6.5-7.6/s            — almost entirely non-causa time
#
# The deficit is not in the causa at all; it is in ENTRY, FORM BUILDING and the waits between.
# Back out the arithmetic and the non-causa stretches emit about 5/s against 21/s inside a causa.
# `ojv.WAIT_PRESENCE` already covers the ~20 s search; what it does not cover is this file, which
# owns the form: `set_select_mouse` alone can burn 4 s per select in a 200 ms poll loop, and the
# datepicker walks up to 36 hops. Those are the stretches with a frozen pointer.
#
# So the engine gets the same hook the search wait has. A worker sets PRESENCE once and every
# wait in here runs through it. With no hook set the behaviour is exactly `wait_for_timeout` —
# the pacing itself does not change, only whether a hand is on the page while it elapses.
PRESENCE = None      # set by the worker: callable(page, seconds)


# ── MOTOR vs PACE: the two kinds of spec, and only one of them is tunable ────
#
# ⚠️⚠️ THE DISTINCTION THAT MAKES "OPTIMAL HUMAN" MEANINGFUL (operator, 2026-08-19):
#
#   MOTOR  biomechanics. Does NOT change with how hard a person is working, so there is no
#          "faster" version of it. A rushed person's click is still ~100 ms; a hurried wheel still
#          emits 100 px notches; a hand in a hurry still tops out near 25 moves/s.
#          → HOLD EXACTLY AT MEASURED. Pushing one of these is what makes a session non-human;
#            a 40 ms click hold is not a fast human, it is not a human.
#
#   PACE   the person deciding. Reading times, how long they dwell, how often and how long they
#          stop. One operator spanned 4.6x on causa cycle WITHIN ONE SESSION (p10 6.1 s, median
#          28.3 s).
#          → SAMPLE FROM THE OPERATOR'S OWN DISTRIBUTION, and choose WHICH BAND with FOCUS.
#
# ⇒ "Optimal human" = motor constants exact, pace variables drawn from the fast end of a band the
# operator DEMONSTRABLY PRODUCED. Nothing is extrapolated to a person who does not exist: every
# value shipped is one that was actually observed.
#
# ★ AND IT IS FASTER THAN WHAT WE SHIP. Measured 2026-08-19: the worker runs ~27-30 s per causa
# while the operator's own p25 is 11.1 s and their p10 is 6.1 s. We are not trading fidelity for
# speed here — on the pace variables we are SLOWER than a human and less human at the same time.
#
# ⚠️ THE DECILES BELOW ARE n=1 SESSION EACH, AND TWO SESSIONS DISAGREE BY 17x. The August
# recording put "open -> switch to book 2" at a 2.0 s median; this one puts it at 34.5 s, because
# the operator was reading documents rather than triaging. Same person, same site, different task.
# So: the FAST end of the union of what has been observed is the defensible target, and a second
# recording of the SAME task is worth more than any amount of tuning against this one.
PACE = {
    # name                     deciles p0..p100, seconds        source
    "book1": (2.0, 2.0, 5.1, 6.1, 10.1, 13.2, 18.2, 34.5, 55.6, 114.3, 241.9),
    #   ⚠️ p0/p10 are the AUGUST session's 2.0 s median, kept because it was really observed and is
    #   the fastest this act has ever been seen done. The rest is 2026-08-19 (n=24).
    "book2": (1.0, 1.0, 1.0, 2.0, 2.0, 3.0, 4.0, 10.1, 12.1, 15.2, 64.7),      # n=24
    "silence": (2.0, 2.0, 2.0, 2.2, 4.0, 6.1, 8.1, 11.1, 16.3, 28.3, 60.4),    # n=129
    "list": (2.0, 3.0, 6.1, 8.1, 11.1, 15.2, 22.3, 34.5, 55.6, 78.0, 180.0),   # causa->causa, n=29
}

# The quantile band to draw pace variables from. (0.0, 1.0) is the whole operator; (0.0, 0.25) is
# the operator on their quickest stretches — still their own behaviour, just the fast quarter.
FOCUS = (0.0, 1.0)
FOCUS_ON = False   # --focus: off keeps the August two-number spans (today's behaviour)


def pace(name):
    """One sample of a PACE variable, from the operator's deciles within the FOCUS band.

    ⚠️ Interpolates the EMPIRICAL deciles rather than fitting a curve. We have one session per
    variable; a lognormal fitted to it would add confidence we have not earned, and would smooth
    away the long tail that is the most distinctive part of the shape.
    """
    d = PACE.get(name)
    if not d:
        return 0.0
    lo_q, hi_q = FOCUS
    q = (lo_q + random.random() * max(1e-6, hi_q - lo_q)) * 10.0
    i = min(9, int(q))
    lo, hi = d[i], d[i + 1]
    return lo + (hi - lo) * (q - i)


# ── THE DUTY CYCLE: a person STOPS, and we never did ─────────────────────────
#
# ⚠️⚠️ THE SPEC WE DID NOT KNOW EXISTED, AND THE ONLY ONE WHERE WE ARE CATEGORICALLY WRONG.
# Measured 2026-08-19 by recording a worker with the SAME instrument used on the operator:
#
#     worker   93% of seconds active,  7% silent    21.0/s active    19.5 per WALL second
#     human    41% of seconds active, 59% SILENT    25.1/s active    11.6 per WALL second
#
# Per ACTIVE second we sit at 84% of the human, which is the number this project quoted for weeks
# while concluding "we are under, emit more". Per WALL second we emit 68% MORE than a human,
# because we almost never stop. Every spec we had been tuning was a RATE; this is a RHYTHM.
#
#     human    129 silences in 40 min   median 6.1 s   p90 28.3 s   max 60 s   3.2 stops/min
#     worker     5 silences in 3.6 min  median 3.0 s   p90  8.2 s   max  8 s
#
# ⚠️ FIX IT BY STOPPING, NEVER BY MOVING SLOWER. The human's rate WHILE MOVING (25.1/s) is HIGHER
# than ours (21/s). Lowering the rate gives the same wall-clock average and a completely different
# distribution — and the distribution is the thing being measured.
#
# ⚠️ SAMPLED FROM THE MEASURED DECILES, not from an invented parametric shape. We have one 40-minute
# session; a lognormal fitted to it would add confidence we have not earned. Interpolating the
# empirical deciles reproduces what was actually observed, including the long tail (one stop of a
# full minute) that any tidy distribution would smooth away.
SILENCE_DECILES = (2.0, 2.0, 2.0, 2.2, 4.0, 6.1, 8.1, 11.1, 16.3, 28.3, 60.4)
SILENCE_PER_MIN = 3.23        # stops per minute of WALL clock, measured
SILENCE_MEAN = 10.9           # mean stop, seconds, measured
DUTY_TARGET = 0.59            # fraction of WALL seconds the operator was completely silent
DUTY_HUMAN = False            # --duty human: insert real stillness. Off = today's always-on hum.

# ⚠⚠ THE GAP BETWEEN STOPS IS IN *ACTIVE* SECONDS, AND 3.23/MIN IS IN *WALL* SECONDS. Arming the
# next stop with `expovariate(SILENCE_PER_MIN / 60)` looks obviously right and is wrong by 40%:
# re-arming after a stop means the gap only ever elapses while we are working, so its mean must be
# the mean ACTIVE stretch (7.6 s), not the mean wall interval (18.6 s). Ship the obvious version
# and you get 2.04 stops per wall minute against a measured 3.23 — the identical shortfall the
# scheduler was written to fix. 129 stops over 40 min with 1,406 s of them silent leaves 994 active
# seconds; 994/129 = 7.7 s, which is what the formula below reproduces from the duty target.
ACTIVE_GAP_MEAN = SILENCE_MEAN * (1.0 - DUTY_TARGET) / DUTY_TARGET      # 7.6 s at FOCUS off


def mean_stop():
    """Mean stillness IN THE CURRENT FOCUS BAND, by integrating the deciles across it.

    WARN: THE GAP MUST FOLLOW THE BAND, AND A CONSTANT CANNOT. `ACTIVE_GAP_MEAN` above is derived
    from SILENCE_MEAN = 10.9, the mean of the WHOLE distribution. `--focus fast` samples the
    operator's p0-p25 band, where every stop is 2.0-2.1 s, and a fixed 7.6 s gap then re-arms far
    too soon: measured 2026-08-20 over 121 stops, 4.8 stops/min against the operator's 3.23, while
    the silent fraction collapsed to 16% against 49% at focus off. The setting preserved NEITHER
    quantity it should.

    WARN: FREQUENCY IS THE INVARIANT, NOT THE DUTY FRACTION -- see silence_secs(): an operator
    working fast stops just as OFTEN and stops BRIEFLY. So the gap absorbs the change: a shorter
    stop must be followed by a LONGER wait, keeping starts-per-minute at SILENCE_PER_MIN.
    """
    lo, hi = FOCUS
    n, tot = 200, 0.0
    for j in range(n):
        q = (lo + (j + 0.5) / n * (hi - lo)) * 10.0
        i = min(9, int(q))
        a, b = SILENCE_DECILES[i], SILENCE_DECILES[i + 1]
        tot += a + (b - a) * (q - i)
    return tot / n


def active_gap():
    """Mean ACTIVE seconds between stops, so that stops START at SILENCE_PER_MIN per wall minute.

    60/SILENCE_PER_MIN is the mean wall interval between the STARTS of two stops (18.6 s). We
    re-arm when a stop ENDS, so the gap we wait is that interval minus the stop we just took.
    At FOCUS off this returns 18.6 - 10.9 = 7.7 s, reproducing the measured constant above; at
    FOCUS fast it returns 18.6 - 2.0 = 16.6 s, which keeps 3.23 stops/min instead of 4.8.
    """
    return max(0.5, 60.0 / SILENCE_PER_MIN - mean_stop())


def silence_secs():
    """One stillness duration, from the operator's distribution within the FOCUS band.

    ⚠️ FREQUENCY IS THE SIGNATURE, DURATION IS THE PACE. An operator working fast still stops just
    as often — they stop BRIEFLY. My first implementation sampled the whole curve including the
    60-second tail, which made a focused worker behave like a distracted one. FOCUS shortens the
    stops; it must never reduce how many there are.
    """
    return pace("silence")


DRAWN = []      # every stillness actually taken, for drawn-vs-measured diagnosis


def still(page, secs):
    """Do NOTHING for `secs`. No pointer, no drift, no hooks — genuinely motionless.

    ⚠️ RECORDS WHAT IT ACTUALLY TOOK, in DRAWN. Two diagnoses of the duty shortfall were wrong
    because both reasoned about the mechanism from the MEASURED output, on 12-18 stops a run —
    far too few to tell a 4.1 s mean from a 5.5 s one. Logging the draws turns "why is the output
    short?" into a subtraction: draws matching the operator with the measurement short means the
    loss is downstream; draws already short means it is the sampler. Guessing cost two runs.

    ⚠️⚠️ THIS MUST NOT GO THROUGH `pause()` OR THE PRESENCE LOOP, and that is the entire point.
    Every other wait in this engine exists to keep a hand on the page; this one exists to take the
    hand OFF it. Routing it through presence would turn the fix into more of the very thing it is
    correcting — and it is exactly the mistake the shape of this file invites, since `pause()` is
    the obvious call to reach for.
    """
    DRAWN.append(round(secs, 2))
    page.wait_for_timeout(int(secs * 1000))


def waiting_for_site(page, secs, presence=None):
    """A wait for the MACHINE, not for the person — so the hand often just rests.

    ⚠️⚠️ WE HAD THIS BACKWARDS. Every wait in this project was filled with pointer motion on the
    reasoning that a frozen pointer is a tell. But look at what the operator actually does: they
    move while READING (active, 25/s) and they go STILL while waiting for a page (passive). Filling
    a 20-second search wait with continuous motion is not what a person does with the twenty
    seconds after they click Buscar — a lot of them take their hand off the mouse.
    ⇒ Sometimes rest, sometimes stay alive. `presence` is the fallback that keeps the old
    behaviour when the duty cycle is off, so this is one variable, not two.
    """
    # ⚠⚠ NO `min(secs, ...)` HERE, AND NO LOCAL PROBABILITY EITHER. Both were bugs, found in
    # that order. The cap clipped every long draw down to the 2-20 s wait it sat inside, killing
    # exactly the tail that makes the distribution human. Removing it exposed the second one: a
    # private `random() < 0.55` here meant two uncoordinated sources of stillness, neither aware
    # of the wall clock. A machine wait is simply a BOUNDARY — offer it to the scheduler and let
    # one rate govern the whole session. Stillness EXTENDS time; it does not fit inside the wait.
    maybe_still(page)
    if secs > 0.05:
        if presence is not None:
            presence(page, secs)
        else:
            # ⚠ THE TAIL WAIT BELONGS HERE, NOT AT FUNCTION LEVEL. It was the orphaned last line
            # of the old `still()` body, absorbed when this function was inserted above it, and it
            # ran unconditionally — so the presence path waited `secs` through `pres.run` and then
            # `secs` AGAIN on a raw timeout. `ojv._hold` hands us the full wait expecting us to
            # consume it exactly once; every search wait was double-length. A mechanical insertion
            # is not safe just because it compiles — the same lesson `pause()` already carries.
            page.wait_for_timeout(int(secs * 1000))


_NEXT_STOP = [None]     # time.monotonic() at which the next stillness comes due


def arm_duty():
    """(Re)start the stillness clock. Call once when a run begins."""
    _NEXT_STOP[0] = time.monotonic() + random.expovariate(1.0 / active_gap())


def maybe_still(page, window_secs=None):
    """Stop, if a stop is DUE. Call at a natural boundary between actions.

    ⚠⚠ THE RATE IS AGAINST THE WALL CLOCK, AND THAT IS THE WHOLE FIX. This used to roll
    `SILENCE_PER_MIN * window_secs / 60` at each call, which delivers 3.2 stops per minute of
    COVERED WINDOW — and the call sites only ever covered reads and causa loads. Every other
    stretch of the session (search waits, form building, navigation, ingest, closing modals) had
    probability ZERO, so the session-wide rate came out at 1.86/min against the operator's 3.23.
    Measured: 11 stops in 5.9 min, 19% silent against a 59% target, with the sampler itself
    verified faithful over 166 offline draws (mean 12.3 s vs the operator's 10.9).

    ⚠⚠⚠ IT IS THE ACTIVE-SECONDS-VERSUS-WALL-SECONDS ERROR, FOR THE THIRD TIME IN THIS
    PROJECT — committed inside the fix for the second one, by the author of the handbook entry
    warning about it. A rate is meaningless until you say what it is per. Here the denominator
    silently became "seconds a call site happens to bracket" instead of "seconds elapsed".

    Now a deadline accrues in real time and is discharged at the next boundary, so an uncovered
    stretch builds debt instead of dropping its stops. `window_secs` is ignored and kept only so
    call sites need not change; the scheduler alone owns the rate.

    ⚠ ONLY AT BOUNDARIES, still. A person does not freeze mid-drag or halfway through reaching
    for a control; they stop between things — after closing a record, after a search returns,
    before deciding what to open next. Sprinkling stillness inside an action would produce the
    right histogram out of impossible behaviour, which is how this project got the metronome
    keyboard. The scheduler sets WHEN; the call sites still decide WHERE.
    """
    if not DUTY_HUMAN:
        return 0.0
    now = time.monotonic()
    if _NEXT_STOP[0] is None:
        arm_duty()
        return 0.0
    if now < _NEXT_STOP[0]:
        return 0.0
    s = silence_secs()
    still(page, s)
    # ⚠ Re-arm from AFTER the stop, which is exactly why ACTIVE_GAP_MEAN and not SILENCE_PER_MIN.
    _NEXT_STOP[0] = time.monotonic() + random.expovariate(1.0 / active_gap())
    return s


def pause(page, ms):
    """Wait `ms`, with the pointer alive if a worker has installed PRESENCE.

    ⚠️ NEVER swallow the wait itself. This replaces `page.wait_for_timeout(ms)` and must wait just
    as long — the point is what happens DURING it, not how long it is. A presence callback that
    returns early would quietly shorten every settle in the form path.
    """
    if PRESENCE is None:
        page.wait_for_timeout(ms)
        return
    try:
        PRESENCE(page, ms / 1000.0)
    except Exception:
        # ⚠️ page.wait_for_timeout, NOT pause() — the fallback must never re-enter this function.
        # A bulk rewrite of `page.wait_for_timeout(...)` -> `pause(page, ...)` caught this very
        # line and turned the fallback into INFINITE RECURSION: every presence hiccup would have
        # become a stack overflow mid-run. Caught by reading the diff; a mechanical edit is not
        # safe just because it compiles.
        page.wait_for_timeout(ms)


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



def read(pres, target, span, selector=None, name=None):
    """Spend `span` seconds READING something, the way a person does: pointer over it, moving.

    This is the only kind of wait in this worker other than waiting for the site. It is not a
    delay with motion bolted on — the aim comes first, so every second of it lands on the content
    and produces the `mouseover` stream that a hand produces and a timer never will.
    """
    pres.aim(target, selector)
    lo, hi = span
    # ⚠️ `name` selects the operator's own measured distribution for THIS act; without it we fall
    # back to the two-number span from the August session. FOCUS then picks which part of that
    # distribution to live in — the whole operator, or the quarter of the time they were quickest.
    # SPEED still multiplies, so the old ramp keeps working, but it should be left at 1.0 when
    # FOCUS is doing the work: two knobs on the same quantity is how a result becomes
    # uninterpretable, which is the mistake `--speed` has already caused twice here.
    secs = pace(name) * SPEED if (name and FOCUS_ON) else jitter(lo * SPEED, hi * SPEED)
    # ⚠️ THE DUTY CYCLE GOES HERE, AND ONLY HERE. `read()` is the one call that means "the person
    # is looking at something" — which is exactly when a human stops moving the mouse. Between
    # closing one record and opening the next, or while taking in a book, they go COMPLETELY
    # STILL, 3.2 times a minute, for a median of 6 s and sometimes a full minute.
    # Every other wait in this engine is mid-action: a person does not freeze halfway through
    # reaching for a control, and putting stillness there would produce the right histogram out of
    # impossible behaviour — which is how this project got the metronome keyboard.
    still_for = maybe_still(target, secs)
    if still_for:
        secs = max(0.0, secs - still_for)      # the stillness IS part of the looking, not extra
    if secs > 0.05:
        pres.run(secs)


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
            pause(page, 400)
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
            pause(page, 800)
    t0 = time.time()
    while time.time() - t0 < settle:
        pause(page, 200)
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
            pause(page, 150)
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
        pause(page, random.randint(180, 380))
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
    pause(page, 500)
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
