import pandas as pd
import streamlit as st

from agent.plan_image import generate_plan_image
from agent.planner import generate_plan
from data.ics_export import generate_ics
from data.plan_store import load_all_plans, save_plan

_TYPE_COLOR = {
    "Rest":       "#6b7280",
    "Easy":       "#22c55e",
    "Endurance":  "#3b82f6",
    "Tempo":      "#f59e0b",
    "Threshold":  "#ef4444",
    "VO2 Max":    "#a855f7",
    "Long Ride":  "#0ea5e9",
}

_ZONE_COLOR = {
    "Z1":    "#bbf7d0",
    "Z1-Z2": "#86efac",
    "Z2":    "#4ade80",
    "Z2-Z3": "#fde68a",
    "Z3":    "#fbbf24",
    "Z3-Z4": "#fb923c",
    "Z4":    "#f97316",
    "Z4-Z5": "#ef4444",
    "Z5":    "#dc2626",
    "Rest":  "#e5e7eb",
}

_SESSION_TYPES = list(_TYPE_COLOR.keys())
_ZONES = list(_ZONE_COLOR.keys())


import re


def _fmt_duration(minutes: int) -> str:
    if minutes >= 60:
        h, m = divmod(minutes, 60)
        return f"{h}h {m}min" if m else f"{h}h"
    return f"{minutes}min"


def _fmt_power(power_pct: str, ftp: int) -> str:
    """Append computed watt range to a power_pct string, e.g. '55-75% (110-150 W)'."""
    if not power_pct or not ftp:
        return power_pct or "—"
    s = power_pct.strip()

    # Range: "55-75%" or "55–75%"
    m = re.match(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)%", s)
    if m:
        lo = round(float(m.group(1)) * ftp / 100)
        hi = round(float(m.group(2)) * ftp / 100)
        return f"{s} ({lo}–{hi} W)"

    # Less-than: "< 55%"
    m = re.match(r"[<＜]\s*(\d+(?:\.\d+)?)%", s)
    if m:
        w = round(float(m.group(1)) * ftp / 100)
        return f"{s} (<{w} W)"

    # Greater-than: "> 120%"
    m = re.match(r"[>＞]\s*(\d+(?:\.\d+)?)%", s)
    if m:
        w = round(float(m.group(1)) * ftp / 100)
        return f"{s} (>{w} W)"

    # Single value: "100%"
    m = re.match(r"(\d+(?:\.\d+)?)%", s)
    if m:
        w = round(float(m.group(1)) * ftp / 100)
        return f"{s} ({w} W)"

    return s


def _zone_bar(structure: list[dict], total_min: int):
    if not structure or total_min == 0:
        return
    segments = []
    for step in structure:
        dur = step.get("duration_min", 0)
        zone = step.get("zone", "Z1")
        color = _ZONE_COLOR.get(zone.strip(), "#d1d5db")
        pct = dur / total_min * 100
        segments.append(
            f'<div style="width:{pct:.1f}%;background:{color};height:100%;'
            f'display:inline-block;border-radius:2px;" title="{zone} — {_fmt_duration(dur)}"></div>'
        )
    st.markdown(
        f'<div style="height:8px;border-radius:4px;overflow:hidden;'
        f'background:#e5e7eb;margin-bottom:8px;">{"".join(segments)}</div>',
        unsafe_allow_html=True,
    )


def _structure_table(structure: list[dict], ftp: int = 0):
    rows = []
    for step in structure:
        rows.append({
            "Step": step.get("label", "—"),
            "Duration": _fmt_duration(step["duration_min"]) if step.get("duration_min") else "—",
            "Zone": step.get("zone", "—"),
            "Power": _fmt_power(step.get("power_pct", ""), ftp),
            "Notes": step.get("notes", ""),
        })
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={"Notes": st.column_config.TextColumn(width="large")},
    )


# ── Mutation helpers ──────────────────────────────────────────────────────────

def _swap_sessions(idx_a: int, idx_b: int):
    """Swap session content between two days (day names stay in place)."""
    plan = st.session_state["current_plan"]
    days = plan["days"]
    for field in ("type", "description", "duration_min", "structure"):
        val_a = days[idx_a].get(field)
        val_b = days[idx_b].get(field)
        days[idx_a][field] = val_b
        days[idx_b][field] = val_a
    save_plan(st.session_state["athlete_id"], plan)
    st.rerun()


def _delete_session(idx: int):
    plan = st.session_state["current_plan"]
    plan["days"][idx].update({
        "type": "Rest",
        "description": "Rest day",
        "duration_min": 0,
        "structure": [],
    })
    save_plan(st.session_state["athlete_id"], plan)
    st.rerun()


# ── Editable day card ─────────────────────────────────────────────────────────

