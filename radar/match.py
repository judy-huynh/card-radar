"""Matcher agent. Listing title -> exact catalog card + variant, grade, condition, red flags, confidence.

Principles
- Never guess upward: when a title is ambiguous we pick the lower-valued reading and mark confidence low.
- Every rejection carries a reason a human can read on the dashboard.
"""
import re
from .text import norm, norm_num

GRADE = re.compile(r"\b(psa|bgs|cgc|sgc|beckett|ace|tag|pca|ags)\s*(?:gem\s*mint|gem\s*mt|mint|nm[\s-]*mt|pristine|black\s*label)?\s*(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4|3|2|1)\b", re.I)
GRADED_WORD = re.compile(r"\b(graded|slab|slabbed)\b", re.I)

FLAGS = [
    ("lot", re.compile(r"\b(lot|lots|bundle|bulk|binder|complete set|full set|set of \d+|x\d+|\d+\s*cards)\b")),
    ("fake", re.compile(r"\b(proxy|custom|replica|reprint|fan art|fanart|orica|fake|not original|metal|gold plated|digital|code card|online code|novelty|art card|altered|skin|card skin)\b")),
    ("modern reprint", re.compile(r"\b(celebrations?|classic collection|30th|25th|anniversary)\b")),
    ("not a single", re.compile(r"\b(booster|pack|box|sealed|sleeve|sleeves|playmat|poster|sticker|figure|tin|empty|deck box|toploader only)\b")),
    ("japanese", re.compile(r"\b(japanese|japan|jpn|jp|japanisch|japonais|giapponese|old back)\b")),
    ("non-English", re.compile(r"\b(german|deutsch|french|francais|italian|italiano|spanish|espanol|korean|chinese|portuguese|italienisch|franz sisch|franzosisch|franzoesisch|spanisch|koreanisch|chinesisch|portugiesisch|allemand)\b")),
]

CONDITIONS = [  # checked in order; first hit wins
    ("DMG", re.compile(r"\b(damaged|dmg|crease|creased|creases|water damage|poor|bent|torn|ink|tinte)\b")),
    ("HP", re.compile(r"\b(heavily played|heavy played|heavy play|hp|stark bespielt|read description|see description)\b")),
    ("LP", re.compile(r"\b(lightly played|light play|light wear|leicht bespielt)\b")),   # before MP's bare "played"
    ("MP", re.compile(r"\b(moderately played|moderate play|mp|played|good|gespielt|gut|gutem)\b")),
    ("LP", re.compile(r"\b(lightly played|light play|light wear|lp|excellent|exc|bespielt|leicht bespielt)\b")),
    ("NM", re.compile(r"\b(near mint|nm|nm m|mint|pack fresh)\b")),
]

REVERSE = re.compile(r"\b(reverse|rev)\s*(holo|holofoil|foil)?\b|\brh\b|\brevholo\b")
NONHOLO = re.compile(r"\bnon\s*holo\b|\bnonholo\b|\bnot holo\b")
FIRST = re.compile(r"\b(1st|first)\s*(ed|edition)?\b")
HOLO = re.compile(r"\b(holo|holofoil|holographic|foil|crystal)\b")

NUM_PAIR = re.compile(r"(?<![a-z0-9])(h?)0*(\d{1,3})\s*/\s*(h?)0*(\d{1,3})(?![0-9])")
NUM_HASH = re.compile(r"#\s*(h?)0*(\d{1,3})(?![0-9])")
NUM_H = re.compile(r"(?<![a-z0-9])h0*(\d{1,2})(?![0-9])")


def extract_numbers(t):
    nums, denoms = set(), set()
    for a, n, b, d in NUM_PAIR.findall(t):
        nums.add(norm_num(a + n)); denoms.add(str(int(d)))
    for a, n in NUM_HASH.findall(t):
        nums.add(norm_num(a + n))
    for n in NUM_H.findall(t):
        nums.add("H" + str(int(n)))
    return nums, denoms


def detect_grade(title, condition_raw):
    m = GRADE.search(title or "")
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"
    if GRADED_WORD.search(title or "") or (condition_raw or "").lower() == "graded":
        return "graded"
    return None


def detect_condition(t):
    for code, rx in CONDITIONS:
        if rx.search(t):
            return code
    return None


