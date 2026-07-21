# HANDOFF — pdf-extractor / "Buskin" (patentes desde demandas JPL)

- **Session ID:** `11c14125-1c5a-47aa-a7c2-aa84f5d86e34`
- **Date:** 2026-07-21
- **Author:** Claude Code (Opus 4.8)
- **Status:** ✅ Full backfill complete — 466 gap-cases processed, 666 plates written, sheet verified clean.
- **Repo:** `dankobuy-ops/Felipe` (branch `main`). Project dir: `C:\Claude\pdf-extractor`.

---

## 1. What this is

A tool that reads Chilean **Juzgado de Policía Local (JPL)** *demanda* PDFs and extracts the
vehicle **patente** (license plate), then joins the other requested fields from the existing
JPL scraper's data. Built for the Lo Barnechea "cobro de peaje" (toll-collection) lawsuits.

Requested output columns: **`Patente | RUT demandado | Rol causa | Tribunal`**.

**Key architectural insight (drove the whole design):** the JPL scraper
(`C:\Claude\felipe\scraper`) already stores **Rol, Tribunal (juzgado), and the demandado's RUT**
in its Google Sheet. The one field it usually *can't* get is the **patente**, because it's only
written inside the scanned demanda image. So this tool extracts **only the patente** and
**joins** the other three columns from data that already exists — it does not re-OCR them.

---

## 2. TL;DR — final results

- **466** Lo Barnechea causas had no plate yet (of 1,534 total; 1,068 already had one from the web scrape).
- **333 resolved with a plate → 666 plates** (660 distinct) written to the output sheet.
- **133 empty:** 65 `none-text` (digital docs that are old-format-only or resolución-only), 66 unreadable scans (`none-ocr`/`cap`), 2 misc.
- **Verified: no false positives** (no plate appears in >2 cases).
- Output sheet (danko.buy): **Patentes extraídas — JPL (demandas)**, id `1tHMJS5UlUkatLvK8KU9veHNZRUMpM33QLidc8ITkH0k`.

---

## 3. Data flow

```
Google Drive "Documentos" folder (danko.buy)         Scraper Google Sheet (danko.buy)
  lobarnechea__<rol>__docN.pdf  (15,305 files)          Causas / CausaXRut / CausaXPatente / Ruts
                 │                                                     │
                 │  (only doc0 per case)                               │  (join by rol)
                 ▼                                                     ▼
      buskin.py: hybrid text-layer / OCR  ──────►  Patente + [Rol, Tribunal, RUT demandado]
                 │                                                     │
                 └──────────────► Output sheet "Patentes extraídas — JPL (demandas)"
```

- **Join key:** the PDF filename encodes the rol — `lobarnechea__1096__doc0.pdf` → juzgado
  `lobarnechea`, rol `1096`, caso_id `lobarnechea/1096` → matches the scraper's `Causas`/`CausaXRut`.
- **Target selection:** only causas whose caso_id is **not** already in the scraper's `CausaXPatente`.

---

## 4. Chilean plate format rules

- **Old (pre-2008):** 2 letters + 4 digits (e.g. `ZP1185`). **Excluded** — the user wants 2008+ only.
- **New (2008+):** 4 letters + 2 digits (e.g. `KGDD66`). The 4 letters are **consonants only**
  (no vowels A/E/I/O/U) — this is a strong filter that kills most OCR noise.
- Regex used: `[BCDFGHJKLMNPQRSTVWXYZ]{4}\d{2}` (see `patente.py`).
- A single defendant can have **many** plates (a fleet — saw up to 10 on one demanda).

---

## 5. Findings — document reality

### 5.1 The corpus is MIXED (this matters most)
- The original 5 sample PDFs were **100% scanned images** (0 selectable text) → pure OCR.
- But the wider Drive corpus is **mixed**: newer cases are **digital PDFs with a real text
  layer** (read instantly & exactly via `page.get_text()`); older cases are **scanned images**
  (need OCR). Buskin is **hybrid**: text layer first, OCR only true scans.

### 5.2 The plate always lives in `doc0`
- Never in the attachment docs (doc1..docN). So Buskin reads **only doc0**.
- On a **template-specific page**:
  - **page 0** — old Procobro / Autopista Central: *"…vehículo(s) placa patente N° KGDD66 las referidas autopistas."*
  - **page 4** — newer Costanera Norte / ACOFK: *"…placa(s) patente(s) única(s) es (son): STHC91-HPZF12-JJZV47."*
  - **page 15** — long "bundle" docs (cover + mandato judicial + demanda + attachments), e.g. rol 277 (62 pages).
