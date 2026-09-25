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
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from garminconnect import Garmin
from garminconnect.exceptions import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)


def migrate_legacy_settings() -> bool:
    """One-time move: settings used to live at ~/.garmin, and now live at ~/.dbhq/garmin.

    load_config() calls this when it reads the default settings file, which
    every script does first, so whichever script runs first does the move.
    Never on import: importing this module, as the test suite does, must not
    move anybody's settings. An existing ~/.dbhq/garmin is never overwritten.

    Returns True if it moved them.
    """
    home = Path.home()
    new_dir = home / ".dbhq" / "garmin"
    old_dir = home / ".garmin"
    if new_dir.exists() or new_dir.is_symlink() or not old_dir.is_dir():
        return False
    new_dir.parent.mkdir(mode=0o700, exist_ok=True)
    os.chmod(new_dir.parent, 0o700)
    old_dir.rename(new_dir)
    os.chmod(new_dir, 0o700)
    return True


DEFAULT_CONFIG_PATH = os.path.expanduser("~/.dbhq/garmin/config.json")
DEFAULT_TOKEN_DIR = os.path.expanduser("~/.dbhq/garmin/tokens")

# After any 429, this file holds the time before which no script calls Garmin.
# A module global rather than a default argument, so the one place that points
# it somewhere else (the test suite) moves it for every caller at once.
COOLDOWN_FILE = os.path.expanduser("~/.dbhq/garmin/ratelimited_until")

# Garmin does not say how long a block lasts, and its 429s rarely carry a
# Retry-After. Half an hour is long enough not to extend a block by knocking on
# it, and short enough that a blip does not cost the afternoon.
DEFAULT_COOLDOWN = timedelta(minutes=30)

# A query that covers several days waits this long between them, so a week is
# a steady trickle rather than a burst. Garmin publishes no rate, so this is a
# courtesy rather than a guarantee. The test suite sets it to zero.
DAY_PAUSE_SECONDS = 1.0


class GarminConfigError(Exception):
    """Raised when Garmin configuration is invalid or missing."""

    pass


class GarminAuthError(GarminConfigError):
    """Raised when a Garmin session cannot be resumed from cached tokens.

    Subclasses GarminConfigError so existing `except GarminConfigError`
    handlers in the CLI scripts catch it unchanged.
    """

    pass


class GarminRateLimitedError(GarminAuthError):
    """Raised instead of calling Garmin while a rate-limit cooldown is running.

    Subclasses GarminAuthError, so every script's `except GarminConfigError`
    already reports it and exits.
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
            A 429 also starts the cooldown, and the message says until when.
    """
    try:
        return fn(*args, **kwargs)
    except FETCH_ERRORS as exc:
        if type(exc) is GarminConnectConnectionError and str(exc) == EMPTY_RESPONSE_MESSAGE:
            return None
        name = getattr(fn, "__name__", "Garmin call")
        if is_rate_limit(exc):
            raise GarminFetchError(f"{name} failed.\n{rate_limit_message(start_cooldown(exc))}") from exc
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


