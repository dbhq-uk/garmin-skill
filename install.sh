#!/bin/bash
# Install the garmin skill into ~/.claude/skills/ as a live symlink install.
#
# SKILL.md references scripts via ${CLAUDE_SKILL_DIR}, which Claude Code
# substitutes to the skill's own directory for personal, project, and plugin
# installs alike. So this script symlinks the whole skill directory into
# ~/.claude/skills/ - every edit (scripts AND SKILL.md) is immediately live,
# with no per-file rewrite. Re-run only when you add a new skill directory.
#
# The venv is deliberately built INSIDE the skill directory rather than in a
# shared location: ${CLAUDE_SKILL_DIR}/.venv/bin/python is then correct under a
# personal install, a Codex install and a plugin install without a lookup.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$HOME/.claude/skills"

echo "=== garmin skill installer (Claude Code) ==="
echo

# --- Dependencies ---
# 3.12 is the floor, and it is the dependency's rather than ours: garminconnect
# 0.3.x declares Requires-Python >=3.12, so pip cannot resolve the pin in
# requirements.txt below it. Checked here so the failure is one clear line
# rather than forty lines of pip resolver output later.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Missing required dependency: python3"
  echo "  macOS:  brew install python@3.12"
  echo "  Ubuntu: sudo apt install python3 python3-venv"
  exit 1
fi
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"; then
  echo "Error: Python 3.12+ required, found $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  echo "  garminconnect 0.3.x does not support older versions."
  exit 1
fi
echo "Dependencies OK."
echo

# --- Install each skill in this repo as a full-directory symlink ---
mkdir -p "$SKILLS_ROOT"
for src in "$SCRIPT_DIR"/skills/*/; do
  src="${src%/}"
  name="$(basename "$src")"
  target="$SKILLS_ROOT/$name"
  echo "Installing '$name' -> $target"
  rm -rf "$target"            # replace any prior copy or partial-symlink install
  ln -sfn "$src" "$target"    # whole-directory symlink; ${CLAUDE_SKILL_DIR} resolves it
  chmod +x "$src"/scripts/*.sh 2>/dev/null || true
done

echo
echo "Installed as directory symlinks - all edits (scripts and SKILL.md) are live. Re-run only when adding a new skill."
echo

# --- Setup: venv + credentials ---
# Two things have to exist before the skill works, and they fail independently:
# the venv, and the credentials. Keying this on credentials alone was the
# obvious version and the wrong one - reinstalling on a machine that already had
# ~/.garmin/config.json skipped setup entirely and left no venv, so every
# command failed on a missing interpreter with nothing pointing at why.
#
# setup.sh builds the venv first and handles credentials second, so running it
# is safe in either case. A non-interactive shell (CI, a piped install) drops out
# at the credential prompt with the venv already built, which is the half that
# cannot be filled in later by hand.
if [ -d "$SKILLS_ROOT/garmin/.venv" ] && [ -f "$HOME/.garmin/config.json" ]; then
  echo "Already set up. Re-run setup any time with:"
  echo "  $SKILLS_ROOT/garmin/scripts/setup.sh"
else
  echo "Running setup..."
  echo
  "$SKILLS_ROOT/garmin/scripts/setup.sh" || echo "Setup incomplete; run scripts/setup.sh when ready."
fi

echo
echo "Done. Try: 'what's my body battery?' or 'how did I sleep?'"
