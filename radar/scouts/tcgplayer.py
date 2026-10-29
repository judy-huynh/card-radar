"""TCGplayer scout. TCGplayer's listing API is closed to new developers, but the daily tcgcsv mirror that the
Catalog agent already loads includes each card's LOWEST CURRENT LISTING price. When that lowest ask drops well
under market, there is a copy for sale worth looking at. Condition isn't shown (the cheapest copy is often
played), so these are valued with the "not stated" condition discount and labelled clearly.

No API calls of its own: it reads the cards table after each catalog refresh."""
from .. import db

NAME = "tcgplayer"
VARIANT_WORDS = {"Reverse Holofoil": "Reverse Holo", "Holofoil": "Holo", "1st Edition Holofoil": "1st Edition Holo",
                 "Unlimited Holofoil": "Unlimited Holo", "Normal": "Non Holo", "1st Edition": "1st Edition Non Holo",
                 "Unlimited": "Unlimited Non Holo"}


class TcgplayerScout:
    name = NAME

    def __init__(self, con):
        self.con = con

    def plan(self, targets):
        from . import Job
        return [Job(NAME, "TCGPLAYER", "NYC", t, "lowest listing") for t in targets if not t.get("paused")]

    def run(self, job):
        rows = db.rows(self.con, "SELECT * FROM cards WHERE target_id=? AND low IS NOT NULL", (job.target["id"],))
        return [listing_for(c, job) for c in rows]

    def counts_against_budget(self):
        return False

    def finalize(self, con, items):
        """A newer lowest price replaces the old one: retire stale rows so they stop showing as open deals."""
        current = {}
        for it in items.values():
            if it["source"] == NAME:
                current[it["pinned_card_key"]] = it["item_id"]
        for key, item_id in current.items():
            con.execute("""UPDATE listings SET tier='SEEN', reason='no longer the lowest TCGplayer price'
                           WHERE source=? AND card_key=? AND item_id != ? AND tier != 'SEEN'""", (NAME, key, item_id))


def listing_for(c, job):
    return {
        "item_id": f"tcgplayer:{c['card_key']}:{c['low']:.2f}", "source": NAME, "marketplace": "TCGPLAYER",
        "target_id": job.target["id"], "pinned_card_key": c["card_key"],
        "title": f"{c['name']} {c['number']} {c['set_name']} {VARIANT_WORDS.get(c['subtype'], c['subtype'])}",
        "url": c["tcg_url"], "image": c["image_url"], "price": float(c["low"]), "currency": "USD",
        "buying": "FIXED_PRICE", "seller": "lowest TCGplayer listing", "feedback": None, "feedback_pct": None,
        "item_country": "US", "item_location": "TCGplayer (US sellers)", "created": None, "ends": None,
        "condition_raw": None, "dest": "NYC", "ship": None, "ship_currency": None,
    }
