# Card Radar — Spec

## End goal

Ben never searches for these cards by hand again. When one of the six targets is listed for sale anywhere we can see,
at a price worth acting on, Ben's phone buzzes (ntfy) with:

- **what** it is, matched to an exact card: set, name, number, variant (holo / reverse holo / 1st edition)
- **what it costs landed**: ask + shipping + FX + tax/duty estimate, to Canada and to NYC, cheaper one first
- **what it's worth**: Collectr value if Ben has entered one, otherwise TCGplayer market (the main source Collectr itself prices from)
- **the gap**: landed vs value, after a condition discount
- one tap → the listing; one tap → the dashboard row

Everything the system sees, pushes, rejects, and decides is visible on the dashboard
(`http://<imac-tailscale-name>:8790`, over Tailscale only), and every threshold is changed there or in config, never in code.

## Targets

| id | Set | What counts | TCGplayer group |
|---|---|---|---|
| `lc-reverse` | Legendary Collection (2002) | Reverse Holofoil, any card | 1374 |
| `southern-islands` | Southern Islands (2001) | any card, any foil | 648 |
| `skyridge-holo` | Skyridge (2003) | Holofoil: H1–H32 + crystal secret rares | 1372 |
| `aquapolis-holo` | Aquapolis (2003) | Holofoil: H1–H32 + crystal secret rares | 1397 |
| `dark-gengar` | Neo Destiny (2002) | Dark Gengar 6/105, 1st Ed or Unlimited holo | 1444 |
| `expedition-holo` | Expedition (2002) | Holofoil 1–32 | 1375 |

## The agents

Each agent is one module with one job. `radar/run.py` runs them in order on every cycle (launchd, every few minutes;
the run itself honours `scan_interval_min`).

| Agent | Module | Job | Fails loud when |
|---|---|---|---|
| **Catalog** | `catalog.py` | Daily: pull every card + variant in the six sets from tcgcsv (TCGplayer data) and store prices with history | prices older than 3 days |
| **FX** | `fx.py` | Daily: ECB rates via Frankfurter (USD base) | rates older than 3 days |
| **Scouts** | `scouts/*.py` | Search each marketplace × ship-to destination, newest first; one interface so new markets plug in | auth fails, errors, zero results 3 runs running |
| **Matcher** | `match.py` | Title → exact catalog card + variant + grade + condition + red flags, with a confidence | — |
| **Valuer** | `value.py` | Card → value (Collectr override > TCGplayer market), condition-adjusted, with source label | — |
| **Landed** | `landed.py` | Listing → USD landed cost per destination | — |
| **Decider** | `decide.py` | Tier each listing: DEAL (push) / LISTED (push, no value) / WATCH / SEEN / REJECT, with the reason | — |
| **Notifier** | `notify.py` | ntfy push with tap-to-dashboard + Open listing button; hourly cap; dedupe; price-drop re-push | push fails |
| **Watchdog** | `watchdog.py` | Health of every agent, API budget, daily digest; pushes system alerts with cooldowns | — |

## Decision rules (defaults, all editable)

- **DEAL**: confidence high/medium, raw, no red flags, value ≥ target `min_value_usd`, landed ≤ value × (1 − `push_gap_pct`). Default push gap 20%: an eBay resale nets roughly 85% of sale price after fees, so 20% under is where a flip starts to pay.
- **LISTED**: matched target card with no market value anywhere (thin, high-end cards). Pushed so Ben sees it, labelled "value unknown".
- **WATCH**: within `watch_gap_pct` of value. Dashboard only.
- **REJECT**: lot, proxy/custom/reprint, Japanese, wrong variant, graded (until graded values exist), seller under min feedback. Dashboard shows why.
- **Condition discount** on value when the title says so: NM 1.0, LP 0.8, MP 0.6, HP 0.4, damaged 0.25, not stated 0.85.
- **Ambiguity is conservative**: when variant is unclear we value at the lower variant and never push low-confidence matches.
- **Seeding**: the first time a market is scanned, everything already listed is stored without pushing; one summary push says how many deals are waiting on the dashboard.
- **Caps**: at most `max_pushes_per_hour`; the overflow becomes one "N more on dashboard" push.

## Markets

Global eBay through one official API (Browse): US, Canada, UK, Australia, Germany, each searched with a ship-to
destination so only listings that can reach Canada or NYC appear. Budget: eBay's default Browse limit
(5,000 calls/day) is enforced by the run; the plan is targets × marketplace-destination pairs per cycle.

Not automated, and why: TCGplayer (API closed to new developers), Cardmarket (API for registered sellers only),
Facebook Marketplace / Kijiji / Mercari (no API; scraping breaks their terms). Collectr (no API) is a manual
value override on the dashboard. Each can become a scout later behind the same interface if access appears.

## Done criteria

1. With eBay keys in `.env`, one cycle searches every target on every configured marketplace-destination pair and stores results.
2. A known listing title for each target matches the right card and variant (tests in `tests/`).
3. A listing under threshold produces exactly one ntfy push with value, landed cost, gap, source; tapping opens its dashboard row.
4. First scan of a market pushes one summary, not hundreds of alerts.
5. The dashboard shows deals, the full feed with reject reasons, per-target thresholds (editable), card values with a Collectr override field, and agent health.
6. Killing the eBay keys or the price feed produces a system push within one cycle, not silence.
7. `python3 -m unittest` passes offline.

## Open decisions (owner: Judy/Ben)

- Canadian province for tax (default Ontario HST 13%).
- Whether graded cards should alert (needs graded values; Collectr has them, TCGplayer does not).
- Whether to automate Collectr values (no API; would mean using their private app endpoints, against their terms).
