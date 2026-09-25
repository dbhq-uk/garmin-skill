#!/usr/bin/env python3
"""
Say whether the skill is ready to call Garmin, without calling Garmin.

Reads only local files: the settings, the saved tokens and the rate-limit
cooldown. It makes no network call, so it is safe to run at any time, a
cooldown included, and it is the first thing to run when a script fails and
the reason is not clear.

Usage:
    python garmin_status.py          # a short report; the last line says what to do
    python garmin_status.py --json   # the same, as JSON

Exit code 0 when the scripts can run, 1 when something has to happen first.
"""

import argparse
import json
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

from garminconnect import Garmin

sys.path.insert(0, str(Path(__file__).parent))
import garmin_client
from garmin_client import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_TOKEN_DIR,
    RELOGIN_COMMAND,
    TOKEN_FILE,
    GarminConfigError,
    cooldown_until,
    load_config,
    token_format,
)

SETUP_COMMAND = f"  {Path(__file__).resolve().parent}/setup.sh"


def _mode(path: Path) -> str | None:
    try:
        return oct(stat.S_IMODE(path.stat().st_mode))[2:]
    except OSError:
        return None


def _settings(config_path: str) -> dict:
    path = Path(config_path)
    report = {"path": str(path), "present": path.is_file(), "email": None, "units": None, "problem": None}
    report["mode"] = _mode(path)
    try:
        config = load_config(config_path)
    except GarminConfigError as exc:
        report["problem"] = str(exc).splitlines()[0]
        return report
    report["email"] = config.get("email")
    report["units"] = config.get("units")
    if "password" in config:
        report["problem"] = "a password is saved here by an earlier version; the next login removes it"
    return report


def _tokens(token_dir: str, now: datetime) -> dict:
    directory = Path(token_dir)
    token_file = directory / TOKEN_FILE
    report = {
        "path": str(token_file),
        "format": token_format(token_dir),
        "saved": None,
        "age_days": None,
        "directory_mode": _mode(directory),
        "file_mode": _mode(token_file),
    }
    if report["format"] == "current":
        # garminconnect's own reader, which is offline: it parses the file and
        # checks the tokens are there. A file it cannot read is as good as none.
        try:
            Garmin().client.load(str(directory))
        except Exception:
            report["format"] = "unreadable"
        saved = datetime.fromtimestamp(token_file.stat().st_mtime, UTC)
        report["saved"] = saved.isoformat(timespec="seconds")
        report["age_days"] = round((now - saved).total_seconds() / 86400, 1)
    return report


def status(config_path: str = DEFAULT_CONFIG_PATH, token_dir: str = DEFAULT_TOKEN_DIR) -> dict:
    """Everything the scripts need before they call Garmin, read from disk only."""
    now = datetime.now(UTC)
    settings = _settings(config_path)
    tokens = _tokens(token_dir, now)
    until = cooldown_until()

    warnings = []
    if settings["mode"] not in (None, "600"):
        warnings.append(f"{settings['path']} is {settings['mode']}, not 600: chmod 600 it")
    if tokens["directory_mode"] not in (None, "700"):
        warnings.append(f"{token_dir} is {tokens['directory_mode']}, not 700: chmod 700 it")
    if tokens["file_mode"] not in (None, "600"):
        warnings.append(f"{tokens['path']} is {tokens['file_mode']}, not 600: chmod 600 it")
    if settings["problem"] and settings["email"]:
        warnings.append(settings["problem"])

    if until is not None:
        ready, next_step = False, garmin_client.rate_limit_message(until)
    elif not settings["email"]:
        ready = False
        next_step = f"Settings: {settings['problem']}\nThe user runs setup, in their own terminal:\n{SETUP_COMMAND}"
    elif tokens["format"] == "missing":
        ready, next_step = False, f"Not logged in. The user logs in, in their own terminal:\n{RELOGIN_COMMAND}"
    elif tokens["format"] == "legacy":
        ready = False
        next_step = f"Old token format. The user logs in once, in their own terminal:\n{RELOGIN_COMMAND}"
    elif tokens["format"] == "unreadable":
        ready = False
        next_step = f"The token file cannot be read. The user logs in again, in their own terminal:\n{RELOGIN_COMMAND}"
    else:
        ready = True
        next_step = "Ready. garminconnect refreshes the tokens as they are used; Garmin can still end the session."

    return {
        "ready": ready,
        "settings": settings,
        "tokens": tokens,
        "cooldown_until": until.isoformat(timespec="seconds") if until else None,
        "warnings": warnings,
        "next_step": next_step,
    }


def format_status(report: dict) -> str:
    settings, tokens = report["settings"], report["tokens"]
    if tokens["age_days"] is not None:
        token_line = f"{tokens['format']}, last saved {tokens['saved']} ({tokens['age_days']} days ago)"
    else:
        token_line = tokens["format"]
    lines = [
        f"Settings: {settings['email'] or 'none'} ({settings['path']})",
        f"Units:    {settings['units'] or '-'}",
        f"Tokens:   {token_line}",
        f"Cooldown: {'until ' + report['cooldown_until'] if report['cooldown_until'] else 'none'}",
    ]
    lines += [f"Warning:  {w}" for w in report["warnings"]]
    lines += ["", report["next_step"]]
    return "\n".join(lines)


def main(
    argv: list[str] | None = None, config_path: str = DEFAULT_CONFIG_PATH, token_dir: str = DEFAULT_TOKEN_DIR
) -> int:
    parser = argparse.ArgumentParser(description="Garmin skill status, offline")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    report = status(config_path, token_dir)
    print(json.dumps(report, indent=2) if args.json else format_status(report))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
