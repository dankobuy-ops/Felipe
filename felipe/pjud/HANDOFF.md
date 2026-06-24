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

## Next steps (in order)
1. Write `pjud/schema.sql` (8 `pjud_*` tables + RLS anon-read + Storage bucket) → user runs once in Supabase.
2. Write `pjud/scraper/run.py`: the flow above, Arica/Tribunal-1, C- only; for each causa →
   header → iterate cuadernos → historia rows (+ download docs) → litigantes → escritos → anexos.
   Build to **run locally first**, verify against live, then wire CI.
3. Export-to-sheet (`pjud` Apps Script + exporter) and the SPA `pjud/` UI + button.

## Open items from the JPL side (paused, FYI)
- Patente enrichment: blocked by Cloudflare escalation; on **cooldown** (try patchright later / paid solver). The watcher fixes were committed.
- JPL `kind` column ALTER + Apps Script redeploy for the `CausaXRut/CausaXPatente` tab rename were
  pending the user running them (see prior session).
