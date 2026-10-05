#!/usr/bin/env python3
"""Launch a built task's v1 fleet: one model (DeepSeek V4-Flash), pass@5, one trial at a time.

    python3 ops/launch_fleet.py <task_dir> [--attempts 5] [--model deepseek/deepseek-v4-flash]

THIS IS A DOCUMENTED STUB, NOT A TESTED SCRIPT. It requires a live Docker daemon, a reachable
model endpoint (LiteLLM base URL + key, per this project's existing AGENTS.md preflight rule:
probe the exact model/base_url/credential with one authenticated request before launching any
batch), and an actual agent harness wired to drive the model against the task's `main` container
-- none of which exist in this repo yet. It is written now so the fleet gate (`../gate/fleet_gate.py`)
and the trajectory layout it expects (`trajectories/passk/<trial>/reward.txt`) have one concrete
caller to validate against once the harness exists, not so it can be run today.

v1 explicitly does NOT implement:
  - multiple models (Kang's 3-stage proposal: deepseek precheck -> mid-tier -> frontier) --
    deferred per your decision; only one model, one stage, here.
  - --continue-legs resumption (synth-gen's answer to a run stopping short under resource
    pressure) -- a short v1 run is rerun whole.
  - parallel trials -- synth-gen gets "one box per model, all at once" for free from agent-env's
    DAG scheduler (independent steps with no depends_on edge run concurrently); this repo does
    not yet have an agent-env Task graph wired up, so v1 runs its 5 trials sequentially.

Each trial: boot the task's environment/docker-compose.yaml under a unique Compose project name
(contamination-free parallelism, once this is made parallel, comes from that alone -- see the
synth-gen `--continue-legs` discussion in CHANGELOG.md for why project-name isolation is
sufficient and no additional sandboxing is needed at this layer), stage the agent harness into
`main`, run it against the task's instruction, run `tests/test.sh`, record
`trajectories/passk/<trial>/reward.txt`.
"""
import argparse
import subprocess
import sys
import uuid
from pathlib import Path


def run_one_trial(task_dir: Path, trial: int, model: str) -> None:
    raise NotImplementedError(
        "ops/launch_fleet.py is a documented stub (see module docstring) -- "
        "no agent harness is wired up yet to actually drive a model against a task. "
        "This function is the one call site gate/fleet_gate.py's trajectory layout "
        "needs implemented before this script does anything live."
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("task_dir", type=Path)
    ap.add_argument("--attempts", type=int, default=5)
    ap.add_argument("--model", default="deepseek/deepseek-v4-flash")
    args = ap.parse_args()

    if not (args.task_dir / "environment" / "docker-compose.yaml").exists():
        sys.exit(f"not a built task: {args.task_dir}")

    for trial in range(1, args.attempts + 1):
        project = f"{args.task_dir.name}-passk-{trial}-{uuid.uuid4().hex[:8]}"
        print(f"[trial {trial}/{args.attempts}] project={project} model={args.model}")
        run_one_trial(args.task_dir, trial, args.model)


if __name__ == "__main__":
    main()
