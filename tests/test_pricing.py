import unittest
from radar.config import load_settings
from radar.decide import decide
from radar.landed import landed

RATES = {"USD": 1.0, "CAD": 1.4, "GBP": 0.75, "EUR": 0.9, "AUD": 1.42, "JPY": 158}
S = load_settings()
S["decide"]["push_every_listing"] = False   # tier rules first; the every-listing switch is tested on its own
EVERY = dict(S, decide=dict(S["decide"], push_every_listing=True))


class Landed(unittest.TestCase):
    def test_canadian_listing_to_canada(self):
        l = {"price": 140.0, "currency": "CAD", "item_country": "CA"}
        out, best = landed(l, [{"dest": "CA", "ship": 14.0, "ship_currency": "CAD", "ships": 1}], S["destinations"], RATES)
        # (140 + 14) / 1.4 = 110 USD, x 1.13 HST, domestic so no import extra
        self.assertEqual(best, "CA")
        self.assertAlmostEqual(out["CA"]["usd"], 110 * 1.13, places=1)
        self.assertFalse(out["CA"]["international"])

    def test_uk_listing_picks_cheaper_destination_and_estimates_missing_shipping(self):
        l = {"price": 75.0, "currency": "GBP", "item_country": "GB"}
        q = [{"dest": "CA", "ship": 7.5, "ship_currency": "GBP", "ships": 1}, {"dest": "NYC", "ship": None, "ships": 1}]
        out, best = landed(l, q, S["destinations"], RATES)
        self.assertTrue(out["NYC"]["ship_estimated"])
        self.assertTrue(out["CA"]["international"])
        self.assertEqual(best, min(out, key=lambda k: out[k]["usd"]))


def match_stub(**kw):
    card = {"name": "Kingdra", "number": "H14/H32", "subtype": "Holofoil", "target_id": "aquapolis-holo"}
    base = {"card": card, "card_key": "k", "confidence": "high", "grade": None, "flags": [], "reason": None, "condition": "NM"}
    base.update(kw)
    return base


T = {"id": "aquapolis-holo", "push_gap_pct": 20, "watch_gap_pct": 5, "min_value_usd": 50, "max_price_usd": 10000}
L = {"feedback": 500, "feedback_pct": 99.9, "buying": "FIXED_PRICE"}


class Decide(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(decide(L, match_stub(), 200, 150, T, S)[0], "DEAL")
        self.assertEqual(decide(L, match_stub(), 200, 185, T, S)[0], "WATCH")
        self.assertEqual(decide(L, match_stub(), 200, 210, T, S)[0], "SEEN")

    def test_guardrails_cap_or_reject(self):
        self.assertEqual(decide(L, match_stub(confidence="low", reason="x"), 200, 100, T, S)[0], "WATCH")
        self.assertEqual(decide(L, match_stub(grade="PSA 9"), 200, 100, T, S)[0], "WATCH")
        self.assertEqual(decide(dict(L, buying="AUCTION"), match_stub(), 200, 100, T, S)[0], "WATCH")
        self.assertEqual(decide(L, match_stub(flags=["fake"]), 200, 100, T, S)[0], "REJECT")
        self.assertEqual(decide(dict(L, feedback=3), match_stub(), 200, 100, T, S)[0], "REJECT")
        self.assertEqual(decide(L, match_stub(card=dict(match_stub()["card"], target_id=None)), 200, 100, T, S)[0], "REJECT")

    def test_tcgplayer_lows_never_push_by_default(self):
        self.assertEqual(decide(dict(L, source="tcgplayer", feedback=None, feedback_pct=None), match_stub(), 300, 100, T, S)[0], "WATCH")

    def test_unvalued_target_is_listed(self):
        self.assertEqual(decide(L, match_stub(), None, 3000, T, S)[0], "LISTED")

    def test_cheap_cards_are_not_pushed(self):
        self.assertEqual(decide(L, match_stub(), 30, 10, T, S)[0], "SEEN")

    def test_every_listing_pushes_real_targets_only(self):
        self.assertEqual(decide(L, match_stub(), 200, 150, T, EVERY)[0], "DEAL")
        self.assertEqual(decide(L, match_stub(), 200, 210, T, EVERY), ("LISTED", "+5% vs value"))
        self.assertEqual(decide(L, match_stub(grade="PSA 9"), 200, 100, T, EVERY)[0], "LISTED")
        self.assertEqual(decide(L, match_stub(), 30, 10, T, EVERY)[0], "LISTED")
        self.assertEqual(decide(L, match_stub(flags=["lot"]), 200, 100, T, EVERY)[0], "REJECT")
        self.assertEqual(decide(dict(L, source="tcgplayer", feedback=None, feedback_pct=None), match_stub(), 300, 100, T, EVERY)[0], "WATCH")


if __name__ == "__main__":
    unittest.main()
