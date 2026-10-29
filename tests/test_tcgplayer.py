import unittest
from radar.match import match
from radar.scouts import Job
from radar.scouts.tcgplayer import listing_for
from tests.helpers import CARDS, cards, target
from radar.config import load_targets


class SynthesizedTitlesRoundTrip(unittest.TestCase):
    def test_every_target_card_matches_itself(self):
        misses = []
        for t in load_targets():
            pool = cards(t["group_id"])
            for c in [c for c in pool if c["target_id"] == t["id"] and c["low"] is not None]:
                l = listing_for(c, Job("tcgplayer", "TCGPLAYER", "NYC", t, ""))
                r = match(l["title"], None, t, pool)
                if r["card_key"] != c["card_key"] and r["card"] and r["card"]["product_id"] == c["product_id"] \
                        and c["rarity"] == "Secret Rare":
                    continue   # crystal with two foil rows: the scout pins the exact row, see pipeline.evaluate
                if r["card_key"] != c["card_key"] or r["confidence"] == "low":
                    misses.append((l["title"], c["subtype"], r["card"] and r["card"]["subtype"], r["confidence"], r["reason"]))
        self.assertEqual(misses, [], "\n".join(map(str, misses[:15])))


if __name__ == "__main__":
    unittest.main()
