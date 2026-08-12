# Poder Judicial Virtual (pjud)

Second scraper — targets the **Oficina Judicial Virtual** del Poder Judicial.

**Goal:** civil *Ejecutivo Obligación de Dar* causas with a **bank plaintiff**, nationwide, with
full detail and PDFs, into **Neon Postgres** (+ documents to Google Drive). It drives a **real,
headed Chrome over CDP** — never headless, and never a bare `.click()`; both are load-bearing and
the reasons are in the handoffs.

### Which document to read

| you want to | read |
|---|---|
| run or change a worker | **`HANDOFF_WORKERS.md`** — architecture, pacing with evidence, block recovery, Neon schema, traps |
| understand the site or the WAF | **`HANDOFF_CDP.md`** — entry gates, block tiers, and how each conclusion was reached. Its header lists what is superseded |
| set up the second machine | **`HANDOFF_PC2.md`** — worker B, the filtered backfill |
| know why it is built this way | `HANDOFF.md` — ⚠️ **superseded**, the abandoned Sheets/headless/cron design, kept for history only |

⚠️ Treat every measurement in these files as **dated**. The OJV is actively changed, and several
conclusions here were overturned by later evidence in the same document — the headers say which.

Layout (mirrors the JPL project's separation):
- `scraper/` — Python backend (scraper + helpers).
- `screenshots/` — dev screenshots (gitignored).
- Frontend SPA lives at `felipe/spa/pjud/` (published to GitHub Pages at `/Felipe/pjud/`).
- GitHub Actions workflows for this scraper live at the repo root `.github/workflows/` (prefix names with `pjud-` to keep them separate from the JPL ones).

The JPL scraper is unchanged: backend at `felipe/scraper/`, frontend at `felipe/spa/jpl/`.
