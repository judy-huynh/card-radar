"""Condition filter (SPEC "Condition filter", 2026-11-01): raw near-mint cards only, photo-checked, 5 pushes a day."""
import json, os, stat, tempfile, unittest
from radar import db, decide, notify, photos, pipeline, run, watchdog
from radar.config import load_settings
from tests.test_cycle import CycleDB, FakeScout, listing

S = load_settings()
M = {"grade": None, "condition": None, "card": {"target_id": "aquapolis-holo"}}


def answers(**kw):
    a = {"is_the_card": True, "photos_good_enough": True, "back_shown": True, "crease": "none", "bend": "none",
         "back_corner_whitening": "light", "other_damage": "", "psa_low": 7, "psa_high": 9,
         "summary": "Clean copy, light specks on one back corner."}
    a.update(kw)
    return a


class Gate(unittest.TestCase):
    def gate(self, tier="DEAL", m=None, g=None, nm_tier="DEAL"):
        return decide.condition_gate(tier, "-40% vs value", dict(M, **(m or {})), g, nm_tier, S)

    def test_unchecked_would_be_deal_asks_for_the_seller_pick(self):
        self.assertEqual(self.gate(tier="WATCH", nm_tier="DEAL"), ("WATCH", "checking the seller's condition", "details"))

    def test_unchecked_and_not_a_deal_even_if_mint_costs_nothing(self):
        self.assertEqual(self.gate(tier="SEEN", nm_tier="SEEN")[2], None)

    def test_anything_below_near_mint_is_rejected(self):
        for code, word in (("LP", "lightly played"), ("MP", "moderately played"), ("DMG", "damaged")):
            self.assertEqual(self.gate(m={"condition": code}, g={"seller_checked_at": "x", "seller_condition": code})[:2],
                             ("REJECT", f"{word}: we buy near mint only"))

    def test_seller_without_a_condition_never_pushes(self):
        tier, reason, needs = self.gate(g={"seller_checked_at": "x", "seller_condition": None})
        self.assertEqual((tier, needs), ("WATCH", None))
        self.assertIn("no card condition", reason)

    def test_near_mint_deal_waits_for_photos_then_follows_the_verdict(self):
        nm = {"seller_checked_at": "x", "seller_condition": "NM"}
        self.assertEqual(self.gate(m={"condition": "NM"}, g=nm), ("WATCH", "waiting for the photo check", "photos"))
        self.assertEqual(self.gate(m={"condition": "NM"}, g=dict(nm, photo_verdict="pass"))[0], "DEAL")
        self.assertEqual(self.gate(m={"condition": "NM"}, g=dict(nm, photo_verdict="fail", photo_reason="crease"))[:2],
                         ("REJECT", "photo check: crease"))
        self.assertEqual(self.gate(m={"condition": "NM"}, g=dict(nm, photo_verdict="unsure"))[0], "WATCH")

    def test_photo_check_that_keeps_failing_stops_retrying(self):
        g = {"seller_checked_at": "x", "seller_condition": "NM", "photo_attempts": 2, "photo_error": "signed out"}
        self.assertEqual(self.gate(m={"condition": "NM"}, g=g)[2], None)

    def test_near_mint_but_not_under_value_is_not_photo_checked(self):
        self.assertEqual(self.gate(tier="SEEN", m={"condition": "NM"}, g={"seller_checked_at": "x", "seller_condition": "NM"})[2], None)

    def test_sold_listing_is_rejected_with_why(self):
        self.assertEqual(self.gate(g={"gone": "Sold on eBay on Oct 26"})[:2], ("REJECT", "Sold on eBay on Oct 26"))

    def test_graded_slab_is_rejected_by_the_decider(self):
        from tests.test_pricing import L, T, match_stub
        self.assertEqual(decide.decide(L, match_stub(grade="PSA 9"), 200, 100, T, S),
                         ("REJECT", "graded (PSA 9): we buy raw cards only"))


