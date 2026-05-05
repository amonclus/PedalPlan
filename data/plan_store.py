import json
from pathlib import Path

PLANS_DIR = Path(__file__).parent.parent / "plans"


def save_plan(plan: dict):
    PLANS_DIR.mkdir(exist_ok=True)
    week = plan.get("week_commencing", "unknown")
    path = PLANS_DIR / f"plan_{week}.json"
    with open(path, "w") as f:
        json.dump(plan, f, indent=2)


def load_all_plans() -> list[dict]:
    if not PLANS_DIR.exists():
        return []
    plans = []
    for p in sorted(PLANS_DIR.glob("plan_*.json"), reverse=True):
        with open(p) as f:
            try:
                plans.append(json.load(f))
            except json.JSONDecodeError:
                pass
    return plans
