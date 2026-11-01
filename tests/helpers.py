import json, os
HERE = os.path.dirname(__file__)
CARDS = json.load(open(os.path.join(HERE, "fixtures", "cards.json")))


def cards(group_id):
    return [c for c in CARDS if c["group_id"] == group_id]


def target(tid):
    from radar.config import load_targets
    return next(t for t in load_targets() if t["id"] == tid)


def legacy_settings():
    """Settings with the condition filter off: the rules before 2026-11-01 (every listing pushes)."""
    from radar.config import load_settings
    s = load_settings()
    s["condition_filter"] = dict(s["condition_filter"], enabled=False)
    s["decide"] = dict(s["decide"], push_every_listing=True)
    return s
