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

### ⚠️ Fallbacks are where the rule quietly dies

A fallback is written on a bad day, to rescue a run. It therefore fires **only when things are
already going wrong** — which is exactly when looking wrong costs the most.

Worked example (2026-08-13). Entry was: load the site's public home page, click the link to the
service. A fallback was added to *type the service's deep URL directly* when that click failed,
justified as "typing a public URL is ordinary browsing; a preference for the prettier path is not
worth losing the run over."

Both halves of that were wrong:

- **Nobody types the deep URL of an internal console.** They land on the home page and click. The
  fallback was not a slightly-less-pretty path, it was a different actor.
- **It only ever ran on already-struggling sessions**, so the least human-looking action in the
  whole run happened at its most fragile moment. The one worker observed using it tried twice and
  never got in, while three siblings on identical machines clicked through first time.

⇒ **Audit your fallbacks against the rule, separately from the happy path.** Ask what triggers
each one, and whether a person in that situation would do that. "Click through, or do not get in"
is a better rule than a fallback that rescues the run by acting like a bot.

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

### ★★ Ask what telemetry a human could not SUPPRESS — and check you emit it

The sharpest question in this file, and it came from the operator watching himself scroll
(PJUD, 2026-08-14): *when a person scrolls a results list, the pointer sits still in screen space
while the page moves underneath, so row after row passes under the cursor.* Those `mouseover` /
`mouseout` events are not something a human chooses to produce. They are unavoidable.

We produced **none of them**. Playwright's virtual mouse starts at `(0,0)`, and `human_scroll`
wheeled without ever positioning it — so every scroll happened from the top-left corner of the
viewport, a place no hand ever rests, with nothing beneath it. Measured live, identical wheel
events both ways:

```
pointer not positioned   ->    0 mouseover,  0 mouseout,  0 rows touched
pointer over the table   ->   12 mouseover, 12 mouseout,  2 rows touched
```

The fix is one `mouse.move()` before the first notch, plus a few pixels of drift between notches,
because a hand resting on a mouse is never perfectly still. It costs nothing.

⇒ **Generalise the question.** "Does my action look human?" is the weaker form. The stronger one
is **"what does a human emit involuntarily while doing this, and is my channel empty?"** An empty
channel cannot be explained away by unusual-but-legitimate behaviour — every real user fills it.

Channels worth auditing on any behaviour-scoring site, each of which we have now been caught
leaving silent at least once:

| channel | filled by a human when… | how we left it empty |
|---|---|---|
| wheel events | reading any long list | parsed the DOM, never scrolled |
| `mouseover`/`mouseout` | scrolling with the pointer over content | scrolled from `(0,0)` |
| pointer approach path | moving to anything clickable | `page.click()` teleports |
| keystroke rhythm | typing | fixed 60/70 ms metronome |
| **`mousemove` while idle** | **hand resting on the mouse** | tested — see below |
| page scrolled to a click target | wheel turned | `scrollIntoView` moved the page with no input device |
| focus arriving in a control | pointer moved to it, or Tab pressed | `.focus()` teleported the caret in |

~~★ **Idle `mousemove` was tested and bought NOTHING** (2026-08-14): two cloud arms, one variable,
both refused at exactly the same record with the same signature. Kept off by default so the
negative result is not rebuilt.~~

★★ **CORRECTED 2026-08-16 — that test was run at one twenty-sixth of a hand.** The arms really did
die identically, so the result stands *for that implementation*; what was wrong was the conclusion
drawn from it. We then recorded a real person doing the same work and counted what they emit:

| | a person | our "idle motion" | our worker between clicks |
|---|---|---|---|
| `mousemove` | **25.8 /s, on 98% of all seconds** | ~1 /s, only during pacing gaps | 0 |
| `mouseover` | **6.4 /s inside a modal** | ~0 — it vibrated in place | only what a click path crosses |
| while a record is loading | **25.2 /s — they keep moving** | 0 | 0 |

⇒ **The amplitude was wrong by more than an order of magnitude, and the SHAPE was wrong too.**
Jitter in place crosses no element boundaries, so it generates no `mouseover` at all — the one
channel that distinguishes a hand from a tremor. A negative result at 4% of the real amplitude is
not evidence about the channel; it is evidence about 4%.

**The rule this replaces "plausible stories" with: do not reason about a channel, MEASURE A HUMAN
FILLING IT, then copy the number.** Every other entry in this table was found the same way and
none of them needed a theory.

⚠️ The last two rows were both found by an operator **watching the browser**, not by reading logs
— the logs showed nothing wrong in either case. And the third, `.focus()` teleporting into a
dropdown, was a genuine tell whose removal did NOT fix the failure being chased. **Remove it
anyway, and record that it was not the cause**, or the next person will try it again.

### ★★ A worker must know WHERE IT IS, not just what it failed to do

Operator's call, 2026-08-14, after the site quietly moved its entry route: *a worker should
recognise where it is and act accordingly.* Every entry failure message we had described what did
**not** happen — "target covered", "no form after attempt 1", "could not reach the site" — and
none said where the worker was standing. It was standing **on the form it had been sent to
fetch**, refusing to click a gate button it had already passed, and the log could not say so.

The cost of that omission was an hour of chasing the WAF. The fix is one function:

```
locate(page) -> form | results | modal | gate | aviso | captcha | blocked | www | blank | unknown
```

Rules that make it worth having:

- **Never raises.** Mid-navigation returns `unknown` — "I could not tell" must be a state, not an
  exception, and must not be confused with "nothing is wrong".
- **Order by what is actionable.** A page can be several things at once (a form *with* results, a
  gate *under* an aviso); return the one that decides the next move.
- **Wire it into the give-up paths, and make them RECOVER.** Every "I am stuck" line should carry
  the state — and where the state says the job is already done, take it instead of failing.
- **One place knows what the site can look like.** Add a state here, not another special case at a
  call site.

⇒ Related failure: a scripted path that only recognises success by the OBSTACLE'S markers. Ours
accepted arrival only if the gate's buttons were present, so a click-through that landed *past*
the gate read as a failure. **Detect the destination, not the hurdle.**

### ★ Detect overlays by hit-test, never by id

Two functions in this repo each knew exactly one overlay by name, and each was written the day
that overlay cost a run. A third overlay would have been invisible to both — the worker could only
report "target covered", with no idea it was an overlay at all.

Asking the browser what is genuinely on top needs no vocabulary and survives the site inventing
another one: `elementFromPoint` at the target's centre, walk up to the nearest floating/dialog-ish
container, read its id, z-index, text **and its own dismiss controls**, then click whichever says
close/cerrar/aceptar/ok/×. Verified against an injected overlay with an id nothing in the codebase
had ever seen — detected and cleared first time.

⚠️ **Protect your own modals.** A generic overlay-closer will happily close the record you are
standing in. Keep an explicit allow-list of overlays that are the work rather than an obstacle.

⚠️ **"Unhittable" is not "covered".** The first version fell back to "whatever is on top", so a
button sitting under a `<select>` in normal flow was reported as covered by a dropdown — and the
cleaner would have hunted for a dismiss control on it. If nothing overlay-like is above the
target, say so: an unhittable target is a **layout** problem, a different diagnosis with a
different fix. Disguising one as the other is how "covered" came to mean three different things in
a single week.

### ★★ The same environment can be served a different SITE — never generalise from one machine

PJUD, 2026-08-14. The landing page changed its entry route: the old link to a gated `/home/` page
was joined by one that goes straight to the search form. I scanned **one** machine, saw only the
new link, concluded the old route was gone **for everyone**, and pushed a single global preference.

Both were wrong. A cloud runner is still offered **both** links — and worse, the two environments
need **opposite** ones:

| | direct link | gated route |
|---|---|---|
| residential | works — 375 record opens | (not offered) |
| datacenter | enters cleanly, then **cannot complete one search** | the only route that works |

⇒ **Environment-dependent behaviour needs an environment-dependent setting**, not a constant. Make
it a flag with the measurement written beside it.
⇒ **A probe that answers "what is this machine actually offered?" costs two page loads.** Each
guess instead cost a whole session. Build the probe first.

### ★★ When something new breaks, ask what you started DOING that you never did before

The hardest bug of that session: a worker that had run for weeks began dying after exactly ten
records, remotely only, always on the same record — while the same code on the same records ran
375 clean locally. Days of counters (opens, bytes, requests, elapsed) explained none of it.

The answer was one line in the diff: the worker now switched to a **second sub-view** on every
record, an interaction it had **never performed before**. Disabling that alone lifted the wall —
the record that had hung for 90 s opened in six.

⇒ **Diff the BEHAVIOUR, not just the code.** "What actions does this version take that the last
one did not?" is a shorter list than the code diff and it is where new failures live.
⇒ Its own docstring had said the risk out loud — *"it went unnoticed because worker A only ever
reads cuaderno 1 and never switches"* — written by someone fixing a related bug months earlier.
**When you make a warning's precondition come true, that warning is now about you.**

### ⚠️ A burst is not a rate

The offending switch fires its second request **~4 s after the first**, where every clean run
spaced that same endpoint **29–38 s** apart. Averaged over a minute the difference looks minor;
as a *pattern* it is two requests in four seconds against one every half-minute.

⇒ **Pacing configured per ITEM says nothing about the shape within an item.** If handling one
record now costs two requests, they land together — and "requests per minute" will not show it.
Nobody opens a case file and flips to its second volume four seconds later.

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

### ~~Read-only inputs: mutate the property, then type for real~~ → **use the widget**

~~For a read-only datepicker, clear `readOnly` as a **DOM property** (a mutation, not an event, so
nothing untrusted is dispatched), then **type** the value with real keystrokes so the browser
itself emits genuine `isTrusted=true` input/change events.~~

★★ **OVERTURNED 2026-08-16 by the operator, who simply tried to use the site: "I can't type the
dates in the search. I can only use the date picker."** Both fields are `readonly` and carry
`hasDatepicker`. So the technique above — unlock the field, type into it, press Escape — is a
sequence **no user can produce**, on the one form where the anti-bot token is minted. It had been
in every run this project has ever made.

The trick is seductive because it is technically clean: the mutation dispatches nothing untrusted,
and the keystrokes really are `isTrusted=true`. Both facts are true and both are beside the point.
**`isTrusted` was never the question — the question is whether a person could have done it.** A
locked field that receives keystrokes is a state the site's own UI cannot reach.

⇒ **If an input is `readonly`, the site is telling you where its real control is. Go and drive
that.** For a jQuery UI datepicker: click the field, wait for `#ui-datepicker-div` to be visible,
click `a.ui-datepicker-prev/next` to the month, click the day link — every step a `human_click`.

⚠️ Two traps found driving it, both mine, both costing a live session each:

- **Poll for the widget; never sleep a flat interval.** A 500 ms wait declared "did not open" on a
  widget that opens in ~700 ms — and the browser died with the process, taking the evidence.
- **Do not threshold on how many days are rendered**, and do not theorise about the number either.
  I required ≥20 day links, which "failed" twice on a widget that was open the whole time; I then
  explained the 16 I had seen as *the site refusing future dates* and wrote that here as fact. The
  live widget shows **31**. One observation, one confident rule, wrong — the exact habit this
  handbook warns about, committed while documenting a different instance of it. Ask only whether a
  calendar is present, then read the value back.
