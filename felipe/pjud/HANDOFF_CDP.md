# PJUD scraper — CDP Handoff (updated 2026-07-20)

**Supersedes the 2026-07-18 version.** Project: **Poder Judicial Virtual** (Oficina
Judicial Virtual, OJV — `oficinajudicialvirtual.pjud.cl`). Goal: collect civil
**"Ejecutivo Obligación de Dar"** causas where a **bank is the plaintiff**, nationwide,
with **full detail + PDF files + GPS**, into a **Neon Postgres** DB (+ PDFs to Google Drive).

The scraper now WORKS end-to-end, is **WAF-safe**, does **files + GPS**, and is
**resumable**. What remains is running the full **Santiago corte for January 2026** across a
few fresh sessions. This doc is everything needed to do that on another PC.

---

## TL;DR — current state (2026-07-20)

- **Approach:** drive a REAL Chrome over CDP (`--remote-debugging-port`), Playwright
  `connect_over_cdp`. `page.click()` = `isTrusted=true` → beats the site's **F5 WAF**
  (which blocks synthetic `isTrusted=false` events). The old in-page bookmarklet is **dead**
  (can't forge trusted events); `felipe/pjud/inpage/*` + `Abrir_PJUD_sin_debug.cmd` are kept
  only as a documented dead end.
- **THE key WAF finding:** the block was **NOT the IP and NOT CDP** — it was the script's
  **`select_option("#fecTribunal", …)`** (a synthetic change event). Proof: on a "burned" IP
  where the script's causa-open hung, the operator could still open causas + download files
  by hand, and a **pure trusted-click open (no select_option/search) loaded in 1.9s**. Two
  fixes, both validated:
  - **`--no-search`**: the operator selects the tribunal + clicks Buscar by hand (trusted);
    the script only *harvests* the displayed results (pure trusted clicks).
  - **`select_tribunal_kbd()`**: change `#fecTribunal` via **trusted keyboard** (focus + arrow
    keys) instead of `select_option` → the script can iterate all 31 tribunals unattended.
- **Files + GPS work** (`--docs`, `--gps`). **Storage wired** to Neon (`ingest_cdp.py`) +
  Drive. **Resumable** (`--resume` + `causas.fill_status`).
- **Still to do:** one clean end-to-end **unattended sweep** of the whole Santiago corte on a
  **fresh session/IP**. Today's dev IP/session got cooked from heavy testing (detail modals
  hang = the throttle symptom), so the last sweep test was a false negative.

---

## Validated so far (live)

- Fresh IP, `--max-causas 20` (metadata): 20 Santiago-1º causas in 5.1 min, no throttle →
  ingested to Neon (causas 3124→3144, 0 dangling FKs).
- Warm IP, `--no-search --docs --gps` (2 causas): clean → **26 PDFs to Drive** + **4 georref
  resolved** → ingested (26 Documentos rows w/ Drive links).
- Trusted keyboard tribunal-switch: 1º→2º, search returned the correct tribunal's 101 rows.
- Neon now holds ~3,144 causas / 63k cuadernos / 14k litigantes / 17k receptor, etc.

---

## The WAF — rules that keep you unblocked

1. **Never `select_option` the tribunal.** That single synthetic change event flags the F5
   session; the next heavy op (detail modal) then hangs. Use `--no-search` (operator selects)
   or the keyboard switch (`select_tribunal_kbd`, already wired into the sweep).
2. **`select_option("#selCuaderno", …)` (cuaderno switch) is TOLERATED** (lighter AJAX) —
   validated. Leave it as-is.
3. **CDP `page.click()` is trusted** — magnifier, Buscar, Siguiente, modal-close, receptor:
   all fine.
