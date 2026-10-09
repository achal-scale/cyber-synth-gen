#!/usr/bin/env bash
# Installs the blackbox-pentest-qa skill and the /quality_check slash
# command into ~/.claude/ (personal scope). Re-running overwrites prior
# copies. Installs alongside blackbox-pentest-pass1, tb-trial-runner, and
# (if you still need it) blackbox-pentest-qa-bundle-legacy's
# /quality_check_bundle without clobbering them.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$here/skills/blackbox-pentest-qa" ] || [ ! -f "$here/commands/quality_check.md" ]; then
  echo "error: expected 'skills/blackbox-pentest-qa/' and 'commands/quality_check.md' next to install.sh." >&2
  echo "       Unzip the archive and run install.sh from inside the extracted folder." >&2
  exit 1
fi

mkdir -p "$HOME/.claude/skills" "$HOME/.claude/commands"

rm -rf "$HOME/.claude/skills/blackbox-pentest-qa"
cp -R "$here/skills/blackbox-pentest-qa" "$HOME/.claude/skills/blackbox-pentest-qa"
chmod +x "$HOME/.claude/skills/blackbox-pentest-qa/scripts/task_qc_check.py"
cp "$here/commands/quality_check.md" "$HOME/.claude/commands/quality_check.md"

# Drop macOS Finder cruft and python bytecode that sneak into zips.
find "$HOME/.claude/skills/blackbox-pentest-qa" \( -name '.DS_Store' -o -name '__pycache__' \) \
  -exec rm -rf {} + 2>/dev/null || true

echo "Installed:"
echo "  skill   -> ~/.claude/skills/blackbox-pentest-qa/"
echo "  command -> ~/.claude/commands/quality_check.md (/quality_check)"
echo "Restart Claude Code so it re-scans ~/.claude/commands/."