- **★★ ...and then BOTH of those were half right (2026-08-18). DRAWN IS NOT SELECTABLE.** The
  widget renders all 31 days *and disables every day after today*: jQuery UI turns a refused day
  into `<td class="ui-datepicker-unselectable ui-state-disabled">` holding a **`<span>`, not an
  `<a>`**. So the original hunch — the site refuses future dates — was true, and the correction —
  it shows 31 — was also true, and counting *cells* could never tell them apart. A cloud runner
  and a local worker died on this cell minutes apart, both asking for `31/08` on the 18th: the day
  locator resolved to **zero elements**, the click helper fell through, and the only evidence
  either produced was `#fecHasta reads ''`. It cost a whole remote run and it was visible at a
  glance in the first traced frame of that picker — greyed cells from 19 onward.
  ⇒ Count the **anchors**, not the cells; check the target cell for `disabled`/`unselectable`
  before clicking it; and clamp a future end-date at the door, because a person standing at that
  calendar clicks today — the 31st is simply not offered.
- **★ Read the calendar's state from its DAY CELLS, never its header.** Both header reads are
  traps and they fail *silently, in opposite directions*. `.ui-datepicker-month` was a `<span>`
  but `.ui-datepicker-year` a `<select>`, so `textContent` returned every option concatenated
  (`"2010201120122013…"`) → a year in the billions → "we are past the target" always true → the
  widget marched **backwards** through months until it ran out of hops. Reading that select's
  `.value` instead gave **2020 while the header displayed Agosto 2026** → always "before the
  target" → it marched **forwards**. I fixed the first, re-ran, and walked straight into the
  second. jQuery UI stamps `data-month` (0-based) and `data-year` on every day `<td>`: the
  calendar stating what it is actually showing, in a form that cannot disagree with itself.
  Scope the day click to that cell too, or a trailing day of the adjacent month can match.

⚠️ And check what the form holds before you trust it: **these fields start EMPTY.** An empty window
searches instantly, returns zero rows, and still reports "results" — a clean-looking answer to a
question nobody asked. Our worker never noticed in months of running, because it typed the dates
in every single time.

⚠️ **Do not** go back to `el.value = x` plus `dispatchEvent(new Event('change'))`. That fires
`isTrusted=false`, and the failure is delayed and confusing: the search succeeds *once*, and the
**next** request comes back as the rejection page. It burned a profile (PJUD, 2026-07-21).

### Select elements: arrow keys, not `select_option` — but check whose rule this is

`select_option`'s synthetic change event was believed to trip the WAF, so the fix was: focus the
select and press Arrow keys the right number of times, with human cadence.

⚠️ **Re-read the evidence before you inherit this, 2026-08-16.** In the project's own notes the
same rule appears twice with opposite strength: "never `select_option` the tribunal" is annotated
*"untested since the 07-22 fix — it may well be innocent too"*, while `select_option` on the
smaller select is recorded as *"TOLERATED — validated"*. Then we measured a real person: **zero
keydowns in an entire session**, both selects changed, because picking from a native dropdown is a
gesture the page sees as a trusted `change` with no keyboard at all.

So the arrow keys are **our invention**, and an expensive one — walking a 230-option list is ~54
metronome keystrokes into a channel the human leaves completely empty. Meanwhile the one thing we
cannot reproduce is the native popup itself: it is an OS surface, and no CDP event reaches it.

⇒ Two honest options, and the choice needs measuring rather than assuming: **trusted keys the user
never pressed**, or **a synthetic change with a real pointer arrival and no keys**. Approach the
control with the pointer either way, and **never click a `<select>`** — that opens the native
popup, and everything after it is delivered into a dropdown nobody can see.

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

### ⚠️ "Online" and "can reach the target" are different questions

A connectivity check that probes **raw IPs** (1.1.1.1, 8.8.8.8) is deliberately independent of the
target — which is right, because it lets you tell an outage from a block. But it means the check
returns *online* while the target's name is unresolvable, and the worker then spends its entire
arrival on a host it never looked up. The run ends looking like it was refused; it never reached
the site at all.

Observed 2026-08-13: a cloud runner hit `ERR_NAME_NOT_RESOLVED` and burned all three entry
attempts. From a residential line at the same minute the site resolved and served HTTP 200 in
1.3 s. Nothing was wrong with it.

⇒ **Ask both questions.** `internet_up()` *and* `can_resolve(target)`. A resolution failure is an
outage, not a refusal: no cool-off, no recovery spent, no profile rotated — there is nothing to
apologise for when you never arrived.

⚠️ And consider that you may be causing it. Every walk-in and every retry re-resolves the host, so
N workers × M attempts is a lot of queries from one address range in minutes. A datacenter
resolver's path to a distant authoritative server is long and rate-limits are real: **a retry
storm can manufacture the DNS failures that then look like blocks.**

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

### ★★ OVERTURNED 2026-08-13 — and the mistake is more instructive than the finding

**Everything in the next section is wrong, and it is left standing because of HOW it was wrong.**

The conclusion below — "concurrent runners are culled as a group, remote means one worker" — rested
entirely on the observation that shards died within seconds of each other, three trials running.
It was never checked against a **solo baseline**. When one was finally measured:

| config (identical pacing, gated arrival) | opens per shard | combined | session life |
|---|---|---|---|
| 1 runner | 77 | 77 | 75 min |
| 2 runners | 75, 72 | 147 | 66 min |
| 3 runners | 74, 72, 70 | **216** | 65 min |

~~**A session gets ~70–77 requests-with-documents and is then refused, whether it is alone or one
of three.**~~ **Overturned 2026-08-13 — there is no per-session budget at all** (see the box below).
What survives from this table is the part that matters: **nothing is shared, and yield scales
linearly with runners.**

### ★★ OVERTURNED 2026-08-13: the "session budget" was our own bug, and there is no counter

Six sessions clustering at 73–85 opens looked exactly like a quota. It was not one. The full set,
once the *blocked* runs were compared against each other instead of against the one that fit:

| run | causa gap | searches | opens | pdf bytes | life | outcome |
|---|---|---|---|---|---|---|
| solo control | 25 s | 8 | 77 | **136.5 MB** | 68 min | blocked |
| — | 25 s | 2 | 77 | **62.6 MB** | — | blocked |
| — | 25 s | 3 | 85 | 80.2 MB | — | blocked |
| — | 25 s | 3 | 74 | 69.8 MB | 70 min | blocked |
| the fast run | **8 s** | 8 | **221** | **179 MB** | **131 min** | clean — *stopped by hand* |

Every candidate dies on this table. **Opens**: 74–85 blocked, 221 clean. **Bytes**: blocked at
62.6 MB, clean at 179 MB — and the blocked runs alone span 29.5–136.5 MB, a **4× spread**.
**Elapsed**: 68–70 vs 131 min. **Searches**: 2–8 in *both* groups.

⚠️ Note what the blocked column alone already proves: two runs that both ended in a refusal, one
at 62.6 MB and one at 136.5 MB. **A byte ceiling was refuted by the failures by themselves**, and
I spent an evening "confirming" one from a single close pair (136.5 vs 125 MB) picked out of that
spread. A wide spread contains a convincing pair for almost any hypothesis.

**The cause is still open, and two candidate causes were killed writing this section.** First a
byte ceiling (above). Then "the blocked runs predate removing the direct-navigation fallback" —
which fit the timestamps perfectly and was **wrong**: grepping the logs for the fallback's own log
line found it fired **zero times in five blocked runs**. It was dead code in every one of them.
Removing it was still right — a referrer-less arrival at a deep URL is a Part 0 violation — but it
explains nothing here.

What the blocked runs actually share, and the clean one does not: the **same June window**, the
**same sweep from index 0**, and a **25 s causa gap (~47 s cycle)**. All of them died in the same
stretch of large Antofagasta civil courts (1041–1043, 349–373 results each) at index 16–18. The
clean run changed window, range **and** pace at once, so it is not a controlled comparison — it
proves the ceiling is not fixed, and nothing more.

⇒ The one-variable probe that would settle it: **same June window, same start at index 0, causa
gap 8 s.** Past ~85 opens ⇒ it was the pace, and *faster is safer*. Dead at ~77 in Antofagasta
again ⇒ it is positional, and the counters were always a coincidence of where 75 opens lands.

Traps, all of which fired here at once:

- **A cluster is not a quota.** Runs sharing a pace *and* a bug run down together. Six agreeing
  numbers are one measurement repeated, not six.
- **Compare the failures with each other, not with the success.** The two blocked runs at 62.6 MB
  and 136.5 MB refute a byte ceiling by themselves. I had been comparing one blocked run to one
  clean run and finding a suspiciously close pair — of course I did; a 4× spread contains any
  number you like.
- **The counter you are hunting may not exist.** Before modelling the target's budget, diff your
  own code against the run timestamps — but then **check the suspect code actually ran.** A commit
  landing between a failure and a success is a coincidence until a log line proves execution. One
  `grep -c` for the fallback's own message would have saved the wrong conclusion above, and it is
  the same discipline as taking a verdict from the response instead of the UI.
- **A run that differs in three ways is not a control.** Window, range and pace all changed here.
  That is enough to refute a fixed ceiling and not enough to name a cause.

And the "coordinated cull" dissolves: three sessions started within three minutes of each other,
each spending an identical allowance at an identical rate, **arrive at zero together**. Simultaneous
deaths were never evidence of coordination — they were evidence of identical clocks started
together. Twenty-one seconds apart, and it means nothing at all.

⚠️ **The generalisable error: "they failed together" does not imply "they caused each other to
fail".** Workers doing the same work at the same pace from the same start will always fail
together, for entirely independent reasons. Without a solo control you cannot tell a shared
ceiling from a per-session budget — and every remedy for the first is wasted effort against the
second. Three trials and two days went into a conclusion one control run reversed.

⚠️ **Still unexplained, and recorded as such:** one earlier trial had four shards die within
18 seconds holding **74, 16, 2 and 38** requests. Wildly unequal work, identical death time — a
per-session budget cannot produce that. Those shards were paced 4× slower and staggered 30 minutes
apart, so they may not be comparable, but the pattern has no account. Do not treat the model below
as complete.

---

### ~~★ SETTLED 2026-08-12: it is the CONCURRENT SESSIONS, not the rate~~ (superseded, see above)

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

### ⚠️ A shared lock is never actually impossible — find the thing both machines can see

The obvious fallback for workers on *separate machines* is a timer, because there is no shared
filesystem. Resist it. A timer cannot express "after the previous one succeeded", and for a
**concurrency test** it is not an approximation but a broken instrument: staggering two runners by
30 minutes means that for those 30 minutes there is exactly one session, which measures nothing
about whether two can coexist.

They always share *something* — the database you are writing results to. One row is enough:

```sql
-- acquire: ONE conditional update, so two racers cannot both win
UPDATE entry_gate SET holder = :me, ts = now()
WHERE id = 1
  AND (holder IS NULL OR holder = :me OR ts < now() - interval :stale)
RETURNING holder            -- a row back means you hold it
```

Three properties make it safe, and each is load-bearing:

- **Single statement.** `SELECT` then `UPDATE` has a window where both readers see "free".
  The database serialises the row; let it.
- **Stale-break.** A holder that dies must not strand everyone. Release with `WHERE holder = :me`
  so a broken-as-stale holder cannot later clear a gate that now belongs to someone else.
