# Generic Scraper

**A library.** Everything this repo has learned about making scrapers work, gathered in one
target-independent place so it can be *used* on the next project instead of excavated from it.

**What it is not.** It does not replace anything. `../SCRAPERS_HANDBOOK.md` and the PJUD handoffs
stay exactly where they are and stay authoritative for their own material — they are the record of
how each thing was found, with the near-misses and the wrong turns intact, and that provenance is
worth as much as the conclusions. This file is the **reusable** cut: organised by *the question you
are asking*, not by *which scraper taught us*, and written so an entry can be acted on without
opening its source.

**The shape.**

| | |
|---|---|
| **Book I** | the invariants — true of every target so far |
| **Book II** | a **blank per-target profile**, plus the ones we have filled in |
| **Books III–V** | build · operate · measure — the working library, by lifecycle stage |
| **Book VI** | the registers — dated measurements, overturned claims, negative results, open questions, traps |

Every claim carries a target and a date. Where two scrapers disagree, both are kept, because
*which problem you have* decides which answer is right — and that distinction is the single most
valuable thing here.

---

## How to use it

| you are | start at |
|---|---|
| building a scraper for a new target | **Book I**, then copy the blank **Book II** form, then **Appendix B** |
| stuck, blocked, or being refused | **I.0** → **IV.1** → **IV.4** → **VI.5** |
| adding workers, or changing pace | **IV.2–IV.3**, and **Book V** before you believe the result |
| about to run an experiment | **Book V** in full. Most often skipped, most often costs the day |
| filing something you just learned | **the ingest contract**, below |
| chasing a number | **VI.1** — every figure in this file is dated there |

---

## ⚠️ The ingest contract

Documentation about anti-bot behaviour rots faster than code, and a stale scraping doc is worse
than none: it sends you to rebuild a theory that was already disproved. So the rules are mechanical.

1. **Date every claim**, with its target. `(PJUD, 2026-08-21)` is the minimum. An undated claim is
   unciteable and will be read as folklore by the next person, including you.
2. **Say whether it is MEASURED or SUSPECTED**, and give `n=`. A large share of what follows rests
   on one trial and says so.
3. **Never delete an overturned claim.** Strike it, name what replaced it, and log it in **VI.2**.
   The *shape* of a mistake repeats long after its specifics stop applying.
4. **Negative results are entries.** "We tried X and it did nothing" is the most expensive kind of
   knowledge and the first to be lost. **VI.3**.
5. **Same commit as the fix.** If a lesson earns a ⚠️ comment in the code, it earns a line here.
6. **Generic here, specific in Book II.** If the sentence needs the target's name to be true, it is
   a Book II fact. If it survives the name being removed, it belongs in Books I / III / IV / V.
7. **One copy.** Edit the existing entry; never add a second. Duplicate detectors go blind
   together, and so do duplicated claims — see IV.1.

### Where a new fact goes

| the fact is… | slot |
|---|---|
| true of scrapers in general | Book I, III, IV or V, by lifecycle stage |
| true of one target | Book II, that target's form |
| a number with a date | VI.1, cited from wherever it is used |
| a claim that just died | VI.2, plus edit the live entry |
| something tried that did nothing | VI.3 |
| something we do not know | VI.4 |
| a way to lose an afternoon | VI.5 |
| a tool, and the question it answers | VI.6 |
| what a given day produced | VI.7 |

### Markers

`★` matters · `★★` cost or saved real time · `★★★`+ load-bearing, changes how you build ·
`⚠️` a trap · `⚠️⚠️` a trap that has bitten more than once · ~~struck~~ overturned, see VI.2.

---
---

# BOOK I — THE INVARIANTS

## I.0 The one rule

> ## A scraper must not do anything a human **could not** do, or **would not** do.

Everything else is a corollary. In nearly every incident this repo has recorded, the scraper was
doing something no person ever does, and the site noticed.

### "Could not" — physically impossible for a person

| what the scraper did | why no human does it | what it cost |
|---|---|---|
| teleported the pointer onto a button (`page.click()`) | a hand moves through space, hovers, presses | **weeks** — the biggest bug in this repo |
| typed at exactly 70 ms per key, for dozens of keys | nobody has metronome fingers | a tier-3 CAPTCHA on the *first* search |
| parsed a 100-row table with zero wheel events | you cannot read a long page without scrolling | contributed to the same |
| clicked a target covered by an overlay | you cannot click what you cannot see | wrong actions, correlated with blocks |
| `el.value = x` plus a synthetic `change` | real keystrokes make the *browser* fire it | burned a profile |
| ran headless | a person is looking at a screen | 17 failed jobs/day for ~13 days |
| worked in a background tab | a person looks at the tab they are using | three "blocks" that were nothing of the kind |
| typed into a `readonly` field | the site's own UI cannot reach that state | in every run this project ever made, for months |
| fetched documents outside the browser with copied cookies | a person's requests come *from* their browser | avoided by design |

### "Would not" — possible, but nobody behaves like that

| what the scraper did | why no human does it | what it cost |
|---|---|---|
| opened six brand-new sessions in the same second | one person opens one browser | five of six never got in |
| fired a steady ~9 req/min for hours | people pause, read, get distracted | three workers blocked within 14 s |
| paced two workers to the same instant each minute | two people never sync to the second | plausibly killed a 3-worker run |
| flipped to a record's second volume 4 s after opening it | nobody reads that fast | a wall at exactly 10 records, remote only |
| re-requested a document already answered "there is none" | you ask once and accept the answer | spends the scarcest budget on a settled question |
| hammered a court that had just refused it | a person waits, or gives up | escalating blocks |
| tried to solve a full-page image CAPTCHA | it is an *explicit* request for a human | never attempted — hard stop |

### ★★ The corollary that saves you time

**When you get blocked, the first question is not "how do I evade this?" but "what am I doing that
a person wouldn't?"** Every time that question was asked properly here, it produced a fix that made
the scraper **faster**:

- fixing the pointer turned a **250 B rejection into 109 KB of results**;
- fixing the keyboard and adding scrolling let the gaps drop 60 s → 20 s and 90 s → 25 s — **3×
  throughput** — because the slow pacing had only ever been paying for a metronome keyboard and a
  session that never scrolled.

⇒ Gentle pacing is what you reach for when you cannot find the real problem. It hides the symptom,
costs throughput permanently, and leaves the actual tell in place. **Before slowing down, check
whether you look wrong.**

### ⚠️⚠️ Fallbacks are where the rule quietly dies

A fallback is written on a bad day to rescue a run, so it fires **only when things are already going
wrong** — exactly when looking wrong costs the most.

Worked example (PJUD, 2026-08-13): entry was "load the public home page, click through to the
service". A fallback typed the service's deep URL directly when that click failed, justified as
"typing a public URL is ordinary browsing; a preference for the prettier path is not worth losing
the run over". Both halves were wrong. **Nobody types the deep URL of an internal console** — they
land on the home page and click; and it only ever ran on already-struggling sessions, so the least
human action of the whole run happened at its most fragile moment. The one worker observed using it
tried twice and never got in, while three siblings on identical machines clicked through first time.

⇒ **Audit your fallbacks against the rule, separately from the happy path.** Ask what triggers each
one and whether a person in that situation would do that. "Click through, or do not get in" beats a
fallback that rescues the run by acting like a bot.

### The honest nuance — ask what the SERVER sees

This is a rule about **observable behaviour**, not a vow of literal-mindedness.

- Reading the DOM over CDP was explicitly tested (PJUD, 2026-07-22) and is **innocent**.
  `Runtime.evaluate` does not affect scoring. Only *input* matters — do not sacrifice DOM reading
  in the name of stealth.
- Having the page itself `fetch()` a document instead of clicking it produces **the same single
  request the click would have made**, from the same session, and skips a viewer the user would
  never have looked at. That is more human, not less.

⇒ Ask what the **server** sees and whether a person could have produced it. Not whether your code
looks like a puppet show.

## I.1 ★ Know which problem you have

The rule is not "always simulate a human". It is **identify what the site measures.**

| the site has | the right move |
|---|---|
| behavioural anti-bot (F5 Shape, PerimeterX, …) | simulate the human precisely — arc, dwell, rhythm, silence |
| no behavioural scoring but fragile UI (ads, overlays, JS handlers) | drive the handler directly and stop worrying about how it looks |
| an authenticated form that must be driven exactly right | real keystrokes and the correct blur, then **read the value back** |

The counter-example is real and cost time to accept: on **patentechile**, a coordinate click
frequently lands on an ad iframe and returns **without error**, so the search silently never fires
and the plate looks like "no data". There the correct move is `el.click()` in JS — the human's
*intent* reaches the server, the pantomime does not.

## I.2 ⚠️⚠️ The rule is a CONSTRAINT. The goal is records per hour.

> **The benchmark is sustained records collected per hour, without ever tripping — measured against
> the SITE.**

The rule bounds the search space. It does not tell you which point inside it to pick, and it is not
a scoring function. Two configurations can both be perfectly plausible as human behaviour and
differ by 2× in throughput; the rule is silent between them and the site is not.

**A human recording is an INSTRUMENT, not a TARGET.** Recording a real operator is how you discover
*which variables exist* and *what values are plausible* — that a duty cycle exists at all, that
wheel deltas arrive quantised, that click holds cluster near 100 ms, that a person types nothing
into a readonly field. None of it was visible until someone was recorded and none could have been
guessed. But **"how closely do we match that session" is a proxy**, and a proxy optimised past the
point where it tracks the objective starts costing you the objective.

- **Stay inside the plausible human range.** Non-negotiable.
- **Choose the value inside that range by live results** — records per hour, and survival.
- ⚠️ **Every spec owes an answer to: what does turning this OFF actually cost us, live?** If the
  answer is "we don't know, but the operator did it", the spec is being paid for on faith.

★ **The failure this exists to prevent** (PJUD, 2026-08-19): a duty cycle — going completely still
~3 times a minute — was designed, debugged through two wrong diagnoses, and shipped because the
recorded operator did it. Its cost was measured precisely: **−54% throughput.** Its benefit has
never been measured, once. Every validation was a comparison against the recording.

⚠️ **The tell that you have made this mistake:** your success metric can be computed offline, from
files, with the site switched off. If nothing in your evaluation requires the target to answer, you
are measuring fidelity, not results.

⇒ **Sort every spec into two lists** — *validated against live outcomes* and *validated only against
a recording* — and keep the second short and suspicious. On PJUD that split put rate limits,
covered clicks and fill-vs-sweep in the first list, and the duty cycle, pointer rate, click hold,
wheel quantisation and focus bands in the second.

## I.3 ★★★ Capacity is not delivery

`opens ≠ records`. `kept ≠ banked`. A run's own tally is not evidence that anything landed; count it
where it is meant to **end up**, joined on a real key.

| PJUD arm | opens | NEW records | useful |
|---|---:|---:|---:|
| 4 workers (2026-08-20) | 589 | 335 | 57% |
| 8 workers (2026-08-20) | 1,008 | 330 | 33% |
| 8 workers (2026-08-21) | 1,385 | **252** | **18%** |

Twice the fleet, twice the opens, **the same records** — the second arm re-swept a window the first
had just harvested. **Capacity scales; delivery is bounded by unharvested territory.**

⇒ On opens/min the 8-worker arm was a 1.76× triumph. On the actual goal it delivered five records
*fewer*. **Scoring on capacity would have concluded "add workers" and been exactly wrong.**
⇒ Before adding workers, ask whether there is anything left for them to find. Targeted re-work
against a database work-list ran **~95% useful** where a blind sweep ran 33%.

## I.4 ⚠️ Every measurement has a denominator, and it is usually wrong

"Per **what**?" has been got wrong more times than anything else here — three times on one project,
the third *inside the fix for the second*, by the author of the warning about it.

- per **active** second vs per **wall** second — an always-on generator has almost no excluded
  seconds while a human has more excluded than included, so comparing the two averages compares
  two different populations of second. You **cannot be under** on a metric that excludes silence;
- per **worker** vs per **fleet** — per-worker timings measure how the work was split (I.5);
- per **open** vs per **record** — I.3;
- per **session** vs per **address** — the limit is nearly always on the address;
- per **covered window** vs per **wall minute** — a probability evaluated only at the call sites
  that happen to bracket it is a rate per "seconds a call site happens to cover", and that
  denominator drifts silently because nobody writes it down.

⇒ **Put the denominator in the name.** `opens_per_min_fleet` cannot be misread; `rate` can.

## I.5 ⚠️⚠️ Per-item timings measure the SPLIT, not the system

Wherever a fixed cost is amortised over a variable number of items, per-item time is a property of
**how the work was divided**.

Measured (PJUD rung 8, 2026-08-21, n=8 shards): opens-per-court vs seconds-per-open correlate at
**r = −0.814**. A shard drawing sparse courts pays a ~19 s search over few records and looks slow;
a dense shard looks fast. This retro-explains a result that was never explicable as contention — a
4-worker rung came out *faster per worker* (8.43 s) than a solo worker (9.42 s).

⇒ **Judge a fleet on aggregate throughput.** Per-worker figures are for spotting a *sick* worker,
never for comparing fleet sizes.
⇒ Before blaming contention, swap or the network, correlate the slowdown against the denominator
each worker actually drew.

## I.6 ⚠️⚠️ A guard built on a proxy will eventually veto the work it was meant to protect

Twice (PJUD, 2026-08-20 and 2026-08-21) a free-RAM pre-flight check stopped or refused an 8-worker
run that was **healthy** — 6.85–9.73 s per open, better than the 4-worker rung — and the second time
the run went on to set the project's throughput record while sitting at **0.51 GB free**.

The guard measured free RAM. The harm it existed to prevent was *swapping*, and swapping shows up
as **workers getting slower** — which was measurable, and was not measured.

⇒ **Guard on the harm, not on its proxy.** If you must use a proxy: **warn and continue**, keep a
hard floor only where the work is genuinely impossible (the browser cannot start at all), and
**log the proxy's value beside the run** so the result can be read with it in view.
⇒ **Check what your safety guards RETURN.** A guard that silently returns "skip" is
indistinguishable from work that finished.

