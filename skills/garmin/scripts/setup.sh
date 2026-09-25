#!/bin/bash
# Set up Garmin skill: Python venv, settings, then one login
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$SKILL_DIR/.venv"
CONFIG_DIR="$HOME/.dbhq/garmin"
CONFIG_FILE="$CONFIG_DIR/config.json"

# One-time migration: settings used to live at ~/.garmin
if [ ! -e "$CONFIG_DIR" ] && [ -d "$HOME/.garmin" ]; then
    mkdir -p "$HOME/.dbhq"
    chmod 700 "$HOME/.dbhq"
    mv "$HOME/.garmin" "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"
fi

echo "=== Garmin Skill Setup ==="

# --- Python venv ---
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PYTHON_VERSION"

# garminconnect 0.3.x declares Requires-Python >=3.12, so pip cannot resolve the
# pin in requirements.txt below that. Stop here with the reason, rather than
# provisioning a venv and then failing inside pip's resolver output.
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"; then
    echo "Error: Python 3.12+ required, found $PYTHON_VERSION"
    echo "  garminconnect 0.3.x does not support older versions."
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists"
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SKILL_DIR/requirements.txt" -q

# --- Settings ---
# config.json holds the account email and settings, never the password: the
# login asks for that, hands it to Garmin and forgets it. The file is written by
# garmin_client.update_config, which quotes with a JSON encoder (so a quote or a
# backslash in the email cannot break it) and creates the file at 600 before
# writing a byte. It also drops a password an earlier version saved here.
mkdir -p "$CONFIG_DIR"
chmod 700 "$HOME/.dbhq" "$CONFIG_DIR"

update_config() {
    "$VENV_DIR/bin/python" - "$SCRIPT_DIR" "$CONFIG_FILE" "$@" <<'PY'
import sys

sys.path.insert(0, sys.argv[1])
from garmin_client import GarminConfigError, update_config

settings = {"email": sys.argv[3]} if len(sys.argv) > 3 else {}
try:
    update_config(sys.argv[2], **settings)
except GarminConfigError as exc:
    sys.exit(f"Error: {exc}")
PY
}

if [ -f "$CONFIG_FILE" ]; then
    echo ""
    echo "Existing settings found at $CONFIG_FILE"
    read -r -p "Change the Garmin email? (y/N): " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        update_config
        echo "Keeping existing settings. No password is stored."
        echo "To log in again, run:"
        echo "  $VENV_DIR/bin/python $SCRIPT_DIR/garmin_login.py"
        echo ""
        echo "=== Setup Complete ==="
        exit 0
    fi
fi

echo ""
read -r -p "Garmin Connect email: " email
update_config "$email"
echo "Settings saved to $CONFIG_FILE (no password: the login asks for it and does not save it)"

# --- Log in (asks for the password, and an MFA code if Garmin sends one) ---
echo ""
echo "Logging in..."
if "$VENV_DIR/bin/python" "$SCRIPT_DIR/garmin_login.py"; then
    echo "Authentication successful!"
else
    # garmin_login.py has already printed why. A wrong password, a rate limit
    # and a network failure each need something different, so the reason is
    # left to speak for itself rather than blamed on the credentials.
    echo "Login did not complete: see the error above." >&2
    echo "When it is sorted, log in with:" >&2
    echo "  $VENV_DIR/bin/python $SCRIPT_DIR/garmin_login.py" >&2
    exit 1
fi

echo ""
echo "=== Setup Complete ==="
echo "Virtual environment: $VENV_DIR"
echo "Settings: $CONFIG_FILE"
echo "Tokens: $CONFIG_DIR/tokens/"
