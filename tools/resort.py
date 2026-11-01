#!/usr/bin/env python3
"""One-time re-sort of the Deals page under the condition filter (SPEC "Condition filter", Judy 2026-11-01).

  python3 tools/resort.py            show what would move (changes nothing)
  python3 tools/resort.py --apply    re-score, then move every open deal that doesn't meet the rules to History as
                                     "Passed: doesn't meet condition rules", with the reason. Nothing is deleted.

Run `python3 -m radar photos N` in between to photo-check the near-mint ones first; those that pass stay on Deals
(marked as already alerted, so Ben isn't buzzed again for them). Never pushes."""
import os, sqlite3, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radar import db, fx, pipeline                         # noqa: E402
from radar.config import load_settings, load_targets      # noqa: E402

WAITING = ("waiting for the photo check", "checking the seller's condition")


def main(apply):
    con = db.connect()
    if not apply:   # re-scoring writes, so the preview runs on a throwaway copy
        path = os.path.join(tempfile.mkdtemp(), "preview.db")
        con.backup(sqlite3.connect(path))
        con = db.connect(path)
    rates, _ = fx.latest(con)
    n = pipeline.rescore(con, load_targets(), rates, load_settings(), where="source != 'tcgplayer'")
    print(f"re-scored {n} listings")
    # what the Deals page showed: open alerts, except day-one seeded ones that weren't deals (those never showed there
    # and stay out of History). Uses the alert's own kind and tier, which re-scoring doesn't change.
    rows = db.rows(con, """SELECT a.id, l.item_id, l.tier, l.reason, l.title FROM alerts a JOIN listings l USING(item_id)
        WHERE a.decision = 'open' AND a.id IN (SELECT MAX(id) FROM alerts GROUP BY item_id)
          AND (a.kind != 'seeded' OR a.tier = 'DEAL')""")
    keep = [r for r in rows if r["tier"] == "DEAL"]
    wait = [r for r in rows if r["tier"] != "DEAL" and r["reason"] in WAITING]
    move = [r for r in rows if r["tier"] != "DEAL" and r["reason"] not in WAITING]
    print(f"{len(rows)} open: {len(keep)} stay on Deals, {len(wait)} still waiting for a check, {len(move)} move to History")
    reasons = {}
    for r in move:
        key = r["reason"].split(":")[0] if r["reason"] else "?"
        reasons[key] = reasons.get(key, 0) + 1
    for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:12]:
        print(f"  {v:4}  {k}")
    if not apply:
        return
    for r in move:
        con.execute("UPDATE alerts SET decision='filtered', decided_at=?, outcome=? WHERE id=?",
                    (db.now(), "Doesn't meet condition rules: " + (r["reason"] or ""), r["id"]))
    for r in keep + wait:   # Ben was already alerted to these: never buzz again for them
        con.execute("UPDATE listings SET pushed_tier='DEAL' WHERE item_id=?", (r["item_id"],))
    con.commit()
    print(f"moved {len(move)}; {len(keep)} kept; {len(wait)} left open until their check finishes")


if __name__ == "__main__":
    main("--apply" in sys.argv)
