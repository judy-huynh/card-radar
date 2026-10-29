"""Catalog agent. Pulls every card and variant in the target sets from tcgcsv.com (a daily mirror of
TCGplayer's catalog and prices) and keeps a price history. TCGplayer market is the main source Collectr
prices English singles from; Ben's own Collectr numbers live in `overrides` and always win."""
import json, urllib.request
from . import db
from .text import clean_name, norm, split_number

BASE = "https://tcgcsv.com/tcgplayer/3"   # category 3 = Pokémon
UA = {"User-Agent": "card-radar/1.0 (personal sourcing tool)"}


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["results"]


def target_for(targets, group_id, subtype, name, rarity=None):
    for t in targets:
        if t["group_id"] != group_id:
            continue
        crystal = t.get("crystal_any_subtype") and rarity == "Secret Rare"   # TCGplayer files crystals under either foil label
        if subtype not in t["subtypes"] and not crystal:
            continue
        if t.get("name") and clean_name(name).lower() != t["name"].lower():
            continue
        return t["id"]
    return None


def refresh(con, targets, fetch=_get):
    """Refresh all target sets. Returns number of card-variants stored."""
    stamp, day, n = db.now(), db.today(), 0
    for group in sorted({t["group_id"] for t in targets}):
        products = {p["productId"]: p for p in fetch(f"{BASE}/{group}/products")}
        set_name = next((t["set_name"] for t in targets if t["group_id"] == group), "")
        for r in fetch(f"{BASE}/{group}/prices"):
            p = products.get(r["productId"])
            if not p:
                continue
            ext = {e["name"]: e["value"] for e in p.get("extendedData", [])}
            number = ext.get("Number")
            if not number:            # sealed product, not a single
                continue
            num, denom = split_number(number)
            name = clean_name(p["name"])
            key = f"{group}:{p['productId']}:{r['subTypeName']}"
            con.execute("""INSERT INTO cards(card_key, target_id, group_id, product_id, set_name, name, name_norm, number,
                             num_norm, denom, subtype, rarity, tcg_url, image_url, market, low, mid, updated)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(card_key) DO UPDATE SET target_id=excluded.target_id, market=excluded.market,
                             low=excluded.low, mid=excluded.mid, updated=excluded.updated, name=excluded.name,
                             name_norm=excluded.name_norm, number=excluded.number, num_norm=excluded.num_norm,
                             denom=excluded.denom, rarity=excluded.rarity, image_url=excluded.image_url""",
                        (key, target_for(targets, group, r["subTypeName"], name, ext.get("Rarity")), group, p["productId"], set_name,
                         name, norm(name), number, num, denom, r["subTypeName"], ext.get("Rarity"),
                         p.get("url"), p.get("imageUrl"), r.get("marketPrice"), r.get("lowPrice"), r.get("midPrice"), stamp))
            con.execute("INSERT OR REPLACE INTO value_history(card_key, day, market, low) VALUES(?,?,?,?)",
                        (key, day, r.get("marketPrice"), r.get("lowPrice")))
            n += 1
    con.commit()
    return n


def age_hours(con):
    r = db.one(con, "SELECT MIN(updated) u FROM cards WHERE target_id IS NOT NULL")
    return _hours_since(r["u"]) if r and r["u"] else None


def _hours_since(ts):
    import time
    return (time.time() - time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S"))) / 3600
