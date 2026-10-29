# Card Radar

Finds the six WOTC-era Pokémon targets for sale on eBay worldwide, works out what each one would cost landed in
Canada or NYC, compares that to its Collectr / TCGplayer value, and pushes the deals to your phone with ntfy.
Everything it sees is on a dashboard reached over Tailscale. It never buys anything.

**Start here:** [SPEC.md](SPEC.md) is the end goal, the agents, the decision rules and the done criteria.
**Preview:** the repo's GitHub Pages site shows the dashboard with example data.

## How a listing becomes a push

```
Scouts (eBay US·CA·UK·AU·DE, newest first, ship-to CA / NYC)
  -> Matcher   title -> exact card, variant, grade, condition, red flags, confidence
  -> Valuer    Collectr value if you entered one, else TCGplayer market; condition-adjusted
  -> Landed    ask + shipping + FX + tax + import estimate, per destination
  -> Decider   DEAL / LISTED / WATCH / SEEN / REJECT, with the reason
  -> Notifier  ntfy push: tap = dashboard row, buttons = Open listing / Dashboard
  -> Watchdog  stale data, failing scouts, API budget, daily digest
```

## Layout

```
config/targets.json    the six targets and their thresholds (dashboard edits this)
config/settings.json   destinations + tax, markets, guardrails, caps (edit by hand)
radar/                 one module per agent; run.py is the cycle; db.py the shared store
server.py              dashboard + JSON API on :8790 (no login: Tailscale only)
dashboard/             index.html, style.css, app.js (live); sample.js + mock.html (preview only)
tests/                 offline tests incl. a full fake-market cycle; fixtures/cards.json = real catalog
tools/                 make_sample.py (preview data via the real pipeline), build_preview.py
launchd/               server (always on), scan (every 5 min; the cycle honours scan_interval_min)
```

## Run it

```
cp .env.example .env              # eBay keys, NTFY_TOPIC, DASHBOARD_URL
python3 -m radar test-push        # phone buzzes
python3 -m radar catalog          # load card values + FX now
python3 -m radar run --force      # one cycle now
python3 -m radar status           # agent health, API calls, last runs
python3 -m unittest discover -s tests -t .
cp launchd/*.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.judy.cardradar.*.plist
```

After changing the dashboard: `python3 tools/make_sample.py && python3 tools/build_preview.py`.

## API

- `GET  /api/state` everything the dashboard renders
- `GET  /api/values?target=<id>` card values for one target
- `POST /api/alerts/<id>/decision` `{"decision": "passed|bought|open", "outcome": "..."}`
- `POST /api/targets/<id>` any of `push_gap_pct, watch_gap_pct, min_value_usd, max_price_usd, paused`
- `POST /api/overrides` `{"card_key": "...", "value_usd": 123 | null}` (Collectr value)

## Keep the repo safe to be public

`.env` (ntfy topic, eBay keys, Tailscale URL) and `radar.db` are git-ignored. Never commit them.
Anyone with the ntfy topic can read the alerts.
