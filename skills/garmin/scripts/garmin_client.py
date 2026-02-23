#!/usr/bin/env python3
"""
Garmin Connect client with session management.

Handles authentication, token caching, and provides a configured
Garmin client instance for other scripts to use.

Usage as library:
    from garmin_client import get_client, load_config
    config = load_config()
    client = get_client(config)
    stats = client.get_stats("2026-02-22")

Usage as CLI (test auth):
    python garmin_client.py
"""

import json
import os
import sys
from pathlib import Path

from garminconnect import Garmin


DEFAULT_CONFIG_PATH = os.path.expanduser("~/.garmin/config.json")
DEFAULT_TOKEN_DIR = os.path.expanduser("~/.garmin/tokens")


class GarminConfigError(Exception):
    """Raised when Garmin configuration is invalid or missing."""
    pass


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Load Garmin credentials from config file.

    Args:
        config_path: Path to config.json containing email and password.

    Returns:
        Dict with 'email' and 'password' keys.

    Raises:
        GarminConfigError: If file missing or fields invalid.
    """
    path = Path(config_path)
    if not path.exists():
        raise GarminConfigError(
            f"Config file not found: {config_path}\n"
            f"Run setup.sh to configure credentials."
        )

    with open(path) as f:
        config = json.load(f)

    if "email" not in config or not config["email"]:
        raise GarminConfigError(
            f"Missing 'email' in {config_path}. Run setup.sh to reconfigure."
        )
    if "password" not in config or not config["password"]:
        raise GarminConfigError(
            f"Missing 'password' in {config_path}. Run setup.sh to reconfigure."
        )

    return config


def get_client(
    config: dict,
    token_dir: str = DEFAULT_TOKEN_DIR,
) -> Garmin:
    """Create an authenticated Garmin client.

    Tries cached tokens first, falls back to email/password login.
    Saves tokens after successful credential-based login.

    Args:
        config: Dict with 'email' and 'password'.
        token_dir: Directory for garth token storage.

    Returns:
        Authenticated Garmin client instance.
    """
    token_path = Path(token_dir)
    token_path.mkdir(parents=True, exist_ok=True)

    # Try cached tokens first
    if any(token_path.iterdir()):
        try:
            garmin = Garmin()
            garmin.login(str(token_path))
            return garmin
        except Exception:
            pass  # Fall through to credential login

    # Credential-based login
    garmin = Garmin(
        email=config["email"],
        password=config["password"],
        is_cn=False,
    )
    garmin.login()
    garmin.garth.dump(str(token_path))
    return garmin


if __name__ == "__main__":
    """Quick auth test - run to verify credentials work."""
    try:
        config = load_config()
        client = get_client(config)
        name = client.get_full_name()
        print(f"Authenticated as: {name}")
    except GarminConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Auth error: {e}", file=sys.stderr)
        sys.exit(1)
