#!/usr/bin/env python3
"""
Interactive Garmin login with MFA support.

Run this script directly in a terminal to complete MFA authentication.
Once tokens are cached, all other garmin scripts will work non-interactively.

Usage:
    python garmin_login.py          # Interactive MFA prompt
    python garmin_login.py 123456   # Pass MFA code as argument
"""

import json
import os
import sys
from pathlib import Path

from garminconnect import Garmin


CONFIG_PATH = os.path.expanduser("~/.garmin/config.json")
TOKEN_DIR = os.path.expanduser("~/.garmin/tokens")


def main():
    # Load credentials
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    email = config["email"]
    password = config["password"]

    token_path = Path(TOKEN_DIR)
    token_path.mkdir(parents=True, exist_ok=True)

    mfa_code = sys.argv[1] if len(sys.argv) > 1 else None

    if mfa_code:
        # Non-interactive: MFA code provided as argument
        def prompt_mfa():
            return mfa_code
    else:
        # Interactive: prompt user
        def prompt_mfa():
            return input("Enter MFA code from your authenticator app: ")

    print(f"Logging in as {email}...")

    garmin = Garmin(
        email=email,
        password=password,
        is_cn=False,
        prompt_mfa=prompt_mfa,
    )
    garmin.login()
    garmin.garth.dump(str(token_path))

    name = garmin.get_full_name()
    print(f"Authenticated as: {name}")
    print(f"Tokens saved to {TOKEN_DIR}")
    print("All garmin scripts should now work without MFA.")


if __name__ == "__main__":
    main()
