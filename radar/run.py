"""One cycle: refresh catalog + FX when due -> scouts fetch -> evaluate every listing -> push -> watchdog.
launchd calls this every few minutes; the cycle itself honours settings.scan_interval_min."""
import json, os, time
import urllib.error
from . import catalog, db, decide, fx, grading, notify, photos, pipeline, watchdog
from .config import load_env, load_settings, load_targets
from .decide import RANK
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


def spare_calls(con, settings, name, run):
    """eBay calls free for lookups (seller condition, photo check, recheck) after reserving a full search for every
    scan still to come today. Searches always come first."""
    left = 1440 - (int(time.strftime("%H")) * 60 + int(time.strftime("%M")))
    reserve = run.get("search_need", 0) * int(left // settings["scan_interval_min"])
    return settings["ebay"]["daily_call_budget"] - db.calls_today(con, name) - reserve


def cycle(con=None, scouts=None, force=False, dry=False, log=print, settings=None, checker=None):
    env = load_env()
    settings, targets = settings or load_settings(), load_targets()
    filtering = decide.filtering(settings)
    push_tiers = decide.push_tiers(settings)
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
        if metered:
            run["search_need"] = run.get("search_need", 0) + len(jobs)
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
    detailers = {s.name: s for s in scouts if hasattr(s, "details")}
    cards_cache, pending, seeded_deals, seeded_items = {}, [], 0, 0
    if found and not rates:
        run["errors"].append("no FX rates: listings stored but not scored")
    for item_id, it in found.items() if rates else []:
        t = by_id[it["target_id"]]
        cards = cards_cache.setdefault(t["group_id"], pipeline.cards_for(con, t["group_id"]))
        prev = db.one(con, "SELECT price, tier, pushed_tier FROM listings WHERE item_id=?", (item_id,))
        res = pipeline.evaluate(con, it, t, cards, rates, settings)
        seeding = not prev and not (scopes_of[item_id] & seeded_scopes)
        pushed_before = RANK.get((prev or {}).get("pushed_tier") or "REJECT", 0)
        would_push = lambda r: r["tier"] in push_tiers and RANK[r["tier"]] > pushed_before
        detailer, gone = detailers.get(it["source"]), None
        if filtering:   # seller pick and photos are read later, in condition_stage
            pipeline.save(con, it, res)
            if not prev:
                run["new"] += 1
            if seeding:   # already for sale on day one: stored, never pushed (SPEC "Seeding")
                seeded_items += 1
                seeded_deals += res["_needs"] is not None   # would-be deals; never checked or pushed
                con.execute("UPDATE listings SET pushed_tier='DEAL' WHERE item_id=?", (item_id,))
            elif would_push(res):
                pending.append((item_id, "new" if not prev else ("price_drop" if it["price"] < prev["price"] else "upgrade")))
            continue
        # about to buzz Ben: read the listing's own record. Search can return listings that already sold, and the
        # seller's "Card Condition" pick (read once) can lower the value and gives the grade range.
        if detailer and not seeding and would_push(res) and db.calls_today(con, detailer.name) < budget:
            try:
                d = detailer.details(item_id, it["marketplace"])
                db.count_call(con, detailer.name); run["calls"] += 1
                gone = d.get("gone")
                g = grading.get(con, item_id)
                if not res["grade"] and not (g and g["seller_text"]):
                    grading.record_seller(con, item_id, d.get("seller_condition"), settings)
                    res = pipeline.evaluate(con, it, t, cards, rates, settings)
            except ScoutError as e:
                run["errors"].append(str(e))
        pipeline.save(con, it, res)
        if not prev:
            run["new"] += 1
        if seeding:
            seeded_items += 1
        if would_push(res):
            kind = "new" if not prev else ("price_drop" if it["price"] < prev["price"] else "upgrade")
            if gone:   # never buzz for something that can't be bought; it goes straight to History
                _record_alert(con, item_id, kind=kind, pushed=0)
                db.mark_gone(con, item_id, gone)
            elif seeding:
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

    # ---- 3. seller's condition + photo check for would-be deals, best flip first ------------------
    if filtering:
        queued = {i for i, _ in pending}
        for item_id in condition_stage(con, detailers, settings, run, checker or photos.check, log):
            already = db.one(con, "SELECT pushed_tier FROM listings WHERE item_id=?", (item_id,))["pushed_tier"]
            on_deals = db.one(con, "SELECT 1 FROM alerts WHERE item_id=? AND decision='open'", (item_id,))
            if item_id not in queued and not on_deals and RANK.get(already or "REJECT", 0) < RANK["DEAL"]:   # never buzz twice
                pending.append((item_id, "new"))

    # ---- 4. push, best first, under the hourly (and, filtering, daily) cap --------------------------
    cap = settings["notify"]["max_pushes_per_hour"]
    hour_ago = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))
    sent = lambda since: db.one(con, "SELECT COUNT(*) n FROM alerts WHERE pushed=1 AND kind!='summary' AND sent_at >= ?", (since,))["n"]
    room = cap - sent(hour_ago)
    day_room = settings["notify"].get("max_pushes_per_day", 10 ** 6) - sent(db.today() + " 00:00:00") if filtering else 10 ** 6
    rank_col = "-COALESCE(flip_usd, 0)" if filtering else "COALESCE(gap_pct, 0)"
    pending.sort(key=lambda p: db.one(con, f"SELECT {rank_col} g FROM listings WHERE item_id=?", (p[0],))["g"])
    held = 0
    for item_id, kind in pending:
        if room <= 0 or day_room <= 0:   # waits on the Deals page instead of buzzing Ben
            _record_alert(con, item_id, kind=kind, pushed=0)
            held += room <= 0 and day_room > 0
            continue
        # SPEC "Sold or ended listings": eBay's own record, read recently, says it's still for sale
        if filtering and not still_for_sale(con, item_id, detailers, settings, run):
            continue
        if _push_deal(con, item_id, kind, base_url, dry, run):
            room -= 1; day_room -= 1
    if held:
        _system_push(f"Card Radar: {held} more deals", f"Hourly cap of {cap} reached. They're on the dashboard.", base_url, dry, run)
    if seeded_items:
        _system_push("Card Radar: new market seeded",
                     f"Stored {seeded_items} listings already for sale without checking or pushing them. "
                     f"{seeded_deals} would be deals if near mint; they're in Leads." if filtering else
                     f"Stored {seeded_items} listings already for sale without pushing them. {seeded_deals} are deals; see the dashboard.",
                     base_url, dry, run)

    recheck_open(con, detailers, settings, run, log)

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


