#!/usr/bin/env python3
"""
Garmin activities and training status query.

Commands:
    python garmin_activities.py 7           # Activities from last 7 days
    python garmin_activities.py 30          # Activities from last 30 days
    python garmin_activities.py training    # Training status (VO2, load, readiness)
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from garmin_client import get_client, load_config, GarminConfigError


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


def _format_distance(metres: float | None) -> str | None:
    """Convert metres to km string, or None if no distance."""
    if metres is None or metres <= 0:
        return None
    km = metres / 1000
    return f"{km:.1f} km"


def format_activities(activities: list[dict]) -> str:
    """Format a list of activities into readable output.

    Args:
        activities: List of activity dicts from Garmin API.

    Returns:
        Formatted string listing activities.
    """
    if not activities:
        return "No activities found for this period."

    lines = ["## Activities", ""]
    for act in activities:
        name = act.get("activityName", "Unknown Activity")
        duration = _format_duration_mins(act.get("duration"))
        distance = _format_distance(act.get("distance"))
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
            te_str = f"Training Effect: Aerobic {aero_te}"
            if anaero_te is not None:
                te_str += f" / Anaerobic {anaero_te}"
            details.append(te_str)

        for d in details:
            lines.append(f"- {d}")
        lines.append("")

    return "\n".join(lines)


def format_training_status(
    training_status: dict | None,
    training_readiness: dict | None,
) -> str:
    """Format training status metrics as a table.

    Args:
        training_status: Response from get_training_status().
        training_readiness: Response from get_training_readiness().

    Returns:
        Formatted string with training metrics table.
    """
    vo2 = None
    load = None
    status = None
    readiness = None

    if training_status:
        vo2 = training_status.get("mostRecentVO2Max") or training_status.get("mostRecentVO2MaxRunning")
        load = training_status.get("weeklyTrainingLoad")
        status_raw = training_status.get("trainingStatusFeedbackPhrase")
        status = status_raw.replace("_", " ").title() if status_raw else None

    if training_readiness:
        readiness = training_readiness.get("score")

    lines = [
        "## Training Status",
        "| Metric | Value |",
        "|--------|-------|",
        f"| VO2 Max | {vo2 if vo2 else 'No data'} |",
        f"| Training Load | {load if load else 'No data'} |",
        f"| Training Readiness | {readiness if readiness else 'No data'} |",
        f"| Training Status | {status if status else 'No data'} |",
    ]
    return "\n".join(lines)


def fetch_activities(client, days: int = 7) -> list[dict]:
    """Fetch recent activities from Garmin API."""
    try:
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=days)).isoformat()
        return client.get_activities_by_date(start, end) or []
    except Exception:
        return []


def fetch_training(client, cdate: str) -> tuple[dict | None, dict | None]:
    """Fetch training status and readiness from Garmin API."""
    status = None
    readiness = None
    try:
        status = client.get_training_status(cdate)
    except Exception:
        pass
    try:
        readiness = client.get_training_readiness(cdate)
    except Exception:
        pass
    return status, readiness


def main():
    parser = argparse.ArgumentParser(description="Garmin activities and training")
    parser.add_argument(
        "command",
        help="Number of days to look back, or 'training' for training status",
    )
    args = parser.parse_args()

    try:
        config = load_config()
        client = get_client(config)
    except GarminConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command == "training":
        cdate = date.today().isoformat()
        status, readiness = fetch_training(client, cdate)
        print(format_training_status(status, readiness))
    else:
        try:
            days = int(args.command)
        except ValueError:
            print(f"Error: expected a number of days or 'training', got '{args.command}'", file=sys.stderr)
            sys.exit(1)
        activities = fetch_activities(client, days)
        print(format_activities(activities))


if __name__ == "__main__":
    main()
