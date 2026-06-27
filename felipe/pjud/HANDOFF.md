# PJUD scraper — Handoff

**Project:** Poder Judicial Virtual (Oficina Judicial Virtual, OJV) — civil causas scraper.

**Status (2026-06-27):** Pivoted to a **daily, nationwide, per-bank civil sweep** → Google
Sheet + Drive. Built, IDs reworked to **plain deterministic codes**, and **verified live on
Arica (all FK joins OK)**. Committed + pushed on branch **`feat/pjud-daily-sweep`**;
**PR #3 open** (https://github.com/dankobuy-ops/Felipe/pull/3), **NOT merged**.
Pick up at **NEXT STEPS** below — continue as if mid-session.

See also memory: [[pjud-google-account]], [[pjud-daily-sweep]].

---

## TL;DR of the current design
- Per bank, sweep **every civil tribunal in Chile** (~230 across 17 Cortes de Apelaciones)
  via *Búsqueda por Rut Persona Jurídica*. Keep causas whose **Rol starts with `C`** AND
  **ingresadas on/after `start_date`** ("from today onwards"). Incremental upsert to the
  Sheet; PDFs to Drive.
- **Banks come from the `Bancos` tab** (the work-list). 13 banks seeded.
- **Daily GitHub Actions workflow** `.github/workflows/pjud.yml`: cron + manual dispatch; a
  setup job reads `Bancos` → matrix; **one parallel job per bank**.
- **No web page** for PJUD (the JPL SPA is a separate, already-migrated project).

## Google account / Sheet / Drive
- Account: **danko.buy@gmail.com** (NOT bcldeals). User-owned **OAuth Desktop client**
  (gcloud ADC + service accounts were both dead-ends — see git history).
- Sheet ID **`1QE07C92oY6h1MKBL4PNkDLxyBXvnQuleCAGSsHOZRyQ`** ("PJUD — Base de datos"),
  inside Drive folder **"Poder Judicial Virtual"** with a **"Documentos"** subfolder for PDFs
  (everything anyone-with-link readable).
- Creds (gitignored; **repo is PUBLIC — never commit**): `client_secret.json`, `token.json`,
  `pjud_config.json` in `felipe/pjud/scraper/`. To work on another PC, copy them via a private
  channel. CI uses secrets `GOOGLE_CLIENT_SECRET` / `GOOGLE_TOKEN_JSON` (already set on the repo;
  `PJUD_*` aliases also accepted). Token is long-lived (consent screen Published to Production).
- `pjud_config.json` holds folder/sheet IDs + **`start_date`** (the go-live anchor for the date
  filter; set on first `--setup`, overridable with `--since`).

## Banks (`Bancos` tab = work-list)
Columns `nombre, rut, dv, razon_social, activo`. A bank is active unless `activo` ∉
{si, sí, yes, true, 1}. 13 seeded (all activo=si):
Banco de Chile `97004000-5`, BCI `97006000-6`, Santander-Chile `97036000-K`,
Scotiabank Chile `97018000-1`, Itaú Chile `97023000-9`, Banco BICE `97080000-K`,
Banco Internacional `97011000-3`, Banco Consorcio `99500410-0`, Banco Falabella `96509660-4`,
Banco Ripley `97947000-2`, BTG Pactual Chile `76362099-9`, Coopeuch `82878900-7`,
BancoEstado `97030000-7`.
(Banco Security `97053000-2` was deliberately DROPPED — absorbed into BICE, Oct 2025.)

## ⚠️ OJV throttles by IP (important for verification)
The OJV **captcha-gates per IP** under repeated guest sessions: the search form silently fails
to render (blank "Consulta Unificada" + a reCAPTCHA frame, no tabs). A **clean IP works**
(confirmed by switching WiFi; GitHub runners are clean). Code mitigations: realistic **UA is
required**; **warm-up search** (the first search after the form loads always returns 0);
**session self-recovery** if `#jurCompetencia` vanishes mid-sweep (`reopen_form`); and
**inter-search pacing** (`PACE_MS`). Production is gentler (each bank job = one runner IP, one
guest session reused across its sweep). **Local end-to-end verification needs a clean network.**

## ID scheme — plain deterministic codes (user-specified, do NOT regress)
Rule from the user: **a column is a key/FK iff its header ends in `id`** (`id`, `causa_id`,
`tribunal_id`, `cuaderno_id`); everything else is plain descriptive text. IDs must be
**deterministic** (13 parallel jobs writing one Sheet can't use sequential/random ids — they'd
collide or duplicate on re-runs), built with a single `-` separator and the cuaderno **number**
(never the long name — the readable name lives only in the `cuaderno`/`Cuaderno` text column).

