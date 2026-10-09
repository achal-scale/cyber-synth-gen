#!/usr/bin/env bash
set -uo pipefail
###############################################################################
# blackbox-pentest-qa -- static pre-pass@k QC check for ONE black-box pentest
# task (no bundle/env_<slug> assumptions).
#
# Just run this: ./run.sh [TASK_DIR] [--strict]
#
# TASK_DIR defaults to ./task (same convention as the pass@k skills). Prints
# terse [FAIL]/[WARN] issue+fix lines; prints exactly "Quality check done,
# passed all the requirement." when clean. See scripts/task_qc_check.py's own
# module docstring for exactly what's checked.
###############################################################################

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/skills/blackbox-pentest-qa/scripts/task_qc_check.py"

# A leading flag (starts with -) is never the task dir -- default to ./task
# and pass everything through as flags instead of swallowing e.g. --strict
# as if it were TASK_DIR.
if [ $# -gt 0 ] && [[ "$1" != -* ]]; then
  TASK_DIR="$1"
  shift
else
  TASK_DIR="task"
fi

exec python3 "$SCRIPT" "$TASK_DIR" "$@"
