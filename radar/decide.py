"""Decider agent. One listing -> tier + human-readable reason. Order of checks = order of importance.

DEAL    push: confident raw match, clean seller, landed at least push_gap_pct under value
LISTED  push: confident target match with no market value anywhere (thin high-end card)
WATCH   dashboard: close to value, or a good price we can't fully trust (low confidence, auction, graded)
SEEN    dashboard feed: a real target listing at or above market
REJECT  dashboard feed: not what we want, with the reason
"""
RANK = {"REJECT": 0, "SEEN": 1, "WATCH": 2, "LISTED": 3, "DEAL": 4}
PUSH_TIERS = ("DEAL", "LISTED")


def decide(listing, m, value, landed_usd, target, settings):
    rules = settings["decide"]
    if m["flags"]:
        return "REJECT", " · ".join(m["flags"])
    if not m["card"]:
        return "REJECT", m["reason"] or "no card match"
    card = m["card"]
    if card.get("target_id") != target["id"]:
        return "REJECT", m["reason"] or f"not a target: {card['name']} {card['number']} {card['subtype']}"
    fb, pct = listing.get("feedback"), listing.get("feedback_pct")
    if fb is not None and fb < rules["min_seller_feedback"]:
        return "REJECT", f"seller has {fb} feedback"
    if pct is not None and pct < rules["min_seller_pct"]:
        return "REJECT", f"seller {pct}% positive"
    if landed_usd is not None and landed_usd > target["max_price_usd"]:
        return "SEEN", f"over your max (US${target['max_price_usd']:,})"

    gap = None if (value is None or landed_usd is None) else (landed_usd / value - 1) * 100
    cap = None   # the highest tier this listing may reach, with why
    if m["confidence"] == "low":
        cap = ("WATCH", "unsure match: " + (m["reason"] or "check the listing"))
    elif m["grade"] and not rules["push_graded"]:
        cap = ("WATCH", f"graded {m['grade']}: compare to graded value yourself")
    elif listing.get("source") == "tcgplayer" and not rules.get("push_tcgplayer_lows"):
        cap = ("WATCH", "cheapest copy · condition unknown")
    elif "AUCTION" in (listing.get("buying") or "") and "FIXED_PRICE" not in (listing.get("buying") or "") and not rules["push_auctions"]:
        cap = ("WATCH", "auction: current bid, not final price")

    if value is None:
        tier, reason = ("LISTED" if rules["push_unvalued"] else "WATCH"), "no market value: add the Collectr value"
    elif value < target["min_value_usd"]:
        return "SEEN", f"card worth under US${target['min_value_usd']}"
    elif gap <= -target["push_gap_pct"]:
        tier, reason = "DEAL", f"{gap:.0f}% vs value"
    elif gap <= -target["watch_gap_pct"]:
        tier, reason = "WATCH", f"{gap:.0f}% vs value"
    else:
        return "SEEN", f"{gap:+.0f}% vs value"
    if cap and RANK[tier] > RANK[cap[0]]:
        return cap
    return tier, reason
