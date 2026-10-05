#!/usr/bin/env python3
"""Launch a built task's v1 fleet: one model (DeepSeek V4-Flash), pass@5, one trial at a time.

    python3 ops/launch_fleet.py <task_dir> --agent-cmd '<command that drives a model against
        the booted task>' [--attempts 5] [--model deepseek/deepseek-v4-flash]
        [--fleet-state-dir DIR]

WHY THIS SCRIPT OWNS THE TRIAL INSTEAD OF HANDING IT TO AN AGENT-ENV AGENT STEP (the lesson from
reading synth-gen's gate/run_attempt.py): an agent-env `prompt_agent`-style step ends the moment
the agent sends its final message, and a long, possibly-stalling agentic trial does not fit that
shape -- the platform would collect a slice the trial is still writing. So, like
synth-gen's run_attempt.py, this script:
  1. derives its OWN deadline from the task's declared `[agent].timeout_sec` plus a setup
     margin, not from whatever step/process wraps this script;
  2. launches the actual model-driving harness as a subprocess under that deadline and kills it
     at the deadline rather than trusting it to stop itself, recording `killed-at-budget`;
  3. runs the verifier itself afterward (`tests/test.sh`, staged into `main` the same way
     `scripts/smoke.sh` does for the oracle), rather than trusting the harness to have graded
     its own run;
  4. checks a shared fleet-state blocked marker before starting, so one task-level defect found
     by an earlier leg (not applicable yet at v1's single-model scope, but kept for the
     multi-model phase) stops every other leg from wasting a trial on a task known to be broken.

WHAT `--agent-cmd` MUST BE. This script does not know, and does not guess, what actually drives
a model against a booted Harbor-shaped docker-compose task in this org's setup (a Harbor CLI
invocation, a terminus-2 agent spec, or something else) -- that is supplied by the caller, not
fabricated here. It is run as a subprocess with `TASK_DIR`, `COMPOSE_PROJECT`, and `MODEL`
in its environment, and is expected to have finished acting on the task (whatever that means for
the harness) by the time it returns; this script runs the verifier itself afterward regardless of
what the agent command did or didn't do internally.

v1 explicitly does NOT implement multi-model fleets (Kang's 3-stage proposal) or
--continue-legs-style resumption of a short run -- both are later-phase ports of synth-gen's
mechanics, not done here. Trials run sequentially, each under its own Compose project name
(contamination-free by construction -- see gate/README.md and the project's own
scripts/smoke.sh convention for why a unique `-p` is sufficient here).
"""
import argparse
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

SETUP_MARGIN_SEC = 300


def _agent_timeout_sec(task_dir: Path) -> float:
    toml_path = task_dir / "task.toml"
    with open(toml_path, "rb") as fh:
        doc = tomllib.load(fh)
    return float(doc.get("agent", {}).get("timeout_sec", 3600.0))


def _fleet_blocked(fleet_state_dir: Path | None) -> str | None:
    if not fleet_state_dir:
        return None
    marker = fleet_state_dir / "blocked.json"
    if marker.exists():
        return marker.read_text().strip()
    return None


def _compose(project: str, env_dir: Path) -> list[str]:
    return ["docker", "compose", "-p", project, "-f", str(env_dir / "docker-compose.yaml")]


def run_one_trial(task_dir: Path, trial: int, model: str, agent_cmd: str,
                   fleet_state_dir: Path | None) -> str:
    """Returns the recorded result string: '0', '1', 'killed-at-budget', or 'fleet-blocked'."""
    blocked_reason = _fleet_blocked(fleet_state_dir)
    if blocked_reason:
        return "fleet-blocked"

    env_dir = task_dir / "environment"
    project = f"{task_dir.name}-passk-{trial}-{uuid.uuid4().hex[:8]}"
    compose = _compose(project, env_dir)
    deadline = time.monotonic() + _agent_timeout_sec(task_dir) + SETUP_MARGIN_SEC
    out_dir = task_dir / "trajectories" / "passk" / str(trial)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(compose + ["up", "-d", "--build", "--wait"], check=True,
                        timeout=max(1, deadline - time.monotonic()))

        remaining = max(1, deadline - time.monotonic())
        env = {**os.environ, "TASK_DIR": str(task_dir), "COMPOSE_PROJECT": project, "MODEL": model}
        try:
            subprocess.run(agent_cmd, shell=True, env=env, timeout=remaining, check=False)
        except subprocess.TimeoutExpired:
            (out_dir / "reward.txt").write_text("killed-at-budget")
            return "killed-at-budget"

        # Staging and running the verifier is a harness-privileged operation, run as root --
        # per this project's own convention (cyber-sample-tasks/AGENTS.md: "[verifier]
        # environment_mode = 'shared' -- verifier runs as root and reads the protected state"),
        # the restricted agent user (uid 1001 in these tasks' images) must not have write access
        # to /tests or read access to whatever the verifier inspects.
        subprocess.run(compose + ["exec", "-T", "--user", "root", "main", "sh", "-lc",
                                   "mkdir -p /tests /logs/verifier"], check=True)
        subprocess.run(compose + ["cp", str(task_dir / "tests") + "/.", "main:/tests/"], check=True)
        subprocess.run(compose + ["exec", "-T", "--user", "root", "main", "sh", "-lc",
                                   "chmod +x /tests/test.sh"], check=True)
        subprocess.run(compose + ["exec", "-T", "--user", "root", "main", "sh", "/tests/test.sh"],
                        check=False)

        reward = subprocess.run(
            compose + ["exec", "-T", "--user", "root", "main", "sh", "-lc",
                        "cat /logs/verifier/reward.txt"],
            check=False, capture_output=True, text=True,
        ).stdout.strip()
        (out_dir / "reward.txt").write_text(reward)
        return reward
    finally:
        subprocess.run(compose + ["down", "-v", "--remove-orphans"], check=False,
                        capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_dir", type=Path)
    ap.add_argument("--agent-cmd", required=True,
                     help="shell command that drives a model against the booted task; "
                          "receives TASK_DIR/COMPOSE_PROJECT/MODEL in its environment")
    ap.add_argument("--attempts", type=int, default=5)
    ap.add_argument("--model", default="deepseek/deepseek-v4-flash")
    ap.add_argument("--fleet-state-dir", type=Path, default=None)
    args = ap.parse_args()

    if not (args.task_dir / "environment" / "docker-compose.yaml").exists():
        sys.exit(f"not a built task: {args.task_dir}")

    for trial in range(1, args.attempts + 1):
        print(f"[trial {trial}/{args.attempts}] model={args.model}", end=" ")
        result = run_one_trial(args.task_dir, trial, args.model, args.agent_cmd,
                                args.fleet_state_dir)
        print(f"-> {result}")
        if result == "fleet-blocked":
            print("stopping: fleet-state marked blocked by another leg")
            break


if __name__ == "__main__":
    main()
