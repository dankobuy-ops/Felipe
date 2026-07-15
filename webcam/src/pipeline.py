"""End-to-end: video file(s) -> plate recognition -> dedup -> database + images."""
from __future__ import annotations

from pathlib import Path

from src import capture
from src.config import Config
from src.dedup import Sighting, SightingAggregator
from src.recognize import PlateRecognizer, looks_like_cl_plate
from src.store import Store


def process_video(
    path: Path,
    config: Config,
    recognizer: PlateRecognizer,
    store: Store,
) -> int:
    """Process one video. Returns the number of sightings written."""
    info = capture.probe(path)
    print(
        f"-> {path.name}  "
        f"({info.frame_count} frames @ {info.fps:.0f}fps, {info.duration_s:.0f}s)"
    )

    written = 0

    def on_flush(sighting: Sighting) -> None:
        nonlocal written
        store.save_sighting(sighting, source_video=path.name, video_start=info.start_time)
        written += 1
        flag = "" if looks_like_cl_plate(sighting.plate) else "  (unusual format)"
        print(
            f"   - {sighting.plate:<8} "
            f"ocr={sighting.ocr_confidence:.2f} "
            f"@ {sighting.best_time_s:6.1f}s  {sighting.color}{flag}"
        )

    aggregator = SightingAggregator(
        merge_window_s=config.merge_window_seconds,
        on_flush=on_flush,
        save_full_frames=config.save_full_frames,
        estimate_color_flag=config.estimate_color,
    )

    for vf in capture.iter_frames(path, sample_every=config.frame_sample_every):
        for det in recognizer.recognize(vf.image):
            if det.ocr_confidence < config.min_ocr_confidence:
                continue
            if det.det_confidence < config.min_det_confidence:
                continue
            aggregator.update(det, vf.image, vf.time_s)

    aggregator.flush_all()
    return written


def process_target(target: Path, config: Config) -> None:
    """Process a single video file or every video in a directory."""
    videos = capture.find_videos(target)
    if not videos:
        print(f"No videos found at {target}")
        return

    config.ensure_dirs()
    store = Store(config)
    print(f"Loading models ({config.detector_model} + {config.ocr_model})...")
    recognizer = PlateRecognizer(config.detector_model, config.ocr_model)

    total = 0
    try:
        for video in videos:
            total += process_video(video, config, recognizer, store)
        n_plates, n_sightings = store.counts()
        print(
            f"\nDone. Wrote {total} new sighting(s) this run.  "
            f"Database now holds {n_sightings} sightings across {n_plates} plates."
        )
    finally:
        store.close()
