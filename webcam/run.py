#!/usr/bin/env python
"""Launcher so you can run the tool from the project root:

    python run.py process data/videos
    python run.py list
"""
from src.cli import main

if __name__ == "__main__":
    main()
