from datetime import date, timedelta

import pandas as pd


def estimate_tss(activity: dict, ftp: int, hr_zones: dict) -> float:
    """
    Estimate TSS from power if available, otherwise from heart rate.
    hr_zones: {"z1": x, "z2": x, "z3": x, "z4": x, "z5": x} — lower bounds in bpm.
    """
    duration_h = activity["moving_time_h"]
    if duration_h == 0:
        return 0.0

    if activity["has_power"] and ftp > 0:
        np_watts = activity["avg_watts"]  # approximation: avg ≈ NP for steady rides
        intensity_factor = np_watts / ftp
        tss = (duration_h * 3600 * np_watts * intensity_factor) / (ftp * 3600) * 100
        return round(tss, 1)

    # HR-based TSS (hrTSS) — simplified: map avg HR to an IF equivalent
    avg_hr = activity.get("avg_hr")
    if not avg_hr or not hr_zones:
        # Fallback: assume moderate Z2 effort
        return round(duration_h * 50, 1)

    lthr = hr_zones.get("z4", 160)  # Zone 4 lower bound ≈ lactate threshold HR
    hr_ratio = avg_hr / lthr
    # Clamp IF equivalent between 0.5 and 1.2
    if_equiv = max(0.5, min(1.2, hr_ratio))
    tss = duration_h * if_equiv ** 2 * 100
    return round(tss, 1)


def compute_training_load(activities: list[dict], ftp: int, hr_zones: dict) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by date with columns: tss, ctl, atl, tsb.
    Covers from the earliest activity date to today.
    """
    if not activities:
        return pd.DataFrame(columns=["tss", "ctl", "atl", "tsb"])

    # Build daily TSS series
    tss_by_date: dict[str, float] = {}
    for act in activities:
        d = act["date"]
        tss_by_date[d] = tss_by_date.get(d, 0) + estimate_tss(act, ftp, hr_zones)

    earliest = min(tss_by_date.keys())
    today = date.today().isoformat()

    # Fill every day from earliest to today
    all_dates = []
    cursor = date.fromisoformat(earliest)
    end = date.today()
    while cursor <= end:
        all_dates.append(cursor.isoformat())
        cursor += timedelta(days=1)

    df = pd.DataFrame({"date": all_dates})
    df["tss"] = df["date"].map(tss_by_date).fillna(0)
    df = df.set_index("date")

    # Exponentially weighted CTL (42-day) and ATL (7-day)
    df["ctl"] = df["tss"].ewm(span=42, adjust=False).mean()
    df["atl"] = df["tss"].ewm(span=7, adjust=False).mean()
    df["tsb"] = df["ctl"] - df["atl"]

    return df.round(1)
