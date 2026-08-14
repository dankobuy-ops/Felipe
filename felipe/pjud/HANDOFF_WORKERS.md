# PJUD — Worker architecture handoff (2026-08-07)

Companion to `HANDOFF_CDP.md`, which remains the reference for **the site and the WAF** (entry
gates, block tiers, the corte-change burst, the two-button trap). This file covers **the workers**:
what they do, why they are shaped this way, and every trap that cost real time.

**⚠️ Treat every measurement here as DATED.** The OJV is being actively changed — "Corte = Todos"
did not work before 2026-08-06 and does now. Re-verify anything load-bearing before relying on it.

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
