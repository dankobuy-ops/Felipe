"""Collapse the dozens of consecutive frames a single car appears in into ONE
sighting, keeping the sharpest / highest-confidence read as its representative.

A plate seen again after a gap longer than ``merge_window_s`` counts as a new
sighting (you passed the same car twice, or two cars share... they don't, but a
long gap means a genuinely separate encounter).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np

from src.color import estimate_color
from src.recognize import Detection


@dataclass
class Sighting:
    plate: str                 # normalized
    text_raw: str              # raw OCR of the best frame
    ocr_confidence: float
    det_confidence: float
    color: str
    first_time_s: float
    last_time_s: float
    best_time_s: float
    box: tuple[int, int, int, int]
    crop_jpg: bytes
    frame_jpg: Optional[bytes]


def _crop(frame_bgr: np.ndarray, box: tuple[int, int, int, int], pad: float = 0.15) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = box
    px = int((x2 - x1) * pad)
    py = int((y2 - y1) * pad)
    x1 = max(0, x1 - px); y1 = max(0, y1 - py)
    x2 = min(w, x2 + px); y2 = min(h, y2 + py)
    return frame_bgr[y1:y2, x1:x2]


def _encode(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes() if ok else b""


class SightingAggregator:
    """Feed detections frame-by-frame in time order; get one Sighting per car."""

    def __init__(
        self,
        merge_window_s: float,
        on_flush: Callable[[Sighting], None],
        save_full_frames: bool = True,
        estimate_color_flag: bool = True,
    ):
        self.merge_window_s = merge_window_s
        self.on_flush = on_flush
        self.save_full_frames = save_full_frames
        self.estimate_color_flag = estimate_color_flag
        self._active: dict[str, Sighting] = {}

    def _is_better(self, det: Detection, current: Sighting) -> bool:
        return (det.ocr_confidence, det.det_confidence) > (
            current.ocr_confidence, current.det_confidence
        )

    def _build(self, det: Detection, frame_bgr: np.ndarray, time_s: float) -> Sighting:
        color = (
            estimate_color(frame_bgr, det.box) if self.estimate_color_flag else "unknown"
        )
        return Sighting(
            plate=det.text,
            text_raw=det.text_raw,
            ocr_confidence=det.ocr_confidence,
            det_confidence=det.det_confidence,
            color=color,
            first_time_s=time_s,
            last_time_s=time_s,
            best_time_s=time_s,
            box=det.box,
            crop_jpg=_encode(_crop(frame_bgr, det.box)),
            frame_jpg=_encode(frame_bgr) if self.save_full_frames else None,
        )

    def update(self, det: Detection, frame_bgr: np.ndarray, time_s: float) -> None:
        # First, retire any active sightings that have gone stale.
        self._flush_stale(time_s)

        current = self._active.get(det.text)
        if current is None:
            self._active[det.text] = self._build(det, frame_bgr, time_s)
            return

        current.last_time_s = time_s
        if self._is_better(det, current):
            rebuilt = self._build(det, frame_bgr, time_s)
            rebuilt.first_time_s = current.first_time_s  # keep original first-seen
            self._active[det.text] = rebuilt

    def _flush_stale(self, now_s: float) -> None:
        stale = [
            plate for plate, s in self._active.items()
            if now_s - s.last_time_s > self.merge_window_s
        ]
        for plate in stale:
            self.on_flush(self._active.pop(plate))

    def flush_all(self) -> None:
        for sighting in self._active.values():
            self.on_flush(sighting)
        self._active.clear()
