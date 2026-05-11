import os
import secrets
import time

import streamlit as st
from dotenv import load_dotenv
from streamlit_cookies_controller import CookieController

load_dotenv()

import db
from auth.strava_oauth import (
    exchange_code_for_tokens,
    get_authorization_url,
    get_valid_access_token,
    revoke_tokens,
)
from data.strava_client import get_athlete, get_athlete_zones, get_parsed_activities, parse_hr_zones
from data.user_settings import load_settings
from data.plan_store import load_all_plans
from metrics.training_load import compute_training_load
from views import overview, plan, settings as settings_view, this_week

st.set_page_config(
    page_title="Training Dashboard",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="collapsed",
)

db.init_db()

_SECURE_COOKIE = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8501").startswith("https")
_SESSION_TTL = 30 * 24 * 3600  # 30 days

controller = CookieController()

# ── Logout handler ─────────────────────────────────────────────────────────────
# Must run before session resolution so we clear state before re-reading it.

if st.session_state.get("_do_logout"):
    sid = st.session_state.get("_sid")
    athlete_id = st.session_state.get("athlete_id")
    if sid:
        db.delete_session(sid)
        controller.remove("sid")
    if athlete_id:
        revoke_tokens(athlete_id)
    st.session_state.clear()
    st.rerun()

# ── Session resolution ─────────────────────────────────────────────────────────
# athlete_id is kept in st.session_state throughout a browser tab session.
# On a fresh tab, restore it from the "sid" cookie if valid.

if "athlete_id" not in st.session_state:
    sid = controller.get("sid")
    if sid:
        athlete_id = db.get_session(sid)
        if athlete_id:
            st.session_state["athlete_id"] = athlete_id
            st.session_state["_sid"] = sid
        else:
            controller.remove("sid")

# ── OAuth callback ─────────────────────────────────────────────────────────────

params = st.query_params
if "code" in params and "athlete_id" not in st.session_state:
    try:
        athlete_id = exchange_code_for_tokens(params["code"])
        token = secrets.token_hex(32)
        expires_at = int(time.time()) + _SESSION_TTL
        db.create_session(token, athlete_id, expires_at)
        controller.set("sid", token, max_age=_SESSION_TTL, secure=_SECURE_COOKIE, same_site="Lax")
        st.session_state["athlete_id"] = athlete_id
        st.session_state["_sid"] = token
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Authentication failed: {e}")

# ── Auth gate ──────────────────────────────────────────────────────────────────

if "athlete_id" not in st.session_state:
    st.title("🚴 Training Dashboard")
    st.markdown("Connect your Strava account to get started.")
    st.link_button("Connect with Strava", get_authorization_url(), type="primary")
    st.stop()

athlete_id: int = st.session_state["athlete_id"]

# ── Session state defaults ─────────────────────────────────────────────────────

if "settings_loaded" not in st.session_state:
    saved = load_settings(athlete_id)
    st.session_state["ftp"] = saved["ftp"]
    st.session_state["weekly_hours"] = saved["weekly_hours"]
    st.session_state["hr_zones"] = saved["hr_zones"]
    st.session_state["goal"] = saved.get("goal", "Base fitness")
    st.session_state["rest_days"] = saved.get("rest_days", ["Sunday"])
    st.session_state["strava_zones_loaded"] = False
    st.session_state["settings_loaded"] = True

if "claude_api_key" not in st.session_state:
    st.session_state["claude_api_key"] = db.get_claude_api_key(athlete_id) or ""

if "current_plan" not in st.session_state:
    from datetime import date, timedelta
    today = date.today()
    this_monday = (today - timedelta(days=today.weekday())).isoformat()
    all_plans = load_all_plans(athlete_id)
    matched = next((p for p in all_plans if p.get("week_commencing") == this_monday), None)
    st.session_state["current_plan"] = matched or (all_plans[0] if all_plans else None)

# ── Fetch Strava data ──────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner="Fetching Strava data…")
def load_strava_data(aid: int) -> tuple:
    token = get_valid_access_token(aid)
    athlete = get_athlete(token)
    activities = get_parsed_activities(token, weeks=16)
    zones = get_athlete_zones(token)
    return athlete, activities, zones


try:
    athlete, activities, strava_zones = load_strava_data(athlete_id)
except Exception as e:
    st.error(f"Failed to load Strava data: {e}")
    st.stop()

if not st.session_state["strava_zones_loaded"] and strava_zones:
    parsed_hr = parse_hr_zones(strava_zones)
    if parsed_hr:
        st.session_state["hr_zones"] = parsed_hr
    st.session_state["strava_zones_loaded"] = True

# ── Compute training load ──────────────────────────────────────────────────────

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
