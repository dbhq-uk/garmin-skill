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
from datetime import datetime
from pathlib import Path

from garminconnect import Garmin

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.garmin/config.json")
DEFAULT_TOKEN_DIR = os.path.expanduser("~/.garmin/tokens")


class GarminConfigError(Exception):
    """Raised when Garmin configuration is invalid or missing."""
    pass


class GarminAuthError(GarminConfigError):
    """Raised when a Garmin session cannot be resumed from cached tokens.

    Subclasses GarminConfigError so existing `except GarminConfigError`
    handlers in the CLI scripts catch it unchanged.
    """
    pass


class GarminFetchError(Exception):
    """Raised when a Garmin API call fails (auth, rate limit, network).

    Distinct from "Garmin has no data for this day", which is a None return.
    Callers that write files must abort on this rather than archive an empty day.
    """
    pass


RELOGIN_COMMAND = (
    "  ~/.claude/skills/garmin/.venv/bin/python "
    "~/.claude/skills/garmin/scripts/garmin_login.py"
)


def read_refresh_expiry(token_dir: str = DEFAULT_TOKEN_DIR) -> datetime | None:
    """Read the refresh token's expiry from the cached oauth2 token.

    Returns None if the token file is missing, unreadable, or has no expiry --
    all of which mean "we cannot say when this expires", not "it is valid".
    """
    token_file = Path(token_dir) / "oauth2_token.json"
    try:
        with open(token_file) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None

    expires_at = data.get("refresh_token_expires_at")
    if not expires_at:
        return None
    try:
        return datetime.fromtimestamp(expires_at)
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def describe_auth_failure(token_dir: str, exc: Exception) -> str:
    """Build an actionable message explaining why a session could not be resumed.

    Deliberately does NOT suggest re-login on a 429: a fresh SSO login while
    rate-limited extends the block rather than clearing it.
    """
    if "429" in str(exc) or "too many requests" in str(exc).lower():
        return (
            "Garmin is rate-limiting this IP (HTTP 429).\n"
            "Wait before retrying. Do not re-run login -- that extends the block."
        )

    expiry = read_refresh_expiry(token_dir)

    if expiry is None:
        return (
            "Not authenticated: no usable Garmin tokens found.\n"
            "Log in to authenticate:\n"
            f"{RELOGIN_COMMAND}"
        )

    if expiry < datetime.now():
        return (
            f"Garmin tokens expired on {expiry.date().isoformat()}.\n"
            "Log in again to refresh them:\n"
            f"{RELOGIN_COMMAND}"
        )

    return (
        f"Could not resume Garmin session: {exc}\n"
        "Log in again to refresh your tokens:\n"
        f"{RELOGIN_COMMAND}"
    )


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

    # Default preferences
    config.setdefault("units", "imperial")

    return config


def get_client(
    config: dict,
    token_dir: str = DEFAULT_TOKEN_DIR,
) -> Garmin:
    """Create a Garmin client by resuming a cached session.

    Resume-only by design. This never performs an SSO login, because doing so
    non-interactively is what drove the account into a Cloudflare 429: it can
    also demand an MFA code that no cron job can supply. Interactive login is
    garmin_login.py's job.

    Args:
        config: Loaded config. Retained for signature compatibility with the
            calling scripts; credentials are not used to log in here.
        token_dir: Directory holding cached garth tokens.

    Returns:
        Authenticated Garmin client.

    Raises:
        GarminAuthError: If the session cannot be resumed. The message names the
            actual cause (no tokens / expired on <date> / rate limited).
    """
    token_path = Path(token_dir)

    try:
        garmin = Garmin()
        garmin.login(str(token_path))
    except Exception as exc:
        raise GarminAuthError(describe_auth_failure(str(token_path), exc)) from exc

    # login() may have refreshed the access token in memory. Persist it so the
    # next run resumes cleanly instead of drifting towards a full re-login.
    try:
        garmin.client.dump(str(token_path))
    except Exception as exc:
        print(f"Warning: could not persist refreshed tokens: {exc}", file=sys.stderr)

    return garmin


if __name__ == "__main__":
    """Quick auth test - run to verify cached tokens work."""
    try:
        config = load_config()
        client = get_client(config)
        name = client.get_full_name()
        print(f"Authenticated as: {name}")
    except GarminConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
