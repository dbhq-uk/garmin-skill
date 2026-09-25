"""After a 429, nothing calls Garmin until the cooldown has passed.

Knocking on a rate limit extends it, and a fresh login is the loudest knock of
all. So any 429 - on login, on resume or on a fetch - writes a cooldown time,
and every script checks it before it goes near Garmin.
"""

import json
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from garminconnect.client import Client
from garminconnect.exceptions import GarminConnectTooManyRequestsError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_activities
import garmin_client
import garmin_health
import garmin_login
import garmin_rollup
import garmin_sleep
import garmin_snapshot
from garmin_client import (
    DEFAULT_COOLDOWN,
    GarminFetchError,
    GarminRateLimitedError,
    check_cooldown,
    cooldown_until,
    fetch,
    get_client,
    start_cooldown,
)

LOGIN_429 = "Too many login attempts. Please wait a few minutes before trying again."


def _set_cooldown(path: Path, until: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(until.isoformat())


class TestCooldownFile:
    def test_no_file_means_no_cooldown(self):
        assert cooldown_until() is None
        check_cooldown()

    def test_start_writes_a_future_time_owner_only(self, private_cooldown_file):
        until = start_cooldown(GarminConnectTooManyRequestsError(LOGIN_429))

        assert until > datetime.now(UTC) + DEFAULT_COOLDOWN - timedelta(minutes=1)
        assert cooldown_until() == until
        assert stat.S_IMODE(private_cooldown_file.stat().st_mode) == 0o600

    def test_retry_after_is_honoured(self):
        response = MagicMock(status_code=429, headers={"Retry-After": "7200"})
        exc = GarminConnectTooManyRequestsError("Rate limit exceeded")
        exc.response = response

        until = start_cooldown(exc)

        assert until > datetime.now(UTC) + timedelta(minutes=119)

    def test_a_passed_cooldown_is_cleared(self, private_cooldown_file):
        _set_cooldown(private_cooldown_file, datetime.now(UTC) - timedelta(minutes=1))
        assert cooldown_until() is None
        assert not private_cooldown_file.exists()

    def test_an_unreadable_file_is_cleared_not_obeyed_forever(self, private_cooldown_file):
        private_cooldown_file.parent.mkdir(parents=True, exist_ok=True)
        private_cooldown_file.write_text("not a time")
        assert cooldown_until() is None
        assert not private_cooldown_file.exists()

    def test_a_running_cooldown_says_until_when(self, private_cooldown_file):
        until = datetime.now(UTC) + timedelta(minutes=20)
        _set_cooldown(private_cooldown_file, until)

        with pytest.raises(GarminRateLimitedError) as excinfo:
            check_cooldown()

        message = str(excinfo.value)
        assert until.astimezone().strftime("%Y-%m-%d %H:%M") in message
        assert "garmin_login.py" not in message


class TestA429StartsTheCooldown:
    def test_on_resume(self, tmp_path):
        with patch("garmin_client.Garmin") as MockGarmin:
            MockGarmin.return_value.login.side_effect = GarminConnectTooManyRequestsError(LOGIN_429)
            with pytest.raises(GarminRateLimitedError) as excinfo:
                get_client({}, token_dir=str(tmp_path / "tokens"))

        assert cooldown_until() is not None
        assert "garmin_login.py" not in str(excinfo.value)

    def test_on_fetch(self):
        with pytest.raises(GarminFetchError, match="until"):
            fetch(MagicMock(side_effect=GarminConnectTooManyRequestsError("Rate limit exceeded")), "2026-09-01")
        assert cooldown_until() is not None

    def test_on_login(self, tmp_path):
        config = tmp_path.resolve() / "config.json"
        config.write_text(json.dumps({"email": "test@example.com", "password": "secret"}))

        def strategy_chain(self, email, password, prompt_mfa=None, return_on_mfa=False):
            raise GarminConnectTooManyRequestsError("All login strategies rate limited (429).")

        with patch.object(Client, "login", strategy_chain):
            with pytest.raises(garmin_client.GarminConfigError):
                garmin_login.login(str(config), str(tmp_path.resolve() / "tokens"))

        assert cooldown_until() is not None


class TestNothingCallsGarminDuringACooldown:
    @pytest.fixture(autouse=True)
    def cooling_down(self, private_cooldown_file):
        _set_cooldown(private_cooldown_file, datetime.now(UTC) + timedelta(minutes=20))

    def test_login_makes_no_attempt(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"email": "test@example.com", "password": "secret"}))
        with patch.object(Client, "login") as strategy_chain:
            with pytest.raises(GarminRateLimitedError):
                garmin_login.login(str(config), str(tmp_path / "tokens"))
        strategy_chain.assert_not_called()

    @pytest.mark.parametrize(
        "module,argv",
        [
            (garmin_health, ["today"]),
            (garmin_health, ["week"]),
            (garmin_sleep, []),
            (garmin_activities, ["7"]),
            (garmin_activities, ["training"]),
            (garmin_snapshot, ["--output-dir", "{out}"]),
            (garmin_rollup, ["--output-dir", "{out}"]),
        ],
        ids=["health-today", "health-week", "sleep", "activities", "training", "snapshot", "rollup"],
    )
    def test_every_script_refuses_and_says_when(self, module, argv, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(module, "load_config", lambda: {"email": "test@example.com", "units": "metric"})
        monkeypatch.setattr(sys, "argv", [module.__file__, *[a.format(out=tmp_path) for a in argv]])

        with patch("garmin_client.Garmin") as MockGarmin:
            with pytest.raises(SystemExit) as excinfo:
                module.main()

        assert excinfo.value.code == 1
        MockGarmin.assert_not_called()
        err = capsys.readouterr().err
        assert "until" in err
        assert "garmin_login.py" not in err
        assert list(tmp_path.glob("*.md")) == []
