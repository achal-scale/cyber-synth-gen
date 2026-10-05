"""Fleet gate (v1: single model, pass@5, non-resumable).

Adapted from synth-gen's gate_fleet.py, reduced to v1 scope: one model (DeepSeek V4-Flash),
5 attempts, no multi-model fleet yet, and no --continue-legs resumption (a short run here is
just rerun whole in v1 — resumable continuation is a later-phase port of synth-gen's mechanism,
not implemented here).

Reads trajectories/passk/<trial>/reward.txt for trial in 1..5 (same shape as our existing
trajectories/{oracle,noop}/reward.txt convention, extended to a numbered trial directory).

THE TWO STOPS (v1 has two, not synth-gen's three, since there is no attempt-cap/leg-short split
without a multi-leg resumable fleet):
  bundle-blocked  any trial's reward.txt is missing, unreadable, or outside {0, 1} -- the task
                  or verifier itself is broken, not a model capability result. Routes back to
                  construction, same as a contract or oracle/noop gate failure would.
  measured        every trial read cleanly as 0 or 1. This is NOT pass/fail for the gate -- a
                  task that goes 5/5 is not blocked, but it is a weak task (see
                  environment-eval/README.md's pass-rate guidance) and should be flagged in the
                  handoff note to the reviewer, not silently shipped.

Args: `task_dir`, `attempts` (default 5).
"""
import sys
from pathlib import Path


def _trial_reward(task_dir, trial):
    p = Path(task_dir) / "trajectories" / "passk" / str(trial) / "reward.txt"
    if not p.exists():
        return None
    return p.read_text().strip()


def run(input):
    args = input.get("args") if isinstance(input, dict) else {}
    task_dir = args.get("task_dir")
    attempts = int(args.get("attempts") or 5)
    if not task_dir:
        raise ValueError("GATE-CONFIG: fleet_gate needs task_dir")

    rewards, unreadable = [], []
    for trial in range(1, attempts + 1):
        raw = _trial_reward(task_dir, trial)
        if raw not in ("0", "1"):
            unreadable.append((trial, raw))
        else:
            rewards.append(int(raw))

    if unreadable:
        detail = "; ".join(f"trial {t}: {r!r}" for t, r in unreadable)
        raise RuntimeError(f"GATE-STOP: fleet gate bundle-blocked ({detail})")

    pass_rate = sum(rewards) / attempts
    flag = None
    if pass_rate >= 1.0:
        flag = "weak: 5/5 pass, no difficulty signal -- reviewer should check for a non-unique path"
    elif pass_rate == 0.0:
        flag = "note: 0/5 pass -- confirm this is genuine difficulty, not an unsolvable task, before fleet-escalating"

    return {
        "status": "measured",
        "attempts": attempts,
        "pass_rate": pass_rate,
        "flag": flag,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run({"args": {"task_dir": sys.argv[1]}}), indent=2))
