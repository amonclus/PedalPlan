import json

import db


def save_plan(athlete_id: int, plan: dict, sport: str = "cycling"):
    week = plan.get("week_commencing", "unknown")
    db.save_plan(athlete_id, week, json.dumps(plan), sport)


def load_all_plans(athlete_id: int, sport: str = "cycling") -> list[dict]:
    plans = []
    for raw in db.load_all_plans(athlete_id, sport):
        try:
            plans.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return plans
