"""Collectr values typed or pasted by Ben. One card per line: the card number, optional variant word(s), the value.

    H14 214.50
    149/147 $520
    6 1st 1000        (Dark Gengar 1st Edition)
    6 unlimited 1100
    11 reverse 2300   (Legendary Collection Gengar reverse)

Anything that can't be pinned to exactly one card comes back unmatched instead of guessing."""
import re
from . import db
from .text import norm_num

HINTS = {"1st": "1st", "first": "1st", "unl": "unlimited", "unlimited": "unlimited", "rev": "reverse",
         "reverse": "reverse", "rh": "reverse", "holo": "holo", "nonholo": "normal", "normal": "normal"}


def _fits(subtype, hints):
    s = subtype.lower()
    for h in hints:
        if h == "1st" and not s.startswith("1st"): return False
        if h == "unlimited" and not s.startswith("unlimited"): return False
        if h == "reverse" and not s.startswith("reverse"): return False
        if h == "holo" and ("holofoil" not in s or s.startswith("reverse")): return False
        if h == "normal" and "holofoil" in s: return False
    return True


def parse(text, rows):
    """rows: target cards. Returns (matches [(card_key, value, line)], unmatched [(line, why)])."""
    matches, unmatched = [], []
    for line in (text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        tokens = re.findall(r"\b1st\b|[A-Za-z]+\d+|\d+/\d+|[$]?\d[\d,]*(?:\.\d+)?|[A-Za-z]+", raw)
        if len(tokens) < 2:
            unmatched.append((raw, "needs a card number and a value")); continue
        try:
            value = float(tokens[-1].replace("$", "").replace(",", ""))
        except ValueError:
            unmatched.append((raw, "last thing on the line must be the value")); continue
        num = norm_num(tokens[0].split("/")[0])
        hints = [HINTS[t.lower()] for t in tokens[1:-1] if t.lower() in HINTS]
        cands = [r for r in rows if r["num_norm"] == num and _fits(r["subtype"], hints)]
        if not cands:
            unmatched.append((raw, f"no target card numbered {tokens[0]}")); continue
        if len({c["product_id"] for c in cands}) > 1 or (len(cands) > 1 and not all(c["rarity"] == "Secret Rare" for c in cands)):
            options = ", ".join(sorted({c["subtype"].replace("Holofoil", "Holo") for c in cands}))
            unmatched.append((raw, f"more than one card fits ({options}); add a word like 1st, unlimited or reverse")); continue
        for c in cands:   # a crystal filed under both foil labels gets the same value on both rows
            matches.append((c["card_key"], value, raw))
    return matches, unmatched


def apply(con, target_id, text):
    rows = db.rows(con, "SELECT card_key, num_norm, subtype, product_id, rarity, name, number FROM cards WHERE target_id=?", (target_id,))
    matches, unmatched = parse(text, rows)
    for key, value, _ in matches:
        con.execute("INSERT OR REPLACE INTO overrides(card_key, value_usd, source, updated) VALUES(?,?,?,?)",
                    (key, value, "Collectr", db.now()))
    con.commit()
    return matches, unmatched
