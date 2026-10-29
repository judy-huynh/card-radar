"""Notifier agent: ntfy.sh pushes (JSON publish, so titles can carry any character).
Every deal push has two buttons: the listing itself and the dashboard row."""
import json, os, urllib.request

SENT = []   # dry-run capture (tests / --dry)


def push(title, message, priority=3, tags=None, click=None, actions=None, dry=False):
    topic = os.environ.get("NTFY_TOPIC")
    body = {"topic": topic, "title": title, "message": message, "priority": priority, "tags": tags or []}
    if click:
        body["click"] = click
    if actions:
        body["actions"] = [{"action": "view", "label": label, "url": url, "clear": False} for label, url in actions]
    if dry or os.environ.get("RADAR_DRY"):
        SENT.append(body)
        return
    if not topic:
        raise RuntimeError("NTFY_TOPIC is not set in .env")
    req = urllib.request.Request(os.environ.get("NTFY_SERVER", "https://ntfy.sh"), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


DEST_SHORT = {"CA": "CA", "NYC": "NYC"}
MP_SHORT = {"EBAY_US": "eBay US", "EBAY_CA": "eBay CA", "EBAY_GB": "eBay UK", "EBAY_AU": "eBay AU", "EBAY_DE": "eBay DE", "TCGPLAYER": "TCGplayer"}


def money(v):
    return "—" if v is None else f"${v:,.0f}"


def deal_message(l, card, kind):
    """Phone-sized: line 1 what + where, line 2 landed vs value, line 3 seller/condition."""
    landed = json.loads(l["landed"] or "{}")
    dests = sorted(landed.items(), key=lambda kv: kv[1]["usd"])
    landed_txt = " · ".join(f"{k} {money(v['usd'])}{'*' if v['ship_estimated'] else ''}" for k, v in dests)
    variant = card["subtype"].replace("Holofoil", "Holo") if card else ""
    head = f"DEAL {l['gap_pct']:.0f}%" if l["tier"] == "DEAL" and l["gap_pct"] is not None else "LISTED · value unknown"
    if kind == "price_drop":
        head = "PRICE DROP · " + head
    title = f"{head} · {card['name']} {card['number']}" if card else head
    lines = [
        f"{card['set_name']} · {variant} · {MP_SHORT.get(l['marketplace'], l['marketplace'])} ({l['item_country'] or '?'})" if card else l["title"],
        f"Ask {l['price']:,.2f} {l['currency']} · landed {landed_txt} (US$)",
        f"Value {money(l['value_usd'])} {l['value_source'] or ''}" + (f" · cond {l['condition']}" if l["condition"] else ""),
        (f"Seller {l['seller']} ({l['feedback']} · {l['feedback_pct']}%)" if l["feedback"] is not None
         else "Cheapest copy on TCGplayer; condition not shown, check the listing"),
    ]
    return title, "\n".join(lines)
