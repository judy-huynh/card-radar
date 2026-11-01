#!/usr/bin/env python3
"""Grade ranges for listings on the Deals page.

  python3 tools/grade.py show                          open deals with their grade range
  python3 tools/grade.py photo ITEM LOW HIGH "note"    record a photo check (ITEM = the eBay number, e.g. 820213730900)
  python3 tools/grade.py backfill                      read the seller's eBay "Card Condition" for open deals that lack one

Writes to the live database unless RADAR_DB points elsewhere. Re-scores the touched listings; never pushes."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radar import db, fx, grading, pipeline                 # noqa: E402
from radar.config import load_env, load_settings, load_targets   # noqa: E402
from radar.scouts.ebay import EbayScout                     # noqa: E402


def item(con, short):
    rows = db.rows(con, "SELECT item_id FROM listings WHERE item_id = ? OR item_id LIKE ?", (short, f"%|{short}|%"))
    if len(rows) != 1:
        sys.exit(f"{short}: {'no listing' if not rows else 'more than one listing'} matches")
    return rows[0]["item_id"]


def rescore(con, ids):
    rates, _ = fx.latest(con)
    for i in ids:
        pipeline.rescore(con, load_targets(), rates, load_settings(), where="item_id=?", args=(i,))


def main(argv):
    con = db.connect()
    cmd = argv[1] if len(argv) > 1 else "show"
    if cmd == "photo" and len(argv) == 6:
        i = item(con, argv[2])
        grading.record_photos(con, i, int(argv[3]), int(argv[4]), argv[5])
        con.commit(); rescore(con, [i])
        print("recorded", i, f"PSA {argv[3]}-{argv[4]}")
    elif cmd == "backfill":
        env, settings = load_env(), load_settings()
        scout = EbayScout(env["EBAY_CLIENT_ID"], env["EBAY_CLIENT_SECRET"], settings)
        todo = [r for r in db.open_deals(con) if r["source"] == "ebay" and not r["grade"] and not grading.get(con, r["item_id"])]
        room = settings["ebay"]["daily_call_budget"] - db.calls_today(con, scout.name)
        for r in todo[:max(room, 0)]:
            d = scout.details(r["item_id"], r["marketplace"])
            db.count_call(con, scout.name)
            code = grading.record_seller(con, r["item_id"], d.get("seller_condition"), settings)
            print(f"{code or '?':3} {d.get('seller_condition') or '(none)':40.40} {r['title'][:50]}")
        con.commit(); rescore(con, [r["item_id"] for r in todo])
        print(len(todo), "listings checked")
    elif cmd == "show":
        for r in db.open_deals(con):
            r.update(grading.get(con, r["item_id"]) or {"low": None})
            r["gs"] = r.get("source")
            rng = f"PSA {r['low']}-{r['high']} {r['gs']}" if r["low"] is not None else (r["grade"] or "-")
            print(f"{rng:22} {r['title'][:70]}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
