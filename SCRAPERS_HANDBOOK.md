# The Scraper's Handbook

**What this is:** everything this repo has learned about making scrapers work, extracted from the
three families of scraper living in it. Read it before building a new one, and before "fixing" an
old one — most of what follows was learned by losing a day to it.

**How to read it:** every claim is tied to where and when it was observed. Nothing here is
received wisdom. Where two scrapers disagree, both are recorded, because *which problem you have*
determines which answer is right — and that distinction is the most valuable thing in this file.

---

# Part 0 — THE ONE RULE

> ## A scraper must not do anything a human **could not** do, or **would not** do.

Everything else in this handbook is a corollary. When you are stuck, come back here: in almost
every incident recorded below, the scraper was doing something no person ever does, and the site
noticed.

It is two tests, and you need both.

### "Could not" — physically impossible for a person

| what the scraper did | why no human does it | cost |
|---|---|---|
| `page.click()` teleports the pointer onto a button | a hand moves through space, hovers, then presses | **weeks.** The single biggest bug in this repo |
| typed at exactly 70 ms per key, for dozens of keys | nobody has metronome fingers | a tier-3 CAPTCHA on the *first* search |
| parsed a 100-row table with zero wheel events | you cannot read a long page without scrolling | contributed to the same |
| clicked a button covered by an overlay | you cannot click what you cannot see | wrong actions, correlated with blocks |
| `el.value = x` + a synthetic `change` event | a person's keystrokes make the browser fire the real thing | burned a profile |
| ran headless — no visible surface | a person is looking at a screen | 17 failed jobs/day for ~13 days |
| worked in a background tab | a person looks at the tab they are using | three "blocked" entries that were nothing of the kind |
| fetched documents from outside the browser with copied cookies | a person's requests come *from* their browser | avoided by design |

### "Would not" — possible, but nobody behaves like that

| what the scraper did | why no human does it | cost |
|---|---|---|
| opened six brand-new sessions in the same second | one person opens one browser | five of six never got in |
| fired ~9 requests/min steadily for hours | people pause, read, get distracted | three runners blocked within 14 s |
| paced two workers to the same instant every minute | two people never sync to the second | plausibly killed a 3-worker run |
| re-requested a document already answered "there is none" | you ask once and accept the answer | spends the scarcest budget on a settled question |
| hammered a court that just refused it | a person waits, or gives up | escalating blocks |
| tried to solve a full-page image CAPTCHA | it is an *explicit* request for a human | never attempted — this is a hard stop |

### The corollary that saves you time

**When you get blocked, the first question is not "how do I evade this?" but "what am I doing
that a person wouldn't?"** Every time that question was asked properly here, it produced a fix
that made the scraper *faster*, not slower:

- Fixing the pointer turned a 250 B rejection into 109 KB of results.
- Fixing the keyboard and adding scrolling let the gaps drop from 60 s to 20 s and 90 s to 25 s —
  **3× the throughput** — because the slow pacing had only ever been compensation for behaviour
  that looked wrong.

Gentle pacing is what you reach for when you cannot find the real problem. It hides the symptom,
costs you throughput forever, and leaves the actual tell in place.

### The honest nuance

This is a rule about **what the site can observe**, not a vow of literal-mindedness. Reading the
DOM over CDP was explicitly tested and is invisible; so is having the page itself `fetch()` a
document instead of clicking it — that produces *the same single request the click would have
made*, from the same session, and skips a viewer the user would never have looked at.

And once — on a site with no behavioural scoring but an ad iframe swallowing clicks — the right
move was to call the button's own `el.click()` handler directly, because a *real* click was
landing on an advert and doing nothing. The human's **intent** reached the server; the pantomime
did not.

⇒ Ask what the **server** sees, and whether a person could have produced it. Not whether your
code looks like a puppet show.

---

## ⚠️ Maintenance contract — this file goes stale silently

Documentation about anti-bot behaviour rots faster than code, and a stale scraping doc is worse
than none: it sends you to rebuild a theory that was already disproved. So:

1. **Date every claim.** `(PJUD, 2026-08-12)` is the minimum. An undated claim is unciteable.
2. **When a measurement overturns an entry, do not delete the old one** — strike it and say what
   replaced it. Half the value here is watching a conclusion get overturned, because the *shape*
   of the mistake repeats even when the specifics do not.
3. **Add the negative results.** "We tried X and it did nothing" is the most expensive kind of
   knowledge and the first to be lost.
4. **Update this when a scraper teaches you something**, in the same commit as the fix. If a
   lesson is worth a ⚠️ comment in the code, it is worth a line here.
5. **Distinguish measured from suspected.** Mark speculation as speculation. Several entries below
   are one trial only and say so.

---

## The scrapers this is drawn from