## I.7 ⚠️ The optimum is not the maximum

Two forms, and both have bitten.

**On fidelity:** once "look human" is a goal there is a strong pull toward *more events*. A pointer
emitting 40 moves/s is as anomalous as one emitting 0. The target is the recorded human's
**distribution**, and being above it is as distinguishable as being below. ⇒ Every spec needs a
measured value, not a direction, and **no spec may be turned up without a recording that justifies
the new number.**

**On speed:** the fastest *setting* is not the fastest *result*. `--speed 0` produced 27 req/min on
one date and 56 on another from the same flag; cutting the read pause 3 s → 2.2 s bought 0.3 s, and
cutting it to a tenth bought nothing measurable. ⇒ **When a knob stops moving the outcome you have
found the floor — say so**, or the next person hunts for speed on an exhausted axis. On PJUD the
rate control became **fleet size**.

## I.8 ★★★★★ Watch a human use the site

You are not scraping what you think you are scraping. Forty minutes of one recorded operator
produced **four request endpoints that appeared nowhere in the codebase**, the largest of them
outnumbering the one endpoint we did collect **five to one** — a whole document class, used most
by the operator, of which we had fetched exactly zero across 117,173 rows for months. The parser
was looking in the right column for the wrong *shape*: a `<form>` where the site puts
`<a onclick=…>`.

⚠️ **"We never look for it" and "these records don't have one" produce IDENTICAL EVIDENCE: zero.**
No amount of reading your own code finds that, because your code is the thing that is wrong.

- **Record the network, not just the screen.** The endpoint list was the finding; a screencast
  would have shown a person clicking icons and taught nothing.
- **Diff the endpoints you saw against the endpoints you implement.** One `grep` per name turned
  "here is a busy log" into "four of these exist nowhere in our source".
- **Then record YOUR OWN scraper with the same instrument** and compare per **wall** second (I.4).
  That experiment needed no new code and had never once been run.
- **Ask the operator where things live, then verify both answers.** Told a control was "usually in
  the header, sometimes in the row", we found it in the row in four of six records — the majority.
- ⚠️ **Three rows is not a sample.** The row-level control sat at rows 3, 6, 7 and 9; a dump of the
  first three showed an empty column every time and produced a confident wrong conclusion.

## I.9 ★ Your NAME for a failure is not an observation of it

A scraper that reports `blocked` has reported that **none of its selectors matched**. That is
evidence about your selectors, not about the site.

PJUD, 2026-08-20: two hours went into an escalating-block model, a cost model and a cool-off
schedule, built on a state name. One attach to the running browser — thirty seconds — showed a
working page with a redeployed DOM.

⇒ **Before believing a scraper that says "blocked", attach to its browser and look.** The tab is
sitting right there.
⇒ Note the asymmetry (I.9 and V.6 together): inferring a block from a **failure** is sound.
Inferring *no block* from an **appearance** is not. Failures are evidence about the world;
appearances are evidence about what the other side chose to show you.

---
---

# BOOK II — THE TARGET PROFILE

Everything site-specific. **One copy of the form per target.** If a fact needs the target's name to
be true, it lives here and nowhere else. This is the part of the library you copy on day one of a
new project; the gaps in your first fill-in are your work-list.

## II.0 The blank form

```
### Identity
  target · URL · what one RECORD is · the scope filter · where output lands · corpus size
### Defence
  what defends it: behavioural scoring / CDN challenge / auth only / nothing
  block tiers, and what each one LOOKS like
### Entry
  the route a human takes · what must be done by hand · what a session costs to establish
  is the route environment-dependent? (residential vs datacenter — measure, do not assume)
### The scarce act
  which single act is rationed · what is free once you have paid for it
### Refusal signatures
  every observed tell, in every language, in every frame, with the detector that catches it
  what "no results" means here, and how you tell it from a refusal
### Limit model
  what is actually counted: rate / concurrency / address / session — with the evidence
  what clears it, and how long it lasts
### Interaction quirks
  readonly fields · widgets · selects · modals (reused? nested?) · pagination · iframes · tabs
### Assets
  how documents are fetched · token lifetime · how to verify one is real
### Storage
  schema · deterministic IDs · join keys · which writer owns which column
### Ceilings
  measured floor per worker · measured fleet ceiling · measured survival envelope
### Open questions
```

## II.1 PJUD — Oficina Judicial Virtual (Chilean judiciary)

The reference fill-in; the only target measured to this depth.
Sources: [`pjud/HANDOFF_WORKERS.md`](pjud/HANDOFF_WORKERS.md) (fleet, pacing, schema) ·
[`pjud/HANDOFF_CDP.md`](pjud/HANDOFF_CDP.md) (site + WAF, and how each conclusion was reached) ·
[`pjud/HANDOFF_PC2.md`](pjud/HANDOFF_PC2.md) · [`pjud/README.md`](pjud/README.md).

| slot | as of 2026-08-24 |
|---|---|
| **record** | a *causa* — civil Ejecutivo Obligación de Dar, bank plaintiff, nationwide, both cuadernos and its PDFs |
| **output** | Neon Postgres + documents to Google Drive. **6,477 causas · 6,307 cuaderno-2 historias · 4,387 documents** |
| **defence** | F5 Shape — behavioural scoring, per-**address** budget, three escalating tiers |
| **entry** | ⚠️ never navigate directly: load `www.pjud.cl`, click through. The direct-URL fallback is banned (I.0). ★ the route is **environment-dependent** — residential is offered a direct link that works; a datacenter address enters cleanly by it and then **cannot complete one search**, and needs the gated route |
| **scarce act** | the **search**. An open is comparatively cheap (~208 queries in an evening with no blocks, against ~24 opens); harvest everything one open reaches before spending another |
| **block shape** | ★★★★★ **a page that renders perfectly with the search form removed** — HTTP 200, no captcha, no error. II.1.a |
| **limit model** | on the **address**, and it lasts **8+ hours**. A router reset clears it instantly (2026-08-20, again 2026-08-21) |
| **refusals** | four distinct tells (IV.1) · `sin resultados` = blocked, not empty · the rejection page is in **Spanish** · a date range > 1 month is refused deterministically · one specific causa refuses every time, and that is a *data* fact, not a rate verdict |
| **quirks** | date fields are **readonly** — drive the picker · the picker *draws* refused days and disables them (`<span>`, not `<a>`) · its header lies in two opposite directions; read `data-month`/`data-year` off the day cells · the document folder modal is **one global element** and will hand you the previous record's rows · a folder is a modal over a modal, so backdrops **stack** · `Etapa` is per-cuaderno, not per-causa · pagination redraws, so row indices go stale · both axes must be scrolled |
| **assets** | fetched **in-page**; the token is a **one-hour JWT**, so enumerate-now / fetch-later is not a design that exists here. Enumerate always, download selectively |
| **worker floor** | 8.6–9.0 s per open = **6.7–7.0 opens/min** — the *site's* floor, not a setting |
| **fleet ceiling** | 1 → 6.37 · 4 → 28.47 · 8 → **50.06** opens/min. Linear to 4, bends at 8 (1.76× for 2× the fleet) |
| **survival** | solo at 6.37/min: **3 h / 1,129 opens clean**. Fleet at 46/min: **30.5 min / 1,385 opens, then refused.** ⚠️ rate and concurrency are confounded — V.4 |
| **remote** | 3 shards each get a full allowance; 4 collapse (2026-08-13). Slower: 13 s search / 8 s causa. Cycle floors at ~28 s |
| **open** | what actually causes the block — VI.4 |

### II.1.a ★★★★★ The block is a degraded page, not a refusal

A blocked address is served the OJV index **rendering perfectly and missing the search form**:
correct title, menu drawn, carousel rotating — and no `#fecCompetencia`, no gate button, no
`<form>`, no `<select>`. It is intermittent: served once, then no tab at all a minute later.

It was diagnosed only when the operator opened the site **on a phone** and it worked instantly;
tethering the PC through that phone reported healthy twice in a row. The address had been blocked
for **8+ hours** with nothing in any log to say so, and eight hours of local evidence were entirely
consistent with "they redeployed and our selectors are stale".

⇒ Generic form: **V.6**.

### II.1.b ⚠️⚠️ The block is invisible from inside

Observed twice (2026-08-20, 2026-08-21). Established sessions worked straight through it:
`refused=0`, zero trouble events, full harvests, every worker finishing on its own work. The
refusal applies to **arrival**. Rung 8 finished at 14:26:24 and the address was refused at
14:26:42 — **18 seconds later** — with the run's own logs completely clean.

⇒ Generic form: **V.5**.

## II.2 HDI — insurer broker cotizador (authenticated)

Source: `cias/HDI-Ruts-Scraper/README.md` (sibling project, outside this repo tree).

| slot | value |
|---|---|
| **record** | email + phone, by RUT |
| **defence** | none to speak of. The enemy is an ASP.NET form that must be driven exactly right |
| **input** | ★ real keystrokes, then blur by **clicking empty space**. `fill()` does nothing at all — the lookup hangs off real keystrokes. Not Tab, and **never the site's own *Limpiar* button**, which reloads dropdowns, jams the ASP.NET queue and turns a 2 s lookup into 20–60 s |
| **truth** | **read the fields back**; what they contain is the answer, not what you sent |
| **dedupe** | a flag column on the work-list, set **whether or not data was found**, makes dedupe free and re-checks a one-column update |

## II.3 patentechile — vehicle plate lookup

Source: `scraper/patente_browser.py`, `scraper/enrich_patentes_local.py`.

| slot | value |
|---|---|
| **defence** | Cloudflare Turnstile + AdSense interstitials |
| **launch** | ⚠️ letting Playwright *launch* Chrome is itself detectable — Turnstile loops forever on it. A normally-launched Chrome with only a debug port and a persistent profile passes with one human click |
| **click** | ⚠️ the counter-example (I.1): a coordinate click lands on an ad iframe and returns **without error**, so use `el.click()` |
| **"no data"** | can be a loading placeholder — allow a 12 s grace before concluding a plate has no record |

## II.4 JPL — Juzgados de Policía Local (municipal ASP.NET)

Source: `scraper/run.py`.

| slot | value |
|---|---|
| **defence** | none. The enemy is fragile ASP.NET postback state |
| **quirk** | ★★ the paginator was losing most of every court. Harvest each page **before** advancing; end-of-list is the site's own greyed *Next*, never a row count. One court went 91 → 135 → **293** records as this was fixed |

⇒ **Four targets, four completely different failure modes. Do not assume the last scraper's
problem.**

---
---

# BOOK III — BUILD

## III.1 Choose the browser strategy first

This decision determines everything downstream. Get it wrong and no amount of careful scraping
logic will save you.

**⚠️ Headless loses to any real anti-bot. Not "is riskier" — loses.** Measured (PJUD, 2026-08-11),
same code, same runner, one flag:

```
headed under Xvfb   entered, 232 courts loaded, search returned results
--headless=new      entry failed after 102 s, the form never appeared
```

F5's challenge script tests `document.visibilityState`, and a headless browser has no visible
surface, so the challenge never completes. **This one flag was the entire reason a daily CI
workflow failed 17 jobs a day for about thirteen days** while everyone looked in the scraping
logic. On a headless CI box, run **headed under Xvfb**.

⚠️ **A background tab has the same problem.** `visibilityState` is `hidden` until you bring it to
the front, so a new tab must be focused before it will clear a challenge (three attempts failed as
blank pages; the same navigation with the tab focused cleared in six seconds).

**⚠️ Letting the automation library *launch* the browser is itself detectable.** Playwright and
patchright add `--disable-blink-features=AutomationControlled`, `--remote-debugging-pipe`,
`--no-sandbox` and a pile of `--disable-features`. Cloudflare Turnstile loops forever on such a
browser. The pattern that works, now used by every family here:

```
1. Launch a REAL chrome.exe yourself (subprocess), with only:
      --remote-debugging-port=<port>   --user-data-dir=<persistent profile>
2. Let a human do whatever must be done by hand (log in, solve a challenge), with
   NOTHING attached.
3. Attach over CDP only afterwards, to drive the page.
```

Cloudflare only scrutinises the *challenge* page, so once solved the attached automation is
invisible on the data pages, and the clearance cookie persists in the profile.

**A persistent profile is not optional.** Logins, clearance cookies and trust tokens live there. A
fresh profile per run makes every run look like a first visit.
⚠️ **The profile directory is the lock, not the port** — one profile dir per concurrent worker.

**★ Attaching over CDP is safe. Reading the DOM is safe.** Explicitly tested in one healthy session
(PJUD, 2026-07-22): `Runtime.evaluate` is innocent and does not affect scoring. Only *input*
matters. Do not sacrifice DOM reading in the name of stealth.

## III.2 Look human where the site is actually measuring

### ★★★ It is the pointer's MOTION, not `isTrusted`

`page.click()` produces `isTrusted=true` events and still gets you blocked, because it **teleports**
the pointer with no approach path and no hover dwell. Measured in one healthy session, same button,
same POST parameters, minutes apart (PJUD, 2026-07-22):

```
page.click()        ->     250 B rejection page in 0.1 s
human arc + dwell   -> 109,234 B of real results
```

The fix: an eased arc with jitter over 18–28 steps, a hover dwell of 140–380 ms, then a press of
55–130 ms. **Never reintroduce a bare `.click()`** on a site that scores behaviour.

★ This one finding *disproved four theories* built on the symptom — that the second search of a
session was refused, that the captcha token was single-use, that beacons had to be fresh, that the
budget was elapsed time. **When a fix disproves theories, delete them in writing**, or someone
rebuilds them.

### The keyboard is scored too

Fixed 60–70 ms between keys is the keyboard equivalent of a teleporting pointer. Measured (PJUD,
2026-08-10) on a session a *human* had just walked into: the whole form cascade passed, and the
very **first** scripted search drew a tier-3 CAPTCHA. One request — no rate involved.

Real typing is noisy: most gaps cluster in a band, with an occasional long one where a person
glances away. Reproduce **both** — a gaussian around a base, plus a random long pause every ~9 keys.

### ★★ Ask what telemetry a human could not SUPPRESS — and check you emit it

