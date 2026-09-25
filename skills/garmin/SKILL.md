---
name: garmin
description: Use for Garmin health and fitness data - body battery, sleep, VO2 max, training load, heart rate, HRV, stress, activities. Trigger on phrases like "garmin", "body battery", "sleep score", "vo2 max", "training load", "fitness data", "pull garmin", "garmin snapshot".
---

# Garmin Health & Fitness

Query Garmin Connect for health metrics, sleep data, activities, and training status. Supports live queries and periodic markdown imports.

## Prerequisites

- Python virtual environment set up (run setup.sh if not done)
- Garmin Connect credentials configured

### First-Time Setup

```bash
${CLAUDE_SKILL_DIR}/scripts/setup.sh
```

## Log In

The query scripts only resume a saved session. They never log in. If one says "Not authenticated" or "Old token format", ask the user to run this once in their own terminal:

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_login.py
```

Do not run it yourself. It needs a terminal and refuses without one, because Garmin may send an MFA code by email or text that the user types at the prompt. If a script says Garmin is rate-limiting, wait: logging in again extends the block.

## On-Demand Queries

### Today's Vitals

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_health.py today
```

Returns: Resting HR, HRV, Body Battery, stress, steps, calories.

### Health for a Specific Date

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_health.py 2026-02-22
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_health.py yesterday
```

### Weekly Vitals Summary

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_health.py week
```

Returns: 7-day table of all vitals with averages.

### Sleep Data

```bash
# Last night
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_sleep.py

# Specific date
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_sleep.py 2026-02-22
```

Returns: Sleep score, duration, deep/light/REM/awake breakdown.

### Recent Activities

```bash
# Last 7 days
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_activities.py 7

# Last 30 days
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_activities.py 30
```

Returns: Activity list with HR, calories, training effect.

### Training Status

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_activities.py training
```

Returns: VO2 max, training load, training readiness, training status.

## Periodic Imports

### Daily Snapshot

Pulls all data for a day and writes to a markdown file:

```bash
# Today (output dir is required)
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_snapshot.py --output-dir /path/to/health/garmin

# Specific date
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_snapshot.py --output-dir /path/to/health/garmin 2026-02-22

# Yesterday
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_snapshot.py --output-dir /path/to/health/garmin yesterday
```

Output: `<output-dir>/YYYY-MM-DD.md`

### Weekly Rollup

Aggregates a week of data into a weekly summary markdown file:

```bash
# Current week
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_rollup.py --output-dir /path/to/health/garmin/weekly

# Last week
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_rollup.py --output-dir /path/to/health/garmin/weekly last

# Specific week
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_rollup.py --output-dir /path/to/health/garmin/weekly 2026-W08
```

Output: `<output-dir>/YYYY-WXX.md`

## Workflows

### Daily Review

1. Run snapshot to capture today's data
2. Reference key metrics in the daily review
3. Note any anomalies or patterns

### Weekly Review

1. Run rollup for the week
2. Compare trends against previous weeks
3. Cross-reference with other health data
4. Add context notes to the rollup file

### Quick Health Check

Ask: "What's my body battery?", "How did I sleep?", "Show my training status"
Claude runs the relevant on-demand query and returns formatted results.

## Error Handling

- **Auth expired:** Auto-refreshes using stored credentials
- **Wrong credentials:** Clear error, suggests re-running setup.sh
- **No data for date:** Sections show "No data" rather than failing
- **Garmin service down:** 30s timeout with clear error
- **MFA required:** Interactive prompt (first login only)

## Test Auth

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_client.py
```
