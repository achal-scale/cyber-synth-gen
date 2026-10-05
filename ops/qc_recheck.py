#!/usr/bin/env python3
"""Re-run every gate against an already-built task, independent of scaffolding or packaging.

    python3 ops/qc_recheck.py <task_dir> <rubric_pipeline_path> [--skip-fleet]

This is the re-verify-only path (synth-gen's equivalent: its separate qc-pipeline/) for a task
that was built and gated a while ago -- after a base-image update, a rubric_pipeline.py change,
or just to confirm a bundle still holds, without going through pipeline-review/new_task.py or
ops/package_deliverable.py's all-or-nothing packaging.

UNLIKE every other gate script in this repo, this one does NOT raise and stop on the first
failure. Each gate's exception, if any, is caught and recorded, and every gate still runs --
the point of a recheck is to see the full current state across all of them in one pass, not to
stop at the first bad one. Exit code is 0 only if every gate that ran reported pass/measured;
non-zero and a printed summary otherwise.

`--skip-fleet` skips fleet_gate.py and stage2_gate.py (both need trajectories/passk/ to mean
anything); without it, a task with no pass@k data yet still reports those two as failing, which
is the correct, honest state to show -- not an error in this tool.

sandbox_escape_gate was dropped from this default sequence (FNA1-driven, not core to this
pipeline's own process) -- still exists in `gate/`, still wired into
`bundle/tasks/gates_smoke.json`, just not required here.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gate"))
import contract_gate
import oracle_noop_gate
import fleet_gate
import stage2_gate


def recheck(task_dir: Path, rubric_pipeline_path: str, skip_fleet: bool) -> dict:
    gates = [
        ("contract", lambda: contract_gate.run({"args": {
            "task_dir": str(task_dir), "rubric_pipeline_path": rubric_pipeline_path}})),
        ("oracle_noop", lambda: oracle_noop_gate.run({"args": {"task_dir": str(task_dir)}})),
    ]
    if not skip_fleet:
        gates.append(("fleet", lambda: fleet_gate.run({"args": {"task_dir": str(task_dir)}})))
        gates.append(("stage2", lambda: stage2_gate.run({"args": {
            "task_dir": str(task_dir), "rubric_pipeline_path": rubric_pipeline_path}})))

    report = {}
    for name, fn in gates:
        try:
            report[name] = {"ok": True, "result": fn()}
        except Exception as e:
            report[name] = {"ok": False, "error": str(e)}
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_dir", type=Path)
    ap.add_argument("rubric_pipeline_path")
    ap.add_argument("--skip-fleet", action="store_true")
    args = ap.parse_args()

    report = recheck(args.task_dir, args.rubric_pipeline_path, args.skip_fleet)

    print(f"QC recheck: {args.task_dir.name}")
    print("-" * 60)
    all_ok = True
    for name, outcome in report.items():
        mark = "OK  " if outcome["ok"] else "FAIL"
        detail = outcome["result"] if outcome["ok"] else outcome["error"]
        print(f"  [{mark}] {name:16} {detail}")
        all_ok = all_ok and outcome["ok"]
    print("-" * 60)
    print("ALL GATES PASS" if all_ok else "ONE OR MORE GATES FAILED")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