def _chain(exc: BaseException | None):
    """The exception, then whatever caused it, then whatever caused that."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def is_rate_limit(exc: BaseException) -> bool:
    """True if Garmin rate-limited the call, anywhere in the exception chain.

    Checked by type, never by message: garminconnect's own 429 on login reads
    "Too many login attempts. Please wait...", which a match on "429" or "too
    many requests" misses. And it wraps errors, so a 429 can arrive as the
    __cause__ of an authentication error.
    """
    return any(
        isinstance(e, GarminConnectTooManyRequestsError)
        or getattr(getattr(e, "response", None), "status_code", None) == 429
        for e in _chain(exc)
    )


def _retry_after(exc: BaseException | None) -> timedelta | None:
    """The wait Garmin asked for in a Retry-After header, if it gave one in seconds."""
    for e in _chain(exc):
        headers = getattr(getattr(e, "response", None), "headers", None)
        value = headers.get("Retry-After") if hasattr(headers, "get") else None
        if value is not None and str(value).strip().isdigit():
            return timedelta(seconds=int(str(value).strip()))
    return None


def _format_until(until: datetime) -> str:
    local = until.astimezone()
    minutes = max(1, round((until - datetime.now(UTC)).total_seconds() / 60))
    return f"{local:%Y-%m-%d %H:%M %Z} (about {minutes} min from now)"


def cooldown_until() -> datetime | None:
    """When the current rate-limit cooldown ends, or None if there is none.

    A cooldown that has passed, or a file that cannot be read, is removed so it
    never blocks anything again.
    """
    path = Path(COOLDOWN_FILE)
    try:
        until = datetime.fromisoformat(path.read_text().strip())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    if until <= datetime.now(UTC):
        path.unlink(missing_ok=True)
        return None
    return until


def start_cooldown(exc: BaseException | None = None) -> datetime:
    """Record a 429: no script calls Garmin again until the returned time."""
    until = datetime.now(UTC) + (_retry_after(exc) or DEFAULT_COOLDOWN)
    existing = cooldown_until()
    if existing and existing > until:
        return existing
    path = Path(COOLDOWN_FILE)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(until.isoformat() + "\n")
    return until


def rate_limit_message(until: datetime) -> str:
    return (
        "Garmin is rate-limiting this IP (HTTP 429).\n"
        f"No script will call Garmin again until {_format_until(until)}.\n"
        "Wait until then. Do not log in again: that extends the block."
    )


def check_cooldown() -> None:
    """Refuse to go near Garmin while a rate-limit cooldown is running.

    Raises:
        GarminRateLimitedError: a cooldown is running. The message says until when.
    """
    until = cooldown_until()
    if until is not None:
        raise GarminRateLimitedError(rate_limit_message(until))


def pause_between_days() -> None:
    """Wait before the next day of a multi-day query, then check it may go ahead.

    A cooldown can start part-way through a run: this run's own 429 has
    already stopped it, but another script can hit one while this one waits.

    Raises:
        GarminFetchError: a cooldown is running. The next day is not fetched.
    """
    time.sleep(DAY_PAUSE_SECONDS)
    until = cooldown_until()
    if until is not None:
        raise GarminFetchError(rate_limit_message(until))


def describe_auth_failure(token_dir: str, exc: Exception) -> str:
    """Build an actionable message explaining why a session could not be resumed.

    Deliberately does NOT suggest re-login on a 429: a fresh SSO login while
    rate-limited extends the block rather than clearing it. A 429 also starts
    the cooldown, so the next script waits instead of knocking again.
    """
    if is_rate_limit(exc):
        return rate_limit_message(start_cooldown(exc))

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
    """Load the account email and settings from config.json.

    There is no password in it. garmin_login.py asks for the password when it
    logs in and never saves it, and every other script resumes from tokens.

    Args:
        config_path: Path to config.json.

    Returns:
        Dict with 'email', 'units' and any other settings.

    Raises:
        GarminConfigError: If file missing, not valid JSON, or has no email.
    """
    if config_path == DEFAULT_CONFIG_PATH:
        migrate_legacy_settings()
    path = Path(config_path)
    if not path.exists():
        raise GarminConfigError(f"Config file not found: {config_path}\nRun setup.sh to configure credentials.")

    try:
        with open(path) as f:
            config = json.load(f)
    except ValueError as exc:
        raise GarminConfigError(f"{config_path} is not valid JSON ({exc}). Run setup.sh to rewrite it.") from exc

    if not isinstance(config, dict) or not config.get("email"):
        raise GarminConfigError(f"Missing 'email' in {config_path}. Run setup.sh to reconfigure.")

    # Default preferences
    config.setdefault("units", "imperial")

    return config


def save_config(config: dict, config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """Write config.json at 600, with any password left out.

    The file is created at 600 before a byte goes into it, then renamed over
    the old one. So it is never readable by anyone else, not even for a
    moment, and never half written. json.dumps does the quoting, so an email
    with a quote or a backslash in it cannot break the file.
    """
    settings = {key: value for key, value in config.items() if key != "password"}
    data = (json.dumps(settings, indent=2) + "\n").encode()

    path = Path(config_path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        tmp.unlink(missing_ok=True)
        raise
    os.close(fd)
    os.replace(tmp, path)


def update_config(config_path: str = DEFAULT_CONFIG_PATH, **settings) -> dict:
    """Rewrite config.json with these settings changed and no password in it.

    Earlier versions stored the Garmin password here. Any rewrite drops it,
    and one with no settings does nothing else.

    Raises:
        GarminConfigError: the existing file cannot be read and no email was
            given to start a new one.
    """
    path = Path(config_path)
    config = {}
    if path.exists():
        try:
            config = json.loads(path.read_text())
        except ValueError:
            config = None
        if not isinstance(config, dict):
            if "email" not in settings:
                raise GarminConfigError(
                    f"{config_path} is not valid settings JSON. Run setup.sh and enter the email again."
                )
            config = {}
    config.update(settings)
    save_config(config, config_path)
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
        GarminRateLimitedError: A rate-limit cooldown is running. Garmin is not
            called at all.
        GarminAuthError: If the session cannot be resumed. The message names the
            actual cause (no tokens / old token format / rate limited).
    """
    check_cooldown()
    token_path = Path(token_dir)

    try:
        garmin = Garmin()
        garmin.login(str(token_path))
    except Exception as exc:
        error = GarminRateLimitedError if is_rate_limit(exc) else GarminAuthError
        raise error(describe_auth_failure(str(token_path), exc)) from exc

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
