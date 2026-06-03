# Handoff — Felipe Project

**Date:** 2026-06-03  
**Branch:** main  
**Repo:** https://github.com/dankobuy-ops/Felipe.git

---

## What this repo is

`C:\Claude\felipe` is an isolated project workspace synced via GitHub (`dankobuy-ops/Felipe`). It is NOT part of the SGA or Apps repos. Its purpose is to work across multiple PCs using GitHub as the bridge.

The git root is `C:\Claude` (one level up from `felipe\`). The Felipe remote is set as `origin` on that root repo.

---

## Git remote setup (do this on a new PC)

```bash
git remote set-url origin https://dankobuy-ops:<GITHUB_PAT_REDACTED>@github.com/dankobuy-ops/Felipe.git
git pull origin main --allow-unrelated-histories
```

If origin doesn't exist yet:
```bash
git remote add origin https://dankobuy-ops:<GITHUB_PAT_REDACTED>@github.com/dankobuy-ops/Felipe.git
git pull origin main --allow-unrelated-histories
```

---

## Gstack setup

Gstack was installed at the root level (`C:\Claude\.claude\skills\`) so it is available in ALL Claude sessions under `C:\Claude\` (felipe, sga, Apps, etc.).

**54 skills installed**, including `/review`, `/qa`, `/ship`, `/office-hours`, `/plan-ceo-review`, etc.

To refresh gstack after a git pull on the sga repo:
```bash
bash /c/Claude/.claude/skills/gstack/setup --no-prefix -q
```

---

## Active work

### CEO Plan: Resilient On-Demand Web Scraper

**File:** `docs/2026-06-02-resilient-web-scraper-ceo-plan.md`  
**Status:** ACTIVE — plan written, implementation not started.

**What it is:**  
A static SPA (hosted on GitHub Pages) where the user enters a `search_code` + `target_url`. Submitting triggers a GitHub Actions workflow that scrapes a highly unstable target (crashes ~every 5 min), iterates a result list, extracts text, downloads PDFs, stores PDFs to Google Cloud Storage (private, signed URLs), and writes data to Google Sheets.

**Core architecture decision:**  
Checkpointed self-healing on GitHub Actions. Google Sheets is the checkpoint store (`jobId + recordId + status`). On crash/timeout the workflow re-dispatches itself and resumes from the first record not marked `done`. Idempotent on `(jobId, recordId)`.

**Security model:**  
SPA never holds the PAT. A thin server-side hop holds the credential and fires `workflow_dispatch`. SPA is owner-gated.

**Critical gaps to close before coding (from the plan):**
1. 0-results vs page-broke discriminator
2. Resume read safety (failed Sheets read must never default to "nothing done")
3. Re-dispatch cap (max N resumes, then mark job `stalled`)
4. No catch-all exceptions around the scrape loop
5. SSRF: validate/allowlist `target_url`
6. Sheets formula injection guard
7. Sheets write-quota: batch checkpoint writes on large jobs

**Next step:** Start implementation. Suggested order:
1. GitHub Actions workflow skeleton with checkpoint logic
2. Scraper script with crash-aware loop
3. Sheets integration (checkpoint read/write)
4. GCS PDF upload + signed URL generation
5. Static SPA (Screen 1 trigger, Screen 2 results)
6. Thin backend hop for PAT-safe `workflow_dispatch`

---

## What was done in this session (2026-06-03)

- Connected `C:\Claude` git repo to `dankobuy-ops/Felipe.git` as `origin`
- Pulled remote state (CEO plan doc + README) into local repo
- Installed gstack at root `C:\Claude\.claude\skills\` (54 skills, available to all projects)
- Created this handoff file

---

## To push changes to GitHub

```bash
git add felipe/
git commit -m "your message"
git push origin main
```
