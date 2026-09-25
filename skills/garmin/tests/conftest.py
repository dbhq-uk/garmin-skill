"""Shared test setup.

Every test gets its own rate-limit cooldown file. Several tests make Garmin
answer 429 on purpose, and that writes a cooldown: without this it would land
in the real ~/.dbhq/garmin of whoever runs the suite and stop their skill from
calling Garmin for half an hour.
"""

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
