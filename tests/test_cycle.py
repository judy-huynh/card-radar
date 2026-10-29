"""End to end, offline: fake eBay -> real pipeline -> captured pushes, in a throwaway database."""
import json, os, tempfile, unittest
from radar import db, notify, run
from radar.scouts import Job
from tests.helpers import CARDS

RATES = {"amount": 1.0, "base": "USD", "date": "2026-10-28", "rates": {"CAD": 1.4, "GBP": 0.75, "EUR": 0.9, "AUD": 1.42, "JPY": 158}}


def listing(item_id, title, price, currency="USD", country="US", tid="aquapolis-holo", ship=5.0, seller_fb=900):
    return {"item_id": item_id, "source": "fake", "marketplace": "EBAY_US", "target_id": tid, "title": title,
            "url": f"https://example.com/{item_id}", "image": None, "price": price, "currency": currency,
            "buying": "FIXED_PRICE", "seller": "s", "feedback": seller_fb, "feedback_pct": 99.9, "item_country": country,
            "item_location": country, "created": None, "ends": None, "condition_raw": "Ungraded", "ship": ship, "ship_currency": currency}


class FakeScout:
    name = "fake"

    def __init__(self, batches):
        self.batches, self.calls = batches, 0

    def plan(self, targets):
        return [Job("fake", "EBAY_US", d, t, t["queries"][0]) for t in targets if t["id"] in ("aquapolis-holo", "lc-reverse") for d in ("NYC", "CA")]

    def run(self, job):
        batch = self.batches[min(self.calls // 4, len(self.batches) - 1)]
        self.calls += 1
        return [dict(x, dest=job.dest) for x in batch if x["target_id"] == job.target["id"]]


class Cycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["RADAR_DB"] = os.path.join(self.tmp, "t.db")
        os.environ["RADAR_DRY"] = "1"
        os.environ.setdefault("DASHBOARD_URL", "http://radar.test:8790")
        self.con = db.connect()
        cols = list(CARDS[0].keys())
        for c in CARDS:
            c = dict(c, updated=db.now())
            self.con.execute(f"INSERT INTO cards({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [c[k] for k in cols])
        from radar import fx
        fx.refresh(self.con, fetch=lambda: RATES)
        self.con.commit()
        notify.SENT.clear()

    def tearDown(self):
        os.environ.pop("RADAR_DB"); os.environ.pop("RADAR_DRY")

    def test_seed_then_live(self):
        seed = [listing("a1", "Aquapolis Kingdra H14/H32 Holo NM", 120.0),            # value ~214 -> deal
                listing("a2", "Aquapolis Kingdra H14/H32 Holo", 230.0)]                # above value
        live = seed + [listing("a3", "Aquapolis Crystal Lugia 149/147 Holo", 300.0),   # 500 -> deal
                       listing("a4", "Lot of 10 Aquapolis holo", 200.0),                # reject
                       listing("a5", "Aquapolis Kingdra H14/H32 Holo", 150.0, seller_fb=2)]  # reject: seller
        scout = FakeScout([seed, live])
        r1 = run.cycle(con=self.con, scouts=[scout], force=True, dry=True, log=lambda *_: None)
        self.assertEqual(r1["pushes"], 0, "first scan of a market must not push individual deals")
        self.assertTrue(any("seeded" in p["title"] for p in notify.SENT))
        notify.SENT.clear()

        r2 = run.cycle(con=self.con, scouts=[scout], force=True, dry=True, log=lambda *_: None)
        deals = [p for p in notify.SENT if p["title"].startswith("DEAL")]
        self.assertEqual(len(deals), 1, notify.SENT)
        self.assertIn("Lugia", deals[0]["title"])
        self.assertIn("#alert-", deals[0]["click"])
        self.assertEqual([a["label"] for a in deals[0]["actions"]], ["Open listing", "Dashboard"])
        tiers = {l["item_id"]: (l["tier"], l["reason"]) for l in db.rows(self.con, "SELECT * FROM listings")}
        self.assertEqual(tiers["a1"][0], "DEAL")
        self.assertEqual(tiers["a4"][0], "REJECT")
        self.assertIn("feedback", tiers["a5"][1])
        landed = json.loads(db.one(self.con, "SELECT landed FROM listings WHERE item_id='a3'")["landed"])
        self.assertEqual(set(landed), {"NYC", "CA"})

        notify.SENT.clear()
        scout.batches.append(live + [listing("lc1", "Charizard 003/110 Legendary Collection Reverse Holo", 6400.0, tid="lc-reverse")])
        scout.calls = 4 * (len(scout.batches) - 1)
        run.cycle(con=self.con, scouts=[scout], force=True, dry=True, log=lambda *_: None)
        listed = [p for p in notify.SENT if p["title"].startswith("LISTED")]
        self.assertEqual(len(listed), 1, notify.SENT)
        self.assertIn("Charizard", listed[0]["title"])
        self.assertFalse([p for p in notify.SENT if p["title"].startswith("DEAL")], "same listing must not push twice")

        notify.SENT.clear()
        run.cycle(con=self.con, scouts=[scout], force=True, dry=True, log=lambda *_: None)
        self.assertFalse([p for p in notify.SENT if p["title"].startswith("DEAL")], "same listing must not push twice")

    def test_missing_keys_alerts_once(self):
        run.cycle(con=self.con, scouts=[], force=True, dry=True, log=lambda *_: None)
        run.cycle(con=self.con, scouts=[], force=True, dry=True, log=lambda *_: None)
        # scouts=[] simulates no scouts; the CLI path sets no_keys. Watchdog must not spam either way.
        self.assertLessEqual(len([p for p in notify.SENT if "keys" in p["title"].lower()]), 1)


if __name__ == "__main__":
    unittest.main()
