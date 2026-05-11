import os
import time

import requests
from dotenv import load_dotenv

import db

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8501")

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
SCOPES = "read,activity:read_all,profile:read_all"


def get_authorization_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPES,
    }
    req = requests.Request("GET", AUTH_URL, params=params)
    return req.prepare().url


def exchange_code_for_tokens(code: str) -> int:
    """Exchange auth code for tokens. Returns the Strava athlete_id."""
    resp = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    data = resp.json()
    athlete_id = data["athlete"]["id"]
    db.upsert_user_tokens(
        athlete_id=athlete_id,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=data["expires_at"],
    )
    return athlete_id


def get_valid_access_token(athlete_id: int) -> str | None:
    tokens = db.get_user_tokens(athlete_id)
    if not tokens:
        return None
    if time.time() >= tokens["expires_at"] - 60:
        tokens = _refresh_tokens(athlete_id, tokens["refresh_token"])
    return tokens["access_token"]


def revoke_tokens(athlete_id: int):
    db.delete_user(athlete_id)


def restore_session(athlete_id: int, refresh_token: str) -> bool:
    """Re-establish a session using a stored refresh token. Returns True on success."""
    try:
        _refresh_tokens(athlete_id, refresh_token)
        return True
    except Exception:
        return False


def _refresh_tokens(athlete_id: int, refresh_token: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    data = resp.json()
    db.upsert_user_tokens(
        athlete_id=athlete_id,
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=data["expires_at"],
    )
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": data["expires_at"],
    }
