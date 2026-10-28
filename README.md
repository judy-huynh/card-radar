# card-radar (stage 1)

Scans eBay US + CA for six WOTC-era Pokémon targets and texts the current cheapest listings via iMessage.
No buying, no thresholds yet.

## Setup
1. eBay developer account: https://developer.ebay.com → create app keyset (Production) → copy Client ID + Client Secret.
2. `cp .env.example .env`, fill in keys and TEXT_TO (your phone number or Apple ID).
3. `python3 scan.py`

Edit `watchlist.json` to change queries, exclusions, price cap, result count. `collectr_usd` is for stage 2.