WAITING = {"checking the seller's condition": "seller", "waiting for the photo check": "photos"}
FRESH_MIN = 30   # a "still for sale" read this recent is good enough to push on


def still_for_sale(con, item_id, detailers, settings, run):
    """Before a push: re-read eBay's record unless it was read in the last FRESH_MIN minutes. Gone -> History, no push.
    If the lookup can't be made (budget, error), the push goes ahead: the hourly recheck catches it later."""
    g = db.one(con, "SELECT avail_at, gone FROM grades WHERE item_id=?", (item_id,)) or {}
    if g.get("gone"):
        return False
    if g.get("avail_at") and _hours_since(g["avail_at"]) * 60 < FRESH_MIN:
        return True
    l = db.one(con, "SELECT source, marketplace FROM listings WHERE item_id=?", (item_id,))
    det = detailers.get(l["source"])
    if not det or spare_calls(con, settings, det.name, run) <= 0:
        return True
    try:
        d = det.details(item_id, l["marketplace"])
    except ScoutError as e:
        run["errors"].append(str(e))
        return True
    finally:
        db.count_call(con, det.name); run["calls"] += 1
    grading.record_availability(con, item_id, d.get("gone"))
    if d.get("gone"):
        db.mark_gone(con, item_id, d["gone"])
        rates = fx.latest(con)[0]
        pipeline.rescore(con, load_targets(), rates, settings, where="item_id=?", args=(item_id,))
        return False
    return True