| scraper | target | defence it faces | where |
|---|---|---|---|
| **PJUD** | Oficina Judicial Virtual (Chilean judiciary) | **F5 Shape** — behavioural scoring, per-IP rate budget, 3 escalating block tiers | `felipe/pjud/` |
| **JPL** | Juzgados de Policía Local (municipal ASP.NET sites) | none to speak of; the enemy is fragile ASP.NET postback state | `felipe/scraper/run.py` |
| **patentechile** | vehicle plate lookup | **Cloudflare Turnstile** + AdSense interstitials | `felipe/scraper/patente_browser.py`, `enrich_patentes_local.py` |
| **HDI** | insurer broker cotizador (authenticated) | none; the enemy is an ASP.NET form that must be driven exactly right | `cias/HDI-Ruts-Scraper/` |

Four targets, four completely different failure modes. Do not assume the last scraper's problem.

---

# Part 1 — Choose the browser strategy first

This decision determines everything downstream. Get it wrong and no amount of careful scraping
logic will save you.

### ⚠️ Headless loses to any real anti-bot. Not "is riskier" — loses.

Measured (PJUD, 2026-08-11), same code, same runner, one flag different:

```
headed under Xvfb    entered, 232 tribunales loaded, search returned results
--headless=new       entry failed after 102 s, the form never appeared
```

F5's challenge script tests `document.visibilityState`, and a headless browser has no visible
surface, so the challenge never completes. **This single flag was the entire reason a daily
GitHub Actions workflow failed 17 jobs a day for about thirteen days** while everyone looked for
the problem in the scraping logic. On a headless CI box, run **headed under Xvfb**.

Corollary: a tab opened in the **background** has the same problem. `document.visibilityState` is
`hidden` until you bring it to the front, so a new tab must be focused before it will clear a
challenge (PJUD, 2026-08-09 — three attempts failed as blank pages; the same navigation with the
tab focused cleared in six seconds).

### ⚠️ Letting Playwright *launch* Chrome is itself detectable

Playwright and patchright add automation flags when they launch a browser —
`--disable-blink-features=AutomationControlled`, `--remote-debugging-pipe`, `--no-sandbox`, a pile
of `--disable-features`. **Cloudflare Turnstile loops forever on such a browser**: the "Verify you
are human" checkbox never passes. A normally-launched Chrome — only a debug port and a persistent
profile, exactly like a user's own browser — passes with one human click.
(patentechile, 2026-07.)

**The pattern that works, and is now used by all three families:**

```
1. Launch a REAL chrome.exe yourself (subprocess), with only:
      --remote-debugging-port=<port>  --user-data-dir=<persistent profile>
2. Let a human do whatever must be done by hand (log in, solve a challenge) with
   NOTHING attached.
3. Attach over CDP (connect_over_cdp) only afterwards, to drive the page.
```

Cloudflare only scrutinises the *challenge* page, so once it is solved the attached automation is
invisible on the data pages. The `cf_clearance` cookie persists in the profile, so later runs
usually skip the challenge entirely.

### A persistent profile is not optional

Logins, clearance cookies and anti-bot trust tokens all live in the profile. A fresh profile per
run throws them away and makes every run look like a first visit. Use one profile directory per
concurrent worker, and keep it.

### ⚠️ Attaching over CDP is safe. Reading the DOM is safe.

Explicitly tested (PJUD, 2026-07-22, in one healthy session): `Runtime.evaluate` over CDP — which
is what every `eval_on_selector` / `parse_*` call becomes — is **innocent**. It does not affect
scoring. Only the *input* matters. Do not sacrifice DOM reading in the name of stealth.

---

# Part 2 — Look human where the site is actually measuring

### ★ The single biggest finding in this repo: it is the pointer's MOTION, not `isTrusted`

`page.click()` and `locator.click()` produce `isTrusted=true` events. They still get you blocked,
because they **teleport** the pointer onto the element and fire down+up with no approach path and
no hover dwell. F5 Shape scores the motion.

Measured in ONE healthy session, same button, same POST parameters, minutes apart
(PJUD, 2026-07-22):

```
page.click()            -> 250 B rejection page in 0.1 s
human arc + dwell       -> 109,234 B of real results
```

The fix is `human_click()`: an eased arc with jitter over 18–28 steps, a hover dwell of
140–380 ms, then a press of 55–130 ms. **Never reintroduce a bare `.click()`** on a site that
scores behaviour.

This finding *disproved* four separate theories that had been built on top of the symptom — that
the second search of a session was refused, that the reCAPTCHA token was single-use, that beacons
had to be fresh, that the budget was elapsed session time. All of them were the pointer bug.
**When a fix disproves theories, delete the theories in writing**, or someone rebuilds them.

### The keyboard is scored too

`select_by_kbd` waited exactly 70 ms between every arrow press; `type_date_kbd` typed at exactly
60 ms per character, for dozens of keys. That is the keyboard equivalent of a teleporting pointer.
Measured (PJUD, 2026-08-10) on a session a *human* had just walked into: the whole form cascade
passed, and the very **first** scripted search drew a tier-3 CAPTCHA. One request — no rate
involved. It was never pacing; it was what the input stream looked like.

Real typing is noisy: most gaps cluster in a band, with an occasional long one where a person
glances away. Reproduce both (`_kbd_pause`: gaussian around a base, plus a random long pause every
~9 keys).

### Scroll like a reader

Parsing the DOM directly means the session produces **no wheel telemetry at all** while
"reading" a 100-row table. Emit real wheel events (`human_scroll`) before and during reads.

