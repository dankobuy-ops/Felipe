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
SEARCH_GAP   = 60.0   # search click to search click
PAGE_GAP     = 20.0   # paginator clicks
CAUSA_GAP    = 90.0   # between causa opens   ← the one that matters
POST_CAUSA   = 30.0
COOL_OFF     = 180.0  # × recovery number, after a block
CLEAN_STREAK = 12     # clean opens that win the recovery budget back
```

Real open-to-open intervals, measured from logs (the two gaps add up, so config ≠ observed):

| config | idle | observed open→open | outcome |
|---|---|---|---|
| 45 + 15 | 60 s | median **99 s** | **blocked at 11 opens** |
| 90 + 30 | 120 s | median **143 s** | 50+ opens, no block |

⚠️ **"One minute between causas" is not an untried idea — it is the setting that blocked.**

The limit behaves like a **rate**, not a quota: the same IP has now done well over 50 opens in a
day without a second block. Searches are cheap and their 60 s is the best-evidenced number here;
do not slow them looking for safety, and do not speed up detail looking for time.

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

## 9. State of play, 2026-08-07 evening

- Worker A sweeping nationwide, 15/07/2026 → 07/08/2026, on `pjud_wA1` / port 9342.
- ~85 causas harvested, **every one with a verified ebook PDF**; 1 block, auto-recovered.
- Neon: **4,120+ causas**, typed columns, 91 direct Drive URLs.
- Ebooks average ~1 MB, 15–16 pages. Budget the full national window at several hundred MB.

### Next

1. Let the sweep finish (~6 h remaining at the time of writing), then re-run `ingest_worker_a.py`.
2. **Build worker B** — `grab_doc` already does the work; it needs the causa-reopen loop and its
   own profile, run on its own so it never competes with A for the same IP budget.
3. **Worker C** — refresh. Needs a decision on what "changed" means (new historia row? new
   escrito?) before it is worth writing.
4. **Notificaciones and Exhortos** modal tabs are still unparsed and have no columns. Free to
   read once the modal is open — they belong in worker A's free harvest when someone adds them.
5. `waf_check.py`'s stale profile-rotation advice (§5).
6. **Revoke the GitHub PAT embedded in the `origin` URL** in `C:\Claude\.git\config` (see it with
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
