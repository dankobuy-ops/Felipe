---
description: Catch this machine up — pull latest code from GitHub and latest DB state from Supabase cloud
---

# /sgapull — Catch up this PC

Bring this machine fully in sync with the team's latest state, both code and data.
Code comes from GitHub; data comes from the Supabase cloud DB.

## What I'll do, in order

Run each step and stop at the first failure. Report what happened either way.

### 1. Refuse to clobber uncommitted local changes

```bash
git status --short
```

If there are any modified, staged, or untracked-but-tracked files, **STOP**. Tell the user
which files have uncommitted changes and recommend either `/sgapush <mensaje>` to save them
first or `git stash` to set them aside. Do NOT proceed past this step.

### 2. Pull code from GitHub

Capture the HEAD before pulling so I can show what came in.

```bash
git rev-parse HEAD
git pull origin main
```

If pull is up to date, note that. If it brought new commits, run `git log <old>..HEAD --oneline`
and report the list.

### 3. Pull the database from cloud → local

```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python scripts/sync_db.py from-cloud
```

This replaces the local DB entirely with cloud's current state. Takes ~60s for ~11k rows.

### 4. Final report

Tell the user:
- **Git HEAD** (current oneline)
- **Alembic head** (query `alembic_version` on local)
- **Row count summary** for a few key tables (`datos.rut`, `gestion.poliza`, `gestion.cuota`)
  to confirm local now matches cloud
- A single line: "Ready to work."

## Notes
- This is the natural first command to run when starting work on a new PC, or when starting
  a new session after work was done on the other PC.
- It is **destructive** to local DB state (rows that exist only locally are lost). That's
  the point — cloud is the source of truth between PCs.
- It is **non-destructive** to git working tree (we refused if there were uncommitted changes
  in step 1).
