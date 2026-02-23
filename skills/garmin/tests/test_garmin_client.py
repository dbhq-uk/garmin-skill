"""Tests for garmin_client.py - auth and session management."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from garmin_client import get_client, load_config, GarminConfigError


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
    """Test Garmin client creation with token caching."""

    @patch("garmin_client.Garmin")
    def test_loads_cached_tokens_first(self, MockGarmin, tmp_path):
        """If tokens exist, should try loading them before using credentials."""
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        # Create a dummy file so iterdir() finds something
        (token_dir / "oauth_token").write_text("dummy")

        mock_garmin = MagicMock()
        MockGarmin.return_value = mock_garmin

        config = {"email": "test@example.com", "password": "secret123"}
        client = get_client(config, token_dir=str(token_dir))

        # Should attempt token-based login
        mock_garmin.login.assert_called_once_with(str(token_dir))
        assert client is mock_garmin

    @patch("garmin_client.Garmin")
    def test_falls_back_to_credentials_on_token_failure(self, MockGarmin, tmp_path):
        """If token login fails, should fall back to email/password."""
        token_dir = tmp_path / "tokens"
        token_dir.mkdir()
        (token_dir / "oauth_token").write_text("dummy")

        # First Garmin() instance: token login fails
        mock_token_garmin = MagicMock()
        mock_token_garmin.login.side_effect = Exception("Token expired")

        # Second Garmin() instance: credential login succeeds
        mock_cred_garmin = MagicMock()
        mock_cred_garmin.login.return_value = ("", "")
        mock_cred_garmin.garth = MagicMock()

        MockGarmin.side_effect = [mock_token_garmin, mock_cred_garmin]

        config = {"email": "test@example.com", "password": "secret123"}
        client = get_client(config, token_dir=str(token_dir))

        assert client is mock_cred_garmin
        # Should have saved tokens after successful credential login
        mock_cred_garmin.garth.dump.assert_called_once_with(str(token_dir))

    @patch("garmin_client.Garmin")
    def test_creates_token_dir_if_missing(self, MockGarmin, tmp_path):
        """Token directory should be created if it doesn't exist."""
        token_dir = tmp_path / "tokens"
        # Don't create it - get_client should

        mock_garmin = MagicMock()
        mock_garmin.login.return_value = ("", "")
        mock_garmin.garth = MagicMock()
        MockGarmin.return_value = mock_garmin

        config = {"email": "test@example.com", "password": "secret123"}
        get_client(config, token_dir=str(token_dir))

        assert token_dir.exists()