### ⚠️ Never click a covered target

Driving raw mouse coordinates loses Playwright's actionability check, so if a backdrop or sticky
header covers the point, the press lands on the overlay. Hit-test it yourself with
`document.elementFromPoint` and **refuse to click** if it misses.

Correlation observed (PJUD, 2026-07-22): 0 covered clicks → survived 50 causas; 1 → blocked at 23;
2 → blocked at 4. ⚠️ **Marked NOT CAUSAL** — a later trial broke the correlation. Refusing is
still right, because a click at coordinates where your element is not is simply a wrong action.

Two traps inside the hit test itself, both real:
- **Scroll the candidate you are about to test.** Centring `querySelector`'s *first* match when
  the page has two matching nodes scrolls the invisible one and leaves the real button off-screen.
- **An off-screen point returns `null`**, which reads as "covered". Only hit-test what is in view.

### ⚠️ …and now the counter-example. Know which problem you have.

On **patentechile**, the correct move is the opposite: call the element's own `el.click()` in JS.
The site wires its search via `addEventListener`, and Playwright's coordinate click frequently
lands on an ad iframe and returns **without error**, so the search silently never fires and the
plate looks like "no data". A scripted call invokes the handler directly and is not swallowed by
the ad's click interceptor.

**The rule is not "always simulate a human". It is: identify what the site measures.**
- Behavioural anti-bot (F5, Shape, PerimeterX) → simulate the human precisely.
- No behavioural scoring, but fragile UI (ads, overlays, JS handlers) → drive the handler
  directly and stop worrying about how it looks.

---

# Part 3 — Getting input the site will actually accept

### `fill()` often does not fire the site's own logic

`page.fill()` sets the value and fires a minimal event. Sites that hang their lookup off real
keystrokes simply do not react. HDI's cotizador does nothing at all on `fill()`; it needs real
keystrokes. (HDI, 2026-07.)

### How you BLUR matters as much as how you type

HDI again: blur by **clicking empty space**. Not Tab, and never the site's own *Limpiar* button —
Limpiar reloads dropdowns that jam the ASP.NET queue and turn a 2 s lookup into 20–60 s.

Finding a safe blank point is worth a helper: walk a grid of viewport points with
`document.elementFromPoint`, rejecting anything interactive (`A`, `BUTTON`, `INPUT`, `SELECT`,
`TEXTAREA`, `LABEL`, `IMG`, `IFRAME`, `OPTION`, anything with an `onclick`, anything inside a
modal). PJUD's `click_away()` and HDI's `FIND_POINT` are the same idea.

⚠️ In PJUD, `click_away` deliberately **hovers without pressing** — a real click on the background
once dismissed things that were needed. Prefer hover-and-settle unless you know a press is safe.

### Read-only inputs: mutate the property, then type for real

For a read-only datepicker, clear `readOnly` as a **DOM property** (a mutation, not an event, so
nothing untrusted is dispatched), then **type** the value with real keystrokes so the browser
itself emits genuine `isTrusted=true` input/change events.

⚠️ **Do not** go back to `el.value = x` plus `dispatchEvent(new Event('change'))`. That fires
`isTrusted=false`, and the failure is delayed and confusing: the search succeeds *once*, and the
**next** request comes back as the rejection page. It burned a profile (PJUD, 2026-07-21).

### Select elements: arrow keys, not `select_option`

`select_option`'s synthetic change event trips the WAF. Focus the select and press Arrow keys the
right number of times, with human cadence.

### ★ Always read the value BACK

Typing is not proof the value arrived. PJUD reads every date field back off the form and refuses
to search if it disagrees — because a wrong date window **does not fail loudly**, it returns
plausible results for the wrong period and files live courts as empty.

Related: validate at the door. A PowerShell `Get-Date -Format "dd/MM/yyyy"` returns `08-08-2026`
under an es-CL locale — `/` in a .NET format string means "the culture's date separator", not a
literal slash. That malformed window reached the form and a live tribunal was recorded as EMPTY
(PJUD, 2026-08-08). The scraper now rejects anything not matching `\d{2}/\d{2}/\d{4}`.

---

# Part 4 — Knowing when you have been refused

This is where scrapers lie to you, and it is the section to read twice. **Almost every "the site
blocked us" incident in this repo was something else**, and several "everything is fine" hours
were a total refusal.

### ★ Judge a search by the RESPONSE, never by the page

The results table keeps showing the **previous** search's rows while a new one runs. So:
- "Does the total say `Total de registros`?" is true *from the last search*. An early version
  returned at 0.0 s every time and recorded every court with the **previous** court's totals.
- A DOM fingerprint cannot tell empty→empty apart: an empty search clears the table, so two
  empties in a row look identical and "changed" never becomes true.

Ground truth is **a response from the search endpoint arriving after the click**. Clear your
network tap immediately before clicking, then wait for the response.

### The four tells of a refusal (PJUD/F5), and why one detector is never enough

1. A frame containing the rejection text.
2. A rejection **body**: the text AND a size in the band the WAF actually uses (100–1000 B).
   ⚠️ Size alone once killed a healthy sweep over a legitimate 0-byte response.
