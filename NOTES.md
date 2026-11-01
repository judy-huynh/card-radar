# Card Radar — project notes

Running notes for Judy, Ben and Claude: where things stand, what was decided, what's next.
`SPEC.md` is the contract (what the system must do); this file is the diary. Newest first.
This repo is public, so never write keys, the ntfy topic or the Tailscale address here.

## Next steps (in order)

0. **Condition filter live** (SPEC "Condition filter", 2026-11-01): raw near-mint cards only, photo-checked by Claude,
   at most 5 pushes a day ranked by profit after Whatnot fees. To do:
   - ask our Whatnot partner which price range sells best live and what share of value a card fetches on stream
     (`whatnot.realize_pct`, now 100%);
   - Claude looks up Collectr values for each photo-passed deal in our sessions and records them in the sheet;
   - check the first night's photo checks in the scan log (they run from the background job; tested in the same
     bare environment, not yet from launchd itself).

1. **Phone alerts match the dashboard.** ntfy titles and text use "Potential return" and "★ Match", the same
   words as the dashboard. *(Done 2026-10-30; see log.)*
2. **Confirm alerts arrive.** *(Done 2026-10-30 23:27: the first scan after activation was clean. It found 24 new
   listings, pushed 7 to Ben, and had no sign-in errors.)* Still to check: Ben confirms that tapping an alert opens
   the right row.
3. **Fact-check the listings.** *(Done 2026-10-31; see log.)* Source fixes still to build:
   - ~~read eBay's "Card Condition" field~~ *(done 2026-10-31, with grade ranges)*;
   - ~~read "PL" (Played) as a condition~~ *(done 2026-11-01)*;
   - ~~catch reprints the title hides~~ *(the photo check caught 3 on 2026-11-01: a Celebrations Lugia, a Pikachu-30
     stamped Lugia, an Arceus promo; slabs are out anyway)*; other languages still possible;
   - distrust a TCGplayer value far above its cheapest copy, or Unlimited above 1st Edition;
   - make the "too cheap, check photos" warning compare against a value that isn't itself broken.
4. **Values by grade in the shared sheet** (SPEC "Values by grade"). Needs the Google Sheets connector on in Claude
   to restructure the sheet (tabs Collectr / Our prices / Deals to check). Then Judy publishes the tabs to the web as
   CSV, the links go in `.env`, and Card Radar reads them hourly.
5. **Share the sheet with Ben** (editor). Waiting on his email or Judy sharing it herself.

## Open questions

- **Southern Islands:** Judy's original list said "Southern Islands *Reverse Holo*". The target currently includes
  the plain (non-holo) versions too. Narrow it to reverse holo only?
- **Whatnot:** which price range sells best live, and what share of value does a card fetch on stream?
- **Collectr values:** TCGplayer's market price looks high for some cards (Dark Gengar at $1,064; Geodude 77/110 at
  $444, while the cheapest copy is $94). Ben's Collectr numbers on the Values page fix this.

## How to…

- **See the dashboard:** open the Tailscale link on any device signed into the same Tailscale account.
- **If a change doesn't show:** press Cmd + Shift + R to force the browser to load a fresh copy.
- **Change what buzzes Ben's phone:** Settings explains the rule; the push gap per set is editable there. The daily
  limit, condition and photo rules live in `config/settings.json` (`condition_filter`, `notify.max_pushes_per_day`).
- **Catch up on photo checks now:** `python3 -m radar photos 10` (never pushes; stays inside the eBay budget).
- **Fix a value:** go to Values, pick the set, and type the Collectr number. Every gap recalculates straight away.

## Log

### 2026-11-01
- **Searches stopped at 11:35 am (and 8 pm–midnight on Oct 31).** The hourly "still for sale?" recheck looked up all
  522 open deals one by one and used the whole 5,000-call day. Fixed: lookups only spend what's left after reserving
  every remaining search of the day, and the recheck checks at most 40 deals an hour, longest-unchecked first.
- **Condition filter (Judy: the edge is ungraded cards in great condition, flipped live on Whatnot).** Now:
  - graded slabs are rejected; the seller must call the card near mint (title and eBay "Card Condition", worse wins);
  - a raw listing that would be a deal at near mint gets one eBay lookup (seller pick + photos + still for sale);
  - near-mint ones get a photo check: Claude Code on the iMac (the subscription, not a separate bill) looks at up to
    8 photos and answers fixed questions; our rule fails a crease, bend, heavy back-corner whitening or the wrong
    card, and calls doubt "unsure". It runs restricted (Read only, inside a throwaway photo folder, no connectors);
  - only photo-passed deals push, best profit after Whatnot fees first (8% + 2.9% + $0.30), at most 5 a day;
  - Deals, pushes and Settings say so; History shows "Passed: rules" with the reason.
- **First real photo checks:** 3 of the 3 near-mint under-value listings were reprints or the wrong card (a
  Celebrations Lugia, a Pikachu-30 stamped Lugia, an Arceus promo). Two more had sold or ended.
- **Deals re-sorted** (`tools/resort.py`): the 522 open deals were moved to History as "Passed: doesn't meet condition
  rules" with the reason (graded, played, photo check). Nothing deleted. The Deals page starts empty; new deals arrive
  as scans find raw near-mint cards that pass.
- Also: "PL" reads as played, "AOG" as a grading company.

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
