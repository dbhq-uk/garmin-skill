"""Shared test setup.

Every test gets its own rate-limit cooldown file. Several tests make Garmin
answer 429 on purpose, and that writes a cooldown: without this it would land
in the real ~/.dbhq/garmin of whoever runs the suite and stop their skill from
calling Garmin for half an hour.

No test may prompt for a password either. A prompt reads the terminal, not
stdin, so it would hang the suite rather than fail it.
"""

import getpass
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_client


@pytest.fixture(autouse=True)
def private_cooldown_file(tmp_path_factory, monkeypatch):
    # Its own directory, not tmp_path: tests that list tmp_path must not see it.
    path = tmp_path_factory.mktemp("cooldown") / "ratelimited_until"
    monkeypatch.setattr(garmin_client, "COOLDOWN_FILE", str(path))
    return path


@pytest.fixture(autouse=True)
def no_password_prompt(monkeypatch):
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)

    def refuse(*_args, **_kwargs):
        raise AssertionError("a test reached the password prompt; pass password= or patch getpass")

    monkeypatch.setattr(getpass, "getpass", refuse)
