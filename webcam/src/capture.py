"""Decode a video and yield frames with their timestamp (seconds into the clip)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


@dataclass
class VideoFrame:
    image: np.ndarray  # BGR frame
    index: int         # frame number in the source
    time_s: float      # seconds from the start of the video


@dataclass
class VideoInfo:
    path: Path
    fps: float
    frame_count: int
    duration_s: float
    # Best-effort absolute time the recording STARTED. Derived from the file's
    # modified time (usually when recording finished) minus its duration.
    # Approximate — good enough to answer "roughly when did I pass this car".
    start_time: datetime


def probe(path: Path) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()

    duration_s = frame_count / fps if fps else 0.0
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    start_time = mtime - timedelta(seconds=duration_s)
    return VideoInfo(
        path=path,
        fps=fps,
        frame_count=frame_count,
        duration_s=duration_s,
        start_time=start_time,
    )


def iter_frames(path: Path, sample_every: int = 1) -> Iterator[VideoFrame]:
    """Yield every `sample_every`-th frame. sample_every=1 means all frames."""
    sample_every = max(1, int(sample_every))
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % sample_every == 0:
                yield VideoFrame(image=frame, index=idx, time_s=idx / fps)
            idx += 1
    finally:
        cap.release()


def find_videos(target: Path) -> list[Path]:
    """Resolve a file or directory into a sorted list of video files."""
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(
            p for p in target.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
        )
    raise FileNotFoundError(f"No such file or directory: {target}")
