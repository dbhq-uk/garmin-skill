<div align="center">

<img src="assets/logo.svg" alt="garmin skill for Claude Code, by DBHQ" width="420">

# garmin

**Your Garmin data, in the conversation you are already having**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude_Code-Plugin-blueviolet)](https://code.claude.com/docs/en/plugins)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey)]()

A free, open-source tool by [DBHQ](https://dbhq.uk)

</div>

---

Ask your agent how you slept and get an answer, rather than opening an app to read a number back to yourself. Body Battery, HRV, resting heart rate, stress, sleep stages, activities, VO2 max, training load, training status and training readiness - live, or archived to markdown you keep.

## What makes it different

**It answers and it archives.** Most integrations do one or the other. A live query returns today's vitals into the conversation; `garmin_snapshot.py` writes a whole day as a markdown file and `garmin_rollup.py` aggregates a week into a summary, both into a directory you name. Those files are yours, in plain text, and they outlive both this skill and your subscription.

**Your credentials never leave your machine.** They sit in `~/.dbhq/garmin/config.json` at mode 600, the OAuth tokens Garmin issues are cached in `~/.dbhq/garmin/tokens/`, and the only host anything is sent to is Garmin's. There is no DBHQ service in the middle, no telemetry, and nothing to sign up for.

**"No data" and "the call failed" are different things, and it treats them differently.** A day Garmin has nothing for renders as "No data" and the file still writes. A fetch that actually failed raises and aborts the write. That distinction sounds pedantic until the alternative bites you: an archive quietly full of empty days, indistinguishable from days you genuinely did not wear the watch.

**It is tested against the real client, not only a mock.** Garmin Connect has no public API and no versioning; the library that wraps it renames things when Garmin moves underneath it. Mocked tests cannot see that, because a `MagicMock` invents whatever attribute it is asked for - which is how an auth-surface rename went unnoticed for months. So one test imports the real `garminconnect` and inspects its actual surface. It still makes no network call.

## Install

### Any agent (Claude Code, Codex, Cursor, Copilot, Windsurf, Gemini, Cline and more)

```bash
npx skills add dbhq-uk/garmin-skill
```

The [skills.sh](https://skills.sh) CLI installs into whichever agent directories it finds.

### Local install (Claude Code or Codex)

```bash
git clone https://github.com/dbhq-uk/garmin-skill.git
cd garmin-skill
./install.sh          # Claude Code: symlinks into ~/.claude/skills (edits are live)
./install-codex.sh    # Codex: installs into ~/.codex/skills
```

[`install.sh`](install.sh) and [`install-codex.sh`](install-codex.sh) are the same install two ways: Claude Code substitutes `${CLAUDE_SKILL_DIR}` so the whole skill directory is symlinked untouched, while Codex does not, so its `SKILL.md` is rewritten at install time.

Either installer builds a virtualenv inside the skill directory and then runs setup, which asks for your Garmin Connect email and password once. MFA is supported and only needed on first login.

### Requirements

- **Python 3.12+.** That floor is `garminconnect`'s, not ours: version 0.3.x declares `Requires-Python >=3.12`, so pip cannot resolve the pinned dependency below it
- A Garmin Connect account - the same one you use in the app

Manual, step-by-step setup is in [`skills/garmin/references/setup.md`](skills/garmin/references/setup.md) for when the script fails part-way.

## Usage

Ask in any session.

```
"what's my body battery?"
"how did I sleep last night?"
"show my training status"
"garmin vitals for the week"
"what did I do in the last 30 days?"
"snapshot today to ./health/garmin"
```

| What you get | Command behind it |
|---|---|
| Resting HR, HRV, Body Battery, stress, steps, calories | `garmin_health.py today` / `yesterday` / a date |
| Seven-day table with averages | `garmin_health.py week` |
| Sleep score, duration, deep/light/REM/awake | `garmin_sleep.py` |
| Activities with HR, calories, training effect | `garmin_activities.py 7` |
| VO2 max, training load, readiness, status | `garmin_activities.py training` |
| A day as markdown | `garmin_snapshot.py --output-dir <dir>` |
| A week as markdown | `garmin_rollup.py --output-dir <dir>` |

The full command reference is in [`skills/garmin/SKILL.md`](skills/garmin/SKILL.md).

## What this will not do

**Write anything back to Garmin.** Every call is a read. The skill has no code path that creates, edits or deletes anything in your Garmin account, and it never will - a health record you did not enter yourself is worse than no record.

**Send your data anywhere but Garmin and you.** No analytics, no aggregation service, no "anonymised" upload. If you run it with the network off it fails to reach Garmin and does nothing else.

**Give you medical advice.** It reports what the watch measured. Garmin's own figures are estimates from a wrist optical sensor, and Body Battery, stress and sleep staging in particular are proprietary models rather than measurements. Treat them as trend lines, not diagnoses.

## Development

Want to hack on the skill or run it from source with live edits? See [`docs/dev-setup.md`](docs/dev-setup.md).

[`CONTRIBUTING.md`](CONTRIBUTING.md) covers working on it, and [`AGENTS.md`](AGENTS.md) is for an AI agent doing so. The skill itself is [`skills/garmin/SKILL.md`](skills/garmin/SKILL.md).

## Acknowledgements

Built on [`garminconnect`](https://github.com/cyberjunky/python-garminconnect) by cyberjunky and [`garth`](https://github.com/matin/garth) by Matin Tamizi, which do the genuinely hard part: keeping up with an API Garmin does not document.

## License

[MIT](LICENSE) © 2026 DBHQ Consulting Ltd