3. A challenge iframe (`TSBrPFrame`, `cs_chlg`).
4. **The submit button stuck `disabled` while the page is NOT busy.** No rejection page, no
   iframe — every other check says healthy. This is exactly how a spent session ran all night
   producing nothing (PJUD, 2026-08-08/09).

### ⚠️ Match every language and every wording

Both PJUD block detectors matched only the **English** F5 text while the site answered this
browser in **Spanish**. Both went blind *at the same moment*, and a run reported health for an
hour while every search was refused (2026-08-05).

It happened a **third** time with the tier-3 CAPTCHA frame, whose wording ("Your support ID is",
"What code is in the image?") matched none of the existing patterns, so two workers sat behind a
full-page CAPTCHA while every detector reported health (2026-08-10).

⇒ **One wording, one language, one frame you are not reading is all it takes.** Search *all*
frames, and match every known phrasing.

### ⚠️ Duplicate detectors go blind together — keep ONE copy

The reason the Spanish failure hit two tools at once is that each carried its own matcher. Entry,
search, freshness and block detection now have exactly one implementation (`ojv.py`). This is not
a style preference; it is the documented failure mode.

### "No results" is ambiguous, and the ambiguity is expensive

- **A spent session returns "no results"** for courts that have data. One PJUD run reported 20
  courts as empty and exited cleanly; a healthy session found 52 causas in one of them. **Every
  court after a block is a false negative that nothing in the data marks.**
- **"No results" can be a loading placeholder.** patentechile shows "Vuelve a consultar en unos
  segundos" transiently; the scraper allows a 12 s grace before concluding a plate has no record.
- **Never call a slow response empty.** PJUD's floor is 25 s before "empty" may be concluded, and
  the hard cap extends to 3× while the site's own spinner says it is still working — a slowdown
  from 11–35 s to over 75 s was discarding valid searches.

### ⚠️ Never judge a downloaded document by size or status

Clicking a document link opens a popup, the browser renders the PDF in its built-in viewer, and
what comes back is the **viewer's host document** — `<embed type="application/x-google-chrome-pdf">`,
about 14 KB of wrapper HTML, status 200.

This produced **two opposite wrong conclusions in one day** (PJUD, 2026-08-07): first three
wrapper files filed on disk as captured PDFs, then a perfectly good scripted click reported as a
WAF block. Separately, F5's anti-bot interstitial is ~8–14 KB of obfuscated JavaScript with a
200 status — comfortably over any size threshold.

**Check the magic bytes. `body[:4] == b"%PDF"`. Nothing else is evidence.**

### The best way to fetch a document: let the page fetch it

Do not click. Read the form's action and token, and have the page itself
`fetch(url, {credentials:'include'})` and hand back the bytes. Same single request the click would
have made, no popup, no viewer, verifiable result (0.7–5.2 s measured).

⚠️ This is **not** the same as an out-of-process HTTP client with copied cookies — that fetches
from outside the browser and looks nothing like a user. This runs *inside* the page already
holding the session.

### A stuck modal looks exactly like a block

A causa open times out → the modal never closes → its backdrop covers the controls → every later
click hits the backdrop → searches "return" nothing. One worker reported 20 courts as empty and
exited successfully. Clear stuck modals explicitly, and wait on the site's own spinner rather than
on your own guess about readiness.

---

# Part 5 — Pacing, rate, and concurrency

### It is a RATE, not a quota

One model fit every PJUD trial: the limit is requests per unit time from an address, not a count
of sessions or a total volume. Evidence: the same IP did 1,618 MB in 8 h with zero hard blocks
while a datacenter address took a terminal block at 431 MB.

### ⚠️ Gentle pacing can be compensation for bad behaviour — and hide it

PJUD ran at a 60 s search gap and a 90 s causa gap for weeks. Then `speed_probe.py` ramped both
down on live sessions (2026-08-10):

```
result requests   45 -> 22 -> 10 -> 6 -> 4 s   across 51 requests   never tripped
causa opens       90 -> 60 -> 40 -> 25 -> 15 -> 8 s  across 18      never tripped, 18/18 documents
```

Below ~15 s neither cycle shrank further, because the **site's own response time** (12–26 s)
dominates. The old gaps were not a rate limit — they were paying for a metronome keyboard and no
scrolling. **Fix the behaviour and most of the budget disappears.** Settings went to 20 s / 25 s,
and the same address then did 730 opens in a day.

⇒ **Before slowing down, check whether you look wrong.** Slowing down hides the real problem and
costs throughput forever.

### ⚠️ The gap is a floor on the interval, never a promise about the rate

Aggregate rate is wrong in **both** directions when derived from the configured gaps:

- **It goes UP when the expensive work runs out.** A worker whose per-item work was dominated by
  an expensive step becomes almost pure querying once those items are already banked. Same code,
  same gaps: 66 result requests in ten hours became one every 20–40 s. ~15× (PJUD, 2026-08-12).
- **It goes DOWN as local workers are added.** They share one connection and one machine, so each
  extra worker stretches every other one's cycle. **Four local workers measured 1.75 result
  requests/min — about what one produces.**