The sharpest question in this library, and it came from an operator watching himself scroll (PJUD,
2026-08-14): *when a person scrolls a list, the pointer sits still in screen space while the page
moves underneath, so row after row passes under the cursor.* Those `mouseover`/`mouseout` events
are not something a human chooses to produce.

We produced **none**. The virtual mouse starts at `(0,0)`, and the scroll helper wheeled without
ever positioning it — so every scroll happened from the top-left corner of the viewport, a place no
hand ever rests, with nothing beneath it. Identical wheel events both ways:

```
pointer not positioned  ->   0 mouseover,  0 mouseout,  0 rows touched
pointer over the table  ->  12 mouseover, 12 mouseout,  2 rows touched
```

One `mouse.move()` before the first notch, plus a few pixels of drift between notches. It costs
nothing.

⇒ **Generalise the question.** "Does my action look human?" is the weak form. The strong one is
**"what does a human emit involuntarily while doing this, and is my channel empty?"** An empty
channel cannot be explained away as unusual-but-legitimate — every real user fills it.

Channels worth auditing, each of which we have been caught leaving silent at least once:

| channel | a human fills it when… | how we left it empty |
|---|---|---|
| wheel events | reading any long list | parsed the DOM, never scrolled |
| `mouseover`/`mouseout` | scrolling with the pointer over content | scrolled from `(0,0)` |
| pointer approach path | moving to anything clickable | `page.click()` teleports |
| keystroke rhythm | typing | fixed 60/70 ms metronome |
| `mousemove` while idle | a hand rests on the mouse | 0 between clicks (human: 25.8/s on 98% of seconds) |
| page scrolled to a click target | the wheel turned | `scrollIntoView` moved the page with no input device |
| focus arriving in a control | the pointer moved there, or Tab | `.focus()` teleported the caret in |
| **silence** | thinking, reading, being distracted | never stopped at all — see the duty cycle below |

### ★★ Do not reason about a channel. Measure a human filling it, then copy the number.

Idle `mousemove` was tested and "bought nothing" — two arms, one variable, both refused at the same
record with the same signature. ★★ **The test was run at one twenty-sixth of a hand.** The arms
really did die identically, so the result stands *for that implementation*; the conclusion drawn
from it was wrong.

| | a person | our "idle motion" | our worker between clicks |
|---|---|---|---|
| `mousemove` | **25.8 /s, on 98% of seconds** | ~1 /s, only during pacing gaps | 0 |
| `mouseover` | **6.4 /s inside a modal** | ~0 — it vibrated in place | only what a click path crosses |
| while a record loads | **25.2 /s — they keep moving** | 0 | 0 |

⇒ The amplitude was wrong by an order of magnitude **and the shape was wrong too**: jitter in place
crosses no element boundaries, so it generates no `mouseover` at all — the one channel that
distinguishes a hand from a tremor. **A negative result at 4% of the real amplitude is not evidence
about the channel; it is evidence about 4%.**

### ⚠️ Motion during a wait must have a DESTINATION

The recorded human during a wait was not trembling, they were **travelling over content** — 25.2
mousemove/s and 6.4 mouseover/s *while a record loaded*. Aim at something and traverse it.
(Physiological tremor may be worth adding on top if the defence reads raw coordinates. It cannot
replace travel, and it is unproven.)

### ★★ Two kinds of wait, and one primitive that does both

```
wait for the SITE to answer          driven by the server  ->  a CONDITION, never a duration
wait because a HUMAN is not instant  driven by the person  ->  a DURATION, from a distribution
```

Conflating them cost real data: a cleanup that removed "padding" also removed the pause after an
AJAX control change, so the page was parsed before it re-rendered and records were banked with an
empty section **while the action itself had succeeded**. Silent loss, from an over-applied rule.

⇒ The protocol, stated once: **act → wait for the reaction (condition) → pause as a person would
(duration) → act again**, with the hand moving over content throughout both waits. One primitive,
between *every* action — nothing a person does is instant.
⚠️ Then check it is applied: eleven raw `sleep`/`wait_for_timeout` calls survived in the *most*
human worker, each one a stretch of dead telemetry in a session built to look alive.

⚠️ And **wait for the thing to CHANGE and the old thing to be GONE**, never for a constant to be
true. A wait for a value that is already correct returns instantly, and you read the previous
record.

### ★★★★★ Measure the DUTY CYCLE — you are probably emitting too much

The first time this project recorded **its own scraper with the instrument it had used on a human**,
the result inverted everything it believed:

```
scraper   93% of seconds active,  7% silent   21.0 events/s active   19.5 per WALL second
human     46% of seconds active, 54% SILENT   25.1 events/s active   11.6 per WALL second
```

Per *active* second the scraper sat at 84% of the human — the number quoted for weeks, and the
reason every plan said "we are under, emit more". Per *wall* second it emitted **68% MORE**.

The structure matters more than the average:

```
human    129 silent stretches in 40 min   median 6.1 s  p90 28.3 s  max 60 s  (29 of 15–60 s)
scraper    5 silent stretches in 3.6 min  median 3.0 s  p90  8.2 s  max  8 s  (none over 15 s)
```

**A person works in bursts separated by real stillness. A generator hums.** Every spec being tuned
was a RATE; this is a RHYTHM, and it is the one an observer notices first.

- **Report per-active-second AND per-wall-second, always, with the silent fraction beside them.**
- **Fix it by STOPPING sometimes, never by moving more slowly.** The human's rate *while moving* is
  higher than the scraper's; lowering the rate gives the same wall average and a completely
  different distribution — which is the thing being measured.
- ⚠️ **This is where "more presence is more human" stops being true.** Past a point, adding presence
  makes you the least human thing on the site (I.7).

⚠️ **The honest cost, and the honest status.** Matching a human's duty cycle roughly **halves**
throughput per wall-hour. ~~"This project's history says the trade pays."~~ **STRUCK the same day it
was written (2026-08-19).** The measurement stands. The prescription does not: the cost is measured,
**the benefit has never been measured at all**, and every validation was against a recording, which
cannot answer the only question that matters. ⇒ **Treat a duty cycle as an untested hypothesis
carrying a known 50% bill, not as a spec.**

### ⚠️ A burst is not a rate

A switch that fires its second request **~4 s after the first**, where every clean run spaced that
same endpoint **29–38 s** apart, looks minor averaged over a minute and is a completely different
*pattern*. Nobody opens a case file and flips to its second volume four seconds later.

⇒ **Pacing configured per ITEM says nothing about the shape within an item.** If handling one record
now costs two requests, they land together, and "requests per minute" will not show it.

## III.3 A worker must know WHERE IT IS

Operator's call (PJUD, 2026-08-14), after the site moved its entry route: *a worker should recognise
where it is and act accordingly.* Every entry-failure message described what did **not** happen —
"target covered", "no form after attempt 1", "could not reach the site" — and none said where the
worker was standing. It was standing **on the form it had been sent to fetch**, refusing to click a
gate button it had already passed. That cost an hour of chasing the WAF.

The fix is one function:

```
locate(page) -> form | results | modal | gate | aviso | captcha | blocked | www | blank | unknown
```

- **Never raises.** Mid-navigation returns `unknown` — "I could not tell" must be a *state*, not an
  exception, and must never be confused with "nothing is wrong".
- **Order by what is actionable.** A page can be several things at once (a form *with* results, a
  gate *under* an overlay); return the one that decides the next move.
- **Wire it into the give-up paths and make them RECOVER.** Where the state says the job is already
  done, take it instead of failing.
- **One place knows what the site can look like.** Add a state here, not another special case at a
  call site.

⇒ Related failure: **detect the destination, not the hurdle.** A path that recognises success only
by the *obstacle's* markers reads a click-through that landed past the gate as a failure.

### ★ Detect overlays by hit-test, never by id

Two functions here each knew exactly one overlay by name, each written the day that overlay cost a
run. A third would have been invisible to both.

Ask the browser what is genuinely on top: `elementFromPoint` at the target's centre, walk up to the
nearest floating/dialog container, read its id, z-index, text **and its own dismiss controls**, then
click whichever says close/cerrar/aceptar/ok/×. Verified against an injected overlay with an id
nothing in the codebase had ever seen — detected and cleared first time.

⚠️ **Protect your own modals.** A generic overlay-closer will happily close the record you are
standing in. Keep an allow-list of overlays that are the *work* rather than an obstacle.
⚠️ **"Unhittable" is not "covered".** A button under a `<select>` in normal flow is a **layout**
problem — a different diagnosis with a different fix. Disguising one as the other is how "covered"
came to mean three things in a week.

### ⚠️ Never click a covered target

Driving raw coordinates loses the library's actionability check, so a backdrop or sticky header
takes the press. Hit-test yourself and **refuse to click** if it misses.

Correlation observed (PJUD, 2026-07-22): 0 covered clicks → survived 50 records; 1 → blocked at 23;
2 → blocked at 4. ⚠️ **Marked NOT CAUSAL** — a later trial broke the correlation. Refusing is still
right, because a click where your element is not is simply a wrong action.

Two traps inside the hit test, both real:
- **Scroll the candidate you are about to test.** Centring `querySelector`'s *first* match when two
  nodes match scrolls the invisible one and leaves the real button off-screen.
- **An off-screen point returns `null`**, which reads as "covered". Only hit-test what is in view.

### ★★ The same environment can be served a different SITE

PJUD, 2026-08-14. The landing page gained a second entry route. One machine was scanned, only the
new link was seen, and a single global preference was pushed. Both halves were wrong — a cloud
runner is still offered **both**, and the two environments need **opposite** ones:

| | direct link | gated route |
|---|---|---|
| residential | works — 375 record opens | (not offered) |
| datacenter | enters cleanly, then **cannot complete one search** | the only route that works |

⇒ **Environment-dependent behaviour needs an environment-dependent setting**, with the measurement
written beside it. ⇒ **A probe that answers "what is this machine actually offered?" costs two page
loads.** Each guess instead cost a whole session.

### ★★ When something new breaks, ask what you started DOING that you never did before

A worker that had run for weeks began dying after exactly ten records, remotely only, always on the
same record — while the same code on the same records ran 375 clean locally. Days of counters
(opens, bytes, requests, elapsed) explained none of it. The answer was one line in the diff: it now
switched to a **second sub-view** on every record, an interaction it had **never performed before**.
Disabling that alone lifted the wall — the record that hung for 90 s opened in six.

⇒ **Diff the BEHAVIOUR, not just the code.** "What actions does this version take that the last one
did not?" is a much shorter list than the code diff, and it is where new failures live.
⇒ Its own docstring had stated the risk — *"it went unnoticed because worker A only ever reads
cuaderno 1 and never switches"* — written months earlier by someone fixing a related bug. **When
you make a warning's precondition come true, that warning is now about you.**

## III.4 Getting input the site will accept

**`fill()` often does not fire the site's own logic.** Sites that hang a lookup off real keystrokes
do nothing at all on `fill()`.

**How you BLUR matters as much as how you type.** Blur by **clicking empty space** — not Tab, and
never the site's own *clear* button (HDI's *Limpiar* reloads dropdowns, jams the ASP.NET queue, and
turns a 2 s lookup into 20–60 s). Finding a safe blank point is worth a helper: walk a grid of
viewport points with `elementFromPoint`, rejecting anything interactive or inside a modal.
⚠️ Prefer **hover-and-settle** over a real press unless you know a press is safe — a click on the
background once dismissed things that were needed.

### ~~Read-only inputs: unlock the property, then type~~ → ★★ **use the widget**

**OVERTURNED 2026-08-16 by the operator, who simply tried to use the site: *"I can't type the dates
in the search. I can only use the date picker."*** Both fields are `readonly` and carry
`hasDatepicker`, so unlock-type-escape is a sequence **no user can produce** — on the one form where
the anti-bot token is minted. It had been in every run this project ever made.

The trick is seductive because it is technically clean: the mutation dispatches nothing untrusted
and the keystrokes really are `isTrusted=true`. Both true, both beside the point. **`isTrusted` was
never the question.**

⇒ **If an input is `readonly`, the site is telling you where its real control is. Go and drive
that.** For a jQuery UI datepicker: click the field, wait for the widget, click prev/next to the
month, click the day link — every step a human click.

⚠️ Four traps found driving one datepicker, each costing a live session:

- **Poll for the widget; never sleep a flat interval.** A 500 ms wait declared "did not open" on a
  widget that opens in ~700 ms.
- **Do not threshold on how many days are rendered.** "≥20 day links" failed twice on a widget that
  was open the whole time.
- ★★ **DRAWN IS NOT SELECTABLE.** The widget renders all 31 days and **disables** every day after
  today: a refused day becomes `<td class="ui-datepicker-unselectable ui-state-disabled">` holding a
  **`<span>`, not an `<a>`**. Counting *cells* can never see this. A cloud runner and a local worker
  died on the same cell minutes apart, both asking for the 31st on the 18th; the only evidence
  either produced was `#fecHasta reads ''`. ⇒ **Count the anchors, not the cells**, check the target
  cell for `disabled`/`unselectable`, and **clamp a future end-date at the door** — a person standing
  at that calendar clicks today; the 31st is simply not offered.
- ★ **Read the calendar's state from its DAY CELLS, never its header.** Both header reads are traps
  and they fail silently *in opposite directions*: `.ui-datepicker-month` was a `<span>` but
  `.ui-datepicker-year` a `<select>`, so `textContent` concatenated every option
  (`"2010201120122013…"`) → a year in the billions → "past the target" always true → the widget
  marched **backwards**; reading `.value` gave **2020 while the header displayed Agosto 2026** →
  always "before the target" → it marched **forwards**. jQuery UI stamps `data-month` (0-based) and
  `data-year` on every day `<td>` — the calendar stating what it is actually showing, in a form
  that cannot disagree with itself.

⚠️ **And check what the form holds before you trust it: these fields start EMPTY.** An empty window
searches instantly, returns zero rows, and still reports "results" — a clean-looking answer to a
question nobody asked. It went unnoticed for months because the worker typed the dates in every time.

