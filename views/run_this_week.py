from datetime import date, timedelta

import pandas as pd
import streamlit as st

_TYPE_COLOR = {
    "Rest":      "#6b7280",
    "Easy":      "#22c55e",
    "Tempo":     "#f59e0b",
    "Intervals": "#ef4444",
    "Long Run":  "#3b82f6",
    "Race Pace": "#a855f7",
}


def _fmt_duration(minutes: int) -> str:
    if not minutes:
        return "—"
    if minutes >= 60:
        h, m = divmod(int(minutes), 60)
        return f"{h}h {m}min" if m else f"{h}h"
    return f"{int(minutes)}min"


def _week_days() -> list[tuple[date, str]]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i), (monday + timedelta(days=i)).strftime("%A")) for i in range(7)]


def _plan_by_weekday(plan: dict | None) -> dict[str, dict]:
    if not plan:
        return {}
    return {d["day"]: d for d in plan.get("days", [])}


def _activities_by_date(activities: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for a in activities:
        result.setdefault(a["date"], []).append(a)
    return result


def render(activities: list[dict], load_df: pd.DataFrame, session: dict):
    st.header("This Week — Running")

    today = date.today()
    week_days = _week_days()
    week_start = week_days[0][0].isoformat()
    week_end = week_days[-1][0].isoformat()

    plan = session.get("current_run_plan")
    plan_map = _plan_by_weekday(plan)
    act_map = _activities_by_date(activities)

    # ── Weekly progress summary ───────────────────────────────────────────────
    week_acts = [a for a in activities if week_start <= a["date"] <= week_end]
    done_km = round(sum(a["distance_km"] for a in week_acts), 1)
    done_h = sum(a["moving_time_h"] for a in week_acts)
    done_tss = load_df.loc[week_start:week_end, "tss"].sum() if not load_df.empty else 0.0
    target_km = session.get("run_weekly_km", 0) or 0

    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("Runs completed", len(week_acts))
    kc2.metric("Distance done", f"{done_km} km")
    kc3.metric("TSS this week", f"{done_tss:.0f}")
    kc4.metric("Km target", f"{target_km} km")

    if target_km > 0:
        progress = min(done_km / target_km, 1.0)
        st.progress(progress, text=f"{done_km} km of {target_km} km target")

    st.divider()

    # ── Day-by-day breakdown ──────────────────────────────────────────────────
    for day_date, day_name in week_days:
        day_str = day_date.isoformat()
        planned = plan_map.get(day_name)
        day_acts = act_map.get(day_str, [])
        is_today = day_date == today
        is_future = day_date > today

        plan_type = planned.get("type", "Rest") if planned else None
        plan_dur = planned.get("duration_min", 0) if planned else 0
        plan_km = planned.get("distance_km", 0) if planned else 0
        plan_color = _TYPE_COLOR.get(plan_type, "#6b7280") if plan_type else "#6b7280"

        if is_future:
            status, status_color = "Upcoming", "#6b7280"
        elif is_today:
            status, status_color = ("Done today", "#16a34a") if day_acts else ("Today", "#2563eb")
        else:
            if day_acts:
                status, status_color = "Done", "#16a34a"
            elif plan_type in (None, "Rest"):
                status, status_color = "Rest", "#6b7280"
            else:
                status, status_color = "Missed", "#dc2626"

        with st.container(border=True):
            hc1, hc2 = st.columns([3, 2])
            with hc1:
                weight = "font-weight:700" if is_today else "font-weight:400"
                st.markdown(
                    f'<span style="{weight};font-size:1rem;">{day_name}'
                    f'{"&nbsp;◀ today" if is_today else ""}</span>',
                    unsafe_allow_html=True,
                )
            with hc2:
                badges = (
                    f'<span style="background:{status_color};color:white;padding:2px 9px;'
                    f'border-radius:10px;font-size:0.78rem;">{status}</span>'
                )
                if plan_type and plan_type != "Rest":
                    label = f"{plan_type} · {plan_km}km · {_fmt_duration(plan_dur)}"
                    badges += (
                        f'&nbsp;<span style="background:{plan_color};color:white;padding:2px 9px;'
                        f'border-radius:10px;font-size:0.78rem;">{label}</span>'
                    )
                st.markdown(f'<div style="text-align:right;">{badges}</div>', unsafe_allow_html=True)

            if planned and planned.get("description") and plan_type != "Rest":
                st.caption(f"Plan: {planned['description']}")

            if day_acts:
                rows = []
                for a in day_acts:
                    act_tss = (
                        load_df.loc[day_str, "tss"]
                        if not load_df.empty and day_str in load_df.index else None
                    )
                    rows.append({
                        "Run": a["name"],
                        "Distance": f"{a['distance_km']} km",
                        "Time": _fmt_duration(int(a["moving_time_h"] * 60)),
                        "Pace": a.get("avg_pace") or "—",
                        "Elevation": f"{int(a['elevation_m'])} m",
                        "Avg HR": f"{int(a['avg_hr'])} bpm" if a.get("avg_hr") else "—",
                        "TSS": f"{act_tss:.0f}" if act_tss is not None else "—",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            elif not is_future and plan_type not in (None, "Rest"):
                st.caption("No run recorded.")
