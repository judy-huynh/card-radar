#!/usr/bin/env python3
"""Stage 1: scan eBay for the watchlist cards and text the current cheapest listings.
No buying. No thresholds yet. Just prove we can see listings and get a text."""
import base64, json, os, sqlite3, subprocess, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

def load_env():
    path = os.path.join(HERE, ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def get_token(cid, secret):
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials",
                                   "scope": "https://api.ebay.com/oauth/api_scope"}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["access_token"]

def search(token, marketplace, query, max_price, limit):
    params = {"q": query, "limit": str(limit), "sort": "price",
              "filter": f"price:[1..{max_price}],priceCurrency:USD,buyingOptions:{{FIXED_PRICE}}"}
    if marketplace == "EBAY_CA":
        params["filter"] = f"price:[1..{int(max_price*1.4)}],priceCurrency:CAD,buyingOptions:{{FIXED_PRICE}}"
    req = urllib.request.Request(SEARCH_URL + "?" + urllib.parse.urlencode(params), headers={
        "Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": marketplace})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("itemSummaries", [])

def keep(item, exclude):
    t = item.get("title", "").lower()
    return not any(x in t for x in exclude)

def db():
    con = sqlite3.connect(os.path.join(HERE, "radar.db"))
    con.execute("""CREATE TABLE IF NOT EXISTS seen (item_id TEXT PRIMARY KEY, card_id TEXT, marketplace TEXT,
                   title TEXT, price REAL, currency TEXT, url TEXT, seller TEXT, feedback INTEGER,
                   first_seen TEXT, texted INTEGER DEFAULT 0)""")
    return con

def send_text(to, msg):
    script = f'tell application "Messages" to send {json.dumps(msg)} to buddy {json.dumps(to)}'
    subprocess.run(["osascript", "-e", script], check=True)

def main():
    load_env()
    cid, secret, to = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET"), os.environ.get("TEXT_TO")
    if not (cid and secret):
        sys.exit("Missing EBAY_CLIENT_ID / EBAY_CLIENT_SECRET in .env")
    cfg = json.load(open(os.path.join(HERE, "watchlist.json")))
    token = get_token(cid, secret)
    con = db()
    new_lines = []
    for card in cfg["cards"]:
        for mp in cfg["marketplaces"]:
            try:
                items = search(token, mp, card["query"], cfg["max_price_usd"], cfg["results_per_card"])
            except Exception as e:
                print(f"[{card['id']}/{mp}] search failed: {e}", file=sys.stderr); continue
            for it in items:
                if not keep(it, card["exclude"]): continue
                iid = it["itemId"]
                if con.execute("SELECT 1 FROM seen WHERE item_id=?", (iid,)).fetchone(): continue
                price = float(it["price"]["value"]); cur = it["price"]["currency"]
                seller = it.get("seller", {})
                con.execute("INSERT INTO seen VALUES (?,?,?,?,?,?,?,?,?,?,0)",
                            (iid, card["id"], mp, it["title"], price, cur, it["itemWebUrl"],
                             seller.get("username"), seller.get("feedbackScore"), time.strftime("%Y-%m-%d %H:%M")))
                new_lines.append(f"{card['id']} [{mp}] {price:.2f} {cur} - {it['title'][:60]}\n{it['itemWebUrl']}")
            time.sleep(0.5)
    con.commit()
    print(f"{len(new_lines)} new listings")
    for l in new_lines: print(l, "\n")
    if new_lines and to:
        for chunk in range(0, len(new_lines), 5):
            send_text(to, "Card radar:\n\n" + "\n\n".join(new_lines[chunk:chunk+5]))
        con.execute("UPDATE seen SET texted=1 WHERE texted=0"); con.commit()

if __name__ == "__main__":
    main()