⚠️ **Do not go back to `el.value = x` + `dispatchEvent(new Event('change'))`.** That fires
`isTrusted=false`, and the failure is delayed and confusing: the search succeeds *once*, and the
**next** request comes back as the rejection page. It burned a profile (PJUD, 2026-07-21).

### Selects: arrow keys, or a real pointer arrival — but check whose rule this is

`select_option`'s synthetic change was *believed* to trip the WAF, so the fix was arrow keys at
human cadence. ⚠️ **Re-read the evidence before inheriting this.** In the project's own notes the
rule appears twice with opposite strength ("never `select_option` the tribunal — untested since the
07-22 fix, it may well be innocent" vs "`select_option` on the smaller select: TOLERATED,
validated"). Then a real person was measured: **zero keydowns in an entire session**, both selects
changed, because picking from a native dropdown is a gesture the page sees as a trusted `change`
with no keyboard at all.

So the arrow keys are **our invention**, and an expensive one — walking a 230-option list is ~54
metronome keystrokes into a channel the human leaves completely empty. Meanwhile the one thing we
cannot reproduce is the native popup: it is an OS surface and no CDP event reaches it.

⇒ Two honest options, and the choice needs measuring: **trusted keys the user never pressed**, or
**a synthetic change with a real pointer arrival and no keys.** Approach the control with the
pointer either way, and **never click a `<select>`** — that opens the native popup, and everything
after it is delivered into a dropdown nobody can see.
⚠️ `select_option`'s default timeout is 30 s of silence.

### ★ Always read the value BACK

Typing is not proof the value arrived. A wrong date window **does not fail loudly** — it returns
plausible results for the wrong period and files live courts as empty.

**And validate at the door.** PowerShell's `Get-Date -Format "dd/MM/yyyy"` returns `08-08-2026`
under an es-CL locale, because `/` in a .NET format string means "the culture's date separator", not
a literal slash. That malformed window reached the form and a live court was recorded as EMPTY
(PJUD, 2026-08-08). Reject anything not matching `\d{2}/\d{2}/\d{4}`.

## III.5 Structuring the work

### ★ Find the scarce act, and harvest everything around it

In PJUD, opening a record is expensive and fragile; queries are cheap (~24 opens before a block
versus 208 queries in an evening with none). Everything the open makes available is already in the
DOM and costs nothing more.

⇒ **The detail view is where you harvest, not where you shop.** Take the header, the parties, the
sub-document list, the history — all of it, every time. Only extra *requests* cost anything.
⇒ Identify your scarce act explicitly. It is rarely the thing that feels slowest.

### ★ Split workers by HOW MUCH of the record they intend to take

Once the scarce act is named, the natural division of labour is by **depth**, not by subject area:

| worker | job | cost per record |
|---|---|---|
| **discovers** | sweep the list, take everything the open makes free + one document | 1 open, 1 fetch |
| **finishes** | every document, every sub-lookup, every tab | 1 open, **40+ fetches** |
| **refreshes** | re-open a finished record, take only what is NEW | 1 open, **0 fetches** |
| **mimics** | exactly what a measured human does, and nothing else | 1 open, **0 fetches** |

This is what lets bounded work run where the budget is small and unbounded work run where it is
large: discovery needs a big allowance and gets the residential address; a finisher is bounded by
construction ("here is a list, finish it") and fits a small cloud session exactly.

⚠️ **A refresh worker's whole value is one number: fetches when nothing changed. It must be zero.**
Otherwise it costs exactly what the deep worker costs and buys nothing — while looking *completely
successful*: same rows written, same green tick. Load what you hold, hand it to the shared harvest
as a skip list, and **assert the invariant in the run's own output.**

⚠️ **Skipping work must never mean forgetting the answer.** The skip list has to carry the *stored
value*, not merely suppress the lookup, because the row still gets written back and a field you
declined to re-fetch goes back **empty** and erases what you had. (Same shape as the upsert trap,
III.6.)

⚠️ **The deterministic row id is what makes any of this work, and it is exactly what drifts.** If
the id scheme changes on either side, nothing matches, every skip list is empty, and the refresh
silently becomes the deep worker again. **Test it by refreshing a record you finished minutes ago**
— anything re-fetched there is drift, not news.

### ★ Reject the record at the cheapest point that can decide

The scarce act buys a *decision* as well as data. Once the record is open its header often says
whether it is wanted at all, so the discard happens **there**, before any sub-view is opened or any
document bought (operator, 2026-08-14: *"if the header doesn't match, ditch that causa; there's no
need to go into its books"*). About 11% of the corpus goes on one rule.

⇒ **Order the work so the cheapest disqualifying test runs first.** "Grab everything while we are
here" is right for *free* data and wrong for anything costing a request.

### ⚠️ A "record-level" field may be a sub-view field in disguise

PJUD's header shows `Etapa: …`, which reads like a property of the record. It belongs to the
**currently displayed cuaderno**, and switching books re-renders it:

```
book 1 — Principal   ->   Etapa: 1 Notificación demanda y su proveído   (9 rows)
book 2 — Apremio     ->   Etapa: 1 Mandamiento                          (2 rows)
```

Parse the header after switching and you store the wrong value into a column named for the record —
and gate on it too. Nothing looks broken at any point.

⇒ **Read record-level fields before touching any sub-view**, and leave the reason in a comment where
the next person will reach.
⚠️ Both books numbered their stage **1**: ordinals are scoped to the sub-view, so an enumeration
inferred from one view does not hold across the record.

### ⚠️ Never match an enumerated label by its full string

Stages arrive as `"8 Terminada"`, `"1 Notificación demanda y su proveído"`. A skip list of exact
strings looked obvious and was quietly broken: it held `"6 Terminada"`, which **does not exist**
(6 is *Impugnación de Sentencia*; Terminada is 8), so that entry matched nothing for as long as it
existed — and the ordinals are sparse (0–8, then 12) *and* per-sub-view.

⇒ **Strip the ordinal, fold case and accents, match a substring.** Sites abbreviate: the single
stored instance of "Téngase por no presentada la demanda" actually reads *"…la **dda** por
apercibimiento"*.
⚠️ **A filter that silently passes everything is indistinguishable from one that correctly matched
nothing.** Count what you dropped and log it, or you cannot tell them apart.

### ★★★ Enumerate always, fetch selectively — and never gate the ENUMERATION on a name

When a container lists items and only some are wanted, the listing is usually **one request for all
the labels** while fetching is one request each. Record the entire inventory every time; download
only what matches. This is not tidiness, it is the difference between two failure modes:

```
matched nothing   ->  "we looked, and this record has no contract"
never enumerated  ->  "we never looked"
```

A name filter alone cannot tell those apart, and the second silently looks like the first.

⚠️ **Labels are free text typed by whoever filed them.** Real examples from one afternoon:
`'1. CONTRATO DE ARRENDAMIENTO'`, `'pagare'`, `'mandato claudio altamirano'`, `'MUTUO'`,
`'EP MUTUO HIPOTECARIO Repertorio Nº 10.180-20'`, and for one counterparty abbreviated to `'CTO'`.
**Any pattern will miss.**

★ It paid out on the first real run: a label the default pattern did not match turned up in **three
of five** records and was, on inspection, the very instrument being sought under another legal name.

### Pagination

- **Harvest each page before advancing.** A row index belongs to the page it was read from;
  paginating to the end and then clicking page-1 indices opens the **wrong records**.
- **End-of-list is the site's own greyed-out *Next*, never a row count.** Counts drift (blank filler
  rows) and an overcount stops the walk one page early, truncating exactly the biggest pages. One
  court went 91 → 135 → **293** as this was fixed.
- ⚠️ **Results usually sort newest-first, so early-quitting pagination silently drops the OLDEST
  items.** A dataset whose records start mid-window is this bug's fingerprint.
- ⚠️ **A pagination click is a query.** It hits the same endpoint and must draw on the same rate
  budget; pacing it separately meant every large page set quietly fired at three times the intended
  rate.
- **Distinguish "no next page" from "the click did not work".** A boolean conflates them and the
  caller reads False as "done". Return a **reason** — `advanced` / `last` / `stuck` — and flag the
  stuck case as incomplete.
- ⚠️ **After a redraw, row indices are stale before they are wrong.** Read the rows only once the
  redraw has finished.

### Resume, and auditable completeness

- Write state after every item, so stopping costs one item.
- Skip completed units **without issuing a request**.
- Re-open an item only if it is missing something it should have — **never one whose answer was
  "there is nothing here"**. Retrying settled questions spends the scarce budget forever.
- Record `rows_seen` against the reported `total` so under-collection is visible later.
- ⚠️ **Audit coverage by the UNION across workers, never by one worker's state.** Overlapping ranges
  inflated per-worker "missing" counts ~3× while the real gap — five pages stuck on page 1 —
  appeared in no worker's state at all.
- ⚠️ **Resumable state belongs to the QUERY that built it.** A slot's state file is only valid for
  the window it was built for.
- **A flag column makes dedupe free.** Mark every key you checked, *whether or not you found data*.
  Write the result first, set the flag second, so a kill mid-item costs a re-check and never a lost
  row.
- ⚠️ **State held in memory is rewritten wholesale.** A running worker rewrites the whole file after
  every item, so outside edits are silently overwritten (49 of them, PJUD, 2026-08-10). Stop the
  worker before touching its state; and because the write is not atomic, a reader can catch a
  truncated file — snapshot and retry rather than parsing the live file.

## III.6 Storage

- **Deterministic IDs, derived from the data.** `<parent_id>-<child_key>` beats a generated id:
  re-running updates in place instead of duplicating, and joins stay checkable by eye.
- ⚠️⚠️ **`upsert` writes EVERY column — so a value the writer lacks becomes empty.** The single most
  destructive trap in this repo. Near-misses: a sweep that would have blanked the `corte` of all 180
  courts, and document URLs on 74 records the moment the sweep reached a scraped region. Remedies,
  by writer: **insert-if-absent** for reference tables · **read the existing values and carry them
  forward** · **a targeted `UPDATE` of only the columns this writer owns** — which is what a
  backfill worker must do, always.
- **Shells must never overwrite real detail.** A discovery pass registers a key and a date with
  `ON CONFLICT DO NOTHING`, so re-running is free and a shell can never blank a full record.
- ⚠️ **Two ids for one object — one stable, one positional — agree until the list changes.** A
  document cached as `{record}/c2-{index:02d}.pdf` while its row is keyed on the document's own
  folio: both correct, and matching perfectly *because every record had been scraped exactly once*.
  The source lists newest-first, so one new filing shifts every index; the next run gets a **cache
  HIT** on that name, stamps the old document's URL onto the new row, uploads nothing, and reports a
  saving. ⚠️ Measured exposure when found: **zero** — a property of the schedule, not the design, and
  the most dangerous kind of clean result. ⇒ **Derive the cache key from the same field the row id is
  derived from**, and ask what happens *the second time you see the same object*.
- ⚠️ **Store the DIRECT link to a file, not its preview page.** Normalise it in **one** helper and
  apply it to every uploader **and every cache** — a cache hit otherwise keeps handing back the old
  shape.
- **Types, and the date trap.** `'15/07/2026'` does not compare as a date; profile every value
  before converting. ⚠️ **Confirm day-vs-month order, never assume it** — PJUD confirmed DD/MM by
  checking the maximum first component was 31 across all date columns; reversed, it would have turned
  100k+ rows into *plausible wrong dates* nothing downstream would ever flag. ⚠️ Convert to ISO in
  **your own code**, not by trusting the session's `DateStyle`. Leave as TEXT anything that only
  looks numeric — identifiers with markers, national IDs whose check digit can be a letter and whose
  leading zeros are significant.
- ⚠️ **A multi-statement ingest has an inconsistent MIDDLE.** Decide whether that is survivable.
- ⚠️ **A consumer that hand-lists its tables drops the one you just added.**
- ⚠️ **A scraper with no ingest has no output.** A harvest sitting on disk is not a result.

## III.7 Assets and documents

- **Let the page fetch it.** Read the form's action and token and have the page itself
  `fetch(url, {credentials:'include'})`. Same single request the click would have made, no popup, no
  viewer, verifiable result (0.7–5.2 s measured). ⚠️ This is **not** an out-of-process HTTP client
  with copied cookies — that fetches from outside the browser and looks nothing like a user.
- ⚠️⚠️ **Never judge a downloaded document by size or status.** Clicking a link opens a popup and the
  browser renders the PDF in its viewer, so what comes back is the **viewer's host document** —
  `<embed type="application/x-google-chrome-pdf">`, ~14 KB of wrapper HTML, status 200. This produced
  **two opposite wrong conclusions in one day**: three wrappers filed on disk as captured PDFs, then
  a perfectly good click reported as a block. F5's interstitial is ~8–14 KB of obfuscated JS, also
  200. ⇒ **Check the magic bytes. `body[:4] == b"%PDF"`. Nothing else is evidence.**
- ⚠️ **A short-lived token means the expensive act cannot be split from the cheap one.** A one-hour
  JWT means enumerate-now / fetch-later is not a design that exists.
- ⚠️ **A sample maximum is not a maximum.** "A record can hold six" went into a code comment and a
  commit message as a bound; it was the largest of five observations, and the seventh record had
  nine. It mattered because that number drove the requests-per-record estimate and therefore the
  pacing. ⇒ **The cheap test is to run the enumeration with a filter that matches nothing** — every
  container opened, nothing downloaded — which yields the true distribution for one request each.
- ⚠️⚠️ **A container reused per record will hand you the PREVIOUS record's contents.** III.2 and
  IV.1 both; the failure is silent and the output is a *corruption*, not a gap.

---
---

# BOOK IV — OPERATE

## IV.1 Knowing when you have been refused

**This is where scrapers lie to you, and it is the section to read twice.** Almost every "the site
blocked us" incident in this repo was something else, and several "everything is fine" hours were a
total refusal.

### ★ Judge a search by the RESPONSE, never by the page

The results table keeps showing the **previous** search's rows while a new one runs.

- *"Does the total say `Total de registros`?"* is true **from the last search**. An early version
  returned at 0.0 s every time and recorded every court with the **previous** court's totals.
- A DOM fingerprint cannot tell empty→empty apart: an empty search clears the table, so two empties
  in a row look identical and "changed" never becomes true.

⇒ Ground truth is **a response from the search endpoint arriving after the click.** Clear your
network tap immediately before clicking, then wait for the response.

### The four tells of a refusal, and why one detector is never enough

1. A frame containing the rejection text.
2. A rejection **body**: the text AND a size in the band the WAF actually uses (100–1000 B).
   ⚠️ Size alone once killed a healthy sweep over a legitimate 0-byte response.
3. A challenge iframe.
4. **The submit button stuck `disabled` while the page is NOT busy.** No rejection page, no iframe —
   every other check says healthy. This is exactly how a spent session ran all night producing
   nothing (PJUD, 2026-08-08/09).

### ⚠️ Match every language and every wording

Both PJUD block detectors matched only the **English** F5 text while the site answered this browser
in **Spanish**. Both went blind *at the same moment*, and a run reported health for an hour while
every search was refused (2026-08-05). It happened a **third** time with the tier-3 CAPTCHA frame,
whose wording matched no existing pattern, so two workers sat behind a full-page CAPTCHA while every
detector reported health (2026-08-10).

⇒ **One wording, one language, one frame you are not reading is all it takes.** Search *all* frames,
match every known phrasing.

### ⚠️ Duplicate detectors go blind together — keep ONE copy

The reason the Spanish failure hit two tools at once is that each carried its own matcher. Entry,
search, freshness and block detection should have exactly one implementation. **This is not a style
preference; it is the documented failure mode.**

### "No results" is ambiguous, and the ambiguity is expensive

- **A spent session returns "no results" for records that exist.** One run reported 20 courts empty
  and exited cleanly; a healthy session found 52 records in one of them. **Every unit after a block
  is a false negative that nothing in the data marks.**
- **"No results" can be a loading placeholder** — allow a grace period before concluding.
- **Never call a slow response empty.** PJUD's floor is 25 s, and the hard cap extends to 3× while
  the site's own spinner says it is still working; a slowdown from 11–35 s to over 75 s was
  discarding valid searches.

### ⚠️ "Online" and "can reach the target" are different questions

A connectivity check that probes **raw IPs** is deliberately independent of the target — which is
right, because it distinguishes an outage from a block. But it returns *online* while the target's
name is unresolvable, and the worker then spends its entire arrival budget on a host it never looked
up. The run ends looking refused; it never reached the site at all (observed 2026-08-13:
`ERR_NAME_NOT_RESOLVED` burned all three entry attempts while a residential line got HTTP 200 in
1.3 s the same minute).

⇒ **Ask both questions: `internet_up()` AND `can_resolve(target)`.** A resolution failure is an
outage, not a refusal — no cool-off, no recovery spent, no profile rotated.
⚠️ **And consider you may be causing it.** Every walk-in and retry re-resolves the host, so N workers
× M attempts is a lot of queries from one address range in minutes: **a retry storm can manufacture
the DNS failures that then look like blocks.**

### A stuck modal looks exactly like a block

A record open times out → the modal never closes → its backdrop covers the controls → every later
click hits the backdrop → searches "return" nothing. One worker reported 20 courts empty and exited
successfully. **Clear stuck modals explicitly**, and wait on the site's own spinner rather than your
guess about readiness.
⚠️ **A nested modal's backdrop is not the outer modal's backdrop.** A helper that waits for *no*
backdrop is correct at depth 1 and impossible at depth 2, because the modal underneath keeps its own.
⇒ The condition is that the backdrop count **returns to what it was before you opened**.

### ⚠️ The silent throttle

The worst failure has no tell at all: no rejection page, no challenge iframe, just operations that
quietly stop working. **Consecutive failures with a clean block-check are themselves the signal.**
Count them and treat N-in-a-row as a block — and scope that counter to the **run**, not to the
current item: scoped per-item it never reaches the limit, and a throttle costing two items per page
degrades for hours without a single detector firing.

## IV.2 Pacing, rate and concurrency

**It is a RATE, not a quota.** One model fit every PJUD trial: requests per unit time from an
address, not a count of sessions or a total volume. The same address did 1,618 MB in 8 h with zero
hard blocks while a datacenter address took a terminal block at 431 MB. ⚠️ But see V.4 — rate and
concurrency have never been separated here.

**⚠️ Gentle pacing can be compensation for bad behaviour, and hide it.** PJUD ran at a 60 s search
gap and a 90 s open gap for weeks. Then a probe ramped both down on live sessions (2026-08-10):

```
result requests  45 -> 22 -> 10 -> 6 -> 4 s   across 51 requests   never tripped
record opens     90 -> 60 -> 40 -> 25 -> 15 -> 8 s  across 18      never tripped, 18/18 documents
```

Below ~15 s neither cycle shrank further, because the **site's own response time** (12–26 s)
dominates. The old gaps were not a rate limit — they were paying for a metronome keyboard and no
scrolling. Settings went to 20 s / 25 s and the same address then did **730 opens in a day.**

**⚠️ The gap is a floor on the interval, never a promise about the rate.** Derived from config it is
wrong in **both** directions:

- **It goes UP when the expensive work runs out.** A worker whose per-item cost was dominated by an
  expensive step becomes almost pure querying once those items are banked: 66 result requests in ten
  hours became one every 20–40 s — **~15×**, same code, same gaps.
- **It goes DOWN as local workers are added.** They share one connection and one machine, so each
  extra worker stretches every other one's cycle. Four local workers measured **1.75 result
  requests/min — about what one produces.**

⇒ **Measure the rate from the logs. Never compute it from the config.**

**⚠️ Remote workers do NOT self-damp — translate the rule.** Each cloud runner has its own machine
and link, so N runners at the same gap really is N× the rate. And the budget may belong to the
**range**, not the address: three shards on three unrelated cloud IPs took their first block within
**fourteen seconds** of each other while residential workers sweeping the same minute were untouched.
⇒ Scale each runner's gap by the shard count: N shards each firing every `base×N` seconds is
`1/base` requests/second whatever N is.

**⚠️ Keep concurrent workers out of lockstep.** Two workers started together pace from the same
instant and stay synchronised forever — observed logging every step at the identical second. To a
rate limiter that is not two requests spread over a minute, it is two requests in the same instant,
once a minute: the worst possible shape. **Add ±15% jitter to every gap.**

**A worker count is not a budget.** "2 workers yes, 3 no" held for weeks and then stopped being true
— four ran clean once the input stopped looking robotic. **What predicted failure was never the
worker count or the rate on its own; it was the trouble events** (blocks, timeouts, failed selects).
Alarm on those.

## IV.3 Arrival, gates and fleets

### Arrival is its own event, separate from rate

A burst of brand-new sessions is itself a trigger. Six shards launched together and only **one** got
in; four fresh local browsers loading the site in the same second all failed.

⚠️ **Fixed offsets do not solve this** — entry can take three minutes, so an 8 s or even 50 s stagger
still leaves every worker inside the entry sequence simultaneously.

⇒ **Use a condition, not a timer.** One worker enters at a time, and the gate opens only when that
worker's **first real query comes back** — not when it merely reaches the form. (On 2026-08-10 all
four workers reached a form and none could search; a form-based release would have opened the gate
four times on the strength of nothing.)

