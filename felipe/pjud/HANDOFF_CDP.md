# PJUD scraper — CDP Handoff (updated 2026-07-22)

**Supersedes the 2026-07-21 version.** Project: **Poder Judicial Virtual** (Oficina
Judicial Virtual, OJV — `oficinajudicialvirtual.pjud.cl`). Goal: collect civil
**"Ejecutivo Obligación de Dar"** causas where a **bank is the plaintiff**, nationwide,
with **full detail + PDF files + GPS**, into a **Neon Postgres** DB (+ PDFs to Google Drive).

The scraper **works end-to-end** — detail, files, GPS, Neon ingest, resume. On 2026-07-22 the
WAF blocker was **found and fixed**: it was our own `page.click()`. Read the next section
first; it **disproves** most of what the 07-20/07-21 versions of this doc concluded.

---

## ★★★ SOLVED 2026-07-22 — `page.click()` WAS THE BUG. START HERE ★★★

### F5 Shape scores the pointer's MOTION, not the `isTrusted` bit

Playwright's `page.click()` / `locator.click()` produce `isTrusted=true` events — that part of
the old model was right — but they **teleport the pointer** onto the element and fire
down+up with **no approach path and no hover dwell**. F5 Shape's behavioural telemetry scores
exactly that shape and F5 rejects the next request. A human's hand produces an arc.

Measured in ONE healthy session, same button, same POST params, minutes apart:

| pointer | pre-click JS | response |
|---|---|---|
| `page.click()` (teleport) | yes | **250 B F5 rejection page in 0.1 s** |
| human arc + dwell + real press duration | no | **109,234 B of real results** ✅ |
| human arc + dwell + real press duration | **yes** | **109,234 B of real results** ✅ |

Consequences, all validated the same session:

1. **`Runtime.evaluate` over CDP is INNOCENT.** Reading the DOM (`eval_on_selector`, all the
   `parse_*` helpers, `page.evaluate`) does not flag anything. Only the pointer matters. Do
   not waste time rewriting the parsers to avoid JS.
2. **The fix is `human_click()`** in `cdp_scrape.py`: arc with easing + jitter (18–28 steps) →
   hover dwell 140–380 ms → `mouse.down` → 55–130 ms press → `mouse.up`. Every `page.click` in
   the scraper now routes through it (Buscar, Siguiente, causa magnifier, receptor, modal
   close, datepicker). **Never reintroduce a bare `.click()`.**
3. **The 3-tribunal sweep that always died at search #2 now completes**: `--count-only
   --max-tribs 3` → **189 bank C-causas in 1.7 min**, three scripted searches plus pagination,
   zero rejections (54 / 91 / 44 for tribunales 259 / 260 / 261).

### What this DISPROVES (do not rebuild these theories)

- **"The 2nd search of a session is F5-rejected."** FALSE. On 2026-07-22 the operator did
  **3 manual searches, paginated 8 pages / 715 records, and opened 3 causas** in one session
  with zero rejections. The old table of "search #2 blocked" runs was measuring *our teleport
  clicks*, which happened to land at that ordinal position.
- **"The reCAPTCHA v3 token is single-use."** FALSE, and provably so: search #2 **reused the
  token from a pagination request 38 s earlier, byte for byte, and returned rows.** The
  `netprobe_manual_1784735615.jsonl` recording has it. Do **not** build "wait for a new token"
  logic — it was next-step #2 in the old doc and would have been wasted work.
- **"Shape telemetry beacons must be fresh."** FALSE. A successful manual search fired
  **113.8 s** after the last beacon.
- **The old "burn budget"** (elapsed time / PDF volume) was almost certainly the same bug
  wearing a different mask: every magnifier click in the detail regime was a teleport too.
  Re-measure it before believing any number in the section below.

### The instant tell (still true and still useful)

After a reject, **`#btnConConsultaFec` (Buscar) stays `disabled` forever** — the site disables
it in `beforeSend` and only re-enables it in the AJAX `success` handler, which a rejected
response never reaches. Also: judge a search by the **response**, not by the results table —
the table keeps the *previous* search's rows, so a rejected search can look like 100 happy
rows (it did, and it produced a false "OK" verdict on 2026-07-22).

