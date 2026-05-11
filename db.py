"""
File-based storage backend. All user data lives under _STORE (default: _store/).
Layout:
  _store/users/{athlete_id}.json   — tokens + settings + claude_api_key
  _store/plans/{athlete_id}/plan_{week}.json
  _store/sessions/{token}.json
"""

import json
import os
import shutil
import time
from pathlib import Path

_STORE = Path(os.getenv("STORE_PATH", "_store"))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _user_file(athlete_id: int) -> Path:
    d = _STORE / "users"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{athlete_id}.json"


def _plans_dir(athlete_id: int) -> Path:
    d = _STORE / "plans" / str(athlete_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sessions_dir() -> Path:
    d = _STORE / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_user(athlete_id: int) -> dict:
    f = _user_file(athlete_id)
    if not f.exists():
        return {}
    return json.loads(f.read_text())


def _save_user(athlete_id: int, data: dict):
    _user_file(athlete_id).write_text(json.dumps(data))


# ── Init (no-op for file store, kept for API compatibility) ───────────────────

def init_db():
    _STORE.mkdir(exist_ok=True)


# ── Tokens ────────────────────────────────────────────────────────────────────

def upsert_user_tokens(athlete_id: int, access_token: str, refresh_token: str, expires_at: int):
    data = _load_user(athlete_id)
    data.update(access_token=access_token, refresh_token=refresh_token, expires_at=expires_at)
    _save_user(athlete_id, data)


def get_user_tokens(athlete_id: int) -> dict | None:
    data = _load_user(athlete_id)
    if not all(k in data for k in ("access_token", "refresh_token", "expires_at")):
        return None
    return {k: data[k] for k in ("access_token", "refresh_token", "expires_at")}


def delete_user(athlete_id: int):
    f = _user_file(athlete_id)
    if f.exists():
        f.unlink()
    d = _STORE / "plans" / str(athlete_id)
    if d.exists():
        shutil.rmtree(d)
    for sf in _sessions_dir().glob("*.json"):
        try:
            if json.loads(sf.read_text()).get("athlete_id") == athlete_id:
                sf.unlink()
        except (json.JSONDecodeError, OSError):
            pass


# ── Claude API key ────────────────────────────────────────────────────────────

def get_claude_api_key(athlete_id: int) -> str | None:
    return _load_user(athlete_id).get("claude_api_key")


def set_claude_api_key(athlete_id: int, api_key: str):
    data = _load_user(athlete_id)
    data["claude_api_key"] = api_key
    _save_user(athlete_id, data)


# ── Settings ──────────────────────────────────────────────────────────────────

def get_settings(athlete_id: int) -> str | None:
    return _load_user(athlete_id).get("settings_json")


def save_settings_json(athlete_id: int, settings_json: str):
    data = _load_user(athlete_id)
    data["settings_json"] = settings_json
    _save_user(athlete_id, data)


# ── Plans ─────────────────────────────────────────────────────────────────────

def save_plan(athlete_id: int, week_commencing: str, plan_json: str, sport: str = "cycling"):
    prefix = "run_plan" if sport == "running" else "plan"
    (_plans_dir(athlete_id) / f"{prefix}_{week_commencing}.json").write_text(plan_json)


def load_all_plans(athlete_id: int, sport: str = "cycling") -> list[str]:
    prefix = "run_plan" if sport == "running" else "plan"
    return [
        p.read_text()
        for p in sorted(_plans_dir(athlete_id).glob(f"{prefix}_*.json"), reverse=True)
    ]


# ── Sessions ──────────────────────────────────────────────────────────────────

def create_session(token: str, athlete_id: int, expires_at: int):
    (_sessions_dir() / f"{token}.json").write_text(
        json.dumps({"athlete_id": athlete_id, "expires_at": expires_at})
    )


def get_session(token: str) -> int | None:
    f = _sessions_dir() / f"{token}.json"
    if not f.exists():
        return None
    data = json.loads(f.read_text())
    if data["expires_at"] > int(time.time()):
        return data["athlete_id"]
    f.unlink()
    return None


def delete_session(token: str):
    f = _sessions_dir() / f"{token}.json"
    if f.exists():
        f.unlink()
