"""--json prints the figures unformatted, so an agent can work with them.

The tables are for reading. An agent that wants to compare days or do a sum
needs the numbers themselves: seconds rather than "7h 24m", metres rather than
miles, 8432 rather than "8,432", and null where Garmin has nothing. These run
each query script's main() with a mocked client, so nothing reaches Garmin, and
parse what it prints.
"""

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_activities
import garmin_health
import garmin_sleep

TODAY = date(2026, 9, 2)

STATS = {
    "totalSteps": 8432,
    "totalKilocalories": 2180,
    "restingHeartRate": 58,
    "bodyBatteryLowestValue": 18,
    "bodyBatteryHighestValue": 95,
    "bodyBatteryMostRecentValue": 62,
}
HRV = {"hrvSummary": {"weeklyAvg": 42, "lastNight": 45, "lastNightAvg": 43, "status": "BALANCED"}}
STRESS = {"avgStressLevel": 34, "maxStressLevel": 88}
# Amounts gained and lost over the day, not levels. They must never be read as one.
BODY_BATTERY = [{"date": "2026-09-01", "charged": 75, "drained": 53}]

SLEEP = {
    "dailySleepDTO": {
        "sleepScores": {"overall": {"value": 82}},
        "sleepTimeSeconds": 26640,
        "deepSleepSeconds": 4320,
        "lightSleepSeconds": 13680,
        "remSleepSeconds": 7560,
        "awakeSleepSeconds": 1080,
    }
}

ACTIVITIES = [
    {
        "activityName": "Morning Run",
        "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-09-01 06:45:00",
        "duration": 2100.0,
        "distance": 5200.0,
        "averageHR": 145.0,
        "maxHR": 168.0,
        "calories": 380.0,
        "aerobicTrainingEffect": 3.2,
        "anaerobicTrainingEffect": 1.5,
    },
    {
        "activityName": "Strength",
        "activityType": {"typeKey": "strength_training"},
        "startTimeLocal": "2026-08-31 07:30:00",
        "duration": 3480.0,
        "distance": None,
        "averageHR": 152.0,
        "maxHR": 178.0,
        "calories": 620.0,
        "aerobicTrainingEffect": 3.8,
        "anaerobicTrainingEffect": 2.1,
    },
]

TRAINING_STATUS = {
    "mostRecentVO2Max": {"generic": {"vo2MaxPreciseValue": 44.3, "vo2MaxValue": 44.0}},
    "trainingStatusFeedbackPhrase": "PRODUCTIVE",
    "weeklyTrainingLoad": 412,
}
TRAINING_READINESS = [{"score": 62, "level": "MODERATE"}]

API_METHODS = [
    "get_stats",
    "get_hrv_data",
    "get_body_battery",
    "get_stress_data",
    "get_sleep_data",
    "get_activities_by_date",
    "get_training_status",
    "get_training_readiness",
]

DAY_KEYS = {"date", "resting_hr_bpm", "hrv", "body_battery", "stress", "steps", "calories_kcal"}


class FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(TODAY.year, TODAY.month, TODAY.day)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    for module in (garmin_health, garmin_sleep, garmin_activities):
        monkeypatch.setattr(module, "date", FrozenDate)


def _client(**responses) -> MagicMock:
    """A client that answers the named calls and returns None, Garmin's "nothing", for the rest."""
    client = MagicMock()
    for name in API_METHODS:
        getattr(client, name).return_value = responses.get(name)
    return client


def _json(module, argv: list[str], client: MagicMock, monkeypatch, capsys, units: str = "imperial"):
    monkeypatch.setattr(module, "load_config", lambda: {"email": "test@example.com", "units": units})
    monkeypatch.setattr(module, "get_client", lambda _config: client)
    monkeypatch.setattr(sys, "argv", [module.__file__, *argv, "--json"])
    module.main()
    out, err = capsys.readouterr()
    assert err == ""
    return json.loads(out)


