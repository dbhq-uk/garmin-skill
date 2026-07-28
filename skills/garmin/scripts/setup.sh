#!/bin/bash
# Set up Garmin skill: credentials + Python venv
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$SKILL_DIR/.venv"
CONFIG_DIR="$HOME/.garmin"
CONFIG_FILE="$CONFIG_DIR/config.json"

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

# --- Credentials ---
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if [ -f "$CONFIG_FILE" ]; then
    echo ""
    echo "Existing credentials found at $CONFIG_FILE"
    read -r -p "Overwrite? (y/N): " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo "Keeping existing credentials."
        echo ""
        echo "=== Setup Complete ==="
        exit 0
    fi
fi

echo ""
echo "Enter your Garmin Connect credentials:"
read -r -p "Email: " email
read -r -s -p "Password: " password
echo ""

cat > "$CONFIG_FILE" <<CRED_EOF
{
  "email": "$email",
  "password": "$password"
}
CRED_EOF
chmod 600 "$CONFIG_FILE"
echo "Credentials saved to $CONFIG_FILE"

# --- Test login (supports MFA) ---
echo ""
echo "Testing authentication..."
if "$VENV_DIR/bin/python" "$SCRIPT_DIR/garmin_login.py"; then
    echo "Authentication successful!"
else
    echo "Authentication failed. Check your credentials and try again."
    exit 1
fi

echo ""
echo "=== Setup Complete ==="
echo "Virtual environment: $VENV_DIR"
echo "Credentials: $CONFIG_FILE"
echo "Tokens: $CONFIG_DIR/tokens/"