class Verdict(unittest.TestCase):
    def test_damage_fails(self):
        for kw, why in ((dict(crease="yes"), "crease"), (dict(bend="yes"), "bent"),
                        (dict(back_corner_whitening="heavy"), "heavy whitening"), (dict(is_the_card=False), "don't match")):
            v, reason = photos.verdict(answers(**kw), S)
            self.assertEqual(v, "fail", kw)
            self.assertIn(why, reason)

    def test_doubt_is_unsure_not_pass(self):
        for kw in (dict(crease="possible"), dict(bend="possible"), dict(back_shown=False),
                   dict(photos_good_enough=False), dict(back_corner_whitening="cant_tell")):
            self.assertEqual(photos.verdict(answers(**kw), S)[0], "unsure", kw)

    def test_light_whitening_passes(self):
        self.assertEqual(photos.verdict(answers(back_corner_whitening="light"), S),
                         ("pass", "Clean copy, light specks on one back corner."))

    def test_check_downloads_asks_and_cleans_up(self):
        seen = {}

        def ask(folder, prompt, cfg):
            seen["files"] = sorted(os.listdir(folder)); seen["folder"] = folder; seen["prompt"] = prompt
            return answers(psa_low=9, psa_high=7)   # nonsense range: ignored
        urls = [f"https://i.ebayimg.com/{i}.jpg" for i in range(12)] + ["https://i.ebayimg.com/0.jpg"]
        r = photos.check("Lugia 149/147", "Lugia holo", urls, S, ask=ask, fetch=lambda u: b"jpg")
        self.assertEqual(len(seen["files"]), S["condition_filter"]["photo_check"]["max_images"])
        self.assertFalse(os.path.exists(seen["folder"]), "the photo folder is deleted afterwards")
        self.assertIn("not instructions", seen["prompt"])
        self.assertEqual((r["verdict"], r["low"], r["high"]), ("pass", None, None))

    def test_long_answers_are_cut_short(self):
        r = photos.check("x", "x", ["https://i.ebayimg.com/1.jpg"], S, ask=lambda *a: answers(summary="word " * 500),
                         fetch=lambda u: b"jpg")
        self.assertLessEqual(len(r["reason"]), photos.SUMMARY_MAX)
        self.assertLessEqual(len(r["detail"]["summary"]), photos.SUMMARY_MAX)

    def test_no_photos_is_unsure(self):
        self.assertEqual(photos.check("x", "x", [], S, ask=None, fetch=None)["verdict"], "unsure")