def _edit_form(idx: int, day: dict):
    structure = day.get("structure", [])
    edited = None

    with st.form(key=f"form_{idx}"):
        c1, c2 = st.columns(2)
        new_type = c1.selectbox(
            "Session type", _SESSION_TYPES,
            index=_SESSION_TYPES.index(day["type"]) if day.get("type") in _SESSION_TYPES else 0,
        )
        new_dur = c2.number_input(
            "Total duration (min)", min_value=0, max_value=480,
            value=int(day.get("duration_min", 0)), step=5,
        )
        new_desc = st.text_input("Description", value=day.get("description", ""))

        if structure:
            st.caption("Workout steps — edit inline, add or remove rows")
            step_df = pd.DataFrame([{
                "Label": s.get("label", ""),
                "Min": int(s.get("duration_min", 0)),
                "Zone": s.get("zone", "Z1"),
                "Power %": s.get("power_pct", "") or "",
                "Notes": s.get("notes", "") or "",
            } for s in structure])
            edited = st.data_editor(
                step_df,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "Zone": st.column_config.SelectboxColumn(options=_ZONES, required=True),
                    "Min": st.column_config.NumberColumn(min_value=0, max_value=300, step=5),
                },
                key=f"steps_{idx}",
            )

        b1, b2 = st.columns(2)
        submitted = b1.form_submit_button("Save", type="primary", use_container_width=True)
        cancelled = b2.form_submit_button("Cancel", use_container_width=True)

    if cancelled:
        st.session_state[f"editing_day_{idx}"] = False
        st.rerun()

    if submitted:
        plan = st.session_state["current_plan"]
        d = plan["days"][idx]
        d["type"] = new_type
        d["description"] = new_desc
        d["duration_min"] = int(new_dur)
        if edited is not None:
            new_structure = []
            for _, row in edited.iterrows():
                new_structure.append({
                    "label": str(row["Label"]),
                    "duration_min": int(row["Min"]),
                    "zone": str(row["Zone"]),
                    "power_pct": str(row["Power %"]) if row["Power %"] else "",
                    "notes": str(row["Notes"]) if row["Notes"] else "",
                })
            d["structure"] = new_structure
            step_total = sum(s["duration_min"] for s in new_structure)
            if step_total > 0:
                d["duration_min"] = step_total
        save_plan(st.session_state["athlete_id"], plan)
        st.session_state[f"editing_day_{idx}"] = False
        st.rerun()


def _day_card_editable(idx: int, day: dict, n_days: int, ftp: int = 0):
    session_type = day.get("type", "Rest")
    color = _TYPE_COLOR.get(session_type, "#6b7280")
    structure = day.get("structure", [])
    total_min = day.get("duration_min", sum(s.get("duration_min", 0) for s in structure))
    is_editing = st.session_state.get(f"editing_day_{idx}", False)

    with st.container(border=True):
        header_col, btn_col = st.columns([4, 3])

        with header_col:
            st.markdown(
                f'<span style="background:{color};color:white;padding:2px 10px;'
                f'border-radius:12px;font-size:0.82rem;">{session_type}</span>'
                f'&nbsp;<strong>{day["day"]}</strong>'
                f'&nbsp;<span style="color:#6b7280;font-size:0.85rem;">{_fmt_duration(total_min)}</span>',
                unsafe_allow_html=True,
            )
            st.caption(day.get("description", ""))

        with btn_col:
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("↑", key=f"up_{idx}", disabled=idx == 0, help="Move session up"):
                _swap_sessions(idx, idx - 1)
            if b2.button("↓", key=f"dn_{idx}", disabled=idx == n_days - 1, help="Move session down"):
                _swap_sessions(idx, idx + 1)
            if b3.button("✏" if not is_editing else "✕", key=f"ed_{idx}", help="Edit session"):
                st.session_state[f"editing_day_{idx}"] = not is_editing
                st.rerun()
            if b4.button("🗑", key=f"del_{idx}", help="Remove session (set to Rest)"):
                _delete_session(idx)

        if is_editing:
            st.divider()
            _edit_form(idx, day)
        elif session_type != "Rest" and structure:
            _zone_bar(structure, total_min)
            _structure_table(structure, ftp)


# ── Read-only plan render (used for history) ──────────────────────────────────

def _day_card_readonly(day: dict, ftp: int = 0):
    session_type = day.get("type", "")
    color = _TYPE_COLOR.get(session_type, "#6b7280")
    structure = day.get("structure", [])
    total_min = day.get("duration_min", sum(s.get("duration_min", 0) for s in structure))

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        col1.markdown(f"**{day['day']}**  —  {day.get('description', '')}")
        col2.markdown(
            f'<div style="text-align:right;">'
            f'<span style="background:{color};color:white;padding:3px 12px;'
            f'border-radius:12px;font-size:0.82rem;">{session_type}</span>'
            f'&nbsp;<span style="color:#6b7280;font-size:0.85rem;">{_fmt_duration(total_min)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if session_type != "Rest" and structure:
            _zone_bar(structure, total_min)
            _structure_table(structure, ftp)


def _weekly_summary(plan: dict):
    rows = []
    total_min = 0
    for d in plan.get("days", []):
        dur = d.get("duration_min", 0)
        total_min += dur
        rows.append({
            "Day": d["day"],
            "Session": d["type"],
            "Duration": _fmt_duration(dur) if dur else "—",
            "Zones": ", ".join({s["zone"] for s in d.get("structure", [])} - {"Rest"}) or "—",
        })
    with st.expander("Weekly summary"):
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"Total planned time: {_fmt_duration(total_min)}")


