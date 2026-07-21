# 🚲 Bike ALPR — Session Handoff

> **Session ID:** `55ccdb90-f8ae-487a-b10c-fd51bc270dbe`
> **Handoff date:** 2026-07-21
> **Project root:** `C:\Claude\webcam` (a subfolder of the `C:\Claude` monorepo → GitHub `dankobuy-ops/Felipe`, branch `main`)
> **Scaffold commit:** `e457c40 — feat(webcam): scaffold offline bike ALPR pipeline`
> **Status:** Scaffolded **and validated on a synthetic clip** (dedup 60→1, OCR 0.97, color + DB all working). **Not yet run on real footage.**

To resume this exact session with full context (Claude Code CLI):

```
claude --resume 55ccdb90-f8ae-487a-b10c-fd51bc270dbe
```

---

## 1. What this project is

A record-then-process tool that reads the **license plates of cars that pass while cycling** and logs them locally. You film a ride with any camera, drop the footage on this PC, and the tool detects + reads each plate frame-by-frame and registers it in a SQLite database, saving a cropped plate image and full frame per sighting.

```
📹  data/videos/*.mp4   →   🔍 detect + read plate   →   🗄️ plate + time + color + images
      (your footage)          (fast-alpr, local)          (SQLite + saved crops/frames)
```

**Everything runs offline. No footage or plate ever leaves the machine.**

---

## 2. Current status

| Stage | State |
|-------|-------|
| Project scaffold (src/, config, CLI) | ✅ done, committed `e457c40` |
| Python venv + dependencies | ✅ installed at `webcam/.venv` |
| Models (yolo-v9 detector + OCR) | ✅ downloaded & cached (`~/.cache/open-image-models`, fast-plate-ocr cache) |
| End-to-end pipeline | ✅ validated on a synthetic clip |
| **Run on real footage** | ❌ **not done — this is the next step** |
| Threshold tuning on real Chilean plates | ❌ pending real footage |

---

## 3. Repo & environment

```bash
cd C:\Claude\webcam
.venv\Scripts\activate          # deps already installed; no pip needed

python run.py process data\videos          # process every clip in the folder
python run.py process data\videos\ride.mp4 # or a single clip
python run.py list                          # recent sightings
python run.py plates                        # unique-plate register + counts
python run.py stats                         # totals
```

Dependencies (`requirements.txt`): `fast-alpr`, `onnxruntime`, `opencv-python`, `numpy`, `PyYAML`. Python 3.12.

---

## 4. How it works (file map)

| Stage | File | Responsibility |
|-------|------|----------------|
| Capture | `src/capture.py` | Decode video → frames + timestamps; probe fps/duration; find video files |
| Recognize | `src/recognize.py` | Wrap fast-alpr → normalized `Detection`; CL plate normalization |
| Color | `src/color.py` | Approximate vehicle color from the body area **above** the plate (HSV) |
| Dedup | `src/dedup.py` | Collapse many consecutive frames of one car into one `Sighting`, keeping the best read |
| Store | `src/store.py` | SQLite schema, upsert plate, insert sighting, save crop/frame JPGs |
| Pipeline | `src/pipeline.py` | Wire it together per video |
| CLI | `src/cli.py` + `run.py` | `process` / `list` / `plates` / `stats` |
| Config | `config.yaml` | All tuning knobs (see §6) |

---

## 5. Data model (SQLite `data/plates.db`)

**`plates`** (the register — one row per unique plate)
`plate` (PK, normalized) · `first_seen` · `last_seen` · `sighting_count`

**`sightings`** (one row per distinct encounter)
`id` · `plate` · `plate_raw` (exact OCR) · `source_video` · `frame_time_s` (seconds into clip) · `seen_at` (best-effort absolute time) · `ocr_confidence` · `det_confidence` · `color` · `make` (**reserved, stays NULL**) · `crop_path` · `frame_path` · `created_at`

> `seen_at` is approximate: derived from the video file's modified-time minus its duration, plus the frame offset. Good for "roughly when," not forensic. Real GPS/absolute time is a future step (§8).

---

## 6. Config knobs (`config.yaml`)

- **`detector_model`** — `yolo-v9-t-384-license-plate-end2end` (fastest). For **small/distant plates**, switch to `yolo-v9-t-640-license-plate-end2end` or `yolo-v9-s-608-license-plate-end2end` (better recall, slower).
- **`ocr_model`** — `global-plates-mobile-vit-v2-model` (works on CL plates).
- **`frame_sample_every`** — process every Nth frame. `1` = every frame (max recall for fast-passing cars, more CPU); `2`–`3` good for 60fps.
- **`min_ocr_confidence`** (0.55) / **`min_det_confidence`** (0.30) — raise to cut false reads, lower to catch more.
- **`merge_window_seconds`** (3.0) — gap that splits one car into two sightings. Raise if one car is split; lower if two cars merge.
- **`save_full_frames`** / **`estimate_color`** — toggles.

---

## 7. Design decisions (chosen 2026-07-15, and why)

1. **Record-then-process, offline** (not real-time on the bike) — fastest path to a working v1, no embedded hardware/power/mounting. Code is structured so a live capture source could later replace `capture.iter_frames` without touching recognition/storage.
2. **Fully local / open-source** recognition (fast-alpr) — free, private, no per-plate cost.
3. **Save plate crop + full frame** per sighting — so misreads can be eyeballed.
4. **Approximate vehicle color** — cheap, populated. **Make/model deferred** — unreliable locally; the one thing a cloud engine (e.g. Plate Recognizer) does much better. `make` column reserved.
5. **No GPS** selected initially — easy to add later if a GPS-capable camera is used.
6. **Camera:** start with the user's **phone** (4K/60, daylight); buy a GoPro/DJI Osmo Action only if the phone's reads prove unreliable. Nothing bought yet.

