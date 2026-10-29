import json, os
HERE = os.path.dirname(__file__)
CARDS = json.load(open(os.path.join(HERE, "fixtures", "cards.json")))


def cards(group_id):
    return [c for c in CARDS if c["group_id"] == group_id]


def target(tid):
    from radar.config import load_targets
    return next(t for t in load_targets() if t["id"] == tid)
