"""Load .env and watchlist.json. Watchlist is the single source of truth for what we scan and when we alert."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")
WATCHLIST_PATH = os.path.join(ROOT, "watchlist.json")
DB_PATH = os.path.join(ROOT, "radar.db")

def load_env():
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    return os.environ

def load_watchlist():
    with open(WATCHLIST_PATH) as f:
        return json.load(f)

def save_watchlist(cfg):
    tmp = WATCHLIST_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, WATCHLIST_PATH)