- Buskin probes pages **[0, 4, 15]** first, then the rest, and stops at the first plate-bearing page.

### 5.3 The scraper's `Documentos` sheet tab is USELESS for locating the plate
- Its `descripcion` is just `ProcesoNNNNN` (no "demanda"/"boleta" label) and it's incomplete
  (3 of 5 samples showed 0 rows there). Use the **Drive filenames**, not that tab.

### 5.4 OCR quirks that shaped the parser (`patente.py`)
- OCR reads **"placa" → "piaca"** and **"N°" → "N�" / "Ne"** → do NOT anchor on "placa"/"N°".
  Anchor on the word **"patente"** (reads cleanly) OR use the text layer.
- Plates come **glued** to each other and to the next word: `KGDD66lasreferidas`,
  `ZP1185RPRW87 PJCL63las`. Solved by scanning for the fixed 6-char consonant+digit shape.
- **OCR sometimes drops the whole plate line** on scanned pages (a detector failure, not
  resolution) — this is why the **text layer** is preferred whenever present.
- OCR **case errors** ("BcxY81") — uppercase before matching.

### 5.5 Scan yield is low
- Digital docs: ~instant and ~exact. Scanned docs: cost ~20s each (download-dominated) and
  only ~30–40% yield a plate — OCR often can't read the plate line. The 66 empty scans are
  genuinely hard (flagged `none-ocr`/`cap` for manual review).

---

## 6. ⚠️ The `LDFL85` false-positive (bug found & fixed mid-run)

- **Symptom:** 29 unrelated cases all extracted the same plate `LDFL85`.
- **Root cause:** a page-wide OCR fallback (added to recover plates when OCR mangles "patente")
  mined the **legal citation** *"artículos 75 del DFL 850 de 1.997"* → OCR `…delDFL850…` →
  the substring `LDFL85` (from "de**l DFL 85**0") matches the plate shape.
- **Fix (in `patente.py` + `buskin.py`):**
  1. **OCR'd pages use `plates_after_anchor` ONLY** — no page-wide fallback on noisy OCR text.
     The page-wide fallback runs **only on clean text-layer pages**.
  2. A **`_CITATION` guard** (`DFL|DECRETO|LEY|ARTÍCULO|DS|MOP`) drops any candidate token that
     sits inside a legal citation.
- **Purge:** the reconcile push only *appends*, so removing bad rows required **clearing +
  rewriting** the sheet from the corrected checkpoint. All 29 removed; re-verified.
- **Sanity check to run after ANY future run:** *no plate should appear in >2 rols.* (Exactly
  2 is fine — same vehicle sued twice, e.g. `GJDF75`.)

---

## 7. Files

| File | Purpose |
|---|---|
| `buskin.py` | **Main app.** Reads doc0 from Drive, hybrid text/OCR, joins, upserts to the sheet. Resumable. |
| `patente.py` | Plate parser + tests (`python patente.py`). `plates_after_anchor` (precise), `plates_in_text` (anchor + guarded page-wide fallback for CLEAN text only). |
| `sheet.py` | Output-sheet writer (creates/reuses the sheet, idempotent upsert keyed on (Patente, Rol)). Auth = scraper's token (danko.buy). |
| `run_extract.py` | Local-folder pipeline (OCR a folder of PDFs on disk → CSV). Pre-Drive/Buskin path. |
| `extract.py` | OCR of a local PDF/folder (used by run_extract). |
| `Patentes_PDF.cmd` | Double-click launcher for the local-folder flow. |
| `README.md` | User-facing usage. |

---

## 8. How to run

```bat
cd C:\Claude\pdf-extractor

python buskin.py                 :: process all remaining gap-cases (resumable; skips done)
python buskin.py --max 25        :: bounded batch (use in FOREGROUND; see lessons below)
python buskin.py --rols 1096,277 :: force specific rols (testing / re-attempt)
python buskin.py --dry-run ...   :: OCR + print, do not write the sheet
```

