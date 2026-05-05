from datetime import date, timedelta

import pandas as pd
import streamlit as st


_TYPE_COLOR = {
    "Rest":       "#6b7280",
    "Easy":       "#22c55e",
    "Endurance":  "#3b82f6",
    "Tempo":      "#f59e0b",
    "Threshold":  "#ef4444",
    "VO2 Max":    "#a855f7",
    "Long Ride":  "#0ea5e9",
}


def _fmt_duration(minutes: int) -> str:
    if not minutes:
        return "—"
    if minutes >= 60:
        h, m = divmod(int(minutes), 60)
        return f"{h}h {m}min" if m else f"{h}h"
    return f"{int(minutes)}min"


def _week_days() -> list[tuple[date, str]]:
    """Mon–Sun of the current week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i), (monday + timedelta(days=i)).strftime("%A")) for i in range(7)]


def _plan_by_weekday(plan: dict | None) -> dict[str, dict]:
    """Map weekday name → planned day dict."""
    if not plan:
        return {}
    return {d["day"]: d for d in plan.get("days", [])}


def _activities_by_date(activities: list[dict]) -> dict[str, list[dict]]:
    """Map date string → list of activities on that date."""
    result: dict[str, list[dict]] = {}
    for a in activities:
        result.setdefault(a["date"], []).append(a)
    return result


def render(activities: list[dict], load_df: pd.DataFrame, session: dict):
    st.header("This Week")

    today = date.today()
    week_days = _week_days()
    week_start = week_days[0][0].isoformat()
    week_end   = week_days[-1][0].isoformat()

    plan = session.get("current_plan")
    plan_map = _plan_by_weekday(plan)
    act_map  = _activities_by_date(activities)

    # ── Weekly progress summary ───────────────────────────────────────────────

    # Accumulate actual time and TSS for the week
    week_acts = [a for a in activities if week_start <= a["date"] <= week_end]
    done_h    = sum(a["moving_time_h"] for a in week_acts)
    done_tss  = (
        load_df.loc[week_start:week_end, "tss"].sum()
        if not load_df.empty else 0.0
    )
    target_h  = session.get("weekly_hours", 0) or 0
    rides_done = len(week_acts)

    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.metric("Rides completed", rides_done)
    kc2.metric(
        "Time done",
        _fmt_duration(int(done_h * 60)),
        help="Moving time of all rides this week",
    )
    kc3.metric("TSS this week", f"{done_tss:.0f}")
    kc4.metric(
        "Time target",
        _fmt_duration(int(target_h * 60)),
        help="Your weekly hours target from Settings",
    )

    if target_h > 0:
        progress = min(done_h / target_h, 1.0)
        st.progress(progress, text=f"{done_h:.1f}h of {target_h}h target")

    st.divider()

    # ── Day-by-day breakdown ──────────────────────────────────────────────────

    for day_date, day_name in week_days:
        day_str   = day_date.isoformat()
        planned   = plan_map.get(day_name)
        day_acts  = act_map.get(day_str, [])
        is_today  = day_date == today
        is_future = day_date > today
        is_past   = day_date < today

        plan_type = planned.get("type", "Rest") if planned else None
        plan_dur  = planned.get("duration_min", 0) if planned else 0
        plan_color = _TYPE_COLOR.get(plan_type, "#6b7280") if plan_type else "#6b7280"

        # Status badge
        if is_future:
            status, status_color = "Upcoming", "#6b7280"
        elif is_today:
            if day_acts:
                status, status_color = "Done today", "#16a34a"
            else:
                status, status_color = "Today", "#2563eb"
        else:  # past
            if day_acts:
                status, status_color = "Done", "#16a34a"
            elif plan_type in (None, "Rest"):
                status, status_color = "Rest", "#6b7280"
            else:
                status, status_color = "Missed", "#dc2626"

        with st.container(border=True):
            # Header row: day name + status + plan badge
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
                    badges += (
                        f'&nbsp;<span style="background:{plan_color};color:white;padding:2px 9px;'
                        f'border-radius:10px;font-size:0.78rem;">'
                        f'{plan_type}&nbsp;{_fmt_duration(plan_dur)}</span>'
                    )
                st.markdown(
                    f'<div style="text-align:right;">{badges}</div>',
                    unsafe_allow_html=True,
                )

            # Planned description
            if planned and planned.get("description") and plan_type != "Rest":
                st.caption(f"Plan: {planned['description']}")

            # Actual rides
            if day_acts:
                rows = []
                for a in day_acts:
                    act_tss = (
                        load_df.loc[day_str, "tss"]
                        if not load_df.empty and day_str in load_df.index
                        else None
                    )
                    rows.append({
                        "Ride": a["name"],
                        "Time": _fmt_duration(int(a["moving_time_h"] * 60)),
                        "Distance": f"{a['distance_km']} km",
                        "Elevation": f"{int(a['elevation_m'])} m",
                        "Avg Power": f"{int(a['avg_watts'])} W" if a.get("avg_watts") else "—",
                        "Avg HR": f"{int(a['avg_hr'])} bpm" if a.get("avg_hr") else "—",
                        "TSS": f"{act_tss:.0f}" if act_tss is not None else "—",
                    })
                st.dataframe(
                    pd.DataFrame(rows),
                    use_container_width=True,
                    hide_index=True,
                )
            elif not is_future and plan_type not in (None, "Rest"):
                st.caption("No ride recorded.")
