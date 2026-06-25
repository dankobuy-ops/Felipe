# PJUD scraper — Handoff

**Project:** Second scraper — **Poder Judicial Virtual** (Oficina Judicial Virtual, OJV).
**Status (2026-06-24):** Recon complete, full flow + DOM mapped. Schema agreed.
Nothing scraped yet. Next: write `pjud/schema.sql` + `pjud/scraper/run.py`.
**Repo is in sync** (`origin/main`). Pick up from "Next steps" below.

---

## Where things are
```
felipe/spa/            published web root (GitHub Pages → /Felipe/)
  index.html           home page, 2 buttons (Consulta JPL, Poder Judicial Virtual)
  jpl/                 the JPL scraper SPA (untouched)
  pjud/index.html      PJUD SPA — STUB ("en construcción"), to be built
felipe/scraper/        JPL backend (untouched)
felipe/pjud/           THIS project
  scraper/             backend (to build) + recon tools (_recon.py, _inspect*.py)
  screenshots/         dev screenshots (gitignored, local only)
  README.md, HANDOFF.md
```
Shared infra (same as JPL): one Supabase project `xjlpsgchgfxryvhhrklx`, service key in
`felipe/scraper/.env` (gitignored). GitHub Pages auto-deploys on push to `felipe/spa/**`
— **remember to bump `app.js?v=N` in any SPA html when JS changes** (caching bit us before).

## The spec
Google Sheet (public): https://docs.google.com/spreadsheets/d/1_faiVg0tO6f_uq6U9G4ww5WZIOlMAwhM8KDpi5oBYR4/edit
Tabs = output target AND field spec. Read tabs via CSV export per tab:
`…/gviz/tq?tqx=out:csv&sheet=<TabName>` (add a unique `&cb=x` to dodge the 15-min fetch cache).
The `setting` tab has the flow; the `ID` columns are the primary keys.

## Target & flow (all verified live via CDP)
Site: **oficinajudicialvirtual.pjud.cl** — public **guest** access, **no captcha**, no login.
```
1. home/index.php → an "AVISO" modal pops up → click "Cerrar" → click "Consulta causas"
2. indexN.php → click tab "Búsqueda por Rut Persona Jurídica"
   fields: #rutJur (rut sin dv) , #dvJur (dv) , #eraJur (año)
           #jurCompetencia (Civil = value "3")
           #corteJur (C.A. de Arica = "10")   ← populates after competencia
           #jurTribunal (1º Juzgado de Letras de Arica = "2")  ← populates after corte
   → click "Buscar"
3. Results table (the one containing "Caratulado"): cols [🔍, Rol, Fecha, Caratulado, Tribunal]
   each 🔍 = <a onclick="detalleCausaCivil('<JWT>')"> → opens #modalDetalleCivil (AJAX)
   KEEP ONLY rows whose Rol starts with "C-"
4. Modal #modalDetalleCivil:
   - header text: ROL, F.Ing, Caratulado, Est.Adm, Proc, Ubicación, Estado Proc, Etapa, Tribunal
   - #selCuaderno  <select> options "1 - Principal", "2 - Apremio…" (JWT values);
     changing it AJAX-reloads the Historia → iterate options to get every cuaderno
   - inner tab-panes (all in DOM even when hidden):
       #historiaCiv   cols: Folio, Doc., Anexo, Etapa, Trámite, Desc. Trámite, Fec. Trámite, Foja, Georref.
       #litigantesCiv cols: Participante, Rut, Persona(NATURAL/JURIDICA), Nombre o Razón Social
       #escritosCiv   cols: Doc., Anexo, Fecha de Ingreso, Tipo Escrito, Solicitante
       (#notificacionesCiv, #exhortosCiv exist but are OUT of scope)
```
**Documents:** each Historia Doc cell is a tiny form:
`<form action="ADIR_871/civil/documentos/docuN.php" method="get"><input name="dtaDoc" value="<JWT>"></form>`
(also `docuS.php`). Download = GET `https://oficinajudicialvirtual.pjud.cl/<action>?dtaDoc=<JWT>`
**in the same session (cookies)** → PDF → upload to Supabase Storage, store public URL.
`ADIR_871` is a per-session path prefix — read it from the form action at runtime, don't hardcode.
**Ebook** (header) = a form submit too → download → `pjud_causas.ebook`.
**Anexos**: header "Anexos de la causa" = `anexoCausaCivil('<JWT>')` → sub-modal `#modalAnexoCausaCivil`;
per-row anexos similar. (Need to open one with an anexo to map the sub-modal — minor, do during build.)

## Locked scope (for now)
- Only **Corte de Arica + Tribunal 1** (1º Juzgado de Letras de Arica).
- Only causas whose **ROL starts with `C`** (skip `E-`, etc.).
- **Download documents into Supabase Storage** (bucket e.g. `pjud-docs`), store URL in Documentos/Anexos.
- Test bank: **Banco de Chile RUT 97004000-5**. (Long-term: free RUT entry; for now just banks.)

