import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent.parent / "user_settings.json"

DEFAULTS = {
    "ftp": 250,
    "weekly_hours": 10,
    "hr_zones": {"z1": 100, "z2": 120, "z3": 140, "z4": 160, "z5": 175},
    "goal": "Base fitness",
    "rest_days": ["Sunday"],
}


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return DEFAULTS.copy()
    with open(SETTINGS_FILE) as f:
        saved = json.load(f)
    # Merge with defaults so new keys added in future are always present
    return {**DEFAULTS, **saved}


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
