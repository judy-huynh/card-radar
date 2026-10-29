"""Watchdog agent. Turns silent failures into pushes, with a cooldown so a broken feed doesn't spam,
and sends a once-a-day digest. The iMac being off overnight is normal and never alerts."""
import time
from . import catalog, db, fx, notify


def _due(con, key, cooldown_h):
    r = db.one(con, "SELECT last_sent FROM system_alerts WHERE key=?", (key,))
    if not r:
        return True
    return (time.time() - time.mktime(time.strptime(r["last_sent"], "%Y-%m-%d %H:%M:%S"))) / 3600 >= cooldown_h


def _mark(con, key):
    con.execute("INSERT OR REPLACE INTO system_alerts(key, last_sent) VALUES(?,?)", (key, db.now()))


def issues(con, settings, run):
    w, out = settings["watchdog"], []
    if run.get("no_keys"):
        out.append(("no_keys", "eBay keys missing", "Add EBAY_CLIENT_ID and EBAY_CLIENT_SECRET to .env. Nothing is being scanned."))
    if run.get("jobs") and run.get("failed_jobs") == run.get("jobs"):
        out.append(("scouts_down", "Scanning is failing", "Every marketplace search failed this cycle: " + (run.get("first_error") or "")))
    age = catalog.age_hours(con)
    if age is None or age > w["stale_values_h"]:
        out.append(("values_stale", "Card values are stale", f"TCGplayer prices last refreshed {'never' if age is None else f'{age:.0f} h ago'}. Deals can't be valued."))
    _, fetched = fx.latest(con)
    if not fetched:
        out.append(("fx_stale", "Exchange rates missing", "No FX rates, so landed cost can't be computed."))
    recent = db.rows(con, "SELECT results, calls FROM runs WHERE calls > 0 ORDER BY id DESC LIMIT ?", (w["zero_result_runs"],))
    if len(recent) == w["zero_result_runs"] and all(r["results"] == 0 for r in recent):
        out.append(("zero_results", "Searches return nothing", f"{w['zero_result_runs']} cycles in a row found zero listings. A query or the API may have changed."))
    budget = settings["ebay"]["daily_call_budget"]
    used = db.calls_today(con, "ebay")
    if used >= budget * w["budget_warn_pct"] / 100:
        out.append(("budget", "eBay call budget running low", f"{used:,} of {budget:,} calls used today."))
    return out


def check(con, settings, run, base_url, dry=False):
    found = issues(con, settings, run)
    for key, title, msg in found:
        if _due(con, key, 24 if key == "no_keys" else settings["watchdog"]["cooldown_h"]):
            try:
                notify.push("Card Radar: " + title, msg, priority=3, tags=["warning"], click=f"{base_url}/#system", dry=dry)
                _mark(con, key)
            except Exception as e:
                db.agent_error(con, "notifier", e)
    (db.agent_error if found else db.agent_ok)(con, "watchdog", "; ".join(t for _, t, _ in found) or "all clear")
    con.commit()
    return found


def digest(con, settings, base_url, dry=False):
    hour = settings["notify"]["digest_hour"]
    key = "digest:" + db.today()
    if int(time.strftime("%H")) < hour or not _due(con, key, 24 * 365):
        return False
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 86400))
    seen = db.one(con, "SELECT COUNT(*) n FROM listings WHERE first_seen >= ?", (since,))["n"]
    tiers = {r["tier"]: r["n"] for r in db.rows(con, "SELECT tier, COUNT(*) n FROM listings WHERE first_seen >= ? GROUP BY tier", (since,))}
    top = db.rows(con, """SELECT l.gap_pct, c.name, c.number FROM listings l LEFT JOIN cards c USING(card_key)
                          WHERE l.tier='DEAL' AND l.last_seen >= ? ORDER BY l.gap_pct LIMIT 3""", (since,))
    lines = [f"{seen} new listings · {tiers.get('DEAL', 0)} deals · {tiers.get('WATCH', 0)} watch · {tiers.get('REJECT', 0)} rejected"]
    lines += [f"{t['gap_pct']:.0f}% {t['name']} {t['number']}" for t in top]
    notify.push("Card Radar · last 24 h", "\n".join(lines), priority=2, tags=["bar_chart"], click=base_url, dry=dry)
    _mark(con, key)
    con.commit()
    return True
