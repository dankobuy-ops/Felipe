"""SQLite persistence: the plate register plus every individual sighting event,
and the on-disk crop / frame images each sighting points to.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config import Config
from src.dedup import Sighting

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plates (
    plate          TEXT PRIMARY KEY,   -- normalized plate string
    first_seen     TEXT,               -- ISO timestamp, earliest sighting
    last_seen      TEXT,               -- ISO timestamp, latest sighting
    sighting_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sightings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    plate          TEXT NOT NULL,      -- normalized (links to plates.plate)
    plate_raw      TEXT,               -- exactly what the OCR read
    source_video   TEXT,
    frame_time_s   REAL,               -- seconds into the source video
    seen_at        TEXT,               -- best-effort absolute timestamp
    ocr_confidence REAL,
    det_confidence REAL,
    color          TEXT,
    make           TEXT,               -- reserved; not populated locally yet
    crop_path      TEXT,
    frame_path     TEXT,
    created_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_sightings_plate ON sightings(plate);
CREATE INDEX IF NOT EXISTS idx_sightings_seen  ON sightings(seen_at);
"""


def _safe(name: str) -> str:
    """Filesystem-safe token for building image filenames."""
    return "".join(c if c.isalnum() else "_" for c in name)


class Store:
    def __init__(self, config: Config):
        self.config = config
        config.ensure_dirs()
        self.conn = sqlite3.connect(str(config.paths.db))
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # -- writing ------------------------------------------------------------
    def save_sighting(
        self,
        sighting: Sighting,
        source_video: str,
        video_start: Optional[datetime],
    ) -> int:
        seen_at = (
            (video_start + timedelta(seconds=sighting.best_time_s)).isoformat()
            if video_start else None
        )
        stamp = _safe(f"{int(sighting.best_time_s * 1000)}")
        stem = _safe(Path(source_video).stem)
        base = f"{sighting.plate}_{stem}_{stamp}"

        crop_path = self.config.paths.crops / f"{base}.jpg"
        crop_path.write_bytes(sighting.crop_jpg)

        frame_path = None
        if sighting.frame_jpg:
            frame_path = self.config.paths.frames / f"{base}.jpg"
            frame_path.write_bytes(sighting.frame_jpg)

        now = datetime.now().isoformat()
        cur = self.conn.execute(
            """INSERT INTO sightings
               (plate, plate_raw, source_video, frame_time_s, seen_at,
                ocr_confidence, det_confidence, color, make,
                crop_path, frame_path, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sighting.plate, sighting.text_raw, source_video,
                sighting.best_time_s, seen_at,
                sighting.ocr_confidence, sighting.det_confidence,
                sighting.color, None,
                str(crop_path), str(frame_path) if frame_path else None, now,
            ),
        )
        self._upsert_plate(sighting.plate, seen_at)
        self.conn.commit()
        return cur.lastrowid

    def _upsert_plate(self, plate: str, seen_at: Optional[str]) -> None:
        row = self.conn.execute(
            "SELECT first_seen, last_seen, sighting_count FROM plates WHERE plate=?",
            (plate,),
        ).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO plates (plate, first_seen, last_seen, sighting_count)"
                " VALUES (?,?,?,1)",
                (plate, seen_at, seen_at),
            )
            return
        first_seen, last_seen, count = row
        # None sorts oddly; only replace when we actually have a timestamp.
        new_first = min(x for x in (first_seen, seen_at) if x) if (first_seen or seen_at) else None
        new_last = max(x for x in (last_seen, seen_at) if x) if (last_seen or seen_at) else None
        self.conn.execute(
            "UPDATE plates SET first_seen=?, last_seen=?, sighting_count=? WHERE plate=?",
            (new_first, new_last, count + 1, plate),
        )

    # -- reading ------------------------------------------------------------
    def recent_sightings(self, limit: int = 25) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        return self.conn.execute(
            "SELECT * FROM sightings ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def plate_summary(self) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        return self.conn.execute(
            "SELECT * FROM plates ORDER BY sighting_count DESC, last_seen DESC"
        ).fetchall()

    def counts(self) -> tuple[int, int]:
        n_plates = self.conn.execute("SELECT COUNT(*) FROM plates").fetchone()[0]
        n_sightings = self.conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
        return n_plates, n_sightings

    def close(self) -> None:
        self.conn.close()
