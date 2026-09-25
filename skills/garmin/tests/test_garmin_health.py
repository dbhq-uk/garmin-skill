"""Tests for garmin_health.py - daily vitals formatting."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_health import body_battery_levels, extract_day_summary, format_daily_vitals, format_weekly_vitals

# Realistic mock data matching Garmin API response shapes
MOCK_STATS = {
    "totalSteps": 8432,
    "totalKilocalories": 2180,
    "restingHeartRate": 58,
    "minHeartRate": 48,
    "maxHeartRate": 178,
    "bodyBatteryLowestValue": 18,
    "bodyBatteryHighestValue": 95,
    "bodyBatteryMostRecentValue": 62,
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
        stats_without_levels = {k: v for k, v in MOCK_STATS.items() if not k.startswith("bodyBattery")}
        result = format_daily_vitals(
            cdate="2026-02-22",
            stats=stats_without_levels,
            hrv=MOCK_HRV,
            body_battery=[],
            stress=MOCK_STRESS,
        )
        assert "| Body Battery | No data |" in result


class TestFormatWeeklyVitals:
    """Test formatting of 7-day vitals table."""

    def test_formats_seven_days(self):
        days = []
        for i in range(7):
            days.append(
                {
                    "date": f"2026-02-{16 + i:02d}",
                    "resting_hr": 56 + i,
                    "hrv": 40 + i,
                    "body_battery_peak": 70 + i,
                    "steps": 7000 + (i * 500),
                    "stress_avg": 30 + i,
                }
            )
        result = format_weekly_vitals(days)
        assert "Mon" in result or "Tue" in result  # Day headers present
        assert "Avg" in result  # Average column present
        assert "Resting HR" in result

    def test_handles_partial_week(self):
        """If fewer than 7 days, should still format what's available."""
        days = [
            {
                "date": "2026-02-22",
                "resting_hr": 58,
                "hrv": 42,
                "body_battery_peak": 75,
                "steps": 8432,
                "stress_avg": 34,
            }
        ]
        result = format_weekly_vitals(days)
        assert "58" in result


# garminconnect's BodyBatteryEntry: "charged" and "drained" are what the day
# gained and lost. Amounts, not levels.
DELTAS_ONLY = [{"charged": 40, "drained": 70}]

LEVEL_DESCRIPTORS = [
    {"bodyBatteryValueDescriptorIndex": 0, "bodyBatteryValueDescriptorKey": "timestamp"},
    {"bodyBatteryValueDescriptorIndex": 1, "bodyBatteryValueDescriptorKey": "bodyBatteryLevel"},
]


def _body_battery_row(result: str) -> str:
    return next(line for line in result.splitlines() if line.startswith("| Body Battery"))


class TestBodyBattery:
    """Body Battery is a level from 0 to 100. Never charged minus drained."""

    def test_deltas_never_become_a_negative_level(self):
        result = format_daily_vitals("2026-09-01", {}, None, DELTAS_ONLY, {})
        row = _body_battery_row(result)
        assert "-30" not in row
        assert "40" not in row
        assert row == "| Body Battery | No data |"

    def test_row_shows_the_range_and_latest_level(self):
        result = format_daily_vitals("2026-09-01", MOCK_STATS, None, DELTAS_ONLY, {})
        assert _body_battery_row(result) == "| Body Battery | 18-95, latest 62 |"

    def test_levels_come_from_the_summary_not_charged(self):
        assert body_battery_levels(MOCK_STATS, DELTAS_ONLY) == (18, 95, 62)

    def test_falls_back_to_the_readings_when_the_summary_has_none(self):
        readings = [
            {
                "charged": 40,
                "drained": 70,
                "bodyBatteryValueDescriptorDTOList": LEVEL_DESCRIPTORS,
                "bodyBatteryValuesArray": [[2000, 60], [1000, 20], [3000, 45]],
            }
        ]
        assert body_battery_levels({}, readings) == (20, 60, 45)

    def test_level_is_found_by_its_descriptor_not_its_position(self):
        readings = [
            {
                "bodyBatteryValueDescriptorDTOList": [
                    {"bodyBatteryValueDescriptorIndex": 0, "bodyBatteryValueDescriptorKey": "timestamp"},
                    {"bodyBatteryValueDescriptorIndex": 1, "bodyBatteryValueDescriptorKey": "bodyBatteryStatus"},
                    {"bodyBatteryValueDescriptorIndex": 2, "bodyBatteryValueDescriptorKey": "bodyBatteryLevel"},
                    {"bodyBatteryValueDescriptorIndex": 3, "bodyBatteryValueDescriptorKey": "bodyBatteryVersion"},
                ],
                "bodyBatteryValuesArray": [[1000, "MEASURED", 50, 2.0], [2000, "MEASURED", 35, 2.0]],
            }
        ]
        assert body_battery_levels({}, readings) == (35, 50, 35)

    def test_readings_without_a_descriptor_are_not_guessed_at(self):
        readings = [{"bodyBatteryValuesArray": [[1000, 60]]}]
        assert body_battery_levels({}, readings) == (None, None, None)

    def test_weekly_peak_is_the_highest_level_not_charged(self):
        data = {"stats": MOCK_STATS, "hrv": None, "body_battery": DELTAS_ONLY, "stress": {}}
        assert extract_day_summary("2026-09-01", data)["body_battery_peak"] == 95

    def test_no_levels_means_no_weekly_peak(self):
        data = {"stats": {}, "hrv": None, "body_battery": DELTAS_ONLY, "stress": {}}
        assert extract_day_summary("2026-09-01", data)["body_battery_peak"] is None
