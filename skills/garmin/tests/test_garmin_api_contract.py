"""Contract tests against the real garminconnect package.

These tests deliberately do NOT mock Garmin. The .garth -> .client rename in
garminconnect 0.3.x went undetected for months precisely because every other
test mocks the class, and MagicMock auto-creates any attribute accessed --
including a .garth that no longer exists. These tests assert the real auth
surface the skill depends on, so the next renaming release fails CI instead of
silently degrading into a rate-limit spiral.

Attribute names are not enough on their own. The login once wrote garth token
files that garminconnect 0.3 could not read, while a check that `dump` and
`load` existed stayed green. So the round-trip test below writes tokens the way
garmin_login.py does and hands them to garminconnect's own login(tokenstore).

No network calls. Where garminconnect would reach Garmin - the login strategy
chain, a token refresh, the profile fetch after a resume - the call is replaced,
and the first two fail the test if they are reached.
"""

import base64
import inspect
import json
import os
import stat
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from garminconnect import Garmin
from garminconnect.client import Client
from garminconnect.exceptions import GarminConnectAuthenticationError, GarminConnectConnectionError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_login
from garmin_client import EMPTY_RESPONSE_MESSAGE, LEGACY_TOKEN_FILES, TOKEN_FILE, fetch


def test_garmin_exposes_client_attribute():
    """The skill persists tokens via Garmin.client, garminconnect's own HTTP client."""
    g = Garmin()
    assert hasattr(g, "client"), "garminconnect renamed its client attribute"


def test_garmin_has_no_garth_attribute():
    """Guard against reintroducing the 0.2.x .garth call sites."""
    g = Garmin()
    assert not hasattr(g, "garth"), "garminconnect exposes .garth again -- reconcile with garmin_client.py"


def test_client_can_dump_and_load_tokens():
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


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def _issue_tokens(client: Client, *_args, **_kwargs):
    """What a successful mobile login leaves on the client: a DI token that will
    not expire during the test, so garminconnect has no reason to refresh it."""
    payload = _b64({"exp": int(time.time()) + 86400, "client_id": "TEST_DI_CLIENT"})
    client.di_token = f"{_b64({'alg': 'RS256', 'typ': 'JWT'})}.{payload}.signature"
    client.di_refresh_token = "test-refresh-token"
    client.di_client_id = "TEST_DI_CLIENT"
    return None, None


def _no_network(*_args, **_kwargs):
    raise AssertionError("garminconnect tried to reach Garmin")


def _load_profile(self: Garmin) -> None:
    self.display_name = "tester"
    self.full_name = "Test User"


class TestTokenRoundTrip:
    """What garmin_login.py writes, garminconnect's own login(tokenstore) accepts."""

    def test_login_accepts_the_tokens_the_login_script_writes(self, tmp_path):
        base = tmp_path.resolve()
        config_path = base / "garmin" / "config.json"
        config_path.parent.mkdir()
        config_path.write_text(json.dumps({"email": "test@example.com"}))
        token_dir = base / "garmin" / "tokens"

        # A loose umask, so the modes asserted below are the code's doing.
        old_umask = os.umask(0o002)
        try:
            with (
                patch.object(Garmin, "_load_profile_and_settings", _load_profile),
                patch.object(Client, "login", _issue_tokens),
            ):
                garmin_login.login(str(config_path), str(token_dir), password="secret")
        finally:
            os.umask(old_umask)

        assert stat.S_IMODE(token_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE((token_dir / TOKEN_FILE).stat().st_mode) == 0o600

        # A fresh Garmin(), with no credentials, resuming from that directory.
        # If it could not load the tokens it would fall back to a credential
        # login, which raises; a refresh or an SSO attempt fails the test.
        with (
            patch.object(Garmin, "_load_profile_and_settings", _load_profile),
            patch.object(Client, "login", _no_network),
            patch.object(Client, "_refresh_session", _no_network),
        ):
            resumed = Garmin()
            resumed.login(str(token_dir))

        assert resumed.client.di_refresh_token == "test-refresh-token"

    def test_the_same_check_rejects_garth_format_tokens(self, tmp_path):
        """The files the old garth-based login wrote. This is what the round trip catches."""
        token_dir = tmp_path.resolve() / "tokens"
        token_dir.mkdir(mode=0o700)
        (token_dir / LEGACY_TOKEN_FILES[0]).write_text(json.dumps({"oauth_token": "x", "oauth_token_secret": "y"}))
        (token_dir / LEGACY_TOKEN_FILES[1]).write_text(
            json.dumps({"access_token": "x", "refresh_token": "y", "expires_at": int(time.time()) + 86400})
        )

        with (
            patch.object(Garmin, "_load_profile_and_settings", _load_profile),
            patch.object(Client, "login", _no_network),
            patch.object(Client, "_refresh_session", _no_network),
        ):
            with pytest.raises(GarminConnectAuthenticationError):
                Garmin().login(str(token_dir))
