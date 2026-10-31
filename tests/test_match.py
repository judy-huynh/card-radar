import unittest
from radar.match import match
from tests.helpers import cards, target


def m(title, tid, cond=None):
    t = target(tid)
    return match(title, cond, t, cards(t["group_id"]))


class MatchTargets(unittest.TestCase):
    def assertCard(self, r, name, number, subtype, conf=("high",)):
        self.assertIsNotNone(r["card"], r["reason"])
        self.assertEqual((r["card"]["name"], r["card"]["number"], r["card"]["subtype"]), (name, number, subtype))
        self.assertIn(r["confidence"], conf, r["reason"])

    def test_lc_reverse_holo_with_number(self):
        r = m("Pokemon Legendary Collection Gengar 11/110 Reverse Holo Fireworks NM", "lc-reverse")
        self.assertCard(r, "Gengar", "011/110", "Reverse Holofoil")
        self.assertEqual(r["card"]["target_id"], "lc-reverse")
        self.assertEqual(r["condition"], "NM")

    def test_lc_regular_holo_is_not_target(self):
        r = m("Legendary Collection Charizard 3/110 Holo Rare WOTC", "lc-reverse")
        self.assertEqual(r["card"]["subtype"], "Holofoil")
        self.assertIsNone(r["card"]["target_id"])

    def test_lc_charizard_reverse_has_no_market(self):
        r = m("Charizard 003/110 Legendary Collection REVERSE HOLO", "lc-reverse")
        self.assertCard(r, "Charizard", "003/110", "Reverse Holofoil")
        self.assertIsNone(r["card"]["market"])

    def test_southern_islands_mew(self):
        r = m("Pokemon Southern Islands Mew 1/18 Promo Holo", "southern-islands")
        self.assertCard(r, "Mew", "01/18", "Reverse Holofoil", ("high", "medium"))

    def test_skyridge_h_number_defaults_to_holo(self):
        r = m("Skyridge Beedrill H4/H32 e-Reader Pokemon Card", "skyridge-holo")
        self.assertCard(r, "Beedrill", "H04/H32", "Holofoil")

    def test_skyridge_reverse_beedrill_is_the_common_not_the_holo(self):
        r = m("Skyridge Beedrill 5/144 Reverse Holo", "skyridge-holo")
        self.assertEqual((r["card"]["number"], r["card"]["subtype"]), ("005/144", "Reverse Holofoil"))
        self.assertIsNone(r["card"]["target_id"])

    def test_contradiction_is_low_confidence(self):
        r = m("Skyridge Beedrill H4/H32 Reverse Holo", "skyridge-holo")   # H4 exists only as holo
        self.assertEqual(r["confidence"], "low")

    def test_skyridge_crystal_ho_oh(self):
        r = m("Pokemon Skyridge Crystal Ho-oh 149/144 Secret Rare", "skyridge-holo")
        self.assertCard(r, "Ho-oh", "149/144", "Reverse Holofoil", ("high", "medium"))
        self.assertEqual(r["card"]["target_id"], "skyridge-holo")

    def test_skyridge_crystal_charizard_uses_priced_row(self):
        r = m("Skyridge Crystal Charizard 146/144 Holo", "skyridge-holo")
        self.assertEqual(r["card"]["market"], 2999.99)

    def test_aquapolis_crystal_lugia(self):
        r = m("Aquapolis Crystal Lugia 149/147 Holo Pokemon", "aquapolis-holo")
        self.assertCard(r, "Lugia", "149/147", "Holofoil", ("high", "medium"))

    def test_aquapolis_kingdra_h14(self):
        r = m("Kingdra H14/H32 Aquapolis Holo Rare", "aquapolis-holo")
        self.assertCard(r, "Kingdra", "H14/H32", "Holofoil")

    def test_dark_gengar_unlimited_by_default(self):
        r = m("Dark Gengar 6/105 Neo Destiny Holo Rare WOTC LP", "dark-gengar")
        self.assertCard(r, "Dark Gengar", "006/105", "Unlimited Holofoil")
        self.assertEqual(r["condition"], "LP")

    def test_dark_gengar_first_edition(self):
        r = m("1st Edition Dark Gengar 6/105 Neo Destiny Holo", "dark-gengar")
        self.assertCard(r, "Dark Gengar", "006/105", "1st Edition Holofoil")

    def test_dark_gengar_not_plain_gengar(self):
        r = m("Dark Gengar Neo Destiny holo", "dark-gengar")
        self.assertEqual(r["card"]["name"], "Dark Gengar")

    def test_expedition_holo_vs_nonholo_number(self):
        r = m("Expedition Alakazam 1/165 Holo", "expedition-holo")
        self.assertCard(r, "Alakazam", "001/165", "Holofoil")
        r = m("Expedition Alakazam 33/165 Non Holo Rare", "expedition-holo")
        self.assertEqual(r["card"]["number"], "033/165")
        self.assertIsNone(r["card"]["target_id"])


