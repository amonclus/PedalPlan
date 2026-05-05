import pandas as pd
import streamlit as st

from auth.strava_oauth import revoke_tokens
from data.strava_client import parse_hr_zones, parse_power_zones
from data.user_settings import save_settings


def render(athlete: dict, strava_zones: dict):
    st.header("Settings")

    # ── Strava account ─────────────────────────────────────────────────────────
    st.subheader("Strava Account")
    col1, col2, col3 = st.columns(3)
    col1.markdown(f"**Name:** {athlete.get('firstname', '')} {athlete.get('lastname', '')}")
    col2.markdown(f"**City:** {athlete.get('city', '—')}, {athlete.get('country', '—')}")
    col3.markdown(f"**Strava ID:** {athlete.get('id', '—')}")

    if st.button("Disconnect Strava", type="secondary"):
        revoke_tokens()
        st.rerun()

    st.divider()

    # ── Training parameters ────────────────────────────────────────────────────
    st.subheader("Training Parameters")
    st.caption("Changes apply immediately to the Overview and Plan tabs.")

    with st.form("training_params"):
        col1, col2 = st.columns(2)
        ftp = col1.number_input(
            "FTP (watts)",
            min_value=50, max_value=600,
            value=st.session_state["ftp"],
            step=5,
        )
        weekly_hours = col2.number_input(
            "Target weekly hours",
            min_value=1, max_value=40,
            value=st.session_state["weekly_hours"],
            step=1,
        )

        goal = st.selectbox(
            "Training goal",
            ["Base fitness", "Race preparation", "Century / sportive", "Weight loss", "Maintain fitness", "Recovery"],
            index=["Base fitness", "Race preparation", "Century / sportive", "Weight loss", "Maintain fitness", "Recovery"].index(
                st.session_state.get("goal", "Base fitness")
            ),
        )

        all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        rest_days = st.multiselect(
            "Preferred rest days",
            options=all_days,
            default=st.session_state.get("rest_days", ["Sunday"]),
            help="The plan will avoid scheduling training on these days where possible.",
        )

        st.markdown("**Heart Rate Zones** — lower bound (bpm)")
        strava_hr = parse_hr_zones(strava_zones) if strava_zones else None
        if strava_hr:
            st.caption("Pre-filled from your Strava account. Override if needed.")

        current_hr = st.session_state["hr_zones"]
        zcols = st.columns(5)
        z1 = zcols[0].number_input("Z1", min_value=60, max_value=220, value=current_hr["z1"])
        z2 = zcols[1].number_input("Z2", min_value=60, max_value=220, value=current_hr["z2"])
        z3 = zcols[2].number_input("Z3", min_value=60, max_value=220, value=current_hr["z3"])
        z4 = zcols[3].number_input("Z4", min_value=60, max_value=220, value=current_hr["z4"])
        z5 = zcols[4].number_input("Z5", min_value=60, max_value=220, value=current_hr["z5"])

        saved = st.form_submit_button("Save Parameters", type="primary")

    if saved:
        new_settings = {
            "ftp": ftp,
            "weekly_hours": weekly_hours,
            "hr_zones": {"z1": z1, "z2": z2, "z3": z3, "z4": z4, "z5": z5},
            "goal": goal,
            "rest_days": rest_days,
        }
        st.session_state.update(new_settings)
        save_settings(new_settings)
        st.session_state["_settings_saved"] = True
        st.rerun()

    if st.session_state.pop("_settings_saved", False):
        st.success("Parameters saved successfully.")

    st.divider()

    # ── HR zones (from Strava) ─────────────────────────────────────────────────
    st.subheader("Heart Rate Zones")
    _render_hr_zones(strava_zones, st.session_state["hr_zones"])

    st.divider()

    # ── Power zones ────────────────────────────────────────────────────────────
    st.subheader("Power Zones")
    _render_power_zones(strava_zones, st.session_state["ftp"])


def _render_hr_zones(strava_zones: dict, current_hr: dict):
    rows = [
        {"Zone": "Z1", "Name": "Recovery",   "Lower bound (bpm)": current_hr["z1"], "Feel": "Very easy, conversational"},
        {"Zone": "Z2", "Name": "Endurance",  "Lower bound (bpm)": current_hr["z2"], "Feel": "Easy, can talk in sentences"},
        {"Zone": "Z3", "Name": "Tempo",      "Lower bound (bpm)": current_hr["z3"], "Feel": "Moderate, uncomfortable to talk"},
        {"Zone": "Z4", "Name": "Threshold",  "Lower bound (bpm)": current_hr["z4"], "Feel": "Hard, only a few words"},
        {"Zone": "Z5", "Name": "VO2 Max",    "Lower bound (bpm)": current_hr["z5"], "Feel": "Very hard, cannot speak"},
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if strava_zones and strava_zones.get("heart_rate", {}).get("custom_zones"):
        st.caption("Using your custom Strava HR zones.")
    elif strava_zones and strava_zones.get("heart_rate"):
        st.caption("Using Strava default HR zones. You can override in the form above.")
    else:
        st.caption("Strava HR zones not available. Using manually entered values.")


def _render_power_zones(strava_zones: dict, ftp: int):
    power_rows = parse_power_zones(strava_zones or {}, ftp)

    if not power_rows:
        st.info("Set your FTP above to see power zones.")
        return

    has_strava_power = bool(strava_zones and strava_zones.get("power", {}).get("zones"))
    if has_strava_power:
        st.caption("Zones pulled directly from your Strava account.")
    else:
        st.caption(f"Calculated from FTP = {ftp} W using classic 7-zone model. "
                   "Strava power zones require a Strava subscription.")

    st.dataframe(pd.DataFrame(power_rows), use_container_width=True, hide_index=True)
