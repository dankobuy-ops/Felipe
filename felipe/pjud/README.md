# Poder Judicial Virtual (pjud)

Second scraper — targets the **Oficina Judicial Virtual** del Poder Judicial.

**Goal:** civil *Ejecutivo Obligación de Dar* causas with a **bank plaintiff**, nationwide, with
full detail and PDFs, into **Neon Postgres** (+ documents to Google Drive). It drives a **real,
headed Chrome over CDP** — never headless, and never a bare `.click()`; both are load-bearing and
the reasons are in the handoffs.

**The score is sustained NEW records per hour, without tripping** — measured against the site,
not against a recording. See [`../CLAUDE.md`](../CLAUDE.md) → "The ultimate goal". A metric you can
compute offline, with the site switched off, is measuring fidelity rather than results.

### Which document to read

| you want to | read |
|---|---|
| run or change a worker | **`HANDOFF_WORKERS.md`** — architecture, pacing with evidence, block recovery, Neon schema, traps |
| understand the site or the WAF | **`HANDOFF_CDP.md`** — entry gates, block tiers, and how each conclusion was reached. Its header lists what is superseded |
| set up the second machine | **`HANDOFF_PC2.md`** — worker B, the filtered backfill |
| know why it is built this way | `HANDOFF.md` — ⚠️ **superseded**, the abandoned Sheets/headless/cron design, kept for history only |
| write a NEW scraper | **[`../../SCRAPERS_HANDBOOK.md`](../../SCRAPERS_HANDBOOK.md)** — what generalises beyond this site, starting with THE ONE RULE |

### The workers, split by how much of the causa each takes

| worker | file | takes | cost per causa |
|---|---|---|---|
| **H** the mimic | `scraper/worker_h.py` | **what a measured human does** — metadata + both cuadernos, zero keystrokes, dates by picker, pointer alive throughout. `--fill` targets the database's work-list instead of sweeping | 1 open, **0 fetches** |
| **A** discovers | `scraper/worker_a.py` | sweeps tribunales; per bank causa the free modal harvest + ebook | 1 open, 1 fetch |
| **B** finishes | `scraper/worker_b.py` | every document, every georreferencia, every cuaderno, receptor | 1 open, **40+ fetches** |
| **C** refreshes | `scraper/worker_c.py` | re-opens a finished causa, takes only what is **new** | 1 open, **0 fetches** |

★ **Worker H is the fastest thing here** — 1,046 opens in 150 minutes with zero blocks, against
worker A's all-time local best of 375. ⚠️ *Safest* is not established: no run has compared block
rates between configurations, and its speed is now known to sit at the SITE's floor (~8-9 s per
open) rather than above it. It is the mimic built from a *recorded* human
session, and every gain came from removing something a person could not do (typed dates into
readonly fields, no horizontal scrolling, a frozen pointer), never from pacing.

⚠️ **`--fill` needs a corpus.** It re-opens causas the database says are incomplete; pointed at a
window nothing was ever swept for it reports `nothing-searched`, which reads like a block and is
not. Sweep a new window with worker A (`pjud-censo.yml`) first.

⚠️ **Worker C's whole value is that last zero.** A refresh that re-downloads what it already holds
costs exactly what B costs and buys nothing — while looking completely successful. The skip lists
live in the *shared* harvest (`cdp_scrape.KNOWN_DOCS` / `KNOWN_GEO` / `KNOWN_HEADER`), and
`night_check.py --stage after-c` fails the run if C re-buys a document for a row it already had.

**Where the work runs:** bulk sweeping is **local** and permanent (a residential session does 730+
opens a day). Runners get worker B and C, whose work is bounded by construction. See
`HANDOFF_WORKERS.md`.

**Test queue:** `.github/workflows/pjud-noche.yml` — one dispatch, six tests, strictly one at a
time. **No cron anywhere in this project**, deliberately.

### Seeing what a runner does — a runner has no screen

| tool | answers |
|---|---|
| `--shots DIR` | *what killed it* — screenshots + page state on failure paths only |
| `--live` + `watch_live.py` | *what is it doing right now* — a live card on `127.0.0.1:8899`, through Neon |
| `--trace {entry,all}` | *how did it get there* — a frame **before and after every action**, plus one contact-sheet HTML (`trace_sheet.py`) |
| `--step {entry,all}` + `step_console.py` | *single-step it* — the runner blocks before each action and waits for `go` / `run` / `abort` |

Both cloud workflows expose `trace`; `pjud-fill.yml` also exposes `step`. See
`HANDOFF_WORKERS.md` → **THE 2026-08-18 SESSION** for how to drive them.

### Measuring it — which question each tool answers

| question | tool |
|---|---|
| is the site up, and what does it serve? | `scraper/site_health.py [--watch N]` — clicks through, no search, no causa |
| what request rate is the fleet making now? | `scraper/rate_watch.py --mins 8` — ⚠️ read the **`result requests alone`** line, not the total |
| how did an experiment arm score? | `scraper/expduty_score.py --new` — ⚠️ run it **before** the ingest, or it scores its own records as already held |
| what does the worker emit vs a human? | `scraper/human_profile.py --file A --vs B` — reports per-ACTIVE and per-WALL second, and the duty cycle |
| record a human, or a worker, identically | `scraper/human_record.py --port N` |
| did the data actually land? | `scraper/ingest_worker_h.py --dry`, then count in Neon — a run's own tally is not evidence |
| how many workers can one address carry? | `Experimento_Fleet.ps1 -Workers N -Speed S` |
| what is a spec setting worth? | `Experimento_Specs.ps1` (a focus × duty matrix) |

⚠️ **The survival column is empty.** Every throughput figure in these docs is real; no run has
ever compared BLOCK rates between two spec configurations, so the duty cycle costs ~50% of
throughput on the strength of a recording and its benefit is unmeasured. See
`HANDOFF_WORKERS.md` → section 00.

⚠️ Treat every measurement in these files as **dated**. The OJV is actively changed, and several
conclusions here were overturned by later evidence in the same document — the headers say which.

Layout (mirrors the JPL project's separation):
- `scraper/` — Python backend (scraper + helpers).
- `screenshots/` — dev screenshots (gitignored).
- Frontend SPA lives at `felipe/spa/pjud/` (published to GitHub Pages at `/Felipe/pjud/`).
- GitHub Actions workflows for this scraper live at the repo root `.github/workflows/` (prefix names with `pjud-` to keep them separate from the JPL ones).

The JPL scraper is unchanged: backend at `felipe/scraper/`, frontend at `felipe/spa/jpl/`.