class TestHealth:
    def test_a_day_is_plain_numbers(self, monkeypatch, capsys):
        client = _client(get_stats=STATS, get_hrv_data=HRV, get_body_battery=BODY_BATTERY, get_stress_data=STRESS)

        day = _json(garmin_health, ["2026-09-01"], client, monkeypatch, capsys)

        assert day == {
            "date": "2026-09-01",
            "resting_hr_bpm": 58,
            "hrv": {"last_night_avg_ms": 43, "weekly_avg_ms": 42, "status": "BALANCED"},
            "body_battery": {"lowest": 18, "highest": 95, "latest": 62},
            "stress": {"avg": 34, "max": 88},
            "steps": 8432,
            "calories_kcal": 2180,
        }

    def test_no_data_is_null(self, monkeypatch, capsys):
        day = _json(garmin_health, ["2026-09-01"], _client(), monkeypatch, capsys)

        assert day["date"] == "2026-09-01"
        assert day["resting_hr_bpm"] is None
        assert day["steps"] is None
        assert set(day["hrv"].values()) == {None}
        assert set(day["body_battery"].values()) == {None}
        assert set(day["stress"].values()) == {None}

    def test_body_battery_is_levels_never_charged_or_drained(self, monkeypatch, capsys):
        client = _client(get_stats={"totalSteps": 100}, get_body_battery=BODY_BATTERY)

        day = _json(garmin_health, ["2026-09-01"], client, monkeypatch, capsys)

        assert day["body_battery"] == {"lowest": None, "highest": None, "latest": None}

    def test_the_week_gives_each_day_in_the_single_day_shape(self, monkeypatch, capsys):
        client = _client(get_stats=STATS, get_hrv_data=HRV, get_stress_data=STRESS)

        week = _json(garmin_health, ["week"], client, monkeypatch, capsys)

        assert [d["date"] for d in week["days"]] == [f"2026-08-{n}" for n in range(27, 32)] + [
            "2026-09-01",
            "2026-09-02",
        ]
        for day in week["days"]:
            assert set(day) == DAY_KEYS
            # Not the table's one merged HRV figure: last night and the weekly
            # average stay apart, as in a single day.
            assert day["hrv"] == {"last_night_avg_ms": 43, "weekly_avg_ms": 42, "status": "BALANCED"}
            assert day["steps"] == 8432

    def test_the_week_table_is_unchanged(self, monkeypatch, capsys):
        monkeypatch.setattr(garmin_health, "load_config", lambda: {"email": "test@example.com"})
        monkeypatch.setattr(garmin_health, "get_client", lambda _config: _client(get_stats=STATS))
        monkeypatch.setattr(sys, "argv", [garmin_health.__file__, "week"])

        garmin_health.main()

        assert capsys.readouterr().out.startswith("| Metric | Thu | Fri |")


class TestSleep:
    def test_a_night_is_seconds_not_hours_and_minutes(self, monkeypatch, capsys):
        night = _json(garmin_sleep, ["2026-09-01"], _client(get_sleep_data=SLEEP), monkeypatch, capsys)

        assert night == {
            "date": "2026-09-01",
            "score": 82,
            "duration_seconds": 26640,
            "deep_seconds": 4320,
            "light_seconds": 13680,
            "rem_seconds": 7560,
            "awake_seconds": 1080,
        }

    def test_no_sleep_is_null(self, monkeypatch, capsys):
        night = _json(garmin_sleep, [], _client(), monkeypatch, capsys)

        assert night["date"] == "2026-09-02"
        assert {k: v for k, v in night.items() if k != "date"} == dict.fromkeys(night.keys() - {"date"})


class TestActivities:
    @pytest.mark.parametrize("units", ["imperial", "metric"])
    def test_distances_are_metres_whatever_the_units_setting(self, units, monkeypatch, capsys):
        client = _client(get_activities_by_date=ACTIVITIES)

        result = _json(garmin_activities, ["7"], client, monkeypatch, capsys, units=units)

        run, strength = result["activities"]
        assert run == {
            "name": "Morning Run",
            "type": "running",
            "start_local": "2026-09-01 06:45:00",
            "duration_seconds": 2100.0,
            "distance_metres": 5200.0,
            "average_hr_bpm": 145.0,
            "max_hr_bpm": 168.0,
            "calories_kcal": 380.0,
            "aerobic_training_effect": 3.2,
            "anaerobic_training_effect": 1.5,
        }
        assert strength["distance_metres"] is None

    def test_no_activities_is_an_empty_list(self, monkeypatch, capsys):
        assert _json(garmin_activities, ["7"], _client(), monkeypatch, capsys) == {"activities": []}

    def test_training(self, monkeypatch, capsys):
        client = _client(get_training_status=TRAINING_STATUS, get_training_readiness=TRAINING_READINESS)

        training = _json(garmin_activities, ["training"], client, monkeypatch, capsys)

        assert training == {
            "date": "2026-09-02",
            "vo2_max": 44.3,
            "training_load": 412,
            "training_readiness": 62,
            "training_status": "Productive",
        }

    def test_no_training_data_is_null(self, monkeypatch, capsys):
        training = _json(garmin_activities, ["training"], _client(), monkeypatch, capsys)

        assert {k: v for k, v in training.items() if k != "date"} == dict.fromkeys(training.keys() - {"date"})

    @pytest.mark.parametrize(
        "status,readiness",
        [(TRAINING_STATUS, TRAINING_READINESS), (TRAINING_STATUS, None), (None, {"score": 40})],
        ids=["both", "no-readiness", "no-status"],
    )
    def test_the_table_and_json_read_the_same_values(self, status, readiness):
        values = garmin_activities.training_values(status, readiness)
        table = garmin_activities.format_training_status(status, readiness)
        for label, key in [
            ("VO2 Max", "vo2_max"),
            ("Training Load", "training_load"),
            ("Training Readiness", "training_readiness"),
            ("Training Status", "training_status"),
        ]:
            expected = "No data" if values[key] is None else str(values[key])
            assert f"| {label} | {expected} |" in table
