"""Structural contract gate: task layout, hint tiers, hygiene, no bolted-on endpoint.

Runs the Stage-1 static checks from cyber-sample-tasks/tools/rubric_pipeline.py against a built
task directory — explicitly excluding rubric_pipeline.STAGE2 ids (TR4, TR5, EV6), which need a
pass@k packet that does not exist yet at this point in the construction loop (the fleet gate
runs those, after ops/launch_fleet.py has produced one). Logic is reused from that pipeline, not
reimplemented here. Field names (`rid`, `verdict`, `evidence` on each result) match
rubric_pipeline.py's `R` class exactly.

Raises a GATE-STOP:-prefixed message naming every FAILing rubric id if any exist. A
REVIEW-verdict rubric does not stop the gate (it is a human-judgment item), but is listed in the
output so a reviewer sees it before taking the task.

Args: `task_dir` (path to the built task), `rubric_pipeline_path` (path to the sibling
cyber-sample-tasks/tools/rubric_pipeline.py; this gate has no copy of its own).
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
        raise ValueError("GATE-CONFIG: contract_gate needs task_dir and rubric_pipeline_path")

    rp = _load_rubric_pipeline(rubric_pipeline_path)
    task = rp.Task(task_dir)
    results = [r for r in rp.check(task) if r.rid not in rp.STAGE2]

    failing = [r for r in results if r.verdict == "FAIL"]
    reviewing = [r for r in results if r.verdict == "REVIEW"]

    if failing:
        ids = ", ".join(r.rid for r in failing)
        raise RuntimeError(f"GATE-STOP: contract gate failing rubrics: {ids}")

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
