import json

import db

DEFAULTS = {
    "ftp": 250,
    "weekly_hours": 10,
    "hr_zones": {"z1": 100, "z2": 120, "z3": 140, "z4": 160, "z5": 175},
    "goal": "Base fitness",
    "rest_days": ["Sunday"],
}


def load_settings(athlete_id: int) -> dict:
    raw = db.get_settings(athlete_id)
    if not raw:
        return DEFAULTS.copy()
    saved = json.loads(raw)
    return {**DEFAULTS, **saved}


def save_settings(athlete_id: int, settings: dict):
    db.save_settings_json(athlete_id, json.dumps(settings))
