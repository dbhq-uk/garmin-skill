"""Multi-day queries go easy on Garmin.

`garmin_health.py week` and the weekly rollup are the scripts that make many
calls in one run. They skip days that have not happened, fetch Body Battery for
the whole range in one call, pause between days, and stop at the first failure
or the first sign of a cooldown. Knocking on a rate limit extends it.
"""

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from garminconnect.exceptions import GarminConnectTooManyRequestsError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_client
import garmin_health
import garmin_rollup

API_METHODS = [
    "get_stats",
    "get_hrv_data",
    "get_body_battery",
    "get_stress_data",
    "get_activities_by_date",
    "get_training_status",
    "get_training_readiness",
]

# A Wednesday. Its ISO week, 2026-W36, runs from Monday 31 August to Sunday
# 6 September, so four of its days have not happened yet.
TODAY = date(2026, 9, 2)
WEEK = "2026-W36"


class FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(TODAY.year, TODAY.month, TODAY.day)


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch):
    for module in (garmin_health, garmin_rollup):
        monkeypatch.setattr(module, "date", FrozenDate)


def _client() -> MagicMock:
    client = MagicMock()
    for name in API_METHODS:
        getattr(client, name).return_value = None
    return client


def _calls(client: MagicMock) -> int:
    return sum(getattr(client, name).call_count for name in API_METHODS)


def _dates_asked_for(client: MagicMock) -> set[str]:
    asked = set()
    for name in API_METHODS:
        for call in getattr(client, name).call_args_list:
            asked.update(a for a in call.args if isinstance(a, str) and len(a) == 10 and a[4] == "-")
    return asked


def _run(module, argv: list[str], client: MagicMock, monkeypatch) -> int:
    monkeypatch.setattr(module, "load_config", lambda: {"email": "test@example.com", "units": "metric"})
    monkeypatch.setattr(module, "get_client", lambda _config: client)
    monkeypatch.setattr(sys, "argv", [module.__file__, *argv])
    try:
        module.main()
    except SystemExit as exc:
        return exc.code
    return 0


class TestFutureDays:
    def test_rollup_of_this_week_asks_for_nothing_after_today(self, tmp_path, monkeypatch):
        client = _client()

        assert _run(garmin_rollup, ["--output-dir", str(tmp_path), WEEK], client, monkeypatch) == 0

        asked = _dates_asked_for(client)
        assert asked, "the rollup made no calls at all"
        assert max(asked) == TODAY.isoformat()
        # Three days have happened, so each per-day endpoint is called three times.
        assert client.get_stats.call_count == 3
        assert (tmp_path / f"{WEEK}.md").exists()

    def test_a_week_that_has_not_started_makes_no_calls_and_writes_nothing(self, tmp_path, monkeypatch, capsys):
        client = _client()

        assert _run(garmin_rollup, ["--output-dir", str(tmp_path), "2026-W37"], client, monkeypatch) == 1

        assert _calls(client) == 0
        assert list(tmp_path.iterdir()) == []
        assert "has not started" in capsys.readouterr().err


class TestFewerCalls:
    def test_body_battery_is_one_range_call_for_the_week(self, monkeypatch):
        client = _client()

        assert _run(garmin_health, ["week"], client, monkeypatch) == 0

        client.get_body_battery.assert_called_once_with("2026-08-27", "2026-09-02")
        assert client.get_stats.call_count == 7

    def test_body_battery_from_the_range_call_reaches_the_right_day(self):
        client = _client()
        descriptors = [
            {"bodyBatteryValueDescriptorIndex": 0, "bodyBatteryValueDescriptorKey": "timestamp"},
            {"bodyBatteryValueDescriptorIndex": 1, "bodyBatteryValueDescriptorKey": "bodyBatteryLevel"},
        ]
        client.get_body_battery.return_value = [
            {
                "date": "2026-09-01",
                "bodyBatteryValueDescriptorDTOList": descriptors,
                "bodyBatteryValuesArray": [[1, 30], [2, 70]],
            },
            {
                "date": "2026-09-02",
                "bodyBatteryValueDescriptorDTOList": descriptors,
                "bodyBatteryValuesArray": [[1, 20], [2, 55]],
            },
        ]

        summaries = garmin_health.fetch_day_summaries(client, ["2026-09-01", "2026-09-02"], TODAY)

        assert [s["body_battery_peak"] for s in summaries] == [70, 55]


class TestStopping:
    @pytest.mark.parametrize(
        "module,argv",
        [(garmin_health, ["week"]), (garmin_rollup, ["--output-dir", "{out}", WEEK])],
        ids=["health-week", "rollup"],
    )
    def test_a_429_on_the_first_call_is_the_only_call(self, module, argv, tmp_path, monkeypatch, capsys):
        client = _client()
        for name in API_METHODS:
            getattr(client, name).side_effect = GarminConnectTooManyRequestsError("Rate limit exceeded")

        code = _run(module, [a.format(out=tmp_path) for a in argv], client, monkeypatch)

        assert code == 1
        assert _calls(client) == 1
        assert "until" in capsys.readouterr().err
        assert list(tmp_path.glob("*.md")) == []

    def test_a_cooldown_started_elsewhere_stops_the_next_day(self, tmp_path, monkeypatch, private_cooldown_file):
        """Another script hit a 429 while this one was between days."""
        client = _client()

        def stats(cdate):
            private_cooldown_file.write_text((datetime.now(UTC) + timedelta(minutes=20)).isoformat())
            return None

        client.get_stats.side_effect = stats

        code = _run(garmin_rollup, ["--output-dir", str(tmp_path), WEEK], client, monkeypatch)

        assert code == 1
        assert client.get_stats.call_count == 1
        assert list(tmp_path.iterdir()) == []


class TestPacing:
    def test_it_pauses_between_days_and_not_before_the_first(self, monkeypatch):
        pauses = []
        monkeypatch.setattr(garmin_client, "DAY_PAUSE_SECONDS", 1.0)
        monkeypatch.setattr(garmin_client.time, "sleep", pauses.append)

        assert _run(garmin_health, ["week"], _client(), monkeypatch) == 0

        assert pauses == [1.0] * 6
