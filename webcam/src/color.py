"""Approximate a vehicle's color from the body area just above the plate.

We only have the plate's bounding box, not the whole car, so we sample the
region directly above it (grille / hood / trunk) and map the dominant hue to a
coarse color name. This is a best-effort hint, not ground truth.
"""
from __future__ import annotations

import cv2
import numpy as np

# (name, hue_low, hue_high) in OpenCV HSV where H is 0..179.
_HUE_NAMES = [
    ("red", 0, 10),
    ("orange", 11, 20),
    ("yellow", 21, 33),
    ("green", 34, 85),
    ("blue", 86, 130),
    ("purple", 131, 160),
    ("red", 161, 179),  # red wraps around the hue circle
]


def _name_from_hsv(h: float, s: float, v: float) -> str:
    # Low saturation = achromatic: decide by brightness.
    if s < 40:
        if v < 55:
            return "black"
        if v > 200:
            return "white"
        return "silver" if v > 130 else "gray"
    if v < 45:
        return "black"
    for name, lo, hi in _HUE_NAMES:
        if lo <= h <= hi:
            # Dark, saturated warm hues usually read as brown, not red/orange.
            if name in ("red", "orange") and v < 110:
                return "brown"
            return name
    return "unknown"


def estimate_color(frame_bgr: np.ndarray, box: tuple[int, int, int, int]) -> str:
    """Sample the car body above the plate box and name its dominant color."""
    h, w = frame_bgr.shape[:2]
    x1, y1, x2, y2 = box
    plate_h = max(1, y2 - y1)
    plate_w = max(1, x2 - x1)

    # A patch roughly the plate's width, sitting just above it.
    sy2 = max(0, y1 - int(0.2 * plate_h))
    sy1 = max(0, sy2 - int(1.5 * plate_h))
    cx = (x1 + x2) // 2
    half = plate_w // 2
    sx1 = max(0, cx - half)
    sx2 = min(w, cx + half)

    if sy2 <= sy1 or sx2 <= sx1:
        return "unknown"

    patch = frame_bgr[sy1:sy2, sx1:sx2]
    if patch.size == 0:
        return "unknown"

    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    h_med = float(np.median(hsv[:, :, 0]))
    s_med = float(np.median(hsv[:, :, 1]))
    v_med = float(np.median(hsv[:, :, 2]))
    return _name_from_hsv(h_med, s_med, v_med)
