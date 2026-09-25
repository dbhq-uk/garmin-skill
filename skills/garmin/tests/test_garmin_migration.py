"""The one-time move of settings from ~/.garmin to ~/.dbhq/garmin.

It used to run on import, so running this test suite could move a developer's
real ~/.garmin. Now it runs when a script first reads the default settings
file. Each test here runs Python in a subprocess with HOME pointed at a
temporary directory, because the default paths are fixed when the module is
imported and only a fresh interpreter picks up a different HOME.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"


def _python(home: Path, code: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(home)}
    prelude = f"import sys; sys.path.insert(0, {str(SCRIPTS)!r})\n"
    return subprocess.run([sys.executable, "-c", prelude + code], env=env, capture_output=True, text=True, timeout=60)


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    old = home / ".garmin"
    old.mkdir(parents=True)
    (old / "config.json").write_text(json.dumps({"email": "old@example.com", "units": "metric"}))
    return home


def test_importing_the_client_moves_nothing(home):
    result = _python(home, "import garmin_client, garmin_login")
    assert result.returncode == 0, result.stderr
    assert (home / ".garmin" / "config.json").is_file()
    assert not (home / ".dbhq").exists()


def test_the_first_settings_read_moves_them(home):
    result = _python(home, "import garmin_client; print(garmin_client.load_config()['email'])")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "old@example.com"
    assert not (home / ".garmin").exists()
    assert json.loads((home / ".dbhq" / "garmin" / "config.json").read_text())["units"] == "metric"
    assert stat.S_IMODE((home / ".dbhq").stat().st_mode) == 0o700
    assert stat.S_IMODE((home / ".dbhq" / "garmin").stat().st_mode) == 0o700


def test_the_status_command_moves_them_too(home):
    result = _python(home, "import garmin_status; garmin_status.status()")
    assert result.returncode == 0, result.stderr
    assert (home / ".dbhq" / "garmin" / "config.json").is_file()


def test_existing_settings_are_never_overwritten(home):
    new = home / ".dbhq" / "garmin"
    new.mkdir(parents=True)
    (new / "config.json").write_text(json.dumps({"email": "new@example.com"}))

    result = _python(home, "import garmin_client; print(garmin_client.load_config()['email'])")

    assert result.stdout.strip() == "new@example.com"
    assert (home / ".garmin" / "config.json").is_file()


def test_a_config_path_given_explicitly_moves_nothing(home, tmp_path):
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps({"email": "x@example.com"}))

    result = _python(home, f"import garmin_client; garmin_client.load_config({str(elsewhere)!r})")

    assert result.returncode == 0, result.stderr
    assert (home / ".garmin").is_dir()
    assert not (home / ".dbhq").exists()
