"""Stage-2 rubric gate: the three checks that need a pass@k packet (TR4, TR5, EV6).

contract_gate.py (gate 1) deliberately excludes rubric_pipeline.STAGE2 ids, because they need a
pass@k packet that doesn't exist yet at that point in the construction loop. This gate is where
they actually get checked -- it must only run AFTER gate/fleet_gate.py has confirmed
trajectories/passk/ is real (not bundle-blocked), since these three rubrics read that data.

Before this gate existed, TR4/TR5/EV6 were structurally unreachable in this pipeline: nothing
ever called rubric_pipeline.check() a second time after the fleet step, so three of the
project's 24-27 rubrics were silently never enforced. This closes that gap.

Same verdict handling as contract_gate.py: FAIL stops the gate, REVIEW is listed but does not
stop it. Field names (`rid`, `verdict`, `evidence`) match rubric_pipeline.py's `R` class.

Args: `task_dir`, `rubric_pipeline_path`.
"""
import importlib.util
import sys


def _load_rubric_pipeline(rubric_pipeline_path):
    spec = importlib.util.spec_from_file_location("rubric_pipeline", rubric_pipeline_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(input):
    args = input.get("args") if isinstance(input, dict) else {}
    task_dir = args.get("task_dir")
    rubric_pipeline_path = args.get("rubric_pipeline_path")
    if not task_dir or not rubric_pipeline_path:
        raise ValueError("GATE-CONFIG: stage2_gate needs task_dir and rubric_pipeline_path")

    rp = _load_rubric_pipeline(rubric_pipeline_path)
    task = rp.Task(task_dir)
    results = [r for r in rp.check(task) if r.rid in rp.STAGE2]

    failing = [r for r in results if r.verdict == "FAIL"]
    reviewing = [r for r in results if r.verdict == "REVIEW"]

    if failing:
        ids = ", ".join(r.rid for r in failing)
        raise RuntimeError(f"GATE-STOP: stage2 gate failing rubrics: {ids}")

    return {
        "status": "pass",
        "failing": [],
        "review": [r.rid for r in reviewing],
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run({"args": {
        "task_dir": sys.argv[1],
        "rubric_pipeline_path": sys.argv[2],
    }}), indent=2))
