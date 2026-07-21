# PJUD scraper — CDP Handoff (updated 2026-07-21, evening)

**Supersedes the 2026-07-20 version.** Project: **Poder Judicial Virtual** (Oficina
Judicial Virtual, OJV — `oficinajudicialvirtual.pjud.cl`). Goal: collect civil
**"Ejecutivo Obligación de Dar"** causas where a **bank is the plaintiff**, nationwide,
with **full detail + PDF files + GPS**, into a **Neon Postgres** DB (+ PDFs to Google Drive).

The scraper **works end-to-end** — detail, files, GPS, Neon ingest, resume — and that is no
longer in doubt. What blocks the project is **not correctness, it is the F5 WAF**. As of the
2026-07-21 evening session the model of *what* trips the WAF changed materially — **read the
next section first; it supersedes the older "burn budget = elapsed time" story below.**

---

## ★★★ NEWEST FINDING (2026-07-21 evening) — START HERE ★★★

### The block is the SECOND search of a session, not the burn budget and not our code

Three independent runs today all show the identical shape:

| Run | Search #1 | Search #2 |
|-----|-----------|-----------|
| 16:16 (yesterday's code, **operator**-established form) | trib 259 → **53 rows** ✅ | trib 2 → blocked ❌ |
| Run 1 (script, dates set via JS `.value`+dispatchEvent) | trib 259 → **53 rows** ✅ | trib 2 → **F5 REJECTED** ❌ |
| Run 2 (script, dates **typed**, fresh profile) | *operator's manual search* ✅ | script's 1st search → **F5 REJECTED** ❌ |

Read run 2 carefully: on the **fresh** profile the operator did one manual search by hand
(worked), *then* the script searched — and that script search was the **session's 2nd search**
and was rejected. So the reject lands at the **same ordinal position (search #2)** regardless
of who issues it or how the form was built. Conclusions, in order of confidence:

1. **It is NOT `establish_form_kbd` / the `--corte` keyboard code.** The 16:16 run used the
   operator's hand-built form and hit the wall at exactly the same place. The keyboard-establish
   itself is **VALIDATED** — twice today it built the form and returned a correct **53** for
   trib 259. (This means the `--count-only --corte 90` "sweep never left trib 259" mystery from
   this morning is *solved*: it wasn't the code, it was search #2 getting rejected every time.)
2. **It is NOT the JS-`.value`+`dispatchEvent` on the dates** (my first guess). Run 2 typed the
   dates with trusted keystrokes and still got rejected at search #2. *(That fix was still worth
   keeping — see `type_date_kbd` below — but it is not the cause.)*
3. **It is NOT elapsed time or PDF volume** (the old "burn budget" model). Search #2 is rejected
   seconds into a fresh session with zero detail opens and zero PDF fetches. The earlier
   "survives ~6 causas" number was a *different* regime (detail opens on an already-warm profile);
   the **search-sweep regime dies at the 2nd search**, full stop.
4. **The instant tell:** after a reject, **`#btnConConsultaFec` (Buscar) stays `disabled`
   forever.** From the site's own JS: the button is disabled in `beforeSend` and only
   re-enabled in the AJAX **`success`** handler — which also calls `recaptchacallbackfechav3()`
   to mint a fresh token. A rejected response skips `success`, so the button never re-enables
   and no fresh token is minted. **Stuck-disabled Buscar == WAF block. Detect this, don't wait
   45 s for rows.**

### The prime suspect: reCAPTCHA v3 token, single-use per session-search

The site refreshes the enterprise reCAPTCHA v3 token in two places only: a `setInterval(…,
60000)` (`llamarCaptchaTodos`) and each search's `success` handler. **Hypothesis:** search #1
consumes the token; search #2 fires before the async refresh has landed a *new* token, reusing
a spent one → F5 rejects. A human doing two manual searches is slow enough that the 60 s
interval (or the success-handler refresh from search #1) has already replaced the token; the
script is fast enough to reuse it. **This is the single most important thing to test next.**

### Built to settle it: `scraper/net_probe.py` (read-only network recorder)

Attaches over CDP, **injects nothing**, logs every page request with full POST params — the
`g-recaptcha-response-fecha` token is **fingerprinted** (`<len=1337 03AF…kQ2f>`) so token
**reuse between two searches is visible at a glance** — plus response status + F5-reject flag,
to `scraper/netprobe_<label>_<epoch>.jsonl`. Usage in its docstring.

### The experiment to run next (one fresh profile, ~2 min)

1. Fresh profile + CAPTCHA, reach Consulta Causas. **Do NOT search yet.**
2. `python net_probe.py --label manual` (start it BEFORE any search).
3. Operator does **TWO manual searches by hand** (trib 1 → results → switch trib → Buscar).
   **The key question: does the 2nd MANUAL search return rows, or also get rejected?**
   - If the 2nd manual search **works** → the fault is script-specific (speed/token reuse);
     diff the script's request against `manual` #2 in the JSONL — the differing param is it.
   - If the 2nd manual search is **also rejected** → the session genuinely allows ~1 search;
     the whole "sweep 31 tribunals in one session" plan is dead and we pivot to **1 search per
     profile**, or find how the site itself refreshes the token before allowing search #2.
4. Likely fix if it's token reuse: before each search after the first, **wait for a NEW token**
   — poll `#g-recaptcha-response-fecha` until its value CHANGES from the last one used (or call
   `recaptchacallbackfechav3()` and wait), then click Buscar. Pacing 60 s+ between searches (to
   let `llamarCaptchaTodos` fire) is the crude version.

---

## TL;DR — current state (2026-07-21)

- **Approach:** drive a REAL Chrome over CDP (`--remote-debugging-port`), Playwright
  `connect_over_cdp`. `page.click()` = `isTrusted=true` → beats the site's **F5 WAF**
  (which blocks synthetic `isTrusted=false` events). The in-page bookmarklet is **dead**
  (can't forge trusted events); `felipe/pjud/inpage/*` + `Abrir_PJUD_sin_debug.cmd` are kept
  only as a documented dead end.
- **Everything in the pipeline is validated live:** trusted-click detail opens, `--docs`
  (PDFs → Drive), `--gps` (lat/lng), `--resume`, keyboard tribunal switch, and
  `ingest_cdp.py` → Neon with 0 dangling FKs.
- **⚠️ The blocker (updated 2026-07-21 evening):** for the **search-sweep** regime it is the
  **2nd search of a session** getting F5-rejected — NOT elapsed time, NOT PDF volume, NOT our
  form code. See the "★★★ NEWEST FINDING" section at the very top; it supersedes the "burn
  budget = time" narrative in "The burn budget" section below (kept for the *detail-open*
  regime evidence, which is a separate, warmer-profile phenomenon). Prime suspect: reCAPTCHA
  v3 token reuse. **Do the `net_probe.py` experiment before writing any more scraper code.**
- **The flag follows the PROFILE, not the IP** (validated — rule 8). Resetting the network
  without resetting `%LOCALAPPDATA%\pjud_cdp` does nothing. **A fresh profile = a fresh profile
  DIR** (`%LOCALAPPDATA%\pjud_cdp`), not a new IP and not new cookies.

---

## The burn budget — the 2026-07-20/21 mobile session, in full

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

## ~~⚠️ THE OPEN QUESTION~~ — RESOLVED 2026-07-21: it is TIME, not volume

> **Verdict (07-21 field results, this PC):** the reduced doc set cut fetches ~47 → ~9 per
> causa and the profile **still** burned after ~3 causas in a long session; a search-only
> list sweep burns too. Cause = **elapsed session time / cumulative activity**. Fix =
> **short rotating sessions** (~3-6 causas each, fresh profile dir per session). The doc-set
> reduction is kept — it's cheaper and faster — but it is not the cure.
> The reasoning below is preserved because the *evidence* still matters; the question isn't.

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
2. **`select_option("#selCuaderno", …)` (cuaderno switch) is TOLERATED** (lighter AJAX) —
   validated. Leave it as-is.
3. **CDP `page.click()` is trusted** — magnifier, Buscar, Siguiente, modal-close, receptor:
   all fine.
4. **Doc downloads via `context.request.get(...dtaDoc=JWT)`** are the prime suspect for the
   burn (see above). The JWTs expire ~1h, so **download during the scrape**, not later.
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

## Environment (the other PC) — including the traps

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

1. **Settle the "search #2" question — this gates everything.** Run the `net_probe.py`
   experiment in the "★★★ NEWEST FINDING" section: fresh profile → probe → **two manual
   searches** → does search #2 survive? This tells you whether the sweep is salvageable at all
   and, if so, exactly which request param (almost certainly the reCAPTCHA token) is stale.
2. **If it's token reuse (expected):** in `cdp_scrape.py`, before every search after the first,
   wait for `#g-recaptcha-response-fecha` to CHANGE from the last used value (poll it, or call
   `recaptchacallbackfechav3()` and wait for a new token) before clicking Buscar. Then the
   `--count-only --corte 90` full-31-tribunal sweep should complete in one session.
3. **Count the job**: that sweep, ingesting each tribunal's list with `ingest_cdp.py
   --list-only`, enumerates the whole corte cheaply and makes the DB — not a JSON in Downloads
   — the work queue. (Only trib 259 = 53 is measured; Santiago-Jan ≈ ~1,500 extrapolated.)
4. Then bulk **detail** collection with `--resume --docs` across rotating profiles. NB the
   detail-open regime is a *separate* WAF phenomenon (warmer profile, ~6 causas) — re-measure
   its budget once the search block is understood; don't assume the old "~6 causas" holds.
5. (Optional) migrate `georref` from the `=HYPERLINK` formula to real lat/lng columns.
6. **Revoke the leaked GitHub PAT** — it was stripped from `settings.local.json` before ever
   being pushed, but the token itself is still live on GitHub.
7. **Housekeeping:** 4 burned profile dirs `%LOCALAPPDATA%\pjud_cdp.burned-*` accumulated on
   2026-07-21; safe to delete once a run is green.

---

## File map (all under `felipe/pjud/`)

**CDP path (current/active):**
- `scraper/cdp_scrape.py` — the scraper. Connect-only; `--no-search` harvest;
  `select_tribunal_kbd` keyboard sweep; **`--corte/--desde/--hasta` → `establish_form_kbd`**
  (builds the whole Búsqueda-por-Fecha form with TRUSTED keyboard, no manual search; VALIDATED
  — returns 53 for trib 259) + `form_ok()` auto-recovery for the session-expiry form reset;
  **`type_date_kbd`** (dates set by real keystrokes, never JS `.value`+dispatchEvent — the old
  synthetic-event pattern is gone); `--docs` (→Drive via `dbstore`), `--gps`, `--resume`;
  incremental JSON; gentle randomized pacing (`P_CAUSA 5-10s / P_PAGE 4-8s / P_TRIB 6-12s /
  P_STEP 0.6-1.6s`). **KNOWN LIMIT: search #2 of a session is F5-rejected (see top section).**
- `scraper/ingest_cdp.py` — JSON → Neon (idempotent upserts, deterministic ids, Drive links,
  marks `fill_status='scraped'`). **`--list-only`** ingests a `--count-only` list as causa
  SHELLS (`ON CONFLICT DO NOTHING`, `fill_status` untouched → stays pending work); the normal
  path now REFUSES a headerless JSON (would blank headers + mark 'scraped').
- `scraper/net_probe.py` — **read-only network recorder (NEW 2026-07-21 eve). Injects nothing.**
  Logs every request's POST params (reCAPTCHA token fingerprinted) + F5-reject flag to
  `netprobe_<label>_<epoch>.jsonl`, so a manual search and a script search can be diffed. This
  is the tool for the "search #2" experiment.
- `scraper/waf_check.py` — **read-only WAF/session health check. Run before and after.**
  (TODO: teach it the stuck-disabled-Buscar signature = instant block tell.)
- `Abrir_CDP.cmd` — open the CDP Chrome only. `Probar_CDP.cmd` — venv + Chrome + scraper.
- `scraper/dbstore.py` (Neon + Drive), `scraper/gauth.py` (Drive OAuth), `scraper/gstore.py`
  (Drive helpers + `TABS` schema), `scraper/pjud_config.json` (gitignored secrets).

**Dead ends / legacy (do NOT invest):**
- `inpage/*` + `Abrir_PJUD_sin_debug.cmd` — in-page bookmarklet (isTrusted wall).
- `scraper/run.py` + `HANDOFF.md` + `schema.sql` + `coord.py` — the older Sheets/daily-sweep
  design; `run.py --fill` CDP-collab is dead for the same isTrusted reason.
