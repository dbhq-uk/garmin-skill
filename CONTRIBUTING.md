# Contributing

Thanks for your interest - contributions are welcome.

## Ways to help

- Report a bug or request a feature via [issues](https://github.com/dbhq-uk/garmin-skill/issues)
- Add a metric the API exposes and this does not, sharpen the markdown output, or improve the skill instructions via a pull request

## Local development

```bash
git clone https://github.com/dbhq-uk/garmin-skill.git
cd garmin-skill
./install.sh          # symlinks into ~/.claude/skills (edits are live)
```

The whole skill directory is symlinked, so edits - including to `SKILL.md`, the scripts and `references/` - are live immediately. For Codex, re-run `./install-codex.sh` after editing a `SKILL.md`, since that path is rewritten at install time. Full walkthrough in [`docs/dev-setup.md`](docs/dev-setup.md).

You need a real Garmin Connect account to run the skill, but not to run the tests: the suite mocks every response.

## Before opening a PR

- `ruff check . && ruff format --check .`
- `cd skills/garmin && .venv/bin/python -m pytest tests/ -v` - all green
- `shellcheck ./install.sh ./install-codex.sh ./skills/*/scripts/*.sh`
- `claude plugin validate .`
- Check one real day's figures against the Garmin Connect app by eye. Nothing automated can do this, and it is the failure that actually ships
- British English, plain hyphens, no trailing full stops on headings

## The bar for a new metric

Garmin's API exposes a great deal, and not all of it means what its field name suggests.

**A new metric needs a test with a real captured response.** Not a hand-written dict that matches what you expect - a payload you actually got back, trimmed. The shapes are inconsistent: VO2 max arrives nested, training readiness arrives as a list, and both were bugs before they were tests.

**It has to survive a day with no data.** Garmin returns `None`, `{}`, an empty list or a populated object with null fields depending on the endpoint and the day. Whichever it is, the snapshot must render "No data" and keep writing rather than raise. Add the empty case to the test alongside the populated one.

**Do not collapse a failed fetch into an absent value.** `GarminFetchError` must keep propagating. See `AGENTS.md` - this is the constraint most easily broken by a well-meant `try/except` around a new call.

## What we will not accept

**A write path.** This skill reads. No pull request that creates, edits or deletes anything in a user's Garmin account will be merged, however carefully guarded. If you want that, it belongs in a different tool with a different consent conversation.

**Anything that moves data off the machine.** No telemetry, no analytics, no "anonymous usage statistics", no optional sync to a third-party service. The whole trust argument for handing a skill your Garmin password is that the only host it talks to is Garmin's.

**Loosened file modes.** `~/.dbhq/garmin` is 700 and `config.json` is 600. If a test is awkward because of it, fix the test.

## Licence

By contributing you agree your work is licensed under the [MIT licence](LICENSE).
