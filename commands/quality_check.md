---
description: Run a generalized static QC pass on ONE black-box pentest task (no bundle/env_<slug> assumptions) -- structure, leaks, anti-cheat ordering, oracle self-pass heuristic, reward.json schema, docker-compose concurrency safety. Confirms the folder is clean enough to spend pass@k trials on.
argument-hint: "[task-dir]"
---

Use the `blackbox-pentest-qa` skill (read its `SKILL.md` first, in full --
it's short) to QC the given single task folder.

Arguments (optional): $ARGUMENTS
- If a task path is given, QC that one; otherwise use `./task` if it has a
  `task.toml`, or ask which directory to check.

Steps:
1. Read `~/.claude/skills/blackbox-pentest-qa/SKILL.md` in full.
2. Run the static checks:
   ```bash
   python3 ~/.claude/skills/blackbox-pentest-qa/scripts/task_qc_check.py <task-dir>
   ```
   Fix every `[FAIL]`. `[WARN]` items need a human judgment call.
3. Manually read `tests/test.sh` and `solution/solve.sh` once -- the ordering
   check is a heuristic, not a proof.
4. Remind the user that a clean static pass is necessary but not sufficient:
   `/oracle` and `/noop` still need to actually pass on a real docker boot
   before spending any `/passk` trials, and a decoy-hardening spot check is
   still worth doing if it hasn't been done yet.
5. Report a concise pass/fail summary: what was checked, what (if anything)
   was found and fixed. Do not restate passing checks at length.