⇒ **Measure the rate from the logs. Never compute it from the config.** (`rate_watch.py`.)

### ⚠️ Remote workers do NOT self-damp — translate the rule

Each cloud runner has its own machine and link, so N runners at the same gap really is N× the
rate. And the budget belongs to the **datacenter range**, not the address: three shards on three
unrelated Azure IPs took their first block within **fourteen seconds** of each other, while
residential workers sweeping that same minute were untouched (PJUD, 2026-08-11).

That trial ran every shard at the single-worker gap — about 9 result requests/min, five times
anything measured safe — so it **confounded concurrency with rate** and could not say which the
range objected to. The fix is to scale each runner's gap by the shard count: N shards each firing
every `base×N` seconds is `1/base` requests/second *whatever N is*.

### ★ SETTLED 2026-08-12: it is the CONCURRENT SESSIONS, not the rate

The experiment was run properly — four runners joining 30 minutes apart, each paced ×4 so the
**aggregate never exceeded one worker's rate**. Every one entered on its first attempt, so
datacenter addresses are plainly not refused at the door. Then:

```
20:23  shard 1 joins  135.232.208.131   -> 1 concurrent
20:53  shard 2 joins  20.3.215.36       -> 2 concurrent
21:23  shard 3 joins  20.102.46.202     -> 3 concurrent
21:34:36  shard 2 blocked --,  FOURTEEN seconds apart   -> back to 1
21:34:50  shard 3 blocked --'
21:53  shard 4 joins  20.81.47.119      -> 2 concurrent
23:39:22  shard 1 blocked --,  EIGHTEEN seconds apart   -> 0
23:39:40  shard 4 blocked --'
```

Holding the rate constant changed nothing: sessions on **unrelated addresses were cut down in
near-simultaneous pairs**, the same signature as the earlier trial. So the verdict is applied to
the range, and it is triggered by concurrent sessions rather than by request rate alone.

And the throughput is *worse than one worker*, because each shard pays the ×N pacing tax and gets
culled anyway:

| | wall clock | causa opens |
|---|---|---|
| 1 shard at 1x | 38 min | 42 (**1.11/min**) |
| 4 shards at x4 | 196 min | **130 total** |
| 1 shard extrapolated | 196 min | ~218 |

⇒ **Remote means ONE worker.** Chain it with a cool-off rather than sharding it. The parallelism
that works is local, where separate sessions on one residential address ran four-wide all day.
Two concurrent runners did survive 1h46m against 11 minutes for three, so if you must have two,
expect to be culled in pairs and make sure every runner ingests before it dies.

### ★ …and then measure the SPEED separately, because it is a different question

Having found that concurrency is the constraint, it is tempting to stop. Don't — you still do not
know how fast ONE of them may go, and we had been guessing (inheriting the local numbers).

Measured 2026-08-12, one runner ramped 45 → 35 → 28 → 22 → 17 → 13 → 10 → 8 → 6 s:

| gap | mean cycle | mean req/min |
|---|---|---|
| 45 s | 67.0 s | 0.90 |
| 22 s | 43.8 s | 1.38 |
| **13 s** | **28.9 s** | **2.10** |
| 10 s | 28.4 s | 2.11 |
| 8 s | 30.8 s | 1.95 |
| 6 s | 29.1 s | 2.07 |

**36 requests, never tripped.** The cycle floors at ~28 s from gap 13 downward, because the site's
own response (17–23 s) plus ~2 s of our activity is all that remains — 8 s and 6 s buy nothing and
8 s is marginally worse. Overall split: **74 s of activity against 662 s of deliberate idling —
10% active.**

⇒ **There is no remote rate limit either.** X is the site's response time, the same answer as
local. We had been running remote workers at 20 s, about half the achievable throughput, for no
reason anyone had measured.

**And this makes the concurrency finding stronger, not weaker.** Those four culled shards were
paced at ×4 — roughly 0.7 req/min each, a *third* of what one runner sustains — and were cut down
in pairs anyway. With speed eliminated as a candidate, concurrent sessions are the only variable
left standing.

⚠️ **The general lesson: "we get blocked" and "how fast can we go" are separate questions, and
answering one does not answer the other.** Test them separately or you will attribute a
concurrency limit to speed, throttle yourself for months, and never find out.

### ⚠️ Keep concurrent workers out of lockstep

Two workers started together pace from the same instant and stay synchronised forever — observed
logging every step at the identical second. To a rate limiter that is not two requests spread over
a minute, it is two requests in the same instant, once a minute: the worst possible shape. Add
±15% jitter to every gap.

### A worker count is not a budget

"2 workers yes, 3 no" held for weeks and then stopped being true — four ran clean once the input
stopped looking robotic. **What predicted failure was never the worker count or the rate on its
own; it was the trouble events** (blocks, timeouts, failed selects). Alarm on those.

### Arrival is its own event, separate from rate

A burst of brand-new sessions is itself a trigger, independent of request rate. Six shards
launched together and only ONE got in; four fresh local browsers loading the site in the same
second all failed.