| Tab | `id` / PK | format | FKs |
|---|---|---|---|
| Tribunales | `id` | OJV tribunal value, e.g. `2` | — |
| Causas | `causa_id` | `<tribunal_id>-<rol>` = `2-C-996-2026` | `tribunal_id`→Tribunales.id |
| Litigantes | `id` | `<causa_id>-<rut>` | `causa_id`→Causas, `rut`→Ruts |
| Cuadernos (trámite rows) | `id` | `<causa_id>-c<n>-<folio>-<k>` = `2-C-996-2026-c1-7-1` | `causa_id`→Causas |
| Documentos | `id` | `<cuadernos.id>-doc` | `cuaderno_id`→**Cuadernos.id** (exact trámite row) |
| Anexos | `id` | `<cuadernos.id>-anexo` | `cuaderno_id`→**Cuadernos.id** |
| Escritos | `id` | `<causa_id>-c<n>-e<i>` | `causa_id`→Causas; `cuaderno`=name text |
| Receptor | `id` | `<causa_id>-r<i>` | `Causa ID`→Causas; `Cuaderno`=name text |

Verified live: every FK resolves to a real PK, 0 dangling. (Docs/anexos point to the exact
trámite row; Receptor/Escritos are cuaderno-level so they FK the causa and keep the cuaderno
name as plain text — there is no standalone cuaderno entity.)

## Current Sheet tabs (`gstore.TABS` — source of truth, `_write_headers` overwrites the Sheet)
```
Bancos:                 nombre, rut, dv, razon_social, activo
Tribunales:             id, corte, tribunal
Ruts:                   rut, tipo, nombre, segundo_nombre, ap_paterno, ap_materno,
                        razon_social, email, telefono, domicilio, updated_at
Causas:                 causa_id, rol, f_ingreso, estado_adm, procedimiento, ubicacion,
                        estado_proc, etapa, tribunal_id, competencia, ebook, updated_at
Notificaciones Receptor:id, Causa ID, Cuaderno, Nombre, Fecha, Estado     (display-style headers)
Litigantes:             id, causa_id, rut, participante, updated_at
Cuadernos:              id, causa_id, cuaderno, folio, etapa, tramite, descripcion_tramite,
                        fecha_tramite, foja, georref
Escritos:               id, causa_id, cuaderno, fecha_ingreso, tipo_escrito, solicitante
Documentos:             id, cuaderno_id, origen, folio, descripcion, url
Anexos:                 id, cuaderno_id, origen, folio, fecha, referencia, url
```
`Store` (gstore.py): incremental **upsert keyed on column A** (read col A → update-in-place or
append) + a 2nd USER_ENTERED pass for `=`-prefixed cells (so `=HYPERLINK` georref evaluates but
DD/MM/YYYY dates stay RAW). `upload_pdf` skips re-upload by flattened filename. `read_tab`,
`_ensure_tabs` (adds missing tabs to an existing Sheet on `--setup`).

## CLI (run from `felipe/pjud/scraper/`)
- `python run.py --setup` — provision/repair (folder, Sheet, Documentos, headers, missing tabs;
  sets `start_date` if unset). Idempotent.
- `python run.py --list-banks` — JSON of active banks for the CI matrix (use the LAST stdout line).
- `python run.py --rut 97004000 --dv 5 --bank "Banco de Chile"` — sweep ONE bank, all cortes.
- omit `--rut` → sweep ALL active banks (local/manual full run).
- flags: `--corte 10` (single corte value), `--since 2026-06-26` (override start_date),
  `--era 2026` (default = current year; range `2024-2026`), `--max-tribunals N`,
  `--max-seconds N`, `--limit N` (per tribunal/bank/era), `--dry-run`, `--skip-docs`, `--headed`.
- Competencia is fixed **Civil = "3"**. 17 cortes are in `CORTES` (values 10,11,15,20,25,30,35,
  40,45,46,50,55,56,60,61,90,91). Tribunales per corte are enumerated **live** (Corte→AJAX).

## Workflow `.github/workflows/pjud.yml`
- `schedule: cron "0 9 * * *"` (≈05:00 Chile) + `workflow_dispatch` (inputs `since`, `corte`).
- Job `banks`: `run.py --list-banks` → `matrix`. Job `scrape` (needs `banks`): fan-out per bank,
  `--max-seconds 6000`, `timeout-minutes 120`, `max-parallel 6`. Creds via the secrets above.

## Verified live (2026-06-27, clean IP)
- Arica sweep for Banco de Chile: C-996 / C-994 / C-976 scraped with header, litigantes,
  receptor, georref `=HYPERLINK`, and PDFs → Drive Documentos.
- `scratchpad/verify_joins.py` style check: **ALL JOINS OK**, 0 dangling FKs.
- Non-issues seen: occasional geo-modal 10s timeouts (caught, falls back to text); one run was
  cut short by a transient DNS/SSL drop (environmental, not code).

