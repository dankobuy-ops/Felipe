"""Load config.yaml into a typed object with paths resolved to the project root."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Project root = the folder that contains this src/ package.
ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Paths:
    videos: Path
    frames: Path
    crops: Path
    db: Path


@dataclass
class Config:
    region: str
    detector_model: str
    ocr_model: str
    frame_sample_every: int
    min_ocr_confidence: float
    min_det_confidence: float
    merge_window_seconds: float
    save_full_frames: bool
    estimate_color: bool
    paths: Paths = field(default=None)  # type: ignore[assignment]

    def ensure_dirs(self) -> None:
        """Create the output folders if they don't exist yet."""
        for p in (self.paths.videos, self.paths.frames, self.paths.crops):
            p.mkdir(parents=True, exist_ok=True)
        self.paths.db.parent.mkdir(parents=True, exist_ok=True)


def _resolve(p: str) -> Path:
    """Resolve a config path against the project root (absolute paths pass through)."""
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)


def load_config(path: str | Path | None = None) -> Config:
    cfg_path = Path(path) if path else (ROOT / "config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    paths = Paths(
        videos=_resolve(raw["paths"]["videos"]),
        frames=_resolve(raw["paths"]["frames"]),
        crops=_resolve(raw["paths"]["crops"]),
        db=_resolve(raw["paths"]["db"]),
    )
    return Config(
        region=raw.get("region", "cl"),
        detector_model=raw["detector_model"],
        ocr_model=raw["ocr_model"],
        frame_sample_every=int(raw.get("frame_sample_every", 1)),
        min_ocr_confidence=float(raw.get("min_ocr_confidence", 0.5)),
        min_det_confidence=float(raw.get("min_det_confidence", 0.3)),
        merge_window_seconds=float(raw.get("merge_window_seconds", 3.0)),
        save_full_frames=bool(raw.get("save_full_frames", True)),
        estimate_color=bool(raw.get("estimate_color", True)),
        paths=paths,
    )
