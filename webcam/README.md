# 🚲 Bike ALPR

Recognize and log the license plates of cars that pass you while you ride.

You film a ride with any camera, drop the footage on this PC, and the tool reads
the plates frame-by-frame and registers each one in a local database — with a
cropped plate image and full frame saved as evidence. **Everything runs offline
on your machine; no footage or plate ever leaves the computer.**

```
📹  your footage  →  🔍  detect + read plate  →  🗄️  plate + time + color + images
   (data/videos/)      (fast-alpr, local)         (SQLite + saved crops/frames)
```

## Setup (one time)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell/CMD
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
```

The first `process` run downloads the recognition models (a few hundred MB) and
caches them — later runs are offline.

## Use it

```bash
# 1. Copy your ride videos into data/videos/
# 2. Process them:
python run.py process data/videos               # a whole folder
python run.py process data/videos/ride1.mp4     # or a single clip

# 3. Look at what it found:
python run.py list        # recent sightings (plate, time, color, video)
python run.py plates      # the plate register (unique plates + counts)
python run.py stats       # totals
```

Saved images live in `data/crops/` (the plate) and `data/frames/` (the whole
frame). Each row in the database points to its images so you can eyeball
anything the OCR might have misread.

## How it works

| Stage | File | What it does |
|-------|------|--------------|
| Capture | `src/capture.py` | Decodes the video, yields frames + timestamps |
| Recognize | `src/recognize.py` | fast-alpr: detect plate box + read characters |
| Color | `src/color.py` | Approximate car color from the body above the plate |
| Dedup | `src/dedup.py` | Collapse many frames of one car into a single sighting |
| Store | `src/store.py` | SQLite `plates` + `sightings` tables, saves crops/frames |
| Pipeline | `src/pipeline.py` | Wires it all together per video |

## Tuning (`config.yaml`)

- **`frame_sample_every`** — process every Nth frame. `1` = every frame (slow,
  most thorough); `2`–`3` is a good speed/accuracy trade for 60fps footage.
- **`min_ocr_confidence` / `min_det_confidence`** — raise to cut false reads,
  lower to catch more (and more garbage).
- **`merge_window_seconds`** — how long a gap splits one car into two sightings.

## Getting good reads (matters more than the camera)

- **Shoot in daylight.** Motion blur + low-light noise are what wreck plate OCR.
- **4K / 60fps** if your camera offers it — more pixels and more chances at a
  sharp frame.
- Action cams: use **"Linear"** field of view, not fisheye (warped characters
  read worse).

## Roadmap / not done yet

- **Make & model** — a `make` column exists in the schema but stays empty. True
  make/model recognition needs a separate trained model and is unreliable
  locally; deferred. (Colour is populated, approximately.)
- **GPS location** — if you later film with a GPS-capable camera/phone, we can
  attach where each car was passed.
- **Review UI** — a small web page to page through sightings and fix bad reads.
- **Live / on-bike mode** — the pipeline is structured so a real-time capture
  source can replace the video reader without rewriting recognition/storage.

Personal-use tool. Keep the data on your machine and mind your local rules on
recording plates.
