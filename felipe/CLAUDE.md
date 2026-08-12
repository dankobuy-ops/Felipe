# felipe — working rules

## ⚠️ Where things go

**Sessions are launched from `C:\Claude\felipe`, and everything belongs here.** New files, docs
and notes go under `felipe/`, never at the repo root and never in a sibling project.

The git repository root is one level up at `C:\Claude`, so `git status` will show unrelated
modifications from other projects (`sga/`, `cias/`, `Apps/`). That is normal and **none of it is
yours to commit** — always stage explicit paths, never `git add -A` or `git commit -a`.

**One deliberate exception:** `../SCRAPERS_HANDBOOK.md` lives at the repo root, because it is
drawn from four scrapers and one of them is `cias/HDI-Ruts-Scraper/`. Leave it there; do not
"tidy" it into `felipe/`.

This project is **scrapers**. Before building or substantially changing one, read
**[`SCRAPERS_HANDBOOK.md`](../SCRAPERS_HANDBOOK.md)**.

## The one rule

> **A scraper must not do anything a human could not do, or would not do.**

When a scraper gets blocked, the first question is *"what am I doing that a person wouldn't?"* —
not *"how do I evade this?"*. Every time that question was asked properly here it produced a fix
that made the scraper **faster**, not slower. Reaching for gentler pacing instead hides the real
tell and costs throughput permanently.

## Keeping the handbook current

**The handbook is a living file. Update it in the same commit as the fix that taught you
something.** If a lesson is worth a ⚠️ comment in the code, it is worth a line in the handbook.

- Date every claim — `(PJUD, 2026-08-12)` is the minimum.
- When a measurement overturns an entry, **strike the old one and say what replaced it**; do not
  delete it. Seeing a conclusion get overturned is half the value.
- Record negative results and disproved theories, or they get rebuilt.
- Mark speculation as speculation. Several entries rest on a single trial and say so.

## Per-project docs

Project-specific detail stays with the project (`felipe/pjud/HANDOFF_WORKERS.md` and friends);
the handbook holds only what **generalises to the next scraper**. Do not duplicate — cross-link.

## House rules learned the hard way

- **Long runs are launched detached** and judged by whether their **log file advances**, never by
  whether a wrapper is still attached. A harness background task is killed after ~30 minutes.
- **Never commit secrets.** `pjud_config.json`, `token.json`, `client_secret.json` are gitignored
  and this repo is **public**.
- **Stage explicit paths when committing.** The tree usually carries unrelated modifications from
  other sessions; never `git add -A`.