## Data model → Supabase tables (`pjud_` prefix; same project as JPL)
`ID` column in each tab = the key.
| table (sheet tab) | key | columns / FKs |
|---|---|---|
| `pjud_tribunales` | id (`arica-1`) | corte, tribunal |
| `pjud_ruts` | rut | tipo(persona/empresa), nombre, segundo_nombre, ap_paterno, ap_materno, razon_social, email, telefono, domicilio |
| `pjud_causas` | rol (`C-996-2026`) | f_ingreso, estado_adm, procedimiento, ubicacion, estado_proc, etapa, tribunal→tribunales, competencia, **ebook**(Storage url) |
| `pjud_litigantes` | id=`‹rol›::‹rut›` | causa→causas, rut→ruts, participante (DTE./DDO./AB.DTE/AP.DTE…) |
| `pjud_cuadernos` | id=`‹rol›::‹cuaderno›::‹folio›::‹n›` | causa→causas, cuaderno, folio, etapa, tramite, descripcion_tramite, fecha_tramite, foja, georref  (NOTE: folio repeats within a cuaderno → need the `::n` dedup index) |
| `pjud_escritos` | id | cuaderno→cuadernos, fecha_ingreso, tipo_escrito, solicitante |
| `pjud_documentos` | id | **cuaderno→pjud_cuadernos.id**, origen, folio, descripcion, url(Storage) |
| `pjud_anexos` | id | **cuaderno→pjud_cuadernos.id**, origen, folio, fecha, referencia, url(Storage) |

Ruts from Litigantes: Persona NATURAL→tipo persona (split "NOMBRE… APELLIDO…", name-first order;
strip "(Poder Amplio/Simple)"); JURIDICA→tipo empresa (razon_social = name). OJV has no email/phone/domicilio.

## Reuse the JPL patterns
- Relational layer → export to the Sheet via an Apps Script web app (see `felipe/scraper/export_sheets.py`
  + `sheets_webapp.gs` for the pattern; build a `pjud` equivalent). Causas/etc. mirror JPL's redesign.