### ⚠️ A shared lock is never actually impossible — find the thing both machines can see

The obvious fallback for workers on separate machines is a timer, because there is no shared
filesystem. Resist it: a timer cannot express "after the previous one succeeded", and for a
*concurrency test* it is not an approximation but a broken instrument — staggering two runners by 30
minutes means that for those 30 minutes there is exactly one session, which measures nothing.

They always share *something* — the database you are writing results to. One row is enough:

```sql
-- acquire: ONE conditional update, so two racers cannot both win
UPDATE entry_gate SET holder = :me, ts = now()
WHERE id = 1
  AND (holder IS NULL OR holder = :me OR ts < now() - interval :stale)
RETURNING holder            -- a row back means you hold it
```

Three properties, each load-bearing:

- **Single statement.** `SELECT` then `UPDATE` has a window where both readers see "free". Let the
  database serialise the row.
- **Stale-break.** A holder that dies must not strand everyone. Release with `WHERE holder = :me`, so
  a broken-as-stale holder cannot later clear a gate that now belongs to someone else.
- **Fail OPEN.** If the database is unreachable, log it and proceed. A gate that failed closed would
  stall the fleet over an unrelated outage; failing open costs at worst one ungated arrival — exactly
  what you had before the gate existed.

Verify all three against the real database: B refused while A holds, B acquires after A releases, a
silent holder broken after `stale`.

### ⚠️ Three ways a shared gate quietly stops working

All three were live at once here and together produced a "concurrency ceiling" that did not exist.
**A gate that is present but not working is worse than none, because you trust the results.**

1. **A killed process never releases it.** Cancel a cloud run and workers are killed outright —
   `atexit` never fires and the row stays held by something that no longer exists; the next run
   queues behind a corpse for the whole stale timeout. ⇒ **Stamp the holder with the run id and break
   foreign holders on sight.** ⚠️ Parse that id carefully: ours were `slot1-<run>` but also
   `slot3-swap-<run>`, and taking the second dash-separated field read `swap` as the run id — which
   would have broken a **live** holder and let two workers in at once, the exact thing the gate
   exists to prevent, introduced while fixing it. **Take the last field.**
2. **Some arrival paths don't use it.** Ours had four ways in — boot, recover, outage re-entry,
   browser swap — and only two were wired to the shared gate; the others fell back to a *file* lock,
   which across machines is meaningless. So every recovery re-entry was ungated: the moment several
   workers blocked, they all walked back in simultaneously. ⇒ **One factory, every path.** Note the
   shape: it only appears once workers start *failing*, so it is invisible in the happy path.
3. **It gets held across a sleep.** A blocked worker cooled off for 3–9 minutes holding the gate,
   turning one worker's rate penalty into the whole fleet's stall. ⇒ **A gate is for arriving.
   Release before any wait**, re-acquire when you are ready to walk in.

### Fleets: what scales, and what the numbers mean

- **Scaling is linear until it bends, and the bend is measurable.** PJUD: linear to 4 workers
  (28.47 opens/min, 4.47× solo), then **1.76× for the step to 8** (50.06/min) — the first measured
  contention here. Anything sublinear *before* that was the **entry gate**, not contention.
- ⚠️ **The entry gate is a throughput tax that grows with fleet size** — every worker pays it once,
  and it is charged at the moment the fleet looks least like a person.
- **A fleet does not end, it DISASSEMBLES.** Shards exhaust at different times, so a rung left
  running becomes an (N−1)-worker rung still labelled N. **Stop at the first completion.**
- **Hold per-worker work constant when comparing fleet sizes**, not total work divided.
- ⚠️ **Rotate the address, or cool off, between rungs** (V.10). ⚠️⚠️ But rotating makes rungs
  incomparable **on survival**, since each meets a different address history. **Throughput
  comparisons want rotation; survival comparisons want one rung per address.** One ladder cannot
  serve both — decide which question it is for before running it.
- ⚠️ **Price a tripped experiment in ADDRESS-HOURS, not records lost.** A block that lasts 8+ hours
  makes walk-the-ladder-until-it-breaks the wrong shape of experiment on any address you also need
  for production. **Test from one address, work from another.**

## IV.4 Recovery — telling the failure modes apart

### ★ There are two failure modes and they need opposite remedies

| symptom | what it is | what fixes it |
|---|---|---|
| rejection page / challenge iframe / support id | a **rate verdict** | cool off, re-enter the same browser |
| every control fails — option list gone, values will not stick | the **session/browser is wedged** | a **replacement browser**. Nothing else. |

Measured four times in one afternoon (PJUD, 2026-08-12): a replacement browser had each worker
searching again within a minute. The negative was proved directly — one worker spent a full 180 s
cool-off *and* a clean re-entry, still could not drive the form, and stopped anyway; relaunched onto
a new browser it pulled the very same page on its first search.

⇒ **A recovery ladder needs both rungs.** Spending six cool-offs on a wedged session is how a worker
loses twenty minutes and then stops regardless.

### The rest of the ladder

- **A block does not burn the profile.** Re-entry clears a tier-2 block in ~18 s: close the tab, walk
  in again, and the exact request that was refused succeeds. **Rotating the profile throws away a
  warm session for nothing.** (This overturned months of folklore, and a diagnostic tool carried the
  stale advice long after.)
- **Cool off proportionally, and let a clean streak win the budget back.** Cool-off scales with the
  recovery number; count **consecutive** blocks and reset after a run of clean work — a lifetime cap
  strands a long job after six blocks however many clean hours sat between them.
- **CAPTCHA is a stop, not a puzzle.** Detect it, report it, stop. Never script an answer. Cooling
  off will not clear it and rotating the profile only earns a fresh one.
- ⚠️ **An outage is not a block.** Check connectivity against **neutral third parties** — never the
  target; asking the site that may be refusing you cannot distinguish the cases — and never charge an
  outage to the block budget. Related: **if the public IP changed during the outage, the session is
  void** — anti-bot systems bind a session to the address issued it.

### ★★ Recovery rescues the WORKER. Make sure it also rescues the WORK.

The most expensive class of bug found here is not in the scraping — it is in the code written to
keep the scraping alive. Two instances in one afternoon, both silent:

1. **A run that skipped items reported success.** The "N consecutive failures = stop" guard only
   fires on a *run* of failures. When the assigned range **ended** first, the loop exited and printed
   a clean `DONE`, with real courts never searched and **nothing in state marking them**. *Absent is
   not the same as incomplete*: no resume revisits an item that was never recorded, and no audit of
   `complete` flags can see the hole.
2. **A browser swap resumed at the wrong index.** After replacing a wedged browser the worker rewound
   one step — the item that tripped the limit — and carried on past the four that had failed *before*
   it. The swap saved the session and abandoned its work.

Both were found only by auditing the **union across all workers**, and both had been live for an
entire national sweep.

⇒ **Every recovery path must ask "what did I skip while failing?" and go back for it.** Rewind over
the whole failure run, not the last step. Record skipped items explicitly, exit non-zero, and never
let a partial pass end in a success code.

