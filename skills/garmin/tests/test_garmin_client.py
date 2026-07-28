"""Tests for garmin_client.py - auth and session management."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_client import (
    GarminAuthError,
    GarminConfigError,
    describe_auth_failure,
    get_client,
    load_config,
    read_refresh_expiry,
)


class TestLoadConfig:
    """Test credential loading from ~/.garmin/config.json."""

    def test_loads_valid_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "email": "test@example.com",
            "password": "secret123"
        }))
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
        _write_oauth2(token_dir, (datetime.now() + timedelta(days=10)).timestamp())

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
        _write_oauth2(token_dir, (datetime.now() - timedelta(days=30)).timestamp())

        mock_garmin = MagicMock()
        mock_garmin.login.side_effect = Exception("Username and password are required")
        MockGarmin.return_value = mock_garmin

        config = {"email": "test@example.com", "password": "secret123"}
        with pytest.raises(GarminAuthError, match="expired"):
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
        _write_oauth2(token_dir, (datetime.now() + timedelta(days=10)).timestamp())

        mock_garmin = MagicMock()
        mock_garmin.login.side_effect = Exception("Error 429: Too Many Requests")
        MockGarmin.return_value = mock_garmin

        with pytest.raises(GarminAuthError) as excinfo:
            get_client({"email": "a@b.c", "password": "x"}, token_dir=str(token_dir))

        assert "garmin_login.py" not in str(excinfo.value)

    @patch("garmin_client.Garmin")
    def test_persists_tokens_after_resume(self, MockGarmin, tmp_path):
        """A resume may silently refresh the access token; persist it."""
        token_dir = tmp_path / "tokens"
        _write_oauth2(token_dir, (datetime.now() + timedelta(days=10)).timestamp())

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


def _write_oauth2(token_dir, expires_at):
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "oauth2_token.json").write_text(
        json.dumps({"refresh_token_expires_at": expires_at})
    )


class TestReadRefreshExpiry:
    def test_returns_none_when_token_dir_missing(self, tmp_path):
        assert read_refresh_expiry(str(tmp_path / "nope")) is None

    def test_returns_none_when_field_absent(self, tmp_path):
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        (token_dir / "oauth2_token.json").write_text(json.dumps({"scope": "x"}))
        assert read_refresh_expiry(str(token_dir)) is None

    def test_returns_none_on_corrupt_json(self, tmp_path):
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        (token_dir / "oauth2_token.json").write_text("{not json")
        assert read_refresh_expiry(str(token_dir)) is None

    def test_reads_expiry_timestamp(self, tmp_path):
        token_dir = tmp_path / "tokens"
        expected = datetime(2026, 3, 25, 10, 25, 14)
        _write_oauth2(token_dir, expected.timestamp())
        assert read_refresh_expiry(str(token_dir)) == expected


class TestAuthFailureClassification:
    def test_no_tokens_says_not_authenticated(self, tmp_path):
        msg = describe_auth_failure(str(tmp_path / "tokens"), Exception("boom"))
        assert "Not authenticated" in msg
        assert RELOGIN_HINT in msg

    def test_expired_tokens_report_the_expiry_date(self, tmp_path):
        token_dir = tmp_path / "tokens"
        expired = datetime.now() - timedelta(days=30)
        _write_oauth2(token_dir, expired.timestamp())

        msg = describe_auth_failure(str(token_dir), Exception("boom"))

        assert "expired" in msg.lower()
        assert expired.date().isoformat() in msg
        assert RELOGIN_HINT in msg

    def test_rate_limit_does_not_advise_relogin(self, tmp_path):
        """A 429 must NOT tell the user to log in again -- that deepens the block."""
        token_dir = tmp_path / "tokens"
        _write_oauth2(token_dir, (datetime.now() + timedelta(days=10)).timestamp())

        msg = describe_auth_failure(str(token_dir), Exception("Error 429: Too Many Requests"))

        assert "rate-limit" in msg.lower() or "rate limit" in msg.lower()
        assert RELOGIN_HINT not in msg

    def test_unknown_error_is_surfaced_verbatim(self, tmp_path):
        token_dir = tmp_path / "tokens"
        _write_oauth2(token_dir, (datetime.now() + timedelta(days=10)).timestamp())

        msg = describe_auth_failure(str(token_dir), Exception("kaboom specifics"))

        assert "kaboom specifics" in msg
        assert RELOGIN_HINT in msg
