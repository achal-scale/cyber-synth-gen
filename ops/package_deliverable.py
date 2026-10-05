#!/usr/bin/env python3
"""Run all gates; if every one passes, zip the task into a deliverable. Refuses otherwise.

    python3 ops/package_deliverable.py <task_dir> <rubric_pipeline_path> [--out out.zip]
                                        [--skip-fleet]

Runs, in order: contract_gate -> oracle_noop_gate -> sandbox_escape_gate -> fleet_gate.
Any gate raising GATE-STOP (or any other exception) stops packaging immediately and this
script exits non-zero, printing which gate and why -- there is no partial/best-effort zip.

--skip-fleet is for a task still in construction, before ops/launch_fleet.py has produced any
trajectories/passk/ results yet; the resulting zip is explicitly marked unfleeted in its manifest
and is NOT a finished deliverable (see root README's Roles section -- the reviewer and attempter
stages still need to happen).

The zip always contains, at minimum: task.toml, instruction.md, instruction_{L0,L1,L2}.md,
environment/, solution/, tests/, unintended_findings.json, trajectories/{oracle,noop}/, and
(unless --skip-fleet) trajectories/passk/. A MANIFEST.json recording which gates ran and their
verdicts is added at the zip root -- this is how a reviewer confirms the zip they received is
what the gates actually checked, not a hand-edited copy made after the fact.
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gate"))
import contract_gate
import oracle_noop_gate
import sandbox_escape_gate
import fleet_gate

REQUIRED_PATHS = (
    "task.toml", "instruction.md", "instruction_L0.md", "instruction_L1.md", "instruction_L2.md",
    "unintended_findings.json", "environment", "solution", "tests",
    "trajectories/oracle", "trajectories/noop",
)


def _check_required_paths(task_dir: Path, skip_fleet: bool) -> list[str]:
    required = list(REQUIRED_PATHS)
    if not skip_fleet:
        required.append("trajectories/passk")
    missing = [p for p in required if not (task_dir / p).exists()]
    return missing


def package(task_dir: Path, rubric_pipeline_path: str, out: Path, skip_fleet: bool) -> None:
    missing = _check_required_paths(task_dir, skip_fleet)
    if missing:
        sys.exit(f"GATE-STOP: package_deliverable missing required paths: {', '.join(missing)}")

    manifest = {"task": task_dir.name, "gates": {}, "unfleeted": skip_fleet}

    gates = [
        ("contract", lambda: contract_gate.run({"args": {
            "task_dir": str(task_dir), "rubric_pipeline_path": rubric_pipeline_path}})),
        ("oracle_noop", lambda: oracle_noop_gate.run({"args": {"task_dir": str(task_dir)}})),
        ("sandbox_escape", lambda: sandbox_escape_gate.run({"args": {"task_dir": str(task_dir)}})),
    ]
    if not skip_fleet:
        gates.append(("fleet", lambda: fleet_gate.run({"args": {"task_dir": str(task_dir)}})))

    for name, fn in gates:
        try:
            result = fn()
        except Exception as e:
            sys.exit(f"GATE-STOP: package_deliverable stopped at gate '{name}': {e}")
        manifest["gates"][name] = result

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in task_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(task_dir))
        zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2))

    print(f"packaged {out} ({'unfleeted' if skip_fleet else 'fleeted'})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_dir", type=Path)
    ap.add_argument("rubric_pipeline_path")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--skip-fleet", action="store_true")
    args = ap.parse_args()
    out = args.out or args.task_dir.with_suffix(".zip")
    package(args.task_dir, args.rubric_pipeline_path, out, args.skip_fleet)


if __name__ == "__main__":
    main()
