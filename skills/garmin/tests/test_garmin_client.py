"""Tests for garmin_client.py - auth and session management."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from garminconnect.exceptions import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_client import (
    GarminAuthError,
    GarminConfigError,
    describe_auth_failure,
    get_client,
    load_config,
    remove_legacy_tokens,
    token_format,
)


class TestLoadConfig:
    """Test credential loading from ~/.dbhq/garmin/config.json."""

    def test_loads_valid_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"email": "test@example.com", "password": "secret123"}))
        config = load_config(config_path=str(config_file))
        assert config["email"] == "test@example.com"
        assert config["password"] == "secret123"

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(GarminConfigError, match="not found"):
            load_config(config_path=str(tmp_path / "nonexistent.json"))

    def test_raises_on_missing_email(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"password": "secret123"}))
        with pytest.raises(GarminConfigError, match="email"):
            load_config(config_path=str(config_file))

    def test_raises_on_missing_password(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"email": "test@example.com"}))
        with pytest.raises(GarminConfigError, match="password"):
            load_config(config_path=str(config_file))


class TestGetClient:
    """get_client resumes from cached tokens and never performs an SSO login."""

    @patch("garmin_client.Garmin")
    def test_resumes_from_cached_tokens(self, MockGarmin, tmp_path):
        token_dir = tmp_path / "tokens"
        _write_current(token_dir)

        mock_garmin = MagicMock()
        MockGarmin.return_value = mock_garmin

        config = {"email": "test@example.com", "password": "secret123"}
        client = get_client(config, token_dir=str(token_dir))

        assert client is mock_garmin
        mock_garmin.login.assert_called_once_with(str(token_dir))
        # Constructed WITHOUT credentials: this is what makes SSO unreachable.
        MockGarmin.assert_called_once_with()

    @patch("garmin_client.Garmin")
    def test_never_attempts_credential_login(self, MockGarmin, tmp_path):
        """The whole point: a failed resume must not fall back to SSO."""
        token_dir = tmp_path / "tokens"
        _write_legacy(token_dir)

        mock_garmin = MagicMock()
        mock_garmin.login.side_effect = Exception("Username and password are required")
        MockGarmin.return_value = mock_garmin

        config = {"email": "test@example.com", "password": "secret123"}
        with pytest.raises(GarminAuthError, match="Old token format"):
            get_client(config, token_dir=str(token_dir))

        # Exactly one Garmin() -- no second, credential-bearing instance.
        MockGarmin.assert_called_once_with()

    @patch("garmin_client.Garmin")
    def test_raises_not_authenticated_when_no_tokens(self, MockGarmin, tmp_path):
        token_dir = tmp_path / "tokens"

        mock_garmin = MagicMock()
        mock_garmin.login.side_effect = Exception("Username and password are required")
        MockGarmin.return_value = mock_garmin

        with pytest.raises(GarminAuthError, match="Not authenticated"):
            get_client({"email": "a@b.c", "password": "x"}, token_dir=str(token_dir))

    @patch("garmin_client.Garmin")
    def test_rate_limit_does_not_advise_relogin(self, MockGarmin, tmp_path):
        token_dir = tmp_path / "tokens"
        _write_current(token_dir)

        mock_garmin = MagicMock()
        # garminconnect's own wording, which contains neither "429" nor
        # "too many requests". Only the type says it is a rate limit.
        mock_garmin.login.side_effect = GarminConnectTooManyRequestsError(
            "Too many login attempts. Please wait a few minutes before trying again."
        )
        MockGarmin.return_value = mock_garmin

        with pytest.raises(GarminAuthError) as excinfo:
            get_client({"email": "a@b.c", "password": "x"}, token_dir=str(token_dir))

        assert "garmin_login.py" not in str(excinfo.value)

    @patch("garmin_client.Garmin")
    def test_persists_tokens_after_resume(self, MockGarmin, tmp_path):
        """A resume may silently refresh the access token; persist it."""
        token_dir = tmp_path / "tokens"
        _write_current(token_dir)

        mock_garmin = MagicMock()
        MockGarmin.return_value = mock_garmin

        get_client({"email": "a@b.c", "password": "x"}, token_dir=str(token_dir))

        mock_garmin.client.dump.assert_called_once_with(str(token_dir))


class TestGarminAuthErrorContract:
    """Test that GarminAuthError preserves the subclass contract required by CLI scripts."""

    def test_garmin_auth_error_is_subclass_of_config_error(self):
        """GarminAuthError MUST subclass GarminConfigError.

        All CLI scripts in garmin/scripts/ catch GarminConfigError
        and rely on this to also catch auth errors, so breaking this
        subclass relationship is a load-bearing bug.
        """
        assert issubclass(GarminAuthError, GarminConfigError)

    def test_auth_error_caught_by_config_error_handler(self):
        """Verify that except GarminConfigError: actually catches GarminAuthError.

        This tests the actual behavior the CLI scripts rely on, not just
        the type relationship.
        """
        caught = False
        try:
            raise GarminAuthError("test auth failure")
        except GarminConfigError:
            caught = True
        assert caught, "GarminAuthError was not caught by except GarminConfigError"


RELOGIN_HINT = "garmin_login.py"


def _write_current(token_dir):
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "garmin_tokens.json").write_text(json.dumps({"di_token": "x", "di_refresh_token": "y"}))


def _write_legacy(token_dir):
    """The two files garth wrote, which garminconnect 0.3 cannot read."""
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "oauth1_token.json").write_text(json.dumps({"oauth_token": "a"}))
    (token_dir / "oauth2_token.json").write_text(json.dumps({"refresh_token_expires_at": 1742898314}))


class TestTokenFormat:
    def test_missing_when_token_dir_missing(self, tmp_path):
        assert token_format(str(tmp_path / "nope")) == "missing"

    def test_missing_when_token_dir_empty(self, tmp_path):
        (tmp_path / "tokens").mkdir()
        assert token_format(str(tmp_path / "tokens")) == "missing"

    def test_legacy_when_only_garth_files(self, tmp_path):
        _write_legacy(tmp_path / "tokens")
        assert token_format(str(tmp_path / "tokens")) == "legacy"

    def test_current_wins_over_leftover_garth_files(self, tmp_path):
        _write_legacy(tmp_path / "tokens")
        _write_current(tmp_path / "tokens")
        assert token_format(str(tmp_path / "tokens")) == "current"

    def test_remove_legacy_tokens_leaves_the_current_file(self, tmp_path):
        token_dir = tmp_path / "tokens"
        _write_legacy(token_dir)
        _write_current(token_dir)
        assert remove_legacy_tokens(str(token_dir)) == ["oauth1_token.json", "oauth2_token.json"]
        assert sorted(p.name for p in token_dir.iterdir()) == ["garmin_tokens.json"]


class TestAuthFailureClassification:
    def test_no_tokens_says_not_authenticated(self, tmp_path):
        msg = describe_auth_failure(str(tmp_path / "tokens"), Exception("boom"))
        assert "Not authenticated" in msg
        assert RELOGIN_HINT in msg

    def test_garth_tokens_say_old_format_not_expired(self, tmp_path):
        """Old-format tokens are not expired, and saying so sends people the wrong way."""
        token_dir = tmp_path / "tokens"
        _write_legacy(token_dir)

        msg = describe_auth_failure(str(token_dir), Exception("Username and password are required"))

        assert "Old token format" in msg
        assert "expired on" not in msg
        assert RELOGIN_HINT in msg

    def test_rate_limit_does_not_advise_relogin(self, tmp_path):
        """A 429 must NOT tell the user to log in again -- that deepens the block."""
        token_dir = tmp_path / "tokens"
        _write_current(token_dir)

        exc = GarminConnectTooManyRequestsError(
            "Too many login attempts. Please wait a few minutes before trying again."
        )
        msg = describe_auth_failure(str(token_dir), exc)

        assert "rate-limit" in msg.lower()
        assert "wait" in msg.lower()
        assert RELOGIN_HINT not in msg

    def test_rate_limit_wrapped_in_an_auth_error_is_still_a_rate_limit(self, tmp_path):
        """garminconnect raises an auth error whose cause is the 429."""
        token_dir = tmp_path / "tokens"
        _write_current(token_dir)
        try:
            try:
                raise GarminConnectTooManyRequestsError("Rate limit exceeded")
            except GarminConnectTooManyRequestsError as inner:
                raise GarminConnectAuthenticationError("Failed to retrieve user settings") from inner
        except GarminConnectAuthenticationError as outer:
            msg = describe_auth_failure(str(token_dir), outer)

        assert "rate-limit" in msg.lower()
        assert RELOGIN_HINT not in msg

    def test_the_word_429_alone_is_not_a_rate_limit(self, tmp_path):
        """Detection is by type. A message that happens to say 429 is surfaced as it is."""
        token_dir = tmp_path / "tokens"
        _write_current(token_dir)
        msg = describe_auth_failure(str(token_dir), Exception("record 429 not found"))
        assert "record 429 not found" in msg

    def test_unknown_error_is_surfaced_verbatim(self, tmp_path):
        token_dir = tmp_path / "tokens"
        _write_current(token_dir)

        msg = describe_auth_failure(str(token_dir), Exception("kaboom specifics"))

        assert "kaboom specifics" in msg
        assert RELOGIN_HINT in msg
