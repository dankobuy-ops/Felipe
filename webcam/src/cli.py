"""Command-line entry point.

    python run.py process data/videos            # process every clip in the folder
    python run.py process data/videos/ride1.mp4  # process one clip
    python run.py list                           # show recent sightings
    python run.py plates                          # show the plate register
    python run.py stats                           # totals
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import load_config
from src.pipeline import process_target
from src.store import Store


def _cmd_process(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    process_target(Path(args.target), config)


def _cmd_list(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    store = Store(config)
    try:
        rows = store.recent_sightings(limit=args.limit)
        if not rows:
            print("No sightings yet. Process some footage first.")
            return
        print(f"{'plate':<9} {'when':<20} {'ocr':>4} {'color':<8} video")
        print("-" * 70)
        for r in rows:
            when = (r["seen_at"] or f"{r['frame_time_s']:.1f}s")[:19]
            print(
                f"{r['plate']:<9} {when:<20} {r['ocr_confidence']:.2f} "
                f"{(r['color'] or '-'):<8} {r['source_video']}"
            )
    finally:
        store.close()


def _cmd_plates(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    store = Store(config)
    try:
        rows = store.plate_summary()
        if not rows:
            print("No plates registered yet.")
            return
        print(f"{'plate':<9} {'count':>5}  {'first_seen':<20} {'last_seen':<20}")
        print("-" * 62)
        for r in rows:
            print(
                f"{r['plate']:<9} {r['sighting_count']:>5}  "
                f"{(r['first_seen'] or '-')[:19]:<20} {(r['last_seen'] or '-')[:19]:<20}"
            )
    finally:
        store.close()


def _cmd_stats(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    store = Store(config)
    try:
        n_plates, n_sightings = store.counts()
        print(f"Plates registered: {n_plates}")
        print(f"Total sightings:   {n_sightings}")
        print(f"Database:          {config.paths.db}")
    finally:
        store.close()


def main() -> None:
    # Windows consoles default to cp1252; force UTF-8 so any character we print
    # (or that shows up in OCR text) never crashes the run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="bike-alpr",
        description="Recognize and log license plates from bike ride footage.",
    )
    parser.add_argument(
        "--config", default=None, help="Path to config.yaml (default: project root)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("process", help="Recognize plates in a video or folder")
    p.add_argument("target", help="A video file or a directory of videos")
    p.set_defaults(func=_cmd_process)

    p = sub.add_parser("list", help="Show recent sightings")
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("plates", help="Show the plate register")
    p.set_defaults(func=_cmd_plates)

    p = sub.add_parser("stats", help="Show totals")
    p.set_defaults(func=_cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
