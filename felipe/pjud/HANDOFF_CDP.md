# PJUD scraper — Handoff (2026‑07‑18): the in‑page bookmarklet is a dead end; **CDP is the way**

**Project:** Poder Judicial Virtual (Oficina Judicial Virtual, OJV) — civil causas scraper.
Goal: collect civil **Ejecutivo Obligación de Dar** causas where a **bank is the plaintiff**,
nationwide, with full detail (header, litigantes, cuadernos/historia, escritos, receptor,
doc links). See also the older design doc `HANDOFF.md` (Sheets/Neon daily‑sweep, `run.py`) and
memory: [[pjud-cdp-beats-waf]], [[pjud-waf]], [[pjud-inpage-human-rules]], [[pjud-storage]].

---

## TL;DR — what we learned this session
1. **The in‑page bookmarklet approach is dead for this WAF.** OJV sits behind an F5 WAF that
   blocks **synthetic events**. Any click made from page JS (`dispatchEvent`, `.click()`) is
   `isTrusted=false`; a real mouse click is `isTrusted=true`. The WAF blocks the bookmarklet
   **at the very first action**, no matter how human the clicks/pacing look. You cannot forge a
   trusted event from page JS — this is a hard wall, not a tuning problem.
2. **CDP works.** Real Chrome launched with `--remote-debugging-port` (NO automation flags),
   driven by Playwright `connect_over_cdp`. `page.click()` then injects input at the browser
   layer → `isTrusted=true`, indistinguishable from a human. **Live‑verified: opened 6 Santiago
   "Ejecutivo Obligación de Dar" bank causas with real clicks, zero block, clean data.**
3. **But CDP still gets rate‑throttled.** Doing ~6 causas fast + three back‑to‑back runs on one
   session degraded it: detail modals hung on "Cargando", then searches returned "sin
   resultados" everywhere. **CDP beats the `isTrusted` check; it does NOT exempt you from rate
   limits.** Pace gently and run once per fresh session (the standing "scrape gently" rule).

**Status:** CDP path proven; `cdp_scrape.py` (full‑fidelity, operator‑driven) built but the
full‑data extraction (litigantes/cuadernos/escritos/receptor) is **NOT yet validated end‑to‑end**
— the session died from over‑use before that run produced a causa. **Pick up at NEXT STEPS.**

---

## The winning design: operator‑driven CDP

The operator does the human/risky parts by hand in a real Chrome; the script only reads and
iterates. This sidesteps the CAPTCHA **and** the corte→tribunal cascade race that plagued the
in‑page version.

**Operator (by hand, in the CDP Chrome):**
1. From **www.pjud.cl** → Oficina Judicial Virtual → **Consulta Causas**, pass entry/CAPTCHA.
2. Open the **Búsqueda por Fecha** tab.
3. Set **Competencia = Civil**, the **Corte**, and the **Fechas** (Desde/Hasta) until the
   **Tribunales** list appears.
4. Do **one manual search** to confirm results actually come back (proves the session is live).

**Script (`cdp_scrape.py`, trusted CDP clicks, gentle pacing):**
- Connects to the running Chrome over CDP; **reads** competencia/corte/dates (never sets them).
- For each `#fecTribunal` option: `select_option` → **click Buscar** → wait for real rows →
  paginate with **click Siguiente** → for each **bank `C‑`causa** on the page, **click its
  magnifier** to open, scrape full detail, **click the X** to close, move on.
- Writes ONE JSON to `Downloads\pjud_cdp_<epoch>.json`, **incrementally** (survives interrupts).

---

## How to run

### Turnkey (recommended): `Probar_CDP.cmd`
Double‑click it. It: ensures `pjud_venv` + Playwright, **launches Chrome on www.pjud.cl** with the
debug port, prints the steps, and **pauses**. You do the operator steps above, press a key, and it
runs `cdp_scrape.py` against that Chrome. JSON lands in Downloads.