### F5 Shape streams behavioural telemetry to `/TSPD/?type=N` — watch this number

Shape's JS posts a continuous stream of XHRs to `oficinajudicialvirtual.pjud.cl/TSPD/?type=N`
(`type=22` is the high-frequency behaviour channel; same cookie family as `TSPD_101_DID`).
The rate is a direct read-out of "does the site believe a human is here":

| session | duration | TSPD events | rate |
|---|---|---|---|
| 2026-07-22 #1 — 3 manual searches, then mostly idle | 11.7 min | 39 | **3/min** |
| 2026-07-22 #2 — heavy manual work (8 searches, 21 causa opens, 38 doc clicks) | 8.7 min | 605 | **70/min** |
| 2026-07-22 #3 — `cdp_scrape` driving with `human_click` | (live) | — | **~44/min** |

Two things follow. **(a)** `human_click`'s pointer motion generates real telemetry — the script
is no longer silent, which is very likely *why* the search fix works. **(b)** A useful
diagnostic: if the TSPD rate collapses toward zero while the scraper runs, the session is
about to look non-human. Measure it from any `netprobe` JSONL:
`[r for r in recs if r["kind"]=="request" and "/TSPD/" in r["url"]]`.

**⚠️ Bench discipline:** the operator's physical mouse passing over the CDP Chrome window fires
real `mousemove` events into the page and inflates this number, which **contaminates any test
of whether the script alone sustains proof-of-life**. Leave the window visible but park the
cursor elsewhere (do not minimise — a minimised window gets throttled and coordinate clicks
break).

### Out-of-page requests are the remaining suspect

`download_doc()` fetches PDFs through Playwright's `APIRequestContext`
(`context.request.get()`). That shares cookies but is issued **outside the page**: no document
origin/referer chain and **no Shape telemetry at all**. On 2026-07-22 a `--docs --gps` run died
after 3 causas / 29 such fetches, while the operator manually pulled ~38 documents in the same
period with zero rejections. **`--docs-inpage`** (new) fetches the identical URL with an
in-page `fetch()` and returns the bytes base64 — same PDF, but issued by the page. A/B these
two before concluding anything about document volume.

### The tools that settled it

- **`scraper/net_probe.py`** — read-only network recorder; injects nothing. Logs every request
  with POST params (reCAPTCHA tokens fingerprinted `<len=1337 03AF…kQ2f>` so **reuse is visible
  at a glance**) + response status/size + F5-reject flag → `netprobe_<label>_<epoch>.jsonl`.
  Two bugs fixed 07-22: it now **follows every tab** (OJV opens Consulta Causas in a NEW tab
  and discards the old one — pinning to one page made it die exactly when the interesting
  traffic began), and it waits via Playwright rather than `time.sleep()` (**a bare `time.sleep`
  blocks the sync greenlet and NO events are ever dispatched** — it silently captured 0 events).
