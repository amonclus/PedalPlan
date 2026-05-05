from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _recommendation(tsb: float, ctl: float) -> tuple[str, str, str]:
    """Returns (label, detail, streamlit color) based on form and fitness."""
    if tsb > 10:
        return (
            "Train Hard",
            "You're fresh and your fitness is solid. Good day for intervals, threshold work, or a long hard ride.",
            "green",
        )
    elif tsb >= -10:
        return (
            "Train Normal",
            "Balanced state — some fatigue but manageable. Stick to your plan; aerobic or moderate tempo work is ideal.",
            "blue",
        )
    elif tsb >= -30:
        return (
            "Train Easy",
            "You've built up meaningful fatigue. Keep intensity low — a Z2 spin or active recovery day will serve you well.",
            "orange",
        )
    else:
        return (
            "Rest",
            "High accumulated fatigue. A rest day or very easy recovery spin will help you absorb training and come back stronger.",
            "red",
        )


def render(athlete: dict, activities: list[dict], load_df: pd.DataFrame):
    name = athlete.get("firstname", "Athlete")
    st.header(f"Welcome back, {name}")

    # ── KPI cards ──────────────────────────────────────────────────────────────
    if not load_df.empty:
        latest = load_df.iloc[-1]
        ctl = latest["ctl"]
        atl = latest["atl"]
        tsb = latest["tsb"]
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        week_tss = load_df.loc[load_df.index >= week_ago, "tss"].sum()
    else:
        ctl = atl = tsb = week_tss = 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Fitness (CTL)", f"{ctl:.0f}", help="42-day exponential average of daily TSS")
    col2.metric("Fatigue (ATL)", f"{atl:.0f}", help="7-day exponential average of daily TSS")
    col3.metric("Form (TSB)", f"{tsb:.0f}", help="CTL − ATL. Positive = fresh, negative = fatigued")
    col4.metric("TSS this week", f"{week_tss:.0f}")

    # ── Recommendation ─────────────────────────────────────────────────────────
    label, detail, color = _recommendation(tsb, ctl)
    color_map = {"green": "#16a34a", "blue": "#2563eb", "orange": "#ea580c", "red": "#dc2626"}
    hex_color = color_map[color]

    st.markdown(
        f"""
        <div style="
            border-left: 5px solid {hex_color};
            background: {hex_color}18;
            padding: 12px 18px;
            border-radius: 6px;
            margin: 12px 0;
        ">
            <span style="font-size:1.1rem; font-weight:700; color:{hex_color};">
                Today's recommendation: {label}
            </span><br/>
            <span style="font-size:0.95rem;">{detail}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Training load chart ────────────────────────────────────────────────────
    st.subheader("Training Load (last 16 weeks)")

    if load_df.empty:
        st.info("No activity data found. Go for a ride and sync Strava!")
    else:
        cutoff = (date.today() - timedelta(weeks=16)).isoformat()
        chart_df = load_df.loc[load_df.index >= cutoff].copy()
        chart_df.index = pd.to_datetime(chart_df.index)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df.index, y=chart_df["ctl"],
            name="CTL (Fitness)", line=dict(color="#3b82f6", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=chart_df.index, y=chart_df["atl"],
            name="ATL (Fatigue)", line=dict(color="#ef4444", width=2),
        ))
        fig.add_trace(go.Bar(
            x=chart_df.index, y=chart_df["tss"],
            name="Daily TSS", marker_color="rgba(100,180,100,0.4)",
            yaxis="y2",
        ))

        fig.update_layout(
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis=dict(title="CTL / ATL"),
            yaxis2=dict(title="TSS", overlaying="y", side="right", showgrid=False),
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("What do these numbers mean?"):
        st.markdown("""
| TSB range | State | Recommendation |
|-----------|-------|----------------|
| > +10 | Fresh | Train Hard |
| 0 to +10 | Neutral | Train Normal |
| −10 to 0 | Slightly tired | Train Normal |
| −10 to −30 | Tired | Train Easy |
| < −30 | Very fatigued | Rest |

**CTL** (Chronic Training Load) — 42-day fitness average.
**ATL** (Acute Training Load) — 7-day fatigue average.
**TSB** = CTL − ATL (your "form").
        """)

    st.divider()

    # ── Recent rides ───────────────────────────────────────────────────────────
    st.subheader("Recent Rides")

    if not activities:
        st.info("No rides found in the last 16 weeks.")
        return

    recent = sorted(activities, key=lambda a: a["date"], reverse=True)
    rows = [{
        "Date": a["date"],
        "Name": a["name"],
        "Distance (km)": a["distance_km"],
        "Time (h)": a["moving_time_h"],
        "Elevation (m)": int(a["elevation_m"]),
        "Avg Power (W)": a["avg_watts"] or "—",
        "Avg HR (bpm)": int(a["avg_hr"]) if a["avg_hr"] else "—",
    } for a in recent]

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=15 * 35 + 38)
