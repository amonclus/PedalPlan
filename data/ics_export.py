import re
import subprocess
import uuid
from datetime import date, timedelta
from pathlib import Path

from icalendar import Calendar, Event

_DAY_OFFSET = {
    "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
    "Friday": 4, "Saturday": 5, "Sunday": 6,
}


def _fmt_duration(minutes: int) -> str:
    if minutes >= 60:
        h, m = divmod(minutes, 60)
        return f"{h}h {m}min" if m else f"{h}h"
    return f"{minutes}min"


def _fmt_power(power_pct: str, ftp: int) -> str:
    if not power_pct or not ftp:
        return power_pct or ""
    s = power_pct.strip()
    m = re.match(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)%", s)
    if m:
        lo = round(float(m.group(1)) * ftp / 100)
        hi = round(float(m.group(2)) * ftp / 100)
        return f"{s} ({lo}–{hi} W)"
    m = re.match(r"[<＜]\s*(\d+(?:\.\d+)?)%", s)
    if m:
        w = round(float(m.group(1)) * ftp / 100)
        return f"{s} (<{w} W)"
    m = re.match(r"[>＞]\s*(\d+(?:\.\d+)?)%", s)
    if m:
        w = round(float(m.group(1)) * ftp / 100)
        return f"{s} (>{w} W)"
    m = re.match(r"(\d+(?:\.\d+)?)%", s)
    if m:
        w = round(float(m.group(1)) * ftp / 100)
        return f"{s} ({w} W)"
    return s


def generate_ics(plan: dict, ftp: int = 0) -> bytes:
    week_str = plan.get("week_commencing", "")
    week_start = date.fromisoformat(week_str)

    cal = Calendar()
    cal.add("prodid", "-//Training Analysis//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", f"Training Plan w/c {week_str}")

    for day in plan.get("days", []):
        session_type = day.get("type", "Rest")
        if session_type == "Rest":
            continue

        day_name = day.get("day", "Monday")
        event_date = week_start + timedelta(days=_DAY_OFFSET.get(day_name, 0))

        total_min = day.get("duration_min", 0)
        structure = day.get("structure", [])

        lines = [f"Total: {_fmt_duration(total_min)}", ""]
        for step in structure:
            label = step.get("label", "Step")
            dur = step.get("duration_min")
            zone = step.get("zone", "")
            power = _fmt_power(step.get("power_pct", ""), ftp)
            parts = [f"{label}:"]
            if dur:
                parts.append(_fmt_duration(dur))
            if zone:
                parts.append(zone)
            if power:
                parts.append(power)
            lines.append(" | ".join(parts))

        description = day.get("description", "")
        if description:
            lines += ["", description]

        event = Event()
        event.add("uid", str(uuid.uuid4()))
        event.add("summary", f"{session_type} — {_fmt_duration(total_min)}")
        event.add("dtstart", event_date)
        event.add("dtend", event_date + timedelta(days=1))
        event.add("description", "\n".join(lines))
        cal.add_component(event)

    return cal.to_ical()


def save_ics_dialog(plan: dict, ftp: int = 0) -> tuple[bool, str]:
    """
    Show a native macOS save dialog, write the .ics file, and return
    (success, path_or_error_message).
    Falls back to ~/Downloads if osascript is unavailable.
    """
    week_str = plan.get("week_commencing", "unknown")
    default_name = f"training_plan_{week_str}.ics"
    ics_data = generate_ics(plan, ftp)

    result = subprocess.run(
        [
            "osascript",
            "-e",
            (
                f'set f to choose file name with prompt "Save training plan" '
                f'default name "{default_name}" '
                f'default location (path to downloads folder)'
            ),
            "-e",
            "POSIX path of f",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # User cancelled or osascript unavailable
        if "User canceled" in result.stderr or result.returncode == 1:
            return False, "cancelled"
        # Fallback: save to ~/Downloads
        filepath = Path.home() / "Downloads" / default_name
    else:
        filepath = Path(result.stdout.strip())

    filepath = Path(str(filepath).strip())
    if filepath.suffix.lower() != ".ics":
        filepath = filepath.with_suffix(".ics")

    filepath.write_bytes(ics_data)
    return True, str(filepath)


def open_in_calendar(filepath: str):
    subprocess.Popen(["open", filepath])
