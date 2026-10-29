"""SQLite store shared by every agent, the CLI and the dashboard server."""
import json, sqlite3, time
from .config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
  card_key TEXT PRIMARY KEY,          -- group:product:subtype
  target_id TEXT,                     -- set when this card+variant is one of our targets
  group_id INTEGER, product_id INTEGER, set_name TEXT,
  name TEXT, name_norm TEXT, number TEXT, num_norm TEXT, denom TEXT,
  subtype TEXT, rarity TEXT, tcg_url TEXT, image_url TEXT,
  market REAL, low REAL, mid REAL, updated TEXT);
CREATE INDEX IF NOT EXISTS cards_group ON cards(group_id);

CREATE TABLE IF NOT EXISTS value_history (card_key TEXT, day TEXT, market REAL, low REAL, PRIMARY KEY(card_key, day));

CREATE TABLE IF NOT EXISTS overrides (
  card_key TEXT PRIMARY KEY, value_usd REAL, source TEXT DEFAULT 'Collectr', note TEXT, updated TEXT);

CREATE TABLE IF NOT EXISTS fx (day TEXT PRIMARY KEY, rates TEXT, fetched TEXT);

CREATE TABLE IF NOT EXISTS listings (
  item_id TEXT PRIMARY KEY, source TEXT, marketplace TEXT, target_id TEXT,
  title TEXT, url TEXT, image TEXT, price REAL, currency TEXT, buying TEXT,
  seller TEXT, feedback INTEGER, feedback_pct REAL, item_country TEXT, item_location TEXT,
  created TEXT, ends TEXT, condition_raw TEXT,
  first_seen TEXT, last_seen TEXT, first_price REAL,
  card_key TEXT, confidence TEXT, variant TEXT, grade TEXT, flags TEXT, condition TEXT,
  value_usd REAL, value_source TEXT, landed TEXT, best_dest TEXT, landed_usd REAL, gap_pct REAL,
  tier TEXT, reason TEXT, pushed_tier TEXT);
CREATE INDEX IF NOT EXISTS listings_seen ON listings(last_seen);
CREATE INDEX IF NOT EXISTS listings_tier ON listings(tier);

CREATE TABLE IF NOT EXISTS quotes (
  item_id TEXT, dest TEXT, ship REAL, ship_currency TEXT, ships INTEGER, seen TEXT, PRIMARY KEY(item_id, dest));

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT, kind TEXT, tier TEXT, sent_at TEXT,
  title TEXT, message TEXT, gap_pct REAL, landed_usd REAL, value_usd REAL,
  pushed INTEGER DEFAULT 0, decision TEXT DEFAULT 'open', decided_at TEXT, outcome TEXT);
CREATE INDEX IF NOT EXISTS alerts_item ON alerts(item_id);

CREATE TABLE IF NOT EXISTS scopes (scope TEXT PRIMARY KEY, seeded_at TEXT);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, started TEXT, finished TEXT, calls INTEGER, results INTEGER,
  new_listings INTEGER, pushes INTEGER, errors TEXT, status TEXT);

CREATE TABLE IF NOT EXISTS agents (agent TEXT PRIMARY KEY, last_ok TEXT, last_error TEXT, last_error_at TEXT, detail TEXT);

CREATE TABLE IF NOT EXISTS system_alerts (key TEXT PRIMARY KEY, last_sent TEXT);

CREATE TABLE IF NOT EXISTS api_calls (day TEXT, source TEXT, n INTEGER, PRIMARY KEY(day, source));
"""


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def today():
    return time.strftime("%Y-%m-%d")


def connect(path=None):
    con = sqlite3.connect(path or db_path(), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args)]


def one(con, sql, args=()):
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None


# ---- agent health -------------------------------------------------------

def agent_ok(con, agent, detail=""):
    con.execute("""INSERT INTO agents(agent, last_ok, detail) VALUES(?,?,?)
                   ON CONFLICT(agent) DO UPDATE SET last_ok=excluded.last_ok, detail=excluded.detail""",
                (agent, now(), detail))


def agent_error(con, agent, err):
    con.execute("""INSERT INTO agents(agent, last_error, last_error_at) VALUES(?,?,?)
                   ON CONFLICT(agent) DO UPDATE SET last_error=excluded.last_error, last_error_at=excluded.last_error_at""",
                (agent, str(err)[:500], now()))


# ---- API budget ---------------------------------------------------------

def count_call(con, source, n=1):
    con.execute("""INSERT INTO api_calls(day, source, n) VALUES(?,?,?)
                   ON CONFLICT(day, source) DO UPDATE SET n = n + excluded.n""", (today(), source, n))


def calls_today(con, source):
    r = one(con, "SELECT n FROM api_calls WHERE day=? AND source=?", (today(), source))
    return r["n"] if r else 0


def jdump(x):
    return json.dumps(x, separators=(",", ":"))
