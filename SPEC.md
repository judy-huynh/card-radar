# Card Radar — Spec

## End goal

Ben never searches for these cards by hand again. When one of the six targets is listed for sale anywhere we can see,
Ben's phone buzzes (ntfy). By default every new listing pushes, whatever the price (Judy, 2026-10-28); a dashboard
switch narrows it to deals only. Each push carries:

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
| **Grader** | `grading.py` | Raw listing → likely PSA range (low–high) with its source: a photo check if one was done, else the seller's eBay "Card Condition" pick | — |
| **Valuer** | `value.py` | Card → value (Collectr override > TCGplayer market), condition-adjusted, with source label | — |
| **Landed** | `landed.py` | Listing → USD landed cost per destination | — |
| **Decider** | `decide.py` | Tier each listing: DEAL (push) / LISTED (push, no value) / WATCH / SEEN / REJECT, with the reason | — |
| **Notifier** | `notify.py` | ntfy push with tap-to-dashboard + Open listing button; hourly cap; dedupe; price-drop re-push | push fails |
| **Watchdog** | `watchdog.py` | Health of every agent, API budget, daily digest; pushes system alerts with cooldowns | — |

## Decision rules (defaults, all editable)

- **DEAL**: confidence high/medium, raw, no red flags, value ≥ target `min_value_usd`, landed ≤ value × (1 − `push_gap_pct`). Default push gap 20%: an eBay resale nets roughly 85% of sale price after fees, so 20% under is where a flip starts to pay.
- **LISTED**: matched target card with no market value anywhere (thin, high-end cards), labelled "value unknown". With
  `push_every_listing` on (the default), every genuine target listing that isn't a DEAL is LISTED too and pushes, with its
  gap in the title. Thresholds then only decide which pushes say DEAL. REJECTs (lots, fakes, Japanese, other cards, weak
  sellers) and TCGplayer's daily cheapest-copy feed never push.
- **WATCH**: within `watch_gap_pct` of value. Dashboard only.
- **REJECT**: lot, proxy/custom/reprint, Japanese, wrong variant, graded (until graded values exist), seller under min feedback. Dashboard shows why.
- **Condition discount** on value when the title says so: NM 1.0, LP 0.8, MP 0.6, HP 0.4, damaged 0.25, not stated 0.85.
  The seller's eBay "Card Condition" pick counts too; when it and the title disagree, the worse one wins.
- **Grade range** (Judy, 2026-10-31), so a deal can be checked against Collectr's price for that grade:
  - Before a raw eBay listing pushes, its details are fetched once to read the seller's "Card Condition".
  - That condition maps to a likely PSA range (`grade_from_condition` in settings: NM 7–8, LP 5–6, MP 3–4, HP 1–2).
  - A photo check (Claude looks at the listing photos, written with `tools/grade.py`) replaces the seller's range.
  - The Deals page shows the range and its source under the condition. Open / Pass / Bought stay manual.
  - Until grade values exist (see Values by grade), the range is shown but doesn't change the value.
- **Ambiguity is conservative**: when variant is unclear we value at the lower variant and never push low-confidence matches.
- **Seeding**: the first time a market is scanned, everything already listed is stored without pushing; one summary push says how many deals are waiting on the dashboard.
- **Caps**: at most `max_pushes_per_hour`; the overflow becomes one "N more on dashboard" push.
- **Sold or ended listings** (Judy, 2026-10-31; a Dark Gengar sold on Oct 26 still came back in search on Oct 30):
  - eBay's search can return listings that already sold, so search alone never proves a listing is for sale.
  - Just before a push, the listing's own record is read (the same lookup as the seller's condition). Sold, out of
    stock or ended means no push; it goes straight to History as "gone" with the reason.
  - Every `recheck_open_min` minutes (default 60) each open Deals listing is looked up again; sold or ended ones move to
    History as "gone". The recheck stays inside the daily eBay budget.
  - Dropping out of search results proves nothing (each search returns only the newest 200), so it isn't used.

## Markets

