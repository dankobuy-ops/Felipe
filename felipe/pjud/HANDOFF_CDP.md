# PJUD scraper — CDP Handoff (updated 2026-07-23)

**Supersedes the 2026-07-21 version.** Project: **Poder Judicial Virtual** (Oficina
Judicial Virtual, OJV — `oficinajudicialvirtual.pjud.cl`). Goal: collect civil
**"Ejecutivo Obligación de Dar"** causas where a **bank is the plaintiff**, nationwide,
with **full detail + PDF files + GPS**, into a **Neon Postgres** DB (+ PDFs to Google Drive).

The scraper **works end-to-end** — detail, files, GPS, Neon ingest, resume. On 2026-07-22 the
WAF blocker was **found and fixed**: it was our own `page.click()`. Read the next section
first; it **disproves** most of what the 07-20/07-21 versions of this doc concluded.

---

## ★★★★★ 2026-08-07 — WORKER A, AND THREE THINGS THAT LOOKED LIKE BLOCKS AND WERE NOT ★★★★★

`worker_a.py` is the discovery worker: sweep every tribunal (Corte=Todos), and for each bank
causa open it **once** and take everything that open makes free — header, litigantes, escritos,
cuaderno list, cuaderno-1 historia — plus the **ebook** PDF. Everything else is worker B's.
`ojv.py` now holds the single copy of walk-in / search / freshness / block detection.
`census.py` is a shim onto `worker_a.py --no-detail`.

**1. A PDF that "failed to download" had downloaded perfectly.** Clicking a doc icon opens a
popup; Chrome renders the PDF in its built-in viewer; and the navigation response Playwright
hands back is the **viewer's host document** — `<embed type="application/x-google-chrome-pdf">`.
So `response.body()` returns ~14 KB of wrapper HTML with status 200. This cost a full day twice
over: first three wrapper files sat on disk named `*.pdf`, then, once magic bytes were checked, a
perfectly good scripted click got reported as a WAF block. **Never judge a document by size or
status. Check for `%PDF`.**

**FIX — do not click documents. Have the page fetch them:**
```js
const url = new URL(form.action, location.href).href + '?' + name + '=' + encodeURIComponent(val);
const buf = new Uint8Array(await (await fetch(url, {credentials:'include'})).arrayBuffer());
```
Same one request the click would have made, no popup, no viewer, bytes verified. Measured
0.7–5.2 s per ebook. This is **not** the out-of-process `APIRequestContext` this file warns
about — that one fetches from outside the browser with copied cookies. This runs *inside* the
page already holding the session.

**2. The result page holds 100 rows, and the 2026-08-06 census read only page 1.** Its 207
causas are a **floor** — 33 tribunales reported totals above 100. Worker A paginates, and
harvests each page's detail *before* advancing, because a row index belongs to the page it was
read from: paginating first and clicking page-1 indices afterwards opens the **wrong causas**.
End-of-list is the site's own greyed-out *Siguiente*, never a row count (the blank filler row
drifts the count and truncates the biggest tribunales — the exact bug pagination was added to
fix).

**3. A tier-2 block does NOT burn the profile — re-entry clears it in ~18 s.** Measured on a
blocked session: close the OJV tab, walk in again, 0 rejection frames, and the very causa that
had been refused opened fine. ⚠️ **`waf_check.py` still advises renaming the profile dir. That
advice is stale** and throws away a warm session for nothing. Worker A now cools off (3, 6, 9…
min — a block is a *rate* verdict) and re-enters automatically; the budget counts **consecutive**
blocks, reset by 12 clean opens, because a lifetime cap strands a long sweep however much clean
work sits between blocks.

**⚠️ OPERATIONAL: long runs must be launched DETACHED.** A background task started from the
agent harness gets **killed** after ~30 minutes. This is what actually happened to the census
that "stalled overnight" on 2026-08-06 at 208/230 — not a block, not a hang. Launch with
`Iniciar_Worker_A.ps1` (PowerShell `Start-Process`), which reparents the process so nothing
reaps it, and poll the log file.

**Budget, measured 2026-08-07:** ~24 causa opens on one IP across an afternoon before a tier-2
block, at 45 s spacing. Detail is the binding constraint — searches are cheap by comparison
(208 in an evening, no search-block). `CAUSA_GAP` is now 90 s.

---

## ★★★★★ 2026-08-06 — "TODOS" WORKS, AND MOST OF OUR BLOCKS WERE SELF-INFLICTED ★★★★★

**Set Competencia=Civil and leave Corte on "Todos": `#fecTribunal` fills with all ~230 civil
tribunales nationwide and searching works across them** (Los Ángeles to Santiago; verified by the
operator by hand, then by script). **This did not work before** — the site is being actively
changed. ⚠️ **Treat every rule in this file as DATED. Re-verify anything load-bearing.** Several
sections below were overturned within a single day.

