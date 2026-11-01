"""Decider agent. One listing -> tier + human-readable reason. Order of checks = order of importance.

DEAL    push: confident raw match, clean seller, landed at least push_gap_pct under value
LISTED  push: confident target match with no market value anywhere (thin high-end card), or, with
        push_every_listing on, any genuine target listing that isn't a DEAL (the reason keeps the gap)
WATCH   dashboard: close to value, or a good price we can't fully trust (low confidence, auction, graded)
SEEN    dashboard feed: a real target listing at or above market
REJECT  dashboard feed: not what we want, with the reason
"""
RANK = {"REJECT": 0, "SEEN": 1, "WATCH": 2, "LISTED": 3, "DEAL": 4}
PUSH_TIERS = ("DEAL", "LISTED")
COND_WORDS = {"NM": "near mint", "LP": "lightly played", "MP": "moderately played", "HP": "heavily played", "DMG": "damaged"}


def filtering(settings):
    return bool(settings.get("condition_filter", {}).get("enabled"))


def push_tiers(settings):
    """With the condition filter on, only photo-passed DEALs ever push (SPEC "Condition filter")."""
    return ("DEAL",) if filtering(settings) else PUSH_TIERS


def decide(listing, m, value, landed_usd, target, settings):
    tier, reason = _tier(listing, m, value, landed_usd, target, settings)
    # Judy 2026-10-28: Ben hears about every listing of the six cards, not just deals. Junk (REJECT) and
    # TCGplayer's daily cheapest-copy feed (not a new listing) still never push.
    # Unsure matches (e.g. no set named, could be another /110 set) stay on the dashboard.
    if (settings["decide"].get("push_every_listing") and not filtering(settings) and tier in ("SEEN", "WATCH")
            and listing.get("source") != "tcgplayer" and m["confidence"] != "low"):
        return "LISTED", reason
    return tier, reason


def _tier(listing, m, value, landed_usd, target, settings):
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
    if m["grade"] and filtering(settings) and settings["condition_filter"].get("raw_only"):
        return "REJECT", f"graded ({m['grade']}): we buy raw cards only"
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
        cap = ("WATCH", "auction: price is the current bid, not the final price")

    if value is None and m["grade"]:
        return "WATCH", f"graded {m['grade']}: no graded value here, compare on Collectr"
    if value is None:
        tier, reason = ("LISTED" if rules["push_unvalued"] else "WATCH"), "no market value: add the Collectr value"
    elif value < target["min_value_usd"]:
        return "SEEN", f"card worth under US${target['min_value_usd']}"
    elif gap <= -target["push_gap_pct"]:
        tier, reason = "DEAL", f"{gap:.0f}% vs value"
        # far below BOTH TCGplayer's market and its cheapest copy: usually damaged, mislabelled or a scam
        ref = min(x for x in (card.get("low"), card.get("market")) if x) if (card.get("low") or card.get("market")) else None
        if ref and landed_usd < ref * 0.5 and listing.get("source") != "tcgplayer":
            reason += f" · under half TCGplayer's price (US${ref:,.0f}): check photos"
    elif gap <= -target["watch_gap_pct"]:
        tier, reason = "WATCH", f"{gap:.0f}% vs value"
    else:
        return "SEEN", f"{gap:+.0f}% vs value"
    if cap and RANK[tier] > RANK[cap[0]]:
        return cap
    return tier, reason


def condition_gate(tier, reason, m, g, nm_tier, settings):
    """SPEC "Condition filter", steps 2-4, for a raw eBay listing. g = its grades row (seller pick, photo check, gone).
    nm_tier = the tier it would have if it were near mint. Returns (tier, reason, needs): needs is "details" when the
    seller's pick should be read, "photos" when the photos should be checked, else None. Never raises a tier."""
    g = g or {}
    if g.get("gone"):
        return "REJECT", g["gone"], None
    if tier == "REJECT" or m["grade"]:
        return tier, reason, None
    must = settings["condition_filter"]["seller_must_say"]
    cond = m["condition"]
    if cond and cond not in must:
        return "REJECT", f"{COND_WORDS.get(cond, cond)}: we buy near mint only", None
    if not g.get("seller_checked_at"):
        if nm_tier == "DEAL":
            return "WATCH", "checking the seller's condition", "details"
        return ("WATCH" if tier in ("DEAL", "LISTED") else tier), reason, None
    if not g.get("seller_condition"):
        return ("WATCH" if RANK[tier] > RANK["WATCH"] else tier), "seller gave no card condition", None
    if tier == "LISTED":   # no market value: nothing to rank a flip on
        return "WATCH", reason, None
    if tier != "DEAL":
        return tier, reason, None
    verdict = g.get("photo_verdict")
    if verdict == "fail":
        return "REJECT", "photo check: " + (g.get("photo_reason") or "failed"), None
    if verdict == "unsure":
        return "WATCH", "photo check unsure: " + (g.get("photo_reason") or ""), None
    if verdict == "pass":
        return "DEAL", reason + " · photos pass", None
    cfg = settings["condition_filter"]["photo_check"]
    if not cfg.get("enabled"):
        return "WATCH", "photo check is off", None
    if (g.get("photo_attempts") or 0) >= cfg["max_attempts"]:
        return "WATCH", "photo check couldn't run: " + (g.get("photo_error") or "check the photos yourself"), None
    return "WATCH", "waiting for the photo check", "photos"
