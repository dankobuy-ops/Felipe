"""Wrap fast-alpr into a small, stable interface the rest of the code depends on.

fast-alpr does two things per frame: detect plate boxes (YOLO) and read the
characters (OCR). We normalize its result objects into a plain ``Detection`` so
that if the library's API shifts, only this file needs to change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

# Chilean car plates (post-2007): 4 letters + 2 digits, e.g. "BFGK43".
# Older format is 2 letters + 4 digits. We normalize but never hard-reject,
# so foreign or legacy plates still get logged.
_CL_MODERN = re.compile(r"^[A-Z]{4}\d{2}$")
_CL_LEGACY = re.compile(r"^[A-Z]{2}\d{4}$")


@dataclass
class Detection:
    text: str            # normalized plate string (uppercased, alphanumeric only)
    text_raw: str        # exactly what the OCR returned
    ocr_confidence: float
    det_confidence: float
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixel coordinates


def normalize_plate(raw: str) -> str:
    """Uppercase and strip anything that isn't a letter or digit."""
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def looks_like_cl_plate(normalized: str) -> bool:
    return bool(_CL_MODERN.match(normalized) or _CL_LEGACY.match(normalized))


def _to_float(value) -> float:
    """OCR confidence may be a float or a per-character sequence — reduce to one."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        arr = np.asarray(value, dtype=float)
        return float(arr.mean()) if arr.size else 0.0
    except (TypeError, ValueError):
        return 0.0


class PlateRecognizer:
    """Lazy wrapper around fast-alpr's ALPR pipeline."""

    def __init__(self, detector_model: str, ocr_model: str):
        # Imported here so `--help` and unit tests don't pay the import cost.
        from fast_alpr import ALPR

        self._alpr = ALPR(detector_model=detector_model, ocr_model=ocr_model)

    def recognize(self, frame_bgr: np.ndarray) -> list[Detection]:
        results = self._alpr.predict(frame_bgr)
        detections: list[Detection] = []

        for r in results:
            det = getattr(r, "detection", None)
            ocr = getattr(r, "ocr", None)
            if det is None or ocr is None:
                continue

            raw_text = getattr(ocr, "text", "") or ""
            normalized = normalize_plate(raw_text)
            if not normalized:
                continue

            box = getattr(det, "bounding_box", det)
            try:
                x1, y1, x2, y2 = (
                    int(box.x1), int(box.y1), int(box.x2), int(box.y2)
                )
            except AttributeError:
                # Some versions expose the box as a 4-tuple instead.
                x1, y1, x2, y2 = (int(v) for v in box)

            detections.append(
                Detection(
                    text=normalized,
                    text_raw=raw_text,
                    ocr_confidence=_to_float(getattr(ocr, "confidence", None)),
                    det_confidence=_to_float(getattr(det, "confidence", None)),
                    box=(x1, y1, x2, y2),
                )
            )
        return detections
