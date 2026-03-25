#!/usr/bin/env python3
"""
Garmin login with MFA support.

Uses garth's mobile API login flow with a browser-like User-Agent to
avoid Cloudflare rate limiting on the default mobile app UA.

Usage:
    python garmin_login.py              # Interactive MFA prompt
    python garmin_login.py 123456       # Pass MFA code as argument

Non-interactive MFA (used by Claude Code):
    Polls /tmp/garmin_mfa.txt for up to 5 minutes.
"""

import json
import os
import sys
import time
from pathlib import Path

from garth import http as garth_http
from garth import sso as garth_sso

CONFIG_PATH = os.path.expanduser("~/.garmin/config.json")
TOKEN_DIR = os.path.expanduser("~/.garmin/tokens")
MFA_FILE = "/tmp/garmin_mfa.txt"

# Use a browser UA to avoid Cloudflare rate-limiting garth's default
# mobile app User-Agent (GCM-iOS-5.22.1.4).
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _get_mfa_code(mfa_code_arg: str | None) -> str:
    if mfa_code_arg:
        return mfa_code_arg
    try:
        return input("Enter MFA code: ")
    except EOFError:
        pass
    mfa_path = Path(MFA_FILE)
    if mfa_path.exists():
        code = mfa_path.read_text().strip()
        mfa_path.unlink(missing_ok=True)
        if code:
            return code
    print(
        f"MFA required. Write the code to {MFA_FILE} "
        f"(waiting up to 300s)..."
    )
    deadline = time.time() + 300
    while time.time() < deadline:
        if mfa_path.exists():
            code = mfa_path.read_text().strip()
            mfa_path.unlink(missing_ok=True)
            if code:
                return code
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for MFA code in {MFA_FILE}")


def main():
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    email = config["email"]
    password = config["password"]

    token_path = Path(TOKEN_DIR)
    token_path.mkdir(parents=True, exist_ok=True)

    mfa_code_arg = sys.argv[1] if len(sys.argv) > 1 else None

    # Patch garth's SSO headers to use Chrome UA (bypasses Cloudflare
    # rate limits that block the default mobile app UA).
    garth_sso.SSO_PAGE_HEADERS["User-Agent"] = CHROME_UA

    client = garth_http.Client()
    client.sess.headers["User-Agent"] = CHROME_UA

    print(f"Logging in as {email}...")

    # Retry on 429 rate limits with backoff
    max_retries = 5
    for attempt in range(max_retries):
        try:
            result = garth_sso.login(
                email, password, client=client, return_on_mfa=True
            )
            break
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait = 30 * (attempt + 1)
                print(f"Rate limited, retrying in {wait}s...")
                time.sleep(wait)
                client = garth_http.Client()
                client.sess.headers["User-Agent"] = CHROME_UA
            else:
                raise

    if isinstance(result, tuple) and result[0] == "needs_mfa":
        print("MFA code sent to your email/phone.")
        mfa_code = _get_mfa_code(mfa_code_arg)
        print("Submitting MFA code...")
        oauth1, oauth2 = garth_sso.resume_login(result[1], mfa_code)
    else:
        oauth1, oauth2 = result

    # Save tokens
    client.configure(
        oauth1_token=oauth1,
        oauth2_token=oauth2,
        domain=oauth1.domain,
    )
    client.dump(str(token_path))

    # Verify
    from garminconnect import Garmin
    garmin = Garmin()
    garmin.garth.load(str(token_path))
    name = garmin.get_full_name()
    print(f"Authenticated as: {name}")
    print(f"Tokens saved to {TOKEN_DIR}")
    print("All garmin scripts should now work without MFA.")


if __name__ == "__main__":
    main()