### ★★ A block is the LAST sign, not the first — learn to see yourself degrading

Every recovery mechanism reacts to a refusal. That is too late, and it need not be: sessions decline
visibly first. Measured on a remote worker (2026-08-13), the decline was legible for **twelve
minutes** before the rejection that ended the run:

| time | signal | lead |
|---|---|---|
| 03:42 | anti-bot interstitial served instead of a document (×2) | **12 min** |
| 03:47 | paginator stalled | 7 min |
| 03:49 | search 75 s → timeout | 5 min |
| 03:50–51 | two "empty" results at 57–59 s | 4 min |
| **03:54** | **hard rejection — run over** | — |

Healthy latency for that site was a **measured** 17–23 s. It ran 45, 57, 59, 75.

**Score the symptoms on a rolling window rather than tripping on any one**, because the site's own
latency varies honestly and a single slow response means nothing. Weight by closeness to an outright
refusal:

```
anti-bot interstitial on a document   2   # this IS a refusal, just not on a search
search timeout / never-proved-fresh   2
search slower than 2x baseline        1   # the trend, never one sample
paginator stall                       1
--- and CLEAR the window on a fast, fresh result ---
```

When it trips, **step back before you are pushed**: cool off and re-enter *pre-emptively*. Re-entry
costs seconds; a hard block costs the recovery budget, and on a cloud runner with one retry it costs
the whole run. Do not charge it to the recovery budget — nothing has refused you yet.

⚠️ **The same score decides what you are allowed to BELIEVE.** An "empty" from a healthy session is
an answer; from a degrading one it is a symptom. On the run above, the worker filed two large courts
as swept-and-empty four minutes before it was blocked — and we already held 26 records from one of
them, so the verdict was provably false. Nothing downstream flags that and a resume skips them for
ever. ⇒ **Record the empty, but only mark it *complete* when the session is clean.**
⇒ Generally: **a scraper's confidence in its own results should be a function of its measured health
at the time it collected them.**

### ⚠️ Stop yourself before the platform stops you

Any hosted runner has a hard ceiling (GitHub: 6 hours, then killed). A kill loses whatever was in
flight *and writes no report*, so the next run cannot tell "the job is finished" from "the last one
was cut off". Give the worker its own **lifespan** below that ceiling: stop cleanly, save state,
record where it got to, exit with a distinct code. A hard kill becomes a handover.

And when chaining runs, **continue on the WORK, not on a hop count.** A fixed number of continuations
either stops with the job half-done or keeps firing at a finished one, because it never looks at what
happened. Have each run write a verdict — finished / reason / stopped-at / blocks — into state the
next run reads, and continue while work remains *and* failures stay in range. Keep a hard hop bound
anyway, as the backstop against a bug in that logic.

## IV.5 Running it unattended

**⚠️ Long runs must be launched DETACHED.** A background task started from an agent harness is killed
after roughly **30 minutes**. This was misdiagnosed as a WAF block, a hang and a browser wedge on
separate occasions; one census "stalled overnight" at 208/230 and sixteen hours of a warm profile
were wasted looking for the cause in the anti-bot system.

⇒ Use a launcher that reparents the process (`Start-Process` on Windows) and writes to a **log file**
rather than a pipe. **Diagnose a "stuck" run by whether the log file is advancing**, never by whether
a wrapper is still attached. Publish the healthy rhythm so long idle gaps are not mistaken for a hang.

**Supervise, with judgement.** An hourly supervisor that ingests, checks liveness and restarts the
dead is worth building — a job died twice in one day and each time sat idle until a human looked,
once for 19 hours. Encode these judgements explicitly:

- **Liveness is the process, not the log age — but evidence of life wins.** An unreadable process
  list is ignorance, not death. (A `CommandLine` scan returns **empty** when run from a different
  session or elevation than the target, so a supervisor that trusted it declared all four workers
  dead and started duplicates: two processes writing one state file.)
- **A running-but-silent worker is reported, never killed.** A wrongly-killed job costs more than a
  late warning.
- **Cap restarts** (e.g. 4 without progress) so a problem needing a human cannot become an hourly
  relaunch loop. Any progress resets the budget.
- **Ignore a stale lock rather than obeying it**, or one crash stops maintenance forever.
- ⚠️ **Match the process precisely.** `ingest_worker_a.py` contains the substring `worker_a.py`, so a
  naive match counts the supervisor's own ingest child as a worker — a false "5 of 4 alive", and
  worse, it would read *3 workers + 1 ingest* as a healthy 4 and stay silent through a real death.

**⚠️ A worker's log format is not an interface — but supervisors will treat it as one.** Measured
2026-08-13: a supervisor checked the **last three lines** for `DONE.`. The worker then gained two
closing lines, pushing `DONE.` out of that window — so the supervisor could no longer see a finished
slot and **restarted it every hour, ten times overnight**, each restart launching a browser, walking
into the site, searching, finding nothing and exiting. **Ten pointless arrivals at a site that scores
arrivals**, and it would have continued indefinitely. Nothing errored; the logs even said `DONE.`
every time.

⇒ **Have the worker write a structured verdict — `finished`, `reason`, `stopped_at` — into the state
file, and have supervisors read THAT.** State is an interface; prose is not.
⇒ **When you change what a worker prints, grep the repo for anything that reads it.** The coupling is
invisible from the worker's side.

**⚠️ Rotate logs, never truncate them.** Redirecting stdout to an existing log truncates it,
destroying the very lines that say why the previous run died. Truncation also leaves NUL bytes, which
make `grep` treat the file as binary and go silent, so monitors stop reporting too.

**⚠️ Own your browser, and take it with you.** Close it on every exit path, via `atexit`. An abandoned
browser holds its profile and its debugging port, and **a listening port is exactly how a supervisor
decides a slot still has a usable browser** — so an orphan actively misleads it. ⚠️ Do not trust the
spawned process handle: Chrome routinely re-launches itself into a new process and lets the original
exit, so `poll()` reports "already gone" while a full browser is still running. Kill the tree you know
about, **then** sweep for anything still holding your profile directory.

**⚠️ Hosted CI — four traps that have each destroyed real work here** (GitHub Actions, PJUD, 2026-08):

- **A concurrency group holds exactly ONE pending run.** `cancel-in-progress: false` protects the run
  that is *executing* and says nothing about the one waiting; dispatch a third and the queued one is
  **silently cancelled**. ⇒ **To run N things in sequence, make them N JOBS IN ONE RUN**, chained with
  `needs:` — jobs queue properly and each still gets its own machine, IP and full timeout.
- **`if: success()` on a chained measurement queue throws away the rest of the night.** A blocked or
  refused test is a *result* — often the one you queued it for. Use `if: !cancelled()`.
- **A step's exit code is the LAST command's.** `python … | tee` reports tee's status, so a traceback
  exits 0 and the job goes green having measured nothing. **`set -o pipefail`, every time.** Same
  family as `|| echo "…"`, which once made a failed ingest look successful and lost 431 MB of PDFs.
- **Validate the YAML before dispatching.** `run: echo "public IP: $(…)"` is a parse error — a plain
  YAML scalar may not contain `": "` — and you find out at dispatch, after queueing behind a five-hour
  job. One `yaml.safe_load` catches it in a second.

**Encoding will bite you on Windows.** Python takes stdout's encoding from the locale (cp1252 here),
so anything outside Latin-1 raises `UnicodeEncodeError` **mid-print**. Force UTF-8 with
`errors="replace"` at startup. Keep `argparse` help strings **ASCII** — a `%` in them must be escaped
as `%%` or `--help` itself raises, and **that includes `description=__doc__`**, which is where the
arrows and ⚠️ live. PowerShell adds its own: Task Scheduler runs PowerShell 5.1, which reads `.ps1` as
ANSI without a **UTF-8 BOM** and then fails to parse any accented character, and 5.1's `Tee-Object`
writes UTF-16. **Test scripts the way the scheduler runs them.**

**Scheduled tasks have conditions you did not set.** A Windows Scheduled Task defaults to
`DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries`; on a laptop the supervisor silently neither
starts nor survives.

**Cron against a broken scraper is a liability.** A daily workflow that could not possibly work fired
17 failing jobs a day for about thirteen days before anyone noticed. **Make scheduled scraping opt-in
and prove it by hand first**, and disable known-dead workflows rather than leaving them dispatchable.

## IV.6 Seeing what a worker is doing

A worker on another machine has no screen. Four different questions, four instruments:

| question | instrument |
|---|---|
| *what killed it* | screenshots + page state, on failure paths only |
| *what is it doing right now* | a live card, pushed through the database |
| *how did it get there* | a frame **before and after every action**, plus one contact sheet |
| *single-step it* | block before each action and wait for a verdict through a side channel |

★★★ **The interesting frame is never the last one** — and the channel that carries a frame *out* can
carry an instruction *back*, which is how single-stepping got built.
★★ **A worker you cannot see needs a WINDOW, not just a black-box recorder.**
⚠️ **Chokepoint instrumentation has exactly the coverage of your chokepoint**, and **a measuring tool
has exactly the coverage of its glob.**
⚠️ **Watch the channel where failure actually speaks** — it is often not stdout.

---
---

# BOOK V — MEASURE (probe discipline)

The part most often skipped, and the part that most often costs the day.

## V.1 The discipline

- **One variable.** A run that differs in three ways is not a control. Window, range and pace all
  changed in one PJUD comparison; that was enough to refute a fixed ceiling and not enough to name a
  cause.
- ★★★ **Check that the arms match before you read the number.** Bitten repeatedly.
- **Take the verdict from the network response**, not from the page.
- **Carry a canary** — a known-good item that proves the instrument still works.
- ⚠️ **A probe must obey the same gate as the worker.** A diagnostic that took the first N rows off
  the results page spent four expensive opens on record types the project does not collect, and
  **the evidence it produced was about the wrong population** — every "look, there are several of
  these!" observation came from out-of-scope records; the in-scope ones had at most one. **Reuse the
  worker's own selection function, not a fresh approximation of it.**
- ⚠️ **A "dry run" must be proven inert before you point it at production.**
- ★★★ **Ask the data you already hold before you ask the site.** The cheapest measurement is the one
  already in the database.

## V.2 ★★ Do not invent a property of the target to explain your own results

The default explanation for a strange result is **your own code**. On PJUD, a supposed per-session
budget, a supposed coordinated cull, a supposed uplink limit and most "blocks" of one whole afternoon
were all ours.

The worked example is worth the space. Six sessions clustering at 73–85 opens looked exactly like a
quota. Once the *blocked* runs were compared **against each other** instead of against the one that
fit:

| run | open gap | searches | opens | pdf bytes | life | outcome |
|---|---|---|---|---|---|---|
| solo control | 25 s | 8 | 77 | **136.5 MB** | 68 min | blocked |
| — | 25 s | 2 | 77 | **62.6 MB** | — | blocked |
| — | 25 s | 3 | 85 | 80.2 MB | — | blocked |
| — | 25 s | 3 | 74 | 69.8 MB | 70 min | blocked |
| the fast run | **8 s** | 8 | **221** | **179 MB** | **131 min** | clean — stopped by hand |

Every candidate dies on this table. **Opens**: 74–85 blocked, 221 clean. **Bytes**: blocked at
62.6 MB, clean at 179 MB — and the blocked runs alone span a **4× spread**. **Elapsed**: 68–70 vs
131 min. **Searches**: 2–8 in *both* groups.

⚠️ Note what the blocked column proves **by itself**: two refusals, one at 62.6 MB and one at
136.5 MB. **A byte ceiling was refuted by the failures alone**, and an evening went into "confirming"
one from a single close pair (136.5 vs 125 MB) picked out of that spread. **A wide spread contains a
convincing pair for almost any hypothesis.**

The traps, all of which fired at once:

- **A cluster is not a quota.** Runs sharing a pace *and* a bug run down together. Six agreeing
  numbers are one measurement repeated, not six.
- **Compare the failures with each other, not with the one success.**
- **The counter you are hunting may not exist.** Before modelling the target's budget, diff your own
  code against the run timestamps — **then check the suspect code actually RAN.** A commit landing
  between a failure and a success is a coincidence until a log line proves execution. One `grep -c`
  showed the suspect fallback fired **zero times in five blocked runs**; it was dead code in every one.
- ⚠️ **"They failed together" does not imply "they caused each other to fail".** Three sessions started
  within three minutes, each spending an identical allowance at an identical rate, **arrive at zero
  together**. Simultaneous deaths were never evidence of coordination — they were evidence of
  identical clocks started together. Without a solo control you cannot tell a shared ceiling from a
  per-session budget, and every remedy for the first is wasted against the second. Three trials and
  two days went into a conclusion one control run reversed.

## V.3 ⚠️ A constant measured locally is not measured remotely

Caught twice. A timing, a threshold or a pause tuned on one machine is a property of *that machine's*
latency and *that machine's* idle behaviour. **A runner is a different environment, so every number
measured elsewhere is unmeasured there.**

⚠️ **And replacing a tuned constant with a condition buys nothing where it was tuned.** Two flat
sleeps were replaced with real conditions; the arithmetic predicted 20%. Measured after: **identical
throughput, to two decimal places** — a condition exits when a well-chosen constant expires.
⇒ That does not make the change wrong: the old check verified the *control* had moved but never that
the *content* had, so a slower link would have filed the wrong data with no error. **The gain is
adaptivity and correctness, not speed** — and "this made it faster" is a claim you must measure.
⇒ ⚠️ **Beware the validating sample.** A 25-record check on a single container showed a 32% gain that
vanished at full scale, because it skipped the per-container work that dominates the average.
**Validate a per-item change on a sample that includes everything the item is embedded in.**

## V.4 ⚠️ Rate and CONCURRENCY are confounded in every "add workers" experiment

Adding workers moves requests-per-minute **and** simultaneous sessions together. **No experiment in
this repo has separated them.** So:

- "8 workers trips it" is **not** established. Only *"8 workers at 46/min"* is.
- ⇒ The experiment that separates them is **N workers paced to a 1-worker aggregate rate**, on a
  fresh address.
