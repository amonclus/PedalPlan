import json
from datetime import date, timedelta

import anthropic

_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are an experienced cycling coach specialising in amateur athletes.
You follow a polarised training philosophy: most training volume is low intensity (Z1-Z2),
with a small proportion of high intensity (Z4-Z5) and minimal tempo (Z3).

When given an athlete's recent training data and current fitness metrics, you generate a
practical, realistic weekly training plan. You write for a motivated amateur who trains
around work and life — plans must be achievable, not aspirational.

Rules:
- Respect the target weekly hours strictly. Do not exceed it.
- Never prescribe a hard session the day after another hard session.
- If TSB is below -20, reduce intensity across the week.
- If TSB is below -30, make it a recovery week (Z1-Z2 only).
- Include at least one full rest day per week.
- Describe each session in plain language — no jargon overload.
- Output valid JSON only, no markdown fences, no extra text.
"""

_STEP_SCHEMA = """{
  "label": "Warm-up",
  "duration_min": 15,
  "zone": "Z1",
  "power_pct": "< 55%",
  "notes": "Easy spin, high cadence"
}"""

_DAY_SCHEMA = """{
  "day": "Monday",
  "type": "Rest | Easy | Endurance | Tempo | Threshold | VO2 Max | Long Ride",
  "duration_min": 75,
  "description": "Plain-language overview of the session and its purpose.",
  "structure": [
    {
      "label": "Warm-up",
      "duration_min": 15,
      "zone": "Z1-Z2",
      "power_pct": "55-75%",
      "notes": "Easy spin to activate the legs"
    },
    {
      "label": "Main set",
      "duration_min": 45,
      "zone": "Z4",
      "power_pct": "95-105%",
      "notes": "3x15 min threshold, 5 min Z1 recovery between each"
    },
    {
      "label": "Cool-down",
      "duration_min": 15,
      "zone": "Z1",
      "power_pct": "< 55%",
      "notes": "Gradual spin down"
    }
  ]
}"""

_OUTPUT_SCHEMA = f"""Return a JSON object with this exact structure:
{{
  "week_commencing": "YYYY-MM-DD",
  "summary": "One sentence overview of the week's training focus.",
  "days": [
    {_DAY_SCHEMA},
    ... (one entry per day, Monday through Sunday)
  ]
}}

Rules for structure:
- The sum of duration_min across all steps must equal the day's total duration_min.
- For Rest days, set structure to an empty list [].
- zone must be one of: Z1, Z1-Z2, Z2, Z2-Z3, Z3, Z3-Z4, Z4, Z4-Z5, Z5, Rest.
- power_pct should reference % of FTP (e.g. "55-75%", "95-105%", "< 55%", "> 120%").
- label should be concise (e.g. "Warm-up", "3x10 min Z4", "Recovery", "Cool-down").
- notes should give concrete instruction (reps, cadence cues, feel, etc.)."""


def _weekly_summaries(activities: list[dict], load_df, num_weeks: int = 8) -> str:
    """Build a per-week summary table for the prompt."""
    lines = ["  Week starting  | Rides | Hours  | TSS   | Avg power | Avg HR"]
    for w in range(num_weeks - 1, -1, -1):
        week_start = date.today() - timedelta(days=date.today().weekday()) - timedelta(weeks=w)
        week_end = week_start + timedelta(days=6)
        ws = week_start.isoformat()
        we = week_end.isoformat()

        week_acts = [a for a in activities if ws <= a["date"] <= we]
        if not week_acts and load_df.empty:
            continue

        rides = len(week_acts)
        hours = round(sum(a["moving_time_h"] for a in week_acts), 1)
        tss = round(load_df.loc[ws:we, "tss"].sum(), 1) if not load_df.empty else 0
        powers = [a["avg_watts"] for a in week_acts if a["avg_watts"]]
        hrs = [a["avg_hr"] for a in week_acts if a["avg_hr"]]
        avg_power = f"{int(sum(powers)/len(powers))}W" if powers else "—"
        avg_hr = f"{int(sum(hrs)/len(hrs))}bpm" if hrs else "—"

        lines.append(f"  {ws}       | {rides:<5} | {hours:<6} | {tss:<5} | {avg_power:<9} | {avg_hr}")

    return "\n".join(lines)


def _build_prompt(activities: list[dict], load_df, user_params: dict) -> str:
    ftp = user_params["ftp"]
    weekly_hours = user_params["weekly_hours"]
    hr_zones = user_params["hr_zones"]
    goal = user_params.get("goal", "Base fitness")
    rest_days = user_params.get("rest_days", [])

    if not load_df.empty:
        latest = load_df.iloc[-1]
        ctl = round(latest["ctl"], 1)
        atl = round(latest["atl"], 1)
        tsb = round(latest["tsb"], 1)
        # CTL trend: compare today vs 7 days ago
        ctl_7d_ago = round(load_df.iloc[-8]["ctl"], 1) if len(load_df) >= 8 else ctl
        ctl_trend = "rising" if ctl > ctl_7d_ago else "falling" if ctl < ctl_7d_ago else "stable"
        atl_7d_ago = round(load_df.iloc[-8]["atl"], 1) if len(load_df) >= 8 else atl
        atl_trend = "rising" if atl > atl_7d_ago else "falling" if atl < atl_7d_ago else "stable"
    else:
        ctl = atl = tsb = 0
        ctl_trend = atl_trend = "unknown"

    # Recent individual rides (last 4 weeks)
    cutoff = (date.today() - timedelta(weeks=4)).isoformat()
    recent = sorted(
        [a for a in activities if a["date"] >= cutoff],
        key=lambda a: a["date"],
        reverse=True,
    )
    activity_lines = []
    for a in recent:
        power = f"{a['avg_watts']}W" if a["avg_watts"] else "no power"
        hr = f"{int(a['avg_hr'])}bpm" if a["avg_hr"] else "no HR"
        activity_lines.append(
            f"  {a['date']} | {a['name']} | {a['distance_km']}km | "
            f"{a['moving_time_h']}h | {int(a['elevation_m'])}m | {power} | {hr}"
        )

    next_monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
    rest_str = ", ".join(rest_days) if rest_days else "none specified"
    comments = user_params.get("comments", "").strip()
    comments_section = f"\nAthlete notes for this week:\n{comments}\n" if comments else ""

    return f"""Athlete profile:
- FTP: {ftp} W
- Target weekly training hours: {weekly_hours} h
- Training goal: {goal}
- Preferred rest days: {rest_str}
- HR Zones (lower bounds): Z1={hr_zones['z1']} Z2={hr_zones['z2']} Z3={hr_zones['z3']} Z4={hr_zones['z4']} Z5={hr_zones['z5']} bpm

Current training load:
- CTL (Fitness): {ctl} ({ctl_trend} vs 7 days ago)
- ATL (Fatigue): {atl} ({atl_trend} vs 7 days ago)
- TSB (Form):    {tsb}

Weekly training history (last 8 weeks):
{_weekly_summaries(activities, load_df)}

Recent individual rides (last 4 weeks):
{chr(10).join(activity_lines) if activity_lines else "  No recent rides."}

{comments_section}Generate a training plan for the week commencing {next_monday.isoformat()}.

{_OUTPUT_SCHEMA}"""


def generate_plan(activities: list[dict], load_df, user_params: dict, api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    prompt = _build_prompt(activities, load_df, user_params)
    message = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)
