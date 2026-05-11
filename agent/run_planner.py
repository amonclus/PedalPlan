import json
from datetime import date, timedelta

import anthropic

_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are an experienced running coach specialising in amateur athletes.
You follow a polarised training philosophy: most volume is easy (Z1-Z2 by HR or pace),
with a small proportion of quality work (tempo, threshold, intervals).

When given an athlete's recent running data and fitness metrics, you generate a practical
weekly training plan. You write for a motivated amateur who trains around work and life.

Rules:
- Respect the target weekly km strictly. Do not exceed it by more than 10%.
- Never schedule a hard session the day after another hard session.
- If TSB is below -20, reduce intensity across the week.
- If TSB is below -30, make it a recovery week (easy running only).
- Include at least one full rest day per week.
- Long run should be on a weekend day wherever possible.
- Output valid JSON only, no markdown fences, no extra text.
"""

_STEP_SCHEMA = """{
  "label": "Warm-up",
  "duration_min": 10,
  "distance_km": 1.5,
  "zone": "Z1",
  "target_pace": "6:30",
  "notes": "Very easy jogging to warm up"
}"""

_DAY_SCHEMA = """{
  "day": "Monday",
  "type": "Rest | Easy | Tempo | Intervals | Long Run | Race Pace",
  "duration_min": 45,
  "distance_km": 8.0,
  "description": "Plain-language overview of the session.",
  "structure": [
    {
      "label": "Warm-up",
      "duration_min": 10,
      "distance_km": 1.5,
      "zone": "Z1",
      "target_pace": "6:30",
      "notes": "Easy jogging"
    },
    {
      "label": "Main set",
      "duration_min": 25,
      "distance_km": 5.0,
      "zone": "Z3",
      "target_pace": "5:10",
      "notes": "Steady tempo, comfortably hard"
    },
    {
      "label": "Cool-down",
      "duration_min": 10,
      "distance_km": 1.5,
      "zone": "Z1",
      "target_pace": "6:30",
      "notes": "Easy jog to finish"
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
- For Rest days, set structure to an empty list [], duration_min to 0, distance_km to 0.
- zone must be one of: Z1, Z1-Z2, Z2, Z2-Z3, Z3, Z3-Z4, Z4, Z4-Z5, Z5, Rest.
- target_pace is the goal pace in MM:SS per km for that step.
- label should be concise (e.g. "Warm-up", "5x1km Z4", "Cool-down", "Easy run").
- The sum of distance_km across all steps should roughly equal the day's total distance_km."""


def _pace_to_secs(pace_str: str) -> int:
    parts = pace_str.strip().split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _secs_to_pace(secs: int) -> str:
    m, s = divmod(max(0, int(secs)), 60)
    return f"{m}:{s:02d}"


def _pace_zones_str(threshold_pace: str) -> str:
    t = _pace_to_secs(threshold_pace)
    return (
        f"  Z1 (Recovery):  slower than {_secs_to_pace(t + 90)} /km\n"
        f"  Z2 (Easy):      {_secs_to_pace(t + 45)} – {_secs_to_pace(t + 90)} /km\n"
        f"  Z3 (Tempo):     {_secs_to_pace(t + 10)} – {_secs_to_pace(t + 45)} /km\n"
        f"  Z4 (Threshold): {_secs_to_pace(t - 10)} – {_secs_to_pace(t + 10)} /km\n"
        f"  Z5 (VO2 Max):   faster than {_secs_to_pace(t - 10)} /km"
    )


def _weekly_summaries(activities: list[dict], load_df, num_weeks: int = 8) -> str:
    lines = ["  Week starting  | Runs | Km     | Hours  | TSS   | Avg Pace | Avg HR"]
    for w in range(num_weeks - 1, -1, -1):
        week_start = date.today() - timedelta(days=date.today().weekday()) - timedelta(weeks=w)
        week_end = week_start + timedelta(days=6)
        ws, we = week_start.isoformat(), week_end.isoformat()
        week_acts = [a for a in activities if ws <= a["date"] <= we]
        if not week_acts and load_df.empty:
            continue
        runs = len(week_acts)
        km = round(sum(a["distance_km"] for a in week_acts), 1)
        hours = round(sum(a["moving_time_h"] for a in week_acts), 1)
        tss = round(load_df.loc[ws:we, "tss"].sum(), 1) if not load_df.empty else 0
        paces = [a["avg_pace"] for a in week_acts if a.get("avg_pace")]
        hrs = [a["avg_hr"] for a in week_acts if a.get("avg_hr")]
        avg_pace = paces[0] if len(paces) == 1 else "—"
        avg_hr = f"{int(sum(hrs)/len(hrs))}bpm" if hrs else "—"
        lines.append(f"  {ws}       | {runs:<4} | {km:<6} | {hours:<6} | {tss:<5} | {avg_pace:<8} | {avg_hr}")
    return "\n".join(lines)


def _build_prompt(activities: list[dict], load_df, user_params: dict) -> str:
    threshold_pace = user_params["run_threshold_pace"]
    weekly_km = user_params["run_weekly_km"]
    hr_zones = user_params["hr_zones"]
    goal = user_params.get("run_goal", "Base fitness")
    rest_days = user_params.get("rest_days", [])

    if not load_df.empty:
        latest = load_df.iloc[-1]
        ctl = round(latest["ctl"], 1)
        atl = round(latest["atl"], 1)
        tsb = round(latest["tsb"], 1)
        ctl_7d_ago = round(load_df.iloc[-8]["ctl"], 1) if len(load_df) >= 8 else ctl
        ctl_trend = "rising" if ctl > ctl_7d_ago else "falling" if ctl < ctl_7d_ago else "stable"
    else:
        ctl = atl = tsb = 0
        ctl_trend = "unknown"

    cutoff = (date.today() - timedelta(weeks=4)).isoformat()
    recent = sorted([a for a in activities if a["date"] >= cutoff], key=lambda a: a["date"], reverse=True)
    activity_lines = [
        f"  {a['date']} | {a['name']} | {a['distance_km']}km | "
        f"{a['moving_time_h']}h | {int(a['elevation_m'])}m elev | "
        f"pace {a.get('avg_pace', '—')}/km | {int(a['avg_hr'])}bpm" if a.get("avg_hr") else
        f"  {a['date']} | {a['name']} | {a['distance_km']}km | {a['moving_time_h']}h"
        for a in recent
    ]

    next_monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
    rest_str = ", ".join(rest_days) if rest_days else "none specified"
    comments = user_params.get("comments", "").strip()
    comments_section = f"\nAthlete notes for this week:\n{comments}\n" if comments else ""

    return f"""Athlete profile:
- Threshold pace: {threshold_pace} /km
- Target weekly distance: {weekly_km} km
- Training goal: {goal}
- Preferred rest days: {rest_str}
- HR Zones (lower bounds): Z1={hr_zones['z1']} Z2={hr_zones['z2']} Z3={hr_zones['z3']} Z4={hr_zones['z4']} Z5={hr_zones['z5']} bpm

Pace zones derived from threshold pace:
{_pace_zones_str(threshold_pace)}

Current running training load:
- CTL (Fitness): {ctl} ({ctl_trend} vs 7 days ago)
- ATL (Fatigue): {atl}
- TSB (Form):    {tsb}

Weekly running history (last 8 weeks):
{_weekly_summaries(activities, load_df)}

Recent runs (last 4 weeks):
{chr(10).join(activity_lines) if activity_lines else "  No recent runs."}

{comments_section}Generate a running plan for the week commencing {next_monday.isoformat()}.

{_OUTPUT_SCHEMA}"""


def generate_run_plan(activities: list[dict], load_df, user_params: dict, api_key: str) -> dict:
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