Env knobs: `BUSKIN_PAGE_CAP` (max scanned pages OCR'd per case, default **4**; plate is on [0,4,15]).

Local-folder flow (no Drive): `python run_extract.py "C:\folder\of\pdfs"`  → `out\patentes_extraidas.csv`.

---

## 9. Config & state files (git-ignored — local only)

| File | Contents |
|---|---|
| `buskin_checkpoint.json` | `{rol: {status, plates, pages}}`. Drives resume + reconcile. Statuses: `ok-text`, `ok-ocr`, `ok`, `none-text`, `none-ocr`, `cap`, `no-docs`, `err`. |
| `drive_index.json` | Cached `rol -> [[docN, fileId], …]` for all 15k Drive PDFs. **Delete to force a re-index** (e.g. after new scrapes). |
| `pdf_config.json` | `{spreadsheet_id}` of the output sheet. |
| `samples/`, `out/`, `inbox/` | Local PDFs / CSV output. **Contain personal legal data — never committed.** |

---

## 10. Google accounts (easy to trip on)

- **danko.buy@gmail.com** — the account the **scraper AND Buskin** authenticate as (via
  `felipe/scraper/token.json`). Owns the scraper Sheet, the Drive Documentos folder, and the
  output sheet. This is where everything reads/writes.
- **danko.brzovic@segurosaegis.cl** — the account wired into **Claude's Google (MCP)
  integration**. A *different* account; cannot be chosen from the tool side. A first sheet was
  mistakenly created here ("Extracción Demandas — Patentes (Lo Barnechea)",
  id `1SuEMdUlsH0DxmACxgIsT-bGECsIK7mi2-gVjDVrbctA`) — **unused, can be deleted.**

---

## 11. Key IDs

- Output sheet (in use): `1tHMJS5UlUkatLvK8KU9veHNZRUMpM33QLidc8ITkH0k` (danko.buy).
- Scraper JPL sheet: `1SqP0w1XjvMGoEpBnbXI16EuneJMhrrSJq3hvvw_Azuo` (from `felipe/scraper/jpl_config.json`).
- Drive "Documentos" folder: `1oPN9ww8zK97wy5l04WE7eHLBZveYjPm2`.
- Unused brzovic sheet: `1SuEMdUlsH0DxmACxgIsT-bGECsIK7mi2-gVjDVrbctA`.

---

## 12. Final numbers (2026-07-21)

| Bucket | Count | Notes |
|---|---:|---|
| Gap cases (no plate yet) | 466 | of 1,534 lobarnechea causas |
| ✅ Resolved with plate | **333** | **666 plates**, 660 distinct |
|   — via text layer (`ok-text`) | 221 | instant, exact |
|   — via OCR (`ok-ocr`) | 67 | scanned, anchor-based |
|   — earlier local run (`ok`) | 45 | includes the 5 original samples |
| ⚪ Empty — `none-text` | 65 | old-format-only OR resolución-only (no demanda) |
| ⚪ Empty — `none-ocr` + `cap` | 66 | scans OCR couldn't read → **manual review** |
| ⚪ Empty — `none` | 2 | misc |

---

## 13. Operational lessons (running a ~466-case batch here)

- **Background tasks get KILLED** (runner time limit, inconsistent). Reliable approach:
  **FOREGROUND `--max N` batches** sized to ~finish in ~9 min. Scanned batches ≈ 20–25 cases.
- **Cache the Drive index.** Re-paging 15k files on every startup is what killed early
  resumes. Now cached in `drive_index.json`.
- **Save progress often:** checkpoint every 5 cases, incremental sheet push every 20
  (`reconcile_push`, idempotent). A kill then never loses work.
- **Reconcile pushes ALL `ok` cases from the checkpoint** — necessary because prior
  `--dry-run`s mark cases `ok` without writing.
- **To purge bad rows you must CLEAR + rewrite the sheet** (upsert only appends).
- **Keep OCR page budget small** (`BUSKIN_PAGE_CAP=4`): the plate is on [0,4,15]; scanning a
  whole scanned bundle to conclude "no plate" is the main time sink.

---

## 14. Known limitations & next steps

- **66 unreadable scans** (`none-ocr`/`cap`) — the plate exists only in a poor scan. Options:
  a better OCR engine (Tesseract w/ a plate whitelist, PaddleOCR) or manual review.
- **A few cases may have the demanda in `doc1`** not `doc0` (rare; current logic reads doc0 only).
- **Owner enrichment not wired.** By user's choice the 666 plates go to the **standalone sheet
  only**. To feed `felipe/scraper/enrich_patentes_local.py` (marca/modelo/propietario), have
  Buskin also upsert into the scraper's `Patentes` + `CausaXPatente` tabs — not done yet.
- **Other juzgados:** logic is lobarnechea-scoped (filename prefix + `TRIBUNAL` map). Vitacura
  etc. would need the same treatment.

---

## 15. Re-run checklist (when new cases are scraped)

1. `python buskin.py` — processes only new gap-cases (checkpoint skips done ones).
2. If Drive got new files, `del drive_index.json` first to re-index.
3. After the run: **sanity check no plate appears in >2 rols** (false-positive guard).