def detect_variant(t):
    if REVERSE.search(t):
        return "reverse"
    if NONHOLO.search(t):
        return "normal"
    if HOLO.search(t):
        return "holo"
    return None


def _subtype_fits(subtype, variant, first, rarity=None):
    s = subtype.lower()
    if rarity == "Secret Rare" and variant in ("holo", None):
        return True   # crystal cards: TCGplayer's foil label is arbitrary
    if first is not None and s.startswith(("1st", "unlimited")):
        if first != s.startswith("1st"):
            return False
    if variant == "reverse":
        return s.startswith("reverse")
    if variant == "holo":
        return "holofoil" in s and not s.startswith("reverse")
    if variant == "normal":
        return "holofoil" not in s
    return True


def _drop_sub_names(cands):
    """If 'dark gengar' matched, drop plain 'gengar' candidates."""
    names = {c["name_norm"] for c in cands}
    return [c for c in cands if not any(o != c["name_norm"] and c["name_norm"] in o for o in names)]


def _rank_default(c):
    """Default variant when the title doesn't say: holo for H-numbered / holo-rarity cards, else lowest value."""
    holoish = (c["num_norm"] or "").startswith("H") or (c["rarity"] or "").startswith("Holo")
    is_holo = "holofoil" in c["subtype"].lower() and not c["subtype"].lower().startswith("reverse")
    return (0 if holoish and is_holo else 1, c["market"] if c["market"] is not None else 1e9)


def match(title, condition_raw, target, cards):
    """cards: catalog rows for the target's set (all subtypes, target and non-target)."""
    t = norm(title)
    out = {"card_key": None, "card": None, "confidence": None, "variant": None,
           "grade": detect_grade(title, condition_raw), "condition": detect_condition(t),
           "flags": [name for name, rx in FLAGS if rx.search(t)], "reason": None}

    nums, denoms = extract_numbers(t)
    set_named = any(f" {a} " in t for a in target.get("set_aliases", [])) or bool(denoms & set(target.get("denoms", [])))
    variant = detect_variant(t)
    first = True if FIRST.search(t) else (False if "unlimited" in t else None)
    if first is None and any(c["subtype"].lower().startswith("1st") for c in cards):
        first = False   # sellers always advertise 1st Edition; silence means Unlimited
    out["variant"] = variant

    by_name = _drop_sub_names([c for c in cards if c["name_norm"] and c["name_norm"] in t])
    by_num = [c for c in by_name if c["num_norm"] in nums] if nums else []
    matched_by = "name+number" if by_num else "name"
    cands = by_num or by_name
    number_conflict = bool(nums) and by_name and not by_num
    if not cands and nums:
        cands = [c for c in cards if c["num_norm"] in nums and (not denoms or c["denom"] in denoms)]
        matched_by = "number"
    if not cands:
        out["reason"] = "no card in this set matches the title"
        return out

    fitting = [c for c in cands if _subtype_fits(c["subtype"], variant, first, c["rarity"])]
    loose = False
    if not fitting and variant == "holo":   # sellers often call a reverse holo just "holo"
        fitting = [c for c in cands if c["subtype"].lower().startswith("reverse")]
        loose = bool(fitting)
    if not fitting:
        best = sorted(cands, key=_rank_default)[0]
        out.update(card_key=best["card_key"], card=best, confidence="low",
                   reason=f"title says {variant or 'unknown variant'}, card exists only as {', '.join(sorted({c['subtype'] for c in cands}))}")
        return out

    products = {c["product_id"] for c in fitting}
    best = sorted(fitting, key=_rank_default)[0]
    if len(products) > 1:   # several different cards fit: conservative = cheapest
        best = sorted(fitting, key=lambda c: c["market"] if c["market"] is not None else 1e9)[0]

    if matched_by == "name+number" and set_named and len(products) == 1 and (variant or len(fitting) == 1 or _rank_default(best)[0] == 0):
        conf = "high"
    elif len(products) == 1 and set_named and not number_conflict:
        conf = "medium"
    else:
        conf = "low"
    if loose and conf == "high":
        conf = "medium"
    reason = None
    if not set_named:
        reason = "set not named in title"
    elif number_conflict:
        reason = "card number in title doesn't match this card"
    elif len(products) > 1:
        reason = "several cards fit; valued at the cheapest"
    out.update(card_key=best["card_key"], card=best, confidence=conf, reason=reason)
    return out
