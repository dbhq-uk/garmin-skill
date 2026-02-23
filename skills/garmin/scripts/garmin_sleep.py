#!/usr/bin/env python3
"""
Garmin sleep data query.

Commands:
    python garmin_sleep.py                 # Last night's sleep
    python garmin_sleep.py 2026-02-22      # Sleep for specific date
    python garmin_sleep.py yesterday       # Yesterday's sleep
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from garmin_client import get_client, load_config, GarminConfigError


def _format_duration(seconds: int | None) -> str:
    """Convert seconds to human-readable duration like '7h 24m'."""
    if seconds is None or seconds < 0:
        return "No data"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def format_sleep_data(cdate: str, sleep_data: dict | None) -> str:
    """Format sleep data as a readable table.

    Args:
        cdate: Date string YYYY-MM-DD.
        sleep_data: Response from client.get_sleep_data() or None.

    Returns:
        Formatted string with sleep table.
    """
    if not sleep_data or "dailySleepDTO" not in sleep_data:
        return f"## Sleep \u2014 {cdate}\n\nNo sleep data recorded for this date."

    dto = sleep_data["dailySleepDTO"]
    scores = dto.get("sleepScores", {})
    overall_score = scores.get("overall", {}).get("value", "No data")

    total = dto.get("sleepTimeSeconds")
    deep = dto.get("deepSleepSeconds")
    light = dto.get("lightSleepSeconds")
    rem = dto.get("remSleepSeconds")
    awake = dto.get("awakeSleepSeconds")

    lines = [
        f"## Sleep \u2014 {cdate}",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Score | {overall_score} |",
        f"| Duration | {_format_duration(total)} |",
        f"| Deep | {_format_duration(deep)} |",
        f"| Light | {_format_duration(light)} |",
        f"| REM | {_format_duration(rem)} |",
        f"| Awake | {_format_duration(awake)} |",
    ]
    return "\n".join(lines)


def fetch_sleep(client, cdate: str) -> dict | None:
    """Fetch sleep data from Garmin API."""
    try:
        return client.get_sleep_data(cdate)
    except Exception:
        return None


def resolve_date(date_arg: str) -> str:
    """Convert date argument to YYYY-MM-DD string."""
    if not date_arg or date_arg == "today":
        return date.today().isoformat()
    elif date_arg == "yesterday":
        return (date.today() - timedelta(days=1)).isoformat()
    else:
        date.fromisoformat(date_arg)
        return date_arg


def main():
    parser = argparse.ArgumentParser(description="Garmin sleep data")
    parser.add_argument(
        "date",
        nargs="?",
        default="today",
        help="'today', 'yesterday', or YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args()

    try:
        config = load_config()
        client = get_client(config)
    except GarminConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    cdate = resolve_date(args.date)
    sleep_data = fetch_sleep(client, cdate)
    print(format_sleep_data(cdate, sleep_data))


if __name__ == "__main__":
    main()
