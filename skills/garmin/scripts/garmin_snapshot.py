#!/usr/bin/env python3
"""
Garmin daily snapshot - pulls all data for a day and writes a markdown file.

Commands:
    python garmin_snapshot.py --output-dir /path/to/dir                # Today
    python garmin_snapshot.py --output-dir /path/to/dir 2026-02-22     # Specific date
    python garmin_snapshot.py --output-dir /path/to/dir yesterday      # Yesterday

Output: <output-dir>/YYYY-MM-DD.md
"""

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from garmin_client import get_client, load_config, GarminConfigError
from garmin_health import fetch_day_data, format_daily_vitals
from garmin_sleep import format_sleep_data, fetch_sleep
from garmin_activities import (
    format_activities,
    format_training_status,
    fetch_activities,
    fetch_training,
)


def generate_daily_markdown(
    cdate: str,
    health_data: dict,
    sleep_data: dict | None,
    activities: list[dict],
    training_status: dict | None,
    training_readiness: dict | None,
) -> str:
    """Generate a complete daily markdown snapshot.

    Args:
        cdate: Date string YYYY-MM-DD.
        health_data: Dict from fetch_day_data() with stats, hrv, body_battery, stress.
        sleep_data: Response from get_sleep_data() or None.
        activities: List of activity dicts for this date.
        training_status: Response from get_training_status() or None.
        training_readiness: Response from get_training_readiness() or None.

    Returns:
        Complete markdown string for the daily snapshot file.
    """
    sections = [f"# Garmin Daily: {cdate}", ""]

    # Vitals
    vitals = format_daily_vitals(
        cdate=cdate,
        stats=health_data.get("stats", {}),
        hrv=health_data.get("hrv"),
        body_battery=health_data.get("body_battery", []),
        stress=health_data.get("stress", {}),
    )
    sections.append(vitals)
    sections.append("")

    # Sleep
    sleep = format_sleep_data(cdate, sleep_data)
    sections.append(sleep)
    sections.append("")

    # Activities
    acts = format_activities(activities)
    sections.append(acts)
    sections.append("")

    # Training status
    training = format_training_status(training_status, training_readiness)
    sections.append(training)
    sections.append("")

    return "\n".join(sections)


def write_snapshot(cdate: str, markdown: str, output_dir: str) -> str:
    """Write a daily snapshot markdown file.

    Args:
        cdate: Date string YYYY-MM-DD.
        markdown: Complete markdown content.
        output_dir: Directory to write the file to.

    Returns:
        Absolute path of the written file.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    file_path = out_path / f"{cdate}.md"
    file_path.write_text(markdown)
    return str(file_path)


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
    parser = argparse.ArgumentParser(description="Garmin daily snapshot")
    parser.add_argument(
        "date",
        nargs="?",
        default="today",
        help="'today', 'yesterday', or YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write the snapshot markdown file to",
    )
    args = parser.parse_args()

    try:
        config = load_config()
        client = get_client(config)
    except GarminConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    cdate = resolve_date(args.date)
    print(f"Fetching Garmin data for {cdate}...")

    # Fetch all data
    health_data = fetch_day_data(client, cdate)
    sleep_data = fetch_sleep(client, cdate)
    activities_data = fetch_activities(client, days=1)
    # Filter activities to just this date
    activities = [
        a for a in activities_data
        if a.get("startTimeLocal", "").startswith(cdate)
    ]
    training_status, training_readiness = fetch_training(client, cdate)

    # Generate and write
    markdown = generate_daily_markdown(
        cdate=cdate,
        health_data=health_data,
        sleep_data=sleep_data,
        activities=activities,
        training_status=training_status,
        training_readiness=training_readiness,
    )

    file_path = write_snapshot(cdate, markdown, output_dir=args.output_dir)
    print(f"Snapshot written to: {file_path}")


if __name__ == "__main__":
    main()
