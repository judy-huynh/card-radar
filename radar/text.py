"""Text normalisation shared by the catalog and the matcher, so both sides compare the same way."""
import re

_PAREN = re.compile(r"\s*\([^)]*\)")
_NONALNUM = re.compile(r"[^a-z0-9/#]+")
_NUM = re.compile(r"^(h?)0*(\d+)$", re.I)


def norm(s):
    """Lowercase, fold symbols to spaces, keep '/' and '#' for card numbers."""
    s = (s or "").lower().replace("é", "e").replace("♀", " f ").replace("♂", " m ").replace("'", "")
    return " " + " ".join(_NONALNUM.sub(" ", s).split()) + " "


def clean_name(product_name):
    """'Beedrill (H4)' -> 'Beedrill'; 'Gengar (13)' -> 'Gengar'."""
    return _PAREN.sub("", product_name or "").strip()


def norm_num(part):
    """'H04' -> 'H4', '003' -> '3'. Returns None when it isn't a card number."""
    m = _NUM.match((part or "").strip())
    if not m:
        return None
    return (m.group(1).upper() + str(int(m.group(2))))


def split_number(number):
    """'H04/H32' -> ('H4', '32'); '003/110' -> ('3', '110')."""
    if not number or "/" not in number:
        return norm_num(number), None
    a, b = number.split("/", 1)
    d = norm_num(b)
    return norm_num(a), (d.lstrip("H") if d else None)
