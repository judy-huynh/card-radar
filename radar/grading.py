"""Grader agent. Raw listing -> likely PSA range, so it can be checked against Collectr's price for that grade.

Two sources, best first:
- photos: a person (or Claude) looked at the listing photos; written with tools/grade.py
- seller: the seller's own eBay "Card Condition" pick, mapped through settings.grade_from_condition
A photo check is never overwritten by the seller's pick."""
import re
from . import db

# eBay's ungraded-card condition values, in English and as sellers' localized sites return them. Worst first.
SELLER_CONDITIONS = [
    ("HP", re.compile(r"heavily|poor|stark bespielt", re.I)),
    ("MP", re.compile(r"moderately|very good|sehr gut|m[äa](?:ß|ss)ig bespielt", re.I)),
    ("LP", re.compile(r"lightly|excellent|exzellent|leicht bespielt", re.I)),
    ("NM", re.compile(r"near mint", re.I)),
]
WORST_FIRST = ["DMG", "HP", "MP", "LP", "NM"]


def seller_code(text):
    """eBay 'Card Condition' text -> NM / LP / MP / HP, or None when it isn't one we know."""
    for code, rx in SELLER_CONDITIONS:
        if rx.search(text or ""):
            return code
    return None


def worse(a, b):
    """The worse of two condition codes; None means unknown and loses to any stated condition."""
    if not a or not b:
        return a or b
    return a if WORST_FIRST.index(a) <= WORST_FIRST.index(b) else b


def from_condition(code, settings):
    rng = settings.get("grade_from_condition", {}).get(code)
    return (rng[0], rng[1]) if rng else (None, None)


def get(con, item_id):
    return db.one(con, "SELECT * FROM grades WHERE item_id=?", (item_id,))


def record_seller(con, item_id, text, settings):
    """Store the seller's pick. Keeps an existing photo range; only fills the seller fields."""
    code = seller_code(text)
    low, high = from_condition(code, settings)
    con.execute("""INSERT INTO grades(item_id, low, high, source, seller_condition, seller_text, checked_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET seller_condition=excluded.seller_condition,
                     seller_text=excluded.seller_text,
                     low=CASE WHEN grades.source='photos' THEN grades.low ELSE excluded.low END,
                     high=CASE WHEN grades.source='photos' THEN grades.high ELSE excluded.high END,
                     source=CASE WHEN grades.source='photos' THEN 'photos' ELSE excluded.source END""",
                (item_id, low, high, "seller" if code else None, code, (text or "")[:200], db.now()))
    return code


def record_photos(con, item_id, low, high, note):
    con.execute("""INSERT INTO grades(item_id, low, high, source, note, checked_at) VALUES(?,?,?,'photos',?,?)
                   ON CONFLICT(item_id) DO UPDATE SET low=excluded.low, high=excluded.high, source='photos',
                     note=excluded.note, checked_at=excluded.checked_at""",
                (item_id, low, high, note, db.now()))