4. **Doc downloads via `context.request.get(...dtaDoc=JWT)` are OK** (26 in a row worked, and
   it's how the existing 1,605 Drive PDFs were made). The JWTs expire ~1h, so **download
   during the scrape**, not later. At full-tribunal scale (~700 fetches) this is unproven —
   watch for throttle.
5. **GPS via `geoReferencia(jwt)`** (in-session JS call) is fine. Some geo refs legitimately
   have no lat/lng → `geo_resolved < geo_links` is normal.
6. **Rate/reputation is the real ceiling.** Even trusted CDP throttles after a while
   (symptoms: detail modals stuck on "Cargando", searches return "sin resultados"). When you
   see that: **STOP, start a FRESH session, and prefer a fresh IP.** Pace gently (defaults
   already do). Don't stack runs on one session. `--resume` lets you spread the corte across
   many sessions/days.
7. **Mobile access (this run):** cellular IPs are usually clean (good). If one gets blocked,
   **toggle airplane mode** to grab a new IP, reopen, re-establish. (Mobile IPs can be
   CGNAT/shared, so a fresh session is still the rule.)

---

## Environment (the other PC)

- **Python 3.12** on PATH. **venv** at `%LOCALAPPDATA%\pjud_venv` with **only `playwright`**
  (no `playwright install` — we drive real Chrome, not a bundled browser). `Probar_CDP.cmd`
  creates/repairs it. (Note: `pip install --upgrade pip` inside the venv trips a Windows file
  lock — skip it; just `pip install playwright`.)
- **Google Chrome** at `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- **CDP port 9333**, dedicated profile `%LOCALAPPDATA%\pjud_cdp` (fresh → CAPTCHA once,
  cookies persist).

### Credentials — MUST be copied (they are gitignored; NOT in the repo)
Put these in `felipe\pjud\scraper\` (copy via a private channel — the repo is PUBLIC):
- `pjud_config.json` — holds `pg_conn` (the **Neon** Postgres secret), Drive `folder_id` +
  `documentos_folder_id`, and `start_date`. `dbstore` + `ingest_cdp` read the DB from here.
- `client_secret.json` + `token.json` — Google OAuth (Drive, `drive.file` scope) for uploading
  PDFs. Account **danko.buy@gmail.com**. (These live in the JPL folder `felipe\scraper\` too;
  same account — copying them over works. `gauth.py` looks in `felipe\pjud\scraper\`.)

Sanity check the DB + Drive before a big run:
```
cd felipe\pjud\scraper
%LOCALAPPDATA%\pjud_venv\Scripts\python.exe -c "import gauth,gstore; c=gstore.load_config(); d=gauth.drive_client(gauth.credentials()); print('Drive OK', bool(d)); print('pg_conn?', bool(c.get('pg_conn')))"
```

---

## How to run

### Step 1 — open the CDP Chrome (operator opens it, never the script)
Double-click **`felipe\pjud\Abrir_CDP.cmd`** (opens Chrome on the CDP port only), OR
**`Probar_CDP.cmd`** (also builds the venv). Then, **by hand in that Chrome (all trusted):**
1. Pass the CAPTCHA → **Consulta Causas** → **Búsqueda por Fecha** tab.
2. **Competencia = Civil**, **Corte = C.A. de Santiago**, **Fechas** Desde `01/01/2026`
   Hasta `31/01/2026`; wait for the **Tribunales** list.
3. Do **one manual search** to confirm results actually come back (proves the session is live).

### Step 2 — run the scraper (from `felipe\pjud\scraper\`, using the venv python)
Two modes:

**A) Unattended full-corte sweep (keyboard tribunal-switch):**
```
%LOCALAPPDATA%\pjud_venv\Scripts\python.exe cdp_scrape.py --docs --gps --resume
```
The script keyboard-switches through every `#fecTribunal` option, searches, harvests each
tribunal's bank C-causas with full detail + PDFs→Drive + GPS, and `--resume` skips causas
already scraped. It **won't finish one corte in one session** (throttle) — when it degrades,
stop, `ingest_cdp.py` what you got, then repeat on a fresh session; `--resume` continues.
Recommended first run: add caps to validate — `--max-tribs 3 --max-causas 12`.

**B) Careful single-tribunal harvest (most WAF-safe, operator drives tribunal selection):**
Operator selects ONE tribunal + Buscar by hand, then:
```
%LOCALAPPDATA%\pjud_venv\Scripts\python.exe cdp_scrape.py --no-search --docs --gps --resume
```
Harvests only the displayed tribunal. Repeat per tribunal (operator changes it each time).

**Flags:** `--port 9333` · `--max-tribs N` (0=all) · `--max-causas N` (0=no limit) ·
`--proc "Ejecutivo Obligación de Dar"` (drop causas whose Proc. ≠ this, after opening) ·
`--docs` · `--gps` · `--no-search` · `--resume`. Output: `Downloads\pjud_cdp_<epoch>.json`
(incremental — survives interrupts).

### Step 3 — ingest the JSON into Neon (+ Drive links)
```
%LOCALAPPDATA%\pjud_venv\Scripts\python.exe ingest_cdp.py "%USERPROFILE%\Downloads\pjud_cdp_<epoch>.json"
```
Idempotent UPSERTs into the `pjud_` tables; creates Documentos/Anexos rows from captured Drive
links; marks each causa `fill_status='scraped'` so `--resume` skips it next time.
(`--dry` previews; `--tribunal-map "Name=value"` only needed for old JSONs lacking `tribunalId`
— new scrapes self-contain it.)

---

## Storage — Neon + Drive

