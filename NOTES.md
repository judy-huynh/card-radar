# Card Radar — project notes

Running notes for Judy, Ben and Claude: where things stand, what was decided, what's next.
`SPEC.md` is the contract (what the system must do); this file is the diary. Newest first.
This repo is public, so never write keys, the ntfy topic or the Tailscale address here.

## Next steps (in order)

1. **Phone alerts match the dashboard.** ntfy titles and text use "Potential return" and "★ Match", the same
   words as the dashboard. *(Done 2026-10-30; see log.)*
2. **Confirm alerts arrive.** Make sure the next scans push new listings to Ben, and that tapping an alert opens the
   right row on the dashboard.
3. **Fact-check the listings.** Judy will ask for this. Go through the current deals and check that each one is
   the right card, has the right value, has the right landed cost and a believable condition. Fix what's wrong at
   the source (matcher, value, landed), not row by row.

## Open questions

- **Southern Islands:** Judy's original list said "Southern Islands *Reverse Holo*". The target currently includes
  the plain (non-holo) versions too. Narrow it to reverse holo only?
- **Graded slabs:** they push as "LISTED" with no return, because we have no graded values. Keep pushing them, or
  only push raw cards?
- **Collectr values:** TCGplayer's market price looks high for some cards (Dark Gengar at $1,064; Geodude 77/110 at
  $444, while the cheapest copy is $94). Ben's Collectr numbers on the Values page fix this.

## How to…

- **See the dashboard:** open the Tailscale link on any device signed into the same Tailscale account.
- **If a change doesn't show:** press Cmd + Shift + R to force the browser to load a fresh copy.
- **Change what buzzes Ben's phone:** go to Settings, then "What buzzes Ben's phone" (every new listing, or deals only).
- **Fix a value:** go to Values, pick the set, and type the Collectr number. Every gap recalculates straight away.

## Log

### 2026-10-30
- **eBay is live.** The developer account is on Judy's real eBay account. The production keys needed the
  "Marketplace Account Deletion" **exemption** (a toggle on the Alerts & Notifications page). To qualify honestly,
  Card Radar stopped storing seller usernames. For about an hour after activation, eBay sign-in kept failing
  randomly. Sign-in now retries twice before reporting a failure.
- **First scan** found 3,342 listings across eBay US, CA, UK, AU and DE. They were saved without pushing, so day
  one didn't buzz hundreds of times. After that: 25 deals, about 1,000 listings, and about 2,250 rejected (mostly
  Japanese or non-English, lots, or another card).
- **Junk found by that scan, now rejected:**
  - credit-card skins and "altered" art
  - 2026 "30th Celebration" Lugia 149/147 reprints
  - "Old Back" Japanese cards
  - German titles that say Italian
- **Condition fixes:** "Lightly Played" now reads as light play (it was reading as moderate). German condition
  words are understood. "Read description" now reads as heavy play.
- **No fake returns:**
  - Graded slabs and auction bids no longer get a return against the raw-card value.
  - Unsure matches stay on the dashboard instead of pushing.
  - A deal under half TCGplayer's cheapest copy shows "check photos".
- **Dashboard:**
  - "Potential return" (value − landed, in $ and %) replaces "gap".
  - Matching rows get a green "★ Match · target" label.
  - Every column sorts, starting at the highest return; the sorted column is tinted.
  - New modern look: white cards on light grey, pill tabs, a status dot.
  - Card photos were tried and removed (too much space).
- **Working agreement (Judy):** a question is a question. Answer it, and only change what she asks for. Keep the
  dashboard easy for a first-time user.

### 2026-10-29
- eBay rejected the first developer registration (personal email). A dashboard "check this listing" idea was parked.
- Leads explained: TCGplayer cheapest-copy rows never push (the condition is unknown, usually played).

### 2026-10-28
- Project started.
  - **Targets:** LC reverse holo, Southern Islands, Skyridge holo, Aquapolis holo, Dark Gengar, Expedition holo.
  - **Alerts:** ntfy to Ben's phone.
  - **Destinations:** Ontario (13% HST) and NYC (8.875%).
  - **Values:** Collectr values entered by hand (Collectr forbids scraping), TCGplayer as fallback.
- Every new listing of the six pushes, not just deals (setting `push_every_listing`).
- Dashboard v3: four views (Deals, Leads, Values, Settings), lists split into pages.
