"""Tests for garmin_login.py - the one script that logs in.

These run the real garminconnect code for everything that touches disk: the
token file is written by garminconnect's own dump() and read back by the same
get_client() every other script uses. Only the calls that would reach Garmin
are replaced - the login strategy chain, the MFA submit and the profile fetch -
so the round trip is proven without a network or an account.

The round trip is the point. The login used to write garth token files that
garminconnect 0.3 cannot read, and every test still passed, because nothing
checked that what the login writes is what the resume path loads.
"""

import base64
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
from garminconnect.exceptions import GarminConnectTooManyRequestsError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import garmin_login
from garmin_client import (
    LEGACY_TOKEN_FILES,
    TOKEN_FILE,
    GarminAuthError,
    GarminConfigError,
    get_client,
)

SCRIPTS = Path(__file__).parent.parent / "scripts"


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def _fake_di_token() -> str:
    """A structurally valid JWT that will not expire during the test.

    garminconnect reads the exp claim to decide whether to refresh. A far
    future exp keeps it from trying to, which would be a network call.
    """
    header = _b64({"alg": "RS256", "typ": "JWT"})
    payload = _b64({"exp": int(time.time()) + 86400, "client_id": "TEST_DI_CLIENT"})
    return f"{header}.{payload}.signature"


def _issue_tokens(client: Client) -> None:
    """What a successful mobile login strategy leaves on the client."""
    client.di_token = _fake_di_token()
    client.di_refresh_token = "test-refresh-token"
    client.di_client_id = "TEST_DI_CLIENT"


def _load_profile(self: Garmin) -> None:
    """Stands in for the two profile calls login makes against Garmin's API."""
    self.display_name = "tester"
    self.full_name = "Test User"


@pytest.fixture
def paths(tmp_path):
    # resolve(): garminconnect refuses a token path with a symlink anywhere in
    # it, and on macOS the temp directory sits under one.
    base = tmp_path.resolve()
    config_dir = base / "garmin"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    config_path.write_text(json.dumps({"email": "test@example.com", "password": "secret"}))
    return config_path, config_dir / "tokens"


@pytest.fixture
def no_profile_calls():
    with patch.object(Garmin, "_load_profile_and_settings", _load_profile):
        yield


