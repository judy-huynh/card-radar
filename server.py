#!/usr/bin/env python3
"""Card Radar dashboard server (stdlib only). Serves dashboard/ and a JSON API over the shared SQLite store.
It has no login: reach it over Tailscale only, never expose it to the public internet."""
import json, os, sys, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from radar import db, fx, overrides, pipeline
from radar.config import ROOT, load_env, load_settings, load_targets, save_settings, save_targets

DASH = os.path.join(ROOT, "dashboard")
TARGET_FIELDS = {"push_gap_pct": float, "watch_gap_pct": float, "min_value_usd": float, "max_price_usd": float, "paused": bool}

LISTING_COLS = """l.item_id, l.marketplace, l.title, l.url, l.image, l.price, l.currency, l.buying, l.seller, l.feedback,
  l.feedback_pct, l.item_country, l.item_location, l.first_seen, l.last_seen, l.first_price, l.confidence, l.grade,
  l.flags, l.condition, l.value_usd, l.value_source, l.landed, l.best_dest, l.landed_usd, l.gap_pct, l.tier, l.reason,
  l.target_id, c.name, c.number, c.subtype, c.set_name, c.market AS tcg_market, c.tcg_url"""


def _decode(rows):
    for r in rows:
        for k in ("landed", "flags"):
            if k in r and isinstance(r[k], str):
                r[k] = json.loads(r[k] or "null")
    return rows


def state(con):
    settings, targets = load_settings(), load_targets()
    week = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 7 * 86400))
    day = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 86400))
    deals = _decode(db.rows(con, f"""SELECT a.id AS alert_id, a.kind, a.pushed, a.sent_at, a.decision, {LISTING_COLS}
        FROM alerts a JOIN listings l USING(item_id) LEFT JOIN cards c ON c.card_key = l.card_key
        WHERE a.decision='open' AND a.id IN (SELECT MAX(id) FROM alerts GROUP BY item_id)
          AND l.tier IN ('DEAL','LISTED')
          AND NOT (a.kind = 'seeded' AND l.tier != 'DEAL')   -- listings already for sale on day one live in Leads
        ORDER BY a.sent_at DESC LIMIT 300"""))
    feed = _decode(db.rows(con, f"""SELECT {LISTING_COLS} FROM listings l LEFT JOIN cards c ON c.card_key = l.card_key
        ORDER BY l.first_seen DESC LIMIT 250"""))
    log = db.rows(con, """SELECT a.id AS alert_id, a.sent_at, a.decision, a.decided_at, a.outcome, a.gap_pct, a.landed_usd,
        a.value_usd, l.title, c.name, c.number, l.url FROM alerts a JOIN listings l USING(item_id)
        LEFT JOIN cards c ON c.card_key = l.card_key WHERE a.decision != 'open' ORDER BY a.decided_at DESC LIMIT 60""")
    counts = {}
    for r in db.rows(con, "SELECT target_id, tier, COUNT(*) n FROM listings WHERE first_seen >= ? GROUP BY 1, 2", (week,)):
        counts.setdefault(r["target_id"], {})[r["tier"]] = r["n"]
    rates, fx_at = fx.latest(con)
    last = db.one(con, "SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    stats = {
        "deals_week": db.one(con, "SELECT COUNT(DISTINCT item_id) n FROM alerts WHERE sent_at >= ?", (week,))["n"],
        "bought_week": db.one(con, "SELECT COUNT(*) n FROM alerts WHERE decision='bought' AND decided_at >= ?", (week,))["n"],
        "passed_week": db.one(con, "SELECT COUNT(*) n FROM alerts WHERE decision='passed' AND decided_at >= ?", (week,))["n"],
        "new_24h": db.one(con, "SELECT COUNT(*) n FROM listings WHERE first_seen >= ?", (day,))["n"],
        "pushes_24h": db.one(con, "SELECT COUNT(*) n FROM alerts WHERE pushed=1 AND sent_at >= ?", (day,))["n"],
    }
    return {
        "example": False, "now": db.now(), "targets": targets, "target_counts": counts, "deals": deals, "feed": feed,
        "log": log, "stats": stats, "agents": db.rows(con, "SELECT * FROM agents ORDER BY agent"),
        "runs": [dict(r, errors=json.loads(r["errors"] or "[]")) for r in db.rows(con, "SELECT * FROM runs ORDER BY id DESC LIMIT 12")],
        "last_run": last, "interval_min": settings["scan_interval_min"],
        "push_every_listing": bool(settings["decide"].get("push_every_listing")),
        "fx": {"cad": rates and rates.get("CAD"), "at": fx_at},
        "budget": {"used": db.calls_today(con, "ebay"), "limit": settings["ebay"]["daily_call_budget"]},
        "markets": [m["id"] for m in settings["ebay"]["marketplaces"]],
        "destinations": {k: {"label": v["label"], "tax_pct": v["tax_pct"], "intl_extra_pct": v["intl_extra_pct"]}
                         for k, v in settings["destinations"].items()},
    }


