"""A failed call is not a day with no data.

GarminFetchError means the call failed, and a script that writes a file must
write nothing. A None return means Garmin has nothing for the day, and the file
still writes with "No data". These tests hold that line from both sides, using
garminconnect's real exception classes.
"""

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from garminconnect.exceptions import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_activities
import garmin_health
import garmin_rollup
import garmin_sleep
import garmin_snapshot
from garmin_client import EMPTY_RESPONSE_MESSAGE, GarminFetchError, fetch

SCRIPTS = Path(__file__).parent.parent / "scripts"

FAILURES = [
    GarminConnectTooManyRequestsError("Rate limit exceeded: 429 Too Many Requests"),
    GarminConnectAuthenticationError("Authentication failed: 401 Unauthorized"),
    GarminConnectConnectionError("Connection error: read timed out"),
    GarminConnectNotFoundError("API client error (404): not found"),
]

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


def _client(*, raises: Exception | None = None) -> MagicMock:
    """A client whose every call raises, or whose every call returns None."""
    client = MagicMock()
    for name in API_METHODS:
        method = getattr(client, name)
        if raises is not None:
            method.side_effect = raises
        else:
            method.return_value = None
    return client


def _calls(client: MagicMock) -> int:
    return sum(getattr(client, name).call_count for name in API_METHODS)


def _run(module, argv: list[str], client: MagicMock, monkeypatch) -> int:
    monkeypatch.setattr(module, "load_config", lambda: {"email": "test@example.com", "units": "metric"})
    monkeypatch.setattr(module, "get_client", lambda _config: client)
    monkeypatch.setattr(sys, "argv", [module.__file__, *argv])
    try:
        module.main()
    except SystemExit as exc:
        return exc.code
    return 0


class TestFetch:
    @pytest.mark.parametrize("failure", FAILURES, ids=lambda e: type(e).__name__)
    def test_a_failed_call_raises_fetch_error(self, failure):
        fn = MagicMock(side_effect=failure)
        with pytest.raises(GarminFetchError) as excinfo:
            fetch(fn, "2026-09-01")
        assert excinfo.value.__cause__ is failure

    def test_none_is_no_data_not_a_failure(self):
        assert fetch(MagicMock(return_value=None), "2026-09-01") is None

    def test_an_empty_response_is_no_data_not_a_failure(self):
        fn = MagicMock(side_effect=GarminConnectConnectionError(EMPTY_RESPONSE_MESSAGE))
        assert fetch(fn, "2026-09-01") is None

    def test_a_bug_in_this_skill_is_not_swallowed(self):
        with pytest.raises(KeyError):
            fetch(MagicMock(side_effect=KeyError("oops")), "2026-09-01")


class TestNothingIsWrittenOnFailure:
    @pytest.mark.parametrize("failure", FAILURES, ids=lambda e: type(e).__name__)
    def test_snapshot_exits_non_zero_and_leaves_the_file(self, failure, tmp_path, monkeypatch, capsys):
        existing = tmp_path / "2026-09-01.md"
        existing.write_text("a good day, archived earlier")

        code = _run(
            garmin_snapshot, ["--output-dir", str(tmp_path), "2026-09-01"], _client(raises=failure), monkeypatch
        )

        assert code == 1
        assert existing.read_text() == "a good day, archived earlier"
        assert "Nothing written" in capsys.readouterr().err

    def test_snapshot_does_not_create_a_file_on_failure(self, tmp_path, monkeypatch):
        code = _run(
            garmin_snapshot, ["--output-dir", str(tmp_path), "2026-09-01"], _client(raises=FAILURES[0]), monkeypatch
        )
        assert code == 1
        assert list(tmp_path.iterdir()) == []

    @pytest.mark.parametrize("failure", FAILURES, ids=lambda e: type(e).__name__)
    def test_rollup_exits_non_zero_and_leaves_the_file(self, failure, tmp_path, monkeypatch, capsys):
        existing = tmp_path / "2026-W36.md"
        existing.write_text("a good week, archived earlier")
        client = _client(raises=failure)

        code = _run(garmin_rollup, ["--output-dir", str(tmp_path), "2026-W36"], client, monkeypatch)

        assert code == 1
        assert existing.read_text() == "a good week, archived earlier"
        assert "Nothing written" in capsys.readouterr().err
        # The first failure ends the run: no second day is fetched.
        assert _calls(client) == 1


class TestNoDataStillWrites:
    def test_snapshot_writes_no_data_when_garmin_has_nothing(self, tmp_path, monkeypatch):
        code = _run(garmin_snapshot, ["--output-dir", str(tmp_path), "2026-09-01"], _client(), monkeypatch)

        assert code == 0
        written = (tmp_path / "2026-09-01.md").read_text()
        assert "No data" in written
        assert "No sleep data" in written


class TestQueriesSayTheCallFailed:
    @pytest.mark.parametrize(
        "module,argv",
        [
            (garmin_health, ["today"]),
            (garmin_health, ["week"]),
            (garmin_sleep, ["2026-09-01"]),
            (garmin_activities, ["7"]),
            (garmin_activities, ["training"]),
            (garmin_health, ["today", "--json"]),
            (garmin_health, ["week", "--json"]),
            (garmin_sleep, ["2026-09-01", "--json"]),
            (garmin_activities, ["7", "--json"]),
            (garmin_activities, ["training", "--json"]),
        ],
        ids=[
            "health-today",
            "health-week",
            "sleep",
            "activities",
            "training",
            "health-today-json",
            "health-week-json",
            "sleep-json",
            "activities-json",
            "training-json",
        ],
    )
    def test_failure_is_an_error_not_no_data(self, module, argv, monkeypatch, capsys):
        code = _run(module, argv, _client(raises=FAILURES[0]), monkeypatch)

        out, err = capsys.readouterr()
        assert code == 1
        assert "Error:" in err
        # Nothing at all on stdout: not "No data" in a table, and not a JSON
        # object of nulls, which an agent would read as a day with no data.
        assert out == ""


def test_no_fetcher_catches_bare_exception():
    """A bare except is how a failed call turned back into "No data"."""
    for name in ["garmin_health", "garmin_sleep", "garmin_activities", "garmin_snapshot", "garmin_rollup"]:
        source = (SCRIPTS / f"{name}.py").read_text()
        assert not re.search(r"except(\s+(Exception|BaseException))?\s*(as\s+\w+)?\s*:", source), name
