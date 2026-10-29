#!/usr/bin/env python3
"""Kept for muscle memory: same as `python3 -m radar run --force`."""
import sys
from radar.__main__ import main
main([sys.argv[0], "run", "--force"] + sys.argv[1:])
