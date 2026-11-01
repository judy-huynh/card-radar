"""The buying rules shown on Settings → Rules (SPEC "Rules on the Settings page"): wording, group and allowed range for
each. Values live in config/settings.json and config/targets.json; this file only says which can be edited and how."""
import copy
from . import db

# (key, group, label, help, kind, options): key is a dotted path into settings.json.
# kind: bool | int | money | pct | multi (options = list of (value, label)). int/money/pct options = (min, max).
RULES = [
    ("condition_filter.raw_only", "buy", "Reject graded slabs", "PSA, BGS, CGC… are thrown out; only ungraded cards.", "bool", None),
    ("condition_filter.seller_must_say", "buy", "Seller's condition must be", "Title and eBay \"Card Condition\" both count; the worse wins.",
     "multi", [("NM", "Near mint"), ("LP", "Lightly played"), ("MP", "Moderately played"), ("HP", "Heavily played")]),
    ("condition_filter.photo_check.enabled", "buy", "Photo check", "Claude looks at every listing photo before a card can buzz.", "bool", None),
    ("condition_filter.photo_check.allowed_whitening", "buy", "Back-corner whitening allowed", "White spots on the blue back corners.",
     "multi", [("none", "None"), ("light", "Light"), ("heavy", "Heavy")]),
    ("notify.max_pushes_per_day", "buzz", "Buzzes per day", "The best ones first; the rest wait on Deals.", "int", (0, 50)),
    ("notify.max_pushes_per_hour", "buzz", "Buzzes per hour", "", "int", (1, 60)),
    ("decide.push_auctions", "buzz", "Buzz for auctions", "An auction's price is only the current bid.", "bool", None),
    ("whatnot.realize_pct", "whatnot", "Share of value a card fetches live", "What our partner gets on stream, as % of the card's value.", "pct", (10, 150)),
    ("whatnot.commission_pct", "whatnot", "Whatnot commission", "", "pct", (0, 30)),
    ("whatnot.processing_pct", "whatnot", "Payment processing", "", "pct", (0, 10)),
    ("whatnot.processing_fixed_usd", "whatnot", "Processing per order", "", "money", (0, 5)),
    ("decide.min_seller_feedback", "sellers", "Seller needs at least this much feedback", "", "int", (0, 100000)),
    ("decide.min_seller_pct", "sellers", "Seller's positive feedback at least", "", "pct", (0, 100)),
    ("ebay.daily_call_budget", "advanced", "eBay calls a day", "eBay allows 5,000. Searches always come first.", "int", (100, 5000)),
    ("ebay.recheck_max_per_hour", "advanced", "\"Still for sale?\" rechecks per hour", "", "int", (0, 200)),
    ("condition_filter.lookups_per_run", "advanced", "Condition lookups per scan", "", "int", (0, 200)),
    ("condition_filter.photo_check.max_per_run", "advanced", "Photo checks per scan", "Each takes about 25 seconds.", "int", (0, 20)),
    ("condition_filter.photo_check.max_per_day", "advanced", "Photo checks per day", "", "int", (0, 500)),
    ("condition_filter.photo_check.max_images", "advanced", "Photos looked at per card", "", "int", (1, 12)),
]
GROUPS = [("buy", "What we buy"), ("buzz", "Buzzes"), ("whatnot", "Whatnot profit"),
          ("sellers", "Sellers"), ("advanced", "Advanced")]
# per-set thresholds (targets.json): field -> (label, kind, range)
TARGET_RULES = {
    "push_gap_pct": ("Push at gap ≥ %", "pct", (0, 95)),
    "watch_gap_pct": ("Watch at gap ≥ %", "pct", (0, 95)),
    "min_value_usd": ("Min value", "money", (0, 1000000)),
    "max_price_usd": ("Max landed", "money", (1, 10000000)),
    "paused": ("Paused", "bool", None),
}
BY_KEY = {r[0]: r for r in RULES}


def _get(settings, key):
    v = settings
    for part in key.split("."):
        v = v[part]
    return v


def _set(settings, key, value):
    *path, last = key.split(".")
    v = settings
    for part in path:
        v = v[part]
    v[last] = value


def current(settings):
    """The rules with their current values, for the dashboard."""
    return {"groups": GROUPS,
            "rules": [{"key": k, "group": g, "label": lab, "help": h, "kind": kind,
                       "options": opts, "value": _get(settings, k)} for k, g, lab, h, kind, opts in RULES],
            "target_rules": {f: {"label": lab, "kind": kind, "range": rng} for f, (lab, kind, rng) in TARGET_RULES.items()}}


def clean(kind, opts, value, label):
    """One submitted value -> the stored value, or ValueError saying why in plain words."""
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{label}: must be on or off")
        return value
    if kind == "multi":
        allowed = [o[0] for o in opts]
        if not isinstance(value, list) or not value or any(v not in allowed for v in value):
            raise ValueError(f"{label}: pick at least one")
        return [v for v in allowed if v in value]   # stored in the listed order
    try:
        n = float(str(value).replace("$", "").replace("%", "").replace(",", "").strip())
    except ValueError:
        raise ValueError(f"{label}: enter a number")
    lo, hi = opts
    if not lo <= n <= hi:
        raise ValueError(f"{label}: must be between {lo:,} and {hi:,}")
    return int(n) if kind == "int" else (round(n, 2) if kind == "money" else round(n, 1))


def apply(settings, targets, rules=None, target_changes=None):
    """Validate every change first; only if all are good, return new (settings, targets, changes). changes is a list
    of (what, key, old, new) for the log, skipping values that didn't change."""
    settings, targets = copy.deepcopy(settings), copy.deepcopy(targets)
    changes = []
    for key, value in (rules or {}).items():
        if key not in BY_KEY:
            raise ValueError(f"{key} can't be changed here")
        _, _, label, _, kind, opts = BY_KEY[key]
        new, old = clean(kind, opts, value, label), _get(settings, key)
        if new != old:
            _set(settings, key, new)
            changes.append((label, key, old, new))
    by_id = {t["id"]: t for t in targets}
    for tid, fields in (target_changes or {}).items():
        t = by_id.get(tid)
        if not t:
            raise ValueError(f"no such set: {tid}")
        for f, value in fields.items():
            if f not in TARGET_RULES:
                raise ValueError(f"{f} can't be changed here")
            label, kind, rng = TARGET_RULES[f]
            new, old = clean(kind, rng, value, f"{t['label']} · {label}"), t.get(f)
            if new != old:
                t[f] = new
                changes.append((f"{t['label']} · {label}", f"target:{tid}.{f}", old, new))
    return settings, targets, changes


def log_changes(con, changes):
    for what, key, old, new in changes:
        con.execute("INSERT INTO rule_changes(at, what, key, old, new) VALUES(?,?,?,?,?)",
                    (db.now(), what, key, db.jdump(old), db.jdump(new)))


def undo_request(change):
    """A logged change -> the (rules, target_changes) that puts the old value back."""
    import json
    old = json.loads(change["old"])
    if change["key"].startswith("target:"):
        tid, f = change["key"][len("target:"):].rsplit(".", 1)
        return {}, {tid: {f: old}}
    return {change["key"]: old}, {}
