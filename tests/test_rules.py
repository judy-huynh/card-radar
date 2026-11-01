"""Settings -> Rules (SPEC "Rules on the Settings page"): checked, saved together, logged, undoable."""
import json, os, shutil, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from radar import catalog, config, db, rules
from tests.test_cycle import CycleDB

S, T = config.load_settings(), config.load_targets()


class Apply(unittest.TestCase):
    def test_good_changes_come_back_with_a_log_line_each(self):
        s, t, changes = rules.apply(S, T, {"notify.max_pushes_per_day": "8", "condition_filter.seller_must_say": ["LP", "NM"]},
                                    {"aquapolis-holo": {"push_gap_pct": 25}})
        self.assertEqual(s["notify"]["max_pushes_per_day"], 8)
        self.assertEqual(s["condition_filter"]["seller_must_say"], ["NM", "LP"], "stored in the listed order")
        self.assertEqual(next(x for x in t if x["id"] == "aquapolis-holo")["push_gap_pct"], 25)
        self.assertEqual(len(changes), 3)
        self.assertEqual(S["notify"]["max_pushes_per_day"], config.load_settings()["notify"]["max_pushes_per_day"],
                         "apply never touches the originals")

    def test_one_bad_value_refuses_everything_with_why(self):
        for bad, why in (({"notify.max_pushes_per_day": 99}, "between"), ({"notify.max_pushes_per_day": "lots"}, "number"),
                         ({"condition_filter.seller_must_say": []}, "at least one"), ({"decide.push_auctions": "yes"}, "on or off"),
                         ({"ebay.limit": 50}, "can't be changed")):
            with self.assertRaises(ValueError) as e:
                rules.apply(S, T, dict(bad, **{"whatnot.realize_pct": 80}))
            self.assertIn(why, str(e.exception))

    def test_unchanged_values_are_not_logged(self):
        self.assertEqual(rules.apply(S, T, {"notify.max_pushes_per_day": S["notify"]["max_pushes_per_day"]})[2], [])

    def test_every_rule_points_at_a_real_setting(self):
        for r in rules.current(S)["rules"]:
            self.assertIsNotNone(r["value"], r["key"])
            rules.clean(r["kind"], r["options"], r["value"], r["label"])   # today's values are inside their ranges


class Server(CycleDB):
    """The real dashboard server on a spare port, writing copies of the config files."""
    def setUp(self):
        super().setUp()
        d = tempfile.mkdtemp()
        self.paths = (config.SETTINGS_PATH, config.TARGETS_PATH)
        for name in ("settings.json", "targets.json"):
            shutil.copy(os.path.join(config.ROOT, "config", name), os.path.join(d, name))
        config.SETTINGS_PATH, config.TARGETS_PATH = os.path.join(d, "settings.json"), os.path.join(d, "targets.json")
        import server
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown(); self.httpd.server_close()
        config.SETTINGS_PATH, config.TARGETS_PATH = self.paths
        super().tearDown()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_save_log_undo(self):
        code, r = self.post("/api/rules", {"rules": {"notify.max_pushes_per_day": 8}, "targets": {"dark-gengar": {"paused": True}}})
        self.assertEqual((code, r["changed"]), (200, 2))
        self.assertEqual(config.load_settings()["notify"]["max_pushes_per_day"], 8)
        self.assertTrue(next(t for t in config.load_targets() if t["id"] == "dark-gengar")["paused"])
        log = db.rows(db.connect(), "SELECT * FROM rule_changes ORDER BY id")
        self.assertEqual([c["what"] for c in log][0], "Buzzes per day")

        code, r = self.post(f"/api/rules/{log[0]['id']}/undo", {})
        self.assertEqual((code, r["changed"]), (200, 1))
        self.assertEqual(config.load_settings()["notify"]["max_pushes_per_day"], S["notify"]["max_pushes_per_day"])
        self.assertEqual(len(db.rows(db.connect(), "SELECT * FROM rule_changes")), 3, "an undo is logged too")

        with urllib.request.urlopen(self.base + "/api/state") as resp:
            state = json.load(resp)
        self.assertEqual(len(state["rule_log"]), 3)
        self.assertTrue(any(x["key"] == "notify.max_pushes_per_day" for x in state["rules"]["rules"]))

    def test_bad_value_saves_nothing(self):
        read = lambda: open(config.SETTINGS_PATH).read()
        before = read()
        code, r = self.post("/api/rules", {"rules": {"notify.max_pushes_per_day": 8, "whatnot.realize_pct": 900}})
        self.assertEqual(code, 400)
        self.assertIn("between", r["error"])
        self.assertEqual(read(), before)


class Freshness(CycleDB):
    def test_a_card_tcgplayer_dropped_doesnt_make_values_stale(self):
        self.con.execute("UPDATE cards SET target_id='aquapolis-holo'")
        self.con.execute("UPDATE cards SET updated='2026-10-01 00:00:00' WHERE rowid = (SELECT MIN(rowid) FROM cards)")
        self.assertLess(catalog.age_hours(self.con), 1)


if __name__ == "__main__":
    unittest.main()
