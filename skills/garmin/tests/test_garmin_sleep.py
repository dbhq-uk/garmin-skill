"""Tests for garmin_sleep.py - sleep data formatting."""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_sleep import format_sleep_data


MOCK_SLEEP = {
    "dailySleepDTO": {
        "sleepScores": {
            "overall": {"value": 82},
        },
        "sleepTimeSeconds": 26640,  # 7h 24m
        "deepSleepSeconds": 4320,   # 1h 12m
        "lightSleepSeconds": 13680, # 3h 48m
        "remSleepSeconds": 7560,    # 2h 06m
        "awakeSleepSeconds": 1080,  # 18m
        "sleepStartTimestampGMT": 1740182400000,
        "sleepEndTimestampGMT": 1740209040000,
    }
}


class TestFormatSleepData:
    """Test formatting of sleep data into readable output."""

    def test_formats_complete_sleep_data(self):
        result = format_sleep_data("2026-02-22", MOCK_SLEEP)
        assert "Sleep" in result
        assert "82" in result  # score
        assert "7h 24m" in result  # duration
        assert "1h 12m" in result  # deep
        assert "3h 48m" in result  # light
        assert "2h 06m" in result  # REM
        assert "18m" in result      # awake

    def test_handles_missing_sleep_data(self):
        result = format_sleep_data("2026-02-22", {})
        assert "No sleep data" in result

    def test_handles_none_sleep_data(self):
        result = format_sleep_data("2026-02-22", None)
        assert "No sleep data" in result

    def test_handles_zero_duration(self):
        """Edge case: sleep tracked but 0 seconds."""
        data = {
            "dailySleepDTO": {
                "sleepScores": {"overall": {"value": 0}},
                "sleepTimeSeconds": 0,
                "deepSleepSeconds": 0,
                "lightSleepSeconds": 0,
                "remSleepSeconds": 0,
                "awakeSleepSeconds": 0,
            }
        }
        result = format_sleep_data("2026-02-22", data)
        assert "0" in result