Fixed offsets do **not** solve this — entry can take three minutes, so an 8 s or even 50 s stagger
still leaves every worker inside the entry sequence simultaneously. Use a **condition, not a
timer**: one worker enters at a time, and the gate opens only when that worker's **first real
query comes back** — not when it merely reaches the form. (On 2026-08-10 all four workers reached
a form and none could search; a form-based release would have opened the gate four times on the
strength of nothing.)

Where a shared lock is impossible (separate cloud runners), use a timer with enough headroom to
cover the slow path twice over — and prefer a long **ramp** (30 min) so each worker proves itself
before the next joins and a failure can be attributed.

---

# Part 6 — Recovery: telling the failure modes apart

### ★ There are two failure modes and they need opposite remedies

| symptom | what it is | what fixes it |
|---|---|---|
| rejection page / challenge iframe / support id | a **rate verdict** | cool off, re-enter the same browser |
| every control fails — option list gone, values will not stick | the **session/browser is wedged** | a **replacement browser**. Nothing else. |

Measured four times in one afternoon (PJUD, 2026-08-12): a replacement browser had each worker
searching again within a minute. The negative was proved directly — one worker spent a full 180 s
cool-off *and* a clean re-entry, still could not drive the form, and stopped anyway; relaunched
onto a new browser it pulled the very same page on its first search.

⇒ **A recovery ladder needs both rungs.** Spending six cool-offs on a wedged session is how a
worker loses twenty minutes and then stops regardless.

### A block does not burn the profile

Re-entry clears a tier-2 block in ~18 s: close the tab, walk in again, and the exact request that
was refused succeeds. **Rotating the profile throws away a warm session for nothing.** (This
overturned months of folklore, and a diagnostic tool still carried the stale advice long after.)

### Cool off proportionally, and let a clean streak win the budget back

Cool-off scales with the recovery number (a block is a rate verdict, so returning at the same pace
earns another one). Count **consecutive** blocks and reset the budget after a run of clean work —
a lifetime cap strands a long job after six blocks however many clean hours sat between them.

### CAPTCHA is a stop, not a puzzle

A full-page image CAPTCHA is an explicit human-verification gate. Detect it, report it, stop.
Never script an answer. Cooling off will not clear it and rotating the profile only earns a fresh
one.

### ⚠️ An outage is not a block

An internet outage produces exactly the symptoms of a block — queries that never return, items
that never open — but none of the remedies apply. Check connectivity against **neutral third
parties** (never the target: asking the site that may be refusing you cannot distinguish the
cases), and never charge an outage to the block budget.

Related: if the **public IP changed** during the outage, the session is void — anti-bot systems
bind a session to the address that was issued it, and re-entry cannot fix that.

### ⚠️ The silent throttle

The worst failure has no tell at all: no rejection page, no challenge iframe, just operations that
quietly stop working. Consecutive failures *with a clean block-check* are themselves the signal —
count them and treat N-in-a-row as a block. Scope that counter to the **run**, not to the current
item: scoped per-item it never reaches the limit, and a throttle that costs two items per page
degrades for hours without a single detector firing.

---

# Part 7 — Structuring the work

### ★ Find the scarce act, and harvest everything around it

In PJUD, opening a record is the expensive, fragile act; queries are cheap (~24 opens before a
block, versus 208 queries in an evening with none). Everything the open makes available is already
in the DOM and costs nothing more.

⇒ **The detail view is where you harvest, not where you shop.** Take the header, the parties, the
sub-documents list, the history — all of it, every time. Only extra *requests* cost anything.

Identify your scarce act explicitly. It is rarely the thing that feels slowest.

### Pagination: harvest each page before advancing

A row index belongs to the page it was read from. Paginating to the end and then clicking page-1
indices opens the **wrong records**.

End-of-list is the site's own greyed-out *Next* control, **never** a row count — counts drift
(blank filler rows) and an accumulated overcount stops the walk one page early, truncating exactly
the biggest pages. One PJUD court went 91 → 135 → **293** records as this was fixed.

⚠️ **Results usually sort newest-first, so early-quitting pagination silently drops the OLDEST
items.** A dataset whose records start mid-window is this bug's fingerprint.

⚠️ **A pagination click is a query.** It hits the same endpoint and returns a result set, so it
must draw on the same rate budget. Pacing it separately meant every large page set quietly fired
at three times the intended rate.

### Distinguish "no next page" from "the click did not work"

A boolean return conflates them and the caller reads False as "done". Return a **reason**
(`advanced` / `last` / `stuck`), and flag the stuck case as incomplete rather than complete.

### Resume must be cheap, and completeness must be auditable

- Write state after every item, so stopping costs one item.
- Skip completed units **without issuing a request**.
- Re-open an item only if it is missing something it should have — never one whose answer was
  "there is nothing here". Retrying settled questions spends the scarce budget forever.
- Record `rows_seen` against the reported `total` so under-collection is visible later.

⚠️ **Audit coverage by the UNION across workers, never by one worker's state.** Overlapping ranges
inflated per-worker "missing" counts about 3× in PJUD; the real gap was five pages stuck on page 1
(PJUD, 2026-08-12).

### A flag column makes dedupe free

