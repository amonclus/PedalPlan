from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _recommendation(tsb: float) -> tuple[str, str, str]:
    if tsb > 10:
        return "Train Hard", "You're fresh. Good day for a quality session — tempo, intervals, or a long run.", "green"
    elif tsb >= -10:
        return "Train Normal", "Balanced state. Stick to your plan — easy running or moderate tempo is ideal.", "blue"
    elif tsb >= -30:
        return "Train Easy", "Meaningful fatigue accumulated. Keep it easy — a Z2 jog or rest will serve you best.", "orange"
    else:
        return "Rest", "High fatigue. A rest day or very easy recovery jog will help you absorb training.", "red"


def render(athlete: dict, activities: list[dict], load_df: pd.DataFrame):
    name = athlete.get("firstname", "Athlete")
    st.header(f"Running — {name}")

    if not activities:
        st.info("No runs found in the last 16 weeks. Go for a run and sync Strava!")
        return

    # ── KPI cards ──────────────────────────────────────────────────────────────
    if not load_df.empty:
        latest = load_df.iloc[-1]
        ctl, atl, tsb = latest["ctl"], latest["atl"], latest["tsb"]
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        week_tss = load_df.loc[load_df.index >= week_ago, "tss"].sum()
    else:
        ctl = atl = tsb = week_tss = 0.0

    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    week_acts = [a for a in activities if a["date"] >= week_start]
    week_km = round(sum(a["distance_km"] for a in week_acts), 1)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fitness (CTL)", f"{ctl:.0f}", help="42-day exponential average of daily TSS")
    col2.metric("Fatigue (ATL)", f"{atl:.0f}", help="7-day exponential average of daily TSS")
    col3.metric("Form (TSB)", f"{tsb:.0f}", help="CTL − ATL. Positive = fresh, negative = fatigued")
    col4.metric("Km this week", f"{week_km} km")

    # ── Recommendation ─────────────────────────────────────────────────────────
    label, detail, color = _recommendation(tsb)
    color_map = {"green": "#16a34a", "blue": "#2563eb", "orange": "#ea580c", "red": "#dc2626"}
    hex_color = color_map[color]
    st.markdown(
        f'<div style="border-left:5px solid {hex_color};background:{hex_color}18;'
        f'padding:12px 18px;border-radius:6px;margin:12px 0;">'
        f'<span style="font-size:1.1rem;font-weight:700;color:{hex_color};">Today\'s recommendation: {label}</span><br/>'
        f'<span style="font-size:0.95rem;">{detail}</span></div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Training load chart ────────────────────────────────────────────────────
    st.subheader("Running Load (last 16 weeks)")
    if not load_df.empty:
        cutoff = (date.today() - timedelta(weeks=16)).isoformat()
        chart_df = load_df.loc[load_df.index >= cutoff].copy()
        chart_df.index = pd.to_datetime(chart_df.index)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["ctl"], name="CTL (Fitness)", line=dict(color="#3b82f6", width=2)))
        fig.add_trace(go.Scatter(x=chart_df.index, y=chart_df["atl"], name="ATL (Fatigue)", line=dict(color="#ef4444", width=2)))
        fig.add_trace(go.Bar(x=chart_df.index, y=chart_df["tss"], name="Daily TSS", marker_color="rgba(100,180,100,0.4)", yaxis="y2"))
        fig.update_layout(
            height=350, margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis=dict(title="CTL / ATL"),
            yaxis2=dict(title="TSS", overlaying="y", side="right", showgrid=False),
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # ── Recent runs ────────────────────────────────────────────────────────────
    st.subheader("Recent Runs")
    recent = sorted(activities, key=lambda a: a["date"], reverse=True)
    rows = [{
        "Date": a["date"],
        "Name": a["name"],
        "Distance (km)": a["distance_km"],
        "Time (h)": a["moving_time_h"],
        "Pace (/km)": a.get("avg_pace") or "—",
        "Elevation (m)": int(a["elevation_m"]),
        "Avg HR (bpm)": int(a["avg_hr"]) if a.get("avg_hr") else "—",
    } for a in recent]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=15 * 35 + 38)
