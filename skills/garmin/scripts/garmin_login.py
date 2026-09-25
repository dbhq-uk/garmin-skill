#!/usr/bin/env python3
"""
Log in to Garmin Connect once, and save tokens the other scripts resume from.

Run it yourself, in your own terminal. It asks for your Garmin password, or
reads it from GARMIN_PASSWORD, hands it to Garmin and never saves it. If your
account has multi-factor authentication, Garmin sends a code by email or text
when the login starts, and this script asks for it at the prompt.

It uses garminconnect's own login and writes garminconnect's own token file,
garmin_tokens.json, at 600 inside a 700 directory. Every other script only
resumes from that file and never logs in.

Usage:
    python garmin_login.py
"""

import getpass
import os
import sys
from pathlib import Path

from garminconnect import Garmin
from garminconnect.exceptions import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

sys.path.insert(0, str(Path(__file__).parent))
from garmin_client import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_TOKEN_DIR,
    TOKEN_FILE,
    GarminConfigError,
    check_cooldown,
    get_client,
    is_rate_limit,
    load_config,
    rate_limit_message,
    remove_legacy_tokens,
    start_cooldown,
    update_config,
)

# Read instead of prompting when it is set, for a password manager's CLI.
PASSWORD_ENV = "GARMIN_PASSWORD"


def _ensure_private_dir(path: Path) -> None:
    """Create a directory at 700, and tighten it to 700 if it already exists.

    mkdir's mode is filtered by the umask and ignored for a directory that is
    already there, so the chmod is what actually guarantees owner-only.
    """
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _prompt_mfa_code() -> str:
    try:
        code = input("MFA code (sent by Garmin to your email or phone): ").strip()
    except EOFError:
        code = ""
    if not code:
        raise GarminConfigError("No MFA code entered. Run the login again when you have the code.")
    return code


def _read_password() -> str:
    """The Garmin password, from GARMIN_PASSWORD or a prompt that does not echo."""
    password = os.environ.get(PASSWORD_ENV)
    if not password:
        try:
            password = getpass.getpass("Garmin password (used for this login only, not saved): ")
        except EOFError:
            password = ""
    if not password:
        raise GarminConfigError("No password entered.")
    return password


def login(
    config_path: str = DEFAULT_CONFIG_PATH,
    token_dir: str = DEFAULT_TOKEN_DIR,
    password: str | None = None,
) -> str:
    """Log in, save the tokens, and prove they load. Returns the account's name.

    The password is used for this one login and never written anywhere. With
    none given, it comes from GARMIN_PASSWORD or a prompt.

    Raises:
        GarminConfigError: the config is unusable, a check failed, or the login
            was refused. The message says which.
    """
    # A login while Garmin is rate-limiting this IP extends the block, so the
    # cooldown is checked before anything else, and one attempt is all a run
    # gets: garminconnect already tries several login strategies per attempt.
    check_cooldown()

    config = load_config(config_path)
    email = config["email"]
    if "password" in config:
        # Saved there by an earlier version. It is not used, and it goes.
        update_config(config_path)
        print(f"Removed the saved password from {config_path}. It is no longer kept on disk.")
    if password is None:
        password = _read_password()

    token_path = Path(token_dir)
    _ensure_private_dir(token_path.parent)
    _ensure_private_dir(token_path)

    # garminconnect falls back to $GARMINTOKENS when login() gets no token
    # store. This script's job is a fresh login, never a resume from some other
    # tool's tokens, so that fallback is switched off here.
    os.environ.pop("GARMINTOKENS", None)

    print(f"Logging in as {email}...")
    garmin = Garmin(email, password, return_on_mfa=True)
    try:
        status, state = garmin.login()
        if status == "needs_mfa":
            garmin.resume_login(state, _prompt_mfa_code())
    except (
        GarminConnectTooManyRequestsError,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
    ) as exc:
        if is_rate_limit(exc):
            raise GarminConfigError(rate_limit_message(start_cooldown(exc))) from exc
        if isinstance(exc, GarminConnectAuthenticationError):
            raise GarminConfigError(f"Garmin refused the login: {exc}") from exc
        raise GarminConfigError(f"Could not reach Garmin to log in: {exc}") from exc

    try:
        garmin.client.dump(str(token_path))
    except ValueError as exc:
        # garminconnect refuses a token path with a symlink anywhere in it.
        raise GarminConfigError(f"Could not save the tokens: {exc}") from exc

    # The file just written has to be one the other scripts can load. Checked
    # offline, before anything else happens: garminconnect falls back to a
    # browser session when Garmin will not issue a mobile token, and that
    # session cannot be saved, so dump() writes a file with no tokens in it.
    try:
        Garmin().client.load(str(token_path))
    except GarminConnectConnectionError as exc:
        raise GarminConfigError(
            f"Logged in, but Garmin did not issue a token that can be saved ({exc}).\n"
            "Try again later. The other scripts cannot resume from this login."
        ) from exc

    for name in remove_legacy_tokens(str(token_path)):
        print(f"Removed old-format token file {name}")

    # Resume through exactly the path every other script uses.
    client = get_client(config, token_dir=str(token_path))
    return client.get_full_name() or email


def main() -> int:
    if not sys.stdin.isatty():
        print(
            "garmin_login.py needs a terminal: it may ask for an MFA code.\n"
            "Run it yourself, in your own terminal, not through an agent.",
            file=sys.stderr,
        )
        return 2
    try:
        name = login()
    except GarminConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Authenticated as: {name}")
    print(f"Tokens saved to {Path(DEFAULT_TOKEN_DIR) / TOKEN_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