def _render_plan_readonly(plan: dict, ftp: int = 0):
    week = plan.get("week_commencing", "")
    st.markdown(f"**Week of {week}** — {plan.get('summary', '')}")
    btn_c1, btn_c2 = st.columns([1, 1])
    try:
        img_bytes = generate_plan_image(plan)
        btn_c1.download_button(
            label="Download as image",
            data=img_bytes,
            file_name=f"training_plan_{week}.png",
            mime="image/png",
        )
    except Exception:
        pass
    btn_c2.download_button(
        label="Export to Calendar (.ics)",
        data=generate_ics(plan, ftp),
        file_name=f"training_plan_{week}.ics",
        mime="text/calendar",
        key=f"ics_export_{week}",
    )

    st.divider()
    for day in plan.get("days", []):
        _day_card_readonly(day, ftp)
    _weekly_summary(plan)


# ── Tab renderers ─────────────────────────────────────────────────────────────

def render(activities: list[dict], load_df: pd.DataFrame, session: dict):
    tab_current, tab_history = st.tabs(["Current Plan", "Plan History"])
    with tab_current:
        _render_current(activities, load_df, session)
    with tab_history:
        _render_history(session)


def _render_current(activities, load_df, session):
    st.header("Weekly Training Plan")

    if not session.get("ftp") or session["ftp"] == 0:
        st.warning("Set your FTP in the Settings tab before generating a plan.")
        return

    plan = st.session_state.get("current_plan")

    comments = st.text_area(
        "Notes for the coach (optional)",
        placeholder="e.g. My legs feel heavy after last week, I have a long day on Wednesday so keep it short, I want to focus on climbing…",
        help="These notes are passed directly to the AI coach when generating your plan.",
        key="plan_comments",
    )

    api_key = session.get("claude_api_key", "")
    if not api_key:
        st.warning(
            "Add your Claude API key in **Settings → Claude API Key** to enable plan generation.",
            icon="🔑",
        )
        return

    btn_col, _ = st.columns([2, 5])
    label = "Generate New Plan" if plan else "Generate Plan"
    if btn_col.button(label, type="primary"):
        user_params = {
            "ftp": session["ftp"],
            "weekly_hours": session["weekly_hours"],
            "hr_zones": session["hr_zones"],
            "goal": session.get("goal", "Base fitness"),
            "rest_days": session.get("rest_days", []),
            "comments": comments.strip(),
        }
        with st.spinner("Generating your training plan…"):
            try:
                new_plan = generate_plan(activities, load_df, user_params, api_key)
                save_plan(session["athlete_id"], new_plan)
                st.session_state["current_plan"] = new_plan
                # Clear any open edit forms from the old plan
                for key in list(st.session_state.keys()):
                    if key.startswith("editing_day_"):
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                st.error(f"Failed to generate plan: {e}")
                return

    if plan:
        if label == "Generate New Plan":
            st.caption("Generating a new plan will replace the current week.")
    else:
        st.info(
            "Hit **Generate Plan** to get a personalised training schedule "
            "based on your current fitness and fatigue.",
            icon="📅",
        )
        st.caption("Plans are generated by Claude AI using your Strava data and the parameters set in Settings.")
        return

    ftp = session.get("ftp", 0) or 0

    # Download buttons for current plan
    week = plan.get("week_commencing", "")
    st.markdown(f"**Week of {week}** — {plan.get('summary', '')}")
    btn_c1, btn_c2 = st.columns([1, 1])
    try:
        img_bytes = generate_plan_image(plan)
        btn_c1.download_button(
            label="Download as image",
            data=img_bytes,
            file_name=f"training_plan_{week}.png",
            mime="image/png",
        )
    except Exception:
        pass
    btn_c2.download_button(
        label="Export to Calendar (.ics)",
        data=generate_ics(plan, ftp),
        file_name=f"training_plan_{week}.ics",
        mime="text/calendar",
        key="ics_export_current",
    )

    st.divider()

    days = plan.get("days", [])
    for idx, day in enumerate(days):
        _day_card_editable(idx, day, len(days), ftp)

    _weekly_summary(plan)


def _render_history(session: dict):
    st.header("Plan History")
    all_plans = load_all_plans(session["athlete_id"])
    if not all_plans:
        st.info("No saved plans yet. Generate your first plan above.")
        return

    ftp = session.get("ftp", 0) or 0
    options = {p.get("week_commencing", "Unknown"): p for p in all_plans}
    selected_week = st.selectbox(
        "Select week", list(options.keys()),
        format_func=lambda w: f"Week of {w}",
    )
    if selected_week:
        _render_plan_readonly(options[selected_week], ftp)
