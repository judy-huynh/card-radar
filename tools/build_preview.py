#!/usr/bin/env python3
"""Regenerate the two static previews from the real dashboard files:
  index.html          GitHub Pages (repo root), example data
  dashboard/mock.html claude.ai artifact, example data
Run after changing dashboard/ or tools/make_sample.py."""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "dashboard", "index.html")).read()
pages = src.replace('href="style.css"', 'href="dashboard/style.css"').replace(
    '<script src="app.js"></script>', '<script src="dashboard/sample.js"></script>\n<script src="dashboard/app.js"></script>')
open(os.path.join(ROOT, "index.html"), "w").write(pages)
body = re.search(r"<body>(.*)</body>", src, re.S).group(1).replace(
    '<script src="app.js"></script>', '<script src="sample.js"></script>\n<script src="app.js"></script>')
open(os.path.join(ROOT, "dashboard", "mock.html"), "w").write(
    '<title>Card Radar</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n<link rel="stylesheet" href="style.css">\n' + body)
print("built index.html and dashboard/mock.html")
