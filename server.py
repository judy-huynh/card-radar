#!/usr/bin/env python3
"""Card Radar dashboard server. Stdlib only. Serves dashboard/ and a small JSON API over the SQLite store.
Bind to 0.0.0.0 so it is reachable over Tailscale; it has no auth, so never expose it to the public internet."""
import json, os, sys, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
from radar import store
from radar.config import load_env, load_watchlist, save_watchlist, ROOT

DASH = os.path.join(ROOT, "dashboard")
EDITABLE = {"alert_gap_pct": float, "max_price_usd": float, "paused": bool, "condition": str, "query": str}

def state():
    cfg = load_watchlist()
    con = store.connect()
    alerts = store.open_alerts(con)
    for a in alerts:  # stage 2 fills these from Collectr values + landed-cost rules
        a.setdefault("landed_ca", None); a.setdefault("landed_nyc", None); a.setdefault("collectr_usd", None); a.setdefault("gap_pct", None)
    log = store.alert_log(con)
    for a in log: a.setdefault("gap_pct", None)
    hits = {r["card_id"]: r["c"] for r in con.execute(
        "SELECT card_id, COUNT(*) c FROM alerts WHERE sent_at >= datetime('now','-7 days','localtime') GROUP BY card_id")}
    return {"alerts": alerts, "log": log, "watchlist": cfg, "hits": hits, "stats": store.stats(con),
            "last_scan": store.last_scan(con), "fx": cfg.get("fx_cad_per_usd"), "interval": cfg.get("scan_interval_min"),
            "today": time.strftime("%Y-%m-%d")}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DASH, **k)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path == "/api/state":
            return self.send_json(state())
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path.strip("/").split("/")
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if path[:2] == ["api", "alerts"] and len(path) == 4 and path[3] == "decision":
            if body.get("decision") not in ("passed", "bought", "open"):
                return self.send_json({"error": "decision must be passed, bought or open"}, 400)
            con = store.connect(); store.decide(con, int(path[2]), body["decision"], body.get("outcome")); con.commit()
            return self.send_json({"ok": True})
        if path[:2] == ["api", "watchlist"] and len(path) == 3:
            cfg = load_watchlist(); i = int(path[2])
            if not 0 <= i < len(cfg["cards"]):
                return self.send_json({"error": "no such card"}, 404)
            for k, v in body.items():
                if k not in EDITABLE:
                    return self.send_json({"error": f"{k} is not editable"}, 400)
                cfg["cards"][i][k] = EDITABLE[k](v)
            save_watchlist(cfg)
            return self.send_json({"ok": True, "card": cfg["cards"][i]})
        self.send_json({"error": "not found"}, 404)

if __name__ == "__main__":
    load_env()
    host, port = os.environ.get("DASHBOARD_HOST", "0.0.0.0"), int(os.environ.get("DASHBOARD_PORT", "8790"))
    print(f"Card Radar dashboard on http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
