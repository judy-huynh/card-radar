"""One scan pass: for each watchlist card and marketplace, fetch listings, store new ones, push an alert.
Stage 1 rule: every new listing under max_price is an alert. Threshold logic arrives in stage 2."""
import os, sys, time
from . import ebay, notify, store
from .config import load_env, load_watchlist

def title_ok(title, exclude):
    t = title.lower()
    return not any(x in t for x in exclude)

def format_alert(card, it):
    return f"{card['id']} [{it['marketplace']}] {it['price']:.2f} {it['currency']} - {it['title'][:70]}\n{it['url']}"

def run(dry=False):
    env = load_env()
    cfg = load_watchlist()
    cid, secret = env.get("EBAY_CLIENT_ID"), env.get("EBAY_CLIENT_SECRET")
    if not (cid and secret):
        sys.exit("Missing EBAY_CLIENT_ID / EBAY_CLIENT_SECRET in .env")
    base = env.get("DASHBOARD_URL", "http://localhost:8790")
    token = ebay.get_token(cid, secret)
    con = store.connect()
    new, sent, errors = 0, 0, []
    for card in cfg["cards"]:
        if card.get("paused"):
            continue
        for mp in cfg["marketplaces"]:
            try:
                items = ebay.search(token, mp, card["query"], card.get("max_price_usd", cfg["max_price_usd"]),
                                    cfg["results_per_card"], cfg.get("fx_cad_per_usd", 1.4))
            except Exception as e:
                errors.append(f"{card['id']}/{mp}: {e}"); continue
            for it in items:
                if store.seen(con, it["item_id"]) or not title_ok(it["title"], card.get("exclude", [])):
                    continue
                store.add_listing(con, card["id"], it); new += 1
                alert_id = store.add_alert(con, card["id"], it)
                con.commit()
                msg = format_alert(card, it)
                print(msg, "\n")
                if not dry:
                    try:
                        notify.push(msg, click=f"{base}/#alert-{alert_id}"); sent += 1
                    except Exception as e:
                        errors.append(f"notify {it['item_id']}: {e}")
            time.sleep(0.5)
    store.log_scan(con, new, sent, errors); con.commit()
    print(f"scan done: {new} new, {sent} alerts, {len(errors)} errors")
    for e in errors: print("  !", e, file=sys.stderr)
