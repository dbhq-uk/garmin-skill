# Developer setup - garmin

Set the skill up from source with a **live symlink install**, so your edits are active immediately in Claude Code (and Codex). End users do not need this - they install with `npx skills add dbhq-uk/garmin-skill` or by cloning and running `./install.sh`.

## Prerequisites

- **Python 3.12+.** The floor is `garminconnect`'s: 0.3.x declares `Requires-Python >=3.12`, so pip cannot resolve the pin below it
- `git` (and the GitHub CLI `gh` if you will push changes)
- A Garmin Connect account, to run the skill. Not needed to run the tests

## 1. Clone

```bash
git clone https://github.com/dbhq-uk/garmin-skill.git ~/dbhq-garmin
cd ~/dbhq-garmin
```

## 2. Install (symlink)

```bash
./install.sh          # Claude Code: symlinks into ~/.claude/skills (edits are live)
./install-codex.sh    # Codex: installs into ~/.codex/skills
```

Any path the skill names uses `${CLAUDE_SKILL_DIR}` (the skill's own directory), which Claude Code substitutes for personal, project and plugin installs alike. So `install.sh` symlinks the **whole skill directory** into `~/.claude/skills/` - `SKILL.md`, `scripts/` and `references/` are all live, and every edit takes effect with no re-run. Codex does not substitute `${CLAUDE_SKILL_DIR}`, so `install-codex.sh` rewrites it to the install path - **re-run `./install-codex.sh` after editing a `SKILL.md`** for Codex.

Both installers build the virtualenv at `skills/garmin/.venv` and then run `scripts/setup.sh`, which asks for your Garmin email and password and does a test login. MFA is prompted for on first login only.

The venv is inside the skill directory rather than somewhere shared, and that is deliberate: `${CLAUDE_SKILL_DIR}/.venv/bin/python` is then the right interpreter under every install shape without a lookup.

## 3. Verify

In Claude Code, ask *"what's my body battery?"* - a working install answers with today's figure.

From the shell:

```bash
cd ~/dbhq-garmin/skills/garmin
.venv/bin/python scripts/garmin_client.py   # prints your name from Garmin Connect
.venv/bin/python -m pytest tests/ -v        # 58 tests, no network
```

## 4. Check the numbers by hand

This is the step that matters and the one nothing automates.

The test suite mocks Garmin's responses, so it proves the parsing and the formatting - **not** that the field you read is the field Garmin means. The API is undocumented, the shapes are inconsistent (VO2 max arrives nested, training readiness arrives as a list), and a plausible-looking wrong number passes every check in this repo.

After changing a fetch or a formatter, run one real day and compare it against the Garmin Connect app by eye:

```bash
.venv/bin/python scripts/garmin_health.py today
.venv/bin/python scripts/garmin_sleep.py
```

## When authentication starts failing

Tokens last roughly a year, and rate limits look like auth failures.

```bash
.venv/bin/python scripts/garmin_login.py           # re-login, MFA supported
.venv/bin/python scripts/garmin_login.py 123456    # or pass the MFA code
rm -rf ~/.dbhq/garmin/tokens                            # nuclear option, forces a fresh login
```

## Where the content lives

| File | Contents |
|---|---|
| `skills/garmin/SKILL.md` | What the agent reads: every command, and when to run it |
| `skills/garmin/scripts/garmin_client.py` | Auth, token handling, the shared client |
| `skills/garmin/scripts/garmin_health.py` | Daily and weekly vitals |
| `skills/garmin/scripts/garmin_sleep.py` | Sleep score and stage breakdown |
| `skills/garmin/scripts/garmin_activities.py` | Activities, and training status |
| `skills/garmin/scripts/garmin_snapshot.py` | A day, as a markdown file |
| `skills/garmin/scripts/garmin_rollup.py` | A week, aggregated |
| `skills/garmin/references/setup.md` | Manual setup, for when `setup.sh` fails part-way |

Adding a metric means adding the fetch, the formatter, a test with a **real captured response**, and a test for the day Garmin has nothing. See [`CONTRIBUTING.md`](../CONTRIBUTING.md) for why the second one is not optional.

## Working across machines

Editing anything under `~/dbhq-garmin` is live immediately in Claude Code - the skill directory is symlinked whole. For Codex, re-run `./install-codex.sh` after a `SKILL.md` edit. If you develop on more than one machine, `git pull` before you start and `git push` when done. The venv and your credentials are local to each machine and are not in the repository.