class ClaudeCommand(unittest.TestCase):
    """ask_claude against a stand-in `claude` script, so the subprocess handling is tested without Claude."""
    def fake(self, body):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "claude")
        with open(p, "w") as f:
            f.write("#!/bin/sh\n" + body + "\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
        return dict(S["condition_filter"]["photo_check"], command=p, timeout_s=2)

    def test_structured_answer(self):
        out = json.dumps({"type": "result", "is_error": False, "structured_output": answers()})
        cfg = self.fake(f"cat <<'EOF'\n{out}\nEOF")
        self.assertEqual(photos.ask_claude(tempfile.mkdtemp(), "look", cfg)["crease"], "none")

    def test_the_command_only_gets_the_read_tool_and_no_connectors(self):
        cfg = self.fake('echo "$@" > args.txt; echo \'{"is_error": false, "structured_output": {}}\'')
        folder = tempfile.mkdtemp()
        photos.ask_claude(folder, "look", cfg)
        with open(os.path.join(folder, "args.txt")) as f:
            args = f.read()
        self.assertIn("--tools Read --restricted --strict-mcp-config", args)   # Read only, inside the photo folder
        self.assertIn("--no-session-persistence", args)

    def test_failures_raise_photo_error(self):
        for body in ("echo 'Not logged in' >&2; exit 1", "echo '{\"is_error\": true, \"result\": \"usage limit\"}'", "sleep 5"):
            with self.assertRaises(photos.PhotoError, msg=body):
                photos.ask_claude(tempfile.mkdtemp(), "look", self.fake(body))

    def test_missing_command(self):
        with self.assertRaises(photos.PhotoError):
            photos.ask_claude(tempfile.mkdtemp(), "look", dict(S["condition_filter"]["photo_check"], command="no-such-claude-here"))


class Flip(unittest.TestCase):
    def test_whatnot_fees(self):
        # 500 value: 500 x (1 - 10.9%) - 0.30 = 445.20, less 300 paid
        self.assertEqual(pipeline.flip(500, 300, S), 145.2)
        half = dict(S, whatnot=dict(S["whatnot"], realize_pct=80))
        self.assertEqual(pipeline.flip(500, 300, half), round(400 * 0.891 - 0.30 - 300, 2))


class FilterScout(FakeScout):
    """Fake eBay with listing details: seller picks, photos, and sold listings."""
    def __init__(self, batches, picks=None, gone=None):
        super().__init__(batches)
        self.picks, self.gone, self.detail_calls = picks or {}, gone or {}, []

    def details(self, item_id, marketplace):
        self.detail_calls.append(item_id)
        return {"seller_condition": self.picks.get(item_id, "Near mint or better"), "gone": self.gone.get(item_id),
                "images": [f"https://i.ebayimg.com/{item_id}.jpg"]}


class InTheScan(CycleDB):
    def setUp(self):
        super().setUp()
        self.settings = load_settings()
        self.verdicts, self.checked = {}, []

    def checker(self, label, title, urls, settings):
        item = urls[0].rsplit("/", 1)[1][:-4]
        self.checked.append(item)
        a = self.verdicts.get(item, answers())
        if isinstance(a, Exception):
            raise a
        v, reason = photos.verdict(a, settings)
        return {"verdict": v, "reason": reason, "detail": a, "low": a["psa_low"], "high": a["psa_high"]}

    def scan(self, scout):
        return run.cycle(con=self.con, scouts=[scout], force=True, dry=True, log=lambda *_: None,
                         settings=self.settings, checker=self.checker)

    def seeded(self, extra, **kw):
        seed = [listing("k0", "Aquapolis Kingdra H14/H32 Holo", 230.0)]
        scout = FilterScout([seed, seed + extra], **kw)
        self.scan(scout); notify.SENT.clear(); scout.detail_calls.clear()
        return scout

    def tier(self, item_id):
        r = db.one(self.con, "SELECT tier, reason FROM listings WHERE item_id=?", (item_id,))
        return r["tier"], r["reason"]

    def deals(self):
        return [p for p in notify.SENT if p["title"].startswith("DEAL")]

    def test_only_photo_passed_near_mint_raw_cards_push(self):
        lugia = "Aquapolis Crystal Lugia 149/147 Holo"
        scout = self.seeded([
            listing("pass", lugia, 300.0),
            listing("slab", lugia + " PSA 9", 300.0),
            listing("lp", lugia, 300.0),
            listing("crease", lugia, 300.0),
            listing("unsure", lugia, 300.0),
            listing("dear", lugia, 900.0),           # over value: never costs a lookup
            listing("sold", lugia, 300.0),
            listing("titlelp", lugia + " LP", 300.0),
        ], picks={"lp": "Lightly played (Excellent)"}, gone={"sold": "Sold on eBay on Oct 30"})
        self.verdicts = {"crease": answers(crease="yes"), "unsure": answers(back_shown=False)}
        self.settings["condition_filter"]["photo_check"]["max_per_run"] = 10
        self.scan(scout)

        self.assertEqual(sorted(scout.detail_calls), ["crease", "lp", "pass", "sold", "unsure"],
                         "one lookup each gives seller pick, photos and availability; slabs, LP titles and dear ones cost none")
        self.assertEqual(sorted(self.checked), ["crease", "pass", "unsure"])
        self.assertEqual(self.tier("pass")[0], "DEAL")
        self.assertEqual(self.tier("slab"), ("REJECT", "graded (PSA 9): we buy raw cards only"))
        self.assertEqual(self.tier("lp"), ("REJECT", "lightly played: we buy near mint only"))
        self.assertEqual(self.tier("titlelp"), ("REJECT", "lightly played: we buy near mint only"))
        self.assertTrue(self.tier("crease")[1].startswith("photo check: crease"))
        self.assertEqual(self.tier("unsure")[0], "WATCH")
        self.assertEqual(self.tier("sold"), ("REJECT", "Sold on eBay on Oct 30"))
        self.assertEqual(self.tier("dear")[0], "SEEN")

        deals = self.deals()
        self.assertEqual(len(deals), 1, notify.SENT)
        self.assertIn("after Whatnot fees", deals[0]["title"])
        self.assertIn("Photos pass", deals[0]["message"])
        self.assertIn("not checked on Collectr", deals[0]["message"])
        self.assertEqual({r["item_id"] for r in db.open_deals(self.con)}, {"pass"})

        notify.SENT.clear(); scout.detail_calls.clear(); self.checked.clear()
        self.scan(scout)
        self.assertEqual((self.deals(), self.checked), ([], []), "each listing is looked at and pushed once")
        self.assertEqual(scout.detail_calls, [], "seller picks are read once")

    def test_five_a_day_best_profit_first(self):
        prices = [300, 280, 260, 240, 220, 200, 320]
        scout = self.seeded([listing(f"c{i}", "Aquapolis Crystal Lugia 149/147 Holo", float(p)) for i, p in enumerate(prices)])
        self.settings["condition_filter"]["photo_check"]["max_per_run"] = 10
        self.scan(scout)
        pushed = db.rows(self.con, "SELECT item_id FROM alerts WHERE pushed=1 AND kind != 'summary'")
        self.assertEqual(sorted(r["item_id"] for r in pushed), ["c1", "c2", "c3", "c4", "c5"], "cheapest = best profit")
        self.assertEqual(len(self.deals()), 5)
        self.assertFalse([p for p in notify.SENT if "more deals" in p["title"]], "the day cap doesn't buzz either")
        self.assertEqual(len(db.open_deals(self.con)), 7, "the other two wait on the Deals page")

    def test_photo_checks_per_run_and_a_broken_checker_stops_early(self):
        scout = self.seeded([listing(f"p{i}", "Aquapolis Crystal Lugia 149/147 Holo", 300.0 - i) for i in range(6)])
        self.scan(scout)
        self.assertEqual(len(self.checked), S["condition_filter"]["photo_check"]["max_per_run"])

        self.checked.clear()
        self.verdicts = {f"p{i}": photos.PhotoError("Not logged in") for i in range(6)}
        r = self.scan(scout)
        self.assertEqual(len(self.checked), 1, "one failure stops the stage for this scan")
        self.assertTrue(any("photo check failed" in e for e in r["errors"]))
        self.assertTrue(any(k == "photos_down" for k, _, _ in watchdog.issues(self.con, self.settings, r)))
        g = db.one(self.con, "SELECT photo_attempts, photo_error FROM grades WHERE photo_attempts IS NOT NULL AND photo_error IS NOT NULL")
        self.assertEqual(g["photo_attempts"] or 0, 0, "Claude Code being down doesn't use up a listing's tries")

    def test_one_listings_bad_photos_dont_stop_the_others_or_alarm(self):
        scout = self.seeded([listing(f"b{i}", "Aquapolis Crystal Lugia 149/147 Holo", 300.0 - i) for i in range(3)])
        self.verdicts = {"b0": photos.ListingPhotoError("a listing photo isn't an image")}
        r = self.scan(scout)
        self.assertEqual(sorted(self.checked), ["b0", "b1", "b2"])
        self.assertFalse(any(k == "photos_down" for k, _, _ in watchdog.issues(self.con, self.settings, r)))
        self.assertEqual(self.tier("b0"), ("WATCH", "waiting for the photo check"), "retried next scan")

    def test_sold_while_on_deals_goes_to_history(self):
        scout = self.seeded([listing("s1", "Aquapolis Crystal Lugia 149/147 Holo", 300.0)])
        self.settings["condition_filter"]["lookups_per_run"] = 0
        self.scan(scout)
        self.settings["condition_filter"]["lookups_per_run"] = 30
        self.con.execute("INSERT INTO alerts(item_id, kind, tier, sent_at, pushed) VALUES('s1', 'new', 'DEAL', ?, 1)", (db.now(),))
        scout.gone = {"s1": "Sold on eBay on Nov 01"}
        self.scan(scout)
        a = db.one(self.con, "SELECT decision, outcome FROM alerts WHERE item_id='s1'")
        self.assertEqual((a["decision"], a["outcome"]), ("gone", "Sold on eBay on Nov 01"))

    def test_a_later_deal_is_checked_for_sale_again_before_it_buzzes(self):
        scout = self.seeded([listing("pd", "Aquapolis Crystal Lugia 149/147 Holo", 460.0)])   # near value: no lookup
        self.con.execute("""INSERT INTO grades(item_id, seller_condition, seller_text, seller_checked_at, photo_verdict,
            photo_reason, avail_at) VALUES('pd', 'NM', 'Near mint or better', '2026-11-01 00:00:00', 'pass', 'clean',
            '2026-11-01 00:00:00')""")
        self.con.commit()
        scout.gone = {"pd": "Sold on eBay on Nov 01"}
        scout.batches.append([dict(x, price=300.0) for x in scout.batches[1]])   # price drop makes it a deal
        scout.calls = 4 * (len(scout.batches) - 1)
        self.scan(scout)
        self.assertEqual(scout.detail_calls, ["pd"])
        self.assertEqual(self.deals(), [])
        self.assertEqual(self.tier("pd"), ("REJECT", "Sold on eBay on Nov 01"))

    def test_lookups_never_eat_the_searches(self):
        self.settings["ebay"]["daily_call_budget"] = 30    # every remaining scan's searches don't fit: no lookups
        scout = self.seeded([listing("n1", "Aquapolis Crystal Lugia 149/147 Holo", 300.0)])
        r = self.scan(scout)
        self.assertEqual(scout.detail_calls, [])
        self.assertTrue(any("reserved for searches" in e for e in r["errors"]))
        self.assertEqual(self.tier("n1"), ("WATCH", "checking the seller's condition"))

    def test_a_would_be_deal_that_drops_out_of_search_still_gets_checked(self):
        self.settings["ebay"]["daily_call_budget"] = 30
        scout = self.seeded([listing("n1", "Aquapolis Crystal Lugia 149/147 Holo", 300.0)])
        self.scan(scout)                                   # lookups paused: stays waiting
        self.settings["ebay"]["daily_call_budget"] = 5000
        scout.batches.append(scout.batches[0])             # n1 no longer in the search results
        scout.calls = 4 * (len(scout.batches) - 1)
        self.scan(scout)
        self.assertEqual(scout.detail_calls, ["n1"])
        self.assertEqual(self.tier("n1")[0], "DEAL")

    def test_an_old_deal_still_on_the_deals_page_is_checked_but_not_pushed_again(self):
        scout = self.seeded([listing("old", "Aquapolis Crystal Lugia 149/147 Holo", 300.0)])
        self.settings["condition_filter"]["lookups_per_run"] = 0
        self.scan(scout)                                   # found, still waiting for its check
        self.settings["condition_filter"]["lookups_per_run"] = 30
        # as if it buzzed Ben under the old rules and dropped out of search days ago
        self.con.execute("UPDATE listings SET pushed_tier='DEAL', last_seen='2026-10-01 00:00:00' WHERE item_id='old'")
        self.con.execute("INSERT INTO alerts(item_id, kind, tier, sent_at, pushed) VALUES('old', 'new', 'DEAL', ?, 1)", (db.now(),))
        self.con.commit()
        scout.batches.append(scout.batches[0]); scout.calls = 4 * (len(scout.batches) - 1)
        self.scan(scout)
        self.assertEqual(self.checked, ["old"])
        self.assertEqual(self.tier("old")[0], "DEAL")
        self.assertEqual(self.deals(), [])
        self.assertEqual({r["item_id"] for r in db.open_deals(self.con)}, {"old"})

    def test_seeded_listings_never_cost_a_lookup_or_push(self):
        seed = [listing("old", "Aquapolis Crystal Lugia 149/147 Holo", 300.0)]
        scout = FilterScout([seed])
        self.scan(scout)
        self.assertIn("1 would be deals", next(p["message"] for p in notify.SENT if "seeded" in p["title"]))
        self.scan(scout)
        self.assertEqual((scout.detail_calls, self.checked, self.deals()), ([], [], []))


class Migration(unittest.TestCase):
    def test_old_seller_picks_count_as_read(self):
        import sqlite3
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        old = sqlite3.connect(path)
        old.execute("CREATE TABLE grades (item_id TEXT PRIMARY KEY, low INTEGER, high INTEGER, source TEXT, "
                    "seller_condition TEXT, seller_text TEXT, note TEXT, checked_at TEXT)")
        old.execute("INSERT INTO grades VALUES ('a', 7, 8, 'seller', 'NM', 'Near mint or better', NULL, '2026-10-31 00:35:09')")
        old.commit(); old.close()
        con = db.connect(path)
        self.assertEqual(db.one(con, "SELECT seller_checked_at FROM grades")["seller_checked_at"], "2026-10-31 00:35:09")
        db.connect(path)   # idempotent


class Recheck(CycleDB):
    def test_capped_per_hour_longest_unchecked_first(self):
        s = load_settings()
        s["ebay"]["recheck_max_per_hour"] = 2
        for i in range(4):
            self.con.execute("INSERT INTO listings(item_id, source, marketplace, title, tier) VALUES(?,?,?,?,?)",
                             (f"r{i}", "fake", "EBAY_US", "Lugia", "DEAL"))
            self.con.execute("INSERT INTO alerts(item_id, kind, tier, sent_at) VALUES(?,?,?,?)", (f"r{i}", "new", "DEAL", db.now()))
        self.con.execute("INSERT INTO grades(item_id, avail_at) VALUES('r0', '2026-11-01 10:00:00'), ('r1', '2026-11-01 09:00:00')")
        scout = FilterScout([[]])
        run.recheck_open(self.con, {"fake": scout}, s, {"calls": 0, "errors": []}, log=lambda *_: None, force=True)
        self.assertEqual(sorted(scout.detail_calls), ["r2", "r3"], "never-checked first, two per hour")


if __name__ == "__main__":
    unittest.main()
