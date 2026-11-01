"""Evaluate one listing end to end: match -> value -> landed -> decide. Used by the scan and by the
dashboard (when a Collectr value or threshold changes, open listings are re-scored without a new scan)."""
import json
from . import db, decide, grading, landed, match, value


def cards_for(con, group_id):
    return db.rows(con, "SELECT * FROM cards WHERE group_id=?", (group_id,))


def evaluate(con, listing, target, cards, rates, settings):
    m = match.match(listing["title"], listing.get("condition_raw"), target, cards)
    pinned = listing.get("pinned_card_key")
    if pinned:   # the source already knows the exact card (TCGplayer): trust it over title parsing
        card = next((c for c in cards if c["card_key"] == pinned), None)
        if card:
            m.update(card=card, card_key=pinned, confidence="high", reason=None)
    g = grading.get(con, listing["item_id"])
    if g and not m["grade"]:   # the seller's eBay "Card Condition" pick; when it and the title disagree, the worse wins
        m["condition"] = grading.worse(m["condition"], g["seller_condition"])
    base, source = value.base_value(con, m["card"])
    if m["grade"]:   # a slab's value is not the raw card's value; we have no graded values, so don't pretend
        base, source = None, None
    val = value.adjusted(base, m["condition"], settings["condition_multipliers"])
    quotes = db.rows(con, "SELECT * FROM quotes WHERE item_id=?", (listing["item_id"],))
    per_dest, best = landed.landed(listing, quotes, settings["destinations"], rates)
    landed_usd = per_dest[best]["usd"] if best else None
    tier, reason = decide.decide(listing, m, val, landed_usd, target, settings)
    needs = None
    if decide.filtering(settings) and listing.get("source") != "tcgplayer":
        # would it be a DEAL if the seller says near mint? Only then is the seller's pick worth a lookup
        nm_tier = tier
        if not (g and g.get("seller_checked_at")) and m["condition"] is None:
            nm_tier, _ = decide.decide(listing, dict(m, condition="NM"),
                                       value.adjusted(base, "NM", settings["condition_multipliers"]), landed_usd, target, settings)
        tier, reason, needs = decide.condition_gate(tier, reason, m, g, nm_tier, settings)
    buying = listing.get("buying") or ""
    auction_only = "AUCTION" in buying and "FIXED_PRICE" not in buying   # price is the current bid, not the final price
    gap = None if (val is None or landed_usd is None or auction_only) else round((landed_usd / val - 1) * 100, 1)
    return {"card_key": m["card_key"], "confidence": m["confidence"], "variant": m["variant"], "grade": m["grade"],
            "flags": json.dumps(m["flags"]), "condition": m["condition"],
            "value_usd": None if val is None else round(val, 2), "value_source": source,
            "landed": json.dumps(per_dest), "best_dest": best, "landed_usd": landed_usd, "gap_pct": gap,
            "flip_usd": None if gap is None else flip(val, landed_usd, settings),
            "tier": tier, "reason": reason, "_needs": needs}


def flip(value_usd, landed_usd, settings):
    """Profit if our partner sells it live on Whatnot: their share of value, less Whatnot's fees, less what we paid."""
    w = settings.get("whatnot")
    if not w:
        return None
    sale = value_usd * w["realize_pct"] / 100
    return round(sale * (1 - (w["commission_pct"] + w["processing_pct"]) / 100) - w["processing_fixed_usd"] - landed_usd, 2)


def save(con, listing, result):
    fields = dict(listing, **result)
    cols = ["item_id", "source", "marketplace", "target_id", "title", "url", "image", "price", "currency", "buying",
            "seller", "feedback", "feedback_pct", "item_country", "item_location", "created", "ends", "condition_raw",
            "card_key", "confidence", "variant", "grade", "flags", "condition", "value_usd", "value_source",
            "landed", "best_dest", "landed_usd", "gap_pct", "flip_usd", "tier", "reason"]
    vals = [fields.get(c) for c in cols]
    stamp = db.now()
    con.execute(f"""INSERT INTO listings({",".join(cols)}, first_seen, last_seen, first_price)
                    VALUES({",".join("?" * len(cols))}, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET {", ".join(f"{c}=excluded.{c}" for c in cols[1:])},
                    last_seen=excluded.last_seen""", vals + [stamp, stamp, listing["price"]])


def rescore(con, targets, rates, settings, where="tier IN ('DEAL','LISTED','WATCH')", args=()):
    """Re-evaluate stored listings (no pushes). Returns count."""
    by_id = {t["id"]: t for t in targets}
    cache, n = {}, 0
    for l in db.rows(con, f"SELECT * FROM listings WHERE {where}", args):
        t = by_id.get(l["target_id"])
        if not t:
            continue
        cards = cache.setdefault(t["group_id"], cards_for(con, t["group_id"]))
        res = {k: v for k, v in evaluate(con, l, t, cards, rates, settings).items() if not k.startswith("_")}
        con.execute(f"UPDATE listings SET {', '.join(f'{k}=?' for k in res)} WHERE item_id=?", list(res.values()) + [l["item_id"]])
        n += 1
    con.commit()
    return n
