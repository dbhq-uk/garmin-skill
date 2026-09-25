"""Tests for garmin_snapshot.py - daily markdown file generation."""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_snapshot
from garmin_snapshot import generate_daily_markdown, write_snapshot

# Reuse mock data structures
MOCK_HEALTH = {
    "stats": {
        "totalSteps": 8432,
        "totalKilocalories": 2180,
        "restingHeartRate": 58,
        "bodyBatteryLowestValue": 22,
        "bodyBatteryHighestValue": 91,
        "bodyBatteryMostRecentValue": 64,
    },
    "hrv": {
        "hrvSummary": {"lastNightAvg": 42, "weeklyAvg": 42, "status": "BALANCED"},
    },
    "body_battery": [{"charged": 75, "drained": 53}],
    "stress": {"overallStressLevel": 34},
}

MOCK_SLEEP = {
    "dailySleepDTO": {
        "sleepScores": {"overall": {"value": 82}},
        "sleepTimeSeconds": 26640,
        "deepSleepSeconds": 4320,
        "lightSleepSeconds": 13680,
        "remSleepSeconds": 7560,
        "awakeSleepSeconds": 1080,
    }
}

MOCK_ACTIVITIES = [
    {
        "activityName": "HYROX Training",
        "activityType": {"typeKey": "strength_training"},
        "startTimeLocal": "2026-02-22 07:30:00",
        "duration": 3480.0,
        "distance": None,
        "averageHR": 152.0,
        "maxHR": 178.0,
        "calories": 620.0,
        "aerobicTrainingEffect": 3.8,
        "anaerobicTrainingEffect": 2.1,
    },
]

MOCK_TRAINING_STATUS = {
    "mostRecentVO2Max": 44.0,
    "trainingStatusFeedbackPhrase": "PRODUCTIVE",
    "weeklyTrainingLoad": 412,
}

MOCK_TRAINING_READINESS = {"score": 62, "level": "MODERATE"}


class TestGenerateDailyMarkdown:
    """Test full daily markdown generation."""

    def test_contains_all_sections(self):
        md = generate_daily_markdown(
            cdate="2026-02-22",
            health_data=MOCK_HEALTH,
            sleep_data=MOCK_SLEEP,
            activities=MOCK_ACTIVITIES,
            training_status=MOCK_TRAINING_STATUS,
            training_readiness=MOCK_TRAINING_READINESS,
        )
        assert "# Garmin Daily: 2026-02-22" in md
        assert "## Vitals" in md
        assert "## Sleep" in md
        assert "## Activities" in md
        assert "## Training Status" in md

    def test_contains_actual_data(self):
        md = generate_daily_markdown(
            cdate="2026-02-22",
            health_data=MOCK_HEALTH,
            sleep_data=MOCK_SLEEP,
            activities=MOCK_ACTIVITIES,
            training_status=MOCK_TRAINING_STATUS,
            training_readiness=MOCK_TRAINING_READINESS,
        )
        assert "58 bpm" in md  # resting HR
        assert "| Body Battery | 22-91, latest 64 |" in md
        assert "82" in md  # sleep score
        assert "HYROX" in md  # activity name
        assert "44" in md  # VO2 max

    def test_handles_no_activities(self):
        md = generate_daily_markdown(
            cdate="2026-02-22",
            health_data=MOCK_HEALTH,
            sleep_data=MOCK_SLEEP,
            activities=[],
            training_status=MOCK_TRAINING_STATUS,
            training_readiness=MOCK_TRAINING_READINESS,
        )
        assert "No activities" in md

    def test_handles_no_sleep(self):
        md = generate_daily_markdown(
            cdate="2026-02-22",
            health_data=MOCK_HEALTH,
            sleep_data=None,
            activities=MOCK_ACTIVITIES,
            training_status=MOCK_TRAINING_STATUS,
            training_readiness=MOCK_TRAINING_READINESS,
        )
        assert "No sleep data" in md


class TestWriteSnapshot:
    """Test writing snapshot to file."""

    def test_writes_file_to_correct_path(self, tmp_path):
        md = "# Garmin Daily: 2026-02-22\n\nTest content"
        output_path = write_snapshot("2026-02-22", md, output_dir=str(tmp_path))
        assert Path(output_path).exists()
        assert output_path.endswith("2026-02-22.md")
        assert Path(output_path).read_text() == md

    def test_creates_directory_if_missing(self, tmp_path):
        target = tmp_path / "garmin"
        md = "# Test"
        write_snapshot("2026-02-22", md, output_dir=str(target))
        assert (target / "2026-02-22.md").exists()

    def test_overwrites_existing_file(self, tmp_path):
        existing = tmp_path / "2026-02-22.md"
        existing.write_text("old content")
        write_snapshot("2026-02-22", "new content", output_dir=str(tmp_path))
        assert existing.read_text() == "new content"


class TestActivitiesForThePastDate:
    """A snapshot of any date holds that date's activities, however long ago it was."""

    ACTIVITY = {
        "activityName": "Morning Run",
        "startTimeLocal": "2026-09-01 07:15:00",
        "duration": 1800.0,
        "distance": 5000.0,
    }

    def _client(self):
        """A client whose activity search honours the date range it is given, as Garmin's does."""
        client = MagicMock()
        for name in ["get_stats", "get_hrv_data", "get_body_battery", "get_stress_data", "get_sleep_data"]:
            getattr(client, name).return_value = None
        client.get_training_status.return_value = None
        client.get_training_readiness.return_value = None

        def activities_by_date(start, end=None):
            day = date.fromisoformat(self.ACTIVITY["startTimeLocal"][:10])
            in_range = date.fromisoformat(start) <= day <= date.fromisoformat(end or start)
            return [self.ACTIVITY] if in_range else []

        client.get_activities_by_date.side_effect = activities_by_date
        return client

    def test_a_backfilled_date_includes_its_activity(self, tmp_path, monkeypatch):
        client = self._client()
        monkeypatch.setattr(garmin_snapshot, "load_config", lambda: {"email": "test@example.com", "units": "metric"})
        monkeypatch.setattr(garmin_snapshot, "get_client", lambda _config: client)
        monkeypatch.setattr(sys, "argv", ["garmin_snapshot.py", "--output-dir", str(tmp_path), "2026-09-01"])

        garmin_snapshot.main()

        written = (tmp_path / "2026-09-01.md").read_text()
        assert "Morning Run" in written
        assert "No activities found" not in written
        # The query names the date asked for, so it cannot depend on today's date.
        client.get_activities_by_date.assert_called_once_with("2026-09-01", "2026-09-01")
