"""Paths, .env, and the two config files. Targets and settings are the only place thresholds live."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")
TARGETS_PATH = os.path.join(ROOT, "config", "targets.json")
SETTINGS_PATH = os.path.join(ROOT, "config", "settings.json")


def db_path():
    return os.environ.get("RADAR_DB") or os.path.join(ROOT, "radar.db")


def load_env():
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            lines = f.read().splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    return os.environ


def _load(path):
    with open(path) as f:
        return json.load(f)


def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_targets():
    return _load(TARGETS_PATH)["targets"]


def save_targets(targets):
    _save(TARGETS_PATH, {"targets": targets})


def load_settings():
    return _load(SETTINGS_PATH)