**Why it matters far beyond convenience: `#corteFec` is the ONLY control that fires a server
request when it changes**, and `select_by_kbd` walks the options one arrow at a time, firing a
`change` — and a tribunal-list load — at EVERY step. Reaching Concepción from the placeholder
fired **ten list-loads in under a second**. That burst caused both:
- **desynced tribunal lists** (`#corteFec`=46 while `#fecTribunal` held Chillán's courts, then
  Iquique's — responses landing out of order, last one wins), and
- **the fast blocks** we spent a day misattributing to profile standing, then to the IP.
The operator got blocked doing the same thing **by hand**. Never changing corte removes the
entire class of problem. Tribunal is a leaf: no cascade, no request, one ArrowDown per step.

### ★ THE BUG THAT FAKED EVERY SCRIPTED "GATE-1 BLOCKED"
`/home/` has **TWO** `accesoConsultaCausas` buttons. Playwright locators are strict, so passing a
SELECTOR to `human_click` makes `bounding_box()` throw ("resolved to 2 elements"); `human_click`
catches it, falls through to `.click()` which throws identically, and returns False. **No click is
ever delivered** — and the caller reports "no form appeared", i.e. a reCAPTCHA refusal, for a
click that never happened. Pick ONE element that hit-tests (`enter_ojv.py` does, and enters first
try every time). **"Two human-only gates", "gate 1 is flaky" and "fresh profiles score low" were
all explanations for a click that never happened.**

### Measured cost of DOCS + GPS (first real numbers)
On a typical `Ejecutivo Obligación de Dar` (C-9923-2026, 9º Civil Santiago): **14 historia docs in
cuaderno 1, 4 in cuaderno 2, 3 header docs, 9 georreferencia rows** — about **30 requests at
~3.5 s each, 2-3 minutes for ONE causa**, versus ~4 requests for a metadata-only open. That is why
docs passes died in 1-2 minutes.

**A document is ONE click and opens a NEW TAB** (`form` + `target=_blank`); the causa modal
survives untouched. The PDF body is readable from that tab's response, so **docs can be captured
without `APIRequestContext`** — the out-of-page fetch this doc flags as the prime block suspect.
Close each tab as you go. Five endpoints: `docu.php` (texto demanda), `docuN.php` (cuaderno 1),
`docuS.php` (cuaderno 2), `docCertificadoDemanda.php`, `newebookcivil.php`. Five documents plus a
cuaderno switch on one session produced **zero rejection frames**.
⚠️ Header doc controls share one ancestor `div` and differ only by **x-position**, and **Anexos
has no `<form>` at all when unavailable** — ordinal position is NOT stable across causas. Map by
neighbouring label or by endpoint, never by index.
★ The demanda PDF carries data **found nowhere in the metadata**: `MATERIA: COBRO DE PAGARÉ`,
`NÚMERO DE OPERACIÓN` (the bank's own loan reference), both parties' legal representatives and
domiciles. It is a **text PDF, not a scan** — extractable without OCR.

### Two whole tabs are never read
The detalle modal has five tabs: Historia, Litigantes, **Notificaciones**, Escritos por Resolver,
**Exhortos**. There is no parser for Notificaciones (`ROL | Est. Notif. | Tipo Notif. | Fecha
Trámite | Tipo Part. | Nombre | Trámite | Obs. Fallida`) or Exhortos, and no column for either in
`gstore.TABS`. Both are pre-rendered in the DOM, so reading them costs **no extra request**. For
debt recovery, `Est. Notif.` and `Obs. Fallida` — whether service succeeded and why it failed —
are arguably as valuable as the causa itself.

### Traps found the same day (all cost hours)
- **Never judge results by the presence of "Total de registros"** — it is left over from the
  PREVIOUS search. A census recorded 35 tribunales at `elapsed 0.0s` with ZERO empties, each
  holding the previous tribunal's numbers. Use the **network** as ground truth: a
  `consultaFechaCivil.php` response after the click proves the search ran. A DOM fingerprint
  cannot tell empty→empty apart — both leave the table cleared.
- **Do not time out while the site's own spinner is up.** `page_busy()` true + Buscar disabled =
  a request genuinely in flight. The site slowed from 11-35 s to over 75 s and we discarded valid
  searches as stale — including Los Ángeles, one of the richest tribunales in the country.
- **`query_selector` throws "Execution context was destroyed" during navigation** — exactly when
  polling for the form after a successful entry click. Unguarded it kills the run at the moment it
  works. See `census.find_form()`.
- **Real mouse coordinates land on the VISIBLE tab.** Leftover `/home/` tabs made retries click the
  wrong tab. Close stale OJV tabs and `bring_to_front()` before every click.
- **Phantom tribunales**: the dropdown carries decommissioned twins (`1º Juzgado De Letras de Arica
  ex 4`) differing only in a suffix that is truncated on a narrow window. They always return
  nothing. Match case-insensitively and log the tribunal **id** next to the name.
- A blocked session returns **`sin resultados`**, not an error. Tribunal 5 was reported empty by
  two runs; a healthy session then found **52 causas** there.
- A **profile is never "burned"**: tier 2 (206 B rejection / `TSBrPFrame` overlay) clears by
  re-entering from www.pjud.cl; tier 3 (full-page image CAPTCHA) clears by rotating to a fresh
  profile dir — **you do not need to solve it**. Never solve it by script: it is an explicit
  human-verification gate.

**New tools (`scraper/`):** `census.py` (national search-only census, resumable by index),
`settle.py` (four-condition quiescence: spinner idle + content assertion + no tracked in-flight
request excluding the Shape endpoint + DOM quiet), `enter_ojv.py` (dismiss AVISO, hit-test, enter),
`step.py` (one operator-driven step at a time: setup / trib / search / open / close).

---

## ★★★ 2026-08-05 — THE BUDGET COLLAPSED: ~2 MINUTES / ~11-14 ACTIONS PER PROFILE ★★★

**Four profiles burned in one afternoon, all on Corte Santiago, window 15/07..05/08/2026.**
Every one died at the same scale of work, and profile standing did NOT predict it:

| run | profile | mode | work done before the block | died at |
|---|---|---|---|---|
| 1 | veteran (created 23-07, 13 d dormant) | detail | 4 searches + 3 causas + 4 cuaderno + 3 receptor ≈ **14** | trib 5 |
| 2 | **fresh, created 20:10** | detail | **identical — the same 3 causas** | trib 5 |
| 3 | fresh, created 21:16 | `--count-only` | 10 searches, no modals ≈ **11** | trib 11 |

Run 2 is the one that matters: **a brand-new profile died in exactly the same place as the
13-day-old veteran** — same tribunal, same 3 causas. That **kills "the profile is decayed"** as an
explanation, the same way trial 3 killed "rich warm-up decides who survives" back on 2026-07-23.

**`sin resultados` at tribunal 5 was the block, not an empty court — PROVEN.** Both detail runs
reported 5º Civil de Santiago as empty. A later healthy session searched that exact tribunal and
window: **52 causas**. So a spent session reports empty searches, and every tribunal after the
block is a false negative. Nothing in the DB marks them.

**Against the documented baseline this is a collapse of ~2 orders of magnitude:** this doc's own
"overnight single-worker sweep" section records one well-warmed profile holding ~3 causas/min and
**439 causas in a single run**. We now get **3 causas, or 10 counted tribunales.**

**What is NOT the cause** (measured, not assumed): profile age or standing (run 1 vs 2); IP
(unchanged all afternoon); detail opens alone (count-only also dies, just later); a stuck modal
(no modal, no backdrop, in every post-mortem).

**★ OPEN — and it inverts the pacing philosophy.** Both ~14-action detail runs and the ~11-action
count-only run also died at **roughly two minutes of scripted activity**. Action-count and
wall-clock are confounded in all three runs, and they imply opposite fixes:

- **action-count** → pacing is irrelevant; plan around ~11 actions per profile.
- **wall-clock** → the gentle pacing (`P_TRIB` 6–12 s, `P_CAUSA` 5–10 s, `P_PAGE` 4–8 s) is
  **spending** the budget, not protecting it, and the scraper should run FASTER.

**The test** (one profile, `search_probe.py` discipline — one variable changed): count-only with
`P_TRIB` stretched ~3×. Dies at ~10 tribunales → action-count. Dies at ~4 → wall-clock.
**Do not plan around the current pacing constants until this is settled.**

**Practical meanwhile:** count-only covers ~10 tribunales/profile, so Santiago's 31 need three
warm-ups via disjoint `--skip-tribs` slices (0/10, 10/10, 20/11). The detail pass at ~3 causas per
profile is not a workflow — ~20 manual warm-ups for one corte-month.

---

## ★★★ 2026-08-05 — BOTH BLOCK DETECTORS WERE BLIND: the rejection page is in SPANISH ★★★

`waf_check.REJECT_MARKERS` and `cdp_scrape.waf_blocked()` both tested the **English** F5 text
(`"requested URL was rejected"`, `"Support ID"`). The page our browser actually gets is Spanish:

```
[X] CLOSE  .  (2)  .   Su numero de soporte es : <11224827243296953039>   [Go Back]
```

Neither matched. **Consequences, measured on one live block:**

- `waf_check` printed `rejection frames: 0` → **`VERDICT: THROTTLED`** on a page carrying **four**
  rejection frames and two distinct support IDs.
- Far worse: `waf_blocked()` returned False, so `--max-empty` / `--max-fails` **never fired**. The
  Santiago sweep sailed past the block and began recording tribunal after tribunal as
  `sin resultados`. Left alone it would have walked all 31 and exited **0 / `[LISTO]`** with most
  of the corte silently missing — the same false-success as the worker-3 collapsed-panel bug, from
  a different cause. It was caught only because the operator was watching the browser.

**Fixed both**, and added a **locale-proof structural tell** so the next rewording cannot repeat
this: Shape injects `TSBrPFrame_cs_chlg_ajax_frame_*` iframes and **parks one directly on top of
`#btnConConsultaFec`**, which is left `disabled`. Verified on the live block —
`covered_by='TSBrPFrame_cs_chlg_ajax_frame_810'`, `buscar_disabled=True`. New
`BLOCKED-CHALLENGE` verdict fires on the structure alone when no text matches.

This also explains the old **"objetivo tapado"** warning from `human_click`: when F5 blocks, its
challenge iframe *is* the thing covering the button. A covered target is not merely correlated
with a block — during a challenge it **is** the block, seen from the pointer's side.

**Rule: never conclude "sin resultados" or `[LISTO]` from a run whose detector you have not
confirmed can see a block in your browser's locale.**

---

## ★★★ 2026-07-23 (evening) — the per-IP limit is a REQUEST-RATE budget, not a session count ★★★

One model now fits every parallelism trial we have:

| config | per-IP request rate | result |
|---|---|---|
| 1 worker (metadata OR docs) | low/moderate | ✅ fine |
| 2 workers, **metadata only** | low-ish | ✅ fine >1 h (morning) |
| 3 workers, metadata | higher | ❌ 2 blocked (morning, ×2) |
| 2 workers, **both docs** | high — docs ≈ 8 PDF fetches/causa ×2 | ❌ both blocked in ~1–2 min |

**Proven by a STAGGERED run on a FRESH IP:** worker 1 solo *with docs* stayed healthy (2 causas,
`docs=8` each); **both died ~1–2 min after the 2nd docs-worker joined.** The block tracks the added
request rate, not the mere existence of a 2nd session (2 metadata sessions are fine for an hour).

**Consequences:**
- **Docs pass = 1 worker per IP.** **Metadata/detail sweep = 2 workers per IP.** A 2nd docs-worker
  needs a **2nd IP** (this is where the mobile connection pays off: 1 docs-worker per connection).
- **⚠️ FLAG GOTCHA:** in-page docs need **BOTH `--docs --docs-inpage`**. `--docs-inpage` alone
  leaves `DOCS=False` and downloads **nothing** — it silently becomes a metadata run. Confirm docs
  are really flowing by `docs=N` (N>0) in the `OK` line. (The first "2-worker docs" block actually
  downloaded zero docs, so that one was pure concurrency/rate, not docs.)
- **Recommended workflow:** run **pass 2 as metadata-only at 2 workers** (fast, builds the target
  list), then a **separate docs pass at 1 worker per IP** on the confirmed keepers.

**Caveats (don't over-trust):** the 2-docs-worker block is ~1 clean trial; these profiles had a
**lighter warm-up** than the morning survivors; and "1 docs-worker sustains a LONG solo run" is not
yet confirmed (only 2 causas solo before the 2nd joined). **NEXT:** (a) a 30-min single-worker docs
run to confirm 1-docs-per-IP is durable; (b) finish the interrupted **1 list-only + 1 docs**
staggered test — list-only is cheap search+pagination, so per the rate model it should survive
alongside one docs-worker, which would confirm the budget is about rate, not sessions.

---

## ★★★ 2026-07-23 — CAN A WORKER RUN WITH ZERO HUMAN INPUT? NO. Two human-only gates. ★★★

The full path a fresh profile must walk (recorded live with `nav_record.py`):

```
www.pjud.cl
  └─ click <a href="https://oficinajudicialvirtual.pjud.cl/home/">   "Plataforma para el ingreso…"
OJV /home/  (login landing, opens in a NEW tab)
  └─ click <button onclick="accesoConsultaCausas()">Consulta causas</button>   ← GATE 1 (reCAPTCHA v3)
indexN.php  (Consulta Unificada console, SAME tab)
  └─ open #BusFecha accordion, establish form by keyboard, search             ← GATE 2 (F5 on 1st search)
```

- **GATE 1 — reCAPTCHA v3 at guest entry.** `accesoConsultaCausas()` runs an INVISIBLE v3 check
  (the floating badge, no checkbox, nothing to solve). A real human click passes silently; a
  **scripted click STALLS on `/home/` and never navigates — even after 3.5 min of scripted pointer
  warm-up** (150 s on pjud.cl + 60 s on /home/). v3 weighs fingerprint / cookie-history / IP /
  timing, which a fresh scripted profile lacks. This gate is UPSTREAM of any search.
- **GATE 2 — F5 Shape trust at the first search.** A human can get past gate 1 in two clicks, but a
  **thin/cold session** (2 clicks, no manual search) is **F5-rejected on its FIRST scripted search**
  (profile "zero", 2026-07-23) — while a well-used session searches fine. So F5 trust ALSO
  accumulates with behavioural history; `human_click`'s good motion is necessary, not sufficient.
  The operator's own day-one instinct was right: **acting before the session has settled/earned
  trust is a bot tell.**

**Irreducible human cost = ONE warm-up per profile:** 2 clicks in **+ a couple of MANUAL searches**
(this is what earns gate-2 trust), then hand off — after which the profile scrapes for **days,
unattended**. Both halves of the ritual are load-bearing, not superstition.

**Corrects two earlier beliefs:** "virgin profile blocked on its first SEARCH" (it never *reached*
a search — it is blocked at *entry*, gate 1) and "2 clicks and the script does the rest" (only true
for an already-warm profile like w5). Tools added: `nav_record.py` (read-mostly click/URL recorder),
`unattended_worker.py` (`--warmup` scripted-entry attempt). ⚠️ `_human_pointer` PRESSES the mouse —
warm-up MUST pass `press=False` or it clicks at random coordinates (it opened stray PDFs/tabs once).

---

## ★★★ SOLVED 2026-07-22 — `page.click()` WAS THE BUG. START HERE ★★★

### F5 Shape scores the pointer's MOTION, not the `isTrusted` bit

Playwright's `page.click()` / `locator.click()` produce `isTrusted=true` events — that part of
the old model was right — but they **teleport the pointer** onto the element and fire
down+up with **no approach path and no hover dwell**. F5 Shape's behavioural telemetry scores
exactly that shape and F5 rejects the next request. A human's hand produces an arc.

Measured in ONE healthy session, same button, same POST params, minutes apart:

| pointer | pre-click JS | response |
|---|---|---|
| `page.click()` (teleport) | yes | **250 B F5 rejection page in 0.1 s** |
| human arc + dwell + real press duration | no | **109,234 B of real results** ✅ |
| human arc + dwell + real press duration | **yes** | **109,234 B of real results** ✅ |

Consequences, all validated the same session:

1. **`Runtime.evaluate` over CDP is INNOCENT.** Reading the DOM (`eval_on_selector`, all the
   `parse_*` helpers, `page.evaluate`) does not flag anything. Only the pointer matters. Do
   not waste time rewriting the parsers to avoid JS.
2. **The fix is `human_click()`** in `cdp_scrape.py`: arc with easing + jitter (18–28 steps) →
   hover dwell 140–380 ms → `mouse.down` → 55–130 ms press → `mouse.up`. Every `page.click` in
   the scraper now routes through it (Buscar, Siguiente, causa magnifier, receptor, modal
   close, datepicker). **Never reintroduce a bare `.click()`.**
3. **The 3-tribunal sweep that always died at search #2 now completes**: `--count-only
   --max-tribs 3` → **189 bank C-causas in 1.7 min**, three scripted searches plus pagination,
   zero rejections (54 / 91 / 44 for tribunales 259 / 260 / 261).

### What this DISPROVES (do not rebuild these theories)

- **"The 2nd search of a session is F5-rejected."** FALSE. On 2026-07-22 the operator did
  **3 manual searches, paginated 8 pages / 715 records, and opened 3 causas** in one session
  with zero rejections. The old table of "search #2 blocked" runs was measuring *our teleport
  clicks*, which happened to land at that ordinal position.
- **"The reCAPTCHA v3 token is single-use."** FALSE, and provably so: search #2 **reused the
  token from a pagination request 38 s earlier, byte for byte, and returned rows.** The
  `netprobe_manual_1784735615.jsonl` recording has it. Do **not** build "wait for a new token"
  logic — it was next-step #2 in the old doc and would have been wasted work.
- **"Shape telemetry beacons must be fresh."** FALSE. A successful manual search fired
  **113.8 s** after the last beacon.
- **The old "burn budget"** (elapsed time / PDF volume) was almost certainly the same bug
  wearing a different mask: every magnifier click in the detail regime was a teleport too.
  Re-measure it before believing any number in the section below.

### The instant tell (still true and still useful)

After a reject, **`#btnConConsultaFec` (Buscar) stays `disabled` forever** — the site disables
it in `beforeSend` and only re-enables it in the AJAX `success` handler, which a rejected
response never reaches. Also: judge a search by the **response**, not by the results table —
the table keeps the *previous* search's rows, so a rejected search can look like 100 happy
rows (it did, and it produced a false "OK" verdict on 2026-07-22).

### F5 Shape streams behavioural telemetry to `/TSPD/?type=N` — watch this number

Shape's JS posts a continuous stream of XHRs to `oficinajudicialvirtual.pjud.cl/TSPD/?type=N`
(`type=22` is the high-frequency behaviour channel; same cookie family as `TSPD_101_DID`).
The rate is a direct read-out of "does the site believe a human is here":

| session | duration | TSPD events | rate |
|---|---|---|---|
| 2026-07-22 #1 — 3 manual searches, then mostly idle | 11.7 min | 39 | **3/min** |
| 2026-07-22 #2 — heavy manual work (8 searches, 21 causa opens, 38 doc clicks) | 8.7 min | 605 | **70/min** |
| 2026-07-22 #3 — `cdp_scrape` driving with `human_click` | (live) | — | **~44/min** |

Two things follow. **(a)** `human_click`'s pointer motion generates real telemetry — the script
is no longer silent, which is very likely *why* the search fix works. **(b)** A useful
diagnostic: if the TSPD rate collapses toward zero while the scraper runs, the session is
about to look non-human. Measure it from any `netprobe` JSONL:
`[r for r in recs if r["kind"]=="request" and "/TSPD/" in r["url"]]`.

**⚠️ Bench discipline:** the operator's physical mouse passing over the CDP Chrome window fires
real `mousemove` events into the page and inflates this number, which **contaminates any test
of whether the script alone sustains proof-of-life**. Leave the window visible but park the
cursor elsewhere (do not minimise — a minimised window gets throttled and coordinate clicks
break).

### Out-of-page requests are the remaining suspect

`download_doc()` fetches PDFs through Playwright's `APIRequestContext`
(`context.request.get()`). That shares cookies but is issued **outside the page**: no document
origin/referer chain and **no Shape telemetry at all**. On 2026-07-22 a `--docs --gps` run died
after 3 causas / 29 such fetches, while the operator manually pulled ~38 documents in the same
period with zero rejections. **`--docs-inpage`** (new) fetches the identical URL with an
in-page `fetch()` and returns the bytes base64 — same PDF, but issued by the page. A/B these
two before concluding anything about document volume.

### A session must be WARMED BY A HUMAN — fully unattended runs are not possible

Tested 2026-07-22 on two Chromes side by side (separate profile dirs and CDP ports, so the
good session was never at risk — **do it this way for any risky experiment**):

| profile | history | verdict |
|---|---|---|
| port 9333 — operator passed the CAPTCHA + searched, then the script ran | human-warmed | **HEALTHY** after 20 causas / 54 PDFs |
| port 9334 — virgin, never touched by a human | script only | **BLOCKED on its first search** |

Clicking through `www.pjud.cl` → Causas *does* reach the date form with no visible challenge
(`#fecCompetencia` is right there). It does not matter. The site runs **reCAPTCHA v3
enterprise** — invisible and **score-based**, the token in every search POST carrying a score
derived from the session's behavioural history. A profile with no human history has nothing to
score. **The manual step is the session earning trust, not solving a puzzle**, so it cannot be
automated away; plan on one human warm-up per session, then unattended running.

*Not yet separated:* that test also used `establish_form_kbd`, whose arrow-key bursts fire one
`leeTrib.php` per press on `#corteFec`. To tell the two apart: pass the CAPTCHA by hand and
**stop there** (no form, no search), then run `--corte 90`. If it works, a session costs the
operator ~10 s instead of ~45 s. `scraper/bootstrap_probe.py` records all of this.

### ★ THE OTHER BIG ONE: a stuck modal looks EXACTLY like a WAF block

Most of the "blocks" chased on 2026-07-22 were not blocks at all. The chain:

1. one causa open goes slow and times out (30 s)
2. **the detail modal never closes**
3. its **backdrop now covers the Buscar button and the magnifier links**
4. every later click lands on the backdrop → searches "return" nothing, causa opens time out
5. `waf_check` sees the dead page trapped in that modal and says **BLOCKED-DETAIL**

Worker 2 hit this and reported **20 consecutive tribunales as "sin resultados"** — then exited
**0 / LISTO**, as if the corte were empty. The tell was in its own log, 20 times:
`[warn] human_click: target still covered`. The operator disproved the block by hand: close the
modal, search again, open a causa — all fine. A script run then scraped the same "dead" profile
without a hitch.

**Fixes (all validated live):**
- **`clear_stuck_modal()`** — Escape → close button → jQuery `modal('hide')` → page reload as a
  last resort. Called from the causa error handler and from `human_click`.
- **`human_click` NEVER clicks a covered target** any more. It waits up to 8 s, tries clearing
  the modal, and then **refuses to click** (returns False). The old "click anyway" fallback sent
  real clicks to backdrops at coordinates where nothing legitimate was.
- **`wait_idle()` / `page_busy()`** — waits on the site's OWN spinner. `#loadPre*` divs are
  EMPTY when idle and get a spinner injected while a request runs; that is the loading icon the
  operator watches. **Never judge readiness by the results table** — it keeps showing the
  PREVIOUS search's rows while a new one runs, which is why a rejected or pending search can
  look like 100 happy rows.
- **`waf_check` now reports STUCK-MODAL** (exit 4) instead of condemning a live profile, and
  prints which modal is open. It over-diagnosed BLOCKED-DETAIL repeatedly and cost good profiles.
- Bonus: **`.loadTotalFec`** holds `Total de registros: N` — the true result count for the
  current search. Use it to verify pagination actually reached the end.

### ★ A BLOCKED PROFILE CAN BE RECOVERED — no rotation, no CAPTCHA

Contradicting rule 8's remedy: the operator revived a genuinely blocked session by **closing the
Consulta-Causas tab and reopening it from `www.pjud.cl`**. Verified functionally straight after
(a real causa scraped in 30 s). This is automatable and worth wiring in.

**But recovery restores function, not standing.** The same profile decays with each cycle:

| profile | run 1 | after 1st recovery | after 2nd |
|---|---|---|---|
| worker 2 | 121 causas | 23 | **2** |
| worker 3 | 4 causas | — | **0** |

So a twice-blocked profile is nearly worthless. Prefer a fresh profile + a rich warm-up.

### ★ PARALLELISM: two workers yes, three no

Setup: one Chrome per worker, each with its **own profile dir and CDP port**
(`--user-data-dir=%LOCALAPPDATA%\pjud_cdp_wN --remote-debugging-port=933N`), one human warm-up
each. **Always test risky things this way** — a burned profile never harmed a healthy one.

- **2 workers:** ran over an hour side by side, ~120 causas on the second, **no blocks**. Worker 1
  held **2.9–3.0 causas/min whether alone or with siblings**, so throughput is ~linear.
- **3 workers:** blocked in TWO independent trials. In the second, **worker 3 was blocked having
  opened ZERO causas, 36 seconds in, with zero clicks refused.** It cannot be caused by how the
  script clicks.
- The survivor in both trials was worker 1 — the profile carrying the operator's rich 8.7-minute
  manual warm-up (8 searches, 21 causa opens, 38 document downloads, ~605 TSPD events).

**Unresolved (the next experiment):** is the limit the IP, or the trust standing of thin
profiles? Give a FRESH profile a RICH warm-up (5+ min of genuine manual browsing) and add it as
the third worker. Survives → warm-up quality is the lever. Blocked on arrival → it is the IP, and
more throughput needs more connections (a phone hotspot / second machine).

**A correlation that turned out NOT to be causal:** covered-clicks predicted blocks perfectly in
trial 1 (0 → survived 50 causas, 1 → blocked at 23, 2 → blocked at 4). Trial 2 killed it: worker 3
blocked with zero covered clicks. The no-blind-click rule is still right — it just was not the
cause. **Do not re-derive that theory.**

### Watchdogs + reliability (new)

- **`--max-fails N` (default 3)** — N consecutive causa failures → check for the F5 rejection
  page → if present, flush the JSON and exit **code 3** ("profile spent"), instead of grinding out
  30 s timeouts for hours unattended, which is what actually happened before it existed.
- **`--max-empty N` (default 4)** — same for consecutive empty searches, the OTHER way a spent
  profile fails. Small rural tribunales genuinely are empty, so only a STREAK is suspicious.
- **Neon reconnect** — `causa_state()` / `scraped_rols()` now retry through `dbstore._reconnect()`.
  A multi-hour sweep outlives Neon's idle timeout; the old code caught the error, returned empty,
  and **silently disabled `--resume`**, so the run re-scraped causas it already had.

### ★★ THE PAGINATOR WAS LOSING MOST OF EVERY TRIBUNAL — fixed 2026-07-23

Not "an undercount". Tribunal 260 (2º Civil de Santiago), January, one identical window:

| run | bank causas |
|---|---|
| old `--count-only` (2026-07-22) | 91 |
| old detail sweep (2026-07-22) | 135 |
| **fixed paginator (2026-07-23)** | **293** — 7 pages, 654/654 rows |

**158 of the 293 were absent from Neon entirely.** Every earlier enumeration is roughly half of
reality, `--list-only` shells are an incomplete work queue, and the ~1,500 Santiago-January
extrapolation was built on sand.

**The cause.** `next_page()` returned `False` for two situations that are nothing alike —
Siguiente *disabled* (genuinely the last page) and *"I clicked and the table never changed within
10 s"* — and both callers read `False` as "tribunal finished" and moved on with exit code 0. A
paginator AJAX slower than the poll was therefore indistinguishable from the end of the list.
Detail sweeps hid it because minutes of causa-opening pass between pages; count runs paginate
back-to-back, which is why they lost the most.

**★ The losses are systematic, not random.** Results sort **newest-first** (page 1 of January
starts at 31/01), so a paginator that quits early always drops the **OLDEST** dates. This is why
every tribunal in Neon starts mid-month — 260's earliest row was 19/01 — and why the 158 new rols
are `C-100`, `C-101`, `C-102`… **If you see a tribunal whose causas begin mid-window, that is this
bug's fingerprint. Do not read it as "a different search window was used" (I did, for an hour).**

**The fix** (`eb987aa`, `bd50def`): `next_page()` returns `"advanced" | "last" | "stuck"`, waits on
the site's own spinner before clicking, polls 20 s instead of 10, re-checks whether Siguiente went
disabled, and retries the click once. `total_registros()` reads the site's own `Total de
registros: N` — the only ground truth for "did we reach the end" — and it is compared against
**all** rows seen, never the bank subset. Every tribunal now prints `[n pag · seen/total filas]`;
a short one is flagged `[INCOMPLETO]` and written to a `<run>.incomplete.json` re-run list that is
rewritten on every flush, so it survives a kill or a `Blocked` exit.

Note when reading `seen/total`: each page carries one blank-rol filler row. Counting those
inflated 654 real rows to 661 — one per page, enough to mask a genuinely short page. Blank rols
are skipped now.

### The tools that settled it

- **`scraper/net_probe.py`** — read-only network recorder; injects nothing. Logs every request
  with POST params (reCAPTCHA tokens fingerprinted `<len=1337 03AF…kQ2f>` so **reuse is visible
  at a glance**) + response status/size + F5-reject flag → `netprobe_<label>_<epoch>.jsonl`.
  Two bugs fixed 07-22: it now **follows every tab** (OJV opens Consulta Causas in a NEW tab
  and discards the old one — pinning to one page made it die exactly when the interesting
  traffic began), and it waits via Playwright rather than `time.sleep()` (**a bare `time.sleep`
  blocks the sync greenlet and NO events are ever dispatched** — it silently captured 0 events).
- **`scraper/search_probe.py`** (new) — fires **one** search per run through the real
  `cdp_scrape` functions with a single variable changed, and judges by the response.
  `--mode click|human|clear|kbd|kbd-slow`, `--bare` (zero `Runtime.evaluate` before the click;
  the button's box comes from the CDP **DOM domain** instead). This is how the table above was
  produced; use it to test any future WAF hypothesis for the price of one search.

---

## TL;DR — current state (2026-07-22)

- **Approach:** drive a REAL Chrome over CDP (`--remote-debugging-port`), Playwright
  `connect_over_cdp`. Trusted events beat the site's **F5 WAF** — but `isTrusted=true` is
  **necessary, not sufficient**: the pointer must also MOVE like a hand (see the top section).
  The in-page bookmarklet is **dead** (can't forge trusted events at all);
  `felipe/pjud/inpage/*` + `Abrir_PJUD_sin_debug.cmd` are kept as a documented dead end.
- **Everything in the pipeline is validated live:** detail opens, `--docs` (PDFs → Drive),
  `--gps` (lat/lng), `--resume`, keyboard tribunal switch, and `ingest_cdp.py` → Neon with
  0 dangling FKs.
- **✅ The blocker is FIXED (2026-07-22): it was our own `page.click()` teleporting the
  pointer.** `human_click()` replaces it everywhere. A 3-tribunal `--count-only` sweep now
  completes clean (189 causas, 1.7 min) where every previous attempt died at search #2.
  The "search #2", "single-use token" and "beacon freshness" theories are all **disproven** —
  see the top section before re-deriving any of them.
- **The flag follows the PROFILE, not the IP** (validated — rule 8). Resetting the network
  without resetting `%LOCALAPPDATA%\pjud_cdp` does nothing. **A fresh profile = a fresh profile
  DIR** (`%LOCALAPPDATA%\pjud_cdp`), not a new IP and not new cookies.
- **Counting is cheap, detail is precious:** a `BLOCKED-DETAIL` profile **still searches and
  paginates**, so `--count-only` enumeration can be run on a burned profile. Spend clean
  profiles on **detail opens**, never on counting.
- **⚠️ Any number produced before 2026-07-23 is a floor, not a census** — the paginator was
  dropping most pages of each tribunal, oldest dates first. See the paginator section.

---

## ⚠️ HISTORICAL — the "burn budget" (2026-07-20/21), now suspect

**Read this as evidence, not as conclusions.** Every run below used teleport `page.click()`,
which we now know is itself the trigger (top section). The "~6 causas then blocked" budget is
therefore almost certainly an artefact of the bug, not a property of the site. **Re-measure
before planning around any number here.** What still stands from this session is rule 8 (the
flag follows the profile, not the IP) and the shape of the block page.

### The 2026-07-20/21 mobile session, in full

The whole session ran on **one mobile connection**, deliberately, so the IP was never a
variable. Two profiles were used.

**Profile A** (carried over from earlier dev work, reused across many past sessions):

| step | result |
|---|---|
| operator setup + manual search | fine — 101 rows |
| scraper's **first** causa open | **REJECTED** — F5 block page, support IDs `8068285243157809776`, `8068285242946234825` |

Zero causas. The block was instant, on a *fresh IP*. That is what proved the flag is
device-scoped, not IP-scoped: **the only thing carried over was the profile.**

**Profile B** (created by renaming A aside; same IP, same code, fresh CAPTCHA):

| run | mode | causas | PDFs | GPS | outcome |
|---|---|---|---|---|---|
| probe | `--no-search --docs --gps --max-causas 3` | 3 | 44 | 5 | clean, 3.3 min, zero warnings |
| sweep | `--docs --gps --resume --max-tribs 3 --max-causas 12` | 3 | 108 | 24 | **blocked** during/after the 3rd |

Per-causa detail from the sweep — note how much heavier these were than the probe's:

```
C-1510-2026  hist=40  rec=15  docs=39  geo=17
C-1513-2026  hist=23  rec=7   docs=22  geo=6
C-1518-2026  hist=49  rec=7   docs=47  geo=1
```

**Profile B total before the block: 6 causas, 152 PDF fetches, roughly 25 min of activity.**

All 6 causas were ingested — nothing was lost to either block, because the JSON is written
incrementally and survives a kill.

### What the block looks like (so you recognise it instantly)

Not a hang. An actual F5 block page rendered **into the detail-modal iframes**:

```
[X] CLOSE  The requested URL was rejected. Please consult with your administrator (2).
Your support ID is: <11224827236444459058>   [Go Back]
```

**The parent page stays perfectly healthy** — tribunal still selected, search still returns
its 101 rows. Only `detalleCausaCivil` is rejected. That asymmetry is the signature; run
`waf_check.py` (below) and it will tell you in one command.

---

## ~~⚠️ THE OPEN QUESTION — volume vs time~~ — BOTH ANSWERS WERE WRONG (2026-07-22)

> **The real answer was neither.** It was `page.click()` teleporting the pointer (top section).
> The 07-21 verdict below ("it is elapsed TIME") was drawn from runs that were all being
> rejected for the pointer, so the correlation with session length was spurious — a longer
> session simply meant more scripted clicks. **The reduced doc set is still worth keeping**
> (cheaper and faster, and Felipe chose that scope), but it was never the cure either.
> Preserved verbatim below only so the evidence trail stays auditable.

**We do not yet know what burns the profile.** The probe and the sweep differ in *two* ways
at once, and the experiment can't separate them:

1. **PDF fetch volume** — 44 fetches survived; the next 108 did not. Rule 4 below always
   flagged doc downloads as the unproven part at scale, and this is consistent with it.
2. **Cumulative session activity / elapsed time** — profile B had already done a full probe
   plus an ingest before the sweep started. Maybe any 25-minute session dies regardless.

These have **opposite fixes**, which is why guessing is expensive:

- If it's **fetch volume** → narrow what we download. 47 PDFs for a single causa is almost
  certainly more than the business needs; filtering to the folios that matter could cut
  fetches by most of that and stretch a profile many times further. **Ask Felipe which
  documents actually matter** — this is a product question, not a technical one, and it may
  make the whole problem disappear.
- If it's **elapsed activity** → shorten sessions and rotate profiles more often; document
  volume is irrelevant and filtering would be wasted work.

### The experiment that settles it (cheap, ~15 min)

On a fresh profile, run **metadata-only** — no `--docs`, no `--gps`:

```
cdp_scrape.py --no-search --resume --max-causas 30
```

- If it sails past 6 causas (the earlier handoff records **20 clean on a fresh IP**, which
  is suggestive but was on an unknown profile age) → **PDF volume is the culprit.** Go
  narrow the doc set.
- If it dies around 6 again → **it's session activity/time.** Forget filtering; redesign
  around short, rotating sessions.

Run `waf_check.py` before and after so the verdict is unambiguous.

### A free measurement you can take on a burned profile

A profile that is `BLOCKED-DETAIL` **still searches and paginates**. The bank filter reads
`caratulado` straight from the results table — no detail modal needed. So you can count the
whole job (bank C-causas per tribunal for the month) on an already-dead profile at zero
cost. **Nobody has done this yet, so the size of the corte is still unknown** — worth doing
before committing to any strategy, because "50 causas" and "2,000 causas" call for very
different designs. Would need a small `--count-only` flag on `cdp_scrape.py`.

---

## The WAF — rules that keep you unblocked

1. **Never `select_option` the tribunal.** That single synthetic change event flags the F5
   session; the next heavy op (detail modal) then hangs. Use `--no-search` (operator selects)
   or the keyboard switch (`select_tribunal_kbd`, already wired into the sweep).
   *(Untested since the 07-22 fix — it may well be innocent too, but there is no reason to
   retest it: the keyboard switch works and costs nothing.)*
2. **`select_option("#selCuaderno", …)` (cuaderno switch) is TOLERATED** (lighter AJAX) —
   validated. Leave it as-is.
3. **⛔ NEVER `page.click()` / `locator.click()` — use `human_click()`.** This is rule #1 in
   practice. Both are `isTrusted=true`, but they teleport the pointer with no approach path
   and no hover dwell, and F5 Shape scores the motion: the request that follows comes back as
   a 250 B rejection page. Validated 2026-07-22 (top section). Applies to **every** target —
   magnifier, Buscar, Siguiente, modal-close, receptor, datepicker.
4. **Doc downloads via `context.request.get(...dtaDoc=JWT)`** were long suspected of causing
   the burn; that suspicion rests on runs that were being rejected for the pointer instead, so
   treat it as unproven. The JWTs expire ~1h, so **download during the scrape**, not later.
5. **GPS via `geoReferencia(jwt)`** (in-session JS call) is fine. Some geo refs legitimately
   have no lat/lng → `n_geo < ` the number of geo links is normal.
6. **Two failure modes, different fixes — don't confuse them:**
   - *Throttle*: detail modals stuck on "Cargando", searches return "sin resultados". No
     block page. A fresh session may be enough.
   - *Device flag*: the F5 rejection page with a support ID, search still working. Only a
     **fresh profile** clears it.
   `waf_check.py` distinguishes them for you.
7. **Mobile access:** cellular IPs are usually clean. If one gets blocked, **toggle airplane
   mode** for a new IP — but see rule 8: that alone is almost never the fix.
8. **⚠️ RESET THE PROFILE, NOT JUST THE IP — the flag follows the device.**
   Validated 2026-07-20 (profile A vs B above, same IP throughout). The jar carries F5
   Shape's **`TSPD_101_DID`** — a *device* id, 224 bytes, set on both
   `oficinajudicialvirtual.pjud.cl` and `www.pjud.cl` — plus a full `TS*` set, all persisted
   across sessions. Renaming the profile dir aside and re-passing the CAPTCHA on the **same**
   IP fixed it immediately. So a "fresh session" means a **fresh profile dir**, not just new
   cookies or a new IP. Keep burned dirs as evidence (~150 MB each).
   *Corollary:* every past "fresh IP didn't help" result is **not** evidence about IPs —
   those runs were all re-using the same burned device id. Don't trust them.

---

## Environment — including the traps

### ⚠️ Which Python? It differs per machine — check before you run
- **Danko PC (`C:\Users\Danko`, the 2026-07-22 session):** there is **no `pjud_venv`**. Use the
  **system** interpreter `C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe` —
  it has playwright + psycopg2 + google-api. Do **not** use `felipe\scraper\.venv`: it has
  playwright and google-api but **no psycopg2**, so it dies at the Neon step.
- **The other PC:** venv at `%LOCALAPPDATA%\pjud_venv` (see below).
- One-liner to pick correctly on any machine:
  `python -c "import playwright,psycopg2,googleapiclient;print('ok')"`

### The other PC
- **Python 3.12** on PATH. **venv** at `%LOCALAPPDATA%\pjud_venv`.
- **⚠️ The venv needs the FULL `scraper/requirements.txt`, not just playwright.** An earlier
  version of this doc said "only playwright" — that is wrong and it fails at runtime:
  `--docs` and `ingest_cdp.py` both import the Google libs, and you get
  `ModuleNotFoundError: No module named 'google'` *after* you've already spent a CAPTCHA.
  ```
  %LOCALAPPDATA%\pjud_venv\Scripts\python.exe -m pip install -r requirements.txt
  ```
  (playwright, psycopg2-binary, requests, google-auth, google-auth-oauthlib,
  google-api-python-client.) Do **not** `pip install --upgrade pip` inside it — Windows file
  lock. No `playwright install` needed: we drive real Chrome, not a bundled browser.
- **⚠️ `felipe/scraper/.venv` is dead on the Usuario PC** — it points at
  `C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe`. Don't use it; it is
  the JPL project's venv from the other machine. Everything PJUD goes through `pjud_venv`.
- **⚠️ Git Bash trap:** `$LOCALAPPDATA` expands with **backslashes**, so
  `"$LOCALAPPDATA/pjud_venv/Scripts/python.exe"` silently falls through to the *system*
  Python and you get `can't open file` or missing modules. Use a fully-qualified
  forward-slash path: `C:/Users/<user>/AppData/Local/pjud_venv/Scripts/python.exe`. Also
  `cd` into `felipe/pjud/scraper` explicitly — the scripts resolve config relative to cwd.
- **Google Chrome** at `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- **CDP port 9333**, profile `%LOCALAPPDATA%\pjud_cdp` (fresh → CAPTCHA once, then persists).

### Credentials — MUST be copied (gitignored; NOT in the repo)
Put these in `felipe\pjud\scraper\` (copy via a private channel — **the repo is PUBLIC**):
- `pjud_config.json` — `pg_conn` (the **Neon** secret), Drive `folder_id` +
  `documentos_folder_id`, `start_date`.
- `client_secret.json` + `token.json` — Google OAuth (Drive, `drive.file` scope).
  Account **danko.buy@gmail.com**. (Same files live in `felipe\scraper\`; copying works.)

Sanity check before any run:
```
cd felipe\pjud\scraper
%LOCALAPPDATA%\pjud_venv\Scripts\python.exe -c "import gauth,gstore; c=gstore.load_config(); d=gauth.drive_client(gauth.credentials()); print('Drive OK', bool(d)); print('pg_conn?', bool(c.get('pg_conn')))"
```
Expect `Drive OK True` / `pg_conn? True`.

---

## Diagnostics — `scraper/waf_check.py` (new, 2026-07-21)

Read-only: no clicks, no searches, no downloads, so it never costs reputation.

```
python waf_check.py            # verdict + session state
python waf_check.py --cookies  # also dump the F5 cookie set
```

Verdicts: **HEALTHY** · **BLOCKED-DETAIL** (device flag → new profile) · **THROTTLED**
(rate → maybe just a new session) · **NO-SESSION**. It also prints the F5 support IDs and
confirms whether `TSPD_101_DID` is present.

**Run it before every scrape and immediately after any suspected block.** It is the single
cheapest habit for not wasting profiles.

---

## How to run

### Step 1 — operator opens the CDP Chrome (never the script)
Double-click **`felipe\pjud\Abrir_CDP.cmd`**. Then **by hand in that Chrome (all trusted):**
1. Pass the CAPTCHA → **Consulta Causas** → **Búsqueda por Fecha** tab.
2. **Competencia = Civil**, **Corte = C.A. de Santiago**, Desde `01/01/2026`
   Hasta `31/01/2026`; wait for the **Tribunales** list.
3. Select a tribunal and do **one manual search** — confirm results come back.
4. Run `waf_check.py` → expect **HEALTHY**.

### Step 2 — run the scraper (from `felipe\pjud\scraper\`, venv python)

**A) Careful single-tribunal harvest (most WAF-safe — use this by default now):**
```
python cdp_scrape.py --no-search --docs --gps --resume
```
Operator picks the tribunal + Buscar by hand; the script only harvests what's displayed,
using pure trusted clicks. Repeat per tribunal.

**B) Unattended sweep (keyboard tribunal-switch):**
```
python cdp_scrape.py --docs --gps --resume
```
Keyboard-switches through every `#fecTribunal` option. **The switch itself is validated and
innocent** — the 2026-07-21 block happened while still on the first tribunal — but given the
~6-causa budget this will not get far unattended. Add caps: `--max-tribs 3 --max-causas 12`.

**Flags:** `--port 9333` · `--max-tribs N` (0=all) · `--max-causas N` (0=no limit) ·
`--proc "Ejecutivo Obligación de Dar"` · `--docs` · `--gps` · `--no-search` · `--resume`.
Output: `Downloads\pjud_cdp_<epoch>.json`, **written incrementally — it survives a kill, so
always ingest what you got before resetting anything.**

### Step 3 — ingest into Neon (+ Drive links)
```
python ingest_cdp.py "%USERPROFILE%\Downloads\pjud_cdp_<epoch>.json"        # --dry to preview
python ingest_cdp.py "...\pjud_cdp_<epoch>.json" --list-only                # a --count-only JSON
```
Idempotent UPSERTs; marks each causa `fill_status='scraped'` so `--resume` skips it.

**`--list-only`** (2026-07-21) ingests a `--count-only` list JSON: causa **shells** only
(`causa_id, rol, f_ingreso, tribunal_id, competencia`) via `INSERT ... ON CONFLICT DO
NOTHING`, so existing causas are untouched and new ones land at `fill_status=''` — i.e. the
rols are registered as *pending work* and a later detail scrape still collects them. The
normal path now **refuses** a headerless JSON (it would have blanked the header columns and
marked them `'scraped'`, so `--resume` would skip them forever). `caratulado` is dropped —
`causas` has no such column; the parties arrive with the litigantes.

---

## Storage — Neon + Drive

- **Neon** `neondb` (PG 18), connection from `pjud_config.json` → `pg_conn`. Tables are
  **UNPREFIXED**, built by `dbstore._ddl()`: `bancos, tribunales, ruts, causas, litigantes,
  cuadernos, escritos, documentos, anexos, notificaciones_receptor` (+ `sweep_progress`,
  `coord.py` worker tables).
- **Drive**: PDFs → the "Documentos" folder (`documentos_folder_id`), flattened
  `<causa_id>__c<n>__<folio>-<k>-doc.pdf`; `documentos.url` holds the webViewLink.

### ⚠️ Actual schema (an earlier version of this doc got this wrong)
The old text said "child FK column is `causa_id`" for everything. **Not true for
`documentos`.** Verified against the live DB 2026-07-21:

```
causas     : causa_id (PK), rol, f_ingreso, estado_adm, procedimiento, ubicacion,
             estado_proc, etapa, tribunal_id, competencia, ebook, updated_at,
             fill, fill_status, uid          <-- there is NO `id` column
cuadernos  : id (PK), causa_id (FK), cuaderno, folio, etapa, tramite,
             descripcion_tramite, fecha_tramite, fecha_diligencia, foja, georref, uid
documentos : id (PK), cuaderno_id (FK -> cuadernos.id), origen, folio,
             descripcion, url, uid           <-- joins via CUADERNO, not causa
```
So counting a causa's documents needs the join:
```sql
select c.causa_id, count(*) from documentos d
  join cuadernos c on c.id = d.cuaderno_id
 where c.causa_id = '259-C-1510-2026' group by 1;
```

### ⚠️ JSON field names (bite-sized traps when verifying a run)
- Drive links are in **`doc_url`** / **`anexo_url`** on each historia row — *not* a `url` key.
- **`geo`** holds the raw **JWT** (the unresolved geo link), **not** coordinates.
- **`georref`** holds the resolved result as a **Google-Sheets formula** — a leftover from
  the pre-Neon design, stored verbatim into `cuadernos.georref`:
  `=HYPERLINK("https://maps.google.com/maps?ll=-33.5605048,-70.5835436&z=16","-33.560504, -70.583543")`
  Grepping the JSON for `lat` finds **nothing**; count resolved rows with
  `georref.startswith('=')`, which is exactly what `n_geo` does.
  *Worth cleaning up eventually* — a spreadsheet formula in a Postgres column makes SQL geo
  queries impossible without string parsing. Left as-is for now for consistency with the
  existing rows; would need scraper + ingest + a lat/lng column together.

### Deterministic IDs (mirror run.py — do NOT regress)
Rols are **per-tribunal** (same rol under many tribunal_ids = distinct cases).
- `tribunal_id` = the OJV `#fecTribunal` option **value** (1º Juzgado Civil de Santiago =
  **259**, 2º=260, 3º=261…). `cdp_scrape` records it as `tribunalId`.
- `causa_id` = `<tribunal_id>-<rol>` (e.g. `259-C-1565-2026`)
- litigante `id` = `<causa_id>-<rut>` · cuaderno `id` = `<causa_id>-c<n>-<folio>-<k>` ·
  escrito `id` = `<causa_id>-e<i>` · receptor `id` = `<causa_id>-r<i>` ·
  documento `id` = `<cuaderno.id>-doc` · anexo `id` = `<cuaderno.id>-anexo`.

---

## Scope / filter

- **Bank plaintiff**: `caratulado` contains a bank token (SANTANDER, BANCOESTADO/BANCO DEL
  ESTADO, ITAU, SCOTIABANK, BCI/CREDITO E INVERSIONES, BANCO DE CHILE, FALABELLA, COOPEUCH,
  BICE, CONSORCIO, RIPLEY, BTG, BANCO INTERNACIONAL). List in `cdp_scrape.BANK`.
- **Rol starts with `C`** — kept. `E-` rols are **Exhorto**, OUT of scope.
- **Procedure**: target is "Ejecutivo Obligación de Dar". Pass
  `--proc "Ejecutivo Obligación de Dar"` to drop non-matching causas after opening. All 6
  causas scraped on 2026-07-21 came back with exactly this procedimiento.

---

## Database state as of 2026-07-21 (end of day, after the list ingest)

```
causas                   3177      fill_status:  ''        2165
cuadernos               63323                    skipped    845
litigantes              13866                    done       124
documentos               1757                    error       37
anexos                      0                    scraped      6
notificaciones_receptor 17173
tribunales                168
```

The **6 `scraped`** are the 07-21 session's, all at tribunal 259 (1º Juzgado Civil de
Santiago): `259-C-1510-2026, -C-1513-2026, -C-1518-2026, -C-1525-2026, -C-1543-2026,
-C-1565-2026`. 0 dangling FKs.

`causas` grew 3144 → **3177** because the 53-causa January list for tribunal 259
(`--count-only`) was ingested with the new **`--list-only`** path: **33 rols that existed
nowhere in the DB** are now registered as shells at `fill_status=''`; the other 20 were
already known and were left untouched. So tribunal 259 / January is now **completely
enumerated** in the DB (53/53) and only the *detail* is missing (47 at `''`, 6 `scraped`).

Note `--resume` skips **only** `fill_status='scraped'`, so the rows at `''` (both the new
shells and the ~2.1k metadata-only rows from the old `run.py`) will be scraped for detail —
that is intended, not a bug.

---

## Where the data stands (end of 2026-07-22)

```
causas     3718        scraped 676 causas across 14 tribunales
litigantes 16265       (started the day at 6 scraped)
cuadernos  74213
receptor   20617
documentos  1816
```
Cortes touched: **Santiago** (259-266, January + some February), **Concepción / Los Ángeles**
(154, 155, 157), **Antofagasta** (13, 16), **La Serena** (40). Santiago 259-266 January are the
most complete. NB worker 1 spent its last hours on **February** Santiago (the operator rebuilt
the form with `01/02..28/02` after a session-expiry reset), so January is NOT finished.

## NEXT STEPS (in order)

1. **Settle the 3-worker question** — fresh profile + RICH manual warm-up (5+ min), added as the
   third worker. IP limit or trust standing? This decides whether throughput scales on one
   connection or needs a second (mobile) one. See the parallelism section.
2. **Run the overnight single-worker sweep.** One well-warmed profile holds ~3 causas/min
   indefinitely (439 causas in one run, then 68 more in another, no blocks). Santiago-January has
   ~23 tribunales left. `cdp_scrape.py --resume` (no `--docs`), watchdogs on.
3. ~~Fix `next_page`~~ **DONE 2026-07-23** — but the consequence is outstanding: **every tribunal
   swept before that commit must be re-swept**, because the missing causas are the oldest dates of
   each window and nothing in the DB marks them as missing. `--resume` handles it correctly (it
   skips what is already `scraped` and collects the rest), so a re-run costs only the new causas.
4. **Automate the block recovery**: close the OJV tab → reopen from `www.pjud.cl` → re-establish
   the form. That is the operator's manual fix and it works; wiring it in turns a block into a
   pause. Pair it with `establish_form_kbd` so a session-expiry reset does not need a human either.
5. **Re-measure the detail/`--docs-inpage` budget.** 5 causas / 54 PDFs ran clean; the ceiling is
   unknown, and the old "died at 3 causas" datum is suspect (it may have been a stuck modal).
6. (Optional) migrate `georref` from the `=HYPERLINK` formula to real lat/lng columns.
7. **⚠️ Revoke the leaked GitHub PAT — still open, and it is more exposed than this list said.**
   It was stripped from `settings.local.json` before ever being pushed, but the token is not just
   sitting in an old file: **it is embedded in the `origin` remote URL in `C:\Claude\.git\config`**
   (`https://dankobuy-ops:ghp_…@github.com/dankobuy-ops/Felipe.git`), so it is what this repo
   authenticates with on every fetch/push and it prints in full to anyone who runs `git remote -v`.
   `.git/config` is not tracked, so it has never been pushed. Fix: revoke the token on GitHub,
   then re-point the remote at the bare URL (`git remote set-url origin
   https://github.com/dankobuy-ops/Felipe.git`) and let the credential manager hold the new one.
8. ~~**Housekeeping:** burned profile dirs~~ **DONE 2026-08-05** — 19 dead
   `%LOCALAPPDATA%\pjud_cdp*.{burned,viejo,polluted,old}-*` dirs deleted, 3.58 GB freed. The 7
   live/experiment profiles (`pjud_cdp`, `_w2`…`_w5`, `_boot`, `_zero`) were left untouched —
   **never delete those; each one holds earned F5/v3 trust that costs a human warm-up to rebuild.**

---

## File map (all under `felipe/pjud/`)

**CDP path (current/active):**
- `scraper/cdp_scrape.py` — the scraper. Connect-only; **`human_click()` + `_human_pointer()`
  — the WAF fix, used for EVERY click (see the top section; never reintroduce a bare
  `.click()`), which now waits via `wait_idle()` and REFUSES to click a covered target**;
  `clear_stuck_modal()` (Escape → close → jQuery hide → reload); `page_busy()`/`wait_idle()` on
  the site's `#loadPre*` spinner; watchdogs `--max-fails` / `--max-empty` (exit 3 = profile
  spent); `download_doc_inpage()` + **`--docs-inpage`** (PDFs fetched BY the page);
  `--no-search` harvest; `select_tribunal_kbd` keyboard sweep;
  **`--corte/--desde/--hasta` → `establish_form_kbd`** (builds the whole Búsqueda-por-Fecha
  form with TRUSTED keyboard, no manual search; VALIDATED — returns 53 for trib 259) +
  `form_ok()` auto-recovery for the session-expiry form reset; **`type_date_kbd`** (dates set
  by real keystrokes, never JS `.value`+dispatchEvent); `--docs` (→Drive via `dbstore`),
  `--gps`, `--resume`, `--count-only`; incremental JSON; gentle randomized pacing
  (`P_CAUSA 5-10s / P_PAGE 4-8s / P_TRIB 6-12s / P_STEP 0.6-1.6s`).
- `scraper/ingest_cdp.py` — JSON → Neon (idempotent upserts, deterministic ids, Drive links,
  marks `fill_status='scraped'`). **`--list-only`** ingests a `--count-only` list as causa
  SHELLS (`ON CONFLICT DO NOTHING`, `fill_status` untouched → stays pending work); the normal
  path now REFUSES a headerless JSON (would blank headers + mark 'scraped').
- `scraper/net_probe.py` — **read-only network recorder. Injects nothing.** Logs every
  request's POST params (reCAPTCHA token fingerprinted) + F5-reject flag to
  `netprobe_<label>_<epoch>.jsonl`, so a manual search and a script search can be diffed.
  Follows **all tabs**; waits via Playwright (never `time.sleep` — that captures 0 events).
- `scraper/search_probe.py` — **one search per run, one variable changed, verdict from the
  RESPONSE.** `--mode click|human|clear|kbd|kbd-slow`, `--bare`. The cheapest way to test any
  future WAF hypothesis; it is what proved `page.click` was the blocker.
- `scraper/waf_check.py` — **read-only WAF/session health check. Run before and after.** Picks the
  tab holding the search form (not a leftover document tab) and distinguishes **STUCK-MODAL**
  (exit 4, recoverable) from **BLOCKED-DETAIL** (exit 1). ⚠️ Still not authoritative: when it says
  blocked, CONFIRM functionally with `cdp_scrape.py --no-search --max-causas 1` before burning a
  profile. (TODO: teach it the stuck-disabled-Buscar signature.)
- `scraper/bootstrap_probe.py` — can we reach Consulta Causas with no human? Clicks through from
  `www.pjud.cl`. Answer: the form is reachable, but a virgin profile is **blocked on its first
  scripted search** — the human warm-up is the session earning a reCAPTCHA-v3 trust score, not
  solving a puzzle.
- `Abrir_CDP.cmd` — open the CDP Chrome only. `Probar_CDP.cmd` — venv + Chrome + scraper.
- `scraper/dbstore.py` (Neon + Drive), `scraper/gauth.py` (Drive OAuth), `scraper/gstore.py`
  (Drive helpers + `TABS` schema), `scraper/pjud_config.json` (gitignored secrets).

**Dead ends / legacy (do NOT invest):**
- `inpage/*` + `Abrir_PJUD_sin_debug.cmd` — in-page bookmarklet (isTrusted wall).
- `scraper/run.py` + `HANDOFF.md` + `schema.sql` + `coord.py` — the older Sheets/daily-sweep
  design; `run.py --fill` CDP-collab is dead for the same isTrusted reason.
  `schema.sql` now carries a SUPERSEDED header (the live Neon tables are unprefixed and built by
  `dbstore._ddl()`, not by that file).

### ★ 2026-08-05 — the daily GitHub-Actions cron was still armed, and failing 17×/day

`.github/workflows/pjud.yml` (at the **repo root**, `C:\Claude\.github\workflows\` — not
`felipe/.github/`, which GitHub ignores) still had `schedule: cron "0 9 * * *"` firing a 17-job
matrix of `run.py`. It had failed **every scheduled run** from at least 2026-07-27 through
2026-08-05 — every corte, same error:

```
RuntimeError: could not establish the date search form: Timeout 30000ms exceeded.
```

That is **GATE 1**: a headless runner never gets past the invisible reCAPTCHA v3 on
`accesoConsultaCausas()`, so it never reaches `indexN.php` and never sees a form to establish.
The failure is a clean confirmation of the two-gates finding from a completely different code
path — and it means the daily job was hitting the OJV from 17 runner IPs for nothing.

**The `schedule:` block is now commented out; `workflow_dispatch` is kept** so the matrix can
still be fired by hand if the site's entry path ever changes. Scraping remains local-CDP only
(`Abrir_Worker.cmd` → `cdp_scrape.py`).
