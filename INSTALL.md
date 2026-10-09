# blackbox-pentest-qa -- install

Runs a generalized static QC pass on ONE black-box pentest task -- no
bundle/env_<slug> assumptions, no shared `behavior_catalog.json` or
`design_note.md`, no cross-contamination step. Confirms a single task
folder is clean enough to spend real pass@k trials on.

## Install

```bash
./install.sh
```

Copies the skill -> `~/.claude/skills/blackbox-pentest-qa/` and the command
-> `~/.claude/commands/quality_check.md` (`/quality_check`). Restart Claude
Code after.

## What it does

Static checks only (`scripts/task_qc_check.py`, no docker required):
structure, vulnerability-naming leaks (word-boundary safe), anti-cheat
ordering, oracle-writes-submission heuristic, `reward.json` schema
(`{"reward": N}`, not `{"score": ...}`), docker-compose concurrency safety
(fixed host ports / hardcoded subnets that break `n_concurrent_trials`),
and `VERIFIER_TOKEN` wiring.

An earlier version of this skill assumed the 1-environment/N-sibling-task
`env_<slug>/task_N_<slug>/` bundle shape and hard-required bundle-only
artifacts that don't exist for a standalone task. That version is preserved
separately as `blackbox-pentest-qa-bundle-legacy`
(`/quality_check_bundle`) for the rare case of re-QAing a genuine
multi-task shared-environment bundle (e.g. the original `cms_publishing`/
`ecommerce_ops` environments).

## What it does NOT do

No docker boot, so it can't prove the task actually grades correctly at
runtime. Still required before spending pass@k trials: `/oracle` (real
`solve.sh -> submission.txt -> test.sh`, reward=1), `/noop` (no exploit
attempted, reward=0), and a decoy-hardening spot check.

## Prerequisites

- `python3` only. No docker needed for this skill.
