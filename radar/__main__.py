"""CLI.
  python3 -m radar run [--force] [--dry]   one cycle (launchd calls this)
  python3 -m radar catalog                 refresh card values now
  python3 -m radar status                  agents, budget, last runs
  python3 -m radar test-push               send a test notification
"""
import sys
from . import catalog, db, fx, notify, run
from .config import load_env, load_targets


def main(argv):
    load_env()
    cmd = argv[1] if len(argv) > 1 else "run"
    if cmd == "run":
        run.cycle(force="--force" in argv, dry="--dry" in argv)
    elif cmd == "catalog":
        con = db.connect()
        n, rates = catalog.refresh(con, load_targets()), fx.refresh(con)
        db.agent_ok(con, "catalog", f"{n} card variants"); db.agent_ok(con, "fx", f"1 USD = {rates['CAD']:.4f} CAD")
        con.commit()
        print(n, "card variants ·", rates)
    elif cmd == "status":
        con = db.connect()
        for a in db.rows(con, "SELECT * FROM agents ORDER BY agent"):
            print(f"{a['agent']:<16} ok {a['last_ok'] or '-':<20} err {a['last_error_at'] or '-':<20} {a['detail'] or ''} {a['last_error'] or ''}")
        print("ebay calls today:", db.calls_today(con, "ebay"))
        for r in db.rows(con, "SELECT * FROM runs ORDER BY id DESC LIMIT 5"):
            print(r["started"], r["calls"], "calls", r["results"], "results", r["new_listings"], "new", r["pushes"], "pushes", r["status"])
    elif cmd == "test-push":
        notify.push("Card Radar test", "Notifications work. Deals will look like this, with buttons to the listing and the dashboard.",
                    actions=[("Dashboard", load_env().get("DASHBOARD_URL", "http://localhost:8790"))])
        print("sent")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
