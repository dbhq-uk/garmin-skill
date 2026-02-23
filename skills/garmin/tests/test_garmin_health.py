"""Tests for garmin_health.py - daily vitals formatting."""

import pytest
from unittest.mock import MagicMock
from datetime import date

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_health import format_daily_vitals, format_weekly_vitals


# Realistic mock data matching Garmin API response shapes
MOCK_STATS = {
    "totalSteps": 8432,
    "totalKilocalories": 2180,
    "restingHeartRate": 58,
    "minHeartRate": 48,
    "maxHeartRate": 178,
}

MOCK_HRV = {
    "hrvSummary": {
        "weeklyAvg": 42,
        "lastNight": 45,
        "lastNightAvg": 43,
        "status": "BALANCED",
    }
}

MOCK_BODY_BATTERY = [
    {"charged": 75, "drained": 53, "startTimestampGMT": "2026-02-22T00:00:00.0"},
]

MOCK_STRESS = {
    "overallStressLevel": 34,
    "restStressDuration": 28800,
    "activityStressDuration": 14400,
    "highStressDuration": 3600,
}


class TestFormatDailyVitals:
    """Test formatting of daily health data into readable output."""

    def test_formats_complete_data(self):
        result = format_daily_vitals(
            cdate="2026-02-22",
            stats=MOCK_STATS,
            hrv=MOCK_HRV,
            body_battery=MOCK_BODY_BATTERY,
            stress=MOCK_STRESS,
        )
        assert "Resting HR" in result
        assert "58 bpm" in result
        assert "HRV" in result
        assert "Steps" in result
        assert "8,432" in result
        assert "Body Battery" in result
        assert "Stress" in result

    def test_handles_missing_hrv(self):
        result = format_daily_vitals(
            cdate="2026-02-22",
            stats=MOCK_STATS,
            hrv=None,
            body_battery=MOCK_BODY_BATTERY,
            stress=MOCK_STRESS,
        )
        assert "HRV" in result
        assert "No data" in result

    def test_handles_empty_body_battery(self):
        result = format_daily_vitals(
            cdate="2026-02-22",
            stats=MOCK_STATS,
            hrv=MOCK_HRV,
            body_battery=[],
            stress=MOCK_STRESS,
        )
        assert "Body Battery" in result
        assert "No data" in result


class TestFormatWeeklyVitals:
    """Test formatting of 7-day vitals table."""

    def test_formats_seven_days(self):
        days = []
        for i in range(7):
            days.append({
                "date": f"2026-02-{16+i:02d}",
                "resting_hr": 56 + i,
                "hrv": 40 + i,
                "body_battery_peak": 70 + i,
                "steps": 7000 + (i * 500),
                "stress_avg": 30 + i,
            })
        result = format_weekly_vitals(days)
        assert "Mon" in result or "Tue" in result  # Day headers present
        assert "Avg" in result  # Average column present
        assert "Resting HR" in result

    def test_handles_partial_week(self):
        """If fewer than 7 days, should still format what's available."""
        days = [{
            "date": "2026-02-22",
            "resting_hr": 58,
            "hrv": 42,
            "body_battery_peak": 75,
            "steps": 8432,
            "stress_avg": 34,
        }]
        result = format_weekly_vitals(days)
        assert "58" in result
