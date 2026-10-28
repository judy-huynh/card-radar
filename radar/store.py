"""SQLite store: every listing we have seen, every alert we sent, every decision you made."""
import sqlite3, time
from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  item_id TEXT PRIMARY KEY, card_id TEXT, marketplace TEXT, title TEXT, price REAL, currency TEXT,
  shipping REAL, url TEXT, seller TEXT, feedback INTEGER, feedback_pct REAL, condition TEXT,
  location TEXT, image TEXT, first_seen TEXT);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT UNIQUE, card_id TEXT, sent_at TEXT,
  price REAL, currency TEXT, decision TEXT DEFAULT 'open', decided_at TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT, new_listings INTEGER, alerts INTEGER, errors TEXT);
"""

def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con

def seen(con, item_id):
    return con.execute("SELECT 1 FROM listings WHERE item_id=?", (item_id,)).fetchone() is not None

def add_listing(con, card_id, it):
    con.execute("""INSERT OR IGNORE INTO listings VALUES (:item_id,:card_id,:marketplace,:title,:price,:currency,
                   :shipping,:url,:seller,:feedback,:feedback_pct,:condition,:location,:image,:first_seen)""",
                dict(it, card_id=card_id, first_seen=now()))

def add_alert(con, card_id, it):
    cur = con.execute("INSERT OR IGNORE INTO alerts (item_id, card_id, sent_at, price, currency) VALUES (?,?,?,?,?)",
                      (it["item_id"], card_id, now(), it["price"], it["currency"]))
    return cur.lastrowid

def log_scan(con, new_listings, alerts, errors):
    con.execute("INSERT INTO scans (ran_at, new_listings, alerts, errors) VALUES (?,?,?,?)",
                (now(), new_listings, alerts, "; ".join(errors)))

def decide(con, alert_id, decision, outcome=None):
    con.execute("UPDATE alerts SET decision=?, decided_at=?, outcome=COALESCE(?, outcome) WHERE id=?",
                (decision, now(), outcome, alert_id))

def open_alerts(con):
    return [dict(r) for r in con.execute("""SELECT a.*, l.title, l.marketplace, l.url, l.seller, l.feedback, l.feedback_pct,
        l.condition, l.location, l.shipping, l.image FROM alerts a JOIN listings l USING(item_id)
        WHERE a.decision='open' ORDER BY a.sent_at DESC""")]

def alert_log(con, limit=100):
    return [dict(r) for r in con.execute("""SELECT a.*, l.title, l.marketplace, l.url FROM alerts a JOIN listings l USING(item_id)
        ORDER BY a.sent_at DESC LIMIT ?""", (limit,))]

def last_scan(con):
    r = con.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None

def stats(con):
    week = con.execute("SELECT COUNT(*) c FROM alerts WHERE sent_at >= datetime('now','-7 days','localtime')").fetchone()["c"]
    bought = con.execute("SELECT COUNT(*) c FROM alerts WHERE decision='bought' AND sent_at >= datetime('now','-7 days','localtime')").fetchone()["c"]
    passed = con.execute("SELECT COUNT(*) c FROM alerts WHERE decision='passed' AND sent_at >= datetime('now','-7 days','localtime')").fetchone()["c"]
    return {"week": week, "bought": bought, "passed": passed}