def values(con, target_id):
    return db.rows(con, """SELECT c.card_key, c.name, c.number, c.subtype, c.rarity, c.market, c.low, c.updated, c.tcg_url,
        o.value_usd AS override_usd, o.updated AS override_at
        FROM cards c LEFT JOIN overrides o USING(card_key) WHERE c.target_id = ?
        ORDER BY COALESCE(o.value_usd, c.market) DESC""", (target_id,))


def rescore(con, where, args=()):
    rates, _ = fx.latest(con)
    if rates:
        pipeline.rescore(con, load_targets(), rates, load_settings(), where, args)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DASH, **k)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/state":
            return self.send_json(state(db.connect()))
        if u.path == "/api/values":
            return self.send_json(values(db.connect(), parse_qs(u.query).get("target", [""])[0]))
        if u.path.endswith(("sample.js",)):   # the live app never serves example data
            return self.send_json({"error": "not found"}, 404)
        super().do_GET()

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self.send_json({"error": "body must be JSON"}, 400)
        con = db.connect()

        if parts[:2] == ["api", "alerts"] and len(parts) == 4 and parts[3] == "decision":
            if body.get("decision") not in ("passed", "bought", "open"):
                return self.send_json({"error": "decision must be passed, bought or open"}, 400)
            con.execute("UPDATE alerts SET decision=?, decided_at=?, outcome=COALESCE(?, outcome) WHERE id=?",
                        (body["decision"], db.now(), body.get("outcome"), int(parts[2])))
            con.commit()
            return self.send_json({"ok": True})

        if parts[:2] == ["api", "targets"] and len(parts) == 3:
            targets = load_targets()
            t = next((x for x in targets if x["id"] == parts[2]), None)
            if not t:
                return self.send_json({"error": "no such target"}, 404)
            for k, v in body.items():
                if k not in TARGET_FIELDS:
                    return self.send_json({"error": f"{k} can't be edited here"}, 400)
                try:
                    t[k] = TARGET_FIELDS[k](v)
                except (TypeError, ValueError):
                    return self.send_json({"error": f"{k} must be a number"}, 400)
            save_targets(targets)
            rescore(con, "target_id=?", (t["id"],))
            return self.send_json({"ok": True, "target": t})

        if parts == ["api", "settings", "push_every_listing"]:
            if not isinstance(body.get("on"), bool):
                return self.send_json({"error": "on must be true or false"}, 400)
            settings = load_settings()
            settings["decide"]["push_every_listing"] = body["on"]
            save_settings(settings)
            rescore(con, "source != 'tcgplayer'")
            return self.send_json({"ok": True})

        if parts == ["api", "overrides", "bulk"]:
            tid = body.get("target_id")
            if not any(t["id"] == tid for t in load_targets()):
                return self.send_json({"error": "no such target"}, 404)
            matches, unmatched = overrides.apply(con, tid, body.get("text", ""))
            for key in {k for k, _, _ in matches}:
                rescore(con, "card_key=?", (key,))
            return self.send_json({"ok": True, "saved": len({line for _, _, line in matches}),
                                   "unmatched": [{"line": l, "why": w} for l, w in unmatched]})

        if parts == ["api", "overrides"]:
            key, v = body.get("card_key"), body.get("value_usd")
            if not db.one(con, "SELECT 1 FROM cards WHERE card_key=?", (key,)):
                return self.send_json({"error": "unknown card"}, 404)
            if v in (None, ""):
                con.execute("DELETE FROM overrides WHERE card_key=?", (key,))
            else:
                try:
                    v = float(v)
                except ValueError:
                    return self.send_json({"error": "value must be a number"}, 400)
                con.execute("INSERT OR REPLACE INTO overrides(card_key, value_usd, source, updated) VALUES(?,?,?,?)",
                            (key, v, "Collectr", db.now()))
            con.commit()
            rescore(con, "card_key=?", (key,))
            return self.send_json({"ok": True})

        self.send_json({"error": "not found"}, 404)


if __name__ == "__main__":
    load_env()
    host, port = os.environ.get("DASHBOARD_HOST", "0.0.0.0"), int(os.environ.get("DASHBOARD_PORT", "8790"))
    print(f"Card Radar dashboard on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
