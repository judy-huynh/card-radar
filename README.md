# Card Radar

Sourcing radar for WOTC-era Pokémon cards. Scans eBay US + CA for a watchlist, pushes alerts to your phone via ntfy,
and serves a decision dashboard over Tailscale. Alert only; it never buys.

```
radar/        the library
  config.py   .env + watchlist.json (single source of truth for what we scan and when we alert)
  ebay.py     eBay Browse API (official; app token + item_summary search)
  notify.py   ntfy push, with a click URL that deep-links to the alert row
  store.py    SQLite: listings seen, alerts sent, decisions made, scan runs
  scan.py     one scan pass
scan.py       CLI: `python3 scan.py` (one pass), `--dry` (no push), `--test-text`
server.py     dashboard + JSON API on :8790 (no auth: Tailscale only, never public)
dashboard/    index.html, style.css, app.js — static, talks to /api
launchd/      plists: server (always on) and scan (every 5 min)
watchlist.json  edit here or from the dashboard; never in code
```

## Setup
1. eBay developer keyset (Production) → `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` in `.env` (copy `.env.example`).
2. ntfy app on phone, subscribe to the topic in `NTFY_TOPIC`.
3. `python3 scan.py --test-text` → phone buzzes.
4. `python3 server.py` → http://localhost:8790
5. Tailscale: start Tailscale on this Mac and on the phone, then set `DASHBOARD_URL=http://<mac-tailscale-name>:8790` in `.env`
   so ntfy click links open the dashboard from anywhere.
6. Always-on: `cp launchd/*.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.judy.cardradar.*.plist`

## API
- `GET  /api/state` — everything the dashboard renders
- `POST /api/alerts/<id>/decision` `{"decision":"passed|bought|open","outcome":"..."}`
- `POST /api/watchlist/<index>` any of `alert_gap_pct, max_price_usd, paused, condition, query`

## Stages
- **1 (now)** every new listing under max ask = alert. Prove the plumbing.
- **2** Collectr reference values per card, landed cost (shipping + FX + tax/duty) to CA and NYC, gap threshold, seller/condition guardrails.
- **3** outcome tracking: did passes sell, did buys arrive as described. Tune thresholds from evidence.
