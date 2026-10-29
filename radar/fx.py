"""FX agent. Daily ECB reference rates (via Frankfurter, free, no key), USD base."""
import json, urllib.request
from . import db

URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=CAD,GBP,EUR,AUD,JPY"


def refresh(con, fetch=None):
    if fetch:
        data = fetch()
    else:
        req = urllib.request.Request(URL, headers={"User-Agent": "card-radar/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    rates = dict(data["rates"], USD=1.0)
    con.execute("INSERT OR REPLACE INTO fx(day, rates, fetched) VALUES(?,?,?)", (data["date"], json.dumps(rates), db.now()))
    con.commit()
    return rates


def latest(con):
    r = db.one(con, "SELECT * FROM fx ORDER BY fetched DESC LIMIT 1")
    return (json.loads(r["rates"]), r["fetched"]) if r else (None, None)


def to_usd(amount, currency, rates):
    """Convert amount in `currency` to USD. Rates are units of currency per 1 USD."""
    if amount is None:
        return None
    if currency == "USD":
        return float(amount)
    rate = rates.get(currency)
    if not rate:
        raise ValueError(f"no FX rate for {currency}")
    return float(amount) / rate
