"""Tests for garmin_activities.py - activities and training formatting."""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_activities import format_activities, format_training_status


MOCK_ACTIVITIES = [
    {
        "activityName": "HYROX Training",
        "activityType": {"typeKey": "strength_training"},
        "startTimeLocal": "2026-02-22 07:30:00",
        "duration": 3480.0,  # 58 min in seconds
        "distance": None,
        "averageHR": 152.0,
        "maxHR": 178.0,
        "calories": 620.0,
        "aerobicTrainingEffect": 3.8,
        "anaerobicTrainingEffect": 2.1,
    },
    {
        "activityName": "Morning Run",
        "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-02-21 06:45:00",
        "duration": 2100.0,  # 35 min
        "distance": 5200.0,  # metres
        "averageHR": 145.0,
        "maxHR": 168.0,
        "calories": 380.0,
        "aerobicTrainingEffect": 3.2,
        "anaerobicTrainingEffect": 1.5,
    },
]

MOCK_TRAINING_STATUS = {
    "mostRecentVO2Max": 44.0,
    "mostRecentVO2MaxRunning": 44.0,
    "trainingStatusFeedbackPhrase": "PRODUCTIVE",
    "weeklyTrainingLoad": 412,
}

MOCK_TRAINING_READINESS = {
    "score": 62,
    "level": "MODERATE",
}


class TestFormatActivities:
    """Test formatting of activity list."""

    def test_formats_multiple_activities(self):
        result = format_activities(MOCK_ACTIVITIES)
        assert "HYROX Training" in result
        assert "Morning Run" in result
        assert "58 min" in result
        assert "152 bpm" in result
        assert "5.2 km" in result

    def test_handles_empty_list(self):
        result = format_activities([])
        assert "No activities" in result

    def test_handles_missing_distance(self):
        """Activities without distance (e.g. strength) should not show distance."""
        result = format_activities([MOCK_ACTIVITIES[0]])
        assert "HYROX Training" in result
        # Should not crash on None distance

    def test_formats_training_effect(self):
        result = format_activities(MOCK_ACTIVITIES)
        assert "3.8" in result  # aerobic TE
        assert "2.1" in result  # anaerobic TE


class TestFormatTrainingStatus:
    """Test formatting of training status metrics."""

    def test_formats_complete_training_data(self):
        result = format_training_status(MOCK_TRAINING_STATUS, MOCK_TRAINING_READINESS)
        assert "VO2 Max" in result
        assert "44" in result
        assert "Training Load" in result
        assert "412" in result
        assert "Training Readiness" in result
        assert "62" in result
        assert "Productive" in result or "PRODUCTIVE" in result

    def test_handles_missing_readiness(self):
        result = format_training_status(MOCK_TRAINING_STATUS, None)
        assert "VO2 Max" in result
        assert "Training Readiness" in result
        assert "No data" in result

    def test_handles_missing_training_status(self):
        result = format_training_status(None, MOCK_TRAINING_READINESS)
        assert "No data" in result or "VO2 Max" in result
