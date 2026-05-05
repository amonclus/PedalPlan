from datetime import datetime, timedelta, timezone

import requests

BASE_URL = "https://www.strava.com/api/v3"


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def get_athlete(access_token: str) -> dict:
    resp = requests.get(f"{BASE_URL}/athlete", headers=_headers(access_token))
    resp.raise_for_status()
    return resp.json()


def get_activities(access_token: str, weeks: int = 16) -> list[dict]:
    """Fetch rides from the past `weeks` weeks, handling pagination."""
    after = int((datetime.now(timezone.utc) - timedelta(weeks=weeks)).timestamp())
    activities = []
    page = 1

    while True:
        resp = requests.get(
            f"{BASE_URL}/athlete/activities",
            headers=_headers(access_token),
            params={"after": after, "per_page": 100, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        page += 1

    return [a for a in activities if a.get("type") == "Ride"]


def parse_activity(raw: dict) -> dict:
    """Extract the fields we care about from a raw Strava activity."""
    moving_time_h = raw.get("moving_time", 0) / 3600
    avg_watts = raw.get("average_watts")
    avg_hr = raw.get("average_heartrate")

    return {
        "id": raw["id"],
        "name": raw.get("name", ""),
        "date": raw.get("start_date_local", "")[:10],
        "distance_km": round(raw.get("distance", 0) / 1000, 1),
        "moving_time_h": round(moving_time_h, 2),
        "elevation_m": raw.get("total_elevation_gain", 0),
        "avg_watts": avg_watts,
        "avg_hr": avg_hr,
        "has_power": avg_watts is not None,
    }


def get_parsed_activities(access_token: str, weeks: int = 16) -> list[dict]:
    raw = get_activities(access_token, weeks=weeks)
    return [parse_activity(a) for a in raw]


def get_athlete_zones(access_token: str) -> dict:
    """
    Returns HR and power zones configured in Strava.
    Power zones require a Strava subscription — returns empty dict on 402.
    HR zones format: list of {min, max} dicts (5 zones, max=-1 means unbounded).
    Power zones format: same, but 7 zones.
    """
    resp = requests.get(f"{BASE_URL}/athlete/zones", headers=_headers(access_token))
    if resp.status_code in (401, 402, 403):
        return {}
    resp.raise_for_status()
    return resp.json()


def parse_hr_zones(zones_data: dict) -> dict | None:
    """Convert Strava HR zones list into {z1..z5} lower-bound dict."""
    hr = zones_data.get("heart_rate", {})
    zones = hr.get("zones", [])
    if len(zones) < 5:
        return None
    keys = ["z1", "z2", "z3", "z4", "z5"]
    return {k: z["min"] for k, z in zip(keys, zones)}


def parse_power_zones(zones_data: dict, ftp: int) -> list[dict] | None:
    """
    Convert Strava power zones list into display-friendly records.
    Falls back to classic 7-zone FTP percentages if Strava zones are absent.
    """
    pwr = zones_data.get("power", {})
    zones = pwr.get("zones", [])
    names = ["Active Recovery", "Endurance", "Tempo", "Threshold", "VO2 Max", "Anaerobic", "Neuromuscular"]
    pct_ranges = ["< 55%", "55–75%", "76–90%", "91–105%", "106–120%", "121–150%", "> 150%"]

    if zones:
        rows = []
        for i, z in enumerate(zones):
            label = names[i] if i < len(names) else f"Zone {i+1}"
            low = z["min"]
            high = z["max"] if z["max"] != -1 else "max"
            rows.append({"Zone": f"Z{i+1}", "Name": label, "Range (W)": f"{low} – {high}"})
        return rows

    if ftp <= 0:
        return None

    # Classic 7-zone FTP percentages as fallback
    pct_bounds = [(0, 0.55), (0.55, 0.75), (0.76, 0.90), (0.91, 1.05),
                  (1.06, 1.20), (1.21, 1.50), (1.50, None)]
    rows = []
    for i, ((lo, hi), name, pct) in enumerate(zip(pct_bounds, names, pct_ranges)):
        low_w = int(ftp * lo)
        high_w = f"{int(ftp * hi)}" if hi else "max"
        rows.append({"Zone": f"Z{i+1}", "Name": name, "Range (W)": f"{low_w} – {high_w}", "% FTP": pct})
    return rows
