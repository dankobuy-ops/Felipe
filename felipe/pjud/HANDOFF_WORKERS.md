# PJUD — Worker architecture handoff (2026-08-07)

> ## ⚠️⚠️ START AT [00. STATE OF PLAY — 2026-08-20](#00-state-of-play--2026-08-20-read-this-before-section-0)
>
> Then [000. WHAT I WOULD HAVE WANTED TO KNOW](#000-what-i-would-have-wanted-to-know-before-the-2026-08-19-session), then
> [THE SPLIT — SPECS vs SETTINGS](#-the-split--specs-vs-settings-2026-08-19).
>
> Since 2026-08-19 there is **one behavioural engine** (`human_engine.py`) and the workers are
> only jobs. Everything in this file that describes a worker's *behaviour* is history: how it
> moves, types, waits and clicks now comes from one place, for all of them.
>
> **SPECS** = how human it is. Always the best we have. **SETTINGS** = what job, where, how fast.
>
> The section that forced it shows worker A, B and C still typing into `readonly` date fields —
> an act no user can perform — three days after worker H stopped.

Companion to `HANDOFF_CDP.md`, which remains the reference for **the site and the WAF** (entry
gates, block tiers, the corte-change burst, the two-button trap). This file covers **the workers**:
what they do, why they are shaped this way, and every trap that cost real time.

**⚠️ Treat every measurement here as DATED.** The OJV is being actively changed — "Corte = Todos"
did not work before 2026-08-06 and does now. Re-verify anything load-bearing before relying on it.

---

## 00. STATE OF PLAY — 2026-08-20 (READ THIS BEFORE SECTION 0)

**Section 0 below is from 2026-08-17 and is superseded on the points listed here.** It is still the
best guide to the traps; it is no longer the best guide to the numbers.

### The score

> **Sustained NEW records per hour, without tripping.** See `felipe/CLAUDE.md` → "The ultimate
> goal". The operator's recording is an INSTRUMENT for finding variables and their plausible
> ranges — it is not a target, and matching it is not the job.

⚠️ **The tell that you have drifted:** your success metric can be computed offline, from files,
with the site switched off. Then you are scoring fidelity, not results.

### Corpus (after the 2026-08-20 ingest)

    6,225 causas   6,063 with a cuaderno-2 historia   4,387 cuaderno-2 documents in Drive
    by month of ingreso: 2026-07 = 3,679   2026-06 = 2,132   2026-08 = 25   2026-05 = 16

⚠️ **August is virtually unswept nationally** (25 causas). July is picked over. That matters more
than any pacing setting — see "capacity vs delivery" below.

### What one worker can do, and it is the SITE's floor

    8.6 – 9.0 s per open   =   6.7 – 7.0 opens/min productive (excluding entry)

Measured 2026-08-20 at `--speed 0`, and identical to the 8–9 s floor found weeks earlier with
reading merely ramped to a tenth. **`--speed 0` is the fastest SETTING, not the fastest RESULT.**
Cutting reading 3 s → 2.2 s once bought 0.3 s; a tenth → zero bought nothing measurable.

⇒ **There is nothing left to find on the speed axis for one worker.** What remains is the site
answering plus the motor work we refuse to cut.

### What a fleet can do

| fleet | steady-state aggregate | per worker | 25 min outcome |
|---|---:|---:|---|
| 4 workers | 26.2 req/min | 6.55 | clean, zero trouble |
| 8 workers | 52.9 req/min | 6.61 | clean, zero trouble |

**Workers scale LINEARLY in steady state** — 2.02× aggregate for 2× the fleet. `rate_watch.py`'s
header says the opposite ("it goes DOWN as workers are added"); that was the ENTRY GATE, not
contention. ⚠️ Per-OPEN time does drift (8.6–11.8 s at four, 9.7–12.2 at eight) and **that may be
this house's uplink rather than the site** — a local measurement of unknown cause, not to be
carried into a remote plan.

⚠️ **`--speed` is no longer a rate control.** It spans ~13% of the request rate (23 → 26 req/min at
four workers) where in August it spanned 23 → 56. **FLEET SIZE is the rate control now.** Design
every rate experiment on worker count.

### ⚠️⚠️ CAPACITY IS NOT DELIVERY

    4 workers    589 opens →  335 NEW   57% useful
    8 workers   1008 opens →  330 NEW   33% useful

Twice the fleet, twice the opens, **the same records** — the second arm re-swept a window the first
had just harvested. Capacity scales; delivery is bounded by **unharvested territory**.

⇒ On a picked-over window, more workers buy nothing. The gain comes from unswept months or from
`--fill` (~95% useful against a sweep's 33%).
⇒ ★ On opens/min the 8-worker arm is a 1.7× triumph. On the actual goal it delivered five records
FEWER. **Scoring on opens would have concluded "add workers" and been exactly wrong.**

### The specs, and what each is worth

| spec | setting | effect on throughput | effect on BLOCKS |
|---|---|---|---|
| `--speed` | 0 = top | at the floor; nothing left | **unmeasured** |
| `--duty human` | 3.23 stops/min, 49% silent | **−54%** (2.66 → 1.23 opens/min) | **unmeasured** |
| `--focus fast` | p0–p25 band | +8% alone | **unmeasured** |

⚠️ **THE SURVIVAL COLUMN HAS EXACTLY ONE ENTRY** (2026-08-20): solo, `--speed 0 --duty off`, THREE
HOURS, 1,129 opens, one lost click, address verified clean before and after. The fastest thing we
have is not self-destructive at solo scale.
⚠️⚠️ **It is still empty for every OTHER configuration and for every fleet size.** No run has
compared block rates BETWEEN two spec configurations. The duty cycle costs half the throughput on
the strength of "the operator did it" and **its benefit has never been measured once**.

⚠️ **`--focus fast` SHRINKS the duty cycle, it does not make it free.** `silence_secs()` samples
through the FOCUS band, so fast draws every stop from the p0–p25 floor: 121 stops, all 2.0–2.1 s,
16% silent against focus-off's 49%. Two behaviours on one knob.

### Site status — THE SITE WAS NEVER DOWN; THIS ADDRESS WAS BLOCKED (see next section)

`site_health.py` reports **OJV-NO-FORM**: `indexN.php` loads and renders, but carries no
`#fecCompetencia`, no gate button, no `<form>` and no `<select>`. Its entry points are now
`ingresoDemanYEscritos`, `consultaUnificada`, `consultaEscritosIndepen`,
`consultaAudienciasLaboral`, `consultaCiudadana`. It is also **intermittent** — served once, then
no tab at all a minute later.

⚠⚠ **RESOLVED 2026-08-20 11:56: that is what a BLOCKED ADDRESS is served.** A phone on a
different network reached the form instantly, and the tethered PC reports FORM twice in a row. No
redeployment, no outage — an eight-hour IP block that serves a healthy page with the search form
removed. `_reach_ojv` and `find_form` need NO changes.

### Struck or suspended by the 2026-08-19/20 session

- ~~"The binding limit is the AGGREGATE REQUEST RATE PER ADDRESS."~~ That test moved `--speed`,
  which moved the rate AND the pointer (6–9 mousemove/s at top speed against 15–20). Two variables,
  one read. We have since held 52.9 req/min clean.
- "It is the SEARCH rate that binds." — **UN-SUSPENDED 2026-08-20**: the site never went down, so
  the August arm did trip a real block and the deaths need a cause again. Still NOT proven (the
  arms differed in window AND time), but it is the leading hypothesis once more.
- ~~"56 req/min kills, 23 is safe."~~ Properties of a BUILD, not of the site. `--speed 0` produced
  27 req/min on 2026-08-20 where it produced 56 on 08-17.
- ~~"Matching the duty cycle is worth halving throughput for."~~ Cost measured, benefit never.
- ~~"www.pjud.cl offers exactly one OJV anchor."~~ `/home/` is back; it offers both.

### The tools, and which question each answers

| question | tool |
|---|---|
| is the site up, and what does it serve? | `site_health.py` (`--watch N`) |
| what rate is the fleet producing RIGHT NOW? | `rate_watch.py --mins 8` — **read the `result requests alone` line, not the total** |
| how did an arm score? | `expduty_score.py --new` — **run it BEFORE the ingest** |
| what does the worker emit vs the operator? | `human_profile.py --file A --vs B` |
| did the data actually land? | `ingest_worker_h.py --dry`, then count in Neon |
| how many workers can this address carry? | `Experimento_Fleet.ps1 -Workers N -Speed S` |
| which spec setting is worth what? | `Experimento_Specs.ps1` |

---

---

# ★★★★★ THE BLOCK IS A **DEGRADED PAGE**, NOT A REFUSAL — AND IT LASTS HOURS (2026-08-20)

The operator tried the OJV **from a phone** while this machine still could not use it, and it worked
instantly. The PC was then tethered through that phone — a new address — and `site_health.py`
reported **FORM** twice in a row, immediately.

    residential IP, 01:04 -> 09:11+ (8+ hours)   SITE OJV-NO-FORM   consistently
    phone-tethered IP, 11:56 / 11:58            SITE FORM          immediately, twice

**The site was never down. We were blocked, by address, for more than eight hours.**

## ⚠️⚠️ WHAT A BLOCK LOOKS LIKE HERE — this is the finding

A blocked address is served `indexN.php` **that renders perfectly and is missing the search form**:

    title "Oficina Judicial Virtual"   menu drawn   carousel rotating   heading "Invitado"
    #fecCompetencia .......... ABSENT
    gate buttons ............. ABSENT
    <form> ................... 0
    <select> ................. 0
    entry points present ..... ingresoDemanYEscritos, consultaUnificada,
                               consultaEscritosIndepen, consultaAudienciasLaboral,
                               consultaCiudadana

**No rejection page. No captcha. No error. No HTTP failure.** The page is healthy, live and
plausible — it simply cannot be used to search. This is the quietest block signature this project
has ever seen, and it is indistinguishable from a site redesign unless you compare two addresses.

⇒ ★ **`site_health.py` is therefore a BLOCK DETECTOR, and that is its real value.**
`OJV-NO-FORM` = this address is blocked. `FORM` = it is not. One check, two page loads, no search.
Run it before blaming a fleet, and run it from a second address before believing either answer.

## ⚠️⚠️⚠️ I HAD THE RIGHT ANSWER AND TALKED MYSELF OUT OF IT

The sequence is worth keeping intact, because the mistake is subtle and I made it *while being
careful*:

| time | evidence | what I concluded | verdict |
|---|---|---|---|
| 01:04 | six sessions die in 13 s | the search rate binds | plausible, unproven |
| 02:21 | canary on a known-good window cannot enter | **the address is blocked** | **CORRECT** |
| 03:24 | attached: OJV open, healthy, DOM changed | "the site was redeployed, we were never blocked" | **WRONG — retracted a correct conclusion** |
| 11:56 | a second address works instantly | it was an address block all along | confirmed |

At 03:24 I attached to the browser — which was the right instinct, and which this file now
recommends in two places — saw a **healthy rendered page**, and took that as proof we were not
blocked. It was proof of nothing of the kind.

⇒ ⚠️ **"THE PAGE LOOKS FINE" IS NOT EVIDENCE THAT YOU ARE NOT BLOCKED.** The absence of a rejection
page is not the absence of a block. A modern WAF can answer 200 with a page that is complete,
styled, interactive and quietly missing the one control you need.
⇒ **The only reliable test is a SECOND ADDRESS.** Everything else — page content, HTTP status,
timing, retry behaviour — is consistent with both explanations. One phone settled in thirty seconds
what eight hours of local evidence could not.
⇒ ★ And note the shape of the error: at 02:21 I inferred a block from a FAILURE and was right; at
03:24 I inferred no-block from an APPEARANCE and was wrong. Failures are evidence about the world.
Appearances are evidence about what the other side chose to show you.

## What this restores, and what it does not

- ~~"The site was redeployed."~~ **WRONG.** There was no deployment. `/home/` reappearing and
  `#fecCompetencia` vanishing were both the block.
- **"It is the SEARCH rate that binds" is UN-SUSPENDED** — the August arm did trip a real block, so
  the deaths need a cause again. ⚠️ Still NOT proven: the July and August arms differed in window
  AND in time, and the search-rate story remains the leading hypothesis rather than a finding.
- **"The address recovered in 25-70 minutes"** — wrong by an order of magnitude. **8+ hours**, and
  we never saw it recover; we changed address instead.
- **The cost model I retracted was right.** A tripped experiment costs the ADDRESS, not the causas
  the arm collected. At 8+ hours and the July arm's delivered rate, the August arm cost on the
  order of **6,000 records of opportunity** against the 71 it collected. I retracted that estimate
  when I believed the outage story; it stands, and it was an order of magnitude too small.

## ⚠️ What this does to experiment design

**A trip costs eight hours of address.** That makes every rate experiment far more expensive than
last night assumed, and it rules out the ladder-until-it-breaks approach on a single address.

⇒ **Never probe a wall on the address you need for production.**
⇒ **Two addresses minimum**: one to work, one to test. The phone tether is now a second address and
should be treated as the *test* one, not the work one.
⇒ **Check `site_health.py` before AND after every arm.** Before, so a degraded start is not read as
a result; after, so a trip is detected in one check instead of eight hours of canaries.
★ **How the address was recovered: the operator RESET THE HOME ROUTER and got a new IP.** The phone
was only the diagnostic — it proved the site was up and the block was per-address. The fix was a new
residential address on the SAME line, so bandwidth, latency and everything else about the uplink are
unchanged, and measurements taken before and after the reset ARE comparable.

⇒ **IP rotation clears this block immediately.** An eight-hour wall became a router reset — worth
knowing before ever planning a long cool-off again, and the cheapest second address there is.
⚠️ It also means the old address is burnt rather than healed: we still do not know how long the
block runs, only that it exceeded eight hours and that we stopped waiting.

---

---

---

# ★★★★★ RUNG 1 — THREE HOURS SOLO AT TOP SPEED, CLEAN (2026-08-20)

The first entry the survival column has ever had.

    1 worker  --speed 0 --duty off --focus off  --window 480x300
    01/07/2026 .. 31/07/2026, courts 0-229, fresh home IP, 12:10 -> 15:10

    1,129 opens   1,033 kept   95 gated   109 searches
    180.1 min lifespan, 171.7 min productive
    6.37 opens/min productive   =   9.43 s per open
    6.9 req/min aggregate

    trouble: ONE lost click in three hours (0.09% of opens)
    site_health BEFORE: FORM      site_health AFTER: FORM      -- the address is clean

★ **Worker A's all-time local best was 375 opens in 190 minutes. This is 1,129 in 180.** Three
times the opens in less time, with one lost click.

## What it settles

**The fastest configuration we have is not self-destructive at solo scale.** Three hours, no duty
cycle, no reading time, and the address is provably as clean at the end as at the start — checked,
not assumed. Yesterday nobody could say that about any configuration.

**The 8-9 s floor is real and it is the SITE's.** 9.43 s per open here, against 8.6-11.8 s for
workers inside a 4-fleet and 9.7-12.2 inside an 8-fleet, all on the same line. A solo worker lands
in the MIDDLE of both ranges. ⇒ **Contention up to eight workers is invisible**, and per-open time
is set by the site, not by the fleet or the uplink.

⚠️ **The one trouble event was OURS, and the instrumentation proved it rather than guessing:**

    [why] busy=False {'modal': True, 'modalShown': False, 'rows': 101, 'links': 100, 'spinners': []}
    [net] 0 responses since the click, causaCivil.php=0 :: []
          our click produced no causa request — one causa lost, session untouched

**Zero network responses after the click** — it never reached the site, so it cannot have been a
refusal. The next row opened four seconds later. Without that `[net]` line this is the exact
signature that has been logged as a block for months.

## ⚠️ The 480x300 window is VERIFIED, not merely tolerated

1,129 opens at a **205 px viewport** with zero click refusals and zero covered targets. The
previous smallest confirmed window was 744x345, and the 760x440 geometry once refused 3.5% of rows;
this one lost 0.09%. ⇒ **Horizontal scrolling really was the fix, and it holds far below any size
this project had tested.** `--window 480x300` is now the default.

## Delivery, and why the number looks small

    1,129 opened   781 already banked   348 NEW   (31% useful)   1.9 new records/min

⚠️ **31% is the WINDOW, not the worker.** July has now been swept by a 4-worker arm, an 8-worker arm
and this run in sequence; useful% has fallen 57% -> 33% -> 31% exactly as depletion predicts.

⚠️ **And do not read "348 beats the fleets' 335 and 330" as a win for solo.** Per minute the fleets
delivered ~13 new records against this run's 1.9 — seven times more. Solo won the total only by
running seven times longer. Compare rungs per unit time, or the ladder tells you the opposite of
the truth.

## What it does NOT settle

- **Nothing about the fleet.** Rungs 4 and 8 have not been run on these specs.
- **Nothing about the duty cycle.** This arm had duty OFF; the comparison that would price it has
  still never been run.
- **Nothing about the request-rate wall.** One worker makes 6.9 req/min. The August fleet died at
  21 req/min and the July 8-fleet held 52.9 — this run does not go near either.

---

# THE LADDER PROTOCOL — 1, then 4, then 8, ALL ON ONE SET OF SPECS (2026-08-20)

⚠️⚠️ **LAST NIGHT'S 4- AND 8-WORKER ARMS ARE NOT COMPARABLE TO THE SOLO RUN, OR TO EACH OTHER'S
SUCCESSOR.** They differ from it in three ways at once — a different IP (since blocked), a
1440x900 window instead of 480x300, and several hours of clock. A ladder whose rungs differ in
their specs measures the specs, not the ladder. The operator called this before the second rung was
launched, which is the only reason it did not become another suspended finding.

⇒ **Re-run 4 and 8 with the SOLO RUN'S EXACT SPECS.** The solo arm is the baseline; the other rungs
exist to be compared against it.

## Held constant across all three rungs

    --speed 0  --duty off  --focus off      the fastest configuration we have
    --window 480x300                        verified across 313 opens, 0 refusals
    --desde 01/07/2026 --hasta 31/07/2026   dense window; a sparse one inverts the request mix
    --gate-release form
    courts 0-229, split evenly by rung
    the SAME address, unrotated for the whole ladder
    --max-minutes 180                       so survival is comparable, not just rate

## Read from each rung

| quantity | how |
|---|---|
| productive rate | first open -> last open, **excluding entry** — the `DONE` line divides by lifespan and understates by ~20% |
| steady-state req/min | `rate_watch.py --mins 8` late in the run, after every shard has arrived |
| trouble | `expduty_score.py` — and ⚠️ **`site_health.py` before AND after**, because a trip and a clean finish look identical in the log |
| delivery | `expduty_score.py --new`, **before the ingest** |

## ⚠️ What NOT to conclude from the ladder

- **Not delivery.** Each rung re-sweeps a window the previous one just banked, so useful% falls by
  construction. Score the ladder on RATE and TROUBLE; delivery needs fresh territory.
- **Not remote behaviour.** Everything here shares one uplink and one address class.

## DEFERRED UNTIL THE LADDER IS DONE: close the www.pjud.cl tab after entry

Every worker holds TWO tabs for its whole shift — the OJV it works in, and the `www.pjud.cl` it
walked in through, idle from the moment entry succeeds. Measured live on 2026-08-20:

    port 9561:  [0] .../indexN.php#modalDetalleCivil   working
                [1] https://www.pjud.cl/               idle since entry

**Safe to close**, on three checks:
- Nothing uses it after entry. Both `_only_tab` calls sit inside the entry RETRY loop, before
  success, and `worker_h` never scans `ctx.pages` or navigates to pjud.cl again.
- The recovery path is unaffected. `walk_in` IS called a second time (worker_h:1242) and picks its
  launcher with `next(q for q in ctx.pages if "pjud.cl" in q.url)` — which matches the OJV host
  too, and **`pages[0]` is already the OJV tab**. Re-entry reuses that tab either way.
- `_only_tab`'s own docstring argues for it: *"a leftover tab does not merely clutter the window —
  it silently swallows every click aimed at the page underneath it."*

**Worth ~50-100 MB per worker**, which is 0.4-0.8 GB across eight — and RAM is exactly what gates
the top of the ladder.

⚠️ **DO NOT LAND IT MID-LADDER.** Rung 3 must run on the same worker code as rungs 1 and 2, or the
comparison breaks the same way last night's arms did. One line after `walk_in` returns
(`ojv._only_tab(ctx, p)`), then a solo run to confirm, then it is available for the fleet.

⚠️ **Separately, that `next(...)` selection is fragile**: it matches both `www.pjud.cl` and
`oficinajudicialvirtual.pjud.cl` and depends on a tab order that is NOT creation order (the OJV tab
is created second and appears first). A re-entry that grabs the wrong tab is a silent failure of
exactly the kind this file keeps rediscovering. Worth tightening independently of the tab close.

## ⚠️ The risk, and why it is now affordable

A tripped rung burns the address. That was an eight-hour wall last night — but **a router reset
cleared it instantly**, so the real cost of a trip is a reset and a restart, not a lost day.
⇒ Run the ladder up, not down: 1 → 4 → 8. If a rung trips, that IS the answer for that rung, and
the next one is not run.
⇒ ⚠️ **Do not carry a rung's result across a reset without re-baselining.** A new IP is a new
address with its own history; the solo baseline should be re-checked if the ladder is interrupted
by one.

---

## 000. WHAT I WOULD HAVE WANTED TO KNOW BEFORE THE 2026-08-19 SESSION

Every one of these cost real time in a single night. They are here because none of them were
guessable and all of them were knowable.

1. **A state name is a hypothesis your code formed, not an observation.** `state=ojv-other` means
   "none of my selectors matched". I read it as "the address is refusing", wrote up a persistent
   escalating block with a cost model and a cool-off schedule, and was wrong for two hours. One CDP
   attach to the running browser — thirty seconds — showed a healthy OJV with a changed DOM.
   ⇒ **When a scraper says "blocked", attach to its browser and look before believing it.**

2. **You cannot tell an outage from a block without an independent check.** Six sessions died in
   thirteen seconds; I published a request-rate wall. The site had gone down. `site_health.py`
   exists now; run it alongside anything that matters.

3. **"Per what?" — always ask it of a rate.** Three separate wrong conclusions came from
   active-seconds vs wall-seconds; the duty scheduler then repeated the error inside its own fix
   (3.23 stops per minute of *covered window*, not of wall clock), and again one line later, arming
   a gap with the wall interval instead of the active interval.

4. **`kept` is not `banked`, and `opens` are not `records`.** The worker's own tally cannot know
   what the bank already holds. Count in Neon, join on **(tribunal_id, rol)** — a rol repeats
   across the 230 courts, and matching on it alone returned MORE hits than there were causas.

5. **Depletion looks exactly like a slow configuration.** Never compare two spec arms on "new
   records" if the first one banked what the second would have found.

6. **Simulate a scheduler offline before you spend a run on it.** A fake `time.monotonic` and a
   fake `wait_for_timeout` took ten minutes and caught an error that three live runs could not
   separate from noise at 11–25 stops apiece.

7. **Log what a random draw PRODUCED, not just its effect.** "Why is the output short?" is a guess;
   "the draws match the operator but the output does not" is a subtraction.

8. **Judge a heavy-tailed spec by its MEDIAN, or budget enough draws to see the tail.** A post-fix
   mean of 7.7 s against an expected 11.1 s looked like a bug and was a 7% sampling event.

9. **The entry gate is a throughput tax that scales with fleet size**, and every worker counts it
   against its own `--max-minutes`. A fixed-length arm penalises the larger fleet for a reason that
   has nothing to do with the WAF. Measure rate in steady state; measure throughput over runs long
   enough to amortise arrival.

10. **Harness background tasks are killed at ~30 min.** Launch long runs DETACHED (`Start-Process`)
    and judge them by whether the log advances. A Drive migration died at 3,000 of 4,375 this way.

11. **Logs carry HH:MM:SS with NO DATE.** A run crossing midnight ends earlier than it starts; a
    naive guard silently scored zero wall and produced 242000000000 causas/min.

12. **Shell escapes cost three defects in one night.** A quoted bash heredoc still collapsed a
    double backslash before `r` into a carriage return — which PowerShell read as a line break,
    turning a comment into a statement 5 lines above `param()`; the same collapse before `n` became
    a real newline inside a Python string; and backticks inside a double-quoted bash string
    EXECUTED, eating a word from a commit message. ⇒ Build such strings with `chr(92)` or
    placeholders, and verify generated code with a real parser (`[Parser]::ParseFile`, `compile()`)
    — **never `ast.parse` alone, which is not a compile check.**

13. **Reuse the guards this repo already has.** The cp1252 print crash, the `worker_[ah].py`
    process-match, the covered-click check — each already existed three files away and each was
    re-broken by not copying it. `human_profile.py --vs` had NEVER been run, because it died on its
    own header for want of a guard `human_record.py` had carried for weeks.

14. **A cache key must come from the same field the record id comes from.** A document was cached
    in Drive under its POSITION in a list while its database row was keyed on its FOLIO. They agree
    until the list changes, then disagree silently. Exposure was zero when found — because no
    document-carrying causa had yet been scraped twice, which is the schedule, not the design.

---

## 0. READ THIS FIRST — the current best configuration (2026-08-17)

> **Newer than this section:** [THE 2026-08-18 SESSION](#the-2026-08-18-session--the-runner-can-be-single-stepped-and-the-block-is-one-causa)
> — `--trace`/`--step` (photograph and single-step a runner), the datepicker's disabled days,
> worker A's blind screenshots, and **the May block is ONE CAUSA**. Then
> [WORKER H TAKES DOCUMENTS](#worker-h-takes-documents--cuaderno-2s-pdfs-by-corte-2026-08-19)
> — `--docs-c2 --corte`, the cuaderno-2 PDFs, at **~5.5 requests per open instead of 2**.
> Corpus as of 2026-08-18: **5,510 causas, 5,377 with a cuaderno 2 (97.6%)**; June and July are
> done, May is the outstanding window.

Everything below this section was written while we believed pacing bought safety. **It did not.**
The whole document is still worth reading for the traps, but start here.

```
6 x worker_h.py --fill --shard i --of 6 --speed 1.0 --gate-release form
                                                 # each: own --port, own --user-data-dir
                                                 # --fill shards the WORK-LIST, not the court index
```

**~16 causa opens/min aggregate on residential, 95% of them useful.** Worker A's all-time best was
375 opens in 190 minutes (1.97/min); its remote best was 306 before a block.

⇒ **Use `--fill`, not a sweep, once you have a corpus.** A sweep re-opens what you already hold —
27% useful and falling as you collect more. Fill asks Neon what is missing: 95% useful, and shards
end `finished` rather than merely out of time.
⇒ **Add workers, do not speed them up.** Six at the operator's pace beat any faster configuration
and are more human at the same time (pointer 15-20 events/s vs 6-9 at top speed).

| what | value | how it was found |
|---|---|---|
| the binding limit | ~~aggregate request RATE per address~~ **NOT ESTABLISHED** | that test moved `--speed`, which moved the rate AND the pointer (6-9 mousemove/s vs 15-20) — two variables, one read. 52.9 req/min ran clean 2026-08-20. See section 00. |
| session count | **close to free, and now measured** | 8 concurrent sessions, one IP, 52.9 req/min, 25 min, zero trouble; linear scaling 2.02x |
| one worker's floor | ~8-9 s per kept causa | reading time ramped to zero; the residue is the site |
| pointer | **~16-20 mousemove/s, ~5 mouseover/s** | a real person emits 25.8 and 6.4 |
| horizontal scroll | **human_scroll_x on every off-side target** | we had never emitted a deltaX |
| window | `--window WxH`, verified on arrival | a PREFERENCE: 744x345 works, see below |
| keystrokes | **ZERO** | a person typed none in a whole session |
| dates | **the datepicker, with the mouse** | the fields are `readonly`; a person CANNOT type them |
| wheel inside a modal | **none** | a person wheels the list, not the modal |

⚠️ **Do not "optimise" this by making workers faster.** Top speed halves the pointer rate (6-9/s
against 15-20/s) and multiplies the request rate, and the request rate is the thing that kills.
Faster workers are both less productive in aggregate AND less human. Add workers instead.

⚠️ **`worker_h.py` has no ingest.** It writes JSON to `data/worker_h/`. See the ingest note at the
end of this file.

---

## 1. The design in one idea

**Opening a causa is the scarce act. Everything else is cheap by comparison.**

Measured: a session ran 19 searches with no search-block, then died on its third causa open
(2026-08-06). On 2026-08-07 one IP sustained ~24 causa opens across an afternoon before a
tier-2 block, while searches never blocked at all (208 in an evening, an earlier run).

Two consequences drive the whole architecture:

1. **The modal is where we harvest, not where we shop.** Once a causa modal is open, the header,
   litigantes, escritos, cuaderno list and cuaderno-1 historia are *already in the DOM*. They cost
   nothing. Take all of them, every time.
2. **Documents are the only per-causa extra**, so they get rationed across workers rather than
   fetched all at once.

### The three workers

| worker | does | costs per causa | status |
|---|---|---|---|
| **A — discovery** (`worker_a.py`) | sweep every tribunal, census + free metadata + **ebook** | 1 open + 1 doc | **built, running** |
| **B — backfill** (`worker_b.py`) | ebooks for causas ALREADY in Neon, from a filtered work-list | 1 open + 1 doc | **built — runs on PC 2, see `HANDOFF_PC2.md`** |
| **C — refresh** | re-check known causas for new movements | 1 search per tribunal | designed, not built |
| **H — the mimic** (`worker_h.py`) | what a MEASURED HUMAN does: metadata + both cuadernos, zero keystrokes, pointer alive throughout. `--fill` targets a known list instead of sweeping | 1 open, 0 docs | **built 2026-08-16, the fastest and safest thing we have** |

Worker B is built (`worker_b.py`): it asks Neon which selected causas lack a document instead of
discovering anything, so it never competes with A, and it writes with a targeted UPDATE rather
than an upsert. It shares A's `enter_and_setup()`, `harvest_causa()` and `grab_doc()` verbatim —
`grab_doc(p, causa_id, label, frag)` fetches ANY document by endpoint fragment, and every causa
record carries a `docs_pending` list naming what is missing, which is what the remaining four
documents will hang off. The endpoint fragments are `docu.php` (texto demanda),
`docCertificadoDemanda` (certificado), `newebook` (ebook); historia-row documents use
`docuN.php` / `docuS.php` and need the row located first.

---

## 2. Files

```
scraper/
  ojv.py               entry + search + freshness + block detection   ← ONE copy, use it
  worker_a.py          the discovery worker
  ingest_worker_a.py   state.json -> Neon (safe to run mid-sweep)
  rate_watch.py        what request rate the fleet is ACTUALLY producing, read from the logs.
                       Never derive it from the gaps — see §4.
  migrate_types.py     one-shot: TEXT -> DATE/TIMESTAMPTZ/INTEGER
  census.py            shim -> worker_a.py --no-detail (superseded)
  cdp_scrape.py        the older single-corte scraper; still the source of the
                       low-level helpers (human_click, parse_*, select_*_kbd)
  dbstore.py           Neon + Drive.  gstore.py = the Sheets backend
Iniciar_Worker_A.ps1   launch DETACHED — see §6
data/worker_a/         gitignored: state.json + pdfs/  (data belongs in Neon/Drive)
```

**`ojv.py` exists because duplication nearly cost a whole sweep.** `waf_check` and `cdp_scrape`
each carried their own English-only rejection matcher; when the site started answering in Spanish
both went blind *at the same time* and a run reported health for an hour while every search was
being refused. Entry, search, freshness and block detection now have exactly one implementation.
The same reasoning put `direct_link()` in `gstore` rather than in both storage backends.

---

## 3. Running it

```powershell
# 1. Chrome on a CDP port with a persistent profile (fresh dir is fine — see §5)
chrome.exe --remote-debugging-port=9342 --user-data-dir=%LOCALAPPDATA%\pjud_wA1 `
           --no-first-run --no-default-browser-check --start-maximized https://www.pjud.cl

# 2. the sweep — DETACHED (see §6, this matters)
.\Iniciar_Worker_A.ps1 -Port 9342 -Desde 15/07/2026

# 3. load results into Neon — safe at any time, including mid-sweep
python scraper\ingest_worker_a.py            # uploads ebooks to Drive + upserts
python scraper\ingest_worker_a.py --dry      # counts only
```

> ### ⚠️ THE SUPERVISOR IS DISABLED (2026-08-13). RE-ENABLE IT BEFORE ANY LOCAL RUN.
>
> ```powershell
> schtasks /change /tn "PJUD mantencion slots" /enable
> ```
>
> It was turned off once July finished and June moved to runners, because an hourly timer has no
> idea the work is over: it kept firing, re-ingesting the same 3,600 rows every hour, and — until
> `7cbe93c` — relaunching a finished slot ten times overnight, each relaunch a real walk-in to the
> OJV.
>
> **The failure mode of forgetting is silent and expensive**: workers run unsupervised, so a slot
> that dies at 01:00 stays dead until someone looks. That is the exact 19-hour outage this task was
> built to prevent. Check `Get-ScheduledTask 'PJUD mantencion slots'` says `Ready`, not `Disabled`.

**Hourly maintenance runs on its own and RESTARTS the sweep** — Windows Scheduled Task
`PJUD mantencion horaria`, registered by `.\Mantencion_Horaria.ps1 -Install`, logging to
`data\worker_a\ingesta.log`. Each hour it ingests, then checks the sweep and relaunches it if it
is down — bringing Chrome back first if CDP is not answering (same profile dir; cookies and
`TSPD_101_DID` survive, nothing is burned).

It exists because the sweep died twice in one day in different ways and each time sat idle until
a human looked — 19 hours on 2026-08-07. Both times the evidence was already in the logs.

Judgement calls in it, so they are not undone by accident:
- **Liveness is the PROCESS, not the log age.** A dead sweep is caught within the hour instead of
  after a staleness timeout, and PID reuse is ruled out by matching the command line.
- **A running-but-silent sweep is reported, never killed.** A wrongly-killed sweep costs more
  than a late warning.
- **Restarts stop after 4 without progress** and say a human is needed, so a tier-3 CAPTCHA (which
  no script may answer) cannot become an hourly relaunch loop. Any progress resets the budget.
- A stale lock from a crash is ignored rather than obeyed — otherwise one crash stops maintenance
  forever, which nobody notices until the data is weeks behind.

`schtasks /run /tn "PJUD mantencion horaria"` fires it by hand.

⚠️ **`.ps1` files here need a UTF-8 BOM.** Task Scheduler invokes Windows PowerShell 5.1, which
reads scripts as ANSI without one — so the `──`/`⚠️` characters in the comments corrupted the
parse and the task failed with exit 1 and an empty log. It ran fine when tested interactively
under PowerShell 7, which is exactly why it has to be tested the way the scheduler runs it.
Same reason `Say()` uses `Add-Content -Encoding UTF8`: 5.1's `Tee-Object` writes UTF-16 and left
half the log unreadable.

Useful flags: `--no-detail` (census only), `--no-ebook` (open causas, take metadata, request no
document), `--max-causas N` (bounded probe), `--start N` (resume at a tribunal index),
`--max-recover N` (consecutive blocks tolerated, default 6).

**Resuming needs no thought.** State is written after every causa. Re-running skips completed
tribunales without issuing a request, and `needs_visit()` re-opens a causa only if it is missing
something it should have — never one whose ebook control simply does not exist.

---

## 4. Pacing — the numbers and the evidence

```python
SEARCH_GAP   = 20.0   # EVERY result request — searches AND page advances
GAP_JITTER   = 0.15   # ±15%, so concurrent workers drift apart instead of firing in unison
CAUSA_GAP    = 25.0   # between causa opens
EBOOK_GAP    =  4.0   # after the modal renders, before asking for the pdf
POST_CAUSA   = 10.0
COOL_OFF     = 180.0  # × recovery number, after a block
CLEAN_STREAK = 12     # clean opens that win the recovery budget back
MAX_SWAPS    = 3      # replacement browsers a worker may open for a wedged form
```

⚠️ **These are NOT the 60/20/90/30 numbers this section used to print.** Those came from the
2026-08-07 trials, and `speed_probe.py` overturned them on 2026-08-10 by ramping the gaps down on
a live session and measuring where it actually broke:

| what was ramped | ramp | result |
|---|---|---|
| result requests, 51 of them | 45 → 22 → 10 → 6 → 4 s | never tripped once |
| causa opens, 18 of them | 90 → 60 → 40 → 25 → 15 → 8 s | never tripped, 18/18 ebooks |

Below ~15 s neither cycle shrinks any further, because the **site's own response time** (12–26 s)
is what dominates — our floor, not the site's limit. **The old 60 s was never a rate limit; it was
compensation for input that did not look human** — a metronome keyboard and no scrolling at all.
Fix the behaviour (`_kbd_pause`, `human_scroll`) and most of the budget disappears. The settings
above sit deliberately *above* the fastest clean level rather than at it.

⚠️ **PAGE_GAP IS GONE ON PURPOSE. A paginator click is a search** — it hits
`consultaFechaCivil.php` and returns a result set. Pacing it separately at 20 s against a 60 s
SEARCH_GAP meant every tribunal over 100 rows quietly fired at three times the intended rate.
One budget now covers every result request.

⚠️ **The per-worker gap is a floor on the interval, never a promise of the fleet's rate**, and it
is wrong in *both* directions. Aggregate rate goes UP when causas are already banked (a seeded
pass skips the opens that used to dominate each cycle — slot 1 produced 66 result requests in ten
hours on 08-11, then one every 20–40 s on 08-12 with identical settings), and DOWN as workers are
added, because they share one connection and slow each other. **Measure it, do not derive it:**
`rate_watch.py` reads the logs and reports what actually went out. Measured 2026-08-12 with four
workers: 2.6 result requests/min over 5 min, **1.8/min sustained over 15 min, zero trouble
events** — comfortably past the ceiling §10 records for three workers.

---

## 5. Blocks

`ojv.blocked()` returns True on any of: a frame containing "numero de soporte"/"requested URL was
rejected"; a rejection **body** (rejection text AND 100 < size < 1000 — size alone once stopped a
healthy sweep over a legitimate 0-byte response); or a `TSBrPFrame`/`cs_chlg` challenge iframe.

**A block does NOT burn the profile.** Measured 2026-08-07 on a blocked session: close the OJV
tab, walk in again → 18 s, 0 rejection frames, and the exact causa that had been refused opened
fine. Worker A does this automatically: cool off (scaling with the recovery number, because a
block is a rate verdict), re-enter, retry the same tribunal, leaving it `complete=False` so any
causa that missed its detail is picked up.

⚠️ **`waf_check.py` still says to rename the profile dir and re-pass a CAPTCHA. That advice is
stale.** It predates the re-entry finding and throws away a warm session for nothing.

The recovery budget counts **consecutive** blocks, reset by 12 clean opens. A lifetime cap would
strand a 250-causa sweep after six blocks however many clean hours sat between them.

### ★★ The second rung: a wedged form needs a NEW BROWSER, not a re-entry (2026-08-12)

There are **two** failure modes here and only one of them is a rate verdict:

| symptom | what it is | what fixes it |
|---|---|---|
| rejection frame / challenge iframe / `numero de soporte` | tier-2 block, a RATE verdict | cool off, re-enter the same browser |
| every `select_tribunal_kbd` fails — option list gone, or the value will not stick | the **session/form is wedged** | **a replacement browser. Nothing else.** |

Measured four times in one afternoon: slots 1, 2 and 3 each reached the state where no tribunal
could be selected, and a replacement Chrome had each of them searching again within a minute.
Slot 1 proved the negative directly — it spent a full 180 s cool-off *and* a clean re-entry,
still could not select a tribunal, and stopped anyway; relaunched onto a new browser it pulled
the very same court (Arica, 139 registros) on its first search.

So `recover()` now has a second rung, `fresh_browser()`: close this Chrome, open another on the
same profile and port, walk in. It is bounded by `MAX_SWAPS` — if the *replacements* keep wedging
then the browser was never the fault, and relaunching for ever would bury that.

⚠️ **A replacement arrives through the entry gate like any other new session**, and the lock is
handed to `boot_lock` so the sweep loop releases it on the next *confirmed search*, not merely on
reaching a form. A fresh browser loading pjud.cl is exactly the burst the gate exists to prevent.

⚠️ **It only fires when the worker opened its own Chrome** (`--launch-chrome`). A worker attached
to a browser someone else started says so and stops, rather than closing a window it does not own.

Until this existed, the only cure lived in the hourly supervisor — so a worker that wedged at
01:00 sat dead until 02:00.

Only **tier 3** (a full-page image CAPTCHA) needs a human. `ojv.walk_in()` detects it, says so,
and stops rather than attempting it.

---

## 6. ⚠️ Long runs must be launched DETACHED

**A background task started from the agent harness is killed after roughly 30 minutes.**

This is what actually happened to the census that appeared to "stall overnight" on 2026-08-06 at
208/230 — not a block, not a hang, not the Chrome CDP wedge. The process was reaped and sixteen
hours of warm profile were wasted while the cause was looked for in the WAF. It killed a sweep
again on 2026-08-07 at 13:58, mid-causa, immediately after a successful ebook.

`Iniciar_Worker_A.ps1` uses `Start-Process`, which reparents the worker so nothing reaps it, and
writes to a log file instead of a pipe. **Diagnose a "stuck" run by whether the log file is
advancing**, never by whether a wrapper is still attached.

Healthy rhythm at current pacing — long idle gaps are normal and look exactly like a hang:

| observed | meaning |
|---|---|
| ~2 min between causa opens | normal |
| ~60 s between tribunal searches | normal |
| >5 min silent | worth a look |
| >20 min silent | genuinely stuck |

---

## 7. Traps that cost real time

**A PDF that "failed" had downloaded perfectly.** Clicking a document icon opens a popup; Chrome
renders the PDF in its built-in viewer; and the response Playwright hands back is the *viewer's
host document* — `<embed type="application/x-google-chrome-pdf">`. `response.body()` therefore
returns ~14 KB of wrapper HTML with status 200. This produced two opposite wrong conclusions in
one day: three wrapper files filed on disk as captured PDFs, then a perfectly good scripted click
reported as a WAF block. **Never judge a document by size or status. Check for `%PDF`.**

**Fix — do not click documents; have the page fetch them** (`worker_a.FETCH_DOC_JS`): read the
form's action and JWT input, `fetch(url, {credentials:'include'})` inside the page, return the
bytes. Same single request the click would have made, no popup, no viewer, verifiable result,
0.7–5.2 s measured. This is **not** the out-of-process `APIRequestContext` `HANDOFF_CDP.md` warns
about — that one fetches from outside the browser with copied cookies. This runs *inside* the page
already holding the session.

**The results page holds 100 rows.** The 2026-08-06 census read page 1 only, so its 207 causas are
a **floor** — 33 tribunales reported totals above 100. Worker A paginates, and harvests each
page's detail *before* advancing, because **a row index belongs to the page it was read from**:
paginating to the end and then clicking page-1 indices opens the *wrong causas*. End-of-list is
the site's own greyed-out *Siguiente*, never a row count — the blank filler row drifts the count
and truncates exactly the biggest tribunales.

**Freshness must be proven by the network, not the DOM.** The site leaves the previous results on
screen while a new search runs, so "does `.loadTotalFec` say Total de registros?" is true *from the
last search*: an early version returned at 0.0 s every time and recorded each tribunal with the
**previous** tribunal's totals. A DOM-fingerprint fix then could not tell empty→empty apart,
because an empty search clears the table and two in a row look identical. Ground truth is a
`consultaFechaCivil.php` **response** arriving after the click.

**Never call a slow tribunal empty.** Live ones settled in 5.5–16.9 s; the floor is 25 s, and the
hard cap extends to 3× while the site's own spinner says it is still working — a slowdown to >75 s
was discarding valid searches, including one tribunal with 11 causas.

**`upsert` writes EVERY column, so a value the writer lacks becomes ''.** Three near-misses in one
ingest: `tribunales.corte` (worker A sweeps Corte=Todos and has no corte — would have blanked all
180), and `causas.ebook` / `texto_demanda` / `certificado` (harmless in the north, quietly
destructive on reaching Santiago where 74 causas already carry those URLs). Both are handled —
insert-if-absent for tribunales, read-and-carry-forward for the document URLs.

**Drive's `webViewLink` is the preview page, not the document.** Store
`https://drive.google.com/uc?export=download&id=<id>` — `gstore.direct_link()` normalises any Drive
URL, and is applied to **both uploaders and both doc caches**, because a cache hit on a file
already in Drive would otherwise keep returning the old shape.

**`state.json` is rewritten non-atomically after every causa**, so a reader can catch truncated
JSON. `ingest_worker_a.snapshot()` copies and retries.

**`query_selector` throws while a page is navigating** ("Execution context was destroyed") — which
is exactly when the form is polled for after the entry click. Unguarded it killed a run at the
moment the click *succeeded*.

---

## 8. Neon schema

Tables are created at runtime by `dbstore._ddl()` from `gstore.TABS` — `schema.sql` is historical
and must not be run. Live tables are unprefixed (`causas`, not `pjud_causas`).

`migrate_types.py` (applied 2026-08-07) gave the store real types. Every value was profiled first
and 0 of 124k failed to convert:

```
causas.f_ingreso, cuadernos.fecha_tramite/fecha_diligencia, escritos.fecha_ingreso,
notificaciones_receptor.fecha, anexos.fecha                          -> DATE
causas/litigantes/ruts/sweep_progress.updated_at                     -> TIMESTAMPTZ
cuadernos.foja                                                       -> INTEGER
```

**DD/MM was confirmed, not assumed** — the max first component is 31 in all three date columns, so
it cannot be a month. Reversed, it would have turned 100k+ rows into plausible wrong dates that
nothing downstream would ever flag.

**Left TEXT deliberately:** `folio` (4,166 values look like `[11E]` — a folio carrying an escrito
marker; an identifier, not a quantity) and `rut`/`dv` (check digits can be `K`, leading zeros are
significant).

The writer changed with the schema, or the next upsert would have failed: `''` becomes NULL for
typed columns, dates are converted to ISO **in Python** rather than depending on the session's
`DateStyle` (get that wrong and 03/07 silently becomes 7 March), and `read_tab()` still returns
`22/07/2026` and `2026-07-08T01:43:03Z` so the Sheets exporter is unaffected.

Backups from the migration: `<table>_bak_20260807`. Drop them once the types have proven out.

---

## 9. State of play, 2026-08-12

**Local: four workers sweeping all of July** (01/07 → 31/07), disjoint index ranges 0–57 / 58–114
/ 115–171 / 172–229, ports 9342/9352/9362/9372, supervised hourly by `Mantencion_Slots.ps1`.

- Neon: **3,700+ causas**, ~2,870 with a verified ebook in Drive.
- Windows swept: 01/06–30/06 (partial, ~9 tribunales), **01/07–14/07 complete**, 15/07–10/08
  complete. June is the outstanding one.
- **The seeding trick that made this cheap:** each slot's `state.json` was pre-loaded with the
  3,117 causas already harvested, so `needs_visit()` returns False for them. The sweep then pays
  for searches and pagination — which are cheap — and buys a causa open only for something
  genuinely new. Arica listed 32 bank causas and cost 3 opens.
- ⚠️ **Do not write a seed under a running worker.** It holds state in memory and rewrites the
  whole file after every causa, so an edit from outside is silently overwritten on the next save.
  Stop the worker, ingest it, then seed.

**Remote:** the June sweep is the current test — see §11 for the rate translation it is testing.

### What the July window taught us about "missing" data

Taking the **union across slots** rather than reading each state separately: every causa ever
discovered had already been harvested. The only real gap was **5 courts whose pagination never
got past page 1** (all showing `pages=1 rows_seen=100`), so ~194 rows were never enumerated at
all. Per-slot "missing" counts were inflated ~3× by overlapping ranges — an artefact of the
supervisor bug that once restarted slots as 39–120 / 78–171 / 117–229.

⇒ **Audit coverage by the union, and by `rows_seen` vs `total`, never by one slot's state.**

### Next

1. **Worker B is built but unwired** — `causas.texto_demanda` is still 0 rows, so no document
   beyond the ebook has ever been fetched. It is the largest untapped gain here.
2. **Worker C** — refresh. Needs a decision on what "changed" means (new historia row? new
   escrito?) before it is worth writing.
3. **Notificaciones and Exhortos** modal tabs are still unparsed and have no columns. Free to
   read once the modal is open — they belong in worker A's free harvest when someone adds them.
4. **Seed remote runs from Neon.** A runner starts from an artifact, so June's 225 already-
   harvested causas will be re-opened — ~9% of the window spent on work already done. A
   `--skip-scraped` that preloads causa ids from Neon at startup would close it; `cdp_scrape.
   scraped_rols()` already reads exactly that.
5. `waf_check.py`'s stale profile-rotation advice (§5).
6. **The supervisor will not run on battery.** The Scheduled Task carries
   `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries`, which is why it went silent from
   18:57 on 08-11 to 13:56 on 08-12 and left a dead slot unnoticed through the night.
7. **Revoke the GitHub PAT embedded in the `origin` URL** in `C:\Claude\.git\config` (see it with
   `git remote -v`). That file is untracked and has never been pushed, but the token is live and
   printed by any `git remote -v`. Revoke it on GitHub, then
   `git remote set-url origin https://github.com/dankobuy-ops/Felipe.git`.

   ⚠️ **Do not paste the token itself into a tracked file to "document" it.** I did exactly that
   in the first draft of this section; GitHub push protection rejected the push, which is the
   only reason a live credential did not land in a PUBLIC repo. The location is enough — the
   value never needs to be written down.

---

## 10. Concurrency — measured 2026-08-09/10, one IP

| workers | pacing | result |
|---|---|---|
| 1 | searches 60 s, pages 20 s | fine for hours |
| 2 | pages at 20 s | ✅ 20 min, then ONE worker blocked mid pagination burst |
| 2 | **pages share the 60 s budget** | ✅ **65 min, 98 result requests, zero blocks** |
| 2 | pages share the 60 s budget, fresh profiles | ✅ **94 min, 131 requests, then ONE blocked** |
| 3 | pages share the 60 s budget | ❌ **all three blocked at once, 6 min in, 2 searches each** |

**Endurance of a 2-worker pair: about 90 minutes / ~130 result requests**, after which one of the
two takes a tier-2 block and recovers on its own. The other kept running clean throughout, which
is the useful part: a block hits ONE session, not the pair, so the sweep degrades rather than
stopping. Plan for it instead of trying to avoid it — the recovery budget exists for exactly this.

**Two workers is the ceiling on one IP.** The three-worker run is the cleanest datum here: fresh
profiles, simultaneous start, and all three rejected within **12 seconds of each other**
(00:21:03 / 00:21:13 / 00:21:15) — which rules out profile age and start ordering, and shows F5
cutting the whole address at once rather than punishing an individual session.

Rough ceiling: two workers sustained ~1.5 result requests/minute for an hour; three would be
~2.2/min and died immediately. So the limit sits between those, and it is a RATE, not a quota.

⚠️ **A paginator click is a search.** It hits consultaFechaCivil.php and returns a result set, so
it must draw on the same budget. `PAGE_GAP` used to be 20 s against `SEARCH_GAP` 60 s, which meant
every tribunal over 100 rows quietly fired at three times the intended rate — Taltal has 270
registros, so one worker alone produced 3 requests in 46 s. A single worker rarely noticed
(pagination averages 1.28 pages/tribunal, so bursts were isolated); two workers made them overlap
and that is what killed round 1. Fixed: one budget for every result request.

**The old "3 workers = blocked" note from 2026-07-23 was right, but for the wrong reason.** It was
measured while every worker also fired the corte-change burst, so it never isolated concurrency.
This trial does, and reaches the same ceiling — now for a reason we can point at.

---

## 11. Four workers, and why the ceiling above is not a worker count (2026-08-12)

**Four local workers ran clean**: 1.75–1.8 result requests/min sustained, **zero trouble events**
over 25 minutes, 73 causa opens and 65 ebooks in a 20-minute window. That is past the rate §10
records for *three* workers dying immediately.

Nothing about the site changed. Two things about us did:

1. **The input stopped looking robotic.** §10 predates `_kbd_pause` and `human_scroll`. The
   2026-08-10 `speed_probe` ramp then showed a single session holding ~3 result requests/min
   without tripping, which already contradicted the §10 ceiling.
2. **Four workers do not make four workers' worth of traffic.** They share one connection and one
   machine, so each extra worker stretches every other one's cycle. The fleet self-damps.

⇒ **A worker count is not a budget.** What predicted every failure on 2026-08-12 was the *trouble
column* — blocks, modal timeouts, failed selects — never the number of workers or the rate on its
own. Measure with `rate_watch.py` and judge by what goes wrong.

### ⚠️ Runners do NOT self-damp — the rule has to be translated

Each runner has its own machine and its own link, so **N shards at the same gap really is N times
the rate**, into a budget that belongs to the whole datacenter **range** (three unrelated Azure
addresses blocked within 14 seconds of each other, 2026-08-11).

That reframes the trial which concluded "sharding is pointless": those three shards each ran at
the single-worker 20 s gap, i.e. **~9 result requests/min, roughly five times anything measured
safe**. It confounded concurrency with rate and could not tell which the range objected to.

So the remote workflow now scales pacing by shard count — `--search-gap` and `--causa-gap` set to
`base × shards`. N shards each firing every `base×N` seconds is `N/(base×N) = 1/base` requests per
second **whatever N is**, so the aggregate is identical at 1, 2 or 6 shards. With `ramp_min`
(default 30 min) letting each runner prove itself before the next joins, a failure can finally be
attributed to the runner that caused it.

### ★★ OVERTURNED 2026-08-13: shards DO scale. Remote = 3 workers, not 1.

**The section below is wrong.** It concluded "remote means one worker" from three trials in which
shards died within seconds of each other — and never once measured a **solo baseline** to compare
against. With one, at gap 13 and a gated arrival:

| config | opens per shard | combined | session life |
|---|---|---|---|
| 1 runner | 77 | 77 | 75 min |
| 2 runners | 75, 72 | 147 | 66 min |
| 3 runners | 74, 72, 70 | **216** | 65 min |

A session gets **~70–77 causa opens** and is then refused — alone or one of three. Nothing is
shared, and yield scales linearly with runners.

The "coordinated cull" was an artefact: three sessions started within three minutes, each spending
an identical allowance at an identical pace, reach zero together. 21 s apart in this trial, and it
carries no information.

⇒ **Use `shards=3`.** Roughly triples the yield per wall-clock hour, and each runner still needs
its own ~65 min before handing over.

⚠️ **Unexplained, so the model is useful rather than complete:** the 08-12 four-shard run died
within 18 s holding **74 / 16 / 2 / 38** opens. Unequal work, identical death time — a per-session
budget cannot produce that. Those shards were paced ×4 and ramped 30 min apart, so they may not be
comparable, but nothing accounts for the pattern.

⚠️ **The lesson worth keeping:** "they failed together" does not imply "they caused each other to
fail". Workers doing the same work at the same pace from the same start always fail together, for
independent reasons. Without a solo control you cannot tell a shared ceiling from a per-session
budget, and every remedy for the first is wasted against the second.

---

### ~~★ Settled the same day: it is the concurrent SESSIONS, not the rate. Remote = one worker.~~ (superseded)

The experiment ran that evening — four runners joining 30 min apart, each paced ×4 so the
**aggregate never exceeded one worker's rate**. All four entered on the first attempt (so a
datacenter address is not refused at the door), and then:

```
20:23  s1 joins 135.232.208.131 -> 1 concurrent
20:53  s2 joins 20.3.215.36     -> 2
21:23  s3 joins 20.102.46.202   -> 3
21:34:36 s2 BLOCKED / 21:34:50 s3 BLOCKED    14 seconds apart   -> back to 1
21:53  s4 joins 20.81.47.119    -> 2
23:39:22 s1 BLOCKED / 23:39:40 s4 BLOCKED    18 seconds apart   -> 0
```

Rate held constant, and unrelated addresses were still cut down in near-simultaneous pairs — the
same signature as 08-11. **The verdict is applied to the range and triggered by concurrent
sessions, not by request rate alone.**

Throughput is *worse* than a single worker, because each shard pays the ×N pacing tax and is
culled regardless:

| | wall clock | causa opens |
|---|---|---|
| 1 shard @ 1× | 38 min | 42 (**1.11/min**) |
| 4 shards @ ×4 | 196 min | **130 total** |
| 1 shard extrapolated | 196 min | ~218 |

⇒ **Remote is ONE worker, chained with a cool-off.** `shards`/`ramp_min` stay in the workflow
because they are how this was measured and how it would be re-measured if the site changes — not
because more runners help. Two runners did survive 1h46m against 11 minutes for three.

### ★ X for a runner, measured 2026-08-12 (`pjud-velocidad`, run 31658994520)

One runner ramped 45 → 35 → 28 → 22 → 17 → 13 → 10 → 8 → 6 s. **36 requests, never tripped.**

| gap | mean cycle | mean req/min |
|---|---|---|
| 45 s | 67.0 s | 0.90 |
| 22 s | 43.8 s | 1.38 |
| **13 s** | **28.9 s** | **2.10** ← use this |
| 10 s | 28.4 s | 2.11 |
| 8 s | 30.8 s | 1.95 |
| 6 s | 29.1 s | 2.07 |

The cycle floors at ~28 s from gap 13 down: the site's own response time (17–23 s) plus ~2 s of
activity is everything that is left. 8 s and 6 s buy nothing. Overall **74 s active against 662 s
idle — 10%**.

⇒ **No remote rate limit exists**, same as local. `base_search_gap` is now **13**, and the ×N
scaling is **off by default** (`scale_pacing`) — it was built to pin the aggregate while rate was
still a suspect, and rate has now been ruled out.

⚠️ **This strengthens the concurrency verdict.** The four shards culled in pairs were paced at ×4,
about 0.7 req/min each — a third of what one runner sustains — and were cut down anyway. Speed is
eliminated; concurrent sessions are the only variable left.

⚠️ **The 40% figure was wrong, and worth correcting explicitly.** It came from ebook fetches
(9.8 s remote vs ~1 s local), which is *bandwidth on document downloads*. The SEARCH round-trip is
identical on a runner (17–23 s vs the local 12–26 s). So a runner is at full speed for census
work, and only slower for document-heavy detail passes.

Every shard did ingest before dying (`if: always()`), so the run still banked its work: June went
352 → 461 causas and 216 → 318 ebooks.

---

## Worker C — refresh (built 2026-08-13, first run is the night queue)

`worker_c.py`. Re-opens a **finished** causa (`fill_status='full'`) and takes only what is new.
The division of labour, by how much of the causa each worker intends to take:

| worker | takes | cost per causa |
|---|---|---|
| A | list sweep + what the modal makes free + ebook | 1 open, 1 fetch |
| B | every document, every georreferencia, every cuaderno, receptor | 1 open, **40+ fetches** |
| C | only what changed since the last visit | 1 open, **0 fetches** |

**How the skipping works.** C loads what Neon already holds — `documentos`/`anexos` ids,
`cuadernos.georref`, the three header document columns — into `cdp_scrape.KNOWN_DOCS` /
`KNOWN_GEO` / `KNOWN_HEADER`. The **shared** harvest (`scrape_causa(full=True)`) consults them.
Worker A and worker B leave them `None` and behave exactly as before. There is deliberately no
second, leaner harvest: that is how the duplicated block detectors drifted, silently, toward
collecting less.

⚠️ **`KNOWN_GEO` carries the stored value; it does not merely suppress the lookup.** Every historia
row is written back as a `Cuadernos` row by an upsert, `georref` included. A row whose geo we
skipped would go back with `georref=''` and blank a coordinate we already own — the same trap as
the upsert that nearly wiped `tribunales.corte` for all 180 rows.

⚠️ **The skip lists are module state and are cleared in a `finally`.** Leaving one set would make
the *next* causa skip documents belonging to a different causa.

⚠️ **The invariant that decides whether C is worth its session budget:** on a causa finished
minutes ago, documents fetched for rows we already held must be **0**. If the row ids drift, every
skip list matches nothing and C quietly becomes worker B at worker B's price — while reporting
success, writing the same rows, and going green. `refresh_causa` counts it as `on_known`, the run
writes `data/worker_c/last_run.json`, and `night_check.py --stage after-c` fails the step on it.

**`updated_at` means "when we last looked", not "when it last changed".** C moves it on every
successful visit including one that found nothing, because that is what makes
`ORDER BY updated_at` a work queue instead of an infinite loop over the same stalest causa.

**State of play 2026-08-13:** Neon holds 5,016 causas and 45,701 cuaderno rows, and
`documentos = 0`, `georref = 0`, `fill_status='full' = 0`. **Worker B has never successfully
written a document** — its only real dispatch was cancelled before it touched the site. So C has
nothing to refresh until B runs, and the night queue orders them accordingly.

## The night queue — `pjud-noche.yml`

One dispatch, six tests, strictly one at a time, each on its own runner and IP.

⚠️ **No cron, ever** (operator). A queue a person started is fine; a schedule is not.

⚠️ **One workflow with chained jobs, NOT six dispatches.** GitHub keeps exactly **one** pending run
per concurrency group — queue a third and it silently cancels the one already waiting, which is how
a worker B run that had never touched the site was destroyed on 2026-08-13. Jobs inside one run
queue properly and each gets its own 350-minute budget.

⚠️ **`if: !cancelled()` on every job, not `success()`.** A blocked test is a *result*; failing the
rest of the night because test 2 was refused would throw away the four measurements after it.

| # | job | question |
|---|---|---|
| 1 | `b_smoke` | does worker B write a document **at all**? (2 causas, gates the rest) |
| 2 | `probe_pace` | June, idx 0, causa gap **8** — one variable off the blocked set |
| 3 | `probe_position` | June, idx **16** (Antofagasta), causa gap 25 — the other arm |
| 4 | `b_real` | how many causas does B actually finish in one session? |
| 5 | `c_smoke` | 3 causas, must cost **0 fetches** |
| 6 | `c_real` | C over every `full` causa |

Probes 2 and 3 exist because the "session budget" turned out not to exist — see
`SCRAPERS_HANDBOOK.md`, Part 5. They separate *pace* from *position*: all five blocked runs shared
the June window, a start at index 0, a 25 s causa gap, and died in the same Antofagasta civil
courts at idx 16–18.

⚠️ **Neither probe restores a state artifact, deliberately.** A resumed run skips causas it already
banked, and a probe that skips opens measures nothing.

### Worker B proven end to end — 2026-08-13, 23:0x

The night queue's `b_smoke` job (2 causas, `--require-docs 1`) passed on its first run:

| | before | after |
|---|---:|---:|
| `documentos` | **0** | **21** |
| `cuadernos.georref` | **0** | **5** |
| `causas.fill_status='full'` | **0** | **2** |

Four counters had sat at zero for days behind the assumption that worker B worked, because its
only real dispatch had been cancelled before it touched the site. **Ten minutes on two causas
settled it.** Size the smoke test to the question, and gate the full session on it.

⚠️ `documentos` keys on **`cuaderno_id`**, not `causa_id` — a row belongs to a historia row
(`<causa>-c<n>-<folio>-<k>`), not to the causa. Worth remembering when writing an ad-hoc query.

---

# Worker A REDEFINED — metadata only, gated on the caratulado (2026-08-14)

Settled with the operator driving a live browser while the session was recorded. Everything below
is **measured on the wire**, not inferred from the DOM.

## What worker A does now

1. Open the causa.
2. **Parse the header ALONE, and gate on its `Etapa`.** Reject → close, and do **not** open a
   single book. *"If the header doesn't match, ditch that causa; there's no need to go into its
   books."*
3. Free harvest (no requests): litigantes, escritos, historia of book 1, cuaderno list.
4. `--only-proc` gate, as before.
5. **Switch to cuaderno 2** and take its historia **and its own header**.
6. Close. **No documents, ever, under any flag.**

`--no-ebook` is still accepted so the workflows keep parsing, and is ignored. A buys nothing.

## The measured request sequence

A full human run, recorded 2026-08-14:

```
GET   indexN.php                     entry (clicked through from www.pjud.cl)
GET   consultaUnificada.php
POST  combosJSON/leeCorte.php        codCompetencia=3 codCorte=0 tipoBusqueda=1
POST  combosJSON/leeTrib.php
POST  ADIR_871/civil/consultaFechaCivil.php    THE SEARCH — 23 s
        g-recaptcha-response-fecha  (1,358 chars)
        action=validate_captcha_fecha  fecDesde  fecHasta
        fecCompetencia=3  fecTribunal=<id>  corteFec=0
POST  ADIR_871/civil/modal/causaCivil.php     open causa   dtaCausa len 621 + token
POST  ADIR_871/civil/modal/causaCivil.php     switch book  dtaCausa len 508 + same token
```

★ **EVERY cuaderno switch costs one `causaCivil.php` POST — measured, no longer assumed.** Seven
POSTs were recorded across one open and six toggles, alternating `dtaCausa` 509 (book 1) / 508
(book 2) with the session token constant. Worker A's visit is therefore **2 requests per causa**.

★ **Neither request touches `docuS.php`**, the document endpoint that refused 16 and 19 times on
2026-08-13. That is the whole point of the redefinition: A stays clear of the thing that blocks.

★ Litigantes, escritos and book-1 historia generate **zero** requests — confirmed by their absence
from the recording, not assumed from the DOM.

## ⚠️⚠️ The header is PER-CUADERNO

The same causa, same modal, seconds apart:

```
book 1 - Principal   ->   Etapa: 1 Notificación demanda y su proveído   (9 historia rows)
book 2 - Apremio     ->   Etapa: 1 Mandamiento                          (2 historia rows)
```

Switching books re-renders the whole caratulado. Consequences, all live:

- The header **must** be parsed while book 1 is displayed — which is what the modal opens on — or
  `causas.etapa` silently becomes the Apremio stage and the gate judges the wrong field.
- `scrape_causa` (workers B and C) already parses the header before its cuaderno loop. **Keep it
  that way.** There is now a ⚠️ at both sites.
- Every `causas.etapa` value in Neon is a **book-1** stage, because A never switched books before.
  The 11.3% Terminada figure is therefore consistent with the gate.
- Book 2's header is captured as `header_c2` now: once the switch is paid for, its Etapa is free,
  and the Apremio stage is exactly what a human sorting these needs. **It has no column yet.**

⚠️ Both books number their stage `1`. The ordinal is scoped to the book, not a global enumeration.

## The Etapa gate — `run.etapa_rejected()`

Discards `Terminada`, `Incidentes`, `Téngase por no presentada`. Shared by worker A and the
ingest, and worker C will use it too.

⚠️ **It strips the leading ordinal and folds case/accents, and it has to.**
- The ten values in Neon run 0,1,2,3,4,5,6,7,8,**12** — sparse, so "Incidentes" cannot be
  predicted; we have no example of it yet.
- `dbstore.FILL_SKIP_ETAPAS` hardcodes `"6 Terminada"`, which **does not exist**: 6 is
  *Impugnación de Sentencia*, Terminada is 8. That entry has matched nothing since it was written.
- The site abbreviates: the one stored instance is *"Téngase por no presentada la **dda** por
  apercibimiento"*. An exact match on the full phrase finds nothing — and reports success.

Verified to discard `8 Terminada` / `6 Terminada` / bare `Terminada` / `1 Incidentes` /
`N Incidentes` / both spellings of the téngase, while keeping `6 Impugnación de Sentencia`,
`12 Incompetencia`, `1 Mandamiento` and `4 Término Probatorio`.

## ⚠️ The ingest trap this created

`ingest_worker_a.as_causa()` used to hardcode
`cuadernos: [{cuaderno: cuads[0], historia: historia_c1}]`. Feeding book 2's historia through that
would stamp its rows **`-c1-`** — colliding with the real book-1 rows, overwriting worker B's data
and pointing worker C's skip lists at ids that mean something else. Nothing would have looked
wrong. Each historia now carries its own cuaderno label, and only books actually READ are emitted.
Verified: `29-C-10301-2026-c1-1-1` and `29-C-10301-2026-c2-1-1` coexist, 0 Documentos rows.

## Pending decisions

- `header_c2` has nowhere to live — needs an `etapa_c2` column if humans will sort on it.
- The ~4,460 existing causas have no book 2 and were never screened: they need an A re-pass.
  **Open question: delete the causas the gate rejects, or mark them?**
- Worker C's two modes wait on the five human categories (3 actionable, 2 not).

---

# ENTRY REWRITTEN — the site moved the door (2026-08-14)

Found with the operator clicking by hand while a network recorder ran. **The worker could not enter
from the residential IP at all**: nine refused clicks across three attempts, then exit.

## What actually happened

`www.pjud.cl` now offers exactly **one** anchor to the OJV:

```
href="https://oficinajudicialvirtual.pjud.cl/includes/sesion-consultaunificada.php"
tooltip: "Sección que permite la revisión de causas"
```

and it lands **straight on the search form**:

```
GET indexN.php            #fecCompetencia present, #btnConConsultaFec present
GET consultaUnificada.php  accesoConsultaCausas count: 0
```

**No `/home/`. No guest-entry gate.** Three assumptions in `ojv.py` were each fatal on their own:

1. `_reach_ojv` sorted candidate links to put **`/home` FIRST** — deliberately walking into the
   gate.
2. `_reach_ojv` only recognised arrival by the **gate's own markers**
   (`accesoConsultaCausas` / `accesoInvitado` / `#no-disponible`). Landing on the form matched
   none of them, so it waited out its full 60 s and reported failure **while standing on exactly
   the page it was sent to fetch**.
3. `walk_in` called `find_form()` once, at the top, *before* navigating — and never again. So the
   click-through succeeded, `_reach_ojv` "failed", and the code went hunting for a guest button
   that does not exist there, found a stale one, and logged `objetivo tapado` nine times.

⇒ Fixed: rank `sesion-consultaunificada` first and `/home` last; accept `#fecCompetencia` as
arrival; re-check `find_form()` after arriving; and on "covered", check whether the form is
already open and take it. **Result: entry in 16 seconds, first attempt.**

```
[15:53:16]  click -> 'Sección que permite la revisión de causas'
[15:53:24]  landed straight on the form — no guest gate on this route
```

⚠️ **Half the entry folklore in this repo may live on a path humans no longer take.** The flaky
gate-1 click, "every fresh profile fails its first entry", the two-`accesoConsultaCausas`-buttons
mess — all of that is `/home/` behaviour. Do not port it forward without re-checking.

## `locate()` — a worker that knows where it is

Operator's call: *"we might need to add a way for a worker to recognise where it is and act
accordingly."* Every entry failure message we had said what did NOT happen — `objetivo tapado`,
`no form after attempt 1`, `could not reach the OJV` — and none said where the worker was standing.

`ojv.locate(page)` returns one of: `form`, `results`, `modal`, `gate`, `aviso`, `captcha`,
`blocked`, `www`, `ojv-other`, `blank`, `elsewhere`, `unknown`. Never raises; `unknown` mid-nav.
`ojv.locate_ctx(ctx)` returns `(state, page)` for the most actionable tab.

It is wired into the three paths that failed, and each **recovers** rather than merely reporting:
covered-button checks for an already-open form; `_reach_ojv` returning None checks the same; and
every give-up line now carries `[state=…]`.

⚠️ Built on the existing `rej_frames()` detector. The first draft invented a `REJECT_TEXT` list —
a second rejection vocabulary is precisely how the duplicated block detectors drifted apart.

## Overlays: detected by HIT-TEST, not by id

`_dismiss_aviso` knew `#no-disponible`; `page_busy` knew `.jquery-loading-modal__bg`. Each was
written the day that particular overlay cost a run, and **a new one was invisible to both**.

`ojv.blocking_overlay(page, sel)` asks the browser what is actually on top of a target, walks up to
the nearest floating/dialog-ish container, and returns its id, class, z-index, text and its own
dismiss controls. `ojv.clear_overlay(page, sel)` clicks whichever control says
close/cerrar/aceptar/entendido/continuar/ok/×, then verifies.

Proven end-to-end against an injected overlay with an id nothing in the codebase knows:

```
overlay covering target: DIV#aviso-mantencion-x z=99999 | text='Sistema en mantencion Aceptar'
clear_overlay -> (True, 'nothing covering')
```

⚠️ `PROTECTED_OVERLAYS` — never closes `#modalDetalleCivil` and friends. Closing the causa modal
"to clear an overlay" would throw away the causa we are standing in.

⚠️ **A target that is merely unhittable is NOT an overlay.** The first version fell back to
"whatever is on top", so a search button under a `<select>` in normal flow was reported as
*covered by SELECT#conTribunal* — and the cleaner would have hunted for a dismiss button on a
dropdown. It now returns `None`: unhittable is a LAYOUT problem, a different diagnosis, and
disguising one as the other is how `covered` came to mean three different things in a week.

## ⚠️ Where the metadata-only worker A stands — UNRESOLVED

| run | code | opens | outcome |
|---|---|---:|---|
| probe_pace 08-13 | old | **306** | clean, ended on our own `--max-minutes` |
| A/B control 08-14 | new | **10** | blocked, causa `2-C-1251-2026` |
| A/B motion 08-14 | new + `--idle-motion` | **10** | blocked, SAME causa, same signature |
| remote control 08-14 | old | — | ran **>54 min** vs the arms' 10.5 |
| local 08-14 | new + all fixes | 25+ | clean, residential |

**`--idle-motion` changed nothing** — same causa, same count. Clean negative; the mousemove theory
buys nothing here. (Hover-on-scroll was different: measured 0 vs 12 events directly.)

⚠️ The A/B "control" was **not a control**: it changed four things at once versus the 306-open
baseline (no ebook, +1 POST for cuaderno 2, the etapa gate, pointer-positioned scrolling) and ran
at a different hour. The remote old-code run is the real comparison and it points at the code.
Bisect order when it lands: pointer scrolling, cuaderno switch, etapa gate, absent ebook.

⚠️ Local surviving proves little — residential has always been the forgiving environment
(730+ opens/day vs a small runner session). It rules out "catastrophically broken", not "worse on
runners".

---

# THE 2026-08-14 SESSION — worker A metadata-only, proven local, blocked remote

## ★ RESULT: local worker A is done. 375 opens, 0 blocks, stopped by OUR clock.

```
RUN REPORT: lifespan | finished=False idx=14 blocks=0 recoveries=0 swaps=0 opens=375 ebooks=0
```

190 minutes, 15 tribunales, 0 blocks / 0 recoveries / 0 swaps / 0 apm challenges, `pdf_bytes=0`
throughout, cuaderno-2 switch firing on every eligible causa. **That beats the best remote run
ever recorded (306) and it ended because the lifespan expired, not because the site refused us.**

Rate: **2.0 causa opens/min**, against the old remote worker's 1.59 on the same window — faster
despite the extra cuaderno-2 POST, because it downloads nothing and the gates discard ~34% of
causas for one open each.

Record shape verified live, not just compiled: of 50 causas, 33 harvested and every one had all
five parts (historia_c1, historia_c2, header_c2, litigantes, escritos); 15 gated on etapa, 2 on
procedimiento; **zero documents bought**.

## ⚠️⚠️ THE REMOTE 10-OPEN WALL — CAUSE FOUND, MECHANISM NOT

**Four** runner sessions stopped at **exactly 10 causa opens**, on the **same causa**
(`2-C-1251-2026`), with the **same signature** (`modal did not open after 90s`,
`rejF=2 hardRej=1`) — across two entry routes, four IPs, and a range quiet for an hour.

**It is the cuaderno-2 switch.** Disabling it alone cleared the wall: the causa that had hung for
90 s three times opened in **six seconds** and the run carried on past causa 15.

It is NOT:
- **the causa** — local opened `2-C-1251-2026` as its own 10th causa, in 6 s, and went on to 375.
- **the position** — same sequence locally, no wall.
- **the entry route** — the 4th death carried `--entry-route home`.
- **the pointer teleport** — reaching the dropdown with a real arc instead of `.focus()` did NOT
  fix it (run 31844271560, same causa, same count). ⚠️ Kept anyway: teleported focus IS a genuine
  tell, it is just not this one. **Recorded so it is not re-attempted.**
- **the wheel-scroll fix, the pointer clamp, or `locate()`** — the 4th death carried all of them.
- **a POST count** — `probe_pace` made 306 `causaCivil.php` POSTs on a runner (08-13), clean.

**What is left, and it is the only property the clean runs never had:** the switch fires its
second `causaCivil.php` POST **~4 s after the open**, where every clean run spaced that endpoint
**29–38 s** apart. A burst of two POSTs we invented. Nobody flips to the Apremio cuaderno four
seconds after a modal renders.

⇒ **NEXT TEST: a human dwell before switching books** (10–20 s of "reading" book 1). It is the
one-variable test that remains, and it is also simply what a person does.

⚠️ **My error, recorded:** I cancelled the `--no-cuaderno2` run at ~causa 15, one causa short of
where a ~16-POST count budget would have shown itself. That would have separated count from burst
for free. Do not cancel a running discriminator for a test that can wait.

## The entry route is PER-ENVIRONMENT (measured)

| environment | direct link | `/home` + guest gate |
|---|---|---|
| residential | **works** — 375 opens; the only reason local entry works at all | (not offered here) |
| datacenter | enters cleanly, then **cannot complete one search** — `rejF=1`, 0 opens, twice | **works** — the only remote route that has ever searched |

`entry_probe.py` proved a runner is still offered **both** anchors, so this is a choice, not a
closed door. `--entry-route {auto,home,direct}`; the censo workflow passes `home`.

⚠️ I scanned ONE machine, saw only the direct link, concluded the site had dropped `/home` for
everyone, and pushed a single global ranking. The runner failed its first search minutes later.
**Two environments already known to be served different pages do not get one hardcoded preference.**

## Seeing what a runner does — `--shots DIR`

A runner has no screen, and for four sessions we could not say what was on the page during those
90 s: a spinner, a rejection interstitial, an overlay, or a normal page missing one element. Four
different fixes; we were choosing between them by counting requests.

`--shots` captures a screenshot **and** page state (url, text, `#modalDetalleCivil` exists vs
shown, which `loadPre*` spinners hold content, backdrop/overlay count, iframes) at **8 s, 30 s and
60 s INTO the hang**, again when it gives up, and on a detail block. Failure paths only. The censo
workflow always passes it and uploads the folder as an artifact.

## Pointer defects found this session — all three were invisible in the logs

| defect | channel left empty | found by |
|---|---|---|
| `human_scroll` wheeled from `(0,0)` | 0 `mouseover` vs 12 for a positioned pointer (measured) | operator, watching |
| `scrollIntoView` before every click | page moved with no input device involved | operator, watching |
| `.focus()` into the cuaderno dropdown | keystrokes arriving with no pointer approach | operator's question |

⚠️ Two of three were found by **watching the browser**, not by reading logs. The logs said nothing
was wrong in every case.

## Negative results — do not rebuild these

- **`--idle-motion` does nothing.** Two runner arms, one variable, both died at exactly 10 opens
  on the same causa with the same signature. Kept off by default so the negative survives.
- **The pointer-approach fix on the cuaderno dropdown does not lift the wall** (above).

## Watching a worker live — `--live` + `watch_live.py` (2026-08-16)

`--shots` is a black box recorder: it answers *what killed it*, out of an artifact you can only
download once the job is over. This is the other half — **what is it doing right now** — and it
was asked for by the operator directly after the table above, which is not a coincidence: two of
the three pointer defects were found by watching a browser, and the runner is the one browser
nobody can watch.

```
runner ──(jpeg + log tail, every ~6 s)──▶ Neon.live_view ◀──(poll)── watch_live.py ──▶ localhost
```

**Run it.**

```
python -u worker_a.py ... --live          # any worker: A, B and C all take it
python watch_live.py                      # your PC — opens http://127.0.0.1:8899
python watch_live.py --once               # one text snapshot, no browser
```

The censo workflow has a `live` input (**default true**) and every worker B/C step in the night
queue passes `--live`. So a dispatched runner is watchable with nothing but `python watch_live.py`
on this machine.

**What the card shows:** the runner's host and public IP, its GitHub run id, uptime, seconds since
the last frame (green under 25 s, red over 90), the current phase, and the worker's own last 18 log
lines under the picture.

### Why it is built the way it is

- **Neon is the transport** because it is the only thing a runner and this desk already share. No
  tunnel, no new secret, no port opened, and it behaves identically for a local Chrome.
- **One row per slot, overwritten.** It is a window, not a recorder — `--shots` owns the history.
- **The phase text is the log tail's last line.** The narration a worker already writes IS its
  status; a parallel status vocabulary would drift out of step with the log.
- **A frame is sent only when the picture changed** (md5), and the viewer sends back the `seq` it
  already holds. A causa sitting through a 25 s pacing wait costs one frame at each end.
- ⚠️ **Every pacing wait now goes through `C.human_idle()`** — in A, B and C. That is what makes
  the view continuous: `human_idle` calls `cdp_scrape.IDLE_HOOK` about once a second, and the
  `time.sleep()` calls it replaced would have left the picture frozen for 20 of every 25 seconds,
  looking exactly like the hang we are hunting. With no hook installed and `IDLE_MOTION` off the
  helper is a single `time.sleep` — the pacing itself did not change.
- **Inside the modal wait loop too**, which is the ninety seconds that killed four remote sessions
  and the one stretch no log line describes.
- **It cannot break a run.** 5 s screenshot timeout (the library default is 30 s, and a page busy
  enough to need 30 s is exactly the page you would be watching), every path swallowed, one
  reconnect, then self-disable after 5 consecutive errors with a line in the log.

### ⚠️ It is a variable

Screenshotting occupies the renderer's main thread. It sends **nothing** to PJUD — CDP screenshots
are local — but "no requests" is not "no difference", and we are hunting a wall that appears at
exactly 10 opens remotely and never locally. Do not leave `--live` on for a one-variable test
unless the arm you are comparing against carries it too.

## WORKER H — the mimic (2026-08-16)

The operator drove a real session while `human_record.py` counted what they emitted. Everything
below is out of `data/human/session-20260816-212249.jsonl` — 6.5 minutes, 15 causas, 389 rows.

### What the recording killed

⚠️⚠️ **THE BURST HYPOTHESIS IS DEAD, AND THE REASONING BEHIND IT WAS A BAD COMPARISON.** The
planned "human dwell before switching books" test would have made us slower for nothing:

| | operator | worker A |
|---|---|---|
| causa open → switch to book 2 | **2.0 s median** (min 2.0, max 5.0, n=12) | ~4 s |
| causa open → next open | **13.1 s** (4.6/min) | 25 s (2.0/min) |
| `causaCivil.php` | **8.0 POST/min** sustained | ~4/min |

A person switches books in two seconds — faster than we do. The "29–38 s spacing in clean runs"
I cited as the baseline came from runs with the switch **disabled**, where that endpoint is hit
once per causa instead of twice: a one-POST pattern compared against a two-POST pattern and the
difference called a burst. **Pace is not what the site objects to** — now shown three ways.

### What it found instead

| channel | operator | worker A |
|---|---|---|
| `mousemove` | **25.8/s, on 98% of seconds** | 0 between clicks |
| `mouseover` | **6.4/s inside the modal** | only what a click path crosses |
| while a causa loads | **25.2/s — they keep moving** | 0, it sits in a wait loop |
| `keydown` | **ZERO all session** | ~54/tribunal + ~20 for dates |
| wheel inside the modal | **ZERO** (0.6/s on the list) | 2–5 notches per causa |

⇒ `--idle-motion` was tested at ~1/s — **one twenty-sixth of a hand** — and it vibrated in place,
so it crossed no elements and produced no `mouseover` at all. The negative result stands for that
implementation and says nothing about the channel.

### ★ The date fields are READONLY (operator, unprompted: "I can't type the dates")

`#fecDesde`/`#fecHasta` are `readonly` with `hasDatepicker`. `type_date_kbd` clears the `readOnly`
property, types into the unlocked field and presses Escape — **a sequence no user can produce**,
on the form where the token is minted, in every run this project has ever made. Worker H drives
the jQuery UI picker with the mouse instead. Three traps, each cost a live session:

- the widget opens in ~700 ms — **poll for it**, never sleep a flat interval;
- **never read its month/year from the header**: `.ui-datepicker-month` is a SPAN but
  `.ui-datepicker-year` is a SELECT, so `textContent` concatenates every option and `.value` read
  2020 while the header showed Agosto 2026 — one made it march backwards, the other forwards.
  Read `data-month`/`data-year` off a day `<td>`;
- **openness is not a state you check once** — it closes between the check and the read.

⚠️ And the fields **start empty**: an empty window searches instantly, returns nothing, and still
reports "results". Worker A never noticed because it typed them every time.

### Status

Zero keystrokes end to end, no wheel in the modal, dates by picker, pointer present throughout.
Measured live: `mouseover` 4.5–7.5/s (human 6.4) ✓, `keydown` 0 ✓, `mousemove` ~16/s against 25.8
— **capped by CDP round-trip cost on a heavy page, not by choice**: raising the target rate from
34 to 52 moved the achieved rate not at all.

**The operator's plan, in order:** (1) mimic the actions at their pace and confirm no block;
(2) maximise speed without tripping; (3) find how many can run in parallel; (4) only then remote.

### Step 1 — does the mimic block? (2026-08-17)

**No. 189 opens, 66 min, 12 courts, 15 searches, zero blocks**, stopped by us rather than by the
site. The remote wall lands at 10 opens; worker A's clean local record is 375.

### Step 2 — the speed ramp

`--ramp-every N --ramp-step F` cuts the READING TIMES only; the acts, their order, the pointer
rate and the zero keystrokes stay as measured, so a trip is attributable to pace and nothing else.

⚠️ **Time each causa open→next-open, and EXCLUDE the ones followed by a court change** — otherwise
a ~20 s search lands inside a causa's duration and reads as a slow causa. That artefact produced a
"29 s gated causa" that briefly looked like the site pushing back.

| reading × | gated causa | kept causa (both books) |
|---|---|---|
| 1.00 (operator) | 12.3 s | 19.6 s |
| 0.75 | 10.2 s | 17.2 s |
| 0.56 | 10.0 s | 13.7 s |
| 0.42 | 8.0 s | 11.3 s |
| 0.32 | 7.6 s | 10.5 s |
| 0.24 | 6.0 s | 9.3 s |
| 0.18 | — | 9.0 s |

★ **The floor is ~8–9 s per kept causa, ~5–6 s gated** — cutting reading from 3 s to 2.2 s bought
0.3 s. That residue is PJUD's own response time plus the acts, the same shape worker A's ramps
found. **~7 causas/min sustainable: 1.5× the operator's session, 3.5× worker A's 2.0/min.**
No block at 80 opens with reading at a tenth of the operator's.

### ⚠️ One profile dir per port

Chrome treats `--user-data-dir` as a singleton and the clash does NOT fail loudly: relaunching
onto a dir another Chrome still held produced a browser that came up, entered, searched, and was
closed under us 75 s later (`TargetClosedError`). That reads exactly like a site problem. Matters
most for step 3, where parallelism means several browsers at once.

### ★★ RESULT — 1,046 opens, 150 min, ZERO blocks, 7.0 causas/min (2026-08-17)

Ended by our own lifespan, not by the site.

| | opens | min | rate | blocks |
|---|---|---|---|---|
| worker A, best LOCAL ever | 375 | 190 | 1.97/min | 0 |
| worker A, best REMOTE ever | 306 | — | 1.59/min | ⚠️ **clean — ended on our own `--max-minutes`, NOT blocked**; "then blocked" here contradicted two other passages in this file and is corrected 2026-08-20 |
| **worker H at the floor** | **1,046** | **150** | **7.0/min** | **0** |

68 courts, 72 searches, 793 causas kept with both cuadernos, 253 discarded by the etapa gate.
**2.7× worker A's all-time local count at 3.5× its rate**, and 1.5× the operator's own session.

⇒ **Every pacing number this project ever carried was compensation for behaviour.** The 60 s
search gap, the 90 s causa gap, the 25 s worker A still ships — none of it bought what fixing the
pointer, the keyboard and the datepicker bought. Fourth time the one rule has paid out, and every
time the answer made us faster.

★ **Speed did NOT cost the pointer presence**, which was the obvious worry:

| reading × | mousemove/s | mouseover/s |
|---|---|---|
| 1.00 | 20.1 | 4.7 |
| 0.32 | 16.2 | 4.5 |
| 0.00 | 16.0 | 5.0 |

Held at ~16/s and 5.0 mouseover/s across 856 causas at zero reading time. The whole-run average
of 3.8/s is diluted by the next item, not by the ramp.

### ⚠️ STILL EMPTY: the pointer is frozen during SEARCHES

`ojv.wait_results` does not run presence, so 72 searches x ~20 s ≈ **23 of the 150 minutes had a
dead input channel** — 15% of the session. The recorded human session cannot settle what a person
does there because they searched exactly once. This is the same shape as every empty-channel bug
this project has found, and the fix is the one already used for the modal wait: run presence
through the search wait too.

### Step 3 — parallelism scales LOCALLY, 1.91x on two workers (2026-08-17)

Two workers, disjoint court ranges (0-100, 101-229), own port, own `--user-data-dir`, own output
files, arrivals serialised through a lock file released on the FIRST CONFIRMED SEARCH. Both ran
their full 60 minutes and stopped on `lifespan`. **Zero blocks.**

| configuration | opens | min | rate |
|---|---|---|---|
| 1 worker, reading x1.0 | 189 | 66 | 2.86/min |
| **2 workers, reading x1.0** | **328** (172 + 156) | 60 | **5.47/min = 1.91x** |
| 1 worker, reading floored | 1,046 | 150 | 6.97/min |

⚠️⚠️ **I ALMOST MISREAD THIS, THE SAME WAY THE BURST THEORY WAS MISREAD.** Compared against the
6.97/min FLOORED single-worker run, two workers at 5.47/min look like parallelism COSTING
throughput. But those arms differ in two variables (worker count AND reading speed). Against the
matching x1.0 baseline it is 1.91x — near-linear. **Check the arms match before reading the
number**; this is the second instance in one session.

★ **Two concurrent local sessions coexist for an hour with no block** — the opposite of the remote
runners, which were culled within fourteen seconds of each other. And presence held up under
load: 17.7 and 18.0 mousemove/s per worker, BETTER than the single floored run's 16.0/s.

**Filling June+July's cuaderno 2 (4,491 causas):** 26.1 h at one worker/operator pace, 13.7 h at
two, 10.7 h at one worker floored, **~5.6 h at two workers floored — PROJECTED, not measured**
(it multiplies two measured effects that could interact). That is one 60-minute run to settle.

### The search-presence fix, verified

`ojv.WAIT_PRESENCE` keeps the pointer alive through `wait_results`. Across both workers: **zero
`stale`, zero `timeout`** — searches returned `results` at 20 s and 41 s with the pointer moving.
The DOM-quiet risk (wait_results needs 10 s of silence and a hover class would reset it) did not
materialise. `--no-search-presence` remains as the control arm.

### ★ `human_click` looked for one point and gave up

It sampled a single random point in the middle 40% of the target and, if that point was covered,
waited a second and sampled again from the same range — eight times. The OJV entry tile refused
three whole entry attempts because `.gallery-item-info`, a caption that expands on hover as a
SIBLING of the link, kept winning the coin toss. **Our own pointer approach triggers the hover
that covers the target.** Now it offers a spread of candidate points and takes the first where our
element is genuinely on top; fully covered targets are still refused, which is the rule that
correlated with blocks in July (0 covered clicks -> 50 causas, 1 -> blocked at 23, 2 -> at 4).

### ⚠️ `select_option`'s default timeout is 30 s of silence

`#fecCompetencia` inside a collapsed accordion is not actionable, so the call sat for thirty
seconds and the run then aborted with "not the national tribunal list" — a misleading verdict for
a panel that needed reopening. 8 s timeout, then reopen the panel and retry once.

## ★★★ IT IS THE AGGREGATE RATE PER ADDRESS, NOT THE SESSION COUNT (2026-08-17)

The one-variable test that settles years of confusion. Four workers, disjoint court ranges, own
port, own `--user-data-dir`, own output files, arrivals serialised on the entry gate — **the only
thing changed between the arms is the reading speed**, and therefore the aggregate request rate:

| 4 workers, one IP | ≈POSTs/min | opens | survival |
|---|---|---|---|
| `--speed 0` (top speed) | ~56 | **60** | **all dead by minute 5**, 3 within 10 s of each other |
| `--speed 1.0` (operator pace) | ~23 | **593** | 2 on lifespan, 2 at 57.1 / 60.9 min |

**Ten times the output and eleven times the survival, from halving the rate with the SAME four
concurrent sessions.** Aggregate 9.9 opens/min — the best sustained figure measured: 3.5x one
worker at the operator's pace, 1.4x one worker at top speed.

⇒ ~~"Remote means ONE worker, chained with a cool-off. The parallelism that works is LOCAL."~~
**OVERTURNED.** That verdict, still in `pjud-censo.yml`, came from runs where shard count and
aggregate rate moved TOGETHER. The unexplained remote 4-shard death holding 74/16/2/38 opens —
"a per-session budget cannot produce that" — is exactly what four fast sessions behind one address
look like. **The right shape is MANY POLITE WORKERS, not few fast ones**, which is the opposite of
what every optimisation in this repo has aimed at.

★ And the polite configuration is also the FAITHFUL one: pointer fidelity was 15-20 mousemove/s
at x1.0 against 6-9 at top speed, because reading time is what the presence loop emits into. Top
speed buys throughput by spending the exact channel we believe keeps us unblocked.

⚠️ **THE DEATH SIGNATURE PROVES NOTHING BY ITSELF.** Three sessions stopping within ten seconds,
unequal work, `blocked=(False, '')`, no rejection page — we produced that on demand from local
resource/rate exhaustion. It is what a shared limit looks like from several sessions at once, and
it is indistinguishable from a coordinated cull.

⚠️ Open: both x1.0 deaths landed at 57.1 and 60.9 min, near the hour. Tail effect or coincidence
in a sample of two — unresolved.

### ⚠️⚠️ CHECK THE ARMS MATCH BEFORE READING THE NUMBER

Three times in one session I nearly drew a confident conclusion from a mismatched comparison:

1. the **burst theory** — our two `causaCivil.php` POSTs per causa against clean runs that fired
   ONE per causa, the difference called a burst. A person does it in 2.0 s.
2. **2-worker scaling** — 5.47/min against the *floored* single-worker 6.97/min, which reads as
   parallelism costing throughput. Against the matching x1.0 baseline it is 1.91x.
3. **4-worker death** — nearly attributed to concurrency, when the arm that died differed in speed
   too. It was the rate.

Each time the fix was the same: **name every variable that differs between the arms before
interpreting the result.** Two of the three would have sent a runner off to test the wrong thing.

### ⚠️ worker H has NO INGEST — tonight's harvest is only on disk

2,228 causa records and **1,659 cuaderno-2 historias** sit in `data/worker_h/h-*.json`. Neon still
shows 13 causas with a second cuaderno. I quoted fill estimates without mentioning this. The
records are safe on disk but they are not banked, and 1,659 of them already answer a third of the
4,523 outstanding for zero further site load.

---

## ★★★ THE AFTERNOON OF 2026-08-17 — every "block" was ours

Six failures were chased today under names that described nothing. Not one was the site. The
pattern is identical each time: a symptom we manufactured, given a label, then a theory built on
the label. What ended each of them was **making the failure describe itself**.

| we called it | it actually was | cost |
|---|---|---|
| "the form is wedged" | a Bootstrap TAB whose nav said `active` while its pane was `display:none` | an afternoon |
| "modal never opened" | `human_click` REFUSED the click and we ignored the return value | weeks, incl. the remote 10-open wall |
| "searches came back empty" | the site refuses a date range **longer than one month** | 3 workers, minutes from exhausting recoveries |
| "the 6th session is starved" | the browser WINDOW was too small to contain what we clicked | 1,224 causas |
| "the row is unreachable" | we had **never scrolled horizontally**, in any worker, ever | the same 1,224 |
| "modal never opened (paging)" | row indices read from a table still redrawing | 4 workers in one test |

### ⚠️⚠️ THE ONE THAT MATTERS MOST: check what your guards RETURN

`human_click()` refuses an unreachable target **on purpose** — a covered click sends a real click
to whatever is underneath, and that correlated exactly with getting blocked (0 covered → 50
causas; 1 → blocked at 23; 2 → at 4). It announces the refusal. **`harvest()` ignored the return
value.** So the worker clicked nothing, waited 90–106 s for a modal never requested, reported
`modal did not open`, and blamed PJUD.

The network tap settled it in one line:

```
[warn] human_click: objetivo tapado tras 8s — NO hago clic
[net] 0 responses since the click, causaCivil.php=0 :: []
```

**Zero. The site was never asked.** ⇒ A refused click costs ONE CAUSA, is counted in the run
verdict (`refused=N`), and must never spend a recovery.

### ★★ We had never scrolled SIDEWAYS

`page.mouse.wheel(0, dy)` — deltaX hard-zero everywhere. The results table is ~1,115 px wide, so
in a narrow viewport the magnifier column sits outside the window and **no amount of waiting or
vertical scrolling can reach it**. Enlarging the window hid it; `human_scroll_x()` fixes it.

Verified in the exact failing geometry (744×345 viewport):

```
before   target x=1307   scrollX=0     (off-screen right)
after    target x=697    scrollX=610   click succeeded
```

⇒ **Window size is a PREFERENCE, not a correctness requirement** — small tiled windows stay
watchable and still work. `--window WxH` sets it; `ensure_window()` applies it via
`Browser.setWindowBounds` (a REAL resize; never `Emulation.setDeviceMetricsOverride`, which fakes
a viewport with no window behind it).

⚠️ `--window-size=` on the command line was **not honoured**: six workers asking for 1440×900 came
up at 958×428, 673×483 and 726×434. Set it after launch and verify — the worker prints
`window: {vw,vh}` on arrival for exactly this reason.

### ⚠️ A tab that is "active" in the nav but not in the panes cannot be clicked back

`#BusFecha` is a Bootstrap tab pane. On a wedged page the nav item carried `active` while the pane
had lost `in active`, so **Bootstrap refused to switch to a tab it already believed was current**
— our click was delivered, trusted, and inert. Every `#fecTribunal` select then timed out at 8 s
on a control that was populated (232 options), enabled, uncovered, and simply INVISIBLE.

The repair is what a person does: click a different tab, then click back. And note the false cure
— re-entry rebuilds the form and re-selects the tab, so recovery *appears* to work and fails again
minutes later. **Recovery succeeding and the symptom returning quickly means you are resetting a
cause, not fixing it.**

### ⚠️ The OJV refuses a date range longer than ONE MONTH

`El rango de fecha no puede ser superior a un Mes` arrives as a sweet-alert; `wait_results` sees no
results and reports `empty`. **An invalid search and an empty one are indistinguishable from the
outside.** Refused at the door now, before a browser opens. Same shape as the date fields starting
EMPTY — which searches instantly, returns nothing, and still reports "results".

### ⚠️ Pagination: read the rows only after the redraw FINISHES

`advance()` returns when the FIRST row changes — a swap started, not finished. Reading then gives
indices into a table still rebuilding, and `.nth(i)` clicks a row whose handler has been replaced:
no request at all. **4 of 4 such failures in one test came after a page advance, none on page 1.**
`wait_idle` + a settle before reading, and a rol comparison at click time as the backstop.

## Where the backfill got to

| | morning | evening |
|---|---|---|
| causas with a cuaderno-2 historia | **13** | **4,948 of 5,739 (86%)** |
| useful opens | 27% (sweeping) | **95%** (`--fill`) |
| throughput | ~2/min (1 worker) | **~16/min (6 workers)** |
| estimated time to finish | 26 h | **~50 min** |

★ **`--fill` beats sweeping because discovery decays as it succeeds.** A sweep re-opens what you
already hold: 794 opens produced 217 new causas and 211 new cuaderno-2 historias — 27%. Fill asks
the database what is missing and opens only that: 1,009 opens, 871 kept, 95%. Two shards ended
`finished` having exhausted every court that owed them anything.

---

# THE 2026-08-18 SESSION — the runner can be single-stepped, and the block is ONE CAUSA

## Where the corpus stands (measured in Neon, 2026-08-18)

| | |
|---|---:|
| causas | **5,510** |
| causas with a cuaderno-2 historia | **5,377 (97.6%)** |
| cuaderno rows | 76,218 |
| litigantes | 23,517 |
| escritos | 586 |

By month of `f_ingreso`: **mayo 16 · junio 2,132 · julio 3,354 · agosto 8**.

⇒ **June and July are essentially done; May has barely been touched.** The May sweep reached
Arica and was refused there (below), so 15/05–31/05 is the outstanding window.

### The gate-rejected records were deleted, and the PDFs with them

The `etapa` gate discards `Terminada` / `Incidentes` / `Téngase por no presentada`, but 245 causas
harvested before the gate existed were still in the database. Operator's call: *"there's no need to
keep gate-rejected data or pdfs."*

```
245 causas   (218 "8 Terminada", 21 "6", 3 "4", 2 "7", 1 "1" — every one a Terminada variant)
1,591 cuadernos · 669 litigantes · 57 escritos          = 2,562 rows
163 Drive PDFs trashed  (163 ok, 0 errors)
5 backup tables *_predel_20260818 created, then dropped
```

⚠️ **A sweep will re-discover all 245 and pay one open for each.** Deleting them removes the
*record*, not the site's listing — the gate then rejects them again, for one open apiece, on every
future pass over June/July. That was flagged before deleting, and accepted. If the cost ever
matters, the fix is a `rechazadas` table of ids, not keeping the rows.

⚠️ **`ingest_worker_h.py` now records WHY a causa was rejected** (commit `246e48d`) — without it,
a gate-rejected causa is indistinguishable from one never visited, and gets re-opened every pass.

---

## `--trace` and `--step` — photograph every action, and stop before each one

Built this session (`77c1333`). The generalised lesson is in `SCRAPERS_HANDBOOK.md`; this is how
to *run* it.

```powershell
# a picture before and after every action, no pausing
python -u worker_h.py ... --shots data\shots --trace all --trace-max 400

# and stop before each action, waiting for a verdict through Neon
python -u worker_h.py ... --shots data\shots --trace all --step all `
                          --step-timeout 1800 --step-on-timeout abort
```

| flag | values | meaning |
|---|---|---|
| `--trace` | `off` \| `entry` \| `all` | `entry` = the arrival only (~30 frames, where remote runs die); `all` = the whole shift |
| `--trace-max` | default 400 | hard frame budget; a shift at `all` is thousands otherwise |
| `--step` | `off` \| `entry` \| `all` | block before each action until told `go` / `run` / `abort` |
| `--step-timeout` | 900 s | how long to wait for a verdict |
| `--step-on-timeout` | `abort` (default) \| `go` | silence ends the run — see below |

**The operator console**, on this machine, against the same Neon:

```powershell
python step_console.py --watch          # frames arrive, saved to data\step_frames\, path printed
python step_console.py --go             # one step
python step_console.py --run            # release the brake, let it finish
python step_console.py --abort          # clean stop, not a crash
python step_console.py --recent 20 --pull DIR --purge
```

Both workflows carry it: `pjud-fill.yml` has `trace` and `step` inputs, `pjud-censo.yml` has
`trace`. Each run ends with a **Contact sheet** step (`trace_sheet.py`) that emits one
self-contained HTML with every frame in order and its own account beside it — a zip of loose JPEGs
is a picture that was captured and still never looked at.

⚠️ **`--trace`/`--step` require `--shots DIR`.** The worker refuses at the door rather than
running a trace that writes nowhere.

⚠️ **A stepped session keeps moving while it waits.** `Stepper` calls `C.human_idle(page, 2.0)`
between polls. A browser frozen stone dead for five minutes is a louder empty telemetry channel
than anything this project has ever fixed.

⚠️ **Verdicts are `go` / `run` / `abort` only — deliberately no `skip`.** `step()` is a context
manager and cannot decline to run its own body without tricks, and a half-executed action is a
worse diagnostic than no action.

### ⚠️⚠️ The trace does NOT photograph the cuaderno switch

`cdp_scrape.step()` wraps `human_click`, because every *click* the scraper makes goes through that
one function — which is exactly why the instrumentation has no holes among clicks. **The cuaderno
switch is not a click.** It is hover → `.focus()` → `ArrowDown`, so it passes through no chokepoint
and produces no frame.

In run `32149016591` that is a **9.1-second hole in the middle of the only failure we have**:

| frame | t | what |
|---|---|---|
| 0101 | t+975.4 | after the row click — correct row (`C-936-2026`) highlighted |
| — | — | modal opens · cuaderno 1 parses 28 rows · **switch fires · F5 refuses** — no frames |
| 0102 | t+984.5 | modal open, header correct, historia EMPTY, rejection box overlaid |

⇒ **Chokepoint instrumentation has exactly the coverage of your chokepoint.** Route the
keyboard-driven selects through `step()` too before the next attempt at this.

---

## Two bugs the trace found immediately

### ★★ The datepicker DRAWS every day and DISABLES the ones it refuses (`431592c`)

Run `32098486677` entered on the first attempt and then died with `#fecHasta reads ''`. Frame 0024
showed Agosto 2026 with every day from **19 onward greyed out** — the run was asking for 31/08 on
2026-08-18.

jQuery UI renders all 31 cells; a refused day is
`<td class="ui-datepicker-unselectable ui-state-disabled">` holding a **`<span>`, not an `<a>`** —
so a day locator resolves to **zero elements** and the field stays empty. `pick_date_mouse` now
asks the DOM whether the cell is disabled *before* clicking it and says so, and `main()` clamps
`--hasta` to today (refusing a `--desde` in the future outright).

⚠️ **This overturned the second half of two earlier entries at once.** "Read `data-month`/
`data-year` off a day `<td>`, never the header" was right and stayed right; "if the day is drawn it
is selectable" was never written down but was assumed by every version of this code. **DRAWN IS NOT
SELECTABLE.**

⚠️ A local worker (p9641) died identically **without** stepping, which is what ruled out the
instrumentation as the cause. Reproduce a stepped failure unstepped before blaming the step mode.

### ⚠️ Worker A's screenshots were never switched on (`9482d86`)

`worker_a.py` carried its own `SHOTS` global and its own `shot()`, and **never set
`cdp_scrape.SHOTS`** — so every `C.shot()` call on the *shared entry path* had been a silent no-op
for worker A since the day it was written. Run `32135642944` took six `state=captcha` entry
refusals in a row and uploaded an **empty artifact**, while looking correctly instrumented from
outside.

Fixed: worker A sets `C.SHOTS` too, takes `--trace`/`--trace-max`, and its `shot()` now uses the
**shared counter** `C._shot_n[0]` — two writers into one directory with private counters both
wrote `001-*.png` over each other.

⇒ **Grep for every copy of a capability before trusting any of it.** Two copies of one facility,
one wired and one blind, is the same failure this project already recorded for the rejection
matchers — and it hurts most in instrumentation, because what fails is your ability to see
anything fail.

---

## ⚠️ `--fill` cannot open a range it has never discovered

Dispatching `pjud-fill.yml` for May returned **`nothing-searched`** and looked like a block. It was
not: `--fill` re-opens causas **already in Neon** that lack a cuaderno 2, and Neon held **zero** May
causas. There was no work-list, so there was no search.

⇒ **A completion worker needs a corpus; a new window needs `pjud-censo.yml` (worker A, sweeping)
first.** Fill and sweep are not interchangeable, and the failure mode of choosing wrong is a green
run that did nothing.

---

## The local fleets, June and July

Four local workers, two per month, `--fill`:

| window | opens | refused | signature |
|---|---:|---:|---|
| June, 2 workers | 20 + 21 | **0** | — |
| July, 2 workers | 30 + 31 | **7** | all seven the *lost click* — click delivered, `causaCivil.php`=0 |

⚠️ **My geometry theory for the July refusals was wrong, twice.** I predicted wide tables and
horizontal scroll; there were no `objetivo tapado` lines and no `[geo]` lines at all, and
`unreachable-row` was 0. The seven were the signature already documented in §"check what your
guards RETURN": the click is refused or lands inert, the site is never asked, and the worker
correctly costs it one causa and moves on.

---

## ★★★ THE MAY BLOCK IS ONE CAUSA — `C-936-2026`, and it is the cuaderno-2 switch

Two remote runs, dispatched hours apart, blocked at **the same causa**, at the same point, with the
same counters:

| run | mode | result |
|---|---|---|
| `32136655492` | `--trace entry` | entered attempt 1, swept 16 min, **19 causas · 13 with detail · 262 cuadernos ingested**, then blocked at `C-936-2026` |
| `32149016591` | `--trace all` | **reproduced exactly** — same causa, same `28 hist c1 · 0 hist c2`, same `rejF=2 hardRej=1`, 105 frames |

`C-936-2026` — 1º Juzgado de Letras de Arica, f. ingreso 19/05/2026, BANCO DEL ESTADO.

### What the frames show

```
0100  t+974.2  before the row click      iframes ['a-a4vqd75z5x8b','']            modals []
0101  t+975.4  after  the row click      iframes ['a-a4vqd75z5x8b','']            modals []
                 ↑ the CORRECT row is highlighted — C-936-2026
0102  t+984.5  before the modal close    + TSBrPFrame_cs_chlg_ajax_frame_810/811  modals ['modalDetalleCivil']
                 ↑ modal OPEN and CORRECT — ROL C-936-2026, F. Ing. 19/05/2026, BANCO DEL ESTADO
                   historia EMPTY, F5 rejection box overlaid, support id 8068285253452880612
```

Captured state at the block: `modal=True modalIn=False`, all four `loadPre*` spinners empty,
`overlays=0`, **two challenge iframes attached to the causa modal**.

### What that rules out

The operator's reading of the earlier frames was *"there's no blocking, just clicks landing
somewhere else"*, and the follow-up hypothesis was *"it might click things a human would not, or
click before it's fully loaded."* Both are answerable now, and the answer is no:

- **The click landed correctly.** Frame 0101 shows the right row selected; the modal opened on the
  right causa with the right header.
- **The page was loaded.** Cuaderno 1 parsed **28 historia rows** — the modal was fully rendered
  and read.
- **It is not pacing, rate, session age, or a burst.** **19 causas in the same session did the same
  switch successfully**, immediately before, at the same speed.
- **It is not position.** `32136655492` and `32149016591` reached it after different amounts of
  work and stopped at the same causa.

⇒ **The refusal is specific to the cuaderno-2 AJAX for this one causa.** Deterministic, per-causa,
after a session of identical successful switches. That is not the shape of a rate verdict — a rate
verdict is a function of *how much* you have done, and this one is a function of *which* causa.

### The two suspects in `select_cuaderno`, both raised by the operator's question

Neither is proven; both are things **a human does not do**, on **exactly the request that gets
refused**:

1. **Hover → `.focus()` → arrow keys is a control that receives keystrokes without ever being
   clicked.** The pointer-approach fix was added precisely because teleported focus is a tell, and
   it did not lift the old 10-open wall — but it left the *shape* intact: a `<select>` that never
   receives a `mousedown` and then emits keydowns. A person opens the dropdown.
2. **`wait_for_timeout(1600)` + worker A's `wait_for_timeout(900)` are flat sleeps, not
   conditions.** They were measured residentially and inherited by a datacenter runner whose
   round-trip is 17–23 s against a local 12–26 s. A fixed sleep tuned on one link is a guess on the
   other — and the constant that was "measured" was never measured *there*.

### Next tests, in order

1. **Read the token.** Open `C-936-2026` locally and dump `#selCuaderno option` values, then the
   same for a causa whose switch succeeds in that same court. If the per-causa token content is
   anomalous, the refusal is a signature match and nothing about our behaviour will fix it.
2. **`--no-cuaderno2` over 15/05–31/05.** If the sweep walks straight past C-936, the switch is
   confirmed as the trigger and we know the exact cost of avoiding it.
3. **Route the switch through `step()`** so the next reproduction is photographed instead of
   inferred (the 9.1-second hole above).
4. **Replace the two flat sleeps with a condition** — wait for the historia table to change, not
   for a number of milliseconds.

⚠️ **Do not run 1 and 2 together.** Two variables, one run, and the confusion this project has
already paid for three times in one session.

---

## Known cosmetic defect

The trace startup line prints a Windows backslash (`.../data/shots\trace`) on Linux runners. The
path itself is correct; only the message is wrong. Recorded so it is not chased as a path bug.

---

# WORKER H TAKES DOCUMENTS — cuaderno 2's PDFs, by corte (2026-08-19)

Asked for: *"6 local h workers, to retrieve all the PDFs of cuaderno 2, for the tribunales of
corte de santiago."* Worker H had **no document capability at all** — it is the metadata mimic,
1 open and 0 fetches — so this is new, and it is the first thing in this project that deliberately
aims at the endpoint worker A was rebuilt to avoid.

```powershell
.\Iniciar_Docs_Santiago.ps1 -Workers 6 -Desde 01/07/2026 -Hasta 31/07/2026
.\Iniciar_Docs_Santiago.ps1 -Workers 1 -MaxCausas 2 -DryList   # the work-list, or a smoke test
python scraper\ingest_worker_h.py            # Drive + Documentos, safe mid-run
```

| piece | where |
|---|---|
| one document fetch that reports WHY it failed | `cdp_scrape.fetch_doc_detail()` |
| `classify()` — pdf / apm / other | moved `worker_a` → `cdp_scrape`, re-exported under its old name |
| work-list mode `docs-c2`, and `--corte` | `worker_h.fill_targets(mode=, corte=)` |
| the document pass | `worker_h.fetch_row_docs()` |
| Drive upload, then `doc_url` on the row | `ingest_worker_h.upload_c2_docs()` |
| six detached workers, one month per launch | `Iniciar_Docs_Santiago.ps1` |

## ★★ The cost was measured BEFORE anything ran, off disk

188 banked worker-H JSON files already held the answer, so the sizing question cost no session,
no probe and no request:

| | |
|---|---:|
| cuaderno-2 historia rows examined | 23,326 |
| of those, carrying a document form | **23,286 — 99.8%** |
| documents per causa | **3.5** (median 3; 1:93 2:2158 3:2150 4:987 5:469 6:238 7:213) |
| endpoint split | `docuN.php` 60% / `docuS.php` 40% |

⇒ **an open goes from 2 requests to ~5.5.** Six workers here make roughly the request rate of
sixteen doing metadata, against the one law this project has measured — *the binding limit is the
aggregate request rate per address*.

⚠️ **2026-08-20: that "one law" is NOT ESTABLISHED** — see section 00. The arithmetic here still
holds (an open costs ~5.5 requests, so a doc fleet is far heavier per worker than a metadata one),
and holding the AGGREGATE rather than the worker count is still the right instinct. What changed is
that the number to hold it below is unknown on the current build: 52.9 req/min ran clean.

★ **Ask the data you already hold before you ask the site.** This changed the pacing, the warning
printed at startup and the whole plan (three launches, not one) before a browser opened. Confirmed
live on the first two causas: 4 and 3 documents, **exactly 3.5 per causa**.

⚠️ **The endpoint split is why the input NAME is read from the DOM.** `parse_historia` captures
the form action and value but assumes the input is called `dtaDoc`. Two endpoints serve these
rows; one evaluate costs nothing and gives the live truth.

## ⚠️ The document token is a ONE-HOUR JWT — a document cannot be banked and fetched later

Decoded from a banked record: HS256, `{iss, aud, iat, exp, data}`, **`exp − iat` = 3600 s**, with
`data` an opaque ciphertext. The site mints a fresh one every time the modal renders.

Two consequences, both structural:

- **Every document costs the causa open it hangs off.** There is no pass that "collects the URLs
  now and fetches them tonight". That is why this rides along with the book-2 switch instead of
  being its own worker.
- **It must be fetched while book 2 is the one on screen**, because the historia in the DOM is
  book 1's until the switch lands.

⚠️ Carry this to the C-936 question. `set_select_mouse` already records that the *cuaderno* option
values are JWTs the site re-mints per render; the document tokens are the same shape. If these are
opaque ciphertext with a rotating `iat`, **"C-936's token contains a byte sequence F5 rejects" is
a weak hypothesis** — the bytes are different on every render. Worth knowing before spending a
session on it.

## ⚠️ It aims at the endpoint worker A was REDEFINED to avoid

`docuN.php`/`docuS.php` refused 16 and 19 times on 2026-08-13, and the 2026-08-14 redefinition of
worker A to metadata-only existed precisely so it would stay clear of that endpoint. **This job
cannot: the documents are the job.** Expect refusals to be the first thing that appears, and read
them as a rate verdict on the address rather than as a broken worker.

### ★ What six workers actually produce — measured, and my estimate was 2.7× too high

I projected ~77 requests/min for six workers and wrote that into the launcher as a danger. The
first five minutes of steady state say otherwise:

| axis | measured | the ceiling it should be read against |
|---|---:|---|
| `causaCivil.php` (searches + opens) | **9.0/min** | ~~~56/min killed four workers in 5 min; ~23/min ran the hour~~ **BUILD-SPECIFIC, see section 00** — the same flags produced 27/min on 2026-08-20 and 52.9/min ran clean |
| documents (`docuN`/`docuS`) | **19.6/min** | **none exists** — this run is the measurement |
| everything | **28.6/min** | the proven six-worker metadata fill sat at ~32/min |
| trouble events, all six shards | **0** | |

**~7.8 causa opens/min, not the 14 I assumed.** Santiago's courts are large — 500+ registros, 21 s
searches — and `--fill` must paginate to reach its rows, so the search cost per causa is far higher
than in the small northern courts the 16 opens/min figure came from. The fleet is *gentler* than
the metadata fill it was modelled on, on every axis.

⚠️ **I derived the rate from a throughput figure measured somewhere else.** 16 opens/min came from
courts with ~100 rows; Santiago's have 500. The handbook already says *measure it, do not derive
it* — and `rate_watch.py` answered in one command what the estimate got wrong by a factor of 2.7.

⚠️ **Report the two axes separately.** They are different endpoints, and the only measured
ceilings belong to `causaCivil.php`. Merging them into one number silently compares a document
rate against a modal-rate ceiling, and there is no evidence for that comparison either way.

⚠️ **`rate_watch.py` COULD NOT SEE THIS FLEET.** It globbed `worker_a*/sweep.log` only, and had no
pattern for documents — so with six workers pulling PDFs at full tilt it printed `0.00/min` and
`[ok] within the range this IP has sustained cleanly`. **A rate tool that cannot see the fleet is
worse than no rate tool, because it answers the question with a reassurance** — and the launcher
tells the operator to use it. Fixed: it reads worker H's shard logs too, and `docs c2: N pdf` is
**summed, not counted** (counting the line would have under-reported by 3.5×, in the direction
that reads as headroom). Third time in three days that a capability existed in one worker and not
another; grep for every producer before trusting a consumer.

If it ever is too much, **take workers off** — never speed them up.

## Design decisions worth keeping

- **Stop at the first network-level refusal, per causa.** `TypeError: Failed to fetch` carries no
  rejection page and no challenge iframe, so `blocked()` sees nothing — on 2026-08-10 a worker
  went on buying opens whose every document was being denied. Spending three more requests to
  confirm what the first one said is how a session gets spent proving what it already knows.
- **`not_pdf` is an ANSWER, not a failure** — unless it is F5's APM interstitial, which is a
  refusal wearing a 200. `classify()` tells them apart; size and status never can.
- **Refuse to fetch when the DOM and the parsed historia disagree on row count.** The stamp back
  onto the historia is BY INDEX, so a table that re-rendered in between would attach every
  document to the wrong trámite — silently, in a column nobody re-checks. A skipped causa is
  cheap; a mis-filed document is permanent.
- **No second row-builder.** `ingest_cdp.build` already emits a `Documentos` row for any historia
  row carrying `doc_url`, keyed `<causa>-c<n>-<folio>-<k>-doc`. Verified against a synthetic
  record before a real one existed.

## ⚠️⚠️ THE GREEN RUN THAT THREW THE DOCUMENTS AWAY

The smoke run fetched 7 PDFs, verified every one as `%PDF`, uploaded all 7 to Drive, printed
`7 link(s) returned`, upserted five tables and finished **green**. The cuaderno-2 document count
in Neon stayed at **12**.

`ingest_worker_h` imports its table order from `ingest_worker_a`, whose `ORDER` is
`["Ruts","Causas","Litigantes","Cuadernos","Escritos"]` — **correct for worker A, which is
metadata-only and produces no documents**. So `ingest_cdp.build` built the Documentos rows and the
ingest loop never looked at that key.

⇒ Fixed by taking the canonical order from `ingest_cdp`, which owns the row builders, minus
`Tribunales` (insert-if-absent). **Do not hand-list tables in a consumer.**

★ This is the same failure as worker H having no ingest at all, one layer further in, and it was
caught by the same rule: **count it where it is meant to LAND.** Every counter on the way was
healthy. `NEON NOW: ... 19 cuaderno-2 documents` is the only line that was ever going to say so.

⚠️ **AND NOW THE INGEST IS ITSELF A LONG RUN — DETACH IT.** With ~3.5 documents per causa the
Drive upload is thousands of files, not the dozens worker A's ebook pass produced. Run through the
agent harness it was **killed at 2,406 uploads in flight**, after which the PDFs were partly in
Drive and the `documentos` rows were not written at all, because the upsert comes after the
upload. Launch it with `Start-Process` like any other long run and judge it by its log.

Re-running is cheap and idempotent: `upload_pdfs_parallel` consults the Drive cache first and
skips every name already in the folder, so a killed ingest resumes rather than re-uploading.

## ⚠️ PowerShell splits an -ArgumentList element on its spaces

`"--corte", "C.A. de Santiago"` reaches the process as **three** arguments and argparse dies with
`unrecognized arguments: de Santiago`. Instantly, into **stderr**, leaving an empty stdout log
that looks exactly like a worker still starting up — ten minutes were spent watching a log file
belonging to a process that had already exited.

1. **The quotes must be part of the value**: `"`"$Corte`""`.
2. **A watch that reads only stdout has no coverage for the crash.** The failure was in the file
   the watch was not reading; silence read as progress. Same shape as every empty-channel bug
   here, and the fix is the same — watch the channel where failure actually speaks.
3. **Run the smoke test down the path you are about to trust**, not around it with a hand-built
   command. `-MaxCausas` exists so the launcher itself is what gets tested.

## ★★★ JULY DONE — 983 opens, 3,370 documents, 92 minutes, ONE lost click

Six workers, `--speed 1.0`, one dispatch. Every shard ended `finished` — it exhausted its
work-list — not on our clock and not on a refusal.

| shard | opens | kept | gated | refused | documents | minutes |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 200 | 193 | 6 | **1** | 692 | 87.0 |
| 2 | 177 | 176 | 1 | 0 | 601 | 77.0 |
| 3 | 210 | 207 | 3 | 0 | 749 | 92.0 |
| 4 | 141 | 135 | 6 | 0 | 467 | 61.5 |
| 5 | 138 | 137 | 1 | 0 | 456 | 61.0 |
| 6 | 117 | 115 | 2 | 0 | 405 | 52.2 |
| **all** | **983** | **963** | **19** | **1** | **3,370** | **92** |

**983 opens against a 983-causa work-list — exact, to the causa.** 2.3 opens/min per worker,
~10.7 aggregate, 3.43 documents per causa (predicted 3.5 from disk).

### ★★★ The document endpoint did NOT refuse. Not once.

This is the finding worth carrying. `docuN.php`/`docuS.php` is the endpoint that refused 16 and 19
times on 2026-08-13 and the reason worker A was redefined to metadata-only on 08-14. Six
concurrent workers pulled **3,370 documents through it in 92 minutes with zero refusals** — no
`Failed to fetch`, no APM interstitial, no challenge iframe.

⚠️ **That does not clear the endpoint; it re-dates the evidence.** The 08-13 refusals came from
worker B, which fetches **40+ documents per causa** against this pass's 3.4, and from a session
whose other behaviour has since been rebuilt (pointer, keyboard, datepicker, horizontal scroll).
Two variables moved. What can be said is narrow and useful: **at ~20 document GETs/min behind a
worker-H session, this endpoint is not the wall we thought it was.**

⇒ The suspicion attached to `docuS.php` should be re-read as a suspicion about **volume per
session**, not about the endpoint. That is a testable difference and worker B is the arm.

★ **The single refusal was the "lost click", not a block:**

```
[13:38:29]     modal did not open after 92s
[13:38:29]       [net] 0 responses since the click, causaCivil.php=0 :: []
[13:38:29]       our click produced no causa request — one causa lost, session untouched
```

The guard did exactly what it was built to do on 2026-08-17: cost it one causa, spend no recovery,
and say plainly that the site was never asked. One in 983.

## ★ AUGUST BROUGHT UP TO TODAY — and the catch-up is TWO passes, not one

Operator: *"do the same with august and june. update the causa of august until today."*

June was a doc pass like July. **August was not**, and the difference is worth stating because it
will recur every time a window is brought current:

> `--fill --docs-c2` **cannot discover**. It re-opens causas the database already holds. The whole
> corpus stopped at **07/08/2026**, because that is where sweeping stopped — so August needed a
> **sweep first** (`Iniciar_Sweep_Corte.ps1`, worker A with the new `--corte`), then the doc pass.

⚠️ **That is two opens per new causa**, and a causa open is the scarcest thing this project spends.
It is the price of worker A being metadata-only by design — redefined 2026-08-14 precisely to stay
clear of the document endpoint. Fine for a short catch-up; if whole-corte catch-ups become
routine, the answer is a sweep that takes documents in the same open, not running this twice.

### `worker_a --corte`

Filters the tribunal list to one Corte de Apelaciones, read from Neon.

⚠️ **Applied AFTER the `len(tl) < 50` national-list check, never before.** That check is how the
worker knows it is looking at the national list rather than a wedged form's leftovers. Narrowing
to 28 courts first would abort every run — or worse, pass a filtered list off as the whole country.
Validate that all 230 are there, then take the slice. `--start`/`--end` then index the *filtered*
list, which is what a sharded corte sweep wants, and the worker says so.

### ⚠️ A slot's `state.json` belongs to the WINDOW that built it

All four sweep workers refused to start: each slot still held July's state, and *completion is
recorded per tribunal with no window attached*, so resuming would mark courts "done" that were
never searched for August's dates — silent under-collection reported as a clean finish. worker A
catches this at startup and is right to.

⇒ The launcher now reads each slot's `meta.desde`/`meta.hasta` **before opening any browser**,
names every mismatch and gives the remedy. Otherwise four workers launch, die into stderr, and
leave four empty stdout logs — which looks like four workers still starting up.

⚠️ **Archive, never delete.** A state file records which causas were GATED; deleting it buys
those opens all over again on the next pass.

### ⚠️ And the sweep must carry the corpus's own procedimiento filter

`worker_a.py --only-proc` defaults to **empty** (store every procedimiento), while
`Iniciar_Worker_A.ps1` and `ingest_worker_a` both use `obligaci.*dar`. A sweep launched without it
would quietly widen the corpus's definition for one window only, and nothing downstream would
flag the inconsistency. The launcher carries it as a parameter with that default.

### ★ What August actually holds — 25 bank causas in 19 days

28 courts, 4 workers, `range complete` on all four, **0 blocks / 0 recoveries / 0 swaps**.

| | July (31 days) | August (19 days) |
|---|---:|---:|
| registros per court | ~500 | **53–58** |
| bank causas per court | 40–100 | **0–2** |
| bank causas, whole corte | 983 | **25** |
| per day | ~32 | **~1.3** |

Date spread of the 25: `01/08:1 · 03/08:6 · 04/08:8 · 05/08:3 · 06/08:2 · 07/08:1 · 13/08:1 ·
18/08:2 · 19/08:1` — and **nothing at all on 08–12 or 14–17 August**.

⚠️ **I reached for "publication lag" and it does not fit.** A lag leaves the *most recent* days
empty, and 18–19 August have causas while 08–12 have none. The honest position is that the drop
is measured and unexplained. Candidates worth one cheap test each before believing any of them:
a genuine seasonal drop in filings; a bank-side pause; or something about how the OJV dates a
causa that makes `f_ingreso` not the day it became listable.

⇒ **Re-sweep August in a fortnight and compare.** If the empty stretches fill in, it is a listing
delay after all and the lesson is that a window is not final until it has been swept twice. If
they stay empty, the filings really were not there. Either way it is one search per court to find
out, and searches are the cheap act.

## ★★★ SANTIAGO COMPLETE — 1,270 causas, 4,368 documents, ONE failure in 1,293 opens

| pass | opens | work-list | refused | documents | wall clock |
|---|---:|---:|---:|---:|---:|
| July docs, 6 workers | 983 | 983 | 1 | 3,370 | 92 min |
| June docs, 6 workers | 263 | 263 | 0 | 884 | 28 min |
| August sweep, 4 workers | 25 | — | 0 blocks | — | 21 min |
| August docs, 4 workers | 22 | 22 | 0 | 105 | 6 min |

Every doc pass hit its work-list **exactly, to the causa**, and every shard ended `finished` —
having exhausted its list, not on our clock and not on a refusal.

| | causas | documents |
|---|---:|---:|
| June | 265 | 891 |
| July | 983 | 3,372 |
| August (to 19/08) | 22 | 105 |
| **total** | **1,270** | **4,368** |

**Every cuaderno-2 row is accounted for.** 4,451 rows exist for the corte; 4,368 carry a document;
the remaining 83 belong to **21 causas, all of them `8 Terminada`** — excluded by the etapa gate by
design, their historia rows left over from harvests that predate the gate. Non-gated gaps: **zero**.
Documents without a direct-download link: **zero**.

★ **The one failure was the lost click, and it retried clean.** `277-C-9207-2026` produced
`[net] 0 responses since the click, causaCivil.php=0` in July's shard 1; re-offered as a
one-causa work-list it opened in **ten seconds** and gave up both its documents. That is the
2026-08-17 guard paying out end to end: cost one causa, spend no recovery, say plainly that the
site was never asked — and stay in the work-list so the next pass collects it.

⚠️ **The gate is what makes the retry cheap.** `fill_targets` gates on the STORED etapa, so the
re-run offered **1 causa, not 22** — the 21 Terminada were filtered out before a browser opened.
Without `ingest_worker_h`'s `regated` UPDATE recording why each was rejected, that retry would
have bought 21 opens to rediscover what we already knew.

⚠️ **And read the table AFTER the ingest finishes, not during it.** I checked `causas.etapa`
mid-run and found 21 causas reading `1 Notificación` where they had been `8 Terminada`, and
called it a regression. It was not: the Causas upsert writes the newest non-gated record's etapa,
and the `regated` UPDATE — which restores the gate verdict — runs *after* it, in the same job
(`updated etapa on 674 gate-rejected causas`). A multi-statement ingest has an inconsistent
middle; sampling it there tells you nothing about the end.

## The Santiago work-list

`C.A. de Santiago` — **28 tribunales, 1,281 causas, 1,253 owing cuaderno-2 documents**, spanning
19/06 to 07/08, so **~4,400 PDFs**.

| window | causas owing | tribunales |
|---|---:|---:|
| June | 265 | 7 |
| **July** | **983** | **28** |
| August | 5 | 3 |

⚠️ **One month per launch, and it is not a preference.** The OJV refuses a range longer than a
month, and a fill run still finds its causa by SEARCHING the window and clicking the row — so a
causa outside the window can never be reached however much it owes. The launcher refuses a wider
window before six browsers arrive to be told the same thing.

⚠️ **Shard by court, so the court count must exceed the worker count.** July's 28 courts split
5/5/5/5/4/4 across six workers; June's 7 would leave five workers with one court each and one with
two. Run the wide month with the fleet, the narrow ones with fewer workers.

⚠️ **An empty work-list is neither success nor a block.** `--corte` matches `tribunales.corte`
exactly, and 25 tribunales carry an empty corte. A name that does not match yields zero causas,
which is now reported as *"either it is finished, or it was never swept"* rather than run as if
finished — the same trap as the May `nothing-searched` dispatch of 2026-08-18.

---

# ★★★★★ THE SPLIT — SPECS vs SETTINGS (2026-08-19)

Operator: *"the settings can change, the specs have to always be the best."*

```
   SPECS      how human the worker is       human_engine.py     ALWAYS THE BEST WE HAVE
   SETTINGS   what job it does, and where   worker_*.py         chosen per run
```

**Everything above this section was written when there were four workers and therefore FOUR
behavioural engines.** They were not equal, and the inequality was invisible because it lived in
four files nobody diffed against each other.

## Why this had to happen — the table that forced it

Measured 2026-08-19, by grepping each worker for the acts we know a human does and does not do:

| worker | dates | selects | pointer presence | sideways scroll |
|---|---|---|---|---|
| A | **types into `readonly`** | keyboard | **none** | **none** |
| B | **types into `readonly`** | keyboard | **none** | **none** |
| C | **types into `readonly`** | keyboard | **none** | **none** |
| **H** | mouse picker | mouse | 19 call sites | yes |

`type_date_kbd` deletes the `readOnly` property, types into the unlocked field and presses Escape
— **a sequence no user can produce** — on the form where the session token is minted. Worker H
stopped doing it on 2026-08-16 and became the only worker that has never been blocked at scale.
A, B and C were still doing it three days later.

⇒ And on 2026-08-19 the August catch-up ran its **discovery** pass on worker A: the least human
worker we owned, sent to do the one job that must visit courts it has never seen.

★ **A fidelity fix that lives in a worker protects one worker.** That is the same failure this
handbook already records for the rejection matchers, for worker A's unwired screenshots, and for
`rate_watch` being blind to worker H — except here the thing that silently differed was *the
behaviour the whole project is built on*.

## What moved

`human_engine.py` — imported by A, B, C and H, and it imports no worker (`CIVIL` moved with it,
because competencia 3 is a property of the SITE, not of a worker).

| | |
|---|---|
| `jitter`, `read` | reading times, spent moving over the content being read |
| `hover` | reach a control and stop; **never click a `<select>`** (native popup = an OS surface no CDP event reaches) |
| `set_select_mouse` | pointer arrival, zero keystrokes, poll the value back by INDEX |
| `pick_date_mouse` | drive the site's own jQuery picker with the mouse |
| `close_modal_human` | close, then wait for it to actually be GONE |
| `build_form_mouse` | the whole search form, mouse only |
| `READ_BOOK1/BOOK2/LIST`, `SPEED`, `RAMP_*` | the measured human's timings |

Still shared from `cdp_scrape`: `human_click` (arc, dwell, refuses covered targets),
`human_scroll` / `human_scroll_x`, `human_idle`, `fetch_doc_detail`. `human_motion.Presence` is
the hand itself.

⚠️ **`type_date_kbd` is kept but marked SUPERSEDED**, because three probes still call it — and a
probe that types where the worker now picks **is not measuring the worker any more.** Fix the
probe before trusting any comparison it produces.

## ⚠️ Setting a spec on the worker instead of the engine is the same bug, one layer in

`read()` divides by `human_engine.SPEED`. `main()` originally set a worker-local `SPEED`, which
would have been assigned, printed, ramped and written into the run report **while every reading
span went on using 1.0** — and the log line reporting the speed reads the wrong copy, so nothing
would ever have said so. Workers now set `E.SPEED`, `E.RAMP_EVERY`, `E.RAMP_STEP`.

⇒ **A module-level global is part of the facility.** Move the function and you must move who
writes to it.

## ★★ THE OPTIMUM IS NOT THE MAXIMUM

The target is the recorded human's **distribution**, not more of everything. A pointer emitting
40 moves/s is as anomalous as one emitting 0 — just in the other direction.

| channel | human | worker H |
|---|---:|---:|
| `mousemove` | 25.8/s, on 98% of seconds | ~16/s |
| `mouseover` inside the modal | 6.4/s | 4.5–7.5/s ✓ |
| `keydown` | **0 all session** | **0** ✓ |
| wheel inside the modal | **0** | **0** ✓ |

We are **under** on `mousemove` and capped by CDP round-trip cost on a heavy page — raising the
target from 34 to 52 moved the achieved rate not at all. Under is the direction to fix. **No spec
may be "turned up" without a recording that justifies the new value.**

## ⚠️ EVERY NUMBER IN THE ENGINE RESTS ON n=1

One operator, one 6.5-minute session, 15 causas
(`data/human/session-20260816-212249.jsonl`). It is the best evidence this project has and it is
still one person on one evening. **The search wait cannot be derived from it at all** — they
searched exactly once. Treat the constants as the best current estimate, never as settled.

## ⚠️ TWO KINDS OF WAIT, AND CONFLATING THEM COST REAL DATA

| | driven by | correct form |
|---|---|---|
| wait for the SITE to answer | the server | **a CONDITION**, never a duration |
| wait because a HUMAN is not instant | the person | **a DURATION**, from a distribution |

Stripping "padding" once removed the pause after the cuaderno switch, so the historia was parsed
before the AJAX had re-rendered it — causas banked with an empty book 2 while the switch itself
had succeeded. Silent data loss, from an over-applied rule.

`Presence.run(secs, poll=…)` is the first kind; `read()` is the second; **both keep the pointer
alive throughout**, which is what makes them one primitive rather than two.

★ **The protocol, stated once:** *act → wait for the reaction (a condition) → pause as a person
would (a duration) → act again*, with the hand moving over content for the whole of both waits.

⚠️ **Not yet applied everywhere.** 11 raw `wait_for_timeout`/`time.sleep` calls survive in worker
H against 19 presence-backed ones. Every one of them is a stretch of dead telemetry, and they are
the next thing to close.

## ⚠️⚠️ TREMOR IS NOT THE MECHANISM — this was already measured

The instinct that a hand keeps moving during a wait is right and is exactly what presence does.
**Tremor is the one implementation already proven to produce nothing.**

`--idle-motion` emitted ~1/s and *vibrated in place*: it crossed no element boundaries, so it
generated **zero `mouseover`**. `mouseover` only fires on crossing a boundary. The recorded human
during a wait was not trembling — they were **travelling over content**, 25.2 mousemove/s and
6.4 mouseover/s.

⇒ Motion during a wait must have a DESTINATION. Physiological tremor may well be worth adding on
top of travel if F5 reads raw coordinates — but it is unproven, and it cannot replace travel.

## Where the split is not finished

1. **Presence is still worker-H-only.** A, B and C now use the engine's dates, selects and
   datepicker, but their harvest loops emit no `mousemove` between clicks. That is the largest
   remaining fidelity gap and it needs their loops restructured, not a one-line swap.
2. **The four workers are still four programs.** The end state is ONE worker whose settings pick
   the job — discovery / collection / documents / refresh. A, B and C keep only their *jobs* now;
   folding those into settings is what retires them.
3. **`worker_h`'s sweep is page-1-only** by design (fidelity: the recording read one page). That
   is why discovery still needs worker A, and it is a spec/settings conflict worth deciding
   deliberately rather than by default.

---

# ANEXOS — the document class we never knew existed (2026-08-19)

Operator wants the **contrato**, because a demandado's email address is sometimes in it. (Email
extraction stays a human job — we download the PDF, a person reads it.)

## ★★★ It was found by WATCHING, and it had been invisible for months

A 40-minute recorded human session produced four endpoints that appear **nowhere in this
codebase**, and the biggest of them outnumbered the one we do fetch five to one:

| endpoint | hits in one session | known to our code |
|---|---:|---|
| `anexoDocCivil.php` | **30** | **no** |
| `anexoCausaCivil.php` | 7 | **no** |
| `docCertificadoEscrito.php` | 4 | **no** |
| `anexoCausaSolicitudCivil.php` | 1 | **no** |
| `causaCivil.php` | 17 | yes |
| `docuN.php` | 6 | yes |

`parse_historia` looks for the anexo as a `<form>` in `td[2]`. Across **117,173 banked historia
rows it found NONE.** The column was right — the headers really are
`['Folio','Doc.','Anexo','Etapa',…]` — and the *shape* was wrong. The site puts an **anchor** there.

⇒ **"We never look for it" and "these causas have none" produce identical evidence: zero.** That is
what made this invisible, and it is the same shape as every other silent gap in this project.

## The structure

```
<a onclick="anexoCausaCivil('<JWT>')">            opens #modalAnexoCausaCivil
<a onclick="anexoSolicitudCivil('<JWT>')">        opens #modalAnexoSolicitudCivil
<a onclick="anexoSolicitudCivilEscrit('<JWT>')">  opens #modalAnexoSolEscritoCivil

  the folder is a table:   Doc. | Fecha | Referencia
  <form action=".../anexoDocCivil.php"><input name="dtaDoc" value="<JWT>">
  <a onclick='$(this).closest("form").submit();'>Descargar Documento</a>
```

**TWO ACTS, NOT ONE:** open the folder, then take what is in it. Anything looking for a direct
link concludes the causa has no anexos.

⚠️ **The anchor has no id, no class and no text** — it is an icon. It is located by its `onclick`
prefix, and **the opening paren is load-bearing**: `anexoSolicitudCivil` is a PREFIX of
`anexoSolicitudCivilEscrit`, so without it the Escrito anchors get clicked against the wrong modal.

⚠️ `#modalAnexoSolicitudCivilSII` exists in the page and is deliberately **not** in `ANEXO_SOURCES`.
An entry should mean "observed in the wild", not "the id exists".

## ★★ Where it lives: the HISTORIA as often as the caratulado

Operator said the folder is *"almost always in the caratulado, sometimes in the historia of book 1"*.
Six **gated** bank C- causas in the 19º Juzgado Civil de Santiago:

| causa | where |
|---|---|
| C-10359 | caratulado ×2 (`anexoCausaCivil` + `anexoSolicitudCivilEscrit`) |
| C-10317 | caratulado |
| C-10268 | **HISTORIA** row 9 |
| C-10101 | **HISTORIA** row 6 |
| C-10100 | caratulado **+ HISTORIA** row 7 |
| C-10089 | **HISTORIA** row 3 |

**Four of six in the historia** — in this court the majority, not the exception.

⚠️ **I claimed the historia path was unreachable. It never was**: the selector is scoped to
`#modalDetalleCivil`, which *contains* `#historiaCiv`. And my "the Anexo cell is always empty" came
from dumping only the first three historia rows when the anexo sits at rows 3, 6, 7 and 9. **Three
rows is not a sample.**

## ⚠️⚠️ THE FOLDER MODAL IS ONE GLOBAL ELEMENT — it filed one causa's documents under another

The worst bug of the day, caught by a test run that was only meant to confirm a refactor.

`#modalAnexoCausaCivil` and friends are **one element reused by every causa**. The wait condition
was *"is the folder table non-empty?"* — satisfied INSTANTLY by the previous causa's rows.

```
277-C-10100 (BancoEstado/VARAS)   md5 82983c28   229785
277-C-10101 (BCI/MANSILLA)        md5 82983c28   229785
```

Two banks, two debtors, **byte-identical PAGARÉ and CONTRATO**. A pagaré carries the debtor's own
details; identical across two debtors is impossible. Three of nine PDFs were mis-filed, and the
FIRST smoke test had it too — which I had reported as a clean success.

⇒ **This is the oldest trap in this project wearing new clothes.** `HANDOFF_WORKERS` already says
it about search results: *freshness must be proven by the NETWORK, not the DOM, because the site
leaves the previous content on screen while the new one loads.* I wrote the same bug anyway, in a
new place, three months later.

⚠️ **Mis-attributed documents are much worse than missing ones.** Nothing downstream can tell them
apart, the file is named after the wrong causa, and the entire point of this class is to read a
NAMED PERSON's contract.

**The fix:** the `dtaDoc` JWTs are minted per render, so they are the freshness signal — wait for
them to CHANGE, and if they do not, **take nothing and say so.** Failing closed is the only safe
direction.

**Verified, same 6 causas, same court, before and after:**

| | before | after |
|---|---:|---:|
| cross-causa duplicate PDFs | **3** | **0** |
| inventories matching their causa | no | yes |

The before-run was lagging by exactly one causa throughout: C-10317 reported C-10359's 9 documents,
and C-10089's "1 document, PAGARÉ 883 KB" was C-10100's content arriving late.

⚠️ A duplicate *within* one causa is fine — C-10100 really does carry the same pagaré in both its
caratulado and its solicitud folder. That is a filer's choice, not our bug.

## ⚠️ A folder is a modal OVER a modal

Closing one leaves its `.modal-backdrop` behind, so the next anchor is refused as covered — exactly
what `close_modal_human` documents. **But the engine's condition cannot be reused here**: it waits
for NO `.modal-backdrop` at all, which is right for the causa modal and impossible for a nested
one, because the causa modal underneath keeps its own the whole time. Bootstrap STACKS backdrops,
so the condition is that the **count returns to what it was** before this folder opened.

⚠️ **Still unexplained, failing safe:** `anexoSolicitudCivilEscrit`'s anchor is refused by
`human_click` on C-10359 in both runs, with no backdrop warning — so the backdrop fix, though
correct, is not what blocks it. 1 of ~16 anchors seen. It skips and logs. **Diagnose it; do not
guess at it.**

## ★★★ ENUMERATE ALWAYS, DOWNLOAD SELECTIVELY — and it paid out immediately

Opening a folder is **one request and yields every label**; downloading is one request each.
So `--anexos` records the whole inventory for every causa and downloads only what matches
`--anexo-match` (default `contrato|cto|ctoi|pagaré`).

⚠️ **`Referencia` is FREE TEXT typed by the filer.** Real labels, minutes apart:

```
'1. CONTRATO DE ARRENDAMIENTO'   '2. COPIA INSCRIPCIÓN DE DOMINIO'   '6. MANDATO JUDICIAL'
'pagare'   'mandato claudio altamirano'   'CERTIFICADO LABORAL CLAUDIO ALTAMIRANO'
'MUTUO'    'EP MUTUO HIPOTECARIO Repertorio Nº 10.180-20'   'Cartola operaciones créditos'
```

Numbered or not, any case, sometimes carrying a person's name. Operator: for Promotora CMR
Falabella the contrato is **'CTO'** or **'ctoi'**. **A pattern WILL miss** — which is exactly why
the enumeration is never gated on it, and why "we looked and found no match" must stay
distinguishable from "we never looked".

★ **It earned its keep on the first real run:** `MUTUO` appears in **three of five** causas'
inventories and the default pattern matches none of them. A *mutuo* is the loan contract itself in
a mortgage-backed case — the contrato equivalent. We know that from real labels across real banks,
instead of discovering in six months that mortgage cases silently yielded nothing.

## ⚠️ How many anexos can a causa hold? UNKNOWN

An early draft of the code said "six" as though it were a bound. Six was the largest of FIVE
observations (6, 5, 3, 3, 3). **One causa later showed NINE.** A sample maximum is not a maximum,
and this number drives the requests-per-causa estimate.

**The cheap test costs no downloads at all:**

```
worker_h --anexos --anexo-match "$^"     # a pattern that matches nothing
```

enumerates every folder and fetches none — one request per folder — so a few hundred causas give
the real distribution out of `listed`.

## ⚠️ And the probe must obey the worker's gate

The first `anexo_probe` took rows 0..N straight off the results table and promptly spent four causa
opens on **E- rols — exhortos**, which this project does not collect. Two costs, the second worse:

1. a causa open is the scarcest thing here, spent on causas we will never store;
2. **the evidence was then about the wrong population.** Every multi-anchor observation I first
   cited came from an exhorto; the C- causas showed at most one anchor per function.

It now uses `C.page_bank_causas` — the workers' own gate (C- rol AND a bank party). 101 rows → 31
candidates, the first at row 9.

⇒ **A probe that samples a different population than the worker answers a different question, and
nothing in its output says so.**

---

# ★★★★★ THE DUTY CYCLE — we emit 68% MORE than a human, not less (2026-08-19)

The first time a worker was recorded with **the same instrument as the human**, and it inverted
everything this project believed about its own pointer.

| | active/wall | mousemove per ACTIVE s | mousemove per WALL s |
|---|---|---:|---:|
| worker (8 causas) | **93% active, 7% silent** | 21.0 | **19.5** |
| human (40 min) | **46% active, 54% SILENT** | 25.1 | **11.6** |

**The human is silent for 54% of their session. The worker is silent for 7%.**

Per active second we sit at 84% of the human — close, and that is the number this project had been
quoting. Per WALL second we emit **68% MORE than a human does**, because we almost never stop.

## The structure of the silence, which is the actual spec

| | silent stretches | median | p90 | max | 15-60 s | >60 s |
|---|---:|---:|---:|---:|---:|---:|
| human, 40 min | **129** | 6.1 s | 28.3 s | 60.4 s | **29** | 1 |
| worker, 3.6 min | 5 | 3.0 s | 8.2 s | **8.2 s** | **0** | 0 |

Per minute the human stops **3.2 times**; the worker stops 1.4 times and **has never once been
still for more than 8 seconds.** The human was still for 15-60 s on twenty-nine separate occasions.

⇒ **Every spec we had been tuning was a RATE. This is a RHYTHM.** A person works in bursts
separated by real stillness; the worker is a continuous 21/s hum that never pauses to think. On
rates we are slightly off. On the duty cycle we are categorically different, and it is the one an
observer would notice first.

## ⚠️⚠️ HOW THIS HID FOR SO LONG: active seconds versus wall seconds

Three claims made in one session, all wrong, all from the same root:

1. *"We emit 16/s against the human's 25."* — wall-seconds compared against active-seconds.
2. *"Non-causa time emits about 5/s."* — arithmetic on those mismatched denominators.
3. *"The form path is where the pointer dies."* — it runs at 19/s there, the same as in a causa.

**You cannot be UNDER on a metric that excludes the silence.** The recorder averages over seconds
in which something happened; a worker that never stops has almost no excluded seconds, and a human
has more excluded than included. Comparing those two averages compares two different populations
of second — the same "check the arms match" error this handbook records three times over, made
again, by the author of the entry.

⇒ **Report both, always: per-active-second AND per-wall-second, with the silent fraction beside
them.** Either alone is a trap.

## What it costs to be wrong in this direction

⚠️ **`E.PRESENCE` — routing the engine's waits through the presence loop — moved nothing** (19.3 →
19.5/s wall, 7% → 7% silent) and its entire justification was the denominator error above. It is
kept because a wait genuinely should have a hand on it, and it is harmless. **It fixes nothing.**
Worse, it pushes in the wrong direction: it fills previously-quiet stretches with more motion, on
a channel where we already emit too much.

★ This is "THE OPTIMUM IS NOT THE MAXIMUM" arriving exactly where the engine's own header warns it
might — on the spec nobody was looking at. Every instinct in this project has been *more presence
is more human*. Past a point it is the opposite, and we are past the point.

## The next spec, with its target distribution already measured

Draw complete-stillness intervals from the human's distribution and insert them at natural
boundaries (between causas, mid-read, after a search returns):

```
55 x  2-5 s      44 x  5-15 s      29 x  15-60 s      1 x >60 s
median 6.1 s     p90 28.3 s        max 60.4 s
~3.2 stops per minute
```

⚠️ **Judgement call, not a mechanical fix.** Some of that 54% is the operator being interrupted,
reading off-screen, or tabbed away — there were 52 `visibilitychange` events in the session. Whether
a worker *should* mimic being interrupted is a real decision, and it costs throughput directly:
matching the human duty cycle roughly halves opens per wall-hour. But "never still for more than
eight seconds across an entire session" is not a thing a person does, and that is what we ship today.

⚠️ **And do not implement it as a lower RATE.** The human's 25.1/s while moving is higher than our
21/s. The fix is to stop sometimes, not to move more slowly — those produce the same wall-clock
average and completely different distributions.

---

## THE DUTY SCHEDULER — built, broken twice, now measured correct (2026-08-19)

`--duty human` shipped at **1.86 stops/min and 19% silent** against the 59% target above. The
fault was not the sampler and not truncation. Both earlier diagnoses were guesses from the output;
the one that worked logged every draw (`E.DRAWN`, reported as the `DUTY DRAWS:` line before `DONE`)
so the question became a subtraction.

**What was wrong — two independent defects in one function:**

1. `maybe_still()` rolled `SILENCE_PER_MIN * window_secs / 60`, which is 3.23 stops per minute of
   **covered window**. Only `read()` and the causa load ever called it, so search waits, form
   building, navigation, ingest and modal closes had probability **zero**. → 1.86/min.
2. `waiting_for_site()` had absorbed the old `still()` body's last line as an unconditional tail,
   so the presence path waited `secs` via `pres.run()` **and again** on a raw timeout. Every search
   wait was double length. It compiled and ran clean.

**What it is now:** one wall-clock deadline (`E.arm_duty()` / `E._NEXT_STOP`), armed with
`expovariate(1 / ACTIVE_GAP_MEAN)` where `ACTIVE_GAP_MEAN = SILENCE_MEAN * (1 - DUTY_TARGET) /
DUTY_TARGET` = 7.6 s. ⚠️ **Not `SILENCE_PER_MIN / 60`** — re-arming after a stop means the gap only
elapses while working, so its mean is the mean ACTIVE stretch (7.6 s), not the mean wall interval
(18.6 s). Shipping the obvious version gives 2.04 stops/wall-min, the same shortfall in a new
costume. Caught by simulating against a fake clock, not by a run.

The local `random() < 0.55` in `waiting_for_site` is **gone**: a machine wait is just another
boundary, offered to the same scheduler. One rate governs the session.

**Measured, 14 causas, tribunal 277, July window — identical to the broken run:**

| | before | after | operator |
|---|---:|---:|---:|
| stops/min (drawn) | 1.86 | **3.29** | 3.23 |
| stop median | 2.0 s | **6.4 s** | 6.1 s |
| silent, drawn/wall | 19% | **42%** | 59% |
| silent, recorder | — | 33% | 59% |
| opens/min | 2.4 | 1.8 | 4.6 |

⚠️ **The mean stop reads 7.7 s against an expected 11.1 s and that is NOT residual truncation.**
20,000 bootstrap samples put 7.7 s at the **9th percentile** of what n=25 produces; the entire
deficit is that no draw landed in the top decile (28-60 s), a 7.2% event. The median is robust to
that tail and lands at 6.4 s vs 6.1 s. **Judge this spec by its median, or budget enough draws to
see the tail** — a 14-causa run cannot resolve the mean.

⚠️ **Why the recorder reads 33% while the draws imply 42%:** the recorder's wall clock (541 s)
brackets entry and form-building, where the worker is continuously active and takes no scheduled
stops; the worker's own causa-loop wall was 456 s. It also counts **36** stops to our 25 — the extra
~11 are natural 2-3 s site waits. That mixed population is the whole reason the pre-fix median
looked pinned at 3.0 s, and it is why `DUTY DRAWS` exists as a separate, unmixed measurement.

⚠️ **Boundary density is now the remaining lever, and it is visible.** Simulated against a virtual
clock: boundaries ~1 s apart → 3.16/min and 63% silent; ~5 s apart → 2.82/min and 54%; ~15 s apart
→ 2.02/min and 40%. If a future job stops calling `read()` as often, the duty cycle falls with it
and nothing will say so. Re-run the sim when the causa loop changes shape.

**New, unrelated, and now visible for the first time:** with duty on we emit **17.6 mousemove per
active second against the operator's 25.1**, and 8.6 per wall second against their 11.6. The rate
spec is now UNDER on both denominators — the opposite of the pre-duty finding. Not chased here.

`human_profile.py` now prints the duty block (wall seconds, silent %, stops/min, stop-length
distribution) **above** the rates, and every rate per ACTIVE and per WALL second side by side. It
previously reported per-active-second only, which is exactly the trap its own handbook entry
warns about.

---

# ★★★★★ THE BENCHMARK IS LIVE RESULTS, NOT THE RECORDING (2026-08-19)

**Sustained causas per hour without tripping.** That is the score. Fidelity to the operator's
recorded session is not the score, and for one day it silently became it. See
`felipe/CLAUDE.md` -> "The ultimate goal" and the handbook's Part 0.

The recording is an **instrument for finding variables and their plausible ranges**. It is how we
learned a duty cycle exists, that wheel deltas are quantised, that holds sit near 100 ms, that a
person types nothing. It cannot tell us which value inside the plausible range to ship, because it
never touches the site.

## The two lists — sort every spec into one of them

| validated against LIVE outcomes | validated only against the RECORDING |
|---|---|
| ⚠️ aggregate request rate — **the 56/23 pair is BUILD-SPECIFIC and the causal claim is suspended** | **duty cycle** — cost measured at ~50% throughput, benefit never measured |
| covered clicks (0 -> 50 causas, 1 -> blocked at 23, 2 -> at 4) | pointer rate (mousemove/s) |
| `--fill` vs sweep (95% useful vs 27%) | click hold (~100 ms) |
| headless / background tab / direct navigation all fatal | wheel quantisation, focus bands |
| 4 workers @ 27 req/min, 19+ min clean (2026-08-19, today's build) | zero keystrokes |

⚠️ **The right-hand column is not "wrong" — it is UNPRICED.** Each entry may be buying survival or
may be pure cost. The way to find out is a live A/B at a matched request rate, not a closer diff
against the recording.

⚠️ **The tell that you are optimising the proxy**: your success metric can be computed offline from
files, with the site switched off.

## ⚠️⚠️ `--speed 0` NO LONGER MEANS WHAT IT MEANT — historical rate figures do not transfer

Relaunching the 08-17 control exactly (4 workers, one IP, disjoint court ranges, `--speed 0`):

| | 2026-08-17 | 2026-08-19 (same flags) |
|---|---:|---:|
| aggregate | ~56 req/min | **27.1 req/min** |
| survival | all four dead by minute 5 | **19+ min, zero trouble** |

`--speed` zeroes only the READING times. Since August the engine has grown real motor work that no
speed setting removes — pointer travel, mouse-driven selects, the datepicker — so today's "top
speed" produces **half** the request rate the same flag produced two days ago.

⇒ **The known-fatal 56 and known-safe 23 are properties of a BUILD, not of the site.** Any
experiment that assumes them is measuring history. Re-measure the wall against the current build
before designing anything around it.
⇒ This killed Experiment B as specified: it needed 4 workers at ~56 and 8 at ~28, and today that
would take 8 and 16 workers respectively. Arm 1 was the validity check and it correctly refused to
reproduce; arm 2 was not launched.

## The arm-1 result, scored the new way (2026-08-19, 22:45-23:10)

4 workers, `--duty off --focus off --speed 0`, sweep of July, one residential address:

    589 causas opened     23.5 causas/min aggregate     26.2 req/min
    556 passed the gate   4/4 shards reached the 25-min lifespan cap
    refused=0             ZERO trouble events

⚠️⚠️ **AND 23.5 OPENS/MIN IS NOT THE SCORE. 13.3 NEW RECORDS/MIN IS.** Counted where the data is
meant to END UP — matching `(tribunal_id, rol)` against Neon, because a `rol` alone repeats across
the 230 courts and matching on it gave more hits than there were causas:

    589 opened
     33 gated (etapa/proc rejected -- deliberately never stored)
    556 kept
    254 already in Neon
    312 NEW records LANDED        ->  12.4 new records/min, 53% of opens useful

The accounting closes exactly: 589 on disk against 566 now in Neon leaves 23 unstored, which is
the 33 gated minus the 10 of them the bank already held. ⚠️ The first estimate of 335/13.3 counted
gated causas as deliverable; the gates reject them precisely because there is no harvest to store,
so they are opens spent, not records won. **Verified after ingest by counting rows in Neon, not by
reading the run's own tally** -- which is the failure `ingest_worker_h.py` exists to prevent.

★ Still the best figure this project has recorded (previous best 9.9 OPENS/min, 4 workers at
operator pace, 2026-08-17 — and that number was never discounted for duplicates either, so the
honest comparison is closer than 2.4x and probably nearer 1.4x on new records). ⚠️ Over 25 minutes,
not an hour — do not quote it as a sustained figure until an hour has been run.

⚠️ **57% useful, against the ~27% this file predicts for a sweep.** July was under-swept, so the
discount is milder than usual. It is a property of THIS WINDOW, not of sweeping, and it will fall
as the window fills. The 08-17 fatal arm died at minute 5, so surviving 25
is real evidence, but the safe arm ran 60.

⚠️⚠️ **AND IT DID NOT TRIP BECAUSE THE RATE WAS SAFE, NOT BECAUSE TOP SPEED IS SAFE.** 26.2 req/min
sits just above the 23/min that held for an hour in August. The finding is not "we can go flat out
now"; it is that **on this build `--speed 0` cannot produce a dangerous rate with four workers**,
because the engine's motor work — pointer travel, mouse-driven selects, the datepicker — sets a
floor no speed setting removes. The old lesson "top speed kills" was true of a build whose top
speed reached 56 req/min. Same flag, different machine underneath.

⇒ The pace axis and the rate axis have come apart. `--speed` is no longer a rate control worth the
name: it moved 4 workers from ~23 to ~26 req/min, a 13% span, where in August it spanned 23 to 56.
**Fleet size is now the rate control.** Design experiments on worker count, not on --speed.

★ Worth sitting with: the configuration that matches the operator LEAST on pace delivered the most
records and tripped on nothing. That is exactly the case the benchmark section above exists to
adjudicate, and on this evidence the pace specs are not earning their cost. One 25-minute run does
not settle it — the duty arms are next — but the direction is already uncomfortable for the
"more human is safer" instinct, which this project has now been wrong about twice in one day.

## What the instrument says about the current build (NOT a defect list)

`human_profile.py --file <operator> --vs <worker>`, per ACTIVE second. Ratios are **where we
differ**, each one a hypothesis to price live — not a gap to close on principle:

    mouseover  x1.01   mouseout x1.01      <- indistinguishable
    mousemove  x0.70   (25.1 -> 17.6/s)
    click      x0.40   wheel x0.34  scroll x0.39  focusin x0.46
    resize     x0.00   visibilitychange x0.00     <- we never tab away or resize
    hold       med 99 -> 109 ms            turn sd 23.6 -> 48.7 deg

⚠️ Much of the click/wheel/scroll gap is TASK MIX, not behaviour: the operator was browsing anexos
and documents, the worker runs a narrower loop. Comparing two different jobs and calling the
difference a tell is the same population error this file records three times over.
⚠️ `mousemove` fell from x0.84 to x0.70 when the duty cycle was switched on, which should not
happen if stops are cleanly excluded from active seconds — most likely one-second buckets that
straddle a stop boundary count as active while holding fewer events. Unproven.

## The next test — pricing the duty cycle

Not "match the operator". **Does `--duty human` reduce blocks, and by enough to pay for the
throughput it costs?**

Both arms ramp identically until trouble, and the x-axis is MEASURED aggregate req/min, not the
speed setting (duty changes the speed->rate mapping, so the setting is not comparable and the rate
is):

    arm  duty-off     4 workers, --duty off,   ramping
    arm  duty-human   4 workers, --duty human, ramping

Read two numbers per arm: **the measured req/min at which trouble starts**, and **causas delivered
before it**. The second one is the benchmark; the first says whether stillness buys headroom.

  same trip rate  -> the duty cycle is pure cost. Remove it and take the throughput back.
  duty trips later -> it buys survival, and now we know the exchange rate.

## ⚠️ LATENT: the Drive object is keyed on POSITION, the row is keyed on FOLIO (2026-08-19)

Asked whether re-running the ingest would duplicate 4,281 PDFs. **It would not** — `upload_c2_docs`
consults the Drive cache before reading a single byte and skips any object already there, exactly
as its own docstring promises. The guard is real and it works.

But checking it surfaced a disagreement between two id schemes for the same document:

    Drive object     {causa_id}/c2-{k:02d}.pdf      <- k is the POSITION in historia_c2
    Documentos row   {causa}-c{n}-{folio}-{k}-doc   <- keyed on the FOLIO

**Folios arrive newest-first** (`['3','2','1']` in every sample). So a causa that gains one filing
between scrapes shifts every position by one: `c2-00.pdf` was folio 3 and is now folio 4. On the
next ingest the cache returns a HIT for `c2-00.pdf` and stamps the OLD document's URL onto the NEW
folio's row — silently, without reading or uploading anything, and the "already in Drive" counter
makes it look like a saving.

⚠️ **Measured exposure today: ZERO.** 1,250 causas carry documents and **not one of them has been
scraped twice**, so no position currently maps to two folios. That is timing, not design — the doc
pass ran once per causa. The first re-scrape of a document-carrying causa is when this bites.

⇒ **Key the Drive object on the folio, not the index** (`c2-f{folio}.pdf`), which makes the two
schemes agree by construction. Anything already uploaded keeps working; the names simply stop
colliding across scrapes.
⇒ The general shape: **when the same object has two identifiers, one stable and one positional,
they agree exactly until the list changes — and then they disagree silently.** A cache keyed on
the positional one turns a re-scrape into corrupted links rather than a re-upload.

## ⚠️ 2,279 worker H records carry NO tribunal_id

Found while counting how much of the corpus is banked. A `rol` is unique only WITHIN a tribunal, so
those records cannot be matched against Neon at all — and my first attempt to count them keyed on
`rol` alone and returned MORE hits than there were causas on disk (861 against 495, a negative
"new" count, which is what exposed it).

⚠️ It also means the "774 unbanked" figure covering the whole corpus is **not trustworthy**: those
2,279 records collapse into `(None, rol)` keys. **Arm 1's 335 is sound** — every one of its 589
records carries a tribunal_id. Do not quote a corpus-wide delivery number until the older records
are either re-keyed or excluded.

---

# ★★★★ GOAL 1 — THE BEST SPECS FOR ONE WORKER (2026-08-20)

A 2x2 of `--focus` x `--duty`, four single workers in parallel, `--speed 1.0`, 25 min, one address.
Parallel so all four meet identical site load and time of day — this project has more than once
attributed to a spec what was really the hour.

| shard | focus | duty | opens/min | duty draws |
|---|---|---|---:|---|
| s1 | off | off | 2.66 | — |
| s2 | **fast** | off | **2.86** | — |
| s3 | off | **human** | **1.23** | n=68 mean 11.0s median 6.2s max 58.0s, 49% silent |
| s4 | **fast** | **human** | **2.86** | n=121 mean 2.0s median 2.0s max 2.1s, 16% silent |

## ⚠️⚠️ s4 IS NOT "THE DUTY CYCLE FOR FREE". `--focus fast` SHRINKS THE DUTY CYCLE.

The obvious reading of the table — *fast cancels duty's cost* — is wrong, and the draws say so.
`silence_secs()` samples through the FOCUS band, so under `fast` every stop is drawn from the
operator's p0-p25 floor: **all 121 of them landed at 2.0-2.1 s.** s4 is silent 16% of the time
against s3's 49%. They are not one spec at two speeds; s4 is a different worker.

⇒ **A knob that was only ever meant to shorten READING also shortens STOPPING.** Two behaviours on
one control, discovered only because the draws are logged. Had `DUTY DRAWS` not existed, s4 would
have been written up as "the duty cycle is free at focus fast" and shipped.

## ⚠️ AND THE INTERACTION IS A BUG, NOT JUST A SURPRISE

`ACTIVE_GAP_MEAN` is derived from `SILENCE_MEAN = 10.9` — the FULL distribution's mean — so it does
not move when FOCUS shortens the stops. The result preserves neither quantity it should:

    stops/min   3.23 (operator)  ->  2.7 at focus off  ->  4.8 at focus fast     frequency UP
    silent %      59 (operator)  ->   49 at focus off  ->   16 at focus fast     fraction DOWN

`human_engine.silence_secs` says in as many words: *"FOCUS shortens the stops; it must never reduce
how many there are."* It does not reduce them — it inflates them, because a shorter stop re-arms
the same fixed gap sooner. Whichever invariant is intended (frequency or duty fraction),
`ACTIVE_GAP_MEAN` has to be derived from the mean stop ACTUALLY IN USE, not from the constant.

★ s3 is the vindication of the scheduler rebuilt earlier tonight: **mean 11.0 s, median 6.2 s, max
58.0 s against the operator's 10.9 / 6.1 / 60.4**, over 68 stops. The earlier 25-stop runs could
not have shown that.

## The answer for one worker, and it is not the human-like one

    --speed 0  --duty off        ~5.8 opens/min   (arm 1, four shards: 6.5 / 5.8 / 4.6 / 6.7)
    --speed 1.0 --focus fast      2.86 opens/min
    --speed 1.0 --focus off       2.66 opens/min
    --speed 1.0 --focus off --duty human   1.23 opens/min

**`--speed 0` is worth about 2x the best focus setting**, because it removes reading entirely while
`fast` only samples the quick quarter of it. Nothing tripped at any setting — but ONE worker at 25
minutes cannot show tripping, and worker A has been blocked on multi-hour single-worker runs
before. ⚠️ **Read this as a throughput ranking with the survival column still empty.**

⇒ Provisional best single-worker specs: **`--speed 0 --duty off`** (focus is moot at speed 0, which
zeroes the reading `--focus` selects from). To be confirmed by a multi-hour run, which is the only
thing that can fill in the survival column.

## ⚠️ THE ENTRY GATE IS A THROUGHPUT TAX THAT GROWS WITH FLEET SIZE (2026-08-20)

Arrivals serialise on the entry gate — deliberately, because six sessions opening in the same
second is the "would not" violation that cost five of six workers their entry. But the cost scales
with N and nobody had ever priced it:

    4 workers   all productive within a few minutes of launch
    8 workers   at minute 5, only 6 shards had opened anything and the fleet was at 8.5 req/min

At `--gate-release form` a worker holds the gate for its walk-in plus its form build. Eight of those
in series is a large slice of a 25-minute run — and every worker still counts those minutes against
its own `--max-minutes`, so the tax is paid twice: once in wall clock, once in lifespan.

⇒ **A fixed-length arm penalises the larger fleet for a reason that has nothing to do with the
WAF.** Comparing 4 vs 8 workers over 25 minutes measures arrival overhead as much as it measures
capacity, and it does so in the direction that makes more workers look worse.

⇒ **Measure the RATE in steady state** (a window near the end, after every shard is working), and
**measure THROUGHPUT over runs long enough to amortise arrival** — an hour at least for eight
workers. The two questions want two different windows, and using one window for both is how a
fleet-size study reaches a confident wrong answer.

⇒ For production the same arithmetic says: **long shifts, not short ones.** The arrival cost is
paid once per run regardless of length, so it is 40% of a 25-minute run and 3% of a six-hour one.

---

# ★★★★★ GOAL 2 — 8 WORKERS, 52.9 req/min, ZERO TROUBLE (2026-08-20)

The rate that killed four workers in five minutes on 2026-08-17 was ~56 POST/min. Today eight
workers held **52.9 req/min for 25 minutes with nothing at all**: no refusals, no modal failures,
no recoveries, `refused=0` on every shard.

    steady state, last 8 min, all eight shards working
    h1 6.38  h2 6.50  h3 6.62  h4 6.88  h5 6.50  h6 6.75  h7 6.88  h8 6.38   ALL 52.88  trouble 0

## ★ Workers scale LINEARLY in steady state — the sublinearity was the entry gate

    4 workers   26.2 req/min   6.55 each
    8 workers   52.9 req/min   6.61 each      2.02x aggregate for 2.0x the workers

⚠️ **Doubling the fleet did not slow the individual worker at all**, which contradicts
`rate_watch.py`'s own header ("it goes DOWN as workers are added... contention stretches the
cycle"). At minute 12 this arm looked like +32% over four workers, and that WAS the arrival tax,
not contention: measured over the whole run the larger fleet is penalised for time it spent
queuing at the entry gate, and measured in steady state it is not penalised at all.

## ⚠️⚠️ THE 08-17 EXPERIMENT CONFOUNDED RATE WITH BEHAVIOUR, AND WE READ ONLY THE RATE

That test moved `--speed`, and `--speed` moved two things at once:

    --speed 0   ~56 POST/min   AND   pointer 6-9 mousemove/s
    --speed 1.0 ~23 POST/min   AND   pointer 15-20 mousemove/s

It was written up as "the binding limit is the aggregate request rate per address", and the
handbook's own entry even notes the pointer collapse in the same breath — *"top speed buys
throughput by spending the exact channel we believe keeps you unblocked"* — without drawing the
obvious conclusion that the arms differed in TWO variables.

Today `--speed 0` no longer wrecks the behaviour: the motor work added since August (pointer
travel, mouse-driven selects, the datepicker) is irreducible, so top speed keeps its pointer and
gets the rate. **We now hold the rate that supposedly kills, with behaviour that does not.**

⇒ ~~"The binding limit is the AGGREGATE REQUEST RATE PER ADDRESS."~~ **OVERTURNED as stated.** The
rate was never varied independently of the behaviour, so what that experiment showed is that
*fast-and-degraded* dies while *slow-and-faithful* lives. 53 req/min of faithful behaviour is fine.
⚠️ It does NOT follow that rate is irrelevant — only that it is not the binding limit at 53/min,
and that any future rate claim must hold behaviour constant to mean anything.

⚠️ **25 minutes, not an hour.** The 08-17 arm died at minute 5, so 25 is 5x the time-to-death and
that is real evidence — but the surviving arm there ran 60 minutes, and this has not. Do not
promote 53 req/min to "sustained" until an hour has been run.

## ⚠️⚠️ CAPACITY DOUBLED. DELIVERY DID NOT. THE WINDOW IS NEARLY EMPTY.

    4 workers    589 opens ->  335 NEW   57% useful   13.3 new records/min
    8 workers   1008 opens ->  330 NEW   33% useful   13.1 new records/min

**Twice the fleet, twice the opens, the same number of records.** Both arms swept the SAME July
window over the SAME 230 courts, an hour apart, so the second spent half its opens re-finding what
the first had just banked. Useful% fell 57 -> 33 and the delivered rate did not move at all.

⚠️ **This is the depletion confound, and it is not a flaw in the experiment — it is the answer.**
Capacity scales beautifully (26 -> 53 req/min, 23.5 -> 40.1 opens/min, linear per worker). Delivery
is bounded by **how much unharvested territory exists**, and July is nearly harvested.

⇒ **At this point adding workers to this window buys nothing.** The bottleneck has moved from rate
to SCOPE. The next throughput gain comes from pointing the fleet at unswept months or courts, or
from `--fill` (which asks the bank what is missing instead of re-discovering it, ~95% useful
against this sweep's 33%) — not from another rung of the ladder.
⇒ ★ **The benchmark protected us here.** On opens/min the 8-worker arm looks like a triumph, 1.7x
the four. On the metric that is actually the goal it delivered five records FEWER. Any study that
had scored itself on opens would have concluded "add workers" and been exactly wrong.

⇒ Next rung: **12 workers, ~79 req/min**, which needs about 6.4 GB free. If that is clean too, the
limit is somewhere we have never looked, and the question stops being "how fast dare we go" and
becomes "how many browsers does this machine hold".

---

# ★★★★★ IT IS THE **SEARCH** RATE, NOT THE REQUEST RATE (2026-08-20)

Two arms, one hour apart. **Same eight workers, same `--speed 0 --duty off`, same machine, same
address, same code.** The only thing changed was the date window:

| window | total req/min | **result req/min** | opens/min | outcome |
|---|---:|---:|---:|---|
| July 01-31 | **52.9** | **3.0** | 40.1 | clean 25 min, zero trouble |
| Aug 01-19 | 21.3 | **11.6** | 9.7 | **6 of 8 dead in ~10 min** |

**The arm that died was running at 40% of the total request rate of the arm that lived.** What it
was running at 3.9x was SEARCHES.

    01:04:21  BLOCKED ON SEARCH after  7 opens / 21 searches
    01:04:23  BLOCKED ON SEARCH after  7 opens / 11 searches
    01:04:23  BLOCKED ON SEARCH after 19 opens / 17 searches
    01:04:25  BLOCKED ON SEARCH after 11 opens / 10 searches
    01:04:29  BLOCKED ON SEARCH after  6 opens / 14 searches
    01:04:34  BLOCKED ON SEARCH after 21 opens / 13 searches

Six sessions, **thirteen seconds**, progress ranging 6 to 21 opens. That is the address-level
signature this file already names: *unequal progress, simultaneous death, look for what they
share.* All six: `Buscar stuck disabled while idle (spent session)`.

## Why a FRESH window is more dangerous than a picked-over one

Sparsity inverts the request mix. In July every search returned a page full of causas and the
worker spent minutes opening them — one search bought a long, quiet, open-heavy stretch. In August
most courts hold nothing for the window, so a search returns little or nothing and the worker
**immediately searches the next court**. Same worker, same pacing constants, four times the search
rate, from the data rather than from any setting.

⚠️⚠️ **THE DANGER OF A WINDOW IS NOT VISIBLE IN THE CONFIGURATION.** Two runs with identical flags
sit on opposite sides of the wall depending only on how much the window happens to contain. Nothing
in `--speed`, `--duty`, worker count or the launcher says which one you have.

⇒ ~~"The binding limit is the aggregate REQUEST rate per address" (08-17)~~ and
~~"53 req/min is fine" (08-20, six hours ago)~~ — **both refined by this.** The quantity that binds
is the **result-request rate** (searches and page advances, `consultaFechaCivil.php`), which is
exactly what `SEARCH_GAP` and the "result request budget" in this file were always about. The
project drifted into counting TOTAL requests and then measured a window where the two diverged.

⇒ **`rate_watch.py` prints `result requests alone:` on its own line and flagged this correctly**
— "[!] above anything this IP has been measured sustaining, on any config" — while the total-request
line still read as healthy. The tool was right and its headline number was the wrong one to watch.
**Watch the result-request line.** Known-clean is ~3/min for a fleet; 11.6/min killed six sessions
in ten minutes.

## ⚠️ Three explanations, one measured, two still open

1. **The search rate binds.** Fits every number here and the whole SEARCH_GAP history.
2. **The August window is special** — it is the CURRENT month, and the site may treat a
   still-accumulating window differently.
3. **The empty results were already refusals.** This file records `sin resultados` = blocked, not
   empty. If sparse-looking searches were in fact soft refusals, the fleet may have been in trouble
   from the first minutes and the "spent session" was the end of it, not the start.

⇒ **The discriminating test is cheap: run the SAME August window with TWO workers**, which puts the
search rate near 2.9/min — July's value. Clean means it is the rate (1). Dead means it is the
window (2 or 3). Do not run it until the address has recovered, and prove recovery with a single
canary worker first.

⚠️ **Cost of learning it: 71 causas.** Six sessions spent, ~10 minutes each. Cheap for a wall that
has been mis-stated in this file twice.

## ⚠️⚠️ THE AUGUST BLOCK PERSISTS PAST 25 MIN, AND IT ESCALATES TO *ENTRY* (2026-08-20)

A single-worker canary on the KNOWN-GOOD July window, 25 minutes after the six sessions died:

    [02:22:43] could not reach the OJV by click-through (attempt 1/3) [state=ojv-other]
    [02:24:02] could not reach the OJV by click-through (attempt 2/3) [state=ojv-other]
    [02:25:21] could not reach the OJV by click-through (attempt 3/3) [state=ojv-other]
    [02:25:39] could not reach the OJV by clicking through, and we do NOT type the URL — stopping

**Not one causa. Not one search. It could not get in at all.** The block began as `Buscar stuck
disabled` on individual sessions and is now refusing the walk-in from `www.pjud.cl` to a brand-new
browser with a fresh profile.

⚠️ **The canary was on JULY on purpose** — the window that ran clean an hour earlier — so this
cannot be read as "August is bad". It is the address.

⚠️ **THE REAL COST OF THE AUGUST ARM WAS NEVER 71 CAUSAS.** It was the address, for 25+ minutes and
counting, during which NOTHING can be collected — no sweep, no fill, no doc pass. Price a failed
rate experiment in dead-address minutes, not in the records the arm itself lost. At the July arm's
delivered rate that is already ~330 records of opportunity gone, five times what the arm collected.

⇒ **A canary must be cheap AND on known-good ground.** This one cost 4 minutes and settled that the
discriminating test cannot run yet — which is exactly what it was for.
⇒ ★ The worker refused to type the URL and stopped instead. That guard is the one rule holding
under pressure: the shortcut was available, it would have "worked", and it is precisely what no
person does.

⇒ Next: a LONGER cool-off, then canary again **with `--trace entry`**, so the refusal page itself is
captured. This file's own instruction is ASK THE PAGE WHY BEFORE RECOVERING, and three block
investigations here have gone nowhere for want of the frame the worker was looking at.

---

# ⚠️⚠️⚠️ CORRECTION: "IT IS THE SEARCH RATE" IS PROBABLY WRONG — THE SITE CHANGED (2026-08-20)

Written about ninety minutes after the entry above, which should be read with this one.

Attaching to the canary's browser mid-attempt showed the OJV tab **open and healthy**:

    page 1: https://oficinajudicialvirtual.pjud.cl/indexN.php
            title "Oficina Judicial Virtual", menu rendered, heading "Invitado"

    #fecCompetencia                    0        <- the form marker _reach_ojv waits for
    [onclick*='accesoConsultaCausas']  0
    [onclick*='accesoInvitado']        0
    form                               0
    select                             0
    onclick attrs PRESENT: consultaUnificada(); consultaEscritosIndepen();
                           consultaAudienciasLaboral(); consultaCiudadana();

**We were never refused entry. We arrived, and did not recognise where we were.** `state=ojv-other`
means "not the OJV page we expect", and it was reported while sitting on the OJV.

`indexN.php` no longer carries the search form. It now serves a MENU whose entry point is
`consultaUnificada()`. The engine's own comment records measuring the opposite on 2026-08-14 —
*"it lands STRAIGHT ON THE FORM (indexN.php, #fecCompetencia present)"* — and `entry_probe.py`
exists because **the site had already changed its entry route once that week.**

## ⚠️ Why this undermines the search-rate finding

A rate limit does not restructure a landing page's DOM. Whatever removed `#fecCompetencia` from
`indexN.php` was a **deployment**, not a throttle. And a deployment at ~01:04 explains the thing
the rate story never explained well:

    01:04:21 .. 01:04:34   six sessions dead in THIRTEEN SECONDS, holding 6 to 21 opens each

Simultaneity across sessions at wildly different progress is exactly what a deploy does — the page
changes under everyone at once. A rate limit reached by six sessions independently, within thirteen
seconds, while a fleet at **2.5x the total request rate** had run clean an hour earlier, was always
the awkward part of that story. `Buscar stuck disabled while idle` is also what a changed page and
stale automation look like.

⇒ ~~"It is the SEARCH rate, not the request rate, that binds."~~ **SUSPENDED, not confirmed.** The
July/August arms were separated by TIME as well as by window, and a site deployment in that gap is
now the leading explanation for both the deaths and the broken entry. The measurements stand; the
causal claim does not.
⚠️ It is not disproved either. Sparsity really does invert the request mix, and that remains worth
testing — but it must be tested against a site we can still drive, and on two arms that are not
separated by ninety minutes.

## ★ The lesson that outlives whichever explanation wins

**I diagnosed a block for two hours without once looking at the page.** The canary said
`state=ojv-other`; I read it as "the address is refusing" and wrote up a persistent escalating
block, a cost in dead-address minutes, and a cool-off schedule. One CDP attach to the running
browser — thirty seconds — showed a healthy OJV with a changed DOM.

⇒ This file's own rule is **ASK THE PAGE WHY, BEFORE RECOVERING**, and it was written after the
same mistake. A state name is a HYPOTHESIS the code formed, not an observation. `ojv-other` is
literally "none of my selectors matched"; treating it as evidence about the SITE rather than about
OUR SELECTORS is how a stale integration reads as hostility.
⇒ **When a scraper reports a block, attach to its browser before you believe it.** The tab is
sitting right there.

## What to do next, in order

1. **Confirm by hand.** Open `www.pjud.cl` in a normal browser on this network and click through to
   the OJV. If a person reaches a working search form, this is entirely ours to fix. That is the
   decisive test and it takes a minute — no automation can substitute for it.
2. **Re-point `_reach_ojv` and `find_form`** at the new structure: accept the menu as a valid
   arrival and drive `consultaUnificada()` to the form. ⚠️ A click on that control did NOT produce a
   form within 20 s in this probe, so the route beyond it is NOT yet known — find it by watching,
   not by guessing selectors.
3. **Only then** re-run the sparse-window test, with both arms back to back.

## What the entry probes actually established (2026-08-20, 03:40)

**www.pjud.cl offers BOTH doors again:**

    https://oficinajudicialvirtual.pjud.cl/home/                          "Plataforma para el ingreso de causas y escritos"
    https://oficinajudicialvirtual.pjud.cl/includes/sesion-consultaunificada.php   "Seccion que permite la revision de causas"

⚠️ The 2026-08-14 note in `ojv.py` says www.pjud.cl offered **exactly one** OJV anchor, the
sesion-consultaunificada one, and half the entry folklore in that file was written off as belonging
to a `/home/` path "a human may no longer take at all". **`/home/` is back.** The entry menu is not
stable across weeks, and `entry_probe.py` exists because it changed once already that week.

**Established:**
- The OJV IS reachable — indexN.php was observed open and healthy at 03:24, menu rendered.
- indexN.php no longer carries `#fecCompetencia`, any gate button, any `<form>` or any `<select>`.
- Its entry points are now `consultaUnificada()`, `consultaEscritosIndepen()`,
  `consultaAudienciasLaboral()`, `consultaCiudadana()`.
- `_reach_ojv` fails purely because none of its four markers match that page.

**NOT established, and I stopped rather than guess:**
- Whether the search form is reachable at all, by either door. Clicking `consultaUnificada()`
  produced no form within 20 s; a later click on the sesion-consultaunificada anchor produced no
  OJV tab within 35 s.
- ⚠️ That last probe used a raw `page.click()`, NOT `C.human_click`, so it had **no covered-element
  check** — this repo's single most expensive bug class. A refused click and a dead link look
  identical from outside. Do not conclude the link is dead from that probe.
- Whether 01:04 was a deployment or a rate block.

⇒ **The decisive test is a person opening www.pjud.cl on this network and clicking through.** If a
human reaches a working search form, this is ours to fix and the shape of the fix is known: teach
`_reach_ojv` to accept the menu as a valid arrival and follow the site's own route to the form.
If a human ALSO cannot get there, the address is degraded and no selector work will help.
⇒ Until that is answered, **do not run fleets.** Every arm would report `ojv-other` and teach
nothing, exactly as two canaries already have.

## ⚠️ CORRECTION: `--speed 0` IS THE FASTEST SETTING, NOT THE FASTEST RESULT (2026-08-20)

I wrote that `--speed 0 --duty off` at ~5.8 opens/min was the best single-worker figure we have.
It is not. Measuring PRODUCTIVE rate (first open to last open, excluding entry) against the floor
this file already recorded:

    arm1 s4   8.6 s per open   7.0 opens/min      <- tonight, best shard
    arm1 s1   8.9 s            6.7
    arm1 s2   9.0 s            6.7
    prior     8-9 s            ~7.0               <- already measured, reading merely ramped to 1/10

**Tonight lands exactly on the floor that was already found, and does not beat it.** The 5.8 figure
was low for two reasons that had nothing to do with pace: the `DONE` line divides by LIFESPAN,
which includes 1.1-5.7 min of entry per shard, and shard s3 drew sparse courts (11.8 s per open,
27 searches against 14).

⇒ **We are at the SITE's floor and have been for weeks.** This file already says so — *"that residue
is PJUD's own response time plus the acts"* — and that cutting reading from 3 s to 2.2 s bought
0.3 s. Going from a tenth to zero bought nothing measurable. **No speed knob touches what is left**,
because what is left is the site answering plus the motor work we refuse to cut.
⇒ ★ **There is nothing further to find on the speed axis for a solo worker.** Max is ~7 opens/min,
measured twice, months apart, on different builds. The open question was never "how fast" — it is
"what does running at the floor cost us in blocks", and that is a SURVIVAL question.

## ⚠️⚠️ AND THE 8-WORKER SLOWDOWN MAY BE THIS HOUSE'S INTERNET, NOT THE SITE

Per-open time drifts up with fleet size:

    4 workers   8.6 - 11.8 s per open
    8 workers   9.7 - 12.2 s per open

⚠️ **UPDATE 2026-08-20: a SOLO worker on the same line lands at 9.75 s per open** — in the middle
of both ranges, not below them. Contention up to eight workers is therefore small enough to be
invisible, and per-open time is dominated by the SITE rather than by the fleet or the line. The
caveat below still holds for a REMOTE fleet, where the uplink genuinely differs; it no longer
explains these numbers.

I called that contention. ⚠️ **On a local machine the operator's own uplink is a shared variable**,
and eight browsers pulling causa pages through one residential connection can throttle each other
with the site entirely innocent. Nothing in these runs separates "the site is slower under our
load" from "our own line is saturated".

⇒ **This is the measure-don't-inherit trap in its exact original form.** A constant measured locally
is not a constant measured remotely: a runner has datacenter bandwidth and would show NO such
slowdown if the cause is the uplink — and the same slowdown if the cause is the site.
⇒ **Do not carry the per-open contention figure into any remote fleet plan.** It is a LOCAL
measurement of unknown cause. The cheap discriminator is to watch bandwidth during a fleet run, or
to run the same ladder on a runner and compare the shape.