- ⚠️ **A shared limit looks exactly like a coordinated cull.**
- ⚠️ **An endpoint's reputation has a DATE and a DOSE on it.** "That endpoint is dangerous" without
  both is not a finding.
- ★ **"We get blocked" and "how fast can we go" are separate questions, and answering one does not
  answer the other.** Test them separately or you will attribute a concurrency limit to speed,
  throttle yourself for months, and never find out. (PJUD ran remote workers at half the achievable
  throughput for weeks on an inherited local number nobody had re-measured.)

## V.5 ★★★★★ Your block detector probably tests ARRIVAL, not the address

A cheap health check — open a fresh browser, walk in, look for the control you need — is the only
reliable way to tell a block from a site change, and it works. Then a four-session fleet ran to
**normal completion**: no refusals, no errors, every session finishing on its own work. **Fourteen
seconds later the health check was refused.** (Repeated at eight workers: **eighteen seconds**.)

⇒ ★ **The check opens a NEW session, so it answers "can a new arrival get in?" — not "does this
address still work?"** Established sessions may carry straight through a block that turns away every
newcomer, and on this evidence they did.

- **Report it as what it measures.** "Arrivals are refused" is supportable; "the address is dead" is
  not — and the two lead to different decisions: one says stop *starting* workers, the other says stop
  *working*.
- **If you need to know whether existing sessions still work, ask an existing one.** A fresh browser
  cannot answer that, however carefully you build it.
- ⚠️ **A fleet can be inside a block without knowing it.** That is how "the run looked healthy" and
  "we were blocked" end up both being true.

## V.6 ★★★★★ A block can be a PAGE THAT LOOKS FINE — only a second address can tell you

A scraper stopped working. The browser was attached to and inspected: the page open, titled correctly,
fully styled, carousel rotating, menu drawn. It was simply missing the one control the scraper needed.
That was read as "they redeployed and our selectors are stale", and **eight hours of evidence were
consistent with it**. Then the operator opened the same site **on a phone** and it worked instantly.

```
blocked address   page renders perfectly, form ABSENT, no error, no captcha, HTTP 200
clean address     identical URL, form present, works immediately
```

⚠️⚠️ **"The page looks fine" is not evidence that you are not blocked.** The absence of a rejection
page is not the absence of a block. A modern WAF can answer 200 with a page that is complete,
interactive and quietly missing the control you need — indistinguishable from a redesign if you only
ever look from one address.

⇒ **The only reliable test is a SECOND ADDRESS.** Content, status, timing and retry behaviour are all
consistent with both explanations. A phone on mobile data settled in thirty seconds what eight hours
of local evidence could not.
⇒ **Build the block test into your tooling.** A two-page-load check asking "is the control I need
present?" is a block detector, not just a health check. Run it **before** an experiment so a degraded
start is not read as a result, and **after** so a trip is caught in one check.
⇒ ★ **Note the asymmetry.** Inferring a block from a **failure** was correct. Inferring no-block from
an **appearance** was wrong. Failures are evidence about the world; appearances are evidence about
what the other side chose to show you.

## V.7 ★★★★★ Split the scraper in two: SPECS and SETTINGS

```
SPECS      how human the worker is       one shared engine   ALWAYS THE BEST YOU HAVE
SETTINGS   what job it does, and where   the workers         chosen per run
```

The most useful architectural line this project has drawn, and it took four workers and two months of
divergence to find. **A fidelity fix that lives in a worker protects one worker.** Four workers meant
four behavioural engines, silently drifting apart because nobody diffs four files against each other.
Three months after the newest was rebuilt from a recorded human session, the other three were still:

```
typing into `readonly` input fields          (an act no user can perform)
driving every dropdown with ~54 keystrokes   (the recorded human emitted ZERO all session)
emitting no pointer motion between clicks    (the human: 25.8 moves/s on 98% of seconds)
never scrolling horizontally                 (so a wide table's right-hand column was unreachable)
```

And the day this was noticed, the *discovery* pass — the job that must visit pages it has never seen —
was running on the least human worker of the four.

- **Enumerate the acts, then grep every worker for each one.** One table settled it: dates, selects,
  pointer presence, sideways scroll. Four rows, four columns, obvious the moment it was written down
  and invisible before.
- **The engine must not import a worker.** A constant that looked worker-owned (`CIVIL = "3"`) was a
  property of the *site*.
- ⚠️ **A module-level global is part of the facility.** Moving a function without moving who *writes*
  its global leaves the worker setting, printing, ramping and reporting a value nothing reads — and
  the log line reporting it reads the wrong copy, so nothing ever says so.
- ⚠️ **Setting a spec on the worker instead of the engine is the same bug, one layer in.** The moment
  two workers can disagree about how human they are, no experiment on either means anything.
- ⚠️ **Every number in the engine may rest on n=1.** Say so beside it.

## V.8 ★★ Simulate a scheduler offline before you measure it live

The duty-cycle fix shipped at **1.86 stops/min and 19% silent** against a 59% target. Two diagnoses
were guessed from the output; both were wrong. The third attempt logged **what was actually drawn**,
turning the question into a subtraction:

```
drawn, in-run   n=11 over 5.9 min   mean  6.2 s   median 2.0 s   max 36.6 s
drawn, offline  n=166               mean 12.3 s   median 6.7 s   max 59.8 s
operator        n=129 over 40 min   mean 10.9 s   median 6.1 s   max 60.4 s
```

The sampler was **fine**. The deficit was entirely in **how often it was called** — the probability
was evaluated only at call sites that bracketed reads and record loads, so searches, form building,
navigation, ingest and modal closes had probability **zero**. 3.23 per *covered* minute arrived as
1.86 per *wall* minute (I.4, third occurrence).

⚠️ **It bit a FOURTH time, one line into the fix.** Re-arming the deadline *after* each stop means the
gap only elapses while working, so its mean must be the mean **active** stretch, not the mean wall
interval:

```
expovariate(SILENCE_PER_MIN / 60)  -> mean gap 18.6 s -> 2.04 stops per WALL min   WRONG
expovariate(1 / 7.6)               -> mean gap  7.6 s -> 3.24 stops per WALL min   right
```

⇒ **Simulate offline before measuring live.** A fake `time.monotonic` and a fake `wait_for_timeout`
took ten minutes and caught the fourth error, which would otherwise have shipped the identical
shortfall in a new costume and looked like a fresh mystery. The same harness made **boundary density
a visible parameter instead of a hidden one**.
⇒ **Log what a random draw PRODUCED, not just its effect.** "Why is the output short?" is a guess;
"the draws match the operator but the output does not" is a subtraction. Two runs were spent reasoning
about a mechanism one logged list settled.
⚠️ **Do not read a mean off a heavy tail with n=25.** A post-fix mean of 7.7 s against an expected
11.1 s looked like residual truncation and was not: 20,000 bootstrap samples put 7.7 s at the 9th
percentile of what n=25 produces, and the whole deficit was that no draw landed in the top decile — a
7.2% event. **The median, robust to that tail, was 6.4 s against the operator's 6.1 s.** Judge a
heavy-tailed spec by its median, or budget enough draws to see the tail.

## V.9 ★★★★★ The dangerous variable may be set by the DATA, not by your configuration

Two runs of one scraper, an hour apart. Identical code, pacing flags, worker count and address. One
ran clean; the other lost six of eight sessions in ten minutes, all within thirteen seconds.

```
dense window    52.9 requests/min total,  3.0 SEARCHES/min   -> clean
sparse window   21.3 requests/min total, 11.6 SEARCHES/min   -> six sessions dead
```

**The run that died was making 40% of the total requests of the run that lived.** The difference was
the request MIX, and nothing chose that mix: on a dense window a search returns a page full of records
and the worker spends minutes reading them, so searches space themselves. On a sparse one the search
returns nothing and the worker immediately searches again. Same code, same constants, four times the
search rate — **decided entirely by how much the target happened to hold.**

⚠️ **A fresh, unharvested window is more dangerous than a picked-over one** — the opposite of the
intuition that new territory is safe because nobody has touched it.

⇒ **Rate-limit the expensive ENDPOINT, not the aggregate.** Cheap requests dilute the average and hide
the one that counts.
⇒ **Know which of your numbers is load-bearing before you need it.** The monitoring tool printed the
search rate on its own line and flagged it correctly; the headline total sat in the healthy band. The
instrument was right and the wrong line was being read.
⇒ **When several sessions with very unequal progress die within seconds of each other, it is the
address, not the session.** (An earlier trial had four shards die within 18 seconds holding **74, 16,
2 and 38** requests. No per-session budget produces that, and the pattern still has no account.)

⚠️⚠️ **CORRECTION, ninety minutes later: the causal claim is SUSPENDED.** Attaching to the browser
showed the landing page had been **redeployed**. A deployment mid-experiment explains six simultaneous
deaths better than a rate limit, and the two arms were separated by ninety minutes as well as by
window. The measurements are real; the cause is not established. (See I.9 for the lesson that survives
either way.)

## V.10 ⚠️ Sequencing is a variable — hold it or randomise it

A ladder of 1 → 4 → 8 workers run back-to-back on one address tripped at the 4-worker rung, which
reads like a clean answer: four is too many. **It is not an answer at all.** The address had absorbed
**~2,700 record opens in under two hours** across all rungs, and every rung inherits the debt of the
ones before it. The 4-worker rung was simply holding the parcel when the music stopped.

⇒ **Rotate the address, or cool off, BETWEEN rungs of any escalating experiment.** Otherwise the
variable you are escalating is confounded with cumulative load — **and the confound always points at
the largest setting, which is exactly the answer you were half-expecting.**
⇒ **Re-baseline after a rotation.** A new address is a new history, not a reset of the old one.
⇒ Same shape as comparing two arms separated by time and reading the difference as their variable.

## V.11 Small-sample traps, collected

- ⚠️ **Three rows is not a sample.** (I.8)
- ⚠️ **A sample maximum is not a maximum.** (III.7)
- ⚠️ **A validating sample that skips the surrounding work measures the wrong thing.** (V.3)
- ⚠️ **A heavy tail needs a median, or enough draws to see the tail.** (V.8)
- ⚠️ **A wide spread contains a convincing pair for any hypothesis.** (V.2)
- ⚠️ **A mechanical insertion is not safe because it compiles — watch the ORPHANED TAIL.** Inserting a
  function *above* an existing body left that body's last line at function-body indentation inside the
  **new** function, where it ran unconditionally — so every search wait was **double length**. It
  compiled, it ran, and it silently halved throughput while the run looked healthy. This is the third
  defect here from a bulk or positional edit. ⇒ **After inserting a function, read the diff asking what
  the line AFTER it now belongs to.** `git diff` shows the insertion; only reading it shows the
  absorption.
- ⚠️ **A fallback for a name you invented manufactures success.**
- ⚠️ **"Bring it up to date" is two jobs**, and the completion worker cannot do the first.

---
---

# BOOK VI — THE REGISTERS

Append-only ledgers. This is what makes the library a container: anything that does not fit a
lifecycle stage still has a home.

## VI.1 Measurement register

| date | target | measurement | n | confidence |
|---|---|---|---|---|
| 2026-07-21 | PJUD | `el.value=` + synthetic change: search succeeds *once*, the **next** request is refused | 1 | measured |
| 2026-07-22 | PJUD | pointer **motion** is scored, not `isTrusted` — 250 B rejection → 109,234 B of results | 1 | measured, load-bearing |
| 2026-07-22 | PJUD | `Runtime.evaluate` over CDP is innocent | 1 | measured |
| 2026-07-23 | PJUD | keyboard + scrolling fixed: gaps 60→20 s and 90→25 s, **3× throughput**; 730 opens/day | — | measured |
| 2026-08-05 | PJUD | both block detectors matched only English; blind for an hour | 1 | measured |
| 2026-08-10 | PJUD | metronome keys drew a tier-3 CAPTCHA on the **first** search — no rate involved | 1 | measured |
| 2026-08-10 | PJUD | pacing probe: 45→4 s search, 90→8 s open, never tripped; floor ~15 s (site latency 12–26 s) | 51+18 | measured |
| 2026-08-11 | PJUD | headless: entry failed at 102 s; headed under Xvfb: 232 courts, results | 1 | measured, load-bearing |
| 2026-08-12 | PJUD | wedged session: 180 s cool-off + clean re-entry failed; replacement browser worked first search | 4 | measured |
| 2026-08-12 | PJUD | four local workers ≈ 1.75 result req/min — about what one produces | 1 | measured |
| 2026-08-12 | PJUD | remote cycle floors at ~28 s from gap 13 s down; 10% active | 36 | measured |
| 2026-08-13 | PJUD | 3 remote shards each get a full allowance (77 / 147 / 216 opens); 4 collapse | 1 | measured, single trial |
| 2026-08-13 | PJUD | degradation legible **12 min** before the refusal | 1 | measured |
| 2026-08-14 | PJUD | pointer over the table: 0 → 12 mouseover per identical scroll | 1 | measured |
| 2026-08-16 | PJUD | operator emits 25.8 mousemove/s on 98% of seconds; **zero** keydowns all session | 1 | measured (40 min) |
| 2026-08-17 | PJUD | mimic worker: 1,046 opens / 150 min / zero blocks | 1 | measured |
| 2026-08-19 | PJUD | scraper 19.5 events/**wall** s vs human 11.6 — **68% more**, at 84% per *active* second | 1 | measured, load-bearing |
| 2026-08-19 | PJUD | operator duty cycle: 3.23 stops/min, 54% silent, median stop 6.1 s, max 60 s | 129 stops | measured |
| 2026-08-19 | PJUD | duty cycle costs **−54%** throughput (2.66 → 1.23 opens/min); benefit **unmeasured** | 1 | cost measured only |
| 2026-08-19 | PJUD | one recorded session revealed 4 endpoints absent from the codebase; the largest 5:1 vs ours | 1 | measured, load-bearing |
| 2026-08-20 | PJUD | one worker's floor 8.6–9.0 s/open = 6.7–7.0 opens/min — the **site's** floor | — | measured |
| 2026-08-20 | PJUD | `--focus fast`: +8% alone, and it **shrinks** the duty cycle to 16% silent | 1 | measured |
| 2026-08-20 | PJUD | blocked address serves a perfect page with the form removed; 8+ hours | 1 | measured, load-bearing |
| 2026-08-20 | PJUD | 4 workers: 28.47 opens/min, 1,023 opens, zero trouble | 1 | measured |
| 2026-08-20 | PJUD | solo: 3 h, 1,129 opens at 6.37/min, address clean either side | 1 | measured |
| 2026-08-20 | PJUD | dense vs sparse window: 3.0 vs 11.6 **searches**/min at 52.9 vs 21.3 total req/min | 2 | measured; cause suspended |
| 2026-08-21 | PJUD | 8 workers, virgin address: 50.06 opens/min, 1,385 opens, zero trouble, refused at 30.5 min | 1 | measured |
| 2026-08-21 | PJUD | 4 → 8 workers returns **1.76×** — first measured contention | 1 | measured |
| 2026-08-21 | PJUD | opens-per-court vs s/open: **r = −0.814** | 8 shards | measured |
| 2026-08-21 | PJUD | the record run sat at **0.51 GB free** | 1 | measured |
| 2026-08-21 | PJUD | arrivals refused **18 s** after a clean fleet finished | 1 | measured |
| 2026-08-21 | PJUD | corpus 6,477 causas / 6,307 historias / 4,387 documents | — | counted in Neon |