HDI marks every RUT it has checked — **whether or not it found data** — so nothing is ever
re-scraped, and clearing the flag is how you force a re-check. Write the result first, set the
flag second, so a kill mid-item costs a re-check and never a lost row.

### ⚠️ State held in memory is rewritten wholesale

A running worker holds its state in memory and rewrites the whole file after every item, so edits
made from outside are silently overwritten on the next save (49 of them, PJUD, 2026-08-10). Stop
the worker before touching its state. And because the write is not atomic, a reader can catch a
truncated file — snapshot and retry rather than parsing the live file.

---

# Part 8 — Storage

### Deterministic IDs, derived from the data

`<parent_id>-<child_key>` beats a generated id: re-running updates in place instead of duplicating,
and joins stay checkable by eye.

### ⚠️ `upsert` writes EVERY column — so a value the writer lacks becomes empty

The single most destructive trap in this repo. A writer that does not know a column will blank it
on conflict. Near-misses: a sweep that would have blanked the `corte` of all 180 courts, and
document URLs on 74 records the moment the sweep reached a region already scraped.

Remedies, by writer:
- **Insert-if-absent** (`ON CONFLICT DO NOTHING`) for reference tables.
- **Read the existing values and carry them forward** before upserting.
- **A targeted `UPDATE` of only the columns this writer owns** — this is what a backfill worker
  must do, always.

### Shells must never overwrite real detail

A discovery pass registers records with a key and a date. `INSERT … ON CONFLICT DO NOTHING` so a
shell can never overwrite a record that already has full detail, and re-running is free.

### ⚠️ Store the DIRECT link to a file, not its preview page

Google Drive's `webViewLink` is the UI wrapper, not the document. Store
`https://drive.google.com/uc?export=download&id=<id>`. Normalise it in **one** helper and apply it
to every uploader **and every cache** — a cache hit on an already-uploaded file otherwise keeps
handing back the old shape.

### Types, and the date trap

Migrating TEXT → DATE/TIMESTAMPTZ/INTEGER makes range queries possible at all (`'15/07/2026'` does
not compare as a date). Profile every value before converting.

⚠️ **Confirm day-vs-month order, never assume it.** PJUD confirmed DD/MM by checking that the
maximum first component was 31 across all date columns. Reversed, it would have turned 100k+ rows
into *plausible wrong dates* that nothing downstream would ever flag.

⚠️ Convert dates to ISO **in your own code**, not by trusting the database session's `DateStyle` —
get that wrong and 03/07 silently becomes 7 March.

Leave as TEXT anything that only looks numeric: identifiers with markers (`[11E]`), and national
ID numbers whose check digit can be a letter and whose leading zeros are significant.

---

# Part 9 — Running it unattended

### ⚠️ Long runs must be launched DETACHED

**A background task started from an agent harness is killed after roughly 30 minutes.** This was
misdiagnosed as a WAF block, a hang, and a browser wedge on separate occasions; one census
"stalled overnight" at 208/230 and sixteen hours of a warm profile were wasted looking for the
cause in the anti-bot system.

Use a launcher that reparents the process (`Start-Process` on Windows) and writes to a **log
file** rather than a pipe. **Diagnose a "stuck" run by whether the log file is advancing**, never
by whether a wrapper is still attached. Publish the healthy rhythm so long idle gaps are not
mistaken for a hang.

### Supervise, with judgement

An hourly supervisor that ingests, checks liveness and restarts the dead is worth building — a job
died twice in one day and each time sat idle until a human looked, once for 19 hours. Encode these
judgements explicitly:

- **Liveness is the process, not the log age** — but *evidence of life wins*. An unreadable
  process list is ignorance, not death. (A `CommandLine` scan returns **empty** when run from a
  different session or elevation than the target — so a supervisor that trusted it declared all
  four workers dead and started duplicates, two processes writing one state file.)
- **A running-but-silent worker is reported, never killed.** A wrongly-killed job costs more than
  a late warning.
- **Cap restarts** (e.g. 4 without progress) so a problem needing a human cannot become an hourly
  relaunch loop. Any progress resets the budget.
- **Ignore a stale lock rather than obeying it**, or one crash stops maintenance forever.
- ⚠️ **Match the process precisely.** `ingest_worker_a.py` contains the substring `worker_a.py`,
  so a naive match counts the supervisor's own ingest child as a worker. That produced a false
  "5 of 4 alive" — and, worse, would have read *3 workers + 1 ingest* as a healthy 4 and stayed
  silent through a real death (2026-08-12).

### ⚠️ Rotate logs, never truncate them

Redirecting stdout to an existing log **truncates** it — destroying the very lines that say why
the previous run died, which is the only reason anyone reads the file. Truncation also leaves NUL
bytes, which make `grep` treat the file as binary and go silent, so monitors stop reporting too.

### ⚠️ Own your browser, and take it with you

A worker that opened a browser must close it on exit — every exit path, via `atexit`. An abandoned
browser holds its profile and its debugging port, and **a listening port is exactly how a
supervisor decides a slot still has a usable browser**, so an orphan actively misleads it.

