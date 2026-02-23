#!/usr/bin/env python3
"""
Garmin health vitals - daily and weekly queries.

Commands:
    python garmin_health.py today          # Today's vitals
    python garmin_health.py 2026-02-22     # Specific date
    python garmin_health.py yesterday      # Yesterday's vitals
    python garmin_health.py week           # Last 7 days summary table
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from garmin_client import get_client, load_config, GarminConfigError


def fetch_day_data(client, cdate: str) -> dict:
    """Fetch all health data for a single day from Garmin API.

    Args:
        client: Authenticated Garmin client.
        cdate: Date string in YYYY-MM-DD format.

    Returns:
        Dict with keys: stats, hrv, body_battery, stress.
    """
    stats = _safe_call(client.get_stats, cdate) or {}
    hrv = _safe_call(client.get_hrv_data, cdate)
    body_battery = _safe_call(client.get_body_battery, cdate) or []
    stress = _safe_call(client.get_stress_data, cdate) or {}
    return {
        "stats": stats,
        "hrv": hrv,
        "body_battery": body_battery,
        "stress": stress,
    }


def _safe_call(fn, *args, **kwargs):
    """Call a Garmin API method, returning None on error."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def format_daily_vitals(
    cdate: str,
    stats: dict,
    hrv: dict | None,
    body_battery: list,
    stress: dict,
) -> str:
    """Format a day's health vitals as a readable table.

    Args:
        cdate: Date string YYYY-MM-DD.
        stats: Response from get_stats().
        hrv: Response from get_hrv_data() or None.
        body_battery: Response from get_body_battery().
        stress: Response from get_stress_data().

    Returns:
        Formatted string with vitals table.
    """
    rhr = stats.get("restingHeartRate")
    rhr_str = f"{rhr} bpm" if rhr else "No data"

    hrv_val = None
    if hrv and isinstance(hrv, dict):
        summary = hrv.get("hrvSummary", {})
        if summary:
            hrv_val = summary.get("lastNightAvg") or summary.get("weeklyAvg")
    hrv_str = f"{hrv_val} ms" if hrv_val else "No data"

    if body_battery and len(body_battery) > 0:
        bb = body_battery[0] if isinstance(body_battery, list) else body_battery
        charged = bb.get("charged", "?")
        drained = bb.get("drained", "?")
        if isinstance(charged, (int, float)) and isinstance(drained, (int, float)):
            bb_str = f"{charged} \u2192 {charged - drained}"
        else:
            bb_str = "No data"
    else:
        bb_str = "No data"

    stress_val = stress.get("overallStressLevel")
    stress_str = f"Avg {stress_val}" if stress_val else "No data"

    steps = stats.get("totalSteps")
    steps_str = f"{steps:,}" if steps else "No data"

    cals = stats.get("totalKilocalories")
    cals_str = f"{cals:,}" if cals else "No data"

    lines = [
        f"## Vitals \u2014 {cdate}",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Resting HR | {rhr_str} |",
        f"| HRV | {hrv_str} |",
        f"| Body Battery | {bb_str} |",
        f"| Stress | {stress_str} |",
        f"| Steps | {steps_str} |",
        f"| Calories | {cals_str} |",
    ]
    return "\n".join(lines)


def extract_day_summary(cdate: str, data: dict) -> dict:
    """Extract summary metrics from a day's raw data for weekly aggregation.

    Args:
        cdate: Date string YYYY-MM-DD.
        data: Dict from fetch_day_data().

    Returns:
        Dict with normalised metric values.
    """
    stats = data.get("stats", {})
    hrv = data.get("hrv")
    body_battery = data.get("body_battery", [])
    stress = data.get("stress", {})

    hrv_val = None
    if hrv and isinstance(hrv, dict):
        summary = hrv.get("hrvSummary", {})
        if summary:
            hrv_val = summary.get("lastNightAvg") or summary.get("weeklyAvg")

    bb_peak = None
    if body_battery and len(body_battery) > 0:
        bb = body_battery[0] if isinstance(body_battery, list) else body_battery
        bb_peak = bb.get("charged")

    return {
        "date": cdate,
        "resting_hr": stats.get("restingHeartRate"),
        "hrv": hrv_val,
        "body_battery_peak": bb_peak,
        "steps": stats.get("totalSteps"),
        "stress_avg": stress.get("overallStressLevel"),
    }


def format_weekly_vitals(days: list[dict]) -> str:
    """Format multiple days of vitals as a weekly summary table.

    Args:
        days: List of dicts from extract_day_summary(), one per day.

    Returns:
        Formatted string with weekly trends table.
    """
    if not days:
        return "No data available for this week."

    # Build day labels from dates
    day_names = []
    for d in days:
        try:
            dt = date.fromisoformat(d["date"])
            day_names.append(dt.strftime("%a"))
        except (ValueError, KeyError):
            day_names.append("?")

    metrics = [
        ("Resting HR", "resting_hr", ""),
        ("HRV", "hrv", ""),
        ("Body Battery Peak", "body_battery_peak", ""),
        ("Steps", "steps", "k"),
        ("Stress", "stress_avg", ""),
    ]

    # Header
    header = "| Metric | " + " | ".join(day_names) + " | Avg |"
    separator = "|--------|" + "|".join(["-----"] * len(days)) + "|-----|"

    rows = [header, separator]
    for label, key, fmt in metrics:
        values = [d.get(key) for d in days]
        cells = []
        for v in values:
            if v is None:
                cells.append("-")
            elif fmt == "k":
                cells.append(f"{v/1000:.1f}k")
            else:
                cells.append(str(v))

        # Average
        numeric = [v for v in values if v is not None]
        if numeric:
            avg = sum(numeric) / len(numeric)
            avg_str = f"{avg/1000:.1f}k" if fmt == "k" else str(round(avg))
        else:
            avg_str = "-"

        row = f"| {label} | " + " | ".join(cells) + f" | {avg_str} |"
        rows.append(row)

    return "\n".join(rows)


def resolve_date(date_arg: str) -> str:
    """Convert date argument to YYYY-MM-DD string.

    Accepts: 'today', 'yesterday', or YYYY-MM-DD.
    """
    if date_arg == "today":
        return date.today().isoformat()
    elif date_arg == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    else:
        # Validate format
        date.fromisoformat(date_arg)
        return date_arg


def main():
    parser = argparse.ArgumentParser(description="Garmin daily health vitals")
    parser.add_argument(
        "command",
        help="'today', 'yesterday', 'week', or a YYYY-MM-DD date",
    )
    args = parser.parse_args()

    try:
        config = load_config()
        client = get_client(config)
    except GarminConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command == "week":
        today = date.today()
        days = []
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            data = fetch_day_data(client, d)
            days.append(extract_day_summary(d, data))
        print(format_weekly_vitals(days))
    else:
        cdate = resolve_date(args.command)
        data = fetch_day_data(client, cdate)
        print(format_daily_vitals(
            cdate=cdate,
            stats=data["stats"],
            hrv=data["hrv"],
            body_battery=data["body_battery"],
            stress=data["stress"],
        ))


if __name__ == "__main__":
    main()
