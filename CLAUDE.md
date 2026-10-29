# Card Radar — working rules for Claude

Owner: Judy (GitHub judy-huynh). Alerts go to Ben. Both are non-technical: explain trade-offs in plain words,
ask only on real forks (money, strategy, terms of service), decide routine things yourself.

## Read first
- `SPEC.md` is the contract: end goal, agents, decision rules, done criteria, open decisions. Change the spec
  before changing behaviour; strategy lives in the spec and config, not in code.
- `config/targets.json` + `config/settings.json` hold every threshold. Never hard-code one.

## Live system guardrails
- The iMac runs it: launchd `com.judy.cardradar.server` (port 8790) and `com.judy.cardradar.scan`.
  Port 8787 belongs to Ben's Kalshi dashboard; don't touch it or anything under ~/Downloads/Kalshi or ~/nrfi.
- `radar.db` is live state. Never delete or stash it; test against a temp DB (`RADAR_DB=...`, see tests).
- Never send test pushes to the real topic without saying so; use `RADAR_DRY=1` or `dry=True`.
- The repo is PUBLIC. Never commit `.env`, the ntfy topic, the Tailscale hostname, or the database.
- The iMac is sometimes switched off overnight on purpose. Gaps in scan history are normal.

## How to change things
- New marketplace = new file in `radar/scouts/` returning the listing shape documented in `scouts/__init__.py`.
- Matching changes need a test in `tests/test_match.py` with a real-looking title. Run the full suite:
  `python3 -m unittest discover -s tests -t .`
- Catalog fixture (`tests/fixtures/cards.json`) is a snapshot of real tcgcsv data; refresh it only on purpose.
- After dashboard changes: `python3 tools/make_sample.py && python3 tools/build_preview.py`, then republish
  the preview artifact (https://claude.ai/artifact/KesV4xBus9Qa1gpn8SJv4n) from `dashboard/mock.html`.
- Python 3.9 stdlib only on the iMac. No pip installs.

## Data sources and their limits
- Values: tcgcsv.com (daily TCGplayer mirror). Collectr has no API; its values come in as manual overrides.
- Listings: eBay Browse API (5,000 calls/day default). The cycle enforces the budget.
- FX: Frankfurter (ECB), daily.
