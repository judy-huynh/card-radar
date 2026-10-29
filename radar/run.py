"""One cycle: refresh catalog + FX when due -> scouts fetch -> evaluate every listing -> push -> watchdog.
launchd calls this every few minutes; the cycle itself honours settings.scan_interval_min."""
import json, os, time
from . import catalog, db, fx, notify, pipeline, watchdog
from .config import load_env, load_settings, load_targets
from .decide import PUSH_TIERS, RANK
from .scouts import ScoutError
from .scouts.ebay import EbayScout
from .scouts.tcgplayer import TcgplayerScout


def _hours_since(ts):
    return (time.time() - time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S"))) / 3600 if ts else 1e9


def refresh_reference_data(con, targets, log):
    if (catalog.age_hours(con) or 1e9) > 20:
        try:
            n = catalog.refresh(con, targets)
            db.agent_ok(con, "catalog", f"{n} card variants")
            log(f"catalog: {n} card variants refreshed")
        except Exception as e:
            db.agent_error(con, "catalog", e); log(f"catalog FAILED: {e}")
    _, fetched = fx.latest(con)
    if _hours_since(fetched) > 20:
        try:
            rates = fx.refresh(con)
            db.agent_ok(con, "fx", f"1 USD = {rates['CAD']:.4f} CAD")
            log(f"fx: 1 USD = {rates['CAD']} CAD")
        except Exception as e:
            db.agent_error(con, "fx", e); log(f"fx FAILED: {e}")
    con.commit()


def cycle(con=None, scouts=None, force=False, dry=False, log=print):
    env = load_env()
    settings, targets = load_settings(), load_targets()
    con = con or db.connect()
    base_url = env.get("DASHBOARD_URL", "http://localhost:8790").rstrip("/")

    last = db.one(con, "SELECT started FROM runs ORDER BY id DESC LIMIT 1")
    if not force and last and _hours_since(last["started"]) * 60 < settings["scan_interval_min"] - 0.5:
        return {"skipped": True}

    run = {"started": db.now(), "jobs": 0, "failed_jobs": 0, "calls": 0, "results": 0, "new": 0, "pushes": 0, "errors": []}
    refresh_reference_data(con, targets, log)
    rates, _ = fx.latest(con)

    if scouts is None:
        cid, secret = env.get("EBAY_CLIENT_ID"), env.get("EBAY_CLIENT_SECRET")
        scouts = [EbayScout(cid, secret, settings)] if cid and secret else []
        run["no_keys"] = not scouts
        if settings.get("tcgplayer", {}).get("enabled", True):
            scouts.append(TcgplayerScout(con))

    # ---- 1. fetch: every job, storing shipping quotes per destination --------------------------
    found, scopes_of, ran_scopes = {}, {}, set()
    budget = settings["ebay"]["daily_call_budget"]
    for scout in scouts:
        jobs = scout.plan(targets)
        metered = getattr(scout, "counts_against_budget", lambda: True)()
        room = budget - db.calls_today(con, scout.name) if metered else len(jobs)
        if len(jobs) > room:
            run["errors"].append(f"{scout.name}: budget allows {max(room, 0)} of {len(jobs)} searches")
            jobs = jobs[:max(room, 0)]
        for job in jobs:
            run["jobs"] += 1
            try:
                items = scout.run(job)
                if metered:
                    db.count_call(con, scout.name); run["calls"] += 1
            except ScoutError as e:
                run["failed_jobs"] += 1; run["errors"].append(str(e)); run.setdefault("first_error", str(e))
                db.agent_error(con, f"scout:{job.marketplace}", e)
                if "sign-in" in str(e):
                    run["failed_jobs"] += len(jobs) - jobs.index(job) - 1
                    break
                continue
            ran_scopes.add(job.scope)
            db.agent_ok(con, f"scout:{job.marketplace}", f"{len(items)} results")
            run["results"] += len(items)
            for it in items:
                con.execute("INSERT OR REPLACE INTO quotes(item_id, dest, ship, ship_currency, ships, seen) VALUES(?,?,?,?,1,?)",
                            (it["item_id"], it["dest"], it["ship"], it["ship_currency"], db.now()))
                found[it["item_id"]] = it
                scopes_of.setdefault(it["item_id"], set()).add(job.scope)
    seeded_scopes = {r["scope"] for r in db.rows(con, "SELECT scope FROM scopes")}
    con.commit()

    # ---- 2. evaluate every unique listing ---------------------------------------------------------
    by_id = {t["id"]: t for t in targets}
    cards_cache, pending, seeded_deals, seeded_items = {}, [], 0, 0
    if found and not rates:
        run["errors"].append("no FX rates: listings stored but not scored")
    for item_id, it in found.items() if rates else []:
        t = by_id[it["target_id"]]
        cards = cards_cache.setdefault(t["group_id"], pipeline.cards_for(con, t["group_id"]))
        prev = db.one(con, "SELECT price, tier, pushed_tier FROM listings WHERE item_id=?", (item_id,))
        res = pipeline.evaluate(con, it, t, cards, rates, settings)
        pipeline.save(con, it, res)
        if not prev:
            run["new"] += 1
        seeding = not prev and not (scopes_of[item_id] & seeded_scopes)
        if seeding:
            seeded_items += 1
        if res["tier"] in PUSH_TIERS and RANK[res["tier"]] > RANK.get((prev or {}).get("pushed_tier") or "REJECT", 0):
            kind = "new" if not prev else ("price_drop" if it["price"] < prev["price"] else "upgrade")
            if seeding:
                seeded_deals += 1
                _record_alert(con, item_id, kind="seeded", pushed=0)
            else:
                pending.append((item_id, kind))
    for scout in scouts:
        if hasattr(scout, "finalize"):
            scout.finalize(con, found)
    for scope in ran_scopes - seeded_scopes:   # an empty first search still counts: later finds are genuinely new
        con.execute("INSERT OR IGNORE INTO scopes(scope, seeded_at) VALUES(?,?)", (scope, db.now()))
    con.commit()

    # ---- 3. push, best gap first, under the hourly cap -----------------------------------------
    cap = settings["notify"]["max_pushes_per_hour"]
    hour_ago = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))
    room = cap - db.one(con, "SELECT COUNT(*) n FROM alerts WHERE pushed=1 AND kind!='summary' AND sent_at >= ?", (hour_ago,))["n"]
    pending.sort(key=lambda p: db.one(con, "SELECT COALESCE(gap_pct, 0) g FROM listings WHERE item_id=?", (p[0],))["g"])
    held = 0
    for item_id, kind in pending:
        if room <= 0:
            _record_alert(con, item_id, kind=kind, pushed=0); held += 1
            continue
        if _push_deal(con, item_id, kind, base_url, dry, run):
            room -= 1
    if held:
        _system_push(f"Card Radar: {held} more deals", f"Hourly cap of {cap} reached. They're on the dashboard.", base_url, dry, run)
    if seeded_items:
        _system_push("Card Radar: new market seeded",
                     f"Stored {seeded_items} listings already for sale without pushing them. {seeded_deals} are deals; see the dashboard.",
                     base_url, dry, run)

    run["finished"] = db.now()
    con.execute("INSERT INTO runs(started, finished, calls, results, new_listings, pushes, errors, status) VALUES(?,?,?,?,?,?,?,?)",
                (run["started"], run["finished"], run["calls"], run["results"], run["new"], run["pushes"],
                 json.dumps(run["errors"][:20]), "ok" if not run["errors"] else "errors"))
    if scouts:
        db.agent_ok(con, "decider", f"{run['new']} new listings scored")
    con.commit()

    watchdog.check(con, settings, run, base_url, dry=dry)
    try:
        watchdog.digest(con, settings, base_url, dry=dry)
    except Exception as e:
        db.agent_error(con, "notifier", e)
    log(f"cycle: {run['calls']} searches, {run['results']} results, {run['new']} new, {run['pushes']} pushes, {len(run['errors'])} errors")
    for e in run["errors"][:10]:
        log("  ! " + e)
    return run


