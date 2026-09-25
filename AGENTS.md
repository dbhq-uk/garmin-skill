# AGENTS.md

Guidance for AI agents (and people) working in this repository.

## What this is

The **garmin** skill for AI coding agents - Garmin Connect health, sleep, activity and training data, live or archived to markdown. It follows the [Agent Skills](https://agentskills.io) layout (`skills/<name>/SKILL.md`) and ships as a [Claude Code plugin](https://code.claude.com/docs/en/plugins).

## Layout

```
.claude-plugin/plugin.json          # plugin manifest
skills/garmin/SKILL.md              # the skill (agent-facing instructions)
skills/garmin/scripts/              # the CLI scripts and setup.sh
skills/garmin/tests/                # pytest suite, no network
skills/garmin/references/setup.md   # manual setup, for when setup.sh fails part-way
skills/garmin/requirements.txt      # garminconnect, pytest
install.sh / install-codex.sh       # local symlink installers (Claude / Codex)
```

The venv lives at `skills/garmin/.venv`, built by `scripts/setup.sh` and gitignored. It is inside the skill directory on purpose: `${CLAUDE_SKILL_DIR}/.venv/bin/python` is then correct under a personal install, a Codex install and a plugin install without a lookup table.

## The three constraints that must not be broken

Everything else here is a preference. These are not.

**1. Every call is a read.** The skill fetches from Garmin and never writes to it. There is no code path that creates, edits or deletes anything in a user's Garmin account, and adding one is not a feature request to weigh up - a health record the user did not enter themselves is worse than no record, and the moment this skill can write, every user has to audit it before trusting it with credentials. If the API grows a tempting setter, do not call it.

**2. "No data" is not "the fetch failed".** `GarminFetchError` means the call failed and the caller must abort rather than write. A `None` return means Garmin genuinely has nothing for that day, and the file still writes with "No data" in the section. Collapsing the two is a one-line change that quietly fills an archive with empty days indistinguishable from days the user did not wear the watch. The distinction is load-bearing; keep it.

**3. Credentials stay on the machine, and stay owner-only.** `~/.dbhq/garmin` is created at 700 and `config.json` written at 600, before anything is written into them. The password is never stored: `garmin_login.py` asks for it, hands it to Garmin and forgets it, so `config.json` holds only the email and settings. Nothing is transmitted anywhere but Garmin. Do not add telemetry, do not add an aggregation service, and do not relax those modes because a test was easier without them.

## Conventions

- Any path a `SKILL.md` names must use `${CLAUDE_SKILL_DIR}` (the skill's own directory), which Claude Code substitutes for personal, project and plugin installs alike. `install.sh` therefore symlinks the whole skill directory into `~/.claude/skills/` with no rewrite. `install-codex.sh` rewrites the variable, since Codex does not substitute it. **Never hardcode an install path** - it is wrong under a Codex install and wrong under a plugin install, and CI fails on it. Python that needs its own location derives it from `__file__` rather than naming a directory, which is what `RELOGIN_COMMAND` in `garmin_client.py` does.
- Shell scripts use `set -e`; errors go to stderr, output to stdout.
- No secrets in the repo, and no fixture that looks like one.
- House style: British English, plain hyphens, no em dashes. CI enforces the last one.

## The upstream API is undocumented, and that shapes the tests

Garmin Connect has no public API, no versioning and no deprecation notices. `garminconnect` tracks it by reverse engineering, and things get renamed underneath it. Its 0.3 release dropped `garth` altogether and changed the token format, and this skill went on writing garth tokens nothing could read.

This is why `tests/test_garmin_api_contract.py` imports the **real** `garminconnect` rather than a mock. A `MagicMock` invents whatever attribute it is asked for, so a mocked suite stays green through an upstream rename - which is exactly how an auth-surface change (`.garth` -> `.client`) went unnoticed for months. That test constructs `Garmin()` and inspects its actual attributes. It still makes no network call: the login assertion fails on the missing tokenstore before any request is built.

Do not "fix" that test by mocking it. It is the only thing in the suite that can see the failure it exists to catch.

## Validating a change

```bash
bash -n install.sh install-codex.sh
shellcheck ./install.sh ./install-codex.sh ./skills/*/scripts/*.sh
ruff check . && ruff format --check .
cd skills/garmin && .venv/bin/python -m pytest tests/ -v
claude plugin validate .
```

CI runs all of that, on Python 3.12 and 3.13, plus both installers end to end.

What none of it covers is whether the data is **right**. The suite mocks Garmin's responses, so it proves the parsing and the formatting, not that the field you read is the field Garmin means. After changing a fetch or a formatter, run it against a real account and check one day's figures against the Garmin Connect app by eye. Nothing asserts that, and a plausible-looking wrong number is the failure this skill can actually ship.
