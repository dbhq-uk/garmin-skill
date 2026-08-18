# Garmin Skill Manual Setup

`scripts/setup.sh` does all of this for you. This page is the fallback for when
it fails part-way, or when you would rather see each step than run one script.

## Prerequisites

- Python 3.12+. That floor comes from `garminconnect` 0.3.x, which declares
  `Requires-Python >=3.12`, so pip cannot resolve the pinned dependency below it
- A Garmin Connect account (the same one you use in the Garmin Connect app)

## Steps

### 1. Install the skill

```bash
git clone https://github.com/dbhq-uk/garmin-skill.git
cd garmin-skill
./install.sh          # Claude Code: symlinks the skill in, so edits are live
./install-codex.sh    # Codex: rewrites SKILL.md and links the rest
```

### 2. Create the virtual environment

The venv lives inside the skill directory, so the scripts find it wherever the
skill is installed.

```bash
cd skills/garmin
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 3. Configure credentials

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

### 4. Test authentication

```bash
.venv/bin/python scripts/garmin_client.py
```

This should print your name from Garmin Connect. On first login, you may be prompted for an MFA code.

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
