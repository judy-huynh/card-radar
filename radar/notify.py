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


COND = {"NM": "Near mint", "LP": "Light play", "MP": "Moderate play", "HP": "Heavy play", "DMG": "Damaged"}


def deal_message(l, card, kind, target_label=None):
    """Same words as the dashboard. Title = the verdict; body = what, where, money, seller."""
    landed = json.loads(l["landed"] or "{}")
    best = landed.get(l["best_dest"]) if l["best_dest"] else None
    ret = None if l["gap_pct"] is None or l["value_usd"] is None or l["landed_usd"] is None else l["value_usd"] - l["landed_usd"]
    name = f"{card['name']} {card['number']}" if card else l["title"][:60]
    buying = l["buying"] or ""
    if l["tier"] == "DEAL" and ret is not None:
        title = f"DEAL · +{money(ret)} potential return · {name}"
    elif ret is not None:
        title = f"LISTED · {name} · " + (f"+{money(ret)} potential return" if ret >= 0 else f"{money(-ret)} over value")
    elif l["grade"]:
        title = f"LISTED · {name} · {l['grade']}"
    elif "AUCTION" in buying and "FIXED_PRICE" not in buying:
        title = f"LISTED · {name} · auction"
    else:
        title = f"LISTED · {name} · value unknown"
    if kind == "price_drop":
        title = "PRICE DROP · " + title

    where = MP_SHORT.get(l["marketplace"], l["marketplace"])
    if l["item_country"] and l["item_country"] not in where:
        where += f" (from {l['item_country']})"
    lines = [f"★ Match · {target_label}" if target_label else (card["set_name"] if card else ""),
             f"{where} · " + (f"Graded {l['grade']}" if l["grade"] else COND.get(l["condition"], "Condition not stated"))]
    money_line = []
    if best:
        money_line.append(f"Landed {money(best['usd'])}{'*' if best['ship_estimated'] else ''} {l['best_dest']}")
    if l["value_usd"] is not None:
        money_line.append(f"Value {money(l['value_usd'])} {l['value_source'] or ''}".strip())
    if money_line:
        lines.append(" · ".join(money_line))
    seller = f" · seller {l['feedback']:,} feedback" if l["feedback"] is not None else ""
    lines.append(f"Ask {l['price']:,.2f} {l['currency']}{seller}")
    if "check photos" in (l["reason"] or ""):
        lines.append("⚠ " + l["reason"].split(" · ", 1)[-1])
    return title, "\n".join(x for x in lines if x)
