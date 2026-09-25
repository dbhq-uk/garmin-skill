"""Contract tests against the real garminconnect package.

These tests deliberately do NOT mock Garmin. The .garth -> .client rename in
garminconnect 0.3.x went undetected for months precisely because every other
test mocks the class, and MagicMock auto-creates any attribute accessed --
including a .garth that no longer exists. These tests assert the real auth
surface the skill depends on, so the next renaming release fails CI instead of
silently degrading into a rate-limit spiral.

No network calls: constructing Garmin() and inspecting attributes is offline.
"""

import inspect
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from garminconnect import Garmin
from garminconnect.exceptions import GarminConnectAuthenticationError, GarminConnectConnectionError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_client import EMPTY_RESPONSE_MESSAGE, fetch


def test_garmin_exposes_client_attribute():
    """The skill persists tokens via Garmin.client (garth client)."""
    g = Garmin()
    assert hasattr(g, "client"), "garminconnect renamed the garth client attribute"


def test_garmin_has_no_garth_attribute():
    """Guard against reintroducing the 0.2.x .garth call sites."""
    g = Garmin()
    assert not hasattr(g, "garth"), "garminconnect exposes .garth again -- reconcile with garmin_client.py"


def test_garth_client_can_dump_and_load_tokens():
    """garmin_login.py depends on client.dump()/client.load()."""
    g = Garmin()
    assert hasattr(g.client, "dump")
    assert hasattr(g.client, "load")


def test_login_accepts_a_tokenstore_path():
    """get_client() resumes sessions via login(tokenstore)."""
    params = inspect.signature(Garmin.login).parameters
    assert "tokenstore" in params


def test_credential_free_login_cannot_reach_sso():
    """Safety property: Garmin() with no credentials cannot start an SSO login.

    get_client() relies on this -- it is why resume-only auth can never trip a
    429 or block on an MFA prompt.
    """
    g = Garmin()
    with pytest.raises(GarminConnectAuthenticationError):
        # Empty tokenstore dir -> tokens fail to load -> must refuse, not log in.
        g.login("/nonexistent/token/dir/for/contract/test")


def test_empty_daily_summary_is_still_reported_the_way_fetch_expects():
    """get_stats() raises one specific error for an empty body, and fetch() reads it as no data.

    Only the HTTP call is replaced. If garminconnect rewords that message or
    changes the exception, a day with no stats would start aborting snapshots,
    and this is the test that says why.
    """
    g = Garmin()
    g.display_name = "tester"
    with patch.object(Garmin, "connectapi", return_value=None):
        with pytest.raises(GarminConnectConnectionError) as excinfo:
            g.get_stats("2026-09-01")
        assert str(excinfo.value) == EMPTY_RESPONSE_MESSAGE
        assert fetch(g.get_stats, "2026-09-01") is None