### Manual split (what was used to validate)
```
REM 1) launch real Chrome with the debug port
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9333 --user-data-dir="%LOCALAPPDATA%\pjud_cdp" ^
  --no-first-run --no-default-browser-check --start-maximized https://www.pjud.cl

REM 2) do the operator setup in that Chrome, then:
"%LOCALAPPDATA%\pjud_venv\Scripts\python.exe" cdp_scrape.py [--max-causas N] [--max-tribs N] [--proc "Ejecutivo Obligación de Dar"]
```
`cdp_scrape.py` flags (all optional): `--port 9333`, `--max-tribs 0` (0=all), `--max-causas 0`
(0=no limit), `--proc ""` (keep only causas whose Proc. matches, e.g. the ejecutivo filter).
**First validation run: use `--max-causas 5` and watch it — don't unleash a full run until the
full‑data extraction is confirmed and the pacing proves gentle enough.**

---

## Files (all under `felipe/pjud/`)

**CDP path (current/active):**
- `scraper/cdp_scrape.py` — the scraper. **Connect‑only** (attaches to a running CDP port), full
  per‑causa extraction, pagination, incremental JSON, gentle randomized pacing, startup
  modal‑cleanup (recovers from a killed run). Parsers ported from `run.py`. **This is the file to
  build on.**
- `Probar_CDP.cmd` — turnkey launcher (Chrome on www.pjud.cl + venv + runs `cdp_scrape.py`).

