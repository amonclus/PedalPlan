import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET")
REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8501")
TOKENS_FILE = Path(__file__).parent.parent / "tokens.json"

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


def exchange_code_for_tokens(code: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    tokens = resp.json()
    _save_tokens(tokens)
    return tokens


def refresh_tokens(refresh_token: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    tokens = resp.json()
    _save_tokens(tokens)
    return tokens


def load_tokens() -> dict | None:
    if not TOKENS_FILE.exists():
        return None
    with open(TOKENS_FILE) as f:
        return json.load(f)


def get_valid_access_token() -> str | None:
    tokens = load_tokens()
    if not tokens:
        return None
    if time.time() >= tokens["expires_at"] - 60:
        tokens = refresh_tokens(tokens["refresh_token"])
    return tokens["access_token"]


def is_authenticated() -> bool:
    return load_tokens() is not None


def revoke_tokens():
    if TOKENS_FILE.exists():
        TOKENS_FILE.unlink()


def _save_tokens(tokens: dict):
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f)