class TestRoundTrip:
    """Whatever the login writes, get_client must be able to load."""

    def test_login_writes_tokens_get_client_can_resume_from(self, paths, no_profile_calls):
        config_path, token_dir = paths

        def strategy_chain(self, email, password, prompt_mfa=None, return_on_mfa=False):
            _issue_tokens(self)
            return None, None

        with patch.object(Client, "login", strategy_chain):
            name = garmin_login.login(str(config_path), str(token_dir))

        assert name == "Test User"
        assert (token_dir / TOKEN_FILE).is_file()

        # A separate resume, as a later run of any query script would do it.
        resumed = get_client({"email": "test@example.com"}, token_dir=str(token_dir))
        assert resumed.client.di_refresh_token == "test-refresh-token"

    def test_token_file_is_600_inside_a_700_directory(self, paths, no_profile_calls):
        config_path, token_dir = paths
        # A loose umask and group-writable directories, as garth left them.
        # The modes asserted below then have to be the code's doing.
        old_umask = os.umask(0o002)
        try:
            token_dir.mkdir()
            os.chmod(token_dir, 0o775)
            os.chmod(token_dir.parent, 0o775)

            def strategy_chain(self, email, password, prompt_mfa=None, return_on_mfa=False):
                _issue_tokens(self)
                return None, None

            with patch.object(Client, "login", strategy_chain):
                garmin_login.login(str(config_path), str(token_dir))
        finally:
            os.umask(old_umask)

        assert stat.S_IMODE(token_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(token_dir.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE((token_dir / TOKEN_FILE).stat().st_mode) == 0o600

    def test_mfa_code_is_asked_for_and_submitted(self, paths, no_profile_calls):
        config_path, token_dir = paths
        submitted = []

        def strategy_chain(self, email, password, prompt_mfa=None, return_on_mfa=False):
            assert return_on_mfa, "the login must ask for MFA itself, not hand garminconnect a prompt"
            self._mfa_pending = True
            return "needs_mfa", None

        def resume(self, _state, code):
            submitted.append(code)
            _issue_tokens(self)
            self._mfa_pending = False
            return None, None

        with (
            patch.object(Client, "login", strategy_chain),
            patch.object(Client, "resume_login", resume),
            patch("builtins.input", return_value=" 123456 "),
        ):
            garmin_login.login(str(config_path), str(token_dir))

        assert submitted == ["123456"]
        get_client({"email": "test@example.com"}, token_dir=str(token_dir))

    def test_old_garth_files_are_deleted_after_a_good_login(self, paths, no_profile_calls):
        config_path, token_dir = paths
        token_dir.mkdir()
        for name in LEGACY_TOKEN_FILES:
            (token_dir / name).write_text("{}")

        def strategy_chain(self, email, password, prompt_mfa=None, return_on_mfa=False):
            _issue_tokens(self)
            return None, None

        with patch.object(Client, "login", strategy_chain):
            garmin_login.login(str(config_path), str(token_dir))

        assert sorted(p.name for p in token_dir.iterdir()) == [TOKEN_FILE]


class TestFailures:
    def test_a_session_that_cannot_be_saved_is_reported(self, paths, no_profile_calls):
        """garminconnect falls back to a browser session it cannot persist."""
        config_path, token_dir = paths
        token_dir.mkdir()
        for name in LEGACY_TOKEN_FILES:
            (token_dir / name).write_text("{}")

        def strategy_chain(self, email, password, prompt_mfa=None, return_on_mfa=False):
            self.jwt_web = "browser-session-cookie"
            return None, None

        with patch.object(Client, "login", strategy_chain):
            with pytest.raises(GarminConfigError, match="cannot resume"):
                garmin_login.login(str(config_path), str(token_dir))

        # Nothing is cleared away on a login that did not produce usable tokens.
        assert all((token_dir / name).exists() for name in LEGACY_TOKEN_FILES)

    def test_rate_limit_is_one_attempt_and_says_wait(self, paths, no_profile_calls):
        config_path, token_dir = paths
        calls = []

        def strategy_chain(self, email, password, prompt_mfa=None, return_on_mfa=False):
            calls.append(email)
            raise GarminConnectTooManyRequestsError("Too many login attempts. Please wait...")

        with patch.object(Client, "login", strategy_chain):
            with pytest.raises(GarminConfigError, match="Wait before trying again"):
                garmin_login.login(str(config_path), str(token_dir))

        assert calls == ["test@example.com"]
        assert not (token_dir / TOKEN_FILE).exists()

    def test_main_refuses_to_run_without_a_terminal(self, monkeypatch):
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        with patch.object(Client, "login") as strategy_chain:
            assert garmin_login.main() == 2
        strategy_chain.assert_not_called()


class TestLegacyTokens:
    def test_garth_only_directory_says_old_format_not_expired(self, tmp_path):
        """Real garminconnect, no mocks: this is what a user upgrading sees."""
        token_dir = tmp_path.resolve() / "tokens"
        token_dir.mkdir()
        (token_dir / "oauth1_token.json").write_text(json.dumps({"oauth_token": "x", "oauth_token_secret": "y"}))
        (token_dir / "oauth2_token.json").write_text(json.dumps({"refresh_token_expires_at": 1}))

        with pytest.raises(GarminAuthError) as excinfo:
            get_client({"email": "test@example.com"}, token_dir=str(token_dir))

        message = str(excinfo.value)
        assert "Old token format" in message
        assert "expired" not in message.replace("have not expired", "")
        assert "garmin_login.py" in message


class TestNoGarth:
    def test_no_script_imports_garth(self):
        for script in SCRIPTS.glob("*.py"):
            source = script.read_text()
            assert "import garth" not in source, script.name
            assert "from garth" not in source, script.name

    def test_garth_is_not_a_requirement(self):
        requirements = (SCRIPTS.parent / "requirements.txt").read_text().lower()
        assert "garth" not in requirements
