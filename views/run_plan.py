import pandas as pd
import streamlit as st

from agent.run_planner import generate_run_plan
from data.ics_export import generate_ics
from data.plan_store import load_all_plans, save_plan

_TYPE_COLOR = {
    "Rest":      "#6b7280",
    "Easy":      "#22c55e",
    "Tempo":     "#f59e0b",
    "Intervals": "#ef4444",
    "Long Run":  "#3b82f6",
    "Race Pace": "#a855f7",
}

_ZONE_COLOR = {
    "Z1":    "#bbf7d0", "Z1-Z2": "#86efac", "Z2":    "#4ade80",
    "Z2-Z3": "#fde68a", "Z3":    "#fbbf24", "Z3-Z4": "#fb923c",
    "Z4":    "#f97316", "Z4-Z5": "#ef4444", "Z5":    "#dc2626",
    "Rest":  "#e5e7eb",
}

_SESSION_TYPES = list(_TYPE_COLOR.keys())
_ZONES = list(_ZONE_COLOR.keys())


def _fmt_duration(minutes: int) -> str:
    if not minutes:
        return "—"
    if minutes >= 60:
        h, m = divmod(int(minutes), 60)
        return f"{h}h {m}min" if m else f"{h}h"
    return f"{int(minutes)}min"


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
        f'<div style="height:8px;border-radius:4px;overflow:hidden;background:#e5e7eb;margin-bottom:8px;">'
        f'{"".join(segments)}</div>',
        unsafe_allow_html=True,
    )


