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

### 3. Save your email

Upgrading from an older install? Settings used to live at `~/.garmin`; the scripts move that directory to `~/.dbhq/garmin` automatically on first run.

`config.json` holds your Garmin email and settings, never your password. This
writes it with a JSON encoder, into a file created at 600:

```bash
.venv/bin/python -c 'import sys; sys.path.insert(0, "scripts"); from garmin_client import update_config; update_config(email=sys.argv[1])' 'your-garmin-email@example.com'
```

An older install may have saved a password in this file. The command above
removes it, and so does the next login.

### 4. Log in

Run this yourself, in a terminal. It asks for your Garmin password, or reads it
from `GARMIN_PASSWORD` if that is set, and does not save it. If your account
has multi-factor authentication, Garmin sends a code by email or text and the
script asks for it.

```bash
.venv/bin/python scripts/garmin_login.py
```

It prints your name from Garmin Connect when the login worked. To check the
saved session again later, without logging in:

```bash
.venv/bin/python scripts/garmin_client.py
```

To see what is set up without calling Garmin at all - the settings, whether
the tokens are there and readable and when they were last saved, and any
rate-limit cooldown - run:

```bash
.venv/bin/python scripts/garmin_status.py
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
1. Check the email in `~/.dbhq/garmin/config.json`
2. Try logging into Garmin Connect in a browser to check the password
3. Run `scripts/garmin_login.py` again and retype the password

### "No password entered"
The login needs your Garmin password each time it runs, because it is never
saved. Type it at the prompt, or set `GARMIN_PASSWORD` for that one command.

### "rate-limiting"
Garmin is blocking requests from your IP for a while. The message gives a time,
and every script, the login included, refuses to call Garmin before it. The
time is kept in `~/.dbhq/garmin/ratelimited_until` and the file goes once the
time has passed. Deleting it early lets the scripts try again sooner, and any
attempt while Garmin is still blocking extends the block.

### MFA prompt
If your account has multi-factor authentication, Garmin sends a code each time
you log in. Enter it at the prompt. The scripts then resume from the saved
tokens without asking again.
