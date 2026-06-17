# Handoff — Felipe Project

**Last updated:** 2026-06-10 (repo cleanup + sheets export + SPA history)  
**Branch:** main  
**Repo:** https://github.com/dankobuy-ops/Felipe.git

---

## ⚠️ ACTIVE NOTES — read before touching deployment/scraper (2026-06-10)

Recent session work (other Claude session, please read):

### REPO CLEANUP (2026-06-10) — history was rewritten
- **Purged `sga/`, `Apps/`, `Recursos/`, `Otros/` from the Felipe repo** (history
  + working tree) via `git filter-repo`. They were unused duplicates bloating the
  repo (~580 MB / ~5,373 files). `.git` went ~400 MB → 124 MB. Force-pushed
  (`f4ec43b`). The ORIGINAL `C:\Claude\sga` is a SEPARATE repo and was untouched.
- **Consequence:** history is rewritten — any old clone must re-clone or hard-reset.
- **Safety backup** (full repo, pre-cleanup): `C:\Claude\Felipe\..\Felipe-backup-precleanup-333796f.bundle`
  (and an earlier `Felipe-backup-fd5ab89.bundle`). Restore with `git clone <bundle>`.
- The Felipe repo root is `C:\Claude\Felipe` (NOT `C:\Claude` — the old note was
  wrong). It now contains only: `.claude .github .gitignore README.md docs felipe`.

### PDF LINKS IN SPA — FIXED (the "broken page")
- The SPA "Abrir" links pointed at the SOURCE `MostrarPDF.aspx` href, which 302s
  to Login.aspx in a normal browser (forms-auth) → broken page. The downloaded
  PDFs live in public Supabase Storage. `run.py download_pdfs` now tags each
  trámite/adjunto with its Supabase public `pdf_url`; `app.js` links to that
  (`safeHref(t.pdf_url)`). Old jobs scraped before this have no `pdf_url` → re-run.

### PREVIOUS-JOBS HISTORY (SPA)
- "Consultas anteriores" list on the trigger screen (`renderJobHistory` in app.js).
  Tracks jobs in localStorage (rut/year/date) + cross-references Supabase
  `__job__`/`__meta__` rows for live status. Click an entry to reopen its results.
  Scraper writes `rut`/`year`/`ts` into `__meta__` (`write_meta`) for labels.

### GOOGLE SHEETS EXPORT (standalone)
- `felipe/scraper/export_sheets.py` — reads Supabase checkpoints (`--job-id` or
  `--all`), builds two linked tables and POSTs to a Google Apps Script web app:
    - **Causas** tab (Level 2 + summary), **Documentos** tab (Level 3 PDFs).
    - Linked by `Caso ID` = `<job-prefix>/<ROL>` (first column, tells dup ROLs apart).
- `felipe/scraper/sheets_webapp.gs` — the Apps Script the user pastes into the
  target sheet (Extensions→Apps Script→deploy as Web app, Execute as Me, Anyone).
  Returns the `/exec` URL; pass via `--webhook` or `SHEETS_WEBHOOK_URL`. Each run
  is a full refresh (clears+writes both tabs). No GCP/service account needed.
  My (Claude) Google MCP can only CREATE sheets, not write to existing ones — hence
  the Apps Script approach.

**STATUS 2026-06-10: scraper works END-TO-END.** Verified run (year=2019,
RUT 96992030-1): search→login→74 causas→Level 3 extraction→PDFs. Job marked
`complete`, 11/11 causas done, PDFs in Supabase Storage with real sizes.
Key fixes below. The site is `appl.smc.cl/JuzgadoDoc` (forms-auth), reached
via the vitacura.cl parent link.

**STORAGE IS NOW PUBLIC.** The `pdfs` bucket was switched to public and
`storage.py` returns permanent public URLs (`/object/public/...`) instead of
1-hour signed URLs (those expired → "broken page"). All previous jobs +
storage objects were wiped on 2026-06-10 for a fresh start.

**'Stuck on last record' — FIXED.** The results list can repeat a ROL;
checkpoints are keyed by (job_id, record_id) so duplicates collapsed and the
old `done_count == len(records)` completion check was unsatisfiable → job
re-dispatched until the cap stalled it. Now records are deduped by ROL and
completion is set-based (`target_rols.issubset(done_rols)`).