| Market | How we watch it | Pushes? |
|---|---|---|
| eBay US, CA, UK, AU, DE | Browse API, newest first, ship-to Ontario and NYC | yes |
| TCGplayer | lowest current listing per card, from the daily tcgcsv feed (no TCGplayer API needed) | no: dashboard leads only, because the cheapest copy is usually played |

Researched 2026-10-28 and not automated:
- **TCGplayer listings**: API closed to new developers. Covered indirectly by the lowest-price feed above.
- **Collectr marketplace**: shows eBay + TCGplayer listings, which we already cover.
- **Facebook Marketplace, Kijiji, Mercari, Instagram, Discord groups**: no API; scraping breaks their terms.
- **Whatnot**: live-stream auctions, nothing to poll.
- **Fanatics Collect / PWCC, Goldin, Heritage**: high-end graded auctions; candidates if graded alerts are switched on.
- **Canadian Shopify card shops** (e.g. Face to Face, Top Shelf): public search works, but none stocked these sets when checked.
- **Reddit r/pkmntcgtrades**: possible later with a free Reddit API key; prices are in post bodies, so alerts would be "listed", not valued.

## Values

Collectr is the value of record wherever Ben has entered it. TCGplayer market fills every card without one. Collectr's
terms forbid crawling, scraping or caching its content and reverse-engineering its app. Its API is by application only
(getcollectr.com/api; personal use allowed, "Powered by Collectr." required); we haven't applied, so its numbers are
never pulled automatically.

### Values by grade (Judy, 2026-10-31)

Collectr prices a card per grade, so a value is stored per **card × grade**: Raw, PSA 6, PSA 7, PSA 8, PSA 9, PSA 10.
Each value carries its source (Collectr, Ours, PriceCharting) and the date it was checked.

- **Where they're typed: the shared Google Sheet** "Card Radar · Collectr values by grade" (Judy's Drive, shared with Ben).
  - Tab **Collectr** (live since 2026-10-31): one row per target card; Ben fills the grade columns and "Checked on".
  - The two tabs below are added once Claude has the Google Sheets connector (Drive alone can't add tabs).
  - Tab **Our prices**: same rows; our own price per grade (what we'd pay or sell at), when we have one.
  - Tab **Deals to check**: the current deals worth a Collectr lookup, with the photo grade range for each.
  - A Card ID column ties every row to exactly one catalog card, so nothing is matched by guesswork.
- **How Card Radar reads them:** each tab is published to the web as CSV (File → Share → Publish to web). The CSV
  links live in `.env`, never in the repo. Card Radar fetches them hourly into a `grade_values` table and re-scores
  open listings. A sheet that can't be read fails loud (watchdog), and the last good values stay in use.
- **Which value a listing uses:** Collectr > Ours > TCGplayer, for the grade that applies:
  - a graded slab uses the value for its grade (this lets slabs become DEALs);
  - a raw card uses Raw, with the condition discount; when a photo grade range exists, the low end of the range.
- The Values page shows the grade values read-only, with a link to the sheet; the sheet is the one place to edit them.

## Done criteria

1. With eBay keys in `.env`, one cycle searches every target on every configured marketplace-destination pair and stores results.
2. A known listing title for each target matches the right card and variant (tests in `tests/`).
3. A listing under threshold produces exactly one ntfy push with value, landed cost, gap, source; tapping opens its dashboard row.
4. First scan of a market pushes one summary, not hundreds of alerts.
5. The dashboard shows deals, the full feed with reject reasons, per-target thresholds (editable), card values with a Collectr override field, and agent health.
6. Killing the eBay keys or the price feed produces a system push within one cycle, not silence.
7. `python3 -m unittest` passes offline.

## Decisions

- 2026-10-28: destinations are Ontario (HST 13%) and New York City (8.875%).
- 2026-10-28: Collectr values are preferred; entered by hand or pasted, never scraped (see Values).

- 2026-10-28: Ben is told about every listing of the six cards, not just deals (`push_every_listing`, switchable in Settings).
- 2026-10-31: values are stored per grade and typed in the shared Google Sheet, not on the dashboard (see Values by grade).

## Open decisions (owner: Judy/Ben)

- Graded cards push as LISTED while `push_every_listing` is on. Once the sheet has grade values they can count as DEALs
  (see Values by grade); until then they stay LISTED.
