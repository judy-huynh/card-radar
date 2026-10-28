#!/usr/bin/env python3
"""CLI. `python3 scan.py` runs one pass. `--dry` stores but does not push. `--test-text` only pushes a test."""
import sys
from radar.config import load_env
from radar import notify, scan

if __name__ == "__main__":
    load_env()
    if "--test-text" in sys.argv:
        notify.push("Card radar test: notifications work."); print("test sent")
    else:
        scan.run(dry="--dry" in sys.argv)