0. **Level 2 search was scraping the FORM, not results — FIXED** (`run.py`).
   - The vitacura form is ASP.NET: search-type radios `RdBoRut/RdBoRol/RdBoPPU`,
     field `txtRut`, submit `btnAceptar`. The old code filled `txtRut` and
     submitted WITHOUT selecting the `RdBoRut` radio, so the postback just
     re-rendered the form. `get_results_list` then parsed the nested layout
     tables and produced fake causas (ROL = "Consulta de Juzgado", "PPU", ...),
     all of which failed at "Abrir". `search_rut` now checks `RdBoRut` first
     (handles AutoPostBack), then fills + submits. Added a FORM_MARKERS guard
     that raises "still on search form" instead of inventing causas.
   - NOTE: the real results-table column mapping in `get_results_list`
     (cells[0]=fecha, [2]=rol, [3]=descripcion) is still UNVERIFIED against a
     real results page — confirm via the [DEBUG TABLES]/[DEBUG Level2] dump on
     the next successful run and adjust if needed.
   - **Runaway re-dispatch — FIXED** in `.github/workflows/scrape.yml` (the
     ROOT one is the ACTIVE workflow; `felipe/.github/workflows/scrape.yml` is
     dormant — GitHub only reads root `.github/workflows`). The cap step's
     `exit 0` only ended that step, so the job kept scraping + re-dispatching
     past the cap (saw attempt 14 / max 10). Now it sets `capped=true` output
     and the Run/Re-dispatch steps skip on it.


1. **GitHub Pages — DO NOT re-add `.github/workflows/apps.yml`.**
   - A repo has exactly ONE Pages site. `apps.yml` deploys the `Apps/` folder
     on *every* push; `pages.yml` deploys `felipe/spa/` only on `felipe/spa/**`
     changes. They target the same `github-pages` environment, so `apps.yml`
     kept overwriting the scraper SPA with the Apps launcher page.
   - **Symptom:** `https://dankobuy-ops.github.io/Felipe/` shows the "Apps —
     dankobuy" page instead of the "Consulta JPL" scraper.
   - **Fix:** `apps.yml` was deleted (again). The Apps launcher has its own
     repo/site at `dankobuy-ops.github.io/Apps`; it should NOT deploy from here.
   - It reappeared once via a pull on 2026-06-10 — if you need Apps served too,
     give it a `paths: ['Apps/**']` filter or its own repo, never an unfiltered
     push trigger here.

2. **PDF downloads — FIXED** (`scraper/run.py` `download_pdfs`/`_fetch_pdf`).
   - The "empty page" PDFs were a SYMPTOM of the broken search: Abrir links are
     `MostrarPDF.aspx?...IdDoc=N` viewer URLs that **302→Login.aspx unless the
     session is authenticated**. With search broken there was no forms-auth
     cookie, so `request.get(href)` returned the Login shell.
   - Now search establishes the auth cookie, so `_fetch_pdf` fetches each
     captured href via `context.request.get` (shares cookies), checks `%PDF-`,
     and falls back one level to an embedded `<embed>/<iframe>/<object>`/href if
     the viewer returns HTML. Verified: real multi-KB/MB PDFs upload to Storage.
   - (An earlier popup-click approach was tried and reverted — the Abrir clicks
     never opened a window in headless; the authenticated href fetch is simpler
     and works.)

3. **Scraper 409 bug — FIXED** (`scraper/checkpoint.py`).
   - `write_checkpoints` did an upsert (`Prefer: resolution=merge-duplicates`)
     but never named the conflict target, so PostgREST resolved against the
     primary key `id` and 409'd on re-dispatch when `(job_id, record_id)` rows
     already existed. Added `?on_conflict=job_id,record_id` to the POST URL.
     This had been killing every run via `mark_stalled`/`mark_job_status`.

4. **TESTING hardcodes — REVERT before production.**
   - `.github/workflows/scrape.yml`: `TEST_SEARCH_CODE=96992030-1` and
     `TEST_TARGET_URL=https://vitacura.cl/.../juzgado-policia-local/` override
     the SPA inputs in the validate/run/re-dispatch steps. Revert to
     `github.event.inputs.*` when done.
   - `felipe/spa/index.html`: the RUT + URL fields are prefilled with those same
     test values (`value="..."`). Clear the `value=` attrs for production.

