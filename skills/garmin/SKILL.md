---
name: garmin
description: Use for Garmin health and fitness data - body battery, sleep, VO2 max, training load, heart rate, HRV, stress, activities. Trigger on phrases like "garmin", "body battery", "sleep score", "vo2 max", "training load", "fitness data", "pull garmin", "garmin snapshot".
---

# Garmin Health & Fitness

Reads the user's Garmin Connect data - vitals, sleep, activities, training status - live, or archived to markdown.

## When not to use

- Anything that writes to Garmin: logging an activity, editing a workout, changing a setting. Every script only reads.
- Medical questions. See "Reading the numbers".

## Commands

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_health.py today       # or yesterday, YYYY-MM-DD, week
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_sleep.py              # last night; or yesterday, YYYY-MM-DD
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_activities.py 7       # activities, last N days
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_activities.py training
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_snapshot.py --output-dir DIR 2026-02-22
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_rollup.py --output-dir DIR 2026-W08
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_client.py             # check the saved session
```

- `health`: resting HR, HRV, Body Battery (the day's lowest to highest level, and the latest), stress, steps, calories. `week` is a 7-day table. It fetches a day at a time with a short pause, so it takes several seconds.
- `training`: VO2 max, training load, readiness, status.
- `snapshot` writes a day to `DIR/YYYY-MM-DD.md` (default today). `rollup` writes an ISO week to `DIR/YYYY-Www.md` (default this week; `last` works). Days after today are left empty and not fetched.

"No data" in a row means Garmin has nothing for that day. It is not an error.

## Settings

`~/.dbhq/garmin/config.json` holds the account email and one preference, `"units"`: `"imperial"` (default, miles) or `"metric"` (km). It changes activity distances only. No password is stored: the login asks for it.

## When a script fails

The scripts only resume a saved session. None of them logs in. Match the message:

| Message | What to do |
|---|---|
| `Config file not found` | Ask the user to run `${CLAUDE_SKILL_DIR}/scripts/setup.sh` in their own terminal |
| `Not authenticated`, `Old token format` or `Could not resume Garmin session` | Ask the user to log in, below |
| `rate-limiting`, with a time | Wait until that time. Do not log in or retry: every script refuses until then, and another attempt extends the block |
| `Garmin refused the login` | Wrong password: the user logs in again. Wrong email: the user reruns `setup.sh` |
| `Error: ... failed` | The call failed. Snapshot and rollup wrote nothing. Say it failed, never "No data" |

The login, for the user to run in their own terminal. Do not run it yourself: it needs a terminal, and asks for an MFA code if Garmin sends one.

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_login.py
```

## Reading the numbers

- They are estimates from a wrist sensor. Body Battery, stress, sleep stages, training readiness and training status are Garmin's own models, not measurements.
- Use Garmin's names and labels as they come ("Body Battery", "Productive"). Do not invent a score or a scale.
- Compare against the user's own recent days (`garmin_health.py week`, earlier snapshots), not population norms.
- Never diagnose, or suggest a condition, from these numbers. If the user is worried by a reading, suggest they talk to a clinician.