- **`scraper/search_probe.py`** (new) — fires **one** search per run through the real
  `cdp_scrape` functions with a single variable changed, and judges by the response.
  `--mode click|human|clear|kbd|kbd-slow`, `--bare` (zero `Runtime.evaluate` before the click;
  the button's box comes from the CDP **DOM domain** instead). This is how the table above was
  produced; use it to test any future WAF hypothesis for the price of one search.

---

## TL;DR — current state (2026-07-22)

- **Approach:** drive a REAL Chrome over CDP (`--remote-debugging-port`), Playwright
  `connect_over_cdp`. Trusted events beat the site's **F5 WAF** — but `isTrusted=true` is
  **necessary, not sufficient**: the pointer must also MOVE like a hand (see the top section).
  The in-page bookmarklet is **dead** (can't forge trusted events at all);
  `felipe/pjud/inpage/*` + `Abrir_PJUD_sin_debug.cmd` are kept as a documented dead end.
- **Everything in the pipeline is validated live:** detail opens, `--docs` (PDFs → Drive),
  `--gps` (lat/lng), `--resume`, keyboard tribunal switch, and `ingest_cdp.py` → Neon with
  0 dangling FKs.
- **✅ The blocker is FIXED (2026-07-22): it was our own `page.click()` teleporting the
  pointer.** `human_click()` replaces it everywhere. A 3-tribunal `--count-only` sweep now
  completes clean (189 causas, 1.7 min) where every previous attempt died at search #2.
  The "search #2", "single-use token" and "beacon freshness" theories are all **disproven** —
  see the top section before re-deriving any of them.
- **The flag follows the PROFILE, not the IP** (validated — rule 8). Resetting the network
  without resetting `%LOCALAPPDATA%\pjud_cdp` does nothing. **A fresh profile = a fresh profile
  DIR** (`%LOCALAPPDATA%\pjud_cdp`), not a new IP and not new cookies.
- **Counting is cheap, detail is precious:** a `BLOCKED-DETAIL` profile **still searches and
  paginates**, so `--count-only` enumeration can be run on a burned profile. Spend clean
  profiles on **detail opens**, never on counting.

---

## ⚠️ HISTORICAL — the "burn budget" (2026-07-20/21), now suspect

**Read this as evidence, not as conclusions.** Every run below used teleport `page.click()`,
which we now know is itself the trigger (top section). The "~6 causas then blocked" budget is
therefore almost certainly an artefact of the bug, not a property of the site. **Re-measure
before planning around any number here.** What still stands from this session is rule 8 (the
flag follows the profile, not the IP) and the shape of the block page.

### The 2026-07-20/21 mobile session, in full

The whole session ran on **one mobile connection**, deliberately, so the IP was never a
variable. Two profiles were used.

**Profile A** (carried over from earlier dev work, reused across many past sessions):

| step | result |
|---|---|
| operator setup + manual search | fine — 101 rows |
| scraper's **first** causa open | **REJECTED** — F5 block page, support IDs `8068285243157809776`, `8068285242946234825` |

Zero causas. The block was instant, on a *fresh IP*. That is what proved the flag is
device-scoped, not IP-scoped: **the only thing carried over was the profile.**

**Profile B** (created by renaming A aside; same IP, same code, fresh CAPTCHA):

| run | mode | causas | PDFs | GPS | outcome |
|---|---|---|---|---|---|
| probe | `--no-search --docs --gps --max-causas 3` | 3 | 44 | 5 | clean, 3.3 min, zero warnings |
| sweep | `--docs --gps --resume --max-tribs 3 --max-causas 12` | 3 | 108 | 24 | **blocked** during/after the 3rd |

Per-causa detail from the sweep — note how much heavier these were than the probe's:

```
C-1510-2026  hist=40  rec=15  docs=39  geo=17
C-1513-2026  hist=23  rec=7   docs=22  geo=6
C-1518-2026  hist=49  rec=7   docs=47  geo=1
```

**Profile B total before the block: 6 causas, 152 PDF fetches, roughly 25 min of activity.**

All 6 causas were ingested — nothing was lost to either block, because the JSON is written
incrementally and survives a kill.

### What the block looks like (so you recognise it instantly)

Not a hang. An actual F5 block page rendered **into the detail-modal iframes**:

```
[X] CLOSE  The requested URL was rejected. Please consult with your administrator (2).
Your support ID is: <11224827236444459058>   [Go Back]
```

**The parent page stays perfectly healthy** — tribunal still selected, search still returns
its 101 rows. Only `detalleCausaCivil` is rejected. That asymmetry is the signature; run
`waf_check.py` (below) and it will tell you in one command.

---

## ~~⚠️ THE OPEN QUESTION — volume vs time~~ — BOTH ANSWERS WERE WRONG (2026-07-22)

> **The real answer was neither.** It was `page.click()` teleporting the pointer (top section).
> The 07-21 verdict below ("it is elapsed TIME") was drawn from runs that were all being
> rejected for the pointer, so the correlation with session length was spurious — a longer
> session simply meant more scripted clicks. **The reduced doc set is still worth keeping**
> (cheaper and faster, and Felipe chose that scope), but it was never the cure either.
> Preserved verbatim below only so the evidence trail stays auditable.

**We do not yet know what burns the profile.** The probe and the sweep differ in *two* ways
at once, and the experiment can't separate them:

1. **PDF fetch volume** — 44 fetches survived; the next 108 did not. Rule 4 below always
   flagged doc downloads as the unproven part at scale, and this is consistent with it.
2. **Cumulative session activity / elapsed time** — profile B had already done a full probe
   plus an ingest before the sweep started. Maybe any 25-minute session dies regardless.

These have **opposite fixes**, which is why guessing is expensive:

- If it's **fetch volume** → narrow what we download. 47 PDFs for a single causa is almost
  certainly more than the business needs; filtering to the folios that matter could cut
  fetches by most of that and stretch a profile many times further. **Ask Felipe which
  documents actually matter** — this is a product question, not a technical one, and it may
  make the whole problem disappear.
- If it's **elapsed activity** → shorten sessions and rotate profiles more often; document
  volume is irrelevant and filtering would be wasted work.

### The experiment that settles it (cheap, ~15 min)

On a fresh profile, run **metadata-only** — no `--docs`, no `--gps`:

```
cdp_scrape.py --no-search --resume --max-causas 30
```

- If it sails past 6 causas (the earlier handoff records **20 clean on a fresh IP**, which
  is suggestive but was on an unknown profile age) → **PDF volume is the culprit.** Go
  narrow the doc set.
- If it dies around 6 again → **it's session activity/time.** Forget filtering; redesign
  around short, rotating sessions.

Run `waf_check.py` before and after so the verdict is unambiguous.

### A free measurement you can take on a burned profile

A profile that is `BLOCKED-DETAIL` **still searches and paginates**. The bank filter reads
`caratulado` straight from the results table — no detail modal needed. So you can count the
whole job (bank C-causas per tribunal for the month) on an already-dead profile at zero
cost. **Nobody has done this yet, so the size of the corte is still unknown** — worth doing
before committing to any strategy, because "50 causas" and "2,000 causas" call for very
different designs. Would need a small `--count-only` flag on `cdp_scrape.py`.

---

## The WAF — rules that keep you unblocked

1. **Never `select_option` the tribunal.** That single synthetic change event flags the F5
   session; the next heavy op (detail modal) then hangs. Use `--no-search` (operator selects)
   or the keyboard switch (`select_tribunal_kbd`, already wired into the sweep).
   *(Untested since the 07-22 fix — it may well be innocent too, but there is no reason to
   retest it: the keyboard switch works and costs nothing.)*
2. **`select_option("#selCuaderno", …)` (cuaderno switch) is TOLERATED** (lighter AJAX) —
   validated. Leave it as-is.
3. **⛔ NEVER `page.click()` / `locator.click()` — use `human_click()`.** This is rule #1 in
   practice. Both are `isTrusted=true`, but they teleport the pointer with no approach path
   and no hover dwell, and F5 Shape scores the motion: the request that follows comes back as
   a 250 B rejection page. Validated 2026-07-22 (top section). Applies to **every** target —
   magnifier, Buscar, Siguiente, modal-close, receptor, datepicker.
4. **Doc downloads via `context.request.get(...dtaDoc=JWT)`** were long suspected of causing
   the burn; that suspicion rests on runs that were being rejected for the pointer instead, so
   treat it as unproven. The JWTs expire ~1h, so **download during the scrape**, not later.
5. **GPS via `geoReferencia(jwt)`** (in-session JS call) is fine. Some geo refs legitimately
   have no lat/lng → `n_geo < ` the number of geo links is normal.
6. **Two failure modes, different fixes — don't confuse them:**
   - *Throttle*: detail modals stuck on "Cargando", searches return "sin resultados". No
     block page. A fresh session may be enough.
   - *Device flag*: the F5 rejection page with a support ID, search still working. Only a
     **fresh profile** clears it.
   `waf_check.py` distinguishes them for you.
7. **Mobile access:** cellular IPs are usually clean. If one gets blocked, **toggle airplane
   mode** for a new IP — but see rule 8: that alone is almost never the fix.
8. **⚠️ RESET THE PROFILE, NOT JUST THE IP — the flag follows the device.**
   Validated 2026-07-20 (profile A vs B above, same IP throughout). The jar carries F5
   Shape's **`TSPD_101_DID`** — a *device* id, 224 bytes, set on both
   `oficinajudicialvirtual.pjud.cl` and `www.pjud.cl` — plus a full `TS*` set, all persisted
   across sessions. Renaming the profile dir aside and re-passing the CAPTCHA on the **same**
   IP fixed it immediately. So a "fresh session" means a **fresh profile dir**, not just new
   cookies or a new IP. Keep burned dirs as evidence (~150 MB each).
   *Corollary:* every past "fresh IP didn't help" result is **not** evidence about IPs —
   those runs were all re-using the same burned device id. Don't trust them.

---

## Environment — including the traps

### ⚠️ Which Python? It differs per machine — check before you run
- **Danko PC (`C:\Users\Danko`, the 2026-07-22 session):** there is **no `pjud_venv`**. Use the
  **system** interpreter `C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe` —
  it has playwright + psycopg2 + google-api. Do **not** use `felipe\scraper\.venv`: it has
  playwright and google-api but **no psycopg2**, so it dies at the Neon step.
- **The other PC:** venv at `%LOCALAPPDATA%\pjud_venv` (see below).
- One-liner to pick correctly on any machine:
  `python -c "import playwright,psycopg2,googleapiclient;print('ok')"`

### The other PC
- **Python 3.12** on PATH. **venv** at `%LOCALAPPDATA%\pjud_venv`.
- **⚠️ The venv needs the FULL `scraper/requirements.txt`, not just playwright.** An earlier
  version of this doc said "only playwright" — that is wrong and it fails at runtime:
  `--docs` and `ingest_cdp.py` both import the Google libs, and you get
  `ModuleNotFoundError: No module named 'google'` *after* you've already spent a CAPTCHA.
  ```
  %LOCALAPPDATA%\pjud_venv\Scripts\python.exe -m pip install -r requirements.txt
  ```
  (playwright, psycopg2-binary, requests, google-auth, google-auth-oauthlib,
  google-api-python-client.) Do **not** `pip install --upgrade pip` inside it — Windows file
  lock. No `playwright install` needed: we drive real Chrome, not a bundled browser.
- **⚠️ `felipe/scraper/.venv` is dead on the Usuario PC** — it points at
  `C:\Users\Danko\AppData\Local\Programs\Python\Python312\python.exe`. Don't use it; it is
  the JPL project's venv from the other machine. Everything PJUD goes through `pjud_venv`.
- **⚠️ Git Bash trap:** `$LOCALAPPDATA` expands with **backslashes**, so
  `"$LOCALAPPDATA/pjud_venv/Scripts/python.exe"` silently falls through to the *system*
  Python and you get `can't open file` or missing modules. Use a fully-qualified
  forward-slash path: `C:/Users/<user>/AppData/Local/pjud_venv/Scripts/python.exe`. Also
  `cd` into `felipe/pjud/scraper` explicitly — the scripts resolve config relative to cwd.
- **Google Chrome** at `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- **CDP port 9333**, profile `%LOCALAPPDATA%\pjud_cdp` (fresh → CAPTCHA once, then persists).

### Credentials — MUST be copied (gitignored; NOT in the repo)
Put these in `felipe\pjud\scraper\` (copy via a private channel — **the repo is PUBLIC**):
- `pjud_config.json` — `pg_conn` (the **Neon** secret), Drive `folder_id` +
  `documentos_folder_id`, `start_date`.
- `client_secret.json` + `token.json` — Google OAuth (Drive, `drive.file` scope).
  Account **danko.buy@gmail.com**. (Same files live in `felipe\scraper\`; copying works.)

Sanity check before any run:
```
cd felipe\pjud\scraper
%LOCALAPPDATA%\pjud_venv\Scripts\python.exe -c "import gauth,gstore; c=gstore.load_config(); d=gauth.drive_client(gauth.credentials()); print('Drive OK', bool(d)); print('pg_conn?', bool(c.get('pg_conn')))"
```
Expect `Drive OK True` / `pg_conn? True`.

---

## Diagnostics — `scraper/waf_check.py` (new, 2026-07-21)

Read-only: no clicks, no searches, no downloads, so it never costs reputation.

```
python waf_check.py            # verdict + session state
python waf_check.py --cookies  # also dump the F5 cookie set
```

Verdicts: **HEALTHY** · **BLOCKED-DETAIL** (device flag → new profile) · **THROTTLED**
(rate → maybe just a new session) · **NO-SESSION**. It also prints the F5 support IDs and
confirms whether `TSPD_101_DID` is present.

**Run it before every scrape and immediately after any suspected block.** It is the single
cheapest habit for not wasting profiles.

---

## How to run

### Step 1 — operator opens the CDP Chrome (never the script)
Double-click **`felipe\pjud\Abrir_CDP.cmd`**. Then **by hand in that Chrome (all trusted):**
1. Pass the CAPTCHA → **Consulta Causas** → **Búsqueda por Fecha** tab.
2. **Competencia = Civil**, **Corte = C.A. de Santiago**, Desde `01/01/2026`
   Hasta `31/01/2026`; wait for the **Tribunales** list.
3. Select a tribunal and do **one manual search** — confirm results come back.
4. Run `waf_check.py` → expect **HEALTHY**.

### Step 2 — run the scraper (from `felipe\pjud\scraper\`, venv python)

**A) Careful single-tribunal harvest (most WAF-safe — use this by default now):**
```
python cdp_scrape.py --no-search --docs --gps --resume
```
Operator picks the tribunal + Buscar by hand; the script only harvests what's displayed,
using pure trusted clicks. Repeat per tribunal.

**B) Unattended sweep (keyboard tribunal-switch):**
```
python cdp_scrape.py --docs --gps --resume
```
Keyboard-switches through every `#fecTribunal` option. **The switch itself is validated and
innocent** — the 2026-07-21 block happened while still on the first tribunal — but given the
~6-causa budget this will not get far unattended. Add caps: `--max-tribs 3 --max-causas 12`.

**Flags:** `--port 9333` · `--max-tribs N` (0=all) · `--max-causas N` (0=no limit) ·
`--proc "Ejecutivo Obligación de Dar"` · `--docs` · `--gps` · `--no-search` · `--resume`.
Output: `Downloads\pjud_cdp_<epoch>.json`, **written incrementally — it survives a kill, so
always ingest what you got before resetting anything.**

### Step 3 — ingest into Neon (+ Drive links)
```
python ingest_cdp.py "%USERPROFILE%\Downloads\pjud_cdp_<epoch>.json"        # --dry to preview
python ingest_cdp.py "...\pjud_cdp_<epoch>.json" --list-only                # a --count-only JSON
```
Idempotent UPSERTs; marks each causa `fill_status='scraped'` so `--resume` skips it.

**`--list-only`** (2026-07-21) ingests a `--count-only` list JSON: causa **shells** only
(`causa_id, rol, f_ingreso, tribunal_id, competencia`) via `INSERT ... ON CONFLICT DO
NOTHING`, so existing causas are untouched and new ones land at `fill_status=''` — i.e. the
rols are registered as *pending work* and a later detail scrape still collects them. The
normal path now **refuses** a headerless JSON (it would have blanked the header columns and
marked them `'scraped'`, so `--resume` would skip them forever). `caratulado` is dropped —
`causas` has no such column; the parties arrive with the litigantes.

---

## Storage — Neon + Drive

- **Neon** `neondb` (PG 18), connection from `pjud_config.json` → `pg_conn`. Tables are
  **UNPREFIXED**, built by `dbstore._ddl()`: `bancos, tribunales, ruts, causas, litigantes,
  cuadernos, escritos, documentos, anexos, notificaciones_receptor` (+ `sweep_progress`,
  `coord.py` worker tables).
- **Drive**: PDFs → the "Documentos" folder (`documentos_folder_id`), flattened
  `<causa_id>__c<n>__<folio>-<k>-doc.pdf`; `documentos.url` holds the webViewLink.

### ⚠️ Actual schema (an earlier version of this doc got this wrong)
The old text said "child FK column is `causa_id`" for everything. **Not true for
`documentos`.** Verified against the live DB 2026-07-21:

```
causas     : causa_id (PK), rol, f_ingreso, estado_adm, procedimiento, ubicacion,
             estado_proc, etapa, tribunal_id, competencia, ebook, updated_at,
             fill, fill_status, uid          <-- there is NO `id` column
cuadernos  : id (PK), causa_id (FK), cuaderno, folio, etapa, tramite,
             descripcion_tramite, fecha_tramite, fecha_diligencia, foja, georref, uid
documentos : id (PK), cuaderno_id (FK -> cuadernos.id), origen, folio,
             descripcion, url, uid           <-- joins via CUADERNO, not causa
```
So counting a causa's documents needs the join:
```sql
select c.causa_id, count(*) from documentos d
  join cuadernos c on c.id = d.cuaderno_id
 where c.causa_id = '259-C-1510-2026' group by 1;
```

### ⚠️ JSON field names (bite-sized traps when verifying a run)
- Drive links are in **`doc_url`** / **`anexo_url`** on each historia row — *not* a `url` key.
- **`geo`** holds the raw **JWT** (the unresolved geo link), **not** coordinates.
- **`georref`** holds the resolved result as a **Google-Sheets formula** — a leftover from
  the pre-Neon design, stored verbatim into `cuadernos.georref`:
  `=HYPERLINK("https://maps.google.com/maps?ll=-33.5605048,-70.5835436&z=16","-33.560504, -70.583543")`
  Grepping the JSON for `lat` finds **nothing**; count resolved rows with
  `georref.startswith('=')`, which is exactly what `n_geo` does.
  *Worth cleaning up eventually* — a spreadsheet formula in a Postgres column makes SQL geo
  queries impossible without string parsing. Left as-is for now for consistency with the
  existing rows; would need scraper + ingest + a lat/lng column together.

### Deterministic IDs (mirror run.py — do NOT regress)
Rols are **per-tribunal** (same rol under many tribunal_ids = distinct cases).
- `tribunal_id` = the OJV `#fecTribunal` option **value** (1º Juzgado Civil de Santiago =
  **259**, 2º=260, 3º=261…). `cdp_scrape` records it as `tribunalId`.
- `causa_id` = `<tribunal_id>-<rol>` (e.g. `259-C-1565-2026`)
- litigante `id` = `<causa_id>-<rut>` · cuaderno `id` = `<causa_id>-c<n>-<folio>-<k>` ·
  escrito `id` = `<causa_id>-e<i>` · receptor `id` = `<causa_id>-r<i>` ·
  documento `id` = `<cuaderno.id>-doc` · anexo `id` = `<cuaderno.id>-anexo`.

---

## Scope / filter

- **Bank plaintiff**: `caratulado` contains a bank token (SANTANDER, BANCOESTADO/BANCO DEL
  ESTADO, ITAU, SCOTIABANK, BCI/CREDITO E INVERSIONES, BANCO DE CHILE, FALABELLA, COOPEUCH,
  BICE, CONSORCIO, RIPLEY, BTG, BANCO INTERNACIONAL). List in `cdp_scrape.BANK`.
- **Rol starts with `C`** — kept. `E-` rols are **Exhorto**, OUT of scope.
- **Procedure**: target is "Ejecutivo Obligación de Dar". Pass
  `--proc "Ejecutivo Obligación de Dar"` to drop non-matching causas after opening. All 6
  causas scraped on 2026-07-21 came back with exactly this procedimiento.

---

## Database state as of 2026-07-21 (end of day, after the list ingest)

```
causas                   3177      fill_status:  ''        2165
cuadernos               63323                    skipped    845
litigantes              13866                    done       124
documentos               1757                    error       37
anexos                      0                    scraped      6
notificaciones_receptor 17173
tribunales                168
```

The **6 `scraped`** are the 07-21 session's, all at tribunal 259 (1º Juzgado Civil de
Santiago): `259-C-1510-2026, -C-1513-2026, -C-1518-2026, -C-1525-2026, -C-1543-2026,
-C-1565-2026`. 0 dangling FKs.

`causas` grew 3144 → **3177** because the 53-causa January list for tribunal 259
(`--count-only`) was ingested with the new **`--list-only`** path: **33 rols that existed
nowhere in the DB** are now registered as shells at `fill_status=''`; the other 20 were
already known and were left untouched. So tribunal 259 / January is now **completely
enumerated** in the DB (53/53) and only the *detail* is missing (47 at `''`, 6 `scraped`).

Note `--resume` skips **only** `fill_status='scraped'`, so the rows at `''` (both the new
shells and the ~2.1k metadata-only rows from the old `run.py`) will be scraped for detail —
that is intended, not a bug.

---

## NEXT STEPS (in order)

1. **Re-measure the detail-open budget with `human_click`.** The old "~6 causas then blocked"
   number was measured with teleport clicks and is probably meaningless now. Run
   `--max-tribs 1 --max-causas N --docs --gps --resume` on a fresh profile and push N up until
   something breaks (or nothing does). **This is the number the whole plan depends on.**
2. **Count the job**: `--count-only` across all 31 tribunales, ingesting each list with
   `ingest_cdp.py --list-only`, enumerates the corte and makes the DB — not a JSON in
   Downloads — the work queue. Measured so far: 259=54, 260=91, 261=44 for January
   (**189 in 3 tribunales**, so Santiago-Jan ≈ ~1,500 is a reasonable extrapolation).
   Cheap: **run it on a burned profile**, never on a clean one.
3. Then bulk **detail** collection with `--resume --docs`, sized by whatever step 1 measures.
4. (Optional) migrate `georref` from the `=HYPERLINK` formula to real lat/lng columns.
6. **Revoke the leaked GitHub PAT** — it was stripped from `settings.local.json` before ever
   being pushed, but the token itself is still live on GitHub.
7. **Housekeeping:** 4 burned profile dirs `%LOCALAPPDATA%\pjud_cdp.burned-*` accumulated on
   2026-07-21; safe to delete once a run is green.

---

## File map (all under `felipe/pjud/`)

**CDP path (current/active):**
- `scraper/cdp_scrape.py` — the scraper. Connect-only; **`human_click()` + `_human_pointer()`
  — the WAF fix, used for EVERY click (see the top section; never reintroduce a bare
  `.click()`)**; `--no-search` harvest; `select_tribunal_kbd` keyboard sweep;
  **`--corte/--desde/--hasta` → `establish_form_kbd`** (builds the whole Búsqueda-por-Fecha
  form with TRUSTED keyboard, no manual search; VALIDATED — returns 53 for trib 259) +
  `form_ok()` auto-recovery for the session-expiry form reset; **`type_date_kbd`** (dates set
  by real keystrokes, never JS `.value`+dispatchEvent); `--docs` (→Drive via `dbstore`),
  `--gps`, `--resume`, `--count-only`; incremental JSON; gentle randomized pacing
  (`P_CAUSA 5-10s / P_PAGE 4-8s / P_TRIB 6-12s / P_STEP 0.6-1.6s`).
- `scraper/ingest_cdp.py` — JSON → Neon (idempotent upserts, deterministic ids, Drive links,
  marks `fill_status='scraped'`). **`--list-only`** ingests a `--count-only` list as causa
  SHELLS (`ON CONFLICT DO NOTHING`, `fill_status` untouched → stays pending work); the normal
  path now REFUSES a headerless JSON (would blank headers + mark 'scraped').
- `scraper/net_probe.py` — **read-only network recorder. Injects nothing.** Logs every
  request's POST params (reCAPTCHA token fingerprinted) + F5-reject flag to
  `netprobe_<label>_<epoch>.jsonl`, so a manual search and a script search can be diffed.
  Follows **all tabs**; waits via Playwright (never `time.sleep` — that captures 0 events).
- `scraper/search_probe.py` — **one search per run, one variable changed, verdict from the
  RESPONSE.** `--mode click|human|clear|kbd|kbd-slow`, `--bare`. The cheapest way to test any
  future WAF hypothesis; it is what proved `page.click` was the blocker.
- `scraper/waf_check.py` — **read-only WAF/session health check. Run before and after.**
  (TODO: teach it the stuck-disabled-Buscar signature = instant block tell.)
- `Abrir_CDP.cmd` — open the CDP Chrome only. `Probar_CDP.cmd` — venv + Chrome + scraper.
- `scraper/dbstore.py` (Neon + Drive), `scraper/gauth.py` (Drive OAuth), `scraper/gstore.py`
  (Drive helpers + `TABS` schema), `scraper/pjud_config.json` (gitignored secrets).

**Dead ends / legacy (do NOT invest):**
- `inpage/*` + `Abrir_PJUD_sin_debug.cmd` — in-page bookmarklet (isTrusted wall).
- `scraper/run.py` + `HANDOFF.md` + `schema.sql` + `coord.py` — the older Sheets/daily-sweep
  design; `run.py --fill` CDP-collab is dead for the same isTrusted reason.