def _record_alert(con, item_id, kind, pushed, title=None, message=None):
    l = db.one(con, "SELECT tier, gap_pct, landed_usd, value_usd FROM listings WHERE item_id=?", (item_id,))
    cur = con.execute("""INSERT INTO alerts(item_id, kind, tier, sent_at, title, message, gap_pct, landed_usd, value_usd, pushed)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (item_id, kind, l["tier"], db.now(), title, message, l["gap_pct"], l["landed_usd"], l["value_usd"], pushed))
    con.execute("UPDATE listings SET pushed_tier=? WHERE item_id=?", (l["tier"], item_id))
    return cur.lastrowid


def _push_deal(con, item_id, kind, base_url, dry, run):
    l = db.one(con, "SELECT * FROM listings WHERE item_id=?", (item_id,))
    card = db.one(con, "SELECT * FROM cards WHERE card_key=?", (l["card_key"],))
    title, message = notify.deal_message(l, card, kind)
    alert_id = _record_alert(con, item_id, kind, pushed=0, title=title, message=message)
    big = l["gap_pct"] is not None and l["gap_pct"] <= -load_settings()["decide"]["big_deal_gap_pct"]
    try:
        notify.push(title, message, priority=5 if big else 4, tags=["moneybag"] if l["tier"] == "DEAL" else ["eyes"],
                    click=f"{base_url}/#alert-{alert_id}",
                    actions=[("Open listing", l["url"]), ("Dashboard", f"{base_url}/#alert-{alert_id}")], dry=dry)
        con.execute("UPDATE alerts SET pushed=1 WHERE id=?", (alert_id,))
        db.agent_ok(con, "notifier", f"last push {db.now()}")
        run["pushes"] += 1
        con.commit()
        return True
    except Exception as e:
        db.agent_error(con, "notifier", e); run["errors"].append(f"push failed: {e}")
        con.commit()
        return False


def _system_push(title, message, base_url, dry, run):
    try:
        notify.push(title, message, priority=3, tags=["information_source"], click=base_url, dry=dry)
    except Exception as e:
        run["errors"].append(f"push failed: {e}")