**In‑page bookmarklet (DEAD END — kept for the record, do NOT invest further):**
- `inpage/inpage_scrape.js` (v10), `inpage/Bookmarks`, `inpage/bookmarklet_inpage.txt`,
  `inpage/Preferences`, `Abrir_PJUD_sin_debug.cmd`. It evolved through v1→v10 (operator‑driven,
  click‑only, human pacing, human modal‑close) and **still blocked immediately** because of the
  `isTrusted` wall. A generator script (session scratchpad) URL‑encoded `inpage_scrape.js` into
  the `Bookmarks` file (verified byte‑exact via Chrome's `encodeURIComponent`).

**Older design (separate, still valid for its scope):** `scraper/run.py` (Playwright, has its own
CDP `--discover`/`--fill` collab modes + Neon/Drive storage), `scraper/dbstore.py`,
`scraper/gstore.py`, `scraper/coord.py`, `schema.sql`, `HANDOFF.md`.

---

## Environment / setup
- **Python** 3.12 (system, on PATH). **venv** at `%LOCALAPPDATA%\pjud_venv` with the **`playwright`
  package only** (1.61.0) — **no `playwright install`** (we drive real Chrome, not a bundled one).
  (Note: `pip install --upgrade pip` in the venv trips a Windows file lock — skip it; just
  `pip install playwright`.)
- **Chrome** at `C:\Program Files\Google\Chrome\Application\chrome.exe` (Chrome 150).
- **CDP port** 9333, dedicated **profile** `%LOCALAPPDATA%\pjud_cdp` (fresh → CAPTCHA once; cookies
  persist after). No automation/debug fingerprint beyond the debug port itself.
- **Output** `%USERPROFILE%\Downloads\pjud_cdp_<epoch>.json`.
- **Repo is PUBLIC** — never commit `scraper/pjud_config.json`, `client_secret.json`, `token.json`
  (gitignored) or `.claude/settings.local.json` (has a leaked PAT — see old HANDOFF).

## Output JSON shape (per causa)
```
rol, caratulado, fecha, tribunal, tribunalSel, corte, rango,
header:{f_ingreso, estado_adm, procedimiento, ubicacion, estado_proc, etapa},
litigantes:[{participante, rut, persona, nombre}],
cuadernos:[{cuaderno, historia:[{folio, doc:{action,val}|null, anexo:{action,val}|null,
                                 etapa, tramite, desc, fecha, foja, georref}]}],
escritos:[{fecha_ingreso, tipo_escrito, solicitante}],
receptor:[{cuaderno, nombre, fecha, estado}],
n_historia
```
Bank filter = Rol starts `C` AND caratulado contains a bank token (SANTANDER, BANCOESTADO, ITAU,
SCOTIABANK, BCI, BANCO DE CHILE, FALABELLA, COOPEUCH, BICE, CONSORCIO, RIPLEY, BTG, BANCO
INTERNACIONAL). Verified sample (Santiago, Jan 2026): C‑1565/1525/1510/1543/1513/1518‑2026 — all
"Ejecutivo Obligación de Dar", plaintiffs BancoEstado / CMR Falabella / Scotiabank.

## Site / DOM reference (Búsqueda por Fecha) — trusted‑click targets
- `#fecCompetencia`=`3` (Civil), `#corteFec`, `#fecTribunal`, `#fecDesde`, `#fecHasta`,
  `#btnConConsultaFec` (Buscar).
- Results table `#dtaTableDetalleFecha` (cols 🔍|Rol|Fecha|Caratulado|Tribunal). Row magnifier =
  `a[onclick*='detalleCausaCivil']`. Pagination = `#sigId` ("Siguiente"; its `<li>` gets
  `.disabled` on the last page; confirm advance by the first row's onclick changing).
- Detail modal `#modalDetalleCivil`; header text carries ROL/F.Ing/Est.Adm/Proc/Ubicación/Estado
  Proc/Etapa. Cuaderno `<select> #selCuaderno` — **switch by INDEX** (option values are JWTs that
  regenerate). Panes `#historiaCiv`, `#litigantesCiv`, `#escritosCiv`.
- Receptor sub‑modal: header `a[onclick*='receptorCivil']` → `#modalReceptorCivil` (causa‑level).
- Docs: each historia Doc/Anexo cell holds `<form action="…docuN.php"><input name="dtaDoc"
  value="<JWT>">` — captured as `{action,val}` for later download; **not downloaded in‑script**
  (a background fetch is a non‑human network command and risks the WAF).
- Close modals with a **real click** on `.modal-header .close` / `[data-dismiss='modal']` (never
  `jQuery.modal('hide')`, synthetic Escape, or backdrop removal — those are automation tells).

## Known issues / caveats
- **Rate/session is the live risk.** Symptoms of a hot session/IP: detail modals stuck on
  "Cargando", or searches returning "sin resultados" for tribunales you know have causas. When you
  see that: STOP, let it cool, start a **fresh** session (reload → re‑navigate → re‑set form →
  manual search). Don't stack runs.
- **Guest session expiry.** OJV guest sessions are short‑lived; a long run may outlive one. For big
  runs, plan session refreshes or split across sessions/days.
- **CAPTCHA** is manual (operator), once per fresh profile session.
- Georref is captured as **text only** (historia `td[8]`); resolving lat/lng needs opening a geo
  sub‑modal per row — skipped for gentleness.

---

## NEXT STEPS (in order)
1. **Validate full‑data extraction on a FRESH session** (cooled IP): launch Chrome (Probar_CDP.cmd
   or manual), operator sets Santiago + Jan 2026 + does a manual search, then
   `cdp_scrape.py --max-causas 5`. Confirm the JSON has non‑empty `litigantes`, `cuadernos`
   (multiple, with `historia`), `escritos`, `receptor`. Watch for "Cargando"/throttle.
2. **Tune pacing** if needed (constants `P_CAUSA/P_PAGE/P_TRIB/P_STEP` at the top of
   `cdp_scrape.py`; currently 5–10s / 4–8s / 6–12s / 0.6–1.6s). Find the fastest that stays under
   the throttle; err slow.
3. **Scale gradually** — `--max-causas 20`, then a full tribunal, then the corte. If a session
   degrades, that's the ceiling for one session; add a refresh strategy.
4. **Wire output → Neon** (`dbstore.py`): map JSON records to the `pjud_` tables
   (`causa_id = <tribunal_id>-<rol>`, deterministic ids per the old HANDOFF). JSON‑only today.
5. **PDFs → Drive** (deferred): historia rows already carry the doc/anexo `{action, dtaDoc}`.
   Download by clicking the doc form (trusted) or an in‑session request, then upload via `gstore`.
6. **Multi‑corte / nationwide**: repeat the operator flow per corte, or extend the operator step to
   change cortes between passes (the script already reads whatever corte is set).

## Session history (why in‑page failed — so nobody re‑walks it)
Built 7 per‑month launchers, then collapsed to one; made the launcher open Chrome only (no
auto‑nav), on www.google.cl then plain. Fixed real bugs in the bookmarklet: results wait
(wait for rows carrying a `detalleCausaCivil` link, not a loading placeholder), corte→tribunal
cascade race (native `change` event, not jQuery‑only), pagination aligned to `run.py`, human
modal‑close (click the X, no DOM surgery), strict close‑before‑open modal ordering, operator‑set
competencia/corte/dates (script iterates tribunales only), and finally **pure clicks + human
pacing**. It **still blocked at the first action** → confirmed the `isTrusted` wall → pivoted to
CDP, which passed. Lesson recorded in [[pjud-cdp-beats-waf]].