- PDFs to Supabase Storage (JPL did this for its `pdfs` bucket — see `felipe/scraper/storage.py`).
- Run in **CI** (GitHub Actions, Playwright) since there's no captcha — like JPL's `scrape.yml`.
- SPA `pjud/` + an "export" button → dispatch a `pjud-export.yml` Action (JPL's export runs in CI; phone-friendly).

## Recon tools (to re-inspect the live site)
Driver-assisted CDP recon (user drives a real Chrome, we inspect):
```
# launch detached Chrome with a debug port (PowerShell Start-Process so it persists):
chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\Users\Danko\.cache\pjud-recon \
           https://oficinajudicialvirtual.pjud.cl/home/index.php
# then inspect the live page:
python pjud/scraper/_inspect.py          # current page: tabs, fields, tables, open modal
python pjud/scraper/_inspect_modal.py    # open modal: cuaderno opts, doc links, tab-panes
```
Connect URL is `http://127.0.0.1:9222` (not `localhost` — IPv6 hiccup).

## Architecture pivot (2026-06-24) — DROP SUPABASE, use Google Sheet + Drive
Decision: PJUD will **not** use Supabase. Data store = an auto-provisioned **Google Sheet**
(8 tabs from the schema); PDFs = a **Google Drive** folder. The SPA reads the Sheet as CSV.
The separate exporter / Apps Script is gone — **`run.py` writes straight to Sheet + Drive.**
`pjud/schema.sql` + the `pjud-docs` bucket are now **unused** (kept in the tree, not deleted).

Approved design details:
- **Write strategy = incremental upsert** by the column-A ID, via the **Sheets API directly from
  Python** (batched) — NOT Apps Script (its 6-min limit would bite; ~40k Cuadernos rows/yr expected).
- **One-time `run.py --setup`**: creates Drive folder **"Poder Judicial Virtual"**, a Google Sheet
  inside it (the DB, 8 tabs + headers from the schema), and a subfolder **"Documentos"** for PDFs.
  Saves the created IDs to a gitignored config. Idempotent — never re-provisions.
- **Auth must live backend-side** (token/ADC), NOT in the browser, so it "never asks again even
  from another phone/browser/account". Scope of work: all Chilean banks, **current year onwards**.
- **Bank list**: a `BANKS` config seeded with Banco de Chile; scraper auto-verifies each RUT by
  checking the returned Caratulado matches the bank name (user supplies bank *names*).
- PDFs → Drive `Documentos`, store `=HYPERLINK()` links in the Sheet; skip re-upload if present.

## ⛔ WHERE WE LEFT OFF — auth blocker (pick up here)
Chose the "zero-console" path: install gcloud + `gcloud auth application-default login`. **Done so
far**: gcloud SDK installed (winget `Google.CloudSDK`, at
`%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd`); Python libs installed
(`google-auth`, `google-auth-oauthlib`, `google-api-python-client`); `pjud/scraper/gauth.py` written
(loads ADC, builds Drive/Sheets clients). **BLOCKER**: gcloud ADC login **does not work for our
scopes** —
  - it forces `cloud-platform` into the scope list, and
  - Google now **blocks the `spreadsheets` scope for gcloud's default client ID** ("will be blocked
    soon… you must provide your own client ID or use service account impersonation").
The browser opened but the login is effectively dead-ended for Sheets. **gcloud ADC is NOT viable.**

### Next step (decided direction): bring our own OAuth client
Switch to a **user-owned OAuth Desktop client** (the ~5-min Google Cloud Console path we deferred):
  1. console.cloud.google.com → new project → enable **Google Drive API** + **Google Sheets API**.
  2. OAuth consent screen: **External**, add `bcldeals@gmail.com` as a test user (or **Publish** so
     the refresh token doesn't expire after 7 days).
  3. Credentials → Create **OAuth client ID → Desktop app** → download `client_secret.json` into
     `pjud/scraper/` (gitignored).
  4. `run.py --setup` runs `InstalledAppFlow.run_local_server()` with scopes `drive.file` +
     `spreadsheets` → opens the *real* default browser → user consents → save refresh token to
     `pjud/scraper/token.json` (gitignored; for CI it becomes a GitHub secret).
  (Alt considered: service-account impersonation — heavier; skip for personal Gmail.)
Note: a Playwright/CDP-driven Chromium can't be used for Google login (Google blocks automated
browsers). Must open the user's real browser.

### Still TODO after auth (in order)
1. `run.py --setup` provisioner (folder + Sheet + Documentos; save config).  [task #5]
2. Swap `run.py` write layer Supabase → Sheets+Drive incremental upsert.     [task #6]
3. Bank list config + RUT auto-verify.                                        [task #7]
4. SPA `felipe/spa/pjud/` reads the Sheet CSV + an Export/run button.         [task #3]

## Build log — verified live 2026-06-24 (corrections to the recon spec)
- **Entry is JS, not a click**: the home "Consulta causas" `<button>` calls
  `accesoConsultaCausas()` which `$.post`s `includes/sesion-invitado.php` (guest session) then
  **same-tab** `location.href = indexN.php`. run.py calls the function and waits for `indexN.php`.
  No AVISO-close needed. No popup/new tab.
- **Search form (indexN.php), Rut-Jurídica tab `#BusJuridica`**: `#rutJur` `#dvJur` `#eraJur`
  (**año is required** — one search per year; `--era 2024` or range `--era 2018-2026`),
  `#jurCompetencia`=**3** Civil → `#corteJur`=**10** Arica → `#jurTribunal`=**2** (1º Letras Arica),
  Buscar = **`#btnConConsultaJur`**. The reCAPTCHA iframe is the invisible badge — non-blocking.
- **Results table = `#dtaTableDetalleJuridica`** (cols 🔍|Rol|Fecha|Caratulado|Tribunal); AJAX takes
  >5 s so wait on `tbody tr`. Banco de Chile ≈ 65 rows/yr, ~49 are C-.
- **Modal `#modalDetalleCivil`** header is tab/newline-delimited (`ROL: … F. Ing.: … Est. Adm.: …
  Proc.: … Ubicación: … Estado Proc.: … Etapa: … Tribunal: …`) — parsed by label regex.
- **Cuaderno switch by INDEX, not value**: `#selCuaderno` option `value` JWTs regenerate per AJAX
  load, so `select_option(value=…)` fails — use `select_option(index=i)`.
- **Docs**: each Historia Doc cell `<form action="ADIR_871/civil/documentos/docuS.php"><input
  name="dtaDoc" value="JWT">`; GET `OJV/<action>?dtaDoc=JWT` via `context.request` (shares cookies)
  → real PDFs. `--skip-docs` for fast metadata-only runs (one causa ≈ 74 PDFs).
- **TODO still open**: (a) **ebook** header form `newebookcivil.php?dtaEbook=` returns HTML/0B on a
  plain GET — generated server-side on form submit; left empty (every doc is downloaded anyway).
  (b) causa-level **"Anexos de la causa"** sub-modal `anexoCausaCivil(JWT)` → `#modalAnexoCausaCivil`
  not yet mapped (need a causa that has anexos). (c) escritos parser unverified (test causa had 0).

## Open items from the JPL side (paused, FYI)
- Patente enrichment: blocked by Cloudflare escalation; on **cooldown** (try patchright later / paid solver). The watcher fixes were committed.
- JPL `kind` column ALTER + Apps Script redeploy for the `CausaXRut/CausaXPatente` tab rename were
  pending the user running them (see prior session).