⚠️ Do not trust the spawned process handle: Chrome routinely re-launches itself into a new process
and lets the original exit, so `poll()` reports "already gone" while a full browser is still
running. Kill the tree you know about, **then** sweep for anything still holding your profile
directory. (Ten orphans and a live CDP port, PJUD, 2026-08-12.)

### Encoding will bite you on Windows

Python takes its stdout encoding from the locale (cp1252 here), so anything outside Latin-1 raises
`UnicodeEncodeError` **mid-print** and anything outside ASCII lands mangled in the log. Force
UTF-8 with `errors="replace"` on stdout/stderr at startup. Keep `argparse` help strings **ASCII**
— they are written straight to the console, and a `%` in them must be escaped as `%%` or `--help`
itself raises.

PowerShell adds its own: Task Scheduler runs Windows PowerShell 5.1, which reads `.ps1` as ANSI
without a **UTF-8 BOM** and then fails to parse any accented character; and 5.1's `Tee-Object`
writes UTF-16. Test scripts the way the scheduler runs them, not interactively in PowerShell 7.

### Scheduled tasks have conditions you did not set

A Windows Scheduled Task defaults to `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries`. On
a laptop that means the supervisor silently neither starts nor survives — a dead worker went
unnoticed overnight for exactly this reason (2026-08-12).

### Cron against a broken scraper is a liability

A daily workflow that could not possibly work fired 17 failing jobs a day for about thirteen days
before anyone noticed. **Make scheduled scraping opt-in and prove it by hand first**, and disable
workflows that are known dead rather than leaving them dispatchable.

---

# Part 10 — How to actually learn something (probe discipline)

The single highest-leverage habit in this repo: when a scraper misbehaves, **stop theorising and
build a one-variable probe.**

`search_probe.py` runs exactly one query per invocation with one thing changed
(`--mode click|human|clear|kbd|kbd-slow`) and takes its verdict from the **response**. It settled
in an afternoon a question that months of theorising had got wrong, and disproved four theories at
once.

Rules that made these probes trustworthy:

1. **One variable per run.** The three-worker trials that "proved" a concurrency ceiling also
   fired a corte-change burst, so they never isolated concurrency at all.
2. **Take the verdict from the network, not the UI.** The UI shows the last successful state.
3. **A canary.** HDI probes a RUT *known to have data* every 50 rows: if the canary comes back
   empty, the session has expired and every "no data" since is suspect. Without one, a dead
   session looks exactly like a run of genuinely empty records.
4. **Re-measure after every fix.** Numbers measured before a behavioural fix describe the old
   behaviour. The 60 s gap, the "~24 opens" ceiling and the "2 workers max" rule were all real
   *and* all obsolete within days of the input being fixed.
5. **Watch out for confounded wall-clock and action count.** Three runs that all died at ~2 min
   *and* at ~11 actions cannot tell you which mattered. Design the probe to separate them.
6. **Write down what you disproved.** Half the entries above exist because a theory was rebuilt
   twice.

---

## Quick checklist for a new scraper

```
[ ] THE ONE RULE: nothing a human could not do, or would not do. Re-read Part 0 when stuck.
[ ] What defends this site?  behavioural scoring / Cloudflare / nothing / auth only
[ ] Launch a REAL browser yourself; attach over CDP. Persistent profile. Headed, always.
[ ] Human at the gate: log in / solve the challenge by hand, with nothing attached.
[ ] Identify the SCARCE act. Harvest everything free around it.
[ ] Input: real keystrokes, correct blur, read the value BACK.
[ ] Pointer: arc + dwell, refuse covered targets — UNLESS the site just needs el.click().
[ ] Refusal detection: from the RESPONSE, all frames, every language, one shared implementation.
[ ] Documents: verify magic bytes. Fetch in-page, never click.
[ ] Pacing: start gentle, then PROBE for the real floor. Jitter every gap.
[ ] Rate: measure from logs, never derive from config.
[ ] Recovery: cool-off for rate verdicts, fresh browser for wedged sessions, stop for CAPTCHAs.
[ ] Storage: deterministic IDs, never blanket-upsert, direct file links, confirm date order.
[ ] Unattended: detached, log-file liveness, rotate logs, own and close your browser.
[ ] Probes: one variable, network verdict, a canary.
[ ] Update THIS FILE with what the build taught you.
```

---

## Where the detail lives

| topic | file |
|---|---|
| PJUD workers, pacing evidence, recovery, schema | `felipe/pjud/HANDOFF_WORKERS.md` |
| PJUD site + WAF, and how each conclusion was reached | `felipe/pjud/HANDOFF_CDP.md` |
| PJUD second machine / backfill worker | `felipe/pjud/HANDOFF_PC2.md` |
| Cloudflare + ad interstitials, launch-vs-attach | `felipe/scraper/patente_browser.py`, `enrich_patentes_local.py` |
| ASP.NET form driving, canary probes, flag-column dedupe | `cias/HDI-Ruts-Scraper/README.md` |
| Live rate measurement | `felipe/pjud/scraper/rate_watch.py` |
| One-variable probes | `felipe/pjud/scraper/search_probe.py`, `speed_probe.py`, `headless_check.py` |
