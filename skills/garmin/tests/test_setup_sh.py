"""Tests for setup.sh - the settings it writes, and what it says when login fails.

setup.sh runs here for real, in a copy of the skill directory with a throwaway
HOME. Only two things are stood in for: pip, so nothing is installed, and
garmin_login.py, so nothing calls Garmin. garmin_client.py is the real one,
because it is what writes config.json.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).parent.parent

# Stands in for garmin_login.py. It notes that it ran, and fails with the
# message it is given, so setup.sh's handling of a failed login can be seen.
FAKE_LOGIN = """\
import os, sys
open(os.environ["FAKE_LOGIN_LOG"], "a").write("called\\n")
message = os.environ.get("FAKE_LOGIN_ERROR")
if message:
    print(message, file=sys.stderr)
    sys.exit(1)
print("Authenticated as: Test User")
"""


def _executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def skill(tmp_path):
    root = tmp_path / "skill"
    (root / "scripts").mkdir(parents=True)
    for name in ["setup.sh", "garmin_client.py"]:
        shutil.copy2(SKILL_DIR / "scripts" / name, root / "scripts" / name)
    (root / "scripts" / "garmin_login.py").write_text(FAKE_LOGIN)
    (root / "requirements.txt").write_text("")

    # An existing venv, so setup.sh does not build one. Its python is the one
    # running this test, which has garminconnect, and its pip does nothing.
    venv_bin = root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    _executable(venv_bin / "python", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    _executable(venv_bin / "pip", "#!/bin/sh\nexit 0\n")

    # setup.sh checks python3's version before anything else.
    path_bin = tmp_path / "bin"
    path_bin.mkdir()
    _executable(path_bin / "python3", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')

    home = tmp_path / "home"
    home.mkdir()
    return {
        "root": root,
        "home": home,
        "config": home / ".dbhq" / "garmin" / "config.json",
        "log": tmp_path / "login.log",
        "path": f"{path_bin}{os.pathsep}{os.environ['PATH']}",
    }


def _run_setup(skill, stdin: str, login_error: str | None = None) -> subprocess.CompletedProcess:
    env = {
        "HOME": str(skill["home"]),
        "PATH": skill["path"],
        "FAKE_LOGIN_LOG": str(skill["log"]),
    }
    if login_error:
        env["FAKE_LOGIN_ERROR"] = login_error
    # umask 000: whatever mode config.json ends up with is then the code's doing.
    return subprocess.run(
        ["bash", "-c", 'umask 000; exec bash "$0"', str(skill["root"] / "scripts" / "setup.sh")],
        input=stdin,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


EMAIL = 'we"ird\\name@example.com'


class TestSettingsFile:
    def test_quotes_and_backslashes_still_make_valid_json(self, skill):
        # A second line too, because the old setup asked for a password next.
        result = _run_setup(skill, f'{EMAIL}\npass"word\\\n')

        assert result.returncode == 0, result.stderr
        assert json.loads(skill["config"].read_text()) == {"email": EMAIL}

    def test_no_password_is_stored(self, skill):
        _run_setup(skill, f"{EMAIL}\nsecret\n")
        text = skill["config"].read_text()
        assert "password" not in json.loads(text)
        assert "secret" not in text

    def test_file_is_600_in_a_700_directory(self, skill):
        _run_setup(skill, f"{EMAIL}\n")
        assert stat.S_IMODE(skill["config"].stat().st_mode) == 0o600
        assert stat.S_IMODE(skill["config"].parent.stat().st_mode) == 0o700

    def test_keeping_existing_settings_drops_a_saved_password(self, skill):
        skill["config"].parent.mkdir(parents=True)
        skill["config"].write_text(json.dumps({"email": "a@b.c", "password": "old", "units": "metric"}))

        result = _run_setup(skill, "n\n")

        assert result.returncode == 0, result.stderr
        assert json.loads(skill["config"].read_text()) == {"email": "a@b.c", "units": "metric"}
        assert stat.S_IMODE(skill["config"].stat().st_mode) == 0o600

    def test_changing_the_email_keeps_other_settings(self, skill):
        skill["config"].parent.mkdir(parents=True)
        skill["config"].write_text(json.dumps({"email": "a@b.c", "password": "old", "units": "metric"}))

        result = _run_setup(skill, "y\nnew@example.com\n")

        assert result.returncode == 0, result.stderr
        assert json.loads(skill["config"].read_text()) == {"email": "new@example.com", "units": "metric"}


class TestLoginFailure:
    def test_the_real_reason_is_shown_not_blamed_on_credentials(self, skill):
        reason = "Error: Garmin is rate-limiting this IP (HTTP 429)."
        result = _run_setup(skill, f"{EMAIL}\n", login_error=reason)

        assert result.returncode == 1
        assert reason in result.stderr
        assert "Check your credentials" not in result.stdout + result.stderr

    def test_login_runs_once(self, skill):
        _run_setup(skill, f"{EMAIL}\n", login_error="Error: Garmin refused the login")
        assert skill["log"].read_text() == "called\n"
