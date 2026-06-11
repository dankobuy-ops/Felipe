---
description: Save and propagate everything — commit local changes, mirror DB to cloud, push to GitHub. Usage:/sgapush <descripción del commit en español>
---

# /sgapush — Save and propagate everything

Commit any local changes, push the new state of the database up to Supabase cloud,
then push the commit to GitHub. This is the "publish my work so the other PC sees it"
workflow.

## Argument: the commit message

The argument string (everything after `/sgapush`) is the commit message. Per the project's
commit convention in CLAUDE.md it MUST be in **Spanish** with format `<tipo>(<scope>): <descripción>`
(e.g. `feat(gestion): ...`, `fix(seed): ...`, `chore(config): ...`, `docs(handoff): ...`).

If no argument is provided, **ask the user for one** before doing anything. If the message
isn't in Spanish or doesn't follow the convention, gently rephrase and confirm before committing.

## What I'll do, in order

Run each step and stop at the first failure. Report what happened either way.

### 1. Show what's about to be committed

```bash
git status --short
git diff --stat HEAD
```

### 2. Stage and commit (if there's anything to commit)

If `git status --short` is empty AND `git log origin/main..HEAD` is empty, there's literally
nothing to do — tell the user and stop. Otherwise:

If working tree has changes:
```bash
git add -A
git commit -m "<arg-message>" -m "Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

If working tree is clean but there are unpushed commits, skip the commit step and continue
with sync + push (the user already committed previously without pushing/syncing).

### 3. Mirror the local DB to cloud — MANDATORY per the DATABASE WORKFLOW rule

```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python scripts/sync_db.py to-cloud
```

This is **always** run, even if the commit looks purely code/docs. It's idempotent (~60s)
and the cost of accidentally skipping it once is the other PC silently diverging. Cheap
insurance.

If the sync fails: the commit is local-only at this point. Tell the user clearly what
state things are in (commit exists locally, cloud unchanged, GitHub unchanged) and let them
decide whether to fix the sync issue and retry, or `git reset --soft HEAD~1` to back out
the commit.

### 4. Push to GitHub

```bash
git push origin main
```

If push is rejected because remote is ahead, **STOP**. Tell the user to `/sgapull` first
and retry. Do NOT force-push.

### 5. Final report

Tell the user:
- **Commit:** `<hash> <message>`
- **Cloud:** synced, X rows mirrored (from the sync output's last line)
- **GitHub:** pushed to `https://github.com/dankobuy-ops/SGA`
- **Local + cloud + GitHub now identical.**

## Notes
- This command is the inverse of `/sgapull` — both halves of the same loop.
- Run it whenever you've done meaningful work and want to checkpoint, or at end of session.
- The `to-cloud` sync step is what makes the multi-PC workflow real: without it, the other
  PC would `/sgapull` after a GitHub push and get the new code but stale data.
