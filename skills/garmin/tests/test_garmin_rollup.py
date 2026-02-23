"""Tests for garmin_rollup.py - weekly rollup markdown generation."""

import pytest
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_rollup import (
    generate_weekly_markdown,
    get_week_dates,
    find_highlights,
    write_rollup,
)


def _make_day_summary(cdate, rhr=58, hrv=42, bb=75, steps=8000, stress=34):
    return {
        "date": cdate,
        "resting_hr": rhr,
        "hrv": hrv,
        "body_battery_peak": bb,
        "steps": steps,
        "stress_avg": stress,
    }


MOCK_WEEK = [
    _make_day_summary("2026-02-16", rhr=58, hrv=42, bb=75, steps=8432, stress=34),
    _make_day_summary("2026-02-17", rhr=56, hrv=45, bb=80, steps=10100, stress=30),
    _make_day_summary("2026-02-18", rhr=59, hrv=38, bb=68, steps=6200, stress=40),
    _make_day_summary("2026-02-19", rhr=57, hrv=44, bb=78, steps=9300, stress=32),
    _make_day_summary("2026-02-20", rhr=55, hrv=48, bb=82, steps=11000, stress=28),
    _make_day_summary("2026-02-21", rhr=58, hrv=41, bb=71, steps=7800, stress=36),
    _make_day_summary("2026-02-22", rhr=56, hrv=46, bb=84, steps=5100, stress=31),
]

MOCK_ACTIVITIES = [
    {
        "activityName": "HYROX Training",
        "startTimeLocal": "2026-02-16 07:30:00",
        "duration": 3480.0,
        "distance": None,
        "aerobicTrainingEffect": 3.8,
    },
    {
        "activityName": "Running",
        "startTimeLocal": "2026-02-18 06:45:00",
        "duration": 2100.0,
        "distance": 5200.0,
        "aerobicTrainingEffect": 3.2,
    },
]


class TestGetWeekDates:
    """Test ISO week date calculation."""

    def test_returns_seven_dates(self):
        dates = get_week_dates(2026, 8)
        assert len(dates) == 7

    def test_starts_on_monday(self):
        dates = get_week_dates(2026, 8)
        first = date.fromisoformat(dates[0])
        assert first.weekday() == 0  # Monday

    def test_ends_on_sunday(self):
        dates = get_week_dates(2026, 8)
        last = date.fromisoformat(dates[-1])
        assert last.weekday() == 6  # Sunday


class TestFindHighlights:
    """Test highlight extraction from weekly data."""

    def test_finds_best_body_battery(self):
        highlights = find_highlights(MOCK_WEEK, MOCK_ACTIVITIES)
        # Best body battery peak is Sunday (84)
        assert any("84" in h for h in highlights)

    def test_finds_highest_hrv(self):
        highlights = find_highlights(MOCK_WEEK, MOCK_ACTIVITIES)
        # Highest HRV is Friday (48)
        assert any("48" in h for h in highlights)

    def test_counts_activities(self):
        highlights = find_highlights(MOCK_WEEK, MOCK_ACTIVITIES)
        assert any("2" in h for h in highlights)  # 2 sessions


class TestGenerateWeeklyMarkdown:
    """Test full weekly markdown generation."""

    def test_contains_all_sections(self):
        md = generate_weekly_markdown(
            year=2026,
            week=8,
            day_summaries=MOCK_WEEK,
            activities=MOCK_ACTIVITIES,
            training_status={"mostRecentVO2Max": 44.0, "weeklyTrainingLoad": 412},
            training_readiness={"score": 62},
        )
        assert "# Garmin Weekly: 2026-W08" in md
        assert "## Trends" in md
        assert "## Activities" in md
        assert "## Highlights" in md
        assert "## Notes" in md

    def test_contains_data_values(self):
        md = generate_weekly_markdown(
            year=2026,
            week=8,
            day_summaries=MOCK_WEEK,
            activities=MOCK_ACTIVITIES,
            training_status={"mostRecentVO2Max": 44.0, "weeklyTrainingLoad": 412},
            training_readiness={"score": 62},
        )
        assert "HYROX" in md
        assert "Running" in md


class TestWriteRollup:
    """Test writing rollup to file."""

    def test_writes_to_correct_path(self, tmp_path):
        md = "# Test rollup"
        path = write_rollup(2026, 8, md, output_dir=str(tmp_path))
        assert Path(path).exists()
        assert "2026-W08.md" in path

    def test_creates_directory(self, tmp_path):
        target = tmp_path / "weekly"
        write_rollup(2026, 8, "# Test", output_dir=str(target))
        assert (target / "2026-W08.md").exists()
