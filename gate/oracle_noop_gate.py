"""Oracle/noop gate: the task actually scores 1 for the known solution and 0 for nothing.

Reads trajectories/{oracle,noop}/reward.txt the same way rubric_pipeline.Task.reward() does
(same read path, same strip()). Does NOT run the containers itself — that happens upstream in
the construction loop's [build] stage via each task's own scripts/smoke.sh-equivalent (see
pipeline-review/README.md); this gate only checks that the recorded result is correct before
anything proceeds to the sandbox-escape gate.

A missing reward.txt for either trajectory is itself a GATE-STOP: an untested oracle/noop is
indistinguishable from a broken one, and this pipeline does not ship on "probably fine."

Args: `task_dir`.
"""
import sys
from pathlib import Path


def _reward(task_dir, which):
    p = Path(task_dir) / "trajectories" / which / "reward.txt"
    if not p.exists():
        return None
    return p.read_text().strip()


def run(input):
    args = input.get("args") if isinstance(input, dict) else {}
    task_dir = args.get("task_dir")
    if not task_dir:
        raise ValueError("GATE-CONFIG: oracle_noop_gate needs task_dir")

    oracle = _reward(task_dir, "oracle")
    noop = _reward(task_dir, "noop")

    problems = []
    if oracle is None:
        problems.append("no trajectories/oracle/reward.txt recorded")
    elif oracle != "1":
        problems.append(f"oracle reward is {oracle!r}, expected '1'")
    if noop is None:
        problems.append("no trajectories/noop/reward.txt recorded")
    elif noop != "0":
        problems.append(f"noop reward is {noop!r}, expected '0'")

    if problems:
        raise RuntimeError("GATE-STOP: oracle/noop gate: " + "; ".join(problems))

    return {"status": "pass", "oracle": oracle, "noop": noop}


if __name__ == "__main__":
    import json
    print(json.dumps(run({"args": {"task_dir": sys.argv[1]}}), indent=2))
