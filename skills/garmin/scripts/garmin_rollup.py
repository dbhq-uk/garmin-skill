#!/usr/bin/env python3
"""
Garmin weekly rollup - aggregates daily data into a weekly summary.

Commands:
    python garmin_rollup.py --output-dir /path/to/dir              # Current week
    python garmin_rollup.py --output-dir /path/to/dir 2026-W08     # Specific ISO week
    python garmin_rollup.py --output-dir /path/to/dir last         # Previous week

Output: <output-dir>/YYYY-WXX.md
"""

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from garmin_client import get_client, load_config, GarminConfigError
from garmin_health import fetch_day_data, extract_day_summary, format_weekly_vitals
from garmin_activities import (
    format_training_status,
    fetch_training,
    _format_duration_mins,
    _format_distance,
)


def get_week_dates(year: int, week: int) -> list[str]:
    """Get all 7 dates (Mon-Sun) for an ISO week.

    Args:
        year: ISO year.
        week: ISO week number.

    Returns:
        List of 7 date strings in YYYY-MM-DD format.
    """
    monday = date.fromisocalendar(year, week, 1)
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


def find_highlights(day_summaries: list[dict], activities: list[dict]) -> list[str]:
    """Extract notable highlights from the week's data.

    Args:
        day_summaries: List of daily summary dicts.
        activities: List of activity dicts for the week.

    Returns:
        List of highlight strings.
    """
    highlights = []

    # Best body battery
    bb_days = [(d["date"], d["body_battery_peak"]) for d in day_summaries if d.get("body_battery_peak")]
    if bb_days:
        best_bb = max(bb_days, key=lambda x: x[1])
        dt = date.fromisoformat(best_bb[0])
        highlights.append(f"**Best Body Battery:** {dt.strftime('%A')} ({best_bb[1]})")

    # Highest HRV
    hrv_days = [(d["date"], d["hrv"]) for d in day_summaries if d.get("hrv")]
    if hrv_days:
        best_hrv = max(hrv_days, key=lambda x: x[1])
        dt = date.fromisoformat(best_hrv[0])
        highlights.append(f"**Highest HRV:** {dt.strftime('%A')} ({best_hrv[1]})")

    # Activity count
    if activities:
        highlights.append(f"**Activities:** {len(activities)} sessions")

    return highlights


def _format_activity_summary(act: dict) -> str:
    """Format a single activity as a one-line summary for the weekly view."""
    name = act.get("activityName", "Unknown")
    duration = _format_duration_mins(act.get("duration"))
    start = act.get("startTimeLocal", "")
    date_part = start.split(" ")[0] if " " in start else start

    day_str = ""
    if date_part:
        try:
            dt = date.fromisoformat(date_part)
            day_str = dt.strftime("%a")
        except ValueError:
            pass

    line = f"- {day_str}: {name} \u2014 {duration}"
    distance = _format_distance(act.get("distance"))
    if distance:
        line += f", {distance}"
    te = act.get("aerobicTrainingEffect")
    if te:
        line += f", TE {te}"

    return line


def generate_weekly_markdown(
    year: int,
    week: int,
    day_summaries: list[dict],
    activities: list[dict],
    training_status: dict | None,
    training_readiness: dict | None,
) -> str:
    """Generate a complete weekly rollup markdown file.

    Args:
        year: ISO year.
        week: ISO week number.
        day_summaries: List of daily summary dicts (from extract_day_summary).
        activities: List of activity dicts for the week.
        training_status: Latest training status or None.
        training_readiness: Latest training readiness or None.

    Returns:
        Complete markdown string for the weekly rollup.
    """
    week_str = f"{year}-W{week:02d}"
    sections = [f"# Garmin Weekly: {week_str}", ""]

    # Trends table
    sections.append("## Trends")
    sections.append(format_weekly_vitals(day_summaries))
    sections.append("")

    # Activities summary
    if activities:
        sections.append(f"## Activities ({len(activities)} sessions)")
        for act in activities:
            sections.append(_format_activity_summary(act))
    else:
        sections.append("## Activities")
        sections.append("No activities recorded this week.")
    sections.append("")

    # Highlights
    highlights = find_highlights(day_summaries, activities)

    # Add training metrics to highlights
    if training_status:
        vo2 = training_status.get("mostRecentVO2Max")
        load = training_status.get("weeklyTrainingLoad")
        if load:
            highlights.append(f"**Training load:** {load}")
        if vo2:
            highlights.append(f"**VO2 Max:** {vo2}")

    sections.append("## Highlights")
    for h in highlights:
        sections.append(f"- {h}")
    sections.append("")

    # Notes placeholder
    sections.append("## Notes")
    sections.append("[Auto-generated \u2014 edit to add context during weekly review]")
    sections.append("")

    return "\n".join(sections)


def write_rollup(year: int, week: int, markdown: str, output_dir: str) -> str:
    """Write a weekly rollup markdown file.

    Args:
        year: ISO year.
        week: ISO week number.
        markdown: Complete markdown content.
        output_dir: Directory to write the file to.

    Returns:
        Absolute path of the written file.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    filename = f"{year}-W{week:02d}.md"
    file_path = out_path / filename
    file_path.write_text(markdown)
    return str(file_path)


def resolve_week(week_arg: str) -> tuple[int, int]:
    """Resolve a week argument to (year, week) tuple.

    Accepts: 'current', 'last', or 'YYYY-WXX'.
    """
    if not week_arg or week_arg == "current":
        today = date.today()
        iso = today.isocalendar()
        return iso.year, iso.week
    elif week_arg == "last":
        last_week = date.today() - timedelta(weeks=1)
        iso = last_week.isocalendar()
        return iso.year, iso.week
    else:
        match = re.match(r"(\d{4})-W(\d{1,2})", week_arg)
        if not match:
            raise ValueError(f"Invalid week format: {week_arg}. Use YYYY-WXX.")
        return int(match.group(1)), int(match.group(2))


def main():
    parser = argparse.ArgumentParser(description="Garmin weekly rollup")
    parser.add_argument(
        "week",
        nargs="?",
        default="current",
        help="'current', 'last', or YYYY-WXX (default: current)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write the rollup markdown file to",
    )
    args = parser.parse_args()

    try:
        config = load_config()
        client = get_client(config)
    except GarminConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    year, week = resolve_week(args.week)
    dates = get_week_dates(year, week)
    print(f"Generating rollup for {year}-W{week:02d} ({dates[0]} to {dates[-1]})...")

    # Fetch daily data for each day
    day_summaries = []
    for d in dates:
        data = fetch_day_data(client, d)
        day_summaries.append(extract_day_summary(d, data))

    # Fetch activities for the week
    try:
        activities = client.get_activities_by_date(dates[0], dates[-1]) or []
    except Exception:
        activities = []

    # Training status from most recent day
    training_status, training_readiness = fetch_training(client, dates[-1])

    # Generate and write
    markdown = generate_weekly_markdown(
        year=year,
        week=week,
        day_summaries=day_summaries,
        activities=activities,
        training_status=training_status,
        training_readiness=training_readiness,
    )

    file_path = write_rollup(year, week, markdown, output_dir=args.output_dir)
    print(f"Rollup written to: {file_path}")


if __name__ == "__main__":
    main()
