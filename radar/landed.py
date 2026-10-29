"""Landed-cost agent. Listing + per-destination shipping quotes -> USD cost delivered to each destination.

landed = (ask + shipping) in USD x (1 + sales tax) x (1 + import estimate if it crosses a border)
All rates are estimates from config/settings.json and are labelled as such on the dashboard."""
from .fx import to_usd


def landed(listing, quotes, destinations, rates):
    out = {}
    for q in quotes:
        d = destinations.get(q["dest"])
        if not d or not q.get("ships", 1):
            continue
        intl = (listing.get("item_country") or "").upper() not in ("", d["country"])
        if q.get("ship") is not None:
            ship_usd, estimated = to_usd(q["ship"], q.get("ship_currency") or listing["currency"], rates), False
        else:
            ship_usd, estimated = float(d["default_ship_usd"]["international" if intl else "domestic"]), True
        base = to_usd(listing["price"], listing["currency"], rates) + ship_usd
        total = base * (1 + d["tax_pct"] / 100) * (1 + (d["intl_extra_pct"] / 100 if intl else 0))
        out[q["dest"]] = {"usd": round(total, 2), "ship_usd": round(ship_usd, 2), "ship_estimated": estimated,
                          "international": intl, "ask_usd": round(to_usd(listing["price"], listing["currency"], rates), 2)}
    best = min(out, key=lambda k: out[k]["usd"]) if out else None
    return out, best
