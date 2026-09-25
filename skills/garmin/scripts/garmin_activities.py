#!/usr/bin/env python3
"""
Garmin activities and training status query.

Commands:
    python garmin_activities.py 7           # Activities from last 7 days
    python garmin_activities.py 30          # Activities from last 30 days
    python garmin_activities.py training    # Training status (VO2, load, readiness)
    python garmin_activities.py 7 --json    # The same figures, unformatted, as JSON
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from garmin_client import GarminConfigError, GarminFetchError, fetch, get_client, load_config


def _format_duration_mins(seconds: float | None) -> str:
    """Convert seconds to 'Xh Ym' or 'Ym' format."""
    if not seconds:
        return "?"
    total_mins = int(seconds / 60)
    hours = total_mins // 60
    mins = total_mins % 60
    if hours > 0:
        return f"{hours}h {mins:02d} min"
    return f"{mins} min"


def _format_distance(metres: float | None, units: str = "imperial") -> str | None:
    """Convert metres to distance string.

    Args:
        metres: Distance in metres.
        units: 'imperial' for miles, 'metric' for km.
    """
    if metres is None or metres <= 0:
        return None
    if units == "metric":
        return f"{metres / 1000:.1f} km"
    return f"{metres / 1609.344:.1f} miles"


def format_activities(activities: list[dict], units: str = "imperial") -> str:
    """Format a list of activities into readable output.

    Args:
        activities: List of activity dicts from Garmin API.
        units: 'imperial' for miles, 'metric' for km.

    Returns:
        Formatted string listing activities.
    """
    if not activities:
        return "No activities found for this period."

    lines = ["## Activities", ""]
    for act in activities:
        name = act.get("activityName", "Unknown Activity")
        duration = _format_duration_mins(act.get("duration"))
        distance = _format_distance(act.get("distance"), units)
        avg_hr = act.get("averageHR")
        max_hr = act.get("maxHR")
        calories = act.get("calories")
        aero_te = act.get("aerobicTrainingEffect")
        anaero_te = act.get("anaerobicTrainingEffect")

        start_time = act.get("startTimeLocal", "")
        date_part = start_time.split(" ")[0] if " " in start_time else start_time

        # Title line
        title = f"### {name} ({duration})"
        if distance:
            title += f" \u2014 {distance}"
        lines.append(title)
        if date_part:
            lines.append(f"*{date_part}*")

        # Detail lines
        details = []
        if avg_hr:
            hr_str = f"Avg HR: {int(avg_hr)} bpm"
            if max_hr:
                hr_str += f" | Max HR: {int(max_hr)} bpm"
            details.append(hr_str)
        if calories:
            details.append(f"Calories: {int(calories)}")
        if aero_te is not None:
            te_str = f"Training Effect: Aerobic {round(aero_te, 1)}"
            if anaero_te is not None:
                te_str += f" / Anaerobic {round(anaero_te, 1)}"
            details.append(te_str)

        for d in details:
            lines.append(f"- {d}")
        lines.append("")

    return "\n".join(lines)


def activity_values(act: dict) -> dict:
    """One activity as plain values for --json: seconds, metres, and None where Garmin has nothing."""
    return {
        "name": act.get("activityName"),
        "type": (act.get("activityType") or {}).get("typeKey"),
        "start_local": act.get("startTimeLocal"),
        "duration_seconds": act.get("duration"),
        "distance_metres": act.get("distance"),
        "average_hr_bpm": act.get("averageHR"),
        "max_hr_bpm": act.get("maxHR"),
        "calories_kcal": act.get("calories"),
        "aerobic_training_effect": act.get("aerobicTrainingEffect"),
        "anaerobic_training_effect": act.get("anaerobicTrainingEffect"),
    }


def training_values(training_status: dict | None, training_readiness: dict | list | None) -> dict:
    """VO2 max, training load, readiness and status, as plain values. None where Garmin has nothing.

    The one place these are read out of Garmin's responses: the table and
    --json both come from here, so they cannot disagree.
    """
    vo2 = None
    load = None
    status = None
    readiness = None

    if training_status:
        # VO2 Max is nested: {generic: {vo2MaxValue: 40.0}, cycling: ...}
        vo2_data = training_status.get("mostRecentVO2Max") or training_status.get("mostRecentVO2MaxRunning")
        if isinstance(vo2_data, dict):
            generic = vo2_data.get("generic") or {}
            vo2 = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
        elif isinstance(vo2_data, (int, float)):
            vo2 = vo2_data
        load = training_status.get("weeklyTrainingLoad")
        status_raw = training_status.get("trainingStatusFeedbackPhrase")
        status = status_raw.replace("_", " ").title() if status_raw else None

    if training_readiness:
        # API may return a list of readiness entries or a single dict
        if isinstance(training_readiness, list) and training_readiness:
            readiness = training_readiness[0].get("score")
        elif isinstance(training_readiness, dict):
            readiness = training_readiness.get("score")

    return {"vo2_max": vo2, "training_load": load, "training_readiness": readiness, "training_status": status}


def format_training_status(
    training_status: dict | None,
    training_readiness: dict | list | None,
) -> str:
    """Format training status metrics as a table.

    Args:
        training_status: Response from get_training_status().
        training_readiness: Response from get_training_readiness().

    Returns:
        Formatted string with training metrics table.
    """
    values = training_values(training_status, training_readiness)
    lines = [
        "## Training Status",
        "| Metric | Value |",
        "|--------|-------|",
        f"| VO2 Max | {values['vo2_max'] or 'No data'} |",
        f"| Training Load | {values['training_load'] or 'No data'} |",
        f"| Training Readiness | {values['training_readiness'] or 'No data'} |",
        f"| Training Status | {values['training_status'] or 'No data'} |",
    ]
    return "\n".join(lines)


def fetch_activities(client, days: int = 7) -> list[dict]:
    """Fetch recent activities from Garmin API. Raises GarminFetchError on a failed call."""
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days)).isoformat()
    return fetch(client.get_activities_by_date, start, end) or []


def fetch_activities_on(client, cdate: str) -> list[dict]:
    """Fetch the activities that started on one date. Raises GarminFetchError on a failed call.

    Asks Garmin for that date alone, so the answer does not depend on today's
    date. A window counted back from today holds nothing for a date before
    yesterday, and a backfilled archive would then lose every activity.
    """
    activities = fetch(client.get_activities_by_date, cdate, cdate) or []
    return [a for a in activities if str(a.get("startTimeLocal") or "").startswith(cdate)]


def fetch_training(client, cdate: str) -> tuple[dict | None, dict | None]:
    """Fetch training status and readiness from Garmin API.

    Either can be None when Garmin has nothing. Raises GarminFetchError when a
    call failed.
    """
    status = fetch(client.get_training_status, cdate)
    readiness = fetch(client.get_training_readiness, cdate)
    return status, readiness


def main():
    parser = argparse.ArgumentParser(description="Garmin activities and training")
    parser.add_argument(
        "command",
        help="Number of days to look back, or 'training' for training status",
    )
    parser.add_argument("--json", action="store_true", help="print the figures as JSON, unformatted")
    args = parser.parse_args()

    try:
        config = load_config()
        client = get_client(config)
    except GarminConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    units = config.get("units", "imperial")

    try:
        if args.command == "training":
            cdate = date.today().isoformat()
            status, readiness = fetch_training(client, cdate)
            if args.json:
                print(json.dumps({"date": cdate, **training_values(status, readiness)}, indent=2))
            else:
                print(format_training_status(status, readiness))
        else:
            try:
                days = int(args.command)
            except ValueError:
                print(f"Error: expected a number of days or 'training', got '{args.command}'", file=sys.stderr)
                sys.exit(1)
            activities = fetch_activities(client, days)
            if args.json:
                print(json.dumps({"activities": [activity_values(a) for a in activities]}, indent=2))
            else:
                print(format_activities(activities, units))
    except GarminFetchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
