# Garmin Health Skill

Pull health, fitness, and training data from Garmin Connect.

## Features

- **On-demand queries:** Body Battery, HRV, sleep, activities, training status
- **Daily snapshots:** Full day's data as a markdown file
- **Weekly rollups:** Aggregated trends and highlights

## Quick Start

```bash
# 1. Run setup (creates venv, installs deps, configures credentials)
${CLAUDE_SKILL_DIR}/scripts/setup.sh

# 2. Test auth
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_client.py

# 3. Try a query
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_health.py today
```

## Data Export

Daily snapshots and weekly rollups write markdown files to any directory you specify:

```bash
# Daily snapshot
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_snapshot.py --output-dir ./health/garmin

# Weekly rollup
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/scripts/garmin_rollup.py --output-dir ./health/garmin/weekly
```

See SKILL.md for full command reference.
