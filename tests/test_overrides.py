import unittest
from radar.overrides import parse
from tests.helpers import CARDS


def rows(tid):
    return [c for c in CARDS if c["target_id"] == tid]


class BulkPaste(unittest.TestCase):
    def test_simple_and_formatted_values(self):
        m, u = parse("H14 214.50\n149/147 $1,020", rows("aquapolis-holo"))
        self.assertEqual(u, [])
        self.assertEqual(sorted(v for _, v, _ in m), [214.5, 1020.0])

    def test_dark_gengar_needs_a_variant_word(self):
        m, u = parse("6 1000", rows("dark-gengar"))
        self.assertEqual(m, []); self.assertIn("1st", u[0][1])
        m, u = parse("6 1st 1000\n6 unlimited 1100", rows("dark-gengar"))
        self.assertEqual(len(m), 2); self.assertEqual(u, [])

    def test_crystal_with_two_rows_sets_both(self):
        m, u = parse("146 3200", rows("skyridge-holo"))
        self.assertEqual(len(m), 2); self.assertEqual(u, [])

    def test_unknown_number_is_reported(self):
        m, u = parse("H99 50", rows("skyridge-holo"))
        self.assertEqual(m, []); self.assertEqual(len(u), 1)


if __name__ == "__main__":
    unittest.main()
