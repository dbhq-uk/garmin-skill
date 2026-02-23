# Garmin Skill Manual Setup

## Prerequisites

- Python 3.10+
- A Garmin Connect account (same one used in the Garmin Connect app)

## Steps

### 1. Create the virtual environment

```bash
cd ~/.claude/skills/garmin
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 2. Configure credentials

```bash
mkdir -p ~/.garmin
chmod 700 ~/.garmin
cat > ~/.garmin/config.json << 'EOF'
{
  "email": "your-garmin-email@example.com",
  "password": "your-garmin-password"
}
EOF
chmod 600 ~/.garmin/config.json
```

### 3. Test authentication

```bash
.venv/bin/python scripts/garmin_client.py
```

This should print your name from Garmin Connect. On first login, you may be prompted for an MFA code.

### 4. Create the symlink (if not already done)

```bash
ln -sf /path/to/claude-skills/garmin ~/.claude/skills/garmin
```

## Token Storage

After first successful login, OAuth tokens are cached at `~/.garmin/tokens/`. These are valid for approximately one year. If authentication starts failing, delete the tokens directory and re-authenticate:

```bash
rm -rf ~/.garmin/tokens
.venv/bin/python scripts/garmin_client.py
```

## Troubleshooting

### "Config file not found"
Run `scripts/setup.sh` or create `~/.garmin/config.json` manually.

### "Authentication failed"
1. Check your email/password in `~/.garmin/config.json`
2. Try logging into Garmin Connect in a browser to verify credentials
3. Delete `~/.garmin/tokens/` and try again

### MFA prompt
Garmin may require MFA on first login. Enter the code when prompted. Subsequent logins use cached tokens.