5. **Security — tokens still need rotation.**
   - Two `ghp_` tokens (old `DISPATCH_PAT` `ghp_L21Y…` and a push token
     `ghp_N3Op…`) were exposed. Git history was rewritten with `git filter-repo`
     to purge them (force-pushed `a7b2751`), and the plaintext token was removed
     from this file. **They are still live until revoked** —
     rotate at https://github.com/settings/tokens.

---

## What this repo is

`C:\Claude\felipe` is an isolated project workspace synced via GitHub (`dankobuy-ops/Felipe`).
It is NOT part of the SGA or Apps repos — it is its own thing.

The git root is `C:\Claude` (one level up from `felipe\`). The Felipe remote is set as `origin` on that root repo.

---

## Step 0 — Pull the repo on the new PC

If the `C:\Claude` repo already exists locally:
```bash
git remote set-url origin https://dankobuy-ops:<GITHUB_PAT>@github.com/dankobuy-ops/Felipe.git
git pull origin main --allow-unrelated-histories
```

If starting fresh:
```bash
git remote add origin https://dankobuy-ops:<GITHUB_PAT>@github.com/dankobuy-ops/Felipe.git
git pull origin main --allow-unrelated-histories
```

---

## Step 1 — Environment checklist

Run each check. If the output says NOT FOUND, install using the command in the next section.

```bash
git --version                          # need 2.x+
node --version                         # need 18+
npm --version                          # comes with node
python --version                       # need 3.10+
pip --version                          # comes with python
bun --version                          # need 1.x+
gh --version                           # GitHub CLI — needed for workflow_dispatch
claude --version                       # Claude Code CLI
gcloud version                         # Google Cloud SDK — needed for GCS
python -c "import playwright"          # Playwright — scraper engine
python -c "import google.cloud.storage"  # GCS Python client
python -c "import googleapiclient"     # Google Sheets API client
python -c "import requests"            # HTTP library
```

**Status on the PC where this was written (2026-06-03):**

| Tool | Status | Version |
|---|---|---|
| Git | INSTALLED | 2.53.0 |
| Node.js | INSTALLED | 24.15.0 |
| npm | INSTALLED | 11.12.1 |
| Python | INSTALLED | 3.12.10 |
| pip | INSTALLED | 25.0.1 |
| Bun | INSTALLED | 1.3.14 |
| gh CLI | **MISSING** | — |
| Claude Code | INSTALLED | 2.1.161 |
| gcloud CLI | **MISSING** | — |
| Playwright (Python) | **MISSING** | — |
| google-cloud-storage | **MISSING** | — |
| google-api-python-client | **MISSING** | — |
| requests | **MISSING** | — |
| Chrome | INSTALLED | (system) |
| gstack skills | INSTALLED | 54 skills |

---

## Step 2 — Install missing tools

Install only what the checklist above flags as missing.

### gh CLI (GitHub CLI)
```bash
winget install --id GitHub.cli -e
```
Then authenticate:
```bash
gh auth login
# choose: GitHub.com → HTTPS → Login with a web browser
```

### gcloud CLI (Google Cloud SDK)
```bash
winget install --id Google.CloudSDK -e
```
After install, restart terminal, then:
```bash
gcloud init
gcloud auth application-default login
```

### Playwright (Python scraper engine)
```bash
pip install playwright
playwright install chromium
```

### Python packages for GCS + Sheets
```bash
pip install google-cloud-storage google-api-python-client google-auth-httplib2 google-auth-oauthlib requests
```

### Bun (used by gstack)
```bash
# In PowerShell:
irm bun.sh/install.ps1 | iex
```

### Node.js (if missing)
Download from https://nodejs.org — LTS version.

---

## Step 3 — Gstack setup

Gstack skills live at `C:\Claude\.claude\skills\` and are available to ALL Claude sessions under `C:\Claude\`.

After pulling the repo, if the skills folder is empty or missing, reinstall:
```bash
bash /c/Claude/.claude/skills/gstack/setup --no-prefix -q
```

To verify:
```bash
ls /c/Claude/.claude/skills/ | wc -l   # should be 54+
```

Available skills include: `/review`, `/qa`, `/ship`, `/office-hours`, `/plan-ceo-review`, `/investigate`, `/health`, and more.

To refresh skills after a gstack update (git pull on sga):
```bash
bash /c/Claude/.claude/skills/gstack/setup --no-prefix -q
```

---

## Step 4 — Verify everything before starting work

```bash
git remote -v                          # origin should point to Felipe.git
git log --oneline -5                   # confirm you have the latest commits
gh auth status                         # GitHub CLI authenticated
gcloud auth list                       # gcloud authenticated
python -c "import playwright; print('playwright ok')"
python -c "import google.cloud.storage; print('gcs ok')"
```

---

## Active work

### CEO Plan: Resilient On-Demand Web Scraper

**File:** `docs/2026-06-02-resilient-web-scraper-ceo-plan.md`  
**Status:** ACTIVE — implementation complete, needs selector adaptation for real target.

**What it is:**  
A static SPA (GitHub Pages) where the user enters a `search_code` + `target_url`. Submit triggers a GitHub Actions workflow that scrapes a highly unstable target (crashes ~every 5 min), iterates a result list, extracts text, downloads PDFs, stores PDFs to Supabase Storage, and writes checkpoint data to Supabase PostgreSQL.

**Stack:**
- Checkpoint store: Supabase PostgreSQL (`checkpoints` table, RLS enabled)
- PDF storage: Supabase Storage (`pdfs` bucket, private)
- Trigger: local `backend/server.py` → GitHub `workflow_dispatch`
- Scraper: Playwright (headless Chromium) running on GitHub Actions
- Frontend: static SPA in `spa/` (Screen 1: trigger, Screen 2: live results)

**Supabase project:** `xjlpsgchgfxryvhhrklx.supabase.co`

**GitHub secrets (already set):** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET`, `DISPATCH_PAT`

**Infrastructure — all gaps closed:**
All 7 critical gaps from the CEO plan are implemented (0-results discriminator, resume-read safety, re-dispatch cap, named exceptions, SSRF guard, injection guard, batch writes).

**What's next:**
1. Adapt selectors in `scraper/run.py` to the real target site — update `page.fill()`, `wait_for_selector()`, and `query_selector_all()` calls after inspecting target HTML
2. Run backend locally to trigger real jobs:

```bash
set DISPATCH_PAT=<GITHUB_PAT>   # store the real token outside the repo (e.g. a local .env, gitignored)
set GH_REPO=dankobuy-ops/Felipe
set SUPABASE_URL=https://xjlpsgchgfxryvhhrklx.supabase.co
set SUPABASE_SERVICE_KEY=sb_secret_HOehhXtQUca0Fb9cEuM3oQ_6B9M-DK3
python felipe/backend/server.py
```

---

## Pushing changes to GitHub

```bash
git add felipe/
git commit -m "your message"
git push origin main
```

---

## Last Claude Code session

To resume the most recent conversation (context + full history):

```
claude --resume e19c461d-de6e-4147-b6b5-4b0722b19bd8
```

File: `C:\Users\Danko\.claude\projects\C--Claude-felipe\e19c461d-de6e-4147-b6b5-4b0722b19bd8.jsonl`

---

## Session log

| Date | What happened |
|---|---|
| 2026-06-03 | Connected repo to Felipe.git, pulled remote state (CEO plan + README), installed gstack at root level (54 skills), created this handoff file |
| 2026-06-03 | Built full scraper stack: GHA workflow, Playwright scraper, Supabase checkpoint store, Supabase Storage for PDFs, static SPA (Screen 1 + 2), local backend hop. Tested end-to-end — pipeline fires, re-dispatches, and caps correctly. |
| 2026-06-17 | Google Sheets export (5-tab schema: RUTs, Causas, Demandados, Trámites, Documentos), upsert by Caso ID, name parsing fix (Chilean no-comma format), patente dedup, per-row unique Caso ID (/d1 /t1 /x1 suffixes), clear/wipe history buttons, per-job delete button, runtime raised to 50 min / 50 re-dispatches. |
