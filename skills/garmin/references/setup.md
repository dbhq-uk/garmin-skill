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

Upgrading from an older install? Settings used to live at `~/.garmin`; the scripts move that directory to `~/.dbhq/garmin` automatically on first run.

```bash
mkdir -p ~/.dbhq/garmin
chmod 700 ~/.dbhq ~/.dbhq/garmin
cat > ~/.dbhq/garmin/config.json << 'EOF'
{
  "email": "your-garmin-email@example.com",
  "password": "your-garmin-password"
}
EOF
chmod 600 ~/.dbhq/garmin/config.json
```

### 4. Log in

Run this yourself, in a terminal. If your account has multi-factor
authentication, Garmin sends a code by email or text and the script asks for it.

```bash
.venv/bin/python scripts/garmin_login.py
```

It prints your name from Garmin Connect when the login worked. To check the
saved session again later, without logging in:

```bash
.venv/bin/python scripts/garmin_client.py
```

## Token Storage

The login saves its tokens to `~/.dbhq/garmin/tokens/garmin_tokens.json`, at
mode 600 in a directory at mode 700. The other scripts only resume from that
file; none of them logs in. If they report "Not authenticated" or "Old token
format", run `scripts/garmin_login.py` again.

Tokens from before `garminconnect` 0.3 (`oauth1_token.json` and
`oauth2_token.json`) cannot be read any more. The next login deletes them.

## Troubleshooting

### "Config file not found"
Run `scripts/setup.sh` or create `~/.dbhq/garmin/config.json` manually.

### "Garmin refused the login"
1. Check your email/password in `~/.dbhq/garmin/config.json`
2. Try logging into Garmin Connect in a browser to verify credentials
3. Run `scripts/garmin_login.py` again

### "rate-limiting"
Garmin is blocking logins from your IP for a while. Wait before trying again:
another attempt extends the block.

### MFA prompt
If your account has multi-factor authentication, Garmin sends a code each time
you log in. Enter it at the prompt. The scripts then resume from the saved
tokens without asking again.
