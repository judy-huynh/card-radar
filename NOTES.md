# Card Radar — project notes

Running notes for Judy, Ben and Claude: where things stand, what was decided, what's next.
`SPEC.md` is the contract (what the system must do); this file is the diary. Newest first.
This repo is public, so never write keys, the ntfy topic or the Tailscale address here.

## Next steps (in order)

1. **Phone alerts match the dashboard.** ntfy titles and text use "Potential return" and "★ Match", the same
   words as the dashboard. *(Done 2026-10-30; see log.)*
2. **Confirm alerts arrive.** *(Done 2026-10-30 23:27: the first scan after activation was clean. It found 24 new
   listings, pushed 7 to Ben, and had no sign-in errors.)* Still to check: Ben confirms that tapping an alert opens
   the right row.
3. **Fact-check the listings.** *(Done 2026-10-31; see log.)* Source fixes still to build:
   - ~~read eBay's "Card Condition" field~~ *(done 2026-10-31, with grade ranges)*;
   - read "PL" (Played) as a condition;
   - catch reprints and other languages the title hides (a 2026 "Stamped" Lugia 149/147 TAG 10 slab still lists);
   - distrust a TCGplayer value far above its cheapest copy, or Unlimited above 1st Edition;
   - make the "too cheap, check photos" warning compare against a value that isn't itself broken.
4. **Values by grade in the shared sheet** (SPEC "Values by grade"). Needs the Google Sheets connector on in Claude
   to restructure the sheet (tabs Collectr / Our prices / Deals to check). Then Judy publishes the tabs to the web as
   CSV, the links go in `.env`, and Card Radar reads them hourly.
5. **Share the sheet with Ben** (editor). Waiting on his email or Judy sharing it herself.

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

### 2026-10-31
- **Sold listings were showing as deals.** The Dark Gengar that buzzed Ben as a DEAL had sold on Oct 26; eBay's
  search still returned it on Oct 30. A Lugia PSA 6 sold tonight and stayed on Deals. Now:
  - just before a push, the listing's own record is checked; sold or ended means no push, straight to History;
  - every hour each open deal is looked up again (`recheck_open_min`); sold or ended ones move to History as "Gone";
  - `python3 -m radar recheck` runs it on demand. Both sold listings are now in History.
  - Not used: "dropped out of search". Each search returns only the newest 200, so older listings vanish while for sale.
- **Grade ranges on deals.** Each raw deal shows a likely PSA range under its condition, with its source:
  - the seller's eBay "Card Condition" pick (fetched once, just before a listing buzzes Ben), or
  - a photo check, recorded with `python3 tools/grade.py photo ITEM LOW HIGH "note"`, which wins.
  - The seller's pick also lowers the value when it's worse than the title. Phone alerts carry the range.
  - Open / Pass / Bought were already on the Deals page; they stay manual.
- **Deals cleaned up.** The 19 deals dropped by the photo check are marked passed, each with its reason (History).
  Three of the 7 keepers left the Deals page: the seller's own condition put them under the deal line, and listings
  seeded on day one only show on Deals while they're DEALs. They're in Leads.
- **Fact-check of the 26 deals.** Landed-cost maths is right. The values were the problem:
  - TCGplayer's market price is too high on thin cards. Dark Gengar Unlimited shows $1,064, above 1st Edition's
    $1,000; PriceCharting raw is about $375. Geodude LC reverse shows $444; raw is about $129.
- **Photo check of every deal.** 5 of 26 were the wrong card, which only the photos showed:
  - Alakazam LC "reverse" was the regular holo;
  - the Lugia crystal was the 2026 30th-anniversary reprint;
  - two "Dark Gengars" were Japanese and one was Italian.
- **Seller condition was ignored.** eBay's "Card Condition" field marked 7 "not stated" deals as moderately or
  heavily played.
- **Result:** 7 deals worth a Collectr check (5 Dark Gengar, Articuno, Marill). 19 dropped (wrong card, damaged, or
  priced at or above raw value).
- **Collectr API exists, by application only.** Judy chose the manual route for now.
- **Values by grade:** Collectr prices per PSA grade, so values will be stored per card × grade and typed in the shared
  Google Sheet (SPEC updated). Sheet created 2026-10-30 in Judy's Drive; 218 cards, 19 marked priority 1.

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