def _structure_table(structure: list[dict]):
    rows = []
    for step in structure:
        rows.append({
            "Step": step.get("label", "—"),
            "Duration": _fmt_duration(step.get("duration_min", 0)),
            "Distance": f"{step['distance_km']} km" if step.get("distance_km") else "—",
            "Zone": step.get("zone", "—"),
            "Target Pace": f"{step['target_pace']} /km" if step.get("target_pace") else "—",
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
    plan = st.session_state["current_run_plan"]
    days = plan["days"]
    for field in ("type", "description", "duration_min", "distance_km", "structure"):
        val_a = days[idx_a].get(field)
        val_b = days[idx_b].get(field)
        days[idx_a][field] = val_b
        days[idx_b][field] = val_a
    save_plan(st.session_state["athlete_id"], plan, sport="running")
    st.rerun()


def _delete_session(idx: int):
    plan = st.session_state["current_run_plan"]
    plan["days"][idx].update({"type": "Rest", "description": "Rest day", "duration_min": 0, "distance_km": 0, "structure": []})
    save_plan(st.session_state["athlete_id"], plan, sport="running")
    st.rerun()


# ── Editable day card ─────────────────────────────────────────────────────────

def _edit_form(idx: int, day: dict):
    structure = day.get("structure", [])
    edited = None

    with st.form(key=f"run_form_{idx}"):
        c1, c2, c3 = st.columns(3)
        new_type = c1.selectbox(
            "Session type", _SESSION_TYPES,
            index=_SESSION_TYPES.index(day["type"]) if day.get("type") in _SESSION_TYPES else 0,
        )
        new_dur = c2.number_input("Duration (min)", min_value=0, max_value=360, value=int(day.get("duration_min", 0)), step=5)
        new_km = c3.number_input("Distance (km)", min_value=0.0, max_value=100.0, value=float(day.get("distance_km", 0)), step=0.5)
        new_desc = st.text_input("Description", value=day.get("description", ""))

        if structure:
            st.caption("Workout steps — edit inline")
            step_df = pd.DataFrame([{
                "Label": s.get("label", ""),
                "Min": int(s.get("duration_min", 0)),
                "Km": float(s.get("distance_km", 0) or 0),
                "Zone": s.get("zone", "Z1"),
                "Pace /km": s.get("target_pace", "") or "",
                "Notes": s.get("notes", "") or "",
            } for s in structure])
            edited = st.data_editor(
                step_df,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "Zone": st.column_config.SelectboxColumn(options=_ZONES, required=True),
                    "Min": st.column_config.NumberColumn(min_value=0, max_value=300, step=5),
                    "Km": st.column_config.NumberColumn(min_value=0.0, max_value=50.0, step=0.5),
                },
                key=f"run_steps_{idx}",
            )

        b1, b2 = st.columns(2)
        submitted = b1.form_submit_button("Save", type="primary", use_container_width=True)
        cancelled = b2.form_submit_button("Cancel", use_container_width=True)

    if cancelled:
        st.session_state[f"run_editing_day_{idx}"] = False
        st.rerun()

    if submitted:
        plan = st.session_state["current_run_plan"]
        d = plan["days"][idx]
        d["type"] = new_type
        d["description"] = new_desc
        d["duration_min"] = int(new_dur)
        d["distance_km"] = float(new_km)
        if edited is not None:
            new_structure = []
            for _, row in edited.iterrows():
                new_structure.append({
                    "label": str(row["Label"]),
                    "duration_min": int(row["Min"]),
                    "distance_km": float(row["Km"]),
                    "zone": str(row["Zone"]),
                    "target_pace": str(row["Pace /km"]) if row["Pace /km"] else "",
                    "notes": str(row["Notes"]) if row["Notes"] else "",
                })
            d["structure"] = new_structure
        save_plan(st.session_state["athlete_id"], plan, sport="running")
        st.session_state[f"run_editing_day_{idx}"] = False
        st.rerun()


def _day_card_editable(idx: int, day: dict, n_days: int):
    session_type = day.get("type", "Rest")
    color = _TYPE_COLOR.get(session_type, "#6b7280")
    structure = day.get("structure", [])
    total_min = day.get("duration_min", 0)
    km = day.get("distance_km", 0)
    is_editing = st.session_state.get(f"run_editing_day_{idx}", False)

    with st.container(border=True):
        header_col, btn_col = st.columns([4, 3])
        with header_col:
            km_str = f" · {km}km" if km else ""
            st.markdown(
                f'<span style="background:{color};color:white;padding:2px 10px;border-radius:12px;font-size:0.82rem;">{session_type}</span>'
                f'&nbsp;<strong>{day["day"]}</strong>'
                f'&nbsp;<span style="color:#6b7280;font-size:0.85rem;">{_fmt_duration(total_min)}{km_str}</span>',
                unsafe_allow_html=True,
            )
            st.caption(day.get("description", ""))
        with btn_col:
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("↑", key=f"run_up_{idx}", disabled=idx == 0):
                _swap_sessions(idx, idx - 1)
            if b2.button("↓", key=f"run_dn_{idx}", disabled=idx == n_days - 1):
                _swap_sessions(idx, idx + 1)
            if b3.button("✏" if not is_editing else "✕", key=f"run_ed_{idx}"):
                st.session_state[f"run_editing_day_{idx}"] = not is_editing
                st.rerun()
            if b4.button("🗑", key=f"run_del_{idx}"):
                _delete_session(idx)

        if is_editing:
            st.divider()
            _edit_form(idx, day)
        elif session_type != "Rest" and structure:
            _zone_bar(structure, total_min)
            _structure_table(structure)


def _day_card_readonly(day: dict):
    session_type = day.get("type", "")
    color = _TYPE_COLOR.get(session_type, "#6b7280")
    structure = day.get("structure", [])
    total_min = day.get("duration_min", 0)
    km = day.get("distance_km", 0)

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        col1.markdown(f"**{day['day']}**  —  {day.get('description', '')}")
        km_str = f" · {km}km" if km else ""
        col2.markdown(
            f'<div style="text-align:right;">'
            f'<span style="background:{color};color:white;padding:3px 12px;border-radius:12px;font-size:0.82rem;">{session_type}</span>'
            f'&nbsp;<span style="color:#6b7280;font-size:0.85rem;">{_fmt_duration(total_min)}{km_str}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if session_type != "Rest" and structure:
            _zone_bar(structure, total_min)
            _structure_table(structure)


def _weekly_summary(plan: dict):
    rows, total_min, total_km = [], 0, 0.0
    for d in plan.get("days", []):
        dur = d.get("duration_min", 0)
        km = d.get("distance_km", 0)
        total_min += dur
        total_km += km
        rows.append({"Day": d["day"], "Session": d["type"], "Duration": _fmt_duration(dur), "Distance": f"{km} km" if km else "—"})
    with st.expander("Weekly summary"):
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"Total: {_fmt_duration(total_min)} · {round(total_km, 1)} km")


def _render_plan_readonly(plan: dict):
    week = plan.get("week_commencing", "")
    st.markdown(f"**Week of {week}** — {plan.get('summary', '')}")
    st.download_button(
        label="Export to Calendar (.ics)",
        data=generate_ics(plan),
        file_name=f"run_plan_{week}.ics",
        mime="text/calendar",
        key=f"run_ics_{week}",
    )
    st.divider()
    for day in plan.get("days", []):
        _day_card_readonly(day)
    _weekly_summary(plan)


# ── Tab renderers ─────────────────────────────────────────────────────────────

def render(activities: list[dict], load_df, session: dict):
    tab_current, tab_history = st.tabs(["Current Plan", "Plan History"])
    with tab_current:
        _render_current(activities, load_df, session)
    with tab_history:
        _render_history(session)


def _render_current(activities, load_df, session):
    st.header("Weekly Running Plan")

    api_key = session.get("claude_api_key", "")
    if not api_key:
        st.warning("Add your Claude API key in **Settings → Claude API Key** to enable plan generation.", icon="🔑")
        return

    plan = st.session_state.get("current_run_plan")

    comments = st.text_area(
        "Notes for the coach (optional)",
        placeholder="e.g. My legs feel heavy, I have a race in 3 weeks, I want to focus on 5K speed…",
        key="run_plan_comments",
    )

    btn_col, _ = st.columns([2, 5])
    label = "Generate New Plan" if plan else "Generate Plan"
    if btn_col.button(label, type="primary", key="run_gen_btn"):
        user_params = {
            "run_threshold_pace": session.get("run_threshold_pace", "5:30"),
            "run_weekly_km": session.get("run_weekly_km", 40),
            "hr_zones": session["hr_zones"],
            "run_goal": session.get("run_goal", "Base fitness"),
            "rest_days": session.get("rest_days", []),
            "comments": comments.strip(),
        }
        with st.spinner("Generating your running plan…"):
            try:
                new_plan = generate_run_plan(activities, load_df, user_params, api_key)
                save_plan(session["athlete_id"], new_plan, sport="running")
                st.session_state["current_run_plan"] = new_plan
                for key in list(st.session_state.keys()):
                    if key.startswith("run_editing_day_"):
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                st.error(f"Failed to generate plan: {e}")
                return

    if plan:
        if label == "Generate New Plan":
            st.caption("Generating a new plan will replace the current week.")
    else:
        st.info("Hit **Generate Plan** to get a personalised running schedule based on your Strava data.", icon="📅")
        return

    week = plan.get("week_commencing", "")
    st.markdown(f"**Week of {week}** — {plan.get('summary', '')}")
    st.download_button(
        label="Export to Calendar (.ics)",
        data=generate_ics(plan),
        file_name=f"run_plan_{week}.ics",
        mime="text/calendar",
        key="run_ics_current",
    )
    st.divider()

    days = plan.get("days", [])
    for idx, day in enumerate(days):
        _day_card_editable(idx, day, len(days))
    _weekly_summary(plan)


def _render_history(session: dict):
    st.header("Plan History")
    all_plans = load_all_plans(session["athlete_id"], sport="running")
    if not all_plans:
        st.info("No saved running plans yet. Generate your first plan above.")
        return
    options = {p.get("week_commencing", "Unknown"): p for p in all_plans}
    selected_week = st.selectbox("Select week", list(options.keys()), format_func=lambda w: f"Week of {w}", key="run_hist_sel")
    if selected_week:
        _render_plan_readonly(options[selected_week])