def condition_stage(con, detailers, settings, run, checker, log=print, limit=None):
    """SPEC "Condition filter" steps 2-4 for would-be deals seen in the last day, best Whatnot profit first. One eBay
    lookup per listing gives the seller's condition, the photos and whether it's still for sale; a near-mint one then
    gets its photo check straight away. Returns the item_ids that are now DEALs.
    limit (the CLI's catch-up run) replaces the per-run and per-day photo limits and the search reserve."""
    cfg = settings["condition_filter"]["photo_check"]
    if not detailers:
        return []
    done_today = db.one(con, "SELECT COUNT(*) n FROM grades WHERE photo_at >= ?", (db.today() + " 00:00:00",))["n"]
    photo_room = limit if limit is not None else min(cfg["max_per_run"], cfg["max_per_day"] - done_today)
    lookups = limit if limit is not None else settings["condition_filter"].get("lookups_per_run", 30)
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 86400))
    todo = db.rows(con, f"""SELECT l.*, c.name AS card_name, c.number AS card_number, c.set_name, c.subtype
        FROM listings l LEFT JOIN cards c USING(card_key)
        WHERE l.reason IN ({",".join("?" * len(WAITING))})
          AND ((COALESCE(l.pushed_tier, '') != 'DEAL' AND l.last_seen >= ?)            -- could still push
               OR EXISTS (SELECT 1 FROM alerts a WHERE a.item_id = l.item_id AND a.decision = 'open'))   -- on Deals
        ORDER BY COALESCE(l.flip_usd, 0) DESC""", (*WAITING, since))
    targets, rates = load_targets(), fx.latest(con)[0]
    rescore = lambda item_id: pipeline.rescore(con, targets, rates, settings, where="item_id=?", args=(item_id,))
    passed = []
    for l in todo:
        det = detailers.get(l["source"])
        if not det:
            continue
        if WAITING[l["reason"]] == "photos" and photo_room <= 0:
            continue
        if lookups <= 0:
            break
        if db.calls_today(con, det.name) >= settings["ebay"]["daily_call_budget"] or (
                limit is None and spare_calls(con, settings, det.name, run) <= 0):
            run["errors"].append("condition checks paused: today's eBay calls are reserved for searches")
            break
        try:
            d = det.details(l["item_id"], l["marketplace"])
            db.count_call(con, det.name); run["calls"] += 1; lookups -= 1
        except ScoutError as e:   # still a call, and it still uses this scan's lookups
            db.count_call(con, det.name); run["calls"] += 1; lookups -= 1
            run["errors"].append(str(e))
            continue
        grading.record_availability(con, l["item_id"], d.get("gone"))
        if d.get("gone"):
            db.mark_gone(con, l["item_id"], d["gone"])   # an old alert still on Deals goes to History as gone
        if not grading.get(con, l["item_id"]).get("seller_checked_at"):
            grading.record_seller(con, l["item_id"], d.get("seller_condition"), settings)
        con.commit()
        rescore(l["item_id"])
        now = db.one(con, "SELECT reason FROM listings WHERE item_id=?", (l["item_id"],))["reason"]
        if now == "waiting for the photo check" and photo_room > 0 and cfg.get("enabled"):
            photo_room -= 1
            label = f"{l['card_name']} {l['card_number']} · {l['set_name']} · {l['subtype']}" if l["card_name"] else l["title"]
            try:
                r = checker(label, l["title"], d.get("images") or [l["image"]], settings)
                grading.record_photo_check(con, l["item_id"], r["verdict"], r["reason"], r["detail"], r["low"], r["high"])
                db.agent_ok(con, "photos", f"{r['verdict']} · {l['title'][:50]}")
                log(f"photos: {r['verdict']} · {r['reason'][:80]} · {l['title'][:50]}")
            except photos.ListingPhotoError as e:   # this listing's photos only: skip it, keep going
                grading.record_photo_error(con, l["item_id"], e)
                con.commit(); rescore(l["item_id"])
                continue
            except (photos.PhotoError, OSError, ValueError) as e:
                grading.record_photo_error(con, l["item_id"], e, counts=False)
                db.agent_error(con, "photos", e); run["errors"].append(f"photo check failed: {e}")
                con.commit(); rescore(l["item_id"])
                break   # Claude Code itself (signed out, offline): don't burn every listing's attempts
            con.commit(); rescore(l["item_id"])
        if db.one(con, "SELECT tier FROM listings WHERE item_id=?", (l["item_id"],))["tier"] == "DEAL":
            passed.append(l["item_id"])
    return passed


def recheck_open(con, detailers, settings, run, log=print, force=False):
    """Look up open Deals listings again, every recheck_open_min minutes, longest-unchecked first and at most
    recheck_max_per_hour. Sold or ended ones move to History. Search alone can't tell: it can keep returning a sold
    listing, and it drops older ones that are still for sale."""
    if not detailers:
        return 0
    last = db.one(con, "SELECT last_ok FROM agents WHERE agent='recheck'")
    if not force and last and _hours_since(last["last_ok"]) * 60 < settings["ebay"].get("recheck_open_min", 60) - 0.5:
        return 0
    checked, gone = 0, 0
    deals = db.open_deals(con)
    seen = {r["item_id"]: r["avail_at"] or "" for r in db.rows(con, "SELECT item_id, avail_at FROM grades")}
    deals.sort(key=lambda r: seen.get(r["item_id"], ""))
    for r in deals[:settings["ebay"].get("recheck_max_per_hour", 40)]:
        det = detailers.get(r["source"])
        if not det:
            continue
        if spare_calls(con, settings, det.name, run) <= 0 and not force:
            run["errors"].append(f"recheck paused: today's eBay calls are reserved for searches ({checked} checked)")
            break
        try:
            d = det.details(r["item_id"], r["marketplace"])
            db.count_call(con, det.name); run["calls"] += 1; checked += 1
        except ScoutError as e:
            run["errors"].append(str(e))
            continue
        grading.record_availability(con, r["item_id"], d.get("gone"))
        if d.get("gone"):
            db.mark_gone(con, r["item_id"], d["gone"]); gone += 1
            log(f"recheck: gone · {d['gone']} · {r['title'][:60]}")
    db.agent_ok(con, "recheck", f"{checked} open deals checked, {gone} gone")
    con.commit()
    return gone


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
    target = next((t for t in load_targets() if card and t["id"] == card["target_id"]), None)
    title, message = notify.deal_message(l, card, kind, target and target["label"], grading.get(con, item_id))
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
