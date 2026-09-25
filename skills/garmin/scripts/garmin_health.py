#!/usr/bin/env python3
"""
Garmin health vitals - daily and weekly queries.

Commands:
    python garmin_health.py today          # Today's vitals
    python garmin_health.py 2026-02-22     # Specific date
    python garmin_health.py yesterday      # Yesterday's vitals
    python garmin_health.py week           # Last 7 days summary table
    python garmin_health.py today --json   # The same figures, unformatted, as JSON
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from garmin_client import (
    GarminConfigError,
    GarminFetchError,
    fetch,
    get_client,
    load_config,
    pause_between_days,
)


def fetch_day_data(client, cdate: str, body_battery: list | None = None) -> dict:
    """Fetch all health data for a single day from Garmin API.

    Args:
        client: Authenticated Garmin client.
        cdate: Date string in YYYY-MM-DD format.
        body_battery: The day's get_body_battery() entries, when a range call
            has already fetched them. None means fetch them here.

    Returns:
        Dict with keys: stats, hrv, body_battery, stress. A key Garmin has
        nothing for is empty, and renders as "No data".

    Raises:
        GarminFetchError: a call failed. Nothing about the day is known.
    """
    stats = fetch(client.get_stats, cdate) or {}
    hrv = fetch(client.get_hrv_data, cdate)
    if body_battery is None:
        body_battery = fetch(client.get_body_battery, cdate) or []
    stress = fetch(client.get_stress_data, cdate) or {}
    return {
        "stats": stats,
        "hrv": hrv,
        "body_battery": body_battery,
        "stress": stress,
    }


def fetch_day_summaries(client, dates: list[str], today: date | None = None, summarise=None) -> list[dict]:
    """Day summaries for several dates, fetched one day at a time.

    Paced: pause_between_days() runs before every day after the first, and
    refuses to go on once a cooldown is running. A date after today gets an
    empty summary and no call, because Garmin has nothing for a day that has
    not happened. Body Battery comes from one range call for all the dates,
    since get_body_battery() takes a range and answers each day in the same
    shape as a single-day call. The other endpoints have no range form with a
    documented shape, so they stay per day.

    summarise turns (date, day data) into the summary, and defaults to
    extract_day_summary(), which the weekly table reads. --json passes
    day_values(), so a day in the week has the same fields as a single day.

    Raises:
        GarminFetchError: a call failed, or a cooldown started. The run stops
            there, and no later day is fetched.
    """
    summarise = summarise or extract_day_summary
    last = (today or date.today()).isoformat()
    past = sorted(d for d in dates if d <= last)
    by_date = {}
    if past:
        entries = fetch(client.get_body_battery, past[0], past[-1]) or []
        by_date = {e.get("date"): e for e in entries if isinstance(e, dict)}

    summaries = []
    fetched = 0
    for d in dates:
        if d > last:
            summaries.append(summarise(d, {}))
            continue
        if fetched:
            pause_between_days()
        data = fetch_day_data(client, d, body_battery=[by_date[d]] if d in by_date else [])
        summaries.append(summarise(d, data))
        fetched += 1
    return summaries


def _is_level(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _levels_from_values_array(body_battery) -> list:
    """Body Battery levels through the day, oldest first, from get_body_battery().

    Each reading in bodyBatteryValuesArray is a list, and the response carries
    a descriptor list naming what each position holds. The level is found by
    that name rather than by a guessed position; with no descriptor, there are
    no levels.
    """
    day = body_battery[0] if isinstance(body_battery, list) and body_battery else body_battery
    if not isinstance(day, dict):
        return []
    positions = {
        d.get("bodyBatteryValueDescriptorKey"): d.get("bodyBatteryValueDescriptorIndex")
        for d in day.get("bodyBatteryValueDescriptorDTOList") or []
        if isinstance(d, dict)
    }
    at_time, at_level = positions.get("timestamp"), positions.get("bodyBatteryLevel")
    if not isinstance(at_level, int):
        return []
    readings = []
    for reading in day.get("bodyBatteryValuesArray") or []:
        if isinstance(reading, list) and len(reading) > at_level and _is_level(reading[at_level]):
            when = reading[at_time] if isinstance(at_time, int) and len(reading) > at_time else 0
            readings.append((when if _is_level(when) else 0, reading[at_level]))
    return [level for _, level in sorted(readings, key=lambda r: r[0])]


def body_battery_levels(stats: dict, body_battery) -> tuple:
    """The day's lowest, highest and most recent Body Battery level (0 to 100).

    Taken from the daily summary's level fields, falling back to the readings
    in get_body_battery() when the summary has none. Never from "charged" and
    "drained": those are how much was gained and lost over the day, amounts
    rather than levels, and subtracting one from the other can go below zero.

    Returns:
        (lowest, highest, most_recent). Any of them can be None.
    """
    stats = stats or {}
    low = stats.get("bodyBatteryLowestValue")
    high = stats.get("bodyBatteryHighestValue")
    latest = stats.get("bodyBatteryMostRecentValue")
    low, high, latest = (v if _is_level(v) else None for v in (low, high, latest))
    if low is None and high is None and latest is None:
        levels = _levels_from_values_array(body_battery)
        if levels:
            low, high, latest = min(levels), max(levels), levels[-1]
    return low, high, latest


def format_body_battery(stats: dict, body_battery) -> str:
    """The Body Battery row: the day's range and its most recent level."""
    low, high, latest = body_battery_levels(stats, body_battery)
    parts = []
    if low is not None and high is not None:
        parts.append(f"{low}-{high}")
    elif high is not None:
        parts.append(f"high {high}")
    elif low is not None:
        parts.append(f"low {low}")
    if latest is not None:
        parts.append(f"latest {latest}")
    return ", ".join(parts) if parts else "No data"


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
        stats: Response from get_stats(). Also the source of Body Battery levels.
        hrv: Response from get_hrv_data() or None.
        body_battery: Response from get_body_battery(), used for Body Battery
            only when stats has no level fields.
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

    bb_str = format_body_battery(stats, body_battery)

    stress_val = stress.get("avgStressLevel") or stress.get("overallStressLevel")
    max_stress = stress.get("maxStressLevel")
    if stress_val:
        stress_str = f"Avg {stress_val}"
        if max_stress:
            stress_str += f", Max {max_stress}"
    else:
        stress_str = "No data"

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

    _, bb_peak, _ = body_battery_levels(stats, body_battery)

    return {
        "date": cdate,
        "resting_hr": stats.get("restingHeartRate"),
        "hrv": hrv_val,
        "body_battery_peak": bb_peak,
        "steps": stats.get("totalSteps"),
        "stress_avg": stress.get("avgStressLevel") or stress.get("overallStressLevel"),
    }


