"""Valuer agent. Card -> value in USD with its source. Ben's Collectr override always wins over TCGplayer."""
from . import db


def base_value(con, card):
    if not card:
        return None, None
    o = db.one(con, "SELECT value_usd, source FROM overrides WHERE card_key=?", (card["card_key"],))
    if o and o["value_usd"] is not None:
        return float(o["value_usd"]), o["source"] or "Collectr"
    if card.get("market") is not None:
        return float(card["market"]), "TCGplayer"
    return None, None


def adjusted(value, condition, multipliers):
    if value is None:
        return None
    return value * multipliers.get(condition or "unknown", multipliers.get("unknown", 1.0))