---

## 8. NEXT STEPS (prioritized, detailed)

### ▶ P0 — Validate on real footage (do this first)
1. Film a **30–60 s daylight clip** with the phone at **4K/60**, capturing plates of passing/parked cars (handlebar or chest mount).
2. Copy it into `webcam\data\videos\`.
3. `cd C:\Claude\webcam && .venv\Scripts\activate && python run.py process data\videos`
4. `python run.py list`, then open the images in `data\crops\` and compare OCR vs. the real plate.
5. Note: hit rate, common misreads, cars missed entirely, false positives.
6. **Tune `config.yaml` from what you see:**
   - Cars not detected → lower `min_det_confidence`; try a bigger `detector_model` (640 / 608).
   - Garbage reads → raise `min_ocr_confidence`.
   - One car split into many rows → raise `merge_window_seconds`; two cars merged → lower it.
   - Fast-passing cars slipping through → set `frame_sample_every: 1`.

### ▶ P1 — Chilean-plate post-correction (high value, low effort)
- Modern CL auto plate = **4 letters + 2 digits**. Add position-aware fixups: in the first 4 (letters) map `0→O 1→I 8→B 5→S 2→Z 6→G`; in the last 2 (digits) map the reverse. Only apply when length is 6 and near the CL shape; keep `plate_raw` untouched.
- Touch: extend `src/recognize.py` (or a new `src/plate_rules.py`).

### ▶ P1 — Multi-frame OCR voting (big accuracy win)
- Today dedup keeps only the single best frame's read (`_is_better`). Instead accumulate **all** reads for an active plate and do a **per-character majority vote** on flush. Keeps the best crop/frame as the representative image.
- Touch: `src/dedup.py` (`Sighting` gains a `reads` list; resolve consensus in `on_flush`).

### ▶ P1 — Idempotency: don't double-count re-runs (real gap)
- Re-processing the same video currently inserts **duplicate sightings**. Add a `processed_videos` table (name + size + mtime, or content hash); `process_video` skips already-done files unless `--force`.
- Touch: `src/store.py` (new table + check), `src/pipeline.py`, `src/cli.py` (`--force`).

### ▶ P1 — Review UI (serves the "eyeball misreads" goal)
- Small **local** web app (Streamlit is fastest; or Flask + minimal HTML). Table of sightings → click a row → crop + full frame side by side → inline-edit the plate, delete false positives, flag "plate of interest". Reads/writes the same SQLite DB.
- New: `src/review_app.py`; add `python run.py review` to launch.

### ▷ P2 — GPS location
- If filming with a GPS camera (GoPro records a GPMF telemetry stream), parse the GPS track and **join by timestamp** to attach lat/lon (+ a maps link) to each sighting. Tools: `exiftool` or a GPMF/`gopro-telemetry` parser; interpolate to `video_start + best_time_s`. Add lat/lon columns.

### ▷ P2 — Export / Google Sheets sync
- `python run.py export` → CSV/JSON of the register; optionally push to a Google Sheet (consistent with the user's other projects).

### ▷ P2 — Make / model recognition
- Deferred by design. Accurate path is a cloud engine (Plate Recognizer returns make/model/color) or a dedicated vehicle-MMR model. `make` column already reserved.

### ▷ P2 — Watchlist / repeat-offender alerts
- `plates` already tracks `sighting_count` + first/last seen. Add `python run.py watch` to flag plates seen ≥N times or across ≥N days (e.g. a car that keeps buzzing the rider).

### ▷ P2 — Performance & robustness
- GPU: install `onnxruntime-gpu` + set the CUDA provider in `src/recognize.py` if an NVIDIA card is available (big speedup on long footage).
- Add a tqdm progress bar + per-video ETA; skip corrupt frames gracefully; log to a file.
- Unit tests: `normalize_plate`, dedup grouping, color naming; a tiny fixture clip.

---

## 9. Things a future session MUST know (gotchas)

- **Monorepo gitignore convention:** `C:\Claude\.gitignore` **ignores all code by default** (`*.py`, `*.json`, …) — it tracks context/memories, not code. Each code project needs an explicit `!webcam/**` exception (already added, mirrors `!felipe/**`). Capture data + venv + db are excluded by `webcam/.gitignore`. If new source files "won't add," this is why.
- **Windows console = cp1252:** printing non-ASCII (arrows, bullets) crashes with `UnicodeEncodeError`. `cli.main()` forces stdout/stderr to UTF-8; keep printed decoration ASCII to be safe.
- **fast-alpr result shape** (verified against installed source, v0.4.0): `ALPRResult.detection` (`DetectionResult`: `.confidence`, `.bounding_box.{x1,y1,x2,y2}`) and `ALPRResult.ocr` (`OcrResult`: `.text`, `.confidence` which may be a float **or a per-char list** — `recognize._to_float` handles both). If fast-alpr's API shifts, `src/recognize.py` is the only file to change.
- **Dedup is time-ordered & online:** frames must be fed in increasing time order; `merge_window_seconds` is the only thing separating two encounters of the same plate string.
- **`data/` is git-ignored** (footage, images, db). It won't survive a fresh clone — the `.gitkeep` files preserve the empty folders only.
- **`webcam/.claude/settings.local.json`** is tracked (repo convention force-tracks `.claude/`) but churns every session. Open item: gitignore just that file if the dirty status is annoying.

---

## 10. Open questions / pending decisions

- Gitignore `webcam/.claude/settings.local.json`? (churns each session)
- Standalone repo vs. staying in the `C:\Claude` monorepo? (currently: monorepo, scoped commits)
- Camera: stick with phone, or buy a GoPro/DJI after the first real test?
- Do we want GPS (changes camera choice + schema)?
