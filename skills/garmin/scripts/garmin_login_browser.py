#!/usr/bin/env python3
"""
Browser-based Garmin login using Playwright.

Uses a headless browser for the initial credential submission (bypasses
API rate limits), then hands off to garth's mobile API for MFA and
OAuth token exchange.

Usage:
    python garmin_login_browser.py          # Interactive MFA prompt
    python garmin_login_browser.py 123456   # Pass MFA code as argument

Non-interactive MFA:
    Polls /tmp/garmin_mfa.txt for up to 5 minutes.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from garth import http as garth_http
from garth.sso import (
    handle_mfa,
    get_oauth1_token,
    exchange,
    SSO_PAGE_HEADERS,
    _parse_sso_response,
    SSO_SUCCESSFUL,
    SSO_MFA_REQUIRED,
)

CONFIG_PATH = os.path.expanduser("~/.garmin/config.json")
TOKEN_DIR = os.path.expanduser("~/.garmin/tokens")
MFA_FILE = "/tmp/garmin_mfa.txt"

MOBILE_SERVICE = "https://mobile.integration.garmin.com/gcm/android"
CLIENT_ID = "GCM_ANDROID_DARK"

MOBILE_SIGNIN_URL = (
    "https://sso.garmin.com/mobile/sso/en/sign-in"
    f"?clientId={CLIENT_ID}"
    f"&service={MOBILE_SERVICE}"
)

LOGIN_PARAMS = {
    "clientId": CLIENT_ID,
    "locale": "en-US",
    "service": MOBILE_SERVICE,
}


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _relaunch_with_xvfb():
    xvfb = shutil.which("xvfb-run")
    if not xvfb:
        return
    print("No display found — relaunching under xvfb...")
    result = subprocess.run(
        [xvfb, "--auto-servernum", "--server-args=-screen 0 1280x720x24",
         sys.executable] + sys.argv,
        env={**os.environ, "GARMIN_XVFB_LAUNCHED": "1"},
    )
    sys.exit(result.returncode)


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
    print(f"MFA required. Write the code to {MFA_FILE} (waiting up to 300s)...")
    deadline = time.time() + 300
    while time.time() < deadline:
        if mfa_path.exists():
            code = mfa_path.read_text().strip()
            mfa_path.unlink(missing_ok=True)
            if code:
                return code
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for MFA code in {MFA_FILE}")


def browser_submit_credentials(email: str, password: str):
    """Use browser to submit credentials, return session cookies.

    This bypasses API rate limits by using the HTML form rather than
    the mobile API endpoint.
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    use_headed = _has_display()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not use_headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        stealth = Stealth()
        stealth.apply_stealth_sync(context)
        page = context.new_page()

        print("Opening Garmin SSO (mobile)...")
        page.goto(MOBILE_SIGNIN_URL, wait_until="networkidle")

        mobile_email = page.query_selector('input#email')
        if mobile_email:
            print("Entering credentials (mobile form)...")
            page.locator('input#email').click()
            page.locator('input#email').type(email, delay=30)
            page.locator('input#password').click()
            page.locator('input#password').type(password, delay=30)
            page.keyboard.press('Enter')
        else:
            raise RuntimeError("Could not find login form")

        # Wait for MFA page or ticket redirect
        print("Waiting for response...")
        try:
            page.wait_for_url(
                lambda url: "ticket=" in url or "/mfa" in url,
                timeout=15000,
            )
        except Exception:
            pass

        # Extract all cookies from the browser session
        import requests
        jar = requests.cookies.RequestsCookieJar()
        for c in context.cookies():
            jar.set(c["name"], c["value"], domain=c["domain"],
                    path=c.get("path", "/"))

        current_url = page.url
        browser.close()
        return jar, current_url


def main():
    if not _has_display() and not os.environ.get("GARMIN_XVFB_LAUNCHED"):
        _relaunch_with_xvfb()

    with open(CONFIG_PATH) as f:
        config = json.load(f)

    email = config["email"]
    password = config["password"]
    token_path = Path(TOKEN_DIR)
    token_path.mkdir(parents=True, exist_ok=True)
    mfa_code_arg = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"Logging in as {email} (browser mode)...")

    # Step 1: Browser submits credentials (bypasses rate limit)
    cookies, url_after_login = browser_submit_credentials(email, password)

    # Step 2: Transfer browser cookies to a garth client
    client = garth_http.Client()
    client.sess.cookies.update(cookies)

    # Step 3: Check if MFA is needed or we already have a ticket
    if "/mfa" in url_after_login:
        print("MFA code sent to your email/phone.")
        mfa_code = _get_mfa_code(mfa_code_arg)
        print("Submitting MFA code via API...")

        # Use garth's mobile API to verify MFA — this returns the
        # proper mobile service ticket (compatible with OAuth exchange)
        client.post(
            "sso",
            "/mobile/api/mfa/verifyCode",
            params=LOGIN_PARAMS,
            headers=SSO_PAGE_HEADERS,
            json={
                "mfaMethod": "email",
                "mfaVerificationCode": mfa_code,
                "rememberMyBrowser": False,
                "reconsentList": [],
                "mfaSetup": False,
            },
        )
        resp_json = _parse_sso_response(
            client.last_resp.json(), SSO_SUCCESSFUL
        )
        ticket = resp_json["serviceTicketId"]
    else:
        raise RuntimeError(
            f"Unexpected state after login: {url_after_login}"
        )

    # Step 4: Exchange ticket for OAuth tokens
    print("Exchanging ticket for OAuth tokens...")
    oauth1 = get_oauth1_token(ticket, client)
    oauth2 = exchange(oauth1, client, login=True)

    # Step 5: Save tokens
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
