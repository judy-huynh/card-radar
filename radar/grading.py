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
    con.execute("""INSERT INTO grades(item_id, low, high, source, seller_condition, seller_text, checked_at, seller_checked_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET seller_condition=excluded.seller_condition,
                     seller_text=excluded.seller_text, seller_checked_at=excluded.seller_checked_at,
                     low=CASE WHEN grades.source='photos' THEN grades.low ELSE excluded.low END,
                     high=CASE WHEN grades.source='photos' THEN grades.high ELSE excluded.high END,
                     source=CASE WHEN grades.source='photos' THEN 'photos' ELSE excluded.source END""",
                (item_id, low, high, "seller" if code else None, code, (text or "")[:200], db.now(), db.now()))
    return code


def record_availability(con, item_id, gone):
    """eBay's own record was just read: still for sale (gone=None) or why not."""
    con.execute("""INSERT INTO grades(item_id, gone, avail_at) VALUES(?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET gone=excluded.gone, avail_at=excluded.avail_at""",
                (item_id, gone, db.now()))


def record_photo_check(con, item_id, verdict, reason, detail, low=None, high=None):
    """A finished photo check. Its PSA range replaces the seller's (source 'photos')."""
    con.execute("""INSERT INTO grades(item_id, photo_verdict, photo_reason, photo_detail, photo_at, photo_error, photo_attempts)
                   VALUES(?,?,?,?,?,NULL,1)
                   ON CONFLICT(item_id) DO UPDATE SET photo_verdict=excluded.photo_verdict, photo_reason=excluded.photo_reason,
                     photo_detail=excluded.photo_detail, photo_at=excluded.photo_at, photo_error=NULL,
                     photo_attempts=COALESCE(grades.photo_attempts, 0) + 1""",
                (item_id, verdict, reason, db.jdump(detail), db.now()))
    if low is not None and high is not None:
        record_photos(con, item_id, low, high, reason)


def record_photo_error(con, item_id, err, counts=True):
    """A photo check that couldn't run. counts=True (this listing's photos were unusable) uses one of its max_attempts;
    counts=False (Claude Code itself failed: signed out, offline) only notes the error, so the listing keeps its tries."""
    n = 1 if counts else 0
    con.execute("""INSERT INTO grades(item_id, photo_error, photo_at, photo_attempts) VALUES(?,?,?,?)
                   ON CONFLICT(item_id) DO UPDATE SET photo_error=excluded.photo_error,
                     photo_at=COALESCE(excluded.photo_at, grades.photo_at),
                     photo_attempts=COALESCE(grades.photo_attempts, 0) + ?""",
                (item_id, str(err)[:300], db.now() if counts else None, n, n))


def record_photos(con, item_id, low, high, note):
    con.execute("""INSERT INTO grades(item_id, low, high, source, note, checked_at) VALUES(?,?,?,'photos',?,?)
                   ON CONFLICT(item_id) DO UPDATE SET low=excluded.low, high=excluded.high, source='photos',
                     note=excluded.note, checked_at=excluded.checked_at""",
                (item_id, low, high, note, db.now()))