def day_values(cdate: str, data: dict) -> dict:
    """A day's vitals as plain values for --json: numbers unformatted, None for no data.

    HRV is given as Garmin gives it, last night's average and the seven-day
    average side by side, so neither can be mistaken for the other.
    """
    stats = data.get("stats") or {}
    hrv = data.get("hrv")
    summary = (hrv.get("hrvSummary") or {}) if isinstance(hrv, dict) else {}
    stress = data.get("stress") or {}
    low, high, latest = body_battery_levels(stats, data.get("body_battery") or [])
    return {
        "date": cdate,
        "resting_hr_bpm": stats.get("restingHeartRate"),
        "hrv": {
            "last_night_avg_ms": summary.get("lastNightAvg"),
            "weekly_avg_ms": summary.get("weeklyAvg"),
            "status": summary.get("status"),
        },
        "body_battery": {"lowest": low, "highest": high, "latest": latest},
        "stress": {
            "avg": stress.get("avgStressLevel") or stress.get("overallStressLevel"),
            "max": stress.get("maxStressLevel"),
        },
        "steps": stats.get("totalSteps"),
        "calories_kcal": stats.get("totalKilocalories"),
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
                cells.append(f"{v / 1000:.1f}k")
            else:
                cells.append(str(v))

        # Average
        numeric = [v for v in values if v is not None]
        if numeric:
            avg = sum(numeric) / len(numeric)
            avg_str = f"{avg / 1000:.1f}k" if fmt == "k" else str(round(avg))
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
    parser.add_argument("--json", action="store_true", help="print the figures as JSON, unformatted")
    args = parser.parse_args()

    try:
        config = load_config()
        client = get_client(config)
    except GarminConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.command == "week":
            today = date.today()
            dates = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
            if args.json:
                days = fetch_day_summaries(client, dates, today, summarise=day_values)
                print(json.dumps({"days": days}, indent=2))
            else:
                print(format_weekly_vitals(fetch_day_summaries(client, dates, today)))
        else:
            cdate = resolve_date(args.command)
            data = fetch_day_data(client, cdate)
            if args.json:
                print(json.dumps(day_values(cdate, data), indent=2))
                return
            print(
                format_daily_vitals(
                    cdate=cdate,
                    stats=data["stats"],
                    hrv=data["hrv"],
                    body_battery=data["body_battery"],
                    stress=data["stress"],
                )
            )
    except GarminFetchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