class Flags(unittest.TestCase):
    def test_graded(self):
        self.assertEqual(m("PSA 9 Mint Dark Gengar 6/105 Neo Destiny Holo", "dark-gengar")["grade"], "PSA 9")
        self.assertEqual(m("CGC 9.5 Aquapolis Kingdra H14/H32", "aquapolis-holo")["grade"], "CGC 9.5")

    def test_red_flags(self):
        self.assertIn("lot", m("Lot of 5 Expedition holo cards", "expedition-holo")["flags"])
        self.assertIn("fake", m("Custom Proxy Dark Gengar Neo Destiny", "dark-gengar")["flags"])
        self.assertIn("japanese", m("Japanese Skyridge Ho-oh crystal", "skyridge-holo")["flags"])

    def test_legendary_collection_word_is_not_a_lot(self):
        self.assertEqual(m("Legendary Collection Gengar 11/110 Reverse Holo", "lc-reverse")["flags"], [])

    def test_wrong_number_lowers_confidence(self):
        r = m("Expedition Alakazam 99/165 Holo", "expedition-holo")
        self.assertEqual(r["confidence"], "low")



class RealTitleJunk(unittest.TestCase):
    """Titles from the first live eBay scan (2026-10-30) that priced as fake 'deals'."""
    def flags(self, title, tid):
        return m(title, tid)["flags"]

    def test_card_skin_is_not_a_card(self):
        self.assertTrue(self.flags("Dark Gengar N4 6/105 CREDIT CARD SKIN", "dark-gengar"))

    def test_30th_celebration_lugia_is_a_modern_reprint(self):
        self.assertIn("modern reprint", self.flags("Pokemon TCG 30th Celebration Classic Collection Lugia 149/147 NM", "aquapolis-holo"))
        self.assertIn("modern reprint", self.flags("Kristall Lugia 149/147 Classic Collection 30. C DE", "aquapolis-holo"))

    def test_old_back_and_german_language_words(self):
        self.assertIn("japanese", self.flags("[MP] Dark Gengar Holo No.094 Neo Destiny Darkness and to Light Old Back", "dark-gengar"))
        self.assertIn("non-English", self.flags("Pokémon Dunkles Gengar Holo #6/105 Neo Destiny Italienisch Gut", "dark-gengar"))

    def test_condition_words(self):
        self.assertEqual(m("Dark Gengar 6/105 Unlimited Holo Rare Neo Destiny Pokemon Card Heavy Played", "dark-gengar")["condition"], "HP")
        self.assertEqual(m("Pokemon Marill Southern Islands Reverse Holo Englisch Leicht Bespielt", "southern-islands")["condition"], "LP")
        self.assertEqual(m("Tentacruel 10/18 Southern Islands Lightly Played", "southern-islands")["condition"], "LP")
        self.assertEqual(m("Pokemon Karte Jumpluff H13/H32 Aquapolis Holo GESPIELT Englisch", "aquapolis-holo")["condition"], "MP")

    def test_read_description_is_not_near_mint(self):
        self.assertEqual(m("Suicune H25/H32 Aquapolis Holo *Read Description*", "aquapolis-holo")["condition"], "HP")


if __name__ == "__main__":
    unittest.main()