- **Fail OPEN.** If the database is unreachable, log it and proceed. A gate that failed closed
  would stall the whole fleet over an unrelated outage; failing open costs at worst one ungated
  arrival — exactly what you had before the gate existed.

Verify all three against the real database before you trust it: B refused while A holds, B
acquires after A releases, a silent holder broken after `stale`.

### ⚠️ Three ways a shared gate quietly stops working

All three were live at once here, and together they produced a "concurrency ceiling" that did not
exist. A gate that is *present but not working* is worse than none, because you trust the results.

**1. A killed process never releases it.** Cancel a cloud run and the workers are killed outright —
`atexit` never fires, and the row stays held by something that no longer exists. The next run then
queues behind a corpse for the whole stale timeout.
⇒ **Stamp the holder with the run/session id and break foreign holders on sight.** If your
scheduler guarantees one run at a time, a holder from a *different* run cannot be alive. Only
holders from your own run deserve the stale timer.
⚠️ Parse that id carefully. Ours were `slot1-<run>` but also `slot3-swap-<run>`; taking the second
dash-separated field read `swap` as the run id, which would have broken a **live** holder and let
two workers in at once — the exact thing the gate exists to prevent, introduced while fixing it.
Take the last field.

**2. Some arrival paths don't use it.** Ours had four ways in — boot, recover, outage re-entry,
browser swap — and only two were wired to the shared gate. The other two fell back to a *file*
lock, which on separate machines is per-machine and therefore meaningless. So every recovery
re-entry was effectively ungated: the moment several workers blocked, they all walked back in
simultaneously.
⇒ **One factory, every path.** Grep for every construction of the lock; a fallback default is how
this hides. And note the shape of the bug: it only appears once workers start *failing*, so it is
invisible in the happy path and in small tests.

**3. It gets held across a sleep.** A blocked worker cooled off for 3–9 minutes while holding the
gate, turning one worker's rate penalty into the whole fleet's stall.
⇒ **A gate is for arriving. Release before any wait**, and re-acquire when you are actually ready
to walk in.

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

### ★★ Recovery rescues the WORKER. Make sure it also rescues the WORK.

The most expensive class of bug found in this repo is not in the scraping — it is in the code
written to keep the scraping alive. Two instances in one afternoon, both silent:

1. **A run that skipped items reported success.** The "N consecutive failures = stop" guard only
   fires on a *run* of failures. When the assigned range **ended** before the run reached the
   limit, the loop simply exited and printed a clean `DONE`, with real courts never searched and
   *nothing in state marking them*. Absent is not the same as incomplete: no resume revisits an
   item that was never recorded, and no audit of `complete` flags can see the hole.
2. **A browser swap resumed at the wrong index.** After replacing a wedged browser, the worker
   rewound one step — the item that tripped the limit — and carried on past the four that had
   failed *before* it. The swap saved the session and abandoned its work.

Both were found only by auditing the **union across all workers**, and both had been live for an
entire national sweep.

⇒ **Every recovery path must ask "what did I skip while failing?" and go back for it.** Rewind
over the whole failure run, not the last step. Record skipped items explicitly, exit non-zero, and
never let a partial pass end in a success code.

⇒ **Audit coverage by the union, not by any single worker's state.** Per-worker "missing" counts
were inflated ~3× by overlapping ranges, while the genuinely absent items appeared in no worker's
state at all.

### ⚠️ Stop yourself before the platform stops you

Any hosted runner has a hard ceiling (GitHub: 6 hours, then killed). A kill loses whatever was in
flight *and writes no report*, so the next run cannot tell "the job is finished" from "the last
one was cut off in the middle". Give the worker its own **lifespan** below that ceiling: stop
cleanly, save state, record where it got to, exit with a distinct code. A hard kill becomes a
handover.

And when chaining runs, **continue on the WORK, not on a hop count.** A fixed number of
continuations either stops with the job half-done or keeps firing at a finished one, because it
never looks at what happened. Have each run write a verdict — finished / reason / stopped-at /
blocks — into the state the next run can read, and continue while work remains *and* the failures
stay within range. Keep a hard hop bound anyway, as the backstop against a bug in that logic.

### ★★ A block is the LAST sign, not the first — learn to see yourself degrading

Every recovery mechanism in this file reacts to a refusal. That is too late, and it need not be:
sessions decline visibly first. Measured on a remote worker, 2026-08-13, the decline was legible
for **twelve minutes** before the rejection that ended the run:

| time | signal | lead |
|---|---|---|
| 03:42 | anti-bot interstitial served instead of a document (×2) | **12 min** |
| 03:47 | paginator stalled | 7 min |
| 03:49 | search 75 s → timeout | 5 min |
| 03:50–51 | two "empty" results at 57–59 s | 4 min |
| **03:54** | **hard rejection — run over** | — |

Healthy latency for that site was a **measured** 17–23 s. It ran 45, 57, 59, 75.

**Score the symptoms on a rolling window rather than tripping on any one**, because the site's own
latency varies honestly (13–29 s here) and a single slow response means nothing. Weight by how
close each symptom is to an outright refusal:

```
anti-bot interstitial on a document   2   # this IS a refusal, just not on a search
search timeout / never-proved-fresh   2
search slower than 2x baseline        1   # the trend, never one sample
paginator stall                       1
--- and CLEAR the window on a fast, fresh result ---
```

When the score trips, **step back before you are pushed**: cool off and re-enter *pre-emptively*.
Re-entry costs seconds; a hard block costs the recovery budget, and on a cloud runner with one
retry it costs the whole run. Do not count this against the recovery budget — nothing has refused
you yet. It is the equivalent of a person noticing a site has gone sluggish and taking a break
rather than clicking harder.

⚠️ **The same score decides what you are allowed to BELIEVE.** An "empty" from a healthy session
is an answer; from a degrading one it is a symptom. On the run above, the worker filed two large
courts as swept-and-empty four minutes before it was blocked — and we already held 26 records from
one of them, so the verdict was provably false. Nothing downstream flags that, and a resume skips
them for ever. So: record the empty, but only mark it *complete* when the session is clean.

⇒ Generally: **a scraper's confidence in its own results should be a function of its measured
health at the time it collected them.**

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

### ★ Split workers by HOW MUCH of the record they intend to take

Once the scarce act is named, the natural division of labour is not by subject area but by depth.
PJUD ended up with three workers spending the same causa open three different ways:

| worker | job | cost per record |
|---|---|---|
| **A** discovers | sweep the list, take everything the open makes free + one document | 1 open, 1 fetch |
| **B** finishes | every document, every sub-lookup, every tab | 1 open, **40+ fetches** |
| **C** refreshes | re-open a finished record, take only what is NEW | 1 open, **0 fetches** |

This is what lets bounded work run where the budget is small and unbounded work run where it is
large: A needs a big allowance and gets the residential address; B is bounded by construction
("here is a list, finish it") and fits a small cloud session exactly.

⚠️ **A refresh worker's whole value is one number: fetches when nothing changed. It must be zero.**
If it re-downloads what it already holds it costs exactly what the deep worker costs and buys
nothing — while looking *completely successful*: same rows written, same green tick. Load what you
already have, hand it to the shared harvest as a skip list, and **assert the invariant in the run's
own output** so the failure is visible from outside.

⚠️ **Skipping work must never mean forgetting the answer.** The skip list has to carry the stored
value, not merely suppress the lookup — because the row still gets written back, and a field you
declined to re-fetch goes back EMPTY and erases what you had. Same shape as the upsert trap in
Part 8: writing every column from a partial harvest blanks everything the harvest had no opinion
about.

⚠️ **The deterministic row id is what makes any of this work, and it is exactly what drifts.** The
skip list is matched by id; if the id scheme changes on either side, nothing matches, every skip
list is empty, and the refresh silently becomes the deep worker again. Test it by refreshing a
record you finished *minutes* ago — anything re-fetched there is drift, not news.

### ★ Reject the record at the cheapest point that can decide

