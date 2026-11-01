"""Grade ranges: the seller's eBay "Card Condition" pick, photo checks, and how they feed the value and the push."""
import unittest
from radar import db, grading, notify, run
from radar.config import load_settings
from tests.helpers import legacy_settings
from tests.test_cycle import CycleDB, FakeScout, listing

SETTINGS = load_settings()


class SellerCondition(unittest.TestCase):
    def test_texts_ebay_returned(self):   # copied from real listings on 2026-10-31, several eBay sites
        cases = {
            "Near mint or better": "NM",
            "Lightly played (Excellent)": "LP",
            "Lightly Played/Excellent (légers défauts)": "LP",
            "Leicht bespielt (Exzellent/Excellent)": "LP",
            "Moderately Played (Very Good)": "MP",
            "Heavily played (Poor)": "HP",
            "Heavily Played (Poor)": "HP",
        }
        for text, code in cases.items():
            self.assertEqual(grading.seller_code(text), code, text)
        self.assertIsNone(grading.seller_code(None))
        self.assertIsNone(grading.seller_code("Ungraded"))

    def test_worse_wins_and_unknown_loses(self):
        self.assertEqual(grading.worse("NM", "MP"), "MP")
        self.assertEqual(grading.worse("HP", "LP"), "HP")
        self.assertEqual(grading.worse(None, "LP"), "LP")
        self.assertEqual(grading.worse("NM", None), "NM")

    def test_range_comes_from_settings(self):
        self.assertEqual(grading.from_condition("LP", SETTINGS), tuple(SETTINGS["grade_from_condition"]["LP"]))
        self.assertEqual(grading.from_condition(None, SETTINGS), (None, None))


class Stored(CycleDB):
    def test_photo_check_survives_seller_pick(self):
        grading.record_photos(self.con, "x1", 6, 8, "clean front")
        grading.record_seller(self.con, "x1", "Heavily played (Poor)", SETTINGS)
        g = grading.get(self.con, "x1")
        self.assertEqual((g["low"], g["high"], g["source"], g["seller_condition"]), (6, 8, "photos", "HP"))

    def test_seller_pick_fills_and_updates(self):
        grading.record_seller(self.con, "x2", "Lightly played (Excellent)", SETTINGS)
        g = grading.get(self.con, "x2")
        self.assertEqual((g["low"], g["high"], g["source"]), (*SETTINGS["grade_from_condition"]["LP"], "seller"))


class DetailScout(FakeScout):
    """Fake eBay with listing details: every listing's seller picked the condition in `picks` (default heavily played)."""
    def __init__(self, batches, picks=None):
        super().__init__(batches)
        self.picks, self.detail_calls = picks or {}, []

    def details(self, item_id, marketplace):
        self.detail_calls.append(item_id)
        return {"seller_condition": self.picks.get(item_id, "Heavily played (Poor)")}


class InTheScan(CycleDB):
    def scan(self, scout):
        return run.cycle(con=self.con, scouts=[scout], force=True, dry=True, log=lambda *_: None, settings=legacy_settings())

    def test_seller_pick_lowers_value_and_rides_the_push(self):
        seed = [listing("k0", "Aquapolis Kingdra H14/H32 Holo", 230.0)]
        live = seed + [listing("d1", "Aquapolis Crystal Lugia 149/147 Holo", 300.0),   # deal if not stated
                       listing("d2", "Aquapolis Crystal Lugia 149/147 Holo NM", 300.0)]  # title NM, seller says LP
        scout = DetailScout([seed, live], picks={"d2": "Lightly played (Excellent)"})
        self.scan(scout)
        self.assertEqual(scout.detail_calls, [], "seeding a market must not fetch details")
        self.scan(scout)
        self.assertEqual(sorted(scout.detail_calls), ["d1", "d2"])
        cond = {r["item_id"]: r["condition"] for r in db.rows(self.con, "SELECT item_id, condition FROM listings")}
        self.assertEqual(cond["d1"], "HP")
        self.assertEqual(cond["d2"], "LP", "title NM, seller LP: the worse one wins")
        pushed = [p for p in notify.SENT if "Lugia" in p["title"]]
        self.assertTrue(pushed and any("likely PSA" in p["message"] for p in pushed), notify.SENT)

        scout.detail_calls.clear()
        self.scan(scout)
        self.assertEqual(scout.detail_calls, [], "details are read once per listing")


if __name__ == "__main__":
    unittest.main()
