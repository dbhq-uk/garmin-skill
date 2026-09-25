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
from garminconnect.exceptions import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


def _migrate_legacy_settings() -> None:
    """One-time migration: settings used to live at ~/.garmin."""
    new_dir = Path(os.path.expanduser("~/.dbhq/garmin"))
    old_dir = Path(os.path.expanduser("~/.garmin"))
    if new_dir.exists() or not old_dir.is_dir():
        return
    new_dir.parent.mkdir(mode=0o700, exist_ok=True)
    os.chmod(new_dir.parent, 0o700)
    old_dir.rename(new_dir)
    os.chmod(new_dir, 0o700)


_migrate_legacy_settings()

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.dbhq/garmin/config.json")
DEFAULT_TOKEN_DIR = os.path.expanduser("~/.dbhq/garmin/tokens")


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


# garminconnect raises exactly these for a call that did not work: a rejected
# session, a rate limit, and every other HTTP or network failure (it wraps
# requests' own errors in GarminConnectConnectionError). Anything else is a bug
# in this skill, and has to surface as one rather than as "No data".
FETCH_ERRORS = (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
    GarminConnectConnectionError,
)

# get_stats() raises this when Garmin answered successfully with an empty body.
# That is Garmin having nothing for the day, not a failed call, so it reads as
# None like every other empty day. test_garmin_api_contract.py pins the wording.
EMPTY_RESPONSE_MESSAGE = "No data received from server"


def fetch(fn, *args, **kwargs):
    """Call one Garmin API method, keeping "no data" and "failed" apart.

    Returns whatever Garmin returned, None included: None means Garmin has
    nothing, and the caller renders "No data".

    Raises:
        GarminFetchError: the call itself failed. A caller that writes a file
            must abort rather than write, and a query must say the call failed.
    """
    try:
        return fn(*args, **kwargs)
    except FETCH_ERRORS as exc:
        if type(exc) is GarminConnectConnectionError and str(exc) == EMPTY_RESPONSE_MESSAGE:
            return None
        name = getattr(fn, "__name__", "Garmin call")
        raise GarminFetchError(f"{name} failed: {exc}") from exc


# Derived from this file's own location rather than hardcoded. The skill can be
# installed under Claude Code's skills directory, under Codex's, or inside a
# plugin directory, and this string is printed when someone is already stuck -
# sending them to a path that does not exist on their machine is the worst
# moment to be wrong. resolve() rather than absolute(): under the symlink
# install the real path is the one that works from any shell.
_SKILL_DIR = Path(__file__).resolve().parent.parent
RELOGIN_COMMAND = f"  {_SKILL_DIR}/.venv/bin/python {_SKILL_DIR}/scripts/garmin_login.py"


# garminconnect 0.3.x keeps its session in this one file inside the token
# directory. It writes the file itself, at 600 inside a 700 directory.
TOKEN_FILE = "garmin_tokens.json"

# What garth wrote before garminconnect 0.3 dropped it. garminconnect cannot
# read these, and there is no way to convert them: the only fix is a new login.
LEGACY_TOKEN_FILES = ("oauth1_token.json", "oauth2_token.json")


def token_format(token_dir: str = DEFAULT_TOKEN_DIR) -> str:
    """Say what kind of tokens the directory holds, without calling Garmin.

    Returns:
        "current" if garminconnect's own token file is there, "legacy" if only
        the old garth files are, and "missing" if neither is.
    """
    path = Path(token_dir)
    if (path / TOKEN_FILE).is_file():
        return "current"
    if any((path / name).is_file() for name in LEGACY_TOKEN_FILES):
        return "legacy"
    return "missing"


def remove_legacy_tokens(token_dir: str = DEFAULT_TOKEN_DIR) -> list[str]:
    """Delete the old garth token files, which nothing can read any more.

    Returns the names of the files removed.
    """
    removed = []
    for name in LEGACY_TOKEN_FILES:
        path = Path(token_dir) / name
        if path.is_file() or path.is_symlink():
            path.unlink()
            removed.append(name)
    return removed


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

    fmt = token_format(token_dir)

    if fmt == "legacy":
        return (
            "Old token format: the saved Garmin tokens were written by an earlier version of this skill,\n"
            "and garminconnect 0.3 cannot read them. They have not expired.\n"
            "Log in once, in your own terminal, to replace them:\n"
            f"{RELOGIN_COMMAND}"
        )

    if fmt == "missing":
        return f"Not authenticated: no Garmin tokens found.\nLog in, in your own terminal:\n{RELOGIN_COMMAND}"

    return (
        f"Could not resume Garmin session: {exc}\n"
        f"Log in again, in your own terminal, to refresh your tokens:\n{RELOGIN_COMMAND}"
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
        raise GarminConfigError(f"Config file not found: {config_path}\nRun setup.sh to configure credentials.")

    with open(path) as f:
        config = json.load(f)

    if "email" not in config or not config["email"]:
        raise GarminConfigError(f"Missing 'email' in {config_path}. Run setup.sh to reconfigure.")
    if "password" not in config or not config["password"]:
        raise GarminConfigError(f"Missing 'password' in {config_path}. Run setup.sh to reconfigure.")

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
        token_dir: Directory holding garminconnect's garmin_tokens.json.

    Returns:
        Authenticated Garmin client.

    Raises:
        GarminAuthError: If the session cannot be resumed. The message names the
            actual cause (no tokens / old token format / rate limited).
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
