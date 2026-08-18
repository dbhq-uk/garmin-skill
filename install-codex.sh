#!/bin/bash
# Install the garmin skill into ~/.codex/skills/ for Codex.
#
# Codex does not substitute ${CLAUDE_SKILL_DIR}, so this script rewrites that
# variable to each skill's installed Codex path and symlinks the supporting
# directories (edits stay live). Re-run after editing a SKILL.md.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_ROOT="$HOME/.codex/skills"

echo "=== garmin skill installer (Codex) ==="
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "Missing required dependency: python3"
  exit 1
fi
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"; then
  echo "Error: Python 3.12+ required (garminconnect 0.3.x declares Requires-Python >=3.12)"
  exit 1
fi
echo "Dependencies OK."
echo

# --- Setup first, then link ---
# Order matters here and it is the one thing this script does differently from
# the prose-only skills in this org. The rewritten SKILL.md names
# <target>/.venv/bin/python, so the venv has to exist in the source tree before
# the link is made - link first and you get a dangling symlink, which fails more
# confusingly than a missing one because it looks installed.
if [ ! -d "$SCRIPT_DIR/skills/garmin/.venv" ]; then
  echo "No venv yet. Building it..."
  "$SCRIPT_DIR/skills/garmin/scripts/setup.sh" || echo "Setup incomplete; the venv is what matters here and is built first."
  echo
fi

mkdir -p "$SKILLS_ROOT"
for src in "$SCRIPT_DIR"/skills/*/; do
  src="${src%/}"
  name="$(basename "$src")"
  target="$SKILLS_ROOT/$name"
  echo "Installing '$name' -> $target"
  mkdir -p "$target"
  # Clear what a previous install left before linking what this one needs.
  # Without this, an entry that has since been renamed or deleted upstream
  # survives as a symlink to a path that no longer exists - and a dangling
  # link fails more confusingly than a missing file, because it looks
  # installed. Only symlinks are removed, so a real SKILL.md is never at risk.
  find "$target" -mindepth 1 -maxdepth 1 -type l -exec rm -f {} +
  # Every directory SKILL.md can reference, so each one exists under the
  # rewritten path too. `.venv` is guarded rather than assumed: if setup did not
  # complete above, no link is made and the user gets a missing path instead of
  # a dangling one.
  for sub in references scripts .venv; do
    [ -d "$src/$sub" ] && ln -sfn "$src/$sub" "$target/$sub"
  done
  chmod +x "$src"/scripts/*.sh 2>/dev/null || true
  sed "s#\${CLAUDE_SKILL_DIR}#$target#g" "$src/SKILL.md" > "$target/SKILL.md"
done

echo
echo "Installed for Codex. Re-run after editing a SKILL.md - that file is
rewritten at install time rather than symlinked, so its edits are not live."
echo
echo "Done. Try: 'what's my body battery?' or 'how did I sleep?'"
