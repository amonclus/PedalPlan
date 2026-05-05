import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from auth.strava_oauth import (
    get_authorization_url,
    exchange_code_for_tokens,
    get_valid_access_token,
    is_authenticated,
    revoke_tokens,
)
from data.strava_client import get_athlete, get_parsed_activities, get_athlete_zones, parse_hr_zones
from data.user_settings import load_settings
from metrics.training_load import compute_training_load
from views import overview, plan, settings as settings_view, this_week

st.set_page_config(
    page_title="Training Dashboard",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── OAuth callback ─────────────────────────────────────────────────────────────

params = st.query_params
if "code" in params and not is_authenticated():
    try:
        exchange_code_for_tokens(params["code"])
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Authentication failed: {e}")

# ── Auth gate ──────────────────────────────────────────────────────────────────

if not is_authenticated():
    st.title("🚴 Training Dashboard")
    st.markdown("Connect your Strava account to get started.")
    st.link_button("Connect with Strava", get_authorization_url(), type="primary")
    st.stop()

# ── Session state defaults ─────────────────────────────────────────────────────

if "settings_loaded" not in st.session_state:
    saved = load_settings()
    st.session_state["ftp"] = saved["ftp"]
    st.session_state["weekly_hours"] = saved["weekly_hours"]
    st.session_state["hr_zones"] = saved["hr_zones"]
    st.session_state["goal"] = saved.get("goal", "Base fitness")
    st.session_state["rest_days"] = saved.get("rest_days", ["Sunday"])
    st.session_state["strava_zones_loaded"] = False
    st.session_state["settings_loaded"] = True

# ── Fetch Strava data (cached, no user-param dependency) ──────────────────────

@st.cache_data(ttl=300, show_spinner="Fetching Strava data…")
def load_strava_data() -> tuple:
    token = get_valid_access_token()
    athlete = get_athlete(token)
    activities = get_parsed_activities(token, weeks=16)
    zones = get_athlete_zones(token)
    return athlete, activities, zones


try:
    athlete, activities, strava_zones = load_strava_data()
except Exception as e:
    st.error(f"Failed to load Strava data: {e}")
    st.stop()

# Pre-populate HR zones from Strava on first load
if not st.session_state["strava_zones_loaded"] and strava_zones:
    parsed_hr = parse_hr_zones(strava_zones)
    if parsed_hr:
        st.session_state["hr_zones"] = parsed_hr
    st.session_state["strava_zones_loaded"] = True

# ── Compute training load with current settings ────────────────────────────────

load_df = compute_training_load(
    activities,
    ftp=st.session_state["ftp"],
    hr_zones=st.session_state["hr_zones"],
)

# ── Navigation ─────────────────────────────────────────────────────────────────

tab_overview, tab_week, tab_plan, tab_settings = st.tabs(["Overview", "This Week", "Plan", "Settings"])

with tab_overview:
    overview.render(athlete, activities, load_df)

with tab_week:
    this_week.render(activities, load_df, st.session_state)

with tab_plan:
    plan.render(activities, load_df, st.session_state)

with tab_settings:
    settings_view.render(athlete, strava_zones)
