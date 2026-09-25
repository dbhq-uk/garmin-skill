# Security

## Reporting a vulnerability

Email <dan@dbhq.uk> rather than opening a public issue. Include what you found,
how to reproduce it, and what an attacker could do with it. You will get a first
response within 48 hours.

## What this skill does

It reads health data from Garmin Connect and, optionally, writes it to markdown
files you nominate. The sections below are the complete account of what it
touches.

### Network

**Garmin, and nothing else.** `garminconnect` talks to Garmin's servers to
authenticate and to fetch. There is no DBHQ endpoint, no telemetry,
no analytics, and no third-party service in the path. Run it with the network
off and it fails to reach Garmin and does nothing else.

Every call is a **read**. The skill has no code path that creates, edits or
deletes anything in your Garmin account.

### Credentials

- **Your password is never stored.** `garmin_login.py` asks for it at a prompt
  that does not echo, or reads it from the `GARMIN_PASSWORD` environment
  variable, hands it to Garmin for that one login, and forgets it. It is never
  written to disk, logged or printed. If an earlier version saved it in
  `config.json`, the next run of `setup.sh` or `garmin_login.py` removes it
- `~/.dbhq/garmin/config.json` holds your Garmin Connect email and settings. It
  is created at mode **600** before anything is written into it, in a directory
  at mode **700**, and replaced whole by a rename, so it is never readable by
  anyone else or half written
- `~/.dbhq/garmin/tokens/garmin_tokens.json` holds the tokens Garmin issues
  after login, written by `garminconnect` at mode **600** in a directory at
  mode **700**. They are what the skill uses day to day, and `garminconnect`
  refreshes them as they are used. Anyone who can read this file can read your
  Garmin data until the tokens expire, which is why it is owner-only
- Nothing is written to the repository

Garmin Connect has no API-key or personal-access-token concept, so a username
and password is the only way to get tokens. Delete `~/.dbhq/garmin/tokens/` to
sign this machine out and force a fresh login; delete `~/.dbhq/garmin/` to
remove everything the skill keeps.

### On disk

- Installs into `~/.claude/skills/garmin` or `~/.codex/skills/garmin`, depending
  on the agent
- Builds a virtualenv at `skills/garmin/.venv`
- Writes markdown only where you point `--output-dir`
- After Garmin answers 429, writes `~/.dbhq/garmin/ratelimited_until` (mode
  **600**): one timestamp, before which no script calls Garmin. It is removed
  once that time has passed
- Writes no cache and no log beyond that

### Third-party code

Two pinned dependencies:
[`garminconnect`](https://github.com/cyberjunky/python-garminconnect) and
`pytest`. Dependabot keeps them
current. Garmin Connect is an undocumented, unversioned API, so these libraries
change more often than most - which is a maintenance fact rather than a security
one, but it is why the pins move.

## Standing position on scanner findings

Automated skill scanners flag the sentences above that name
`~/.dbhq/garmin/config.json` and the token file as "sensitive file access". That is accurate
documentation, not a defect, and the remediation such scanners advise -
owner-only permissions - is already implemented.

**We do not delete accurate documentation to clear a scanner finding.** A
credential store you cannot find is harder to audit, not safer.

Encrypted or keyring-backed storage was considered and declined: a `chmod 600`
dotfile is what `gh`, `aws`, `docker` and `kubectl` all do, and the
cross-platform cost is not worth the modest gain.
