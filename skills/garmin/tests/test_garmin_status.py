"""Tests for garmin_status.py - what is set up, read from disk, with no network.

The point of the command is that it is safe to run at any time, a cooldown
included. So every test here runs with garminconnect's network layer and its
login replaced by something that fails the test if it is reached.
"""

import json
import os
import stat
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from garminconnect.client import Client

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_status
from garmin_client import LEGACY_TOKEN_FILES, TOKEN_FILE


def _no_network(*_args, **_kwargs):
    raise AssertionError("garmin_status.py reached for the network")


@pytest.fixture(autouse=True)
def offline():
    with (
        patch.object(Client, "_run_request", _no_network),
        patch.object(Client, "login", _no_network),
        patch.object(Client, "_refresh_session", _no_network),
    ):
        yield


@pytest.fixture
def paths(tmp_path):
    base = tmp_path.resolve() / "garmin"
    base.mkdir(mode=0o700)
    return base / "config.json", base / "tokens"


def _write_config(config_path: Path, **settings) -> None:
    config_path.write_text(json.dumps({"email": "test@example.com", **settings}))
    config_path.chmod(0o600)


def _write_current_tokens(token_dir: Path) -> None:
    """The file garminconnect's own dump() writes after a login."""
    client = Client()
    client.di_token = "header." + "e30" + ".signature"
    client.di_refresh_token = "test-refresh-token"
    client.di_client_id = "TEST_DI_CLIENT"
    client.dump(str(token_dir))


def _status(paths) -> dict:
    config_path, token_dir = paths
    return garmin_status.status(str(config_path), str(token_dir))


class TestWhatToDoNext:
    def test_nothing_set_up_says_run_setup(self, paths):
        report = _status(paths)
        assert not report["ready"]
        assert "setup.sh" in report["next_step"]

    def test_settings_but_no_tokens_says_log_in(self, paths):
        _write_config(paths[0])
        report = _status(paths)
        assert not report["ready"]
        assert report["tokens"]["format"] == "missing"
        assert "garmin_login.py" in report["next_step"]

    def test_old_token_format_is_named(self, paths):
        _write_config(paths[0])
        paths[1].mkdir(mode=0o700)
        for name in LEGACY_TOKEN_FILES:
            (paths[1] / name).write_text("{}")
        report = _status(paths)
        assert report["tokens"]["format"] == "legacy"
        assert "Old token format" in report["next_step"]

    def test_a_token_file_garminconnect_cannot_read_is_not_ready(self, paths):
        _write_config(paths[0])
        paths[1].mkdir(mode=0o700)
        (paths[1] / TOKEN_FILE).write_text("not json")
        report = _status(paths)
        assert report["tokens"]["format"] == "unreadable"
        assert not report["ready"]

    def test_current_tokens_are_ready_with_their_age(self, paths):
        _write_config(paths[0], units="metric")
        _write_current_tokens(paths[1])
        two_days_ago = time.time() - 2 * 86400
        os.utime(paths[1] / TOKEN_FILE, (two_days_ago, two_days_ago))

        report = _status(paths)

        assert report["ready"]
        assert report["tokens"]["format"] == "current"
        assert report["tokens"]["age_days"] == pytest.approx(2.0, abs=0.1)
        assert report["settings"]["units"] == "metric"
        assert report["warnings"] == []

    def test_a_cooldown_comes_first_and_never_says_log_in(self, paths, private_cooldown_file):
        _write_config(paths[0])
        _write_current_tokens(paths[1])
        until = datetime.now(UTC) + timedelta(minutes=20)
        private_cooldown_file.write_text(until.isoformat())

        report = _status(paths)

        assert not report["ready"]
        assert report["cooldown_until"] is not None
        assert "until" in report["next_step"]
        assert "garmin_login.py" not in report["next_step"]


class TestWarnings:
    def test_loose_modes_are_reported(self, paths):
        _write_config(paths[0])
        _write_current_tokens(paths[1])
        paths[0].chmod(0o644)
        paths[1].chmod(0o755)
        (paths[1] / TOKEN_FILE).chmod(0o644)

        warnings = _status(paths)["warnings"]

        assert any("config.json is 644" in w for w in warnings)
        assert any("tokens is 755" in w for w in warnings)
        assert any(f"{TOKEN_FILE} is 644" in w for w in warnings)

    def test_a_saved_password_is_reported(self, paths):
        _write_config(paths[0], password="old")
        _write_current_tokens(paths[1])
        report = _status(paths)
        assert report["ready"]
        assert any("password" in w for w in report["warnings"])


class TestIsReadOnly:
    def test_it_changes_nothing_it_reads(self, paths):
        _write_config(paths[0], password="old")
        _write_current_tokens(paths[1])
        before = {p: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in [paths[0], paths[1] / TOKEN_FILE]}

        _status(paths)

        after = {p: (p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in before}
        assert after == before


class TestCommand:
    def test_exit_code_is_0_when_ready_and_1_when_not(self, paths, capsys):
        config_path, token_dir = (str(p) for p in paths)
        assert garmin_status.main([], config_path, token_dir) == 1
        _write_config(paths[0])
        _write_current_tokens(paths[1])
        assert garmin_status.main([], config_path, token_dir) == 0
        assert "Ready" in capsys.readouterr().out

    def test_json_parses(self, paths, capsys):
        _write_config(paths[0])
        garmin_status.main(["--json"], str(paths[0]), str(paths[1]))
        report = json.loads(capsys.readouterr().out)
        assert report["ready"] is False
        assert report["tokens"]["format"] == "missing"
