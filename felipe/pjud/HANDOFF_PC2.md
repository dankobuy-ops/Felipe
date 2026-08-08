# PJUD — second PC handoff: worker B (filtered ebook backfill)

**Written 2026-08-08 for the machine that is NOT running the nationwide sweep.**

Read `HANDOFF_WORKERS.md` first — it holds the architecture, the pacing evidence and every trap.
This file is only what the second PC needs to do its own job without colliding with the first.

---

## 1. The division of labour

| | PC 1 (this repo's main box) | **PC 2 (you)** |
|---|---|---|
| worker | **A** — `worker_a.py` | **B** — `worker_b.py` |
| finds work by | sweeping all 230 tribunales | **asking Neon** which causas are selected and lack an ebook |
| window | 15/07/2026 → today | **01/01/2026 → 28/02/2026** |
| writes | full upsert of everything it scraped | **targeted UPDATE** of the document + header columns only |
| supervision | hourly Scheduled Task, auto-restart | run it by hand until it has proven out |

**Why two machines and not two workers on one:** the WAF limit is a per-IP request **rate**. Two
document workers on ONE IP were measured blocking each other within 1–2 minutes (2026-07-23). Two
machines on two connections is the only honest way to double throughput. ⚠️ **If PC 2 is on the
same connection as PC 1 (same router/WAN IP), you are NOT getting a second IP** — check
<https://ifconfig.me> on both. If they match, run worker B *instead of* A, not alongside.

They never fight over rows either: different date windows, and B only ever UPDATEs.

---

## 2. Setup

```powershell
git clone https://github.com/dankobuy-ops/Felipe.git C:\Claude   # or: git pull
cd C:\Claude\felipe\pjud\scraper
python -m pip install -r requirements.txt
python -m playwright install chromium      # only if Playwright's browsers are missing
```

### ⚠️ Three secret files the repo does NOT contain

They are gitignored deliberately — **this repo is PUBLIC**. Copy them from PC 1 by hand (USB,
private message, password manager — not a commit, not a public paste):

```
felipe/pjud/scraper/pjud_config.json    Neon connection (pg_conn dict) + Drive folder ids
felipe/pjud/scraper/token.json          Google OAuth token  (account: danko.buy)
felipe/pjud/scraper/client_secret.json  Google OAuth client
```

Verify before anything else — this fails loudly and early if a file is missing or stale:

```powershell
python -c "import dbstore,psycopg2; c=psycopg2.connect(**dbstore._conn_kwargs()); print('neon ok')"
python -c "import dbstore; print('drive ok:', bool(dbstore.Store().docs_folder))"
```

`pjud_config.json` carries `pg_conn` as a **dict**, not a URL — so it is
`psycopg2.connect(**dbstore._conn_kwargs())`, never a DSN string.

### Chrome

Use a **different port and profile dir** from PC 1, so nothing is ambiguous if the two are ever
on the same machine:

```powershell
chrome.exe --remote-debugging-port=9350 --user-data-dir=%LOCALAPPDATA%\pjud_wB1 `
           --no-first-run --no-default-browser-check --start-maximized https://www.pjud.cl
```

A **fresh profile dir is fine** — no warm-up ritual is needed. That folklore was disproved on
2026-08-06: the "gate" was the `#no-disponible` AVISO covering the entry button, which the
scripted walk-in now dismisses. Worker B walks in on its own.

---

## 3. Filtering — do this first

Worker B fetches a **selection**, not everything. Unfiltered, Jan+Feb is **3,779 causas ≈ 133 h**
of continuous running, because every ebook still costs one causa open (the document's JWT only
exists inside the modal — there is no cheaper route).

Four ways to say which causas qualify. Pick whichever matches how you do the filtering:

```powershell
# a) the manual checkbox that already exists — set causas.fill = true from AppSheet   [DEFAULT]
python worker_b.py --port 9350 --desde 01/01/2026 --hasta 28/02/2026 --dry

# b) express the filter as SQL
python worker_b.py --port 9350 --select where --where "procedimiento ILIKE '%Obligaci%Dar%'" --dry

# c) filter anywhere you like, hand over a list of causa_ids (one per line)
python worker_b.py --port 9350 --select ids --ids-file seleccion.txt --dry

# d) no filter at all — the full 133 h
python worker_b.py --port 9350 --select all --dry
```

**Always `--dry` first.** It prints the work-list, the tribunal spread and an ETA, and stops
without touching the site.

Marking causas from SQL, if you would rather not use AppSheet:

```sql
UPDATE causas SET fill = true
WHERE f_ingreso BETWEEN date '2026-01-01' AND date '2026-02-28'
  AND ebook = '' AND <your criteria>;
```

The date columns are real DATEs since the 2026-08-07 migration, so ranges and `date_trunc` work.

---

## 4. Running it

```powershell
python worker_b.py --port 9350 --desde 01/01/2026 --hasta 28/02/2026 --limit 5   # first probe
python worker_b.py --port 9350 --desde 01/01/2026 --hasta 28/02/2026             # the real run
```

Start with `--limit 5`. It proves the whole chain — entry, search, causa open, ebook fetch, Drive
upload, Neon update — for the price of five opens, and a mistake found there costs minutes rather
than a day.

**Launch long runs DETACHED**, the same way PC 1 does, or the process is killed roughly half an
hour in (this is what looked like an overnight "stall" on 2026-08-06):

```powershell
Start-Process python -ArgumentList "-u","worker_b.py","--port","9350","--desde","01/01/2026","--hasta","28/02/2026" `
  -WorkingDirectory "C:\Claude\felipe\pjud\scraper" `
  -RedirectStandardOutput "C:\Claude\felipe\pjud\data\worker_b\run.log" `
  -RedirectStandardError  "C:\Claude\felipe\pjud\data\worker_b\run.err" -WindowStyle Hidden
```

Progress is read from the **log file**, never from whether a wrapper is still attached.

It is resumable for free: the work-list is recomputed from Neon each run, and a causa that now
has an ebook is no longer in it. Stop it any time; restart with the same command.

### What healthy looks like

Roughly **one causa every two minutes** — long idle gaps are the pacing, not a hang.

| observed | meaning |
|---|---|
| ~2 min between causa opens | normal |
| >5 min silent | worth a look |
| `SILENT THROTTLE` in the log | it stopped that tribunal deliberately; see below |
| `BLOCKED` then `cooling off` | normal; it re-enters by itself |

---

## 5. What can go wrong

**A block is not a burned profile.** Re-entry clears a tier-2 block in ~18 s and worker B does it
automatically (cool-off 3, 6, 9… minutes — a block is a *rate* verdict). ⚠️ `waf_check.py` still
advises renaming the profile dir; **that advice is stale** and throws away a warm session.

**The silent throttle** is the one with no tell: no rejection page, no challenge iframe, no
support id — just causa modals that never open. Three failures in a row and worker B stops that
tribunal. If it keeps happening, the session is spent: leave it alone for a few hours (a 19-hour
idle profile came back fine on 2026-08-08) or start a fresh profile dir on a new port.

**Tier 3 — a full-page image CAPTCHA** ("What code is in the image?") needs a human. The scripts
detect it, say so, and stop. Do not script an answer to it.

**Never `store.upsert()` a causa from worker B.** upsert writes *every* column from EXCLUDED, so
it would blank `texto_demanda`, `certificado`, `fill` and anything else B has no opinion about.
`store_result()` does a targeted UPDATE for exactly this reason. The same trap nearly wiped
`tribunales.corte` for all 180 rows on 2026-08-07.

**Dates must be `dd/mm/yyyy`.** PowerShell's `Get-Date -Format "dd/MM/yyyy"` returns `08-08-2026`
on an es-CL machine — `/` in a .NET format string means "this culture's date separator". That
malformed window reached the form on 2026-08-08 and a live tribunal was recorded as EMPTY. Worker
B refuses a window that is not `dd/mm/yyyy`, and reads the dates back off the form after typing
them, because typing is not proof they arrived.

---

## 6. Checking the result

```sql
-- how the backfill is going
SELECT to_char(date_trunc('month',f_ingreso),'YYYY-MM') mes,
       count(*) total, count(*) FILTER (WHERE ebook <> '') con_ebook
FROM causas
WHERE f_ingreso >= date '2026-01-01' AND f_ingreso < date '2026-03-01'
GROUP BY 1 ORDER BY 1;
```

A stored URL must be the **direct** form — `https://drive.google.com/uc?export=download&id=…`,
which returns the PDF itself. Drive's `webViewLink` (`/file/d/<id>/view`) is its UI wrapper page
and is NOT what belongs in the column; `gstore.direct_link()` normalises it everywhere.

Spot-check that a link really works, with no auth:

```powershell
curl -sL -o t.pdf "<the url from causas.ebook>" ; (Get-Content t.pdf -First 1) -match '^%PDF'
```

⚠️ **Never judge a document by size or status.** A clicked PDF returns Chrome's viewer wrapper —
~14 KB of HTML with status 200 — which is how three files sat on disk named `*.pdf` for a day
while none of them was a PDF. Check the magic bytes, always.

---

## 7. Ground rules

1. **`--dry` before every real run.** It is free and it has caught a wrong window twice.
2. **Never two document workers on one IP.** Confirm PC 1 and PC 2 have different WAN IPs.
3. **Do not speed up `CAUSA_GAP`.** 60 s of idle blocked at 11 opens; 120 s ran 50+ clean. The
   numbers are in `HANDOFF_WORKERS.md` §4 with the evidence.
4. **Do not commit `pjud_config.json`, `token.json` or `client_secret.json`.** Public repo.
5. **Pull before you start.** PC 1 is actively committing to `main`.
