"""Sold or ended listings: never pushed, and moved off the Deals page by the hourly recheck."""
import unittest
from radar import db, notify, run
from radar.config import load_settings
from radar.scouts.ebay import gone_reason
from tests.test_cycle import CycleDB, listing
from tests.test_grading import DetailScout


class GoneReason(unittest.TestCase):
    NOW = "2026-10-31T05:00:00"

    def test_sold_out_of_stock(self):   # the Dark Gengar from 2026-10-31, as eBay returned it
        data = {"estimatedAvailabilities": [{"estimatedAvailabilityStatus": "OUT_OF_STOCK", "estimatedAvailableQuantity": 0,
                                             "estimatedSoldQuantity": 1}], "itemEndDate": "2026-10-26T10:04:33.000Z"}
        self.assertEqual(gone_reason(data, self.NOW), "Sold on eBay on Oct 26")

    def test_ended_without_sale(self):
        data = {"estimatedAvailabilities": [{"estimatedAvailabilityStatus": "IN_STOCK"}], "itemEndDate": "2026-10-30T12:00:00.000Z"}
        self.assertEqual(gone_reason(data, self.NOW), "Listing ended on Oct 30")

    def test_still_for_sale(self):
        self.assertIsNone(gone_reason({"estimatedAvailabilities": [{"estimatedAvailabilityStatus": "IN_STOCK"}]}, self.NOW))
        self.assertIsNone(gone_reason({"estimatedAvailabilities": [{"estimatedAvailabilityStatus": "IN_STOCK"}],
                                       "itemEndDate": "2026-11-10T04:59:01.000Z"}, self.NOW))


class GoneScout(DetailScout):
    def __init__(self, batches):
        super().__init__(batches, picks={})
        self.gone = {}

    def details(self, item_id, marketplace):
        d = super().details(item_id, marketplace)
        d["seller_condition"] = "Near mint or better"
        return dict(d, gone=self.gone.get(item_id))


class InTheScan(CycleDB):
    def scan(self, scout):
        return run.cycle(con=self.con, scouts=[scout], force=True, dry=True, log=lambda *_: None)

    def open_ids(self):
        return {r["item_id"] for r in db.open_deals(self.con)}

    def test_sold_listing_never_pushes(self):
        seed = [listing("k0", "Aquapolis Kingdra H14/H32 Holo", 230.0)]
        live = seed + [listing("s1", "Aquapolis Crystal Lugia 149/147 Holo", 300.0),
                       listing("s2", "Aquapolis Crystal Lugia 149/147 Holo", 310.0)]
        scout = GoneScout([seed, live])
        scout.gone = {"s1": "Sold on eBay on Oct 26"}
        self.scan(scout); notify.SENT.clear()
        self.scan(scout)
        titles = " ".join(p["title"] for p in notify.SENT)
        self.assertEqual(sum("Lugia" in p["title"] for p in notify.SENT), 1, titles)
        a = db.one(self.con, "SELECT decision, outcome, pushed FROM alerts WHERE item_id='s1'")
        self.assertEqual((a["decision"], a["outcome"], a["pushed"]), ("gone", "Sold on eBay on Oct 26", 0))
        self.assertEqual(self.open_ids(), {"s2"})

    def test_hourly_recheck_moves_sold_deals_to_history(self):
        seed = [listing("k0", "Aquapolis Kingdra H14/H32 Holo", 230.0)]
        live = seed + [listing("r1", "Aquapolis Crystal Lugia 149/147 Holo", 300.0)]
        scout = GoneScout([seed, live])
        self.scan(scout); self.scan(scout)
        self.assertEqual(self.open_ids(), {"r1"})

        scout.gone = {"r1": "Sold on eBay on Oct 31"}
        settings = load_settings()
        self.assertEqual(run.recheck_open(self.con, {scout.name: scout}, settings, {"calls": 0, "errors": []}), 0,
                         "the scan just rechecked, so it waits for recheck_open_min")
        gone = run.recheck_open(self.con, {scout.name: scout}, settings, {"calls": 0, "errors": []}, log=lambda *_: None, force=True)
        self.assertEqual(gone, 1)
        self.assertEqual(self.open_ids(), set())
        a = db.one(self.con, "SELECT decision, outcome FROM alerts WHERE item_id='r1' ORDER BY id DESC")
        self.assertEqual((a["decision"], a["outcome"]), ("gone", "Sold on eBay on Oct 31"))


if __name__ == "__main__":
    unittest.main()
