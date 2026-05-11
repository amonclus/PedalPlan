import json

import db


def save_plan(athlete_id: int, plan: dict):
    week = plan.get("week_commencing", "unknown")
    db.save_plan(athlete_id, week, json.dumps(plan))


def load_all_plans(athlete_id: int) -> list[dict]:
    plans = []
    for raw in db.load_all_plans(athlete_id):
        try:
            plans.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return plans