## Git / deploy state
- Branch **`feat/pjud-daily-sweep`** committed + pushed; **PR #3** vs `main`, **not merged**.
- The Supabase→Google migration PRs for JPL (#2) and PJUD core (#1) already merged to `main`.
- `.claude/settings.local.json` is **intentionally NOT committed** — it contains a **leaked
  GitHub PAT** (`ghp_…`). User should **revoke** it; keep it out of any commit (public repo).

## NEXT STEPS (in order)
1. **Merge PR #3.** (workflow_dispatch reads its inputs from the workflow on the *default*
   branch, so dispatch only works cleanly once it's on `main`.)
2. **Dispatch `pjud.yml`** restricted to one corte (e.g. `corte=10`, optionally a permissive
   `since`) → watch it run across clean runner IPs for all 13 banks; confirm Sheet + Drive at scale.
3. Then a full unrestricted daily run. Watch for OJV captcha gating *within* a single
   230-tribunal session (self-recovery handles soft blocks; if hard-blocked, increase `PACE_MS`
   or split cortes across jobs).
4. (Optional) Clear the handful of Arica test rows now in the Sheet before go-live — or just let
   the daily upsert + `start_date` filter take over.

## Live site flow & DOM (verified — keep for maintenance)
Site **oficinajudicialvirtual.pjud.cl**, public **guest** access, no login.
```
1. home/index.php → JS entry: page.evaluate("accesoConsultaCausas()") POSTs a guest session,
   then same-tab redirect to indexN.php. (No AVISO-close, no popup.)
2. indexN.php → the consulta form renders via AJAX; WAIT for a[href='#BusJuridica'] (needs a
   realistic UA or you get the blank captcha page). Click that tab.
   #jurCompetencia = "3" (Civil)  →  #corteJur = <corte value>  (repopulates #jurTribunal)
   →  #jurTribunal = <tribunal value>  ;  #rutJur (rut sin dv) , #dvJur , #eraJur (año, required)
   →  click #btnConConsultaJur.   Corte "Todos" = value "0" lists ALL 230 tribunales (but a
   specific tribunal is still required to search — so we iterate per (corte, tribunal)).
3. Results table #dtaTableDetalleJuridica (cols 🔍|Rol|Fecha|Caratulado|Tribunal). AJAX is slow
   (poll tbody tr). Keep Rol starting "C". Each 🔍 = a[onclick="detalleCausaCivil('<JWT>')"].
4. Modal #modalDetalleCivil: header is tab/newline text (ROL/F.Ing/Est.Adm/Proc/Ubicación/
   Estado Proc/Etapa). #selCuaderno <select> — switch by INDEX (option value JWTs regenerate).
   Panes (all in DOM even hidden): #historiaCiv, #litigantesCiv, #escritosCiv.
   - Receptor: header a[onclick="receptorCivil('<JWT>')"] → #modalReceptorCivil (causa-level).
   - Georref: per historia row a[onclick="geoReferencia('<JWT>')"] → #modalGeoReferenciaCivil,
     read hidden input[name=latitud/longitud] → georref cell = =HYPERLINK("maps…","lat, lng").
   - Docs: each Historia Doc/Anexo cell is a <form action="ADIR_xxx/civil/documentos/docuN.php"
     ><input name="dtaDoc" value="<JWT>"> ; download = GET OJV/<action>?dtaDoc=<JWT> via
     context.request (shares cookies) → PDF. ADIR_xxx prefix is per-session, read at runtime.
   - Ebook header form newebookcivil.php returns HTML/0B on a plain GET (server-side generated)
     → left empty; every historia doc is downloaded anyway.
```
Open/unmapped: causa-level "Anexos de la causa" sub-modal `anexoCausaCivil(JWT)` →
`#modalAnexoCausaCivil` (need a causa that has anexos). `era` (#eraJur) semantics are fuzzy
(results sometimes mix years; we search current year and filter by parsed Fecha ≥ start_date).
Results appear capped ~100 rows/query — irrelevant for "from today onwards" (low per-tribunal
volume); revisit pagination only if backfilling.

## Recon tools (re-inspect the live site)
`felipe/pjud/scraper/_recon.py`, `_inspect.py`, `_inspect_modal.py`. Driver-assisted CDP:
launch Chrome `--remote-debugging-port=9222`, connect over `http://127.0.0.1:9222` (not
`localhost`). One-off recon/verify scripts were kept in the session scratchpad (ephemeral).

## JPL side (separate project, paused — FYI)
JPL migration to Google Sheet/Drive is merged to `main`. Patente enrichment was blocked by a
Cloudflare escalation (cooldown). Those are independent of PJUD.