The scarce act buys a decision as well as data. Once PJUD's causa modal is open its header says
whether the causa is wanted at all — so the discard happens **there**, before any sub-view is
opened or any document bought (operator, 2026-08-14: *"if the header doesn't match, ditch that
causa; there's no need to go into its books"*). A rejected record costs one open and nothing more;
about 11% of the corpus goes on one rule.

⇒ **Order the work so the cheapest disqualifying test runs first**, with the expensive harvest
strictly after it. "Grab everything while we are here" is right for *free* data and wrong for
anything costing a request.

### ⚠️ A "record-level" field may be a sub-view field in disguise

PJUD's causa header shows `Etapa: …`, which reads like a property of the causa. It is not — it
belongs to the **currently displayed cuaderno**, and switching books re-renders it:

```
book 1 - Principal   ->   Etapa: 1 Notificación demanda y su proveído   (9 rows)
book 2 - Apremio     ->   Etapa: 1 Mandamiento                          (2 rows)
```

Parse the header after switching sub-views and you store the wrong value into a column named for
the record — and gate on it too. Nothing looks broken at any point. **Read record-level fields
before touching any sub-view, and leave the reason in a comment where the next person will reach.**

⚠️ Both books numbered their stage **1**: ordinals are scoped to the sub-view, so an enumeration
inferred from one view does not hold across the record.

### ⚠️ Never match an enumerated label by its full string

PJUD stages arrive as `"8 Terminada"`, `"1 Notificación demanda y su proveído"`. A skip list of
exact strings looked obvious and was quietly broken: it held `"6 Terminada"`, which **does not
exist** (6 is *Impugnación de Sentencia*; Terminada is 8), so that entry matched nothing for as
long as it existed — and the ordinals are sparse (0–8, then 12) *and* per-sub-view.

⇒ **Strip the ordinal, fold case and accents, match a substring.** Sites abbreviate: the single
stored instance of "Téngase por no presentada la demanda" actually reads *"…la **dda** por
apercibimiento"*. An exact match finds nothing while reporting the filter working perfectly —
**a filter that silently passes everything is indistinguishable from one that correctly matched
nothing.** Count what you dropped and log it, or you cannot tell the two apart.

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

### ⚠️ A worker's log format is not an interface — but supervisors will treat it as one

A supervisor that decides anything by grepping a worker's output has a hidden coupling to that
output, and nothing will fail when you break it.

Measured 2026-08-13: a supervisor checked the **last three lines** of the log for `DONE.` to decide
a slot had finished. The worker then gained two closing lines — a structured run report, and a
"closed the browser I opened" message — which pushed `DONE.` out of that window. The supervisor
could no longer see a finished slot, and **restarted it every hour, ten times overnight**, each
restart launching a browser, walking into the site, running a search, finding nothing to do and
exiting. Ten pointless arrivals at a site that scores arrivals, and it would have continued
indefinitely.

Nothing errored. Nothing looked wrong. The logs even said `DONE.` every single time.

⇒ **Have the worker write a structured verdict — `finished`, `reason`, `stopped_at` — into the
state file, and have supervisors read THAT.** State is an interface; prose is not. Keep a log
fallback for old state, but read a generous tail rather than an exact line count.

⇒ More generally: **when you change what a worker prints, grep the repo for anything that reads
it.** The coupling is invisible from the worker's side.

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

### ⚠️ Running it on hosted CI — the traps that cost whole runs

Cloud runners are attractive for a scraper: free minutes, a fresh IP per job, no machine to babysit.
Four things about the *platform* have each destroyed real work here (GitHub Actions, PJUD, 2026-08).

**A concurrency group holds exactly ONE pending run.** `cancel-in-progress: false` protects the run
that is *executing*; it says nothing about the one waiting. Dispatch a third and the queued one is
**silently cancelled** — that is how a worker-B run that had never touched the site was destroyed.
⇒ **To run N things in sequence, make them N JOBS IN ONE RUN**, chained with `needs:`. Jobs queue
properly, each still gets its own machine, its own IP and its own full job timeout.

**`if: success()` on a chained measurement queue throws away the rest of the night.** A blocked or
refused test is a *result* — often the very result you queued it for. Use `if: !cancelled()` so one
refusal does not cost the four measurements behind it, and keep cancellation as the off switch.

**A step's exit code is the LAST command's.** `python … | tee` reports tee's status, so a traceback
exits 0 and the job goes green having measured nothing. `set -o pipefail`, every time. Same family
as `|| echo "…"`, which once made a failed ingest look successful and lost 431 MB of PDFs.

**Validate the YAML before dispatching it.** `run: echo "public IP: $(…)"` is a parse error — a
plain YAML scalar may not contain `": "` — and you find out at dispatch, after queueing behind a
five-hour job. One `yaml.safe_load` over the file catches it in a second. Boilerplate repeated
across six jobs belongs in a composite action for the same reason: a fix applied in five places
and missed in the sixth is the normal outcome.

⇒ And the one that is not a platform quirk: **a runner is a different environment, so every number
measured elsewhere is unmeasured here.** See Part 10.

### Encoding will bite you on Windows

Python takes its stdout encoding from the locale (cp1252 here), so anything outside Latin-1 raises
`UnicodeEncodeError` **mid-print** and anything outside ASCII lands mangled in the log. Force
UTF-8 with `errors="replace"` on stdout/stderr at startup. Keep `argparse` help strings **ASCII**
— they are written straight to the console, and a `%` in them must be escaped as `%%` or `--help`
itself raises. **That includes `description=__doc__`**, which is the easy one to miss: the module
docstring is where the arrows and ⚠️ live, and passing it to `ArgumentParser` puts them on a
cp1252 console. `watch_live.py --help` died that way (PJUD, 2026-08-16) while the tool itself ran
perfectly — pass a short ASCII description and let the docstring stay rich for readers.

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

### ★★ Do not invent a property of the target to explain your own results

The most expensive hour of 2026-08-13 went on a theory that the site's address range "tires" and
needs ~90 minutes to recover. The evidence was a real correlation — every run that worked had over
an hour of quiet before it; every collapse came ~20 minutes after another run.

It was wrong, and the operator killed it in one sentence: *we ran back-to-back tests all day
locally with no decay.* The correlation existed because I had **also** been raising the worker
count over the same period — two variables moving together across eight runs, and I attributed the
result to the one I could not measure.

Worse, the theory was *self-protecting*: it made every experiment cost 90 minutes, which meant
fewer experiments, which meant it stayed untested.

⇒ **When your results need a new property of the target to make sense, suspect your own code
first.** In this case the real causes were all local: an ungated recovery path, a gate held by a
killed process, a DNS failure nobody was checking for. Every one was findable without a theory
about the site.

⇒ **A rule that makes testing expensive should be the first thing you test.**

### ⚠️ A "dry run" must be proven inert before you point it at production

While verifying a scheduler script, I ran it with `shards=0` believing that would be rejected. The
planner clamped `0 → 1` and it **dispatched a real run at the live site**, during the very quiet
period the test was meant to protect. It was cancelled 50 seconds in, still inside `pip install`,
so it never reached the target — luck, not design.

⇒ **A safe-looking parameter is not a dry run.** Either have a real `--dry` path that exits before
any request, or test the wiring against something that cannot reach production at all.

### ★★★ It is the aggregate RATE per address, not the number of sessions

The most expensive wrong belief this project ever held was that **concurrent sessions** were what a
scored site objects to. It was drawn from runs where session count and request rate moved together,
and it cost months of throughput: the fleet was cut to one worker, and every optimisation aimed at
making that worker faster — which is the exact wrong direction.

The one-variable test, four workers behind one address, identical isolation, only the pace differing:

| 4 workers, one IP | ≈requests/min | records opened | survival |
|---|---|---|---|
| top speed | ~56 | **60** | all dead by minute 5 |
| human pace | ~23 | **593** | 2 of 4 ran the full hour |

**Ten times the output and eleven times the survival, from halving the rate with the same four
sessions.** Sessions are close to free; the rate is the wall.

Consequences worth internalising:

- **Add workers, do not accelerate them.** N polite sessions beat one fast one, and the aggregate
  is what you control: N × per-worker rate is a number you choose.
- ★ **The polite configuration is often the FAITHFUL one too.** Here, slowing each worker doubled
  the pointer-event rate — because human-like idle behaviour needs wall-clock to happen in. Top
  speed bought throughput by spending the exact signal that keeps you unblocked. Those two goals
  are usually described as a trade-off; measure before believing it of your target.
- **A per-session budget cannot explain simultaneous deaths.** If several workers with very
  unequal progress stop at the same instant, stop looking for a session counter and look for the
  thing they share.

### ⚠️ A shared limit looks exactly like a coordinated cull

Several sessions stopping within seconds of each other, holding unequal amounts of work, with **no
rejection page** — that was filed here for months as evidence the target was culling our fleet
deliberately. We then produced it on demand, locally, by pushing four browsers behind one address
past the rate limit.

**The signature proves that a shared limit was crossed. It says nothing about intent, and nothing
about which shared resource.** Address rate, uplink, and the local machine all produce it. Do not
name the cause until you have varied one of them.

### ★★★ Scroll BOTH axes, or half the page is unreachable for ever

Every scroll this project ever made was `wheel(0, dy)` — deltaX hard-zero. So any target past the
right edge of the window could not be reached **at any window size, by any amount of waiting**.
The click helper refused it correctly and said "target covered"; the overlay hit-test found
nothing on top, because nothing was on top — the element was simply outside.

Measured cost in one afternoon: 3.5% of record clicks refused, and the *next page* button
unreachable on **39% of listings**, truncating them silently. 1,224 records never opened.

Verified fix, in the exact geometry that failed (744×345 viewport):

    before   target x=1307   scrollX=0     off-screen right
    after    target x=697    scrollX=610   click succeeded

- **A person with a narrow window scrolls across.** Trackpad swipe or shift+wheel, a few uneven
  notches, pointer parked over the content, with the small correction back after overshooting.
- **It is also an empty telemetry channel** — the same family as never wheeling at all. A reader
  of a table wider than their window emits deltaX; we never had.
- ⇒ **Window size becomes a preference, not a correctness requirement.** Small windows stay
  watchable and still work, which matters when watching the browser is how you find bugs.

⚠️ And do not trust `--window-size=` on the command line: six browsers asking for 1440×900 came up
at 958×428, 673×483 and 726×434. Set the bounds after launch through the debug protocol, **verify
the viewport, and log it** — an undersized window should announce itself, not be discovered weeks
later through missing records. Never fake it with device-metric emulation: a real person's browser
has a real window behind its viewport.

### ⚠️ After a paginated redraw, row indices are stale before they are wrong

A "next page" helper typically returns as soon as the FIRST row changes — proof that a swap
*started*, not that it *finished*. Read your row list at that moment and you capture indices into
a table still rebuilding; clicking `nth(i)` then hits a row whose handler has been replaced, **no
request is issued at all**, and it is indistinguishable from the server ignoring you.

4 of 4 such failures in one controlled run came after a page advance; none on page one.

- **Wait for idle plus a short settle before reading the new page.**
- **Verify identity at the moment of clicking** — compare the row's own key against the record you
  meant to open, and skip rather than click the wrong one. Cheap, and it turns a silent
  mis-click into a counted event.

### ★★★ Check that the arms match before you read the number

Three times in a single session I nearly published a confident conclusion from a comparison whose
arms differed in two variables:

| the comparison | what it "showed" | the truth |
|---|---|---|
| our 2 requests per record vs clean runs' spacing | we were bursting | those runs made **1** request per record; a human does ours in 2.0 s |
| 2 workers (slow) vs 1 worker (fast) | parallelism costs throughput | against the matching arm it is **1.91× — linear** |
| 4 workers (fast) dying | concurrency is the limit | the arm also differed in speed; it was the **rate** |

Two of the three would have sent expensive work off in the wrong direction, and the first already
had — a whole test was designed around it.

⇒ **Before interpreting any measurement, write down every variable that differs between the arms.**
It takes one line and it is the cheapest error-check available. The temptation is strongest when
the new number is dramatic, because a dramatic number feels like it explains itself.

### ★★★ Check what your safety guards RETURN, or they become the bug

The most expensive defect in this project's history was a boolean thrown away.

`human_click()` refuses to click a target it cannot reach, on purpose: a covered click sends a
real click to whatever is underneath, and that correlated exactly with getting blocked (0 covered
clicks → 50 records; 1 → blocked at 23; 2 → at 4). It announces the refusal in the log. **The
caller ignored the return value.** So the worker clicked nothing, waited 90–106 seconds for a
modal that had never been requested, reported *"modal did not open"*, and concluded the site had
refused it.

That one omission produced, over weeks: dead workers, a "10-open wall" on cloud runners that four
separate sessions died against, and theories blaming the record itself, its position in the list,
the entry route, a per-session request budget, a burst pattern, concurrent sessions, and the
datacenter address range. Every one of those was built on a symptom **we manufactured**.

What settled it in one line was counting requests instead of reading the DOM:

    [warn] human_click: objetivo tapado — NO hago clic
    [net] 0 responses since the click, causaCivil.php=0 :: []

Zero. The site was never asked. It had never refused anything.

Rules that follow:

- **A guard that can decline must be checked at every call site.** Grep for the function and look
  at each one; a guard whose refusal is ignored is worse than no guard, because it converts a
  cheap skip into an expensive fake failure.
- **Cost the failure correctly.** A refused click costs ONE RECORD. It is not a spent session, not
  a block, and must never trigger a recovery — ours did, and each recovery slept 3, 6, then 9
  minutes before walking back into the same unreachable row.
- **Count it in the run's own verdict.** `refused=33` beside `opens=1009` is a 3% loss you can see
  and chase; silence made the same losses look like the site throttling us.
- ★ **When the DOM says "nothing happened", ask the NETWORK whether you asked for anything.**
  Element state tells you what the page looks like; the request log tells you whether the failure
  is even the server's to explain. That single question separated our bug from a site refusal
  after weeks of arguing about the latter.

### ★★★ Your NAME for a failure is not an observation of it

For most of a day, workers died against a condition recorded in every log and every handoff as
*"the form is wedged"*. That phrase was **my label for "`select_option` timed out after 8 s"**, and
it was carried for hours as though it described something. Whole theories were built on it: that
the address was throttled, that six concurrent sessions were too many, that a particular range of
records was poisoned. Each was tested and each was wrong, at the cost of an afternoon.

The moment the code was made to ask the page instead — one probe, printed on failure — the answer
arrived immediately:

    busy=False  covered_by=None  where=results
    select={opts:232, disabled:false, vis:FALSE, pointerEvents:'auto', spinners:[], sheets:0}

The control was populated, enabled, uncovered, on an idle page, and **invisible**. Everything the
label had implied — load, refusal, contention — was absent from the evidence.

⇒ **When you name a failure, write the observation next to the name, and never let the name travel
alone.** "Wedged" is a diagnosis wearing a symptom's clothes. The test: could a stranger reproduce
your claim from what you wrote down? "select_option timed out" they can; "the form is wedged" they
cannot.

The corollary is cheap and worth doing everywhere: **make each failure path print the state it
failed in** — busy flags, the element's own visibility/disabled/pointer-events, what is on top by
hit-test, which spinners hold content, and where the page thinks it is. It costs a dozen lines and
it converts every future occurrence from an argument into a measurement.

### ⚠️ A tab that is "active" in the nav but not in the panes cannot be clicked

The concrete bug under that label, and it is a general trap for any Bootstrap-style tab or
accordion UI. The nav item carried `active` while its pane had lost `in active` and sat at
`display:none`, with a sibling pane shown instead. **The framework will not switch to a tab it
already believes is current**, so clicking the nav link delivers a real, trusted click that does
nothing at all — and a click helper correctly reports success.

Everything downstream then fails in a way that looks like the site: the form's controls are in the
DOM, fully populated and enabled, and simply invisible, so every interaction times out on an
actionability wait.

- **Detect it by comparing the two states**, not by trusting either: `navItem.active !==
  pane.classList.contains('active')`.
- **Repair it the way a person does** — click a *different* tab, then click back. That forces the
  framework to actually move the active marker.
- **Suspect it whenever a control is present-but-invisible**, especially after a navigation or a
  result render redraws part of the page.

⚠️ And beware the false cure: re-entering the site rebuilds the form and re-selects the tab, so a
recovery ladder *appears* to work and then fails again minutes later. That pattern — recovery
succeeds, symptom returns quickly — is itself a signal that you are treating a symptom whose cause
your recovery merely resets.

### ★★ Re-discovery is the tax you forget to count

An afternoon of sweeping produced, per fleet-hour:

    794 record opens  ->  217 records new  ->  211 that gained the field we were collecting

**27%.** The other ~580 opens re-opened records already held complete, because successive fleets
swept the same slices and the sweep had no idea what was already banked. The run reports looked
excellent throughout — opens per minute, zero blocks, healthy counters — because they measure
*work done*, not *work that needed doing*.

⇒ Once you HAVE a corpus, discovery and completion are different jobs and want different workers:

| | discovery | completion |
|---|---|---|
| picks records by | what the site lists | **what your database says is missing** |
| cost per useful result | 1 / hit-rate | ~1 |
| gets worse as you collect more | **yes** | no |

The discovery worker's efficiency *decays as it succeeds*: the more you hold, the larger the share
of what it finds that you already have. That is the opposite of the intuition that a sweep gets
cheaper once the hard records are banked.

- **Ask the database for the work-list**, and apply your reject filters to it *before* spending the
  expensive act — a record you can skip entirely beats one you open fast.
- **Shard the work-list, not the site's index.** Which records are outstanding changes after every
  ingest, so slicing by the site's own ordering hands several workers the same work.
- **Count useful results, not actions.** "794 opens, no blocks" and "211 fields collected" describe
  the same hour, and only the second is the thing you wanted.

(PJUD, 2026-08-17: 4,143 outstanding at 27% efficiency is ~19 h of sweeping, or ~5 h of targeted
filling at the same measured rate.)

⚠️ **A completion worker cannot open a range it has never discovered, and says so in a way that
looks like a block.** Pointed at a month the database held nothing for, the fill run reported
`nothing-searched` and was read as a refusal — there was no work-list, so no search was ever
issued. **Fill and sweep are not interchangeable**: a new window needs discovery first, and the
failure mode of choosing wrong is a green run that did nothing.

(PJUD, 2026-08-18.)

### ⚠️ A scraper with no ingest has no output

Worker H harvested 2,228 records across an evening, 1,659 of them carrying the exact field the
whole exercise existed to collect. The database still showed **13**. It wrote JSON to disk and
nobody had built the path into storage — and I quoted delivery estimates twice without noticing,
because the run reports were full of healthy numbers.

**A run's own tally is not evidence that the data landed.** Count it where it is meant to end up,
not where it is produced — the same rule as judging a probe by whether the measurement was
written, and the same failure as a green step that ingested nothing.

### ★★ Copy the BEHAVIOUR, not the interval

Having measured a person at 13.1 s between records, the obvious move is to wait 13.1 s between
records. It is the wrong move, and an operator watching the result named it in one line: *"it
takes a while randomly moving from record to record — why not just go directly to the next one?"*

A person's 13 seconds is **reading the list, deciding, travelling to the next row, clicking it**.
Reproduce it as a delay and you get a worker that is simultaneously *slower than the human* and
*less like them*: eight seconds of pointer motion with no destination, which is a behaviour no
person has ever produced. The interval is an OUTPUT of what they did, not an input.

⇒ Copy the acts and let the interval fall out of them. Here that meant: aim the pointer at the
next row, travel to it, click — and the gap becomes however long the travel takes (~8-10 s, well
inside the observed 5-27 s range) without a single second of invented waiting.

The same test applies to every number you lift off a recording: **is this a thing they DID, or a
consequence of things they did?** Copy the first kind. Derive the second.

### ★★ A fallback for a name you invented manufactures success

Writing a prototype against an unfamiliar module, I guessed at three function names and hedged
each one:

```python
rows = C.result_rows(p) if hasattr(C, "result_rows") else []
kind, el, why = ojv.settle_search(...) if hasattr(ojv, "settle_search") else ("results", 0, "")
```

`result_rows` does not exist. So the run reported **`search -> results in 0s, 0 rows, DONE`** and
exited green, while the page in front of it held 117 records and 21 matching rows. The hedge did
not make the code robust — **it converted "I called something that isn't there" into a clean
result nobody would question.** The same shape as swallowing a traceback with `|| echo`, and the
same lesson: *a failure that looks like an answer is worse than a crash.*

- **Call the real function. Let a wrong name raise on the first run** — that is the cheapest
  possible failure and it happens before any live request is spent.
- **Verify the symbol instead of guarding it.** One `hasattr` sweep over the names you intend to
  call, run once at import, tells you the truth without hiding it at the call site.
- Corollary for edits: **grep the file afterwards to confirm the change is on disk.** A patch that
  reported success but never landed is what let this ship — the search block I "fixed" was still
  the guessed version, and the run's fake verdict is what made that invisible.

### ⚠️ The profile directory is the lock, not the port

A relaunch hung forever with no error: the previous browser had survived, and although the new one
asked for a *different* debug port, it wanted the **same `--user-data-dir`** — which the old
process still holds. Killing by port, or assuming a dead script means a dead browser, both leave
this. Check for a live process on the profile before launching, and remember the inverse too: a
browser started by a script that is `kill -9`'d does **not** always die with it, so the evidence
you wanted may still be sitting there — or the lock you did not want.

### ★★ Your instrumentation will lie to you more often than your scraper does

On the day this section was written, the scrapers ran all day and the *monitoring* produced four
false readings in a row. Every one looked like a real event:

| what it reported | what was true | the bug |
|---|---|---|
| "5 of 4 workers alive — duplicate!" | 4 alive | the ingest script's filename **contains** the worker's, so it matched |
| "0 of 4 alive" for three hours | 1 alive and working | `(...).Count` returns **empty** on a single object in PowerShell; needs `@(...)` |
| "10 orphaned browsers" | one healthy browser | a single Chrome **is** ~10 processes |
| two green probe runs "measuring" | two setup crashes | `\|\| echo "a refusal is the measurement"` swallowed tracebacks |

The last one is the dangerous shape: **a probe whose failures look like results launders a bug
into a number somebody will later plan against.** Its fix is the general rule — decide green/red
on whether the measurement was *written*, never on the process exiting.

Rules that follow:

- **A monitor must distinguish "nothing wrong" from "I could not tell".** Silence and success must
  not look identical. If your check cannot run, say so loudly.
- **Count with the array form, match with the exact form.** Both classic bugs above are one
  character of shell each.
- **Prefer evidence of life over evidence of absence.** A process list that comes back empty
  because of permissions is *ignorance*, not death — never kill or restart on it alone.
- **When an alarm fires, verify before acting.** Three of the four above would have caused a
  harmful intervention on a healthy fleet.

### ★★ A worker you cannot see needs a WINDOW, not just a black box recorder

Failure screenshots (`--shots`) were built after four remote sessions died identically and nobody
could say what was on the page. They worked — and they were still not enough, because a CI
artifact can only be downloaded **once the job has ended**. You get to study the crash; you never
get to watch the approach. Every diagnosis stayed a post-mortem, and a post-mortem cannot answer
"is it doing the right thing *now*".

So give the worker a window. It is much less work than it sounds:

- **Publish over whatever the two ends already share.** Here that was the Postgres the runner
  already writes to, so there was no tunnel, no new secret, no port opened, and it works
  identically for a Chrome on the desk and a runner in a datacenter. Ask what both sides can
  already reach before building transport.
- **A jpeg plus the log tail is the whole payload.** Do not invent a second status vocabulary —
  the narration the worker already logs *is* its phase description, and a parallel one drifts out
  of step with the log the first time either changes.
- **Instrument the WAIT, not the failure.** Nearly all of a polite scraper's wall clock is pacing
  gaps and wait loops, and that is exactly where a hang is indistinguishable from patience. Put
  the frame grab inside the idle helper and inside the "wait for the thing to appear" loop, and
  coverage comes for free. ⚠️ Which means every pacing wait must go **through one helper**: a
  `time.sleep()` that skipped it left a live view frozen for 20 of every 25 seconds, looking
  exactly like the hang it exists to distinguish.
- **Send a frame only when the picture CHANGED**, and have the viewer send back the sequence
  number it already holds. A page sitting through a 25 s wait then costs one frame, not five, at
  both ends. This is the difference between a watchable tool and one you turn off to save bandwidth.
- **A stale frame must not look live.** Refresh the timestamp even when the picture is identical,
  and show its age — otherwise "nothing is moving" and "the worker is dead" are the same picture.
- **The watcher must never be able to break the run.** Short explicit timeout on the capture
  (a screenshot library default of 30 s will stall you at the worst possible moment), every path
  swallowed, and self-disable after N consecutive errors. A spectator that can stop the game is
  worse than no spectator.
- ⚠️ **And it is a variable.** Screenshotting occupies the renderer's main thread. It sends nothing
  to the target — but "no requests" is not "no difference", so do not leave it on for a
  one-variable test unless the arm you are comparing against carries it too.

(PJUD, 2026-08-16. `live_view.py` / `watch_live.py` — ~200 lines each.)

---

### ★★★ The interesting frame is never the last one — and the channel that carries it out carries instructions back

A failure screenshot tells you where a run **ended**. It cannot tell you how it got there, and
"how it got there" is the entire question. Two cloud runners died on 2026-08-18 with a log that
read: click delivered, forty-five seconds of silence, then a WAF rejection page. Whether the
refusal arrived at second 1 or second 40 decides whether the click was the trigger or a bystander,
and nothing in the run had looked at the page in between.

So photograph every action, both sides of it:

- **Hook the chokepoint, not the call sites.** Every action this scraper takes goes through one
  `human_click`, so the trace wraps that one function and no call site can be forgotten. Wrapping
  forty callers is how instrumentation ends up with holes exactly where the odd paths are.
- **The `after` frame belongs in a `finally`.** An action that threw still leaves a picture of what
  it left behind — the one frame you always want and never have.
- **Sample the silent waits.** The blind spot is never the action; it is the poll loop after it.
  A frame every three seconds inside "wait for the thing to appear" puts a timestamp on the
  refusal, and a timestamp is most of the diagnosis.
- **Scope it, and budget it.** The arrival is ~30 frames and is where remote runs actually die; a
  whole shift is thousands. `--trace entry` vs `--trace all`, plus a hard frame cap, is the
  difference between a diagnostic and an incident.
- **JPEG, and one contact sheet.** Ninety frames is ~6 MB as jpeg and ~34 MB as png, and a zip of
  loose images is a picture that got captured and still never looked at. Emit one self-contained
  HTML with the frames in order and each frame's own account beside it.

Then notice that the channel is bidirectional. A cloud runner has no inbound network, no screen and
no shell — but it already polls a database, so it can **stop before each action, publish the frame
it is looking at, and wait to be told go / run / abort**. Single-stepping a scraper through a WAF
you do not understand is worth more than any number of post-mortems, and it costs one table.

- ⚠️ **A paused session must keep moving.** A browser frozen stone dead for five minutes — no
  pointer, no idle motion — is a longer, louder empty telemetry channel than anything this project
  has ever fixed. Run the idle-motion helper between polls; a pause should look like a person
  reading, which is what it is.
- ⚠️ **Default to STOP on silence.** If nobody answers within the timeout, end the run. A runner
  nobody is watching should not quietly finish the hour on its own — that is precisely the
  unattended run the step mode was built to replace.
- **An operator saying stop is not a crash.** Exit clean and say so, or the traceback reads like
  the target did something.

(PJUD, 2026-08-18. `stepgate.py` / `step_console.py` / `trace_sheet.py`, and `cdp_scrape.step()`.)

⚠️ **And then check that the eyes are actually WIRED, in every worker.** Worker A carried its own
`shot()` and its own `SHOTS` global and never set the shared module's — so every capture on the
*shared* entry path was a silent no-op for that worker, for as long as it had existed. The
workflow passed `--shots`, uploaded the artifact, and the artifact was empty; six entry refusals in
a row produced zero frames while the run looked correctly instrumented from the outside. Two copies
of one facility, one wired and one blind, is the same failure this handbook already records for the
rejection matchers — and instrumentation is where it hurts most, because the thing that fails is
your ability to see anything fail. **Grep for every copy of a capability before trusting any of
it, and share the counter too: two writers into one directory with private counters overwrite each
other's `001-*.png`.**

(PJUD, 2026-08-18.)

---

### ⚠️ A literal `%` in an argparse help string only crashes `--help`

`"refused 3.5% of rows"` in a help string is read as the format spec `%o`, and argparse raises
`TypeError: %o format: an integer is required`. Every real invocation works; only `--help` dies,
so it survives in a mature CLI indefinitely — this one had been there for days and was found by
grepping for it after `--help` failed on an unrelated change. Escape as `%%`, and run `--help` in
whatever passes for a smoke test.

(PJUD, 2026-08-18.)

### ★★★ A refusal that is DETERMINISTIC and per-item is not a rate verdict

Two cloud runs, dispatched hours apart, were refused at **the same record**, at the same point in
the visit, with the same counters — after nineteen records in the same session had been processed
identically and successfully. Everything this project had learned about being blocked said *rate*:
cool off, slow down, add jitter, add workers instead of speed. None of it applies here.

**A rate verdict is a function of HOW MUCH you have done. This was a function of WHICH item.**

That single distinction re-sorts the whole suspect list:

| if the refusal is… | then it cannot be… | and the test is… |
|---|---|---|
| deterministic on one item | pacing, burst, session age, position, address reputation | **process that item alone, from a fresh session** |
| reproducible across sessions | anything about the session | change ONE thing about the *request*, not the schedule |
| preceded by N identical successes | the shape of the action in general | what is different about **this** item's payload |

⇒ **Before theorising, count the successes that came first.** Nineteen identical acts that worked,
then one that did not, is nearly a proof by itself — and it is a proof you already own, sitting in
the log, costing nothing to read. Every reflex the project had built (slow down, back off, fewer
sessions) would have made the run longer and failed at the same record.

⚠️ **And ask what YOU do on that request that a person does not**, because per-item determinism
points at the payload, and the payload is where our own shortcuts live. The two suspects here were
both behaviours, not accidents of the target: a `<select>` driven by `.focus()` plus arrow keys —
so it receives keystrokes having never been clicked — and two flat `wait_for_timeout()` sleeps that
were measured on a residential link and inherited unchanged by a datacenter one. **A constant
measured in one environment is a guess in the other**, which this handbook already records twice.

(PJUD, 2026-08-18. Unresolved at the time of writing: the next test is to read the per-item token
the request carries and compare it against one that succeeds.)

---

### ⚠️ Chokepoint instrumentation has exactly the coverage of your chokepoint

The step trace above wraps **one** function, on the argument that every action goes through it —
and among *clicks* that is exactly right, which is why it has no holes there. Then the failure
happened in the one action that is not a click: a dropdown driven by focus and arrow keys, which
passes through no chokepoint and produced **no frame at all**.

The result is a nine-second hole in the middle of the only failure we have:

```
frame 0101   t+975.4   after the row click — correct row highlighted
   (modal opens · first tab parses 28 rows · the switch fires · the WAF refuses)   ← no frames
frame 0102   t+984.5   modal open and correct, content EMPTY, rejection box overlaid
```

Everything about the diagnosis had to be inferred from the two frames bracketing the gap.

- **Enumerate your action verbs, not your call sites.** "Every action goes through `human_click`"
  was true of clicking and silently false of typing, selecting, scrolling and key-pressing. One
  chokepoint per verb, or one wrapper they all call.
- **The gap is self-concealing.** An untraced action leaves no marker; you discover it by noticing
  a *time* discontinuity between two frame numbers, which nobody looks for until the trace has
  already failed to answer the question.
- **Instrument the suspect FIRST.** The action most likely to be refused is the one you least
  understand, and it is therefore the one most likely to sit outside a chokepoint you designed
  around the actions you did understand.

(PJUD, 2026-08-18. The same shape as the blind copy of a facility recorded above — there the eyes
were unwired, here they were pointed at the wrong verb.)

### ★★★ Ask the data you already hold before you ask the site

"How many documents per record?" decided the pacing, the worker count, the warning printed at
startup and whether the job was one launch or three. The obvious way to find out is a probe: open
a session, visit some records, count. That costs the scarcest thing the project spends.

It was already on disk. 188 banked JSON files from earlier runs held **23,326 sub-rows**, and
parsing them took one command and no requests:

    99.8% of rows carry a document form (23,286 of 23,326)
    3.5 documents per record, median 3
    two endpoints, 60/40 — so the input NAME cannot be assumed

Every one of those changed the build. The density set the request-rate estimate; the 60/40 split
is why the form's input name is read from the DOM instead of hardcoded; the per-record count made
the cost statement concrete enough to argue about. Confirmed live on the first two records: 4 and
3 documents — exactly 3.5.

- **Your own output is a corpus.** A scraper that has run for weeks has already answered most
  questions about the shape of the target; it just answered them into files nobody queries.
- **A free measurement beats a cheap probe**, and a cheap probe beats an assumption. The ordering
  is obvious and gets skipped anyway, because writing the probe feels like the real work.
- **Say what the job will cost before it costs it.** "2 requests per record becomes 5.5" is a
  sentence that can be checked, disputed and acted on. "It might be a bit heavier" is not.

(PJUD, 2026-08-19.)

---

### ⚠️ An endpoint's reputation has a DATE and a DOSE on it

One endpoint in this project had been the prime suspect for months: it refused 16 and 19 times in
a day, and a whole worker was redesigned around never touching it. Six concurrent workers then
pulled **3,370 files through that same endpoint in 92 minutes with zero refusals**.

The temptation is to conclude it was never the problem. That is as unfounded as the original
verdict. **Two things differed between the arms**: the old worker fetched 40+ files per record and
this one fetches 3.4, and everything else about the session's behaviour had been rebuilt in
between. What can honestly be claimed is narrow, and narrow is what makes it useful:

> at ~20 fetches/minute behind this kind of session, this endpoint is not the wall we thought.

- **Re-read a blocked-endpoint story as a story about DOSE per session**, not about the URL.
  *That endpoint blocks* and *forty of those per record blocks* predict the same past and
  different futures, and only one of them is worth redesigning a worker around.
- **A reputation earned under old behaviour expires when the behaviour changes.** Every pacing
  number in this project turned out to be compensation for something else; endpoint fear is the
  same kind of debt, and it is paid off the same way — by re-measuring, not by remembering.
- **Say which variables moved.** A clean run against a feared endpoint is evidence, and writing it
  down as *it is fine now* throws away the half of it that was actually measured.

(PJUD, 2026-08-19.)

---

### ⚠️ A one-hour token means the expensive act cannot be split from the cheap one

Every document behind this site's rows is fetched with a URL carrying a JWT: `iat`, `exp`, and
**one hour between them**, minted fresh each time the page renders, with an opaque ciphertext
payload.

That single fact rules out the design everybody reaches for first — *collect the links now, fetch
the files tonight, out of hours, in bulk*. There is no "later": the link is dead before any queue
drains, so **every file costs the page-open it hangs off**, and the fetch must happen while the
right view is on screen.

- **Decode the token before designing around it.** It takes one command. Discovering the hour
  limit after building the deferred-download queue costs the queue.
- **Rotating opaque tokens also weaken a whole class of hypothesis.** "That record's token
  contains something the WAF rejects" cannot be true of a value that is different ciphertext on
  every render — worth knowing before spending a session testing it.

(PJUD, 2026-08-19. Same shape as the option values the select helper already refuses to compare
against, for the same reason: never verify against a value that rotates.)

---

### ⚠️ A consumer that hand-lists its tables drops the one you just added

The run fetched the files, verified every one, uploaded them all, printed `7 link(s) returned`,
wrote five tables and finished **green**. The document count in the database did not move.

The ingest imported its table order from a *sibling* ingest whose worker is metadata-only and
produces no documents — so the row builder built the document rows and the write loop, iterating a
list that never mentioned them, threw them away. Nothing errored. Every counter on the path was
healthy, and each one was counting something real.

- **Take the canonical list from whoever owns the builders**, not from a sibling consumer whose
  needs are a subset of yours. A hand-maintained list of tables/fields/columns rots silently the
  first time the producer grows.
- **The failure is invisible from every intermediate counter.** Bytes fetched, files verified,
  uploads returned, rows upserted — all true, all beside the point.
- ⇒ **Count it where it is meant to LAND**, and print that number at the end of every ingest. It
  is the only line in the run that was ever going to say so. (Third time this rule has paid out in
  this project, each time one layer further in than the last.)

(PJUD, 2026-08-19.)

---

### ⚠️ A measuring tool has exactly the coverage of its glob

Six workers were pulling files at full tilt and the project's own rate meter printed
`0.00/min` and `[ok] within the range this address has sustained cleanly`. It globbed one
worker's log directory — written when there was only one worker — and had no pattern for the new
kind of request at all. The launcher told the operator to use it.

**A measuring tool that cannot see the work is worse than no measuring tool, because it answers
the question with a reassurance.** An absent tool sends you looking; a blind one ends the enquiry.

- **Grep for every producer before trusting a consumer.** Same rule as the duplicated detectors
  and the unwired screenshots — and it lands hardest on measurement, because what fails is your
  ability to know anything is failing.
- ⚠️ **One line can be N events.** The new worker reported a whole record's files in a single log
  line (`docs: 4 pdf`), so the count had to be SUMMED, not counted. Counting it would have
  under-reported the rate by 3.5× — in the direction that reads as headroom.
- **Report separate axes separately.** Two endpoints with different histories should not be
  merged into one number, or you end up comparing a new rate against a ceiling measured for
  something else and calling the result safe.

⇒ And the estimate the tool corrected was out by **2.7×**: the projection multiplied a throughput
figure measured on small pages by a per-record cost measured on large ones. *Measure it, do not
derive it* — one command answered what an afternoon of arithmetic got wrong.

(PJUD, 2026-08-19.)

---

### ⚠️ Watch the channel where failure actually speaks

A worker was launched detached and a watch armed on its stdout log, filtering for progress lines
and for the words that mean trouble. Ten minutes later the watch had said nothing, which read as
"still starting up". The process had died **one second after launch**: a shell had split a
command-line argument on its spaces, the argument parser rejected it, and the message went to
**stderr** — a file the watch was not reading. The stdout log it *was* reading was zero bytes, and
a zero-byte log looks exactly like a process that has not printed yet.

- **If the process died right now, would the watch emit anything?** Ask it before arming. If the
  answer is no, the filter is not selective, it is blind.
- **Silence is the one signal with two meanings** — healthy-and-quiet, and dead. Anything that
  makes those distinguishable (a heartbeat, a stderr tail, an exit notification) is worth more
  than a tighter filter on the happy path.
- **Quote every argument containing a space, inside the string.** A launcher that joins an
  argument array with spaces will hand three arguments to a program expecting one, and the error
  arrives instantly, on the channel nobody is watching, at the moment that looks most like normal
  startup.
- **Smoke-test down the path you are about to trust.** The first attempt used a hand-built command
  rather than the launcher, so it tested something that was never going to run again. Give the
  launcher a "just N records" flag instead.

(PJUD, 2026-08-19.)

### ⚠️ "Bring it up to date" is two jobs, and the completion worker cannot do the first

A corpus stops wherever collection stopped, not at today. So *bring last month up to date* means
**discover, then complete** — and the completion worker, which picks its work-list out of the
database, is structurally incapable of the first half. Pointed at a window nothing was ever swept
for, it does not fail: it finds an empty work-list, issues no requests at all, and reports
something that reads exactly like a refusal.

- **Sequence it explicitly: sweep, ingest, then complete.** Each stage's input is the previous
  stage's *banked* output, not its run report.
- **It costs two opens per new record** when the discovery worker deliberately does not collect
  the expensive part. That is a fine price for a short catch-up and a bad one as a standing
  pattern — if it becomes routine, make discovery take the expensive part in the same visit
  rather than running the whole pipeline twice.
- **Never run the two fleets at once.** They share the address, and aggregate rate is the wall.
  The launcher should refuse, not trust the operator to remember.

### ⚠️ Resumable state belongs to the QUERY that built it

The discovery worker records completion **per container, with no window attached** — so a state
file from last month's window, resumed against this month's, marks containers "done" that were
never searched for these dates. Silent under-collection, reported as a clean finish.

The worker refused at startup, which is right. The failure worth recording is what that looked
like from outside: **all four workers launched, died into stderr, and left four empty stdout
logs** — indistinguishable from four workers still starting up. The check belongs in the launcher
too, *before any browser opens*, naming every mismatch and the remedy.

⚠️ **Archive such a file, never delete it.** It records which records were REJECTED BY A FILTER —
and that is exactly the knowledge that stops you buying those opens again. Deleting it looks like
tidying and is a bill.

### ⚠️ A multi-statement ingest has an inconsistent MIDDLE

An ingest that writes several tables and then repairs one of them is not atomic from the outside.
Sampling the database while it runs showed 21 records carrying the value a *superseded* row had
set, and it looked exactly like a regression — the newer verdict overwritten by an older harvest.
It was not. The bulk upsert writes whatever the newest *unfiltered* record says, and a targeted
UPDATE that restores the filter's verdict runs afterwards, in the same job.

- **Check the end state, not the middle.** A job that prints a final tally prints it for a reason;
  read that line rather than querying underneath a run in progress.
- **Know which of your writes is the authority for each column**, and in what order they fire. Two
  writers to one column is fine when the order is deliberate and documented, and indistinguishable
  from a bug when it is not.
- ⇒ And this is why the filter's verdict must be *stored*: the next pass builds its work-list from
  that column, so a retry offered ONE record instead of twenty-two. Recording why something was
  rejected is not bookkeeping — it is what keeps the expensive act from being spent again.

(PJUD, 2026-08-19.)

### ⚠️ A tool's default and its launcher's default are two different defaults

The sweep worker's `--only-proc` defaults to *empty* — store everything. Every launcher and the
ingest use a real filter. A new launcher that simply omitted the flag would have widened the
corpus's own definition for one window only, and nothing downstream would ever have flagged the
inconsistency: the rows are valid, they are just answering a different question from their
neighbours.

⇒ **When you write a second launcher for an existing tool, diff its arguments against the first
one** and carry every semantic flag across deliberately. The dangerous ones are those whose
default is *permissive*, because omitting them produces more data rather than an error.

(PJUD, 2026-08-19.)

### ★★★★★ SPLIT THE SCRAPER IN TWO: SPECS AND SETTINGS

The most useful architectural line this project has drawn, and it took four workers and two months
of divergence to find it:

```
   SPECS      how human the worker is       one shared engine   ALWAYS THE BEST YOU HAVE
   SETTINGS   what job it does, and where   the workers         chosen per run
```

**A fidelity fix that lives in a worker protects one worker.** Four workers meant four behavioural
engines, and they silently drifted apart because nobody diffs four files against each other. Three
months after the newest one was rebuilt from a recorded human session, the other three were still:

    typing into `readonly` input fields  (an act no user can perform)
    driving every dropdown with ~54 keystrokes  (the recorded human emitted ZERO all session)
    emitting no pointer motion at all between clicks  (the human: 25.8 moves/s on 98% of seconds)
    never scrolling horizontally  (so a wide table's right-hand column was unreachable)

And the day this was noticed, the *discovery* pass — the job that must visit pages it has never
seen — was running on the least human worker of the four.

- **Enumerate the acts, then grep every worker for each one.** One table settled it: dates,
  selects, pointer presence, sideways scroll. Four rows, four columns, and the answer was obvious
  the moment it was written down and invisible before.
- **The engine must not import a worker.** A constant that looked worker-owned (`CIVIL = "3"`) was
  a property of the *site*, and moving it with the engine broke the last dependency.
- ⚠️ **A module-level global is part of the facility.** The speed multiplier lived beside the
  reading-time function; moving the function without moving who *writes* the global would have
  left the worker setting, printing, ramping and reporting a value that nothing read. The log line
  reporting the speed reads the wrong copy, so nothing would ever have said so.

⇒ The end state is ONE program whose settings pick the job. Everything behavioural is shared and
is always the best known; everything else is an argument.

### ⚠️ THE OPTIMUM IS NOT THE MAXIMUM

Once fidelity is a first-class goal there is a strong pull toward "more human = more events". It
is wrong. **A pointer emitting 40 moves/s is as anomalous as one emitting 0** — the target is the
recorded human's *distribution*, and being above it is as distinguishable as being below.

Which means every spec needs a measured value, not a direction — and **no spec may be turned up
without a recording that justifies the new number.**

### ⚠️ Motion during a wait must have a DESTINATION

"Keep the pointer alive while waiting" is right, and the obvious implementation — a small tremor —
is the one variant already measured to produce nothing. Vibration in place **crosses no element
boundaries**, and `mouseover` fires only on crossing one, so it generated exactly zero of the
channel it was added to fill.

The recorded human during a wait was not trembling; they were **travelling over content** — 25.2
mousemove/s and 6.4 mouseover/s *while a record loaded*. Aim at something and traverse it.

(Physiological tremor is real and may be worth adding on top, if the defence reads raw coordinates.
It cannot replace travel, and it is unproven.)

### ★★ Two kinds of wait, and one primitive that does both

    wait for the SITE to answer      driven by the server   ->  a CONDITION, never a duration
    wait because a HUMAN is not instant   driven by the person   ->  a DURATION, from a distribution

Conflating them cost real data here: a cleanup that removed "padding" also removed the pause after
an AJAX control change, so the page was parsed before it had re-rendered and records were banked
with an empty section *while the action itself had succeeded*. Silent loss, from an over-applied
rule.

⇒ The protocol, stated once: **act → wait for the reaction (condition) → pause as a person would
(duration) → act again**, with the hand moving over content for the whole of both waits. That is
one primitive, not two, and it belongs between *every* action — nothing a person does is instant.

⚠️ And then check it is actually applied. Eleven raw `sleep`/`wait_for_timeout` calls survived in
the *most* human worker; each one is a stretch of dead telemetry in the middle of a session built
to look alive.

(PJUD, 2026-08-19. `human_engine.py`.)

### ★★★★★ Watch a human use the site. You are not scraping what you think you are scraping.

Forty minutes of a recorded human session produced **four request endpoints that appeared nowhere
in the codebase** — and the biggest of them outnumbered the one endpoint we did collect **five to
one**. It was the document class the operator used most, and we had fetched exactly zero of them,
for months, across a hundred thousand records.

The parser was looking in the right column and for the wrong *shape*: a `<form>` where the site
puts an `<a onclick=…>`. Across 117,173 rows it matched none.

⇒ **"We never look for it" and "these records don't have one" produce IDENTICAL EVIDENCE: zero.**
That is what makes this class of gap invisible, and no amount of reading your own code finds it —
your code is the thing that is wrong. Only watching someone who knows the site does.

- **Record the network, not just the screen.** The endpoint list was the finding. A screenshot of
  the same session would have shown a person clicking icons and taught nothing.
- **Diff the endpoints you saw against the endpoints you implement.** One `grep` per endpoint name
  turned "here is a busy log" into "four of these do not exist anywhere in our source".
- **Ask the operator where things live, then verify BOTH answers.** Told the control was "usually
  in the header, sometimes in the row", we found it in the row in four of six records — the
  majority. Had we checked only the header we would have called the other answer rare.
- ⚠️ **Three rows is not a sample.** The row-level control sat at rows 3, 6, 7 and 9; a dump of the
  first three rows showed an empty column every time and produced a confident wrong conclusion.

### ⚠️⚠️ A modal reused for every record will hand you the PREVIOUS record's contents

The folder listing the documents is **one global element**, re-populated per record. The wait
condition was the obvious one — *"is the list non-empty?"* — and it is satisfied INSTANTLY by the
previous record's rows.

The result was documents filed under the wrong record: two different lenders, two different
debtors, **byte-identical PDFs under both ids**. A third of everything the new code had ever
fetched. The first smoke test had it too, and was reported as a clean success.

This is the same rule this handbook already states about paginated results — *freshness must be
proven by the network, not the DOM, because the site leaves the previous content on screen* —
rediscovered three months later in a different widget by the same author.

- **Every reused container needs a freshness proof, not just tables of results.** Modals, drawers,
  side panels, detail panes: if it is populated by AJAX and reused, "it has content" is not
  "it has THIS record's content".
- **Use a per-render token as the signal.** These rows carry short-lived JWTs minted per render, so
  "the tokens changed" is a reliable proof where "the row count changed" is not.
- **Fail CLOSED.** If freshness cannot be established, take nothing and say so. A missing document
  is a gap; a mis-attributed one is a corruption that nothing downstream can detect, because the
  file is named after the wrong record.
- ⚠️ **Byte-compare your output across records.** One md5 pass over the downloads found it in
  seconds. Identical bytes under two ids is nearly always a staleness bug, and nothing else in the
  run reports it — every counter was healthy and every file was a valid PDF.

### ⚠️ A nested modal's backdrop is not the outer modal's backdrop

Closing an inner modal leaves a backdrop behind for a moment, so the next click is refused as
covered. The existing helper waits for **no backdrop at all** — correct for a top-level modal, and
impossible for a nested one, because the modal underneath keeps its own the whole time. Bootstrap
STACKS them.

⇒ The condition is that the backdrop count **returns to what it was before you opened**, not that
it reaches zero. A helper written for depth 1 is not automatically right at depth 2.

### ★★★ Enumerate always, fetch selectively — and never gate the ENUMERATION on a name

When a container lists items and only some are wanted, the listing is usually **one request for
all the labels** while fetching is one request each. So record the entire inventory every time and
download only what matches.

This is not tidiness, it is the difference between two failure modes:

    matched nothing        -> "we looked, and this record has no contract"
    never enumerated       -> "we never looked"

A name filter alone cannot tell those apart, and the second silently looks like the first.

⚠️ **The labels are free text typed by whoever filed them.** Real examples from one afternoon:
`'1. CONTRATO DE ARRENDAMIENTO'`, `'pagare'`, `'mandato claudio altamirano'`, `'MUTUO'`,
`'EP MUTUO HIPOTECARIO Repertorio Nº 10.180-20'` — numbered or not, any case, sometimes containing
a person's name, and for one particular counterparty abbreviated to `'CTO'`. **Any pattern will
miss.**

★ It paid out on the first real run: a label the default pattern did not match turned up in
**three of five** records and was, on inspection, the very instrument being sought under another
legal name. That was learnable only because the non-matching labels had been recorded anyway.

### ⚠️ A sample maximum is not a maximum

"A record can hold six" went into a code comment and a commit message as though it were a bound.
It was the largest of five observations. The seventh record had nine.

It mattered because that number drove the requests-per-record estimate, and therefore the pacing.
**The cheap test is to run the enumeration with a filter that matches nothing** — every container
opened, nothing downloaded — which yields the true distribution for one request each.

### ⚠️ A probe must obey the same gate as the worker

A diagnostic that took the first N rows off the results page spent four expensive opens on record
types the project does not collect — and worse, **the evidence it produced was about the wrong
population**. Every "look, there are several of these controls!" observation came from those
out-of-scope records; the in-scope ones had at most one.

⇒ **A probe that samples a different population than the worker answers a different question, and
nothing in its output says so.** Reuse the worker's own selection function, not a fresh
approximation of it.

(PJUD, 2026-08-19.)

### ★★★★★ Measure the DUTY CYCLE, not just the rate — you are probably emitting too much

The first time this project recorded its own scraper with **the same instrument it had used on a
human**, the result inverted everything it believed about its own behaviour:

    scraper    93% of seconds active,  7% silent     21.0 events/s active    19.5 per WALL second
    human      46% of seconds active, 54% SILENT     25.1 events/s active    11.6 per WALL second

Per *active* second the scraper sat at 84% of the human — the number the project had been quoting
for weeks, and the reason every plan said "we are under, emit more". Per *wall* second it emitted
**68% MORE than the human**, because it almost never stopped.

The structure matters more than the average:

    human    129 silent stretches in 40 min   median 6.1 s   p90 28.3 s   max 60 s   (29 of 15-60 s)
    scraper    5 silent stretches in 3.6 min  median 3.0 s   p90  8.2 s   max  8 s   (none over 15 s)

**A person works in bursts separated by real stillness. A generator hums.** Every spec being tuned
was a RATE; this is a RHYTHM, and it is the one an observer notices first — you can match a human's
events-per-second exactly and still be the only session on the site that never once pauses to think.

- **Report per-active-second AND per-wall-second, always, with the silent fraction beside them.**
  Either alone is a trap, and the trap is directional: an always-on generator has almost no
  excluded seconds while a human has more excluded than included, so comparing the two averages
  compares two different populations of second.
- ⚠️ **You cannot be UNDER on a metric that excludes the silence.** Three separate wrong
  conclusions in one afternoon came from that single confusion — "we emit 16/s against 25", "the
  idle stretches emit 5/s", "the setup path is where the pointer dies" (it ran at the same rate as
  everywhere else). Each was a real measurement compared against a differently-defined one.
- **Fix it by STOPPING sometimes, never by moving more slowly.** The human's rate while moving is
  HIGHER than the scraper's. Lowering the rate produces the same wall-clock average and a
  completely different distribution — which is the thing being measured.
- ⚠️ **And notice what this does to "more presence is more human".** That instinct drove every
  improvement here for a month and was right until it wasn't. Past a point, adding presence makes
  you the least human thing on the site. *The optimum is not the maximum* — and the spec where it
  bites is the one nobody is looking at.

⚠️ **The honest cost.** Matching a human's duty cycle roughly HALVES throughput per wall-hour,
because half of a human's session is spent not touching anything. That is a decision, not a
measurement. But this project's own history says the trade usually pays: every time it chose
fidelity over pace, throughput went UP within a week, because the pacing that had been
compensating for bad behaviour could then be removed.

(PJUD, 2026-08-19. Found by attaching the human recorder to a running worker — an experiment that
required no new code and had never once been run.)

### ★★★★★ "Per WHAT?" — the same denominator error three times, the third inside its own fix

The duty-cycle fix above shipped at **1.86 stops/min and 19% silent** against a 59% target. Two
diagnoses were guessed from the output and both were wrong. The third attempt logged **what was
actually drawn**, turning the question into a subtraction:

    drawn, in-run   n=11 over 5.9 min   mean 6.2 s   median 2.0 s   max 36.6 s
    drawn, offline  n=166               mean 12.3 s  median 6.7 s   max 59.8 s
    operator        n=129 over 40 min   mean 10.9 s  median 6.1 s   max 60.4 s

The sampler was **fine**. The deficit was entirely in **how often it was called**:

```python
if random.random() > (SILENCE_PER_MIN * window_secs / 60.0):   # 3.23 per minute of... WHAT?
```

That is 3.23 stops per minute **of covered window**, and the call sites only ever bracketed reads
and causa loads. Search waits, form building, navigation, ingest and modal closes had probability
**zero**. 3.23 per covered minute arrived as 1.86 per wall minute.

⚠️⚠️ **The active-seconds-versus-wall-seconds error for the third time in this project — committed
inside the fix for the second one, by the author of the entry above warning about it.** A rate is
meaningless until you say what it is *per*, and the denominator drifts silently because it is never
written down: it had quietly become "seconds a call site happens to bracket".

**Fix: a deadline that accrues in real time and is discharged at the next boundary**, so uncovered
stretches build debt instead of dropping their stops. Call sites still choose WHERE (only at
boundaries — a person never freezes mid-drag); the scheduler alone owns WHEN.

⚠️ **It bit a FOURTH time, one line into the fix.** Re-arming the deadline *after* each stop means
the gap only elapses while working, so its mean must be the mean **active** stretch, not the mean
wall interval:

    expovariate(SILENCE_PER_MIN / 60)  -> mean gap 18.6 s -> 2.04 stops per WALL min   WRONG
    expovariate(1 / 7.6)               -> mean gap  7.6 s -> 3.24 stops per WALL min   right

7.6 s is not a new measurement, it is forced by the two already in hand:
`mean_stop x (1 - duty) / duty = 10.9 x 0.41 / 0.59`. Equivalently, 129 stops and 1,406 s of silence
inside 2,400 s leave 994 active seconds, and 994/129 = 7.7 s.

**Measured after the fix (14 causas, same tribunal and window as the broken run):**

    stops       3.29/min drawn   (operator 3.23)      <- fixed, was 1.86
    stop median 6.4 s            (operator 6.1)       <- no truncation
    silent      33% measured / 42% drawn-over-wall    (operator 59%)  <- see below

⇒ **Simulate a scheduler offline before measuring it live.** A fake `time.monotonic` and a fake
`wait_for_timeout` took ten minutes and caught the fourth error, which would otherwise have shipped
the identical shortfall in a new costume and looked like a fresh mystery. The same harness shows
the one real remaining lever: at boundaries ~5 s apart the scheduler lands at 2.82/min and 54%
silent, but if boundaries thin to 15 s apart it falls to 2.02/min and 40%. **Boundary density is
now a visible parameter instead of a hidden one.**

⇒ **Log what a random draw PRODUCED, not just its effect.** "Why is the output short?" is a guess;
"the draws match the operator but the output does not" is a subtraction. Two runs were spent
reasoning about a mechanism that one logged list settled.

⚠️ **And do not read a mean off a heavy tail with n=25.** The post-fix mean stop was 7.7 s against
an expected 11.1 s, which looks like residual truncation and is not: 20,000 bootstrap samples put
7.7 s at the 9th percentile of what n=25 produces, and the whole deficit is that no draw landed in
the top decile (28-60 s), a 7.2% event. **The median — robust to that tail — was 6.4 s against the
operator's 6.1 s.** Judge a heavy-tailed spec by its median, or budget enough draws to see the tail.

(PJUD, 2026-08-19.)

### ⚠️ A mechanical insertion is not safe because it compiles — watch the ORPHANED TAIL

Inserting `waiting_for_site()` **above** the body of `still()` left `still()`'s last line
(`page.wait_for_timeout(int(secs * 1000))`) sitting at function-body indentation inside the NEW
function, where it ran unconditionally. The presence path then waited `secs` through `pres.run()`
and `secs` **again** on a raw timeout — and `ojv._hold` hands the callee the whole wait expecting it
consumed exactly once, so **every search wait was double length**. It compiled, it ran, and it
silently halved throughput while the run looked healthy.

This is the third defect here from a bulk or positional edit — see the `pause()` infinite recursion
(a bulk rewrite caught its own fallback line) and the duty instrumentation twice landing inside
`pause()`.

⇒ **After inserting a function, read the diff asking what the line AFTER it now belongs to.**
`git diff` shows the insertion; only reading it shows the absorption.

(PJUD, 2026-08-19.)


---

## Quick checklist for a new scraper

```
[ ] THE ONE RULE: nothing a human could not do, or would not do. Re-read Part 0 when stuck.
[ ] What defends this site?  behavioural scoring / Cloudflare / nothing / auth only
[ ] Launch a REAL browser yourself; attach over CDP. Persistent profile. Headed, always.
[ ] Human at the gate: log in / solve the challenge by hand, with nothing attached.
[ ] Identify the SCARCE act. Harvest everything free around it.
[ ] WATCH A HUMAN USE IT, recording the network. Diff their endpoints against yours.
[ ] Record YOUR OWN scraper with the SAME instrument. Compare per-wall-second, not just
    per-active-second — a generator that never stops emits more than a human, not less.
[ ] Any container reused per record needs a FRESHNESS PROOF, or it serves you the last one.
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
[ ] SPECS (how human) in ONE shared engine; SETTINGS (what job) in the workers.
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