## VI.2 Overturned claims

Kept, struck, with what replaced them. **Do not rebuild these.**

| struck | date | what replaced it |
|---|---|---|
| ~~"The second search of a session is refused / the token is single-use / beacons must be fresh / the budget is elapsed time."~~ | 2026-07-22 | all four were the pointer bug |
| ~~"A blocked profile must be rotated."~~ | 2026-08-12 | re-entry clears a tier-2 block in ~18 s; rotation throws away a warm session |
| ~~"There is a fixed per-session budget (~70–85 opens)."~~ | 2026-08-13 | our own bug; the blocked runs refute it among themselves |
| ~~"Sharding buys nothing; parallelism only works locally."~~ | 2026-08-13 | 3 remote shards each get a full allowance |
| ~~"Concurrent runners are culled as a group; remote means one worker."~~ | 2026-08-13 | identical clocks started together arrive at zero together |
| ~~"Idle mousemove was tested and bought nothing."~~ | 2026-08-16 | tested at 1/26th of a hand — evidence about 4%, not about the channel |
| ~~"Readonly inputs: unlock the property, then type."~~ | 2026-08-16 | use the widget; the operator cannot type there |
| ~~"Arrow keys, never `select_option`."~~ | 2026-08-16 | our invention — the recorded human pressed zero keys |
| ~~"The datepicker shows only 16 days because the site refuses future dates."~~ | 2026-08-16 → 08-18 | it draws all 31 and **disables** the refused ones. Both earlier claims were half right |
| ~~"It is the concurrent SESSIONS, not the rate."~~ | 2026-08-17 | superseded by aggregate-rate-per-address, itself now suspended |
| ~~"The binding limit is the aggregate REQUEST RATE per address."~~ | 2026-08-19 | the test moved `--speed`, which moved the rate **and** the pointer |
| ~~"Matching the duty cycle is worth halving throughput for."~~ | 2026-08-19 | cost measured, benefit never |
| ~~"56 req/min kills, 23 is safe."~~ | 2026-08-20 | properties of a **build**, not the site — one flag gave 27 and 56 on different dates |
| ~~"The site was down."~~ | 2026-08-20 | the address was blocked, 8+ hours, serving a page that looked fine |
| ~~"`--speed 0` is the fastest result."~~ | 2026-08-20 | it is the fastest **setting** (I.7) |
| ~~"It is the SEARCH rate that binds."~~ | 2026-08-20 | suspended: the landing page had been redeployed mid-experiment |
| ~~"The 8-worker slowdown is this house's uplink."~~ | 2026-08-21 | court density — r = −0.814 (I.5) |
| ~~"The warm-up ritual is real."~~ | — | an overlay was covering the entry button |

## VI.3 Negative results — tried, did nothing

- **Cutting the read pause to a tenth**: no measurable gain. (I.7)
- **Replacing two tuned constants with conditions**, in the place they were tuned: identical
  throughput to two decimals. Right for correctness, worth nothing for speed. (V.3)
- **Condition-based waits, locally**: bought nothing — correct, because locally there was nothing to
  wait for.
- **Tremor as the scored mechanism**: not it, already measured. Vibration crosses no element
  boundaries and generates zero `mouseover`. (III.2)
- **Removing `.focus()` teleporting into a dropdown**: a genuine tell, and its removal did **not** fix
  the failure being chased. Remove it anyway, and record that it was not the cause.
- **Gap 8 s and 6 s on a remote worker**: buy nothing over 13 s, and 8 s is marginally worse.

## VI.4 Open questions

1. **What actually causes the block?** Rate, concurrency, or search rate? All confounded (V.4). The
   experiment: **N workers paced to a 1-worker aggregate rate**, on a fresh address.
2. **Does any spec reduce blocks?** The survival column is empty for every configuration. No run has
   ever compared block rates between two spec configurations.
3. **What is the survival envelope as a function of rate?** Two points only: 6.37/min survived 3 h;
   46/min survived 30.5 min.
4. **How much unswept territory is left?** Delivery is bounded by it (I.3), and it is the only
   variable with a proven effect on the actual goal.
5. **Does the block escalate with repetition on the same address?**
6. **Unexplained and recorded as such:** four shards died within 18 seconds holding **74, 16, 2 and
   38** requests. Wildly unequal work, identical death time. No model here produces that.

## VI.5 Traps register

The ones that cost a real afternoon and are nobody's obvious fault.

- A modal reused per record hands you the **previous** record's contents — and one md5 pass over the
  downloads finds it in seconds. Identical bytes under two ids is nearly always staleness.
- A folder modal that is one global element files one record's documents under another.
- A nested modal's backdrop is not the outer modal's backdrop; Bootstrap **stacks** them.
- A tab that is "active" in the nav but not in the panes **cannot be clicked**.
- After a paginated redraw, row indices are stale before they are wrong.
- A datepicker that *draws* the days it refuses and merely disables them.
- A datepicker header that lies in two opposite directions depending on how you read it.
- A stuck modal looks exactly like a block.
- `select_option`'s default timeout is 30 s of silence.
- PowerShell splits an `-ArgumentList` element on its spaces.
- `Get-Date -Format "dd/MM/yyyy"` returns `08-08-2026` under a non-en locale.
- A literal `%` in an argparse help string only crashes `--help` — including via `description=__doc__`.
- Duplicate detectors go blind together — keep **one** implementation.
- Your instrumentation will lie to you more often than your scraper does.

## VI.6 Tool register — which question each answers

Generic shape; the concrete scripts live under `pjud/scraper/`.

| question | instrument |
|---|---|
| is the target up, and what does it serve? | a check that clicks through and stops before the scarce act. ⚠️ it measures **arrival** (V.5) |
| are we blocked, or did they redeploy? | **a second address.** Nothing else answers it (V.6) |
| what rate is the fleet making right now? | a log-derived rate watcher — read the *expensive-endpoint* line, not the total (V.9) |
| how did this arm score? | a scorer run **before** the ingest, or it counts its own records as already held |
| what do we emit vs a human? | a profiler reporting per-**wall** second and the silent fraction (I.4) |
| did the data actually land? | a dry-run ingest, then count where it is meant to end up (I.3) |
| what is it doing right now / how did it get there / single-step it | IV.6 |
| how many workers can this address carry? | the ladder — per-worker work held constant (IV.3) |
| what is a spec setting worth? | a matrix over the spec axes, one variable at a time (V.1) |

## VI.7 Session log

One line per day that produced knowledge. Detail stays in the project handoffs.

| date | what it produced |
|---|---|
| 2026-07-20/21 | the "burn budget" — later suspect, then dismantled |
| 2026-07-22 | the pointer finding, and four theories deleted with it |
| 2026-07-23 | the paginator was losing most of every court; the per-IP limit is a rate |
| 2026-08-05 | both block detectors were blind: the rejection page is in Spanish |
| 2026-08-06 | most blocks were self-inflicted; two whole tabs were never read |
| 2026-08-07 | three things that looked like blocks and were not |
| 2026-08-11 | headless loses; a CI runner IP is not refused at the door |
| 2026-08-13 | sharding overturned; the fallback that killed a worker; degradation is legible |
| 2026-08-14 | the site moved its door; `locate()`; hit-test overlays; the unsuppressible-channel question |
| 2026-08-16 | the operator was recorded: readonly dates, zero keystrokes, the duty cycle |
| 2026-08-17 | every "block" that afternoon was ours; sideways scrolling; what guards RETURN |
| 2026-08-18 | single-stepping a remote worker; a per-item deterministic refusal; drawn ≠ selectable |
| 2026-08-19 | the anexos document class; SPECS vs SETTINGS; the duty cycle priced at −54% |
| 2026-08-20 | the block is a degraded page; rungs 1 and 4; the site was never down |
| 2026-08-21 | rung 8 on a virgin address — 50 opens/min, contention at 8, court density, the RAM guard |
| 2026-08-24 | this library |

---
---

# APPENDIX A — Source map

Where each part of this library came from. **Nothing was moved or deleted**; the sources remain
authoritative for their own material and hold the reasoning, the near-misses and the exact wording of
what was observed.

| here | drawn from |
|---|---|
| Book I | `../SCRAPERS_HANDBOOK.md` Part 0 · `CLAUDE.md` |
| Book II — PJUD | `pjud/HANDOFF_WORKERS.md` · `pjud/HANDOFF_CDP.md` · `pjud/HANDOFF_PC2.md` · `pjud/README.md` |
| Book II — HDI | `cias/HDI-Ruts-Scraper/README.md` (sibling project, outside this repo tree) |
| Book II — patentechile | `scraper/patente_browser.py`, `scraper/enrich_patentes_local.py` |
| Book II — JPL | `scraper/run.py` |
| Book III | handbook Parts 1, 2, 3, 7, 8 |
| Book IV | handbook Parts 4, 5, 6, 9 |
| Book V | handbook Part 10 |
| VI.1–VI.5 | `pjud/HANDOFF_WORKERS.md` §00 and its dated sections; the handbook's struck entries |
| VI.6 | `pjud/README.md` measurement tables |
| history only, superseded | `pjud/HANDOFF.md` (Sheets/headless/cron) · `HANDOFF.md` (repo/deploy) |

# APPENDIX B — Checklist for a new scraper

```
[ ] THE ONE RULE: nothing a human could not do, or would not do. Re-read Book I when stuck.
[ ] Write the goal as records/hour BEFORE writing code. If it can be scored offline, it is wrong.
[ ] Copy the blank Book II form and fill in what you know. The gaps are your work-list.
[ ] What defends this site? behavioural scoring / CDN challenge / auth only / nothing. KNOW WHICH
    PROBLEM YOU HAVE — the right move for one is the wrong move for another.
[ ] Launch a REAL browser yourself; attach over CDP. Persistent profile, one dir per worker. Headed.
[ ] Human at the gate: log in or solve the challenge by hand, with NOTHING attached.
[ ] Probe what THIS machine is offered. Entry routes differ by environment; do not generalise.
[ ] WATCH A HUMAN USE IT, recording input and network. Then record YOUR scraper the same way and
    diff per WALL second, with the silent fraction beside it.
[ ] Identify the SCARCE act. Harvest everything free around it. Reject at the cheapest decision point.
[ ] Any container reused per record needs a FRESHNESS PROOF. Fail closed; byte-compare your output.
[ ] Input: real keystrokes, correct blur, read the value BACK, drive the widget for readonly fields.
[ ] Pointer: arc + dwell, refuse covered targets, keep it travelling over content during waits.
[ ] locate(): the worker must know WHERE IT IS. "I could not tell" is a state, not an exception.
[ ] Refusal detection: from the RESPONSE, all frames, every language, ONE shared implementation.
[ ] Get a SECOND ADDRESS before you need it. Without one you have no block detector.
[ ] Documents: verify magic bytes, fetch in-page, check the token's lifetime.
[ ] Storage: deterministic IDs, never blanket-upsert, direct file links, confirm date order.
[ ] Pacing: start gentle, then PROBE for the real floor. Jitter every gap. Measure from logs.
[ ] Rate-limit the EXPENSIVE endpoint, not the aggregate — the data sets the mix, not your config.
[ ] Arrival is its own event: gate it on a CONDITION (first real query returns), never a timer.
[ ] Recovery: cool-off for rate verdicts, fresh browser for wedged sessions, stop for CAPTCHAs.
    And go back for whatever you skipped while failing.
[ ] Degradation score on a rolling window — step back before you are pushed.
[ ] Unattended: detached, log-file liveness, rotate logs, structured verdict in STATE not prose,
    own and close your browser. No blind cron.
[ ] Probes: one variable, network verdict, a canary, same gate as the worker, and check the arms match.
[ ] SPECS (how human) in ONE shared engine; SETTINGS (what job) in the workers.
[ ] Guard on the HARM, not on a proxy. Check what your guards RETURN.
[ ] File what you learned HERE, in the same commit as the fix.
```

# APPENDIX C — What this library deliberately does not hold

It is a library, not an archive, and the distinction is what keeps it usable.

- **The reasoning and the near-misses.** The handbook's ~180 entries record *how* each thing was
  found, including the wrong turns — and the wrong turns are half the value, because the shape of a
  mistake repeats after its specifics stop applying. Where an entry here compresses that, the source
  is named.
- **Project runbooks.** Flags, workflows, schemas, how to start worker B on the second machine. That
  is `pjud/`'s job and it belongs there.
- **Anything not yet generalised.** Book II holds one target at real depth and three sketches, because
  nobody has sat down with the other three the way PJUD was measured. That is honest, and the blank
  form in II.0 is where the next one goes.

⚠️ **The maintenance risk this shape carries** is two live copies of one claim drifting apart. The
ingest contract's rule 7 is the mitigation: one copy, edit in place, and when a claim here and a claim
in a source disagree, **the dated one wins and the other gets struck** — never quietly reconciled.
