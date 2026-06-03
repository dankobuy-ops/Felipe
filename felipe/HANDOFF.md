# Handoff — Felipe Project

**Last updated:** 2026-06-03  
**Branch:** main  
**Repo:** https://github.com/dankobuy-ops/Felipe.git

---

## What this repo is

`C:\Claude\felipe` is an isolated project workspace synced via GitHub (`dankobuy-ops/Felipe`).
It is NOT part of the SGA or Apps repos — it is its own thing.

The git root is `C:\Claude` (one level up from `felipe\`). The Felipe remote is set as `origin` on that root repo.

---

## Step 0 — Pull the repo on the new PC

If the `C:\Claude` repo already exists locally:
```bash
git remote set-url origin https://dankobuy-ops:<GITHUB_PAT_REDACTED>@github.com/dankobuy-ops/Felipe.git
git pull origin main --allow-unrelated-histories
```

If starting fresh:
```bash
git remote add origin https://dankobuy-ops:<GITHUB_PAT_REDACTED>@github.com/dankobuy-ops/Felipe.git
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
set DISPATCH_PAT=<GITHUB_PAT_REDACTED>
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

## Session log

| Date | What happened |
|---|---|
| 2026-06-03 | Connected repo to Felipe.git, pulled remote state (CEO plan + README), installed gstack at root level (54 skills), created this handoff file |
| 2026-06-03 | Built full scraper stack: GHA workflow, Playwright scraper, Supabase checkpoint store, Supabase Storage for PDFs, static SPA (Screen 1 + 2), local backend hop. Tested end-to-end — pipeline fires, re-dispatches, and caps correctly. |