- **Neon** `neondb` (PG 18), connection = `pjud_config.json` → `pg_conn` (host/port/user/
  password/dbname, sslmode+channel_binding=require). Tables are **UNPREFIXED** and built by
  `dbstore._ddl()` from `gstore.TABS`: `bancos, tribunales, ruts, causas, litigantes,
  cuadernos, escritos, documentos, anexos, notificaciones_receptor` (+ `sweep_progress`, and
  the `coord.py` worker tables). Child FK column is **`causa_id`** (NOT `causa`). Every table
  also has a `uid` (short base62) + causas has `fill`/`fill_status`.
- **Drive**: PDFs go to the "Documentos" folder (`documentos_folder_id`), names flattened
  `<causa_id>__c<n>__<folio>-<k>-doc.pdf`. `documentos.url` / `anexos.url` store the webViewLink.

### Deterministic IDs (mirror run.py — do NOT regress)
Rols are **per-tribunal** (same rol under many tribunal_ids = distinct cases).
- `tribunal_id` = the OJV `#fecTribunal` option **value** (e.g. 1º Juzgado Civil de Santiago =
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
- **Rol starts with `C`** — kept. `E-` rols are **Exhorto** (inter-court letters), OUT of
  scope; do NOT include them.
- **Procedure**: the true target is "Ejecutivo Obligación de Dar". Pass `--proc "Ejecutivo
  Obligación de Dar"` to drop non-matching causas after opening (header-checked). Verified 1º
  bank C-causas are all this proc.

---

## Known issues / caveats

- **Throttle ceiling** is the main constraint. Metadata-only sustained 20 on a fresh IP;
  docs+GPS make each causa much heavier (~13 PDF fetches), so the per-session ceiling is lower.
  Plan multiple fresh sessions + `--resume`.
- **Slowness**: the results AJAX and detail modals can be slow — `fire_search` polls 45s, the
  modal wait is 30s. On a *cooked* session they hang past that (that's your cue to refresh).
- **GPS**: `geo_resolved < geo_links` is normal (some refs have no coords).
- **Docs**: some historia "doc" forms return non-PDF/empty → skipped (e.g. 14/19 downloaded).
- **1º Juzgado already partially in Neon** (259-C-1565/1525 fully w/ docs; ~20 more metadata-
  only from the earlier run, `fill_status=''` → a docs sweep will re-scrape them to add files).

---

## NEXT STEPS (in order, on the other PC / mobile IP)

1. Copy the 3 cred files into `felipe\pjud\scraper\`; run the Drive+DB sanity check above.
2. Fresh session (mobile IP): `Abrir_CDP.cmd` → operator setup (Santiago, Jan 2026, manual
   search) → **bounded** validation: `cdp_scrape.py --docs --gps --resume --max-tribs 3
   --max-causas 12`. Confirm: multiple tribunals via keyboard-switch, PDFs in Drive, GPS
   resolved, no block. Then `ingest_cdp.py` the JSON; check Neon.
3. If clean, drop the caps and let the **full corte sweep** run: `cdp_scrape.py --docs --gps
   --resume`. When it throttles, ingest, refresh the session/IP, run again (resume continues)
   until the whole Santiago corte for January is covered.
4. Then other cortes / other months (repeat the operator setup with different Corte/Fechas).
5. (Optional) revoke the leaked GitHub PAT embedded in the `origin` remote URL (repo is public).

---

## File map (all under `felipe/pjud/`)

**CDP path (current/active):**
- `scraper/cdp_scrape.py` — the scraper. Connect-only; `--no-search` harvest;
  `select_tribunal_kbd` keyboard sweep; `--docs` (→Drive via `dbstore`), `--gps`, `--resume`;
  incremental JSON; gentle randomized pacing (`P_CAUSA 5-10s / P_PAGE 4-8s / P_TRIB 6-12s /
  P_STEP 0.6-1.6s`).
- `scraper/ingest_cdp.py` — JSON → Neon `pjud_` tables (idempotent upserts, deterministic ids,
  Documentos/Anexos w/ Drive links, marks `fill_status='scraped'`).
- `Abrir_CDP.cmd` — open the CDP Chrome only. `Probar_CDP.cmd` — venv + Chrome + runs scraper.
- `scraper/dbstore.py` (Neon + Drive), `scraper/gauth.py` (Drive OAuth), `scraper/gstore.py`
  (Drive helpers + `TABS` schema), `scraper/pjud_config.json` (gitignored secrets).

**Dead ends / legacy (do NOT invest):**
- `inpage/*` + `Abrir_PJUD_sin_debug.cmd` — in-page bookmarklet (isTrusted wall).
- `scraper/run.py` + `HANDOFF.md` + `schema.sql` + `coord.py` — the older Sheets/daily-sweep
  design; `run.py --fill` CDP-collab is dead for the same isTrusted reason.
