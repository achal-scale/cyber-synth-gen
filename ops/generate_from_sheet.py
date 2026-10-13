#!/usr/bin/env python3
"""General, sheet-driven entry point: one CSV row in, one task out (scaffolded, or, once
already built, published as a real hub fleet DAG). This is the thing `ops/build_hub_task.py`
on its own is NOT -- that script takes one already-built `task_dir` as an argument; this
script is the batch driver on top of it, the piece the user asked for after seeing
`build_hub_task.py` only handle one hardcoded task.

    python3 ops/generate_from_sheet.py sheet.csv --project-id <id> [--publish]

CSV COLUMNS (header row required):
    env         required  the real application, e.g. "dolibarr", "glpi"
    vuln_type   required  e.g. "idor", "sqli", "ssrf", "xxe", "traversal", "mass-assignment"
    cwe         optional  e.g. "CWE-639"
    cve         optional  e.g. "CVE-2022-0731"
    ticket      optional  4-digit ticket number for the instruction header; auto-generated
                          (a stable hash of env+vuln_type) when omitted, never random, so
                          re-running the same sheet is idempotent
    attempts    optional  fleet legs for this row; default 3
    tier        optional  instruction tier (L0/L1/L2); default L0
    model       optional  a2a model string passed to each prompt_agent step

Per row, exactly one of three things happens:
    1. tasks_built/<env>-<vuln_type>/ does not exist yet -> SCAFFOLDED via
       `pipeline-review/new_task.py`'s `scaffold()`. Reported `needs-manual-build`: the
       vulnerability injection, Dockerfiles, solve.sh and test.sh are real engineering work
       this script deliberately does not fake (see `new_task.py`'s own docstring) -- re-run
       this same sheet after that work lands and the row advances to (2) on its own.
    2. tasks_built/<env>-<vuln_type>/ exists but still has an unfinished TODO marker in its
       task.toml or instruction_L0.md (the scaffold's own placeholder text) -> reported
       `scaffold-incomplete`, same as (1): still needs the manual build step.
    3. tasks_built/<env>-<vuln_type>/ exists and looks built -> a hub fleet DAG is generated
       via `build_hub_task.build_steps()` and PUBLISHED (with `--publish`; otherwise just
       printed) as `cyber-synth-gen-<env>-<vuln_type>-fleet`, same stand-ins/limitations
       documented in `build_hub_task.py`'s own module docstring (setup/verify steps are not
       yet the real `run_code`/`env_outcome_verifier` shape -- see README.md's "Hub pipeline"
       section for why and the exact swap-over).

Every row's outcome is independent: one bad or incomplete row never stops the rest of the
sheet (mirrors `create_delivery_from_csv`'s own per-row independence on the platform side).
"""
import argparse
import csv
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "pipeline-review"))

import build_hub_task  # noqa: E402
import hub  # noqa: E402
import new_task  # noqa: E402

TASKS_BUILT = REPO / "tasks_built"


def _stable_ticket(env: str, vuln_type: str) -> str:
    """A deterministic 4-digit ticket number from env+vuln_type, so re-running the same
    sheet twice names the same ticket rather than drifting (the scaffold's own `--ticket`
    flag otherwise defaults to "0000" for every row)."""
    digest = hashlib.sha256(f"{env}-{vuln_type}".encode()).hexdigest()
    return str(int(digest[:8], 16) % 9000 + 1000)


def _looks_built(task_dir: Path) -> tuple[bool, str]:
    """(built, reason-if-not). A scaffold is "built" once its TODO markers are gone and a
    real environment/ exists; anything short of that is still (1)/(2) in the module
    docstring, not (3)."""
    if not task_dir.is_dir():
        return False, "does not exist yet"
    toml_path = task_dir / "task.toml"
    instr_path = task_dir / "instruction_L0.md"
    if not toml_path.is_file() or not instr_path.is_file():
        return False, "missing task.toml or instruction_L0.md"
    if "TODO" in toml_path.read_text():
        return False, "task.toml still has a TODO placeholder"
    if "TODO" in instr_path.read_text():
        return False, "instruction_L0.md still has a TODO placeholder"
    compose = task_dir / "environment" / "docker-compose.yaml"
    if not compose.is_file():
        return False, "environment/docker-compose.yaml does not exist"
    return True, ""


def process_row(row: dict, project_id: str, publish: bool) -> dict:
    env = row["env"].strip()
    vuln_type = row["vuln_type"].strip()
    slug = f"{env}-{vuln_type}"
    task_dir = TASKS_BUILT / slug
    hub_task_id = f"cyber-synth-gen-{slug}-fleet"

    built, reason = _looks_built(task_dir)
    if not built and task_dir.is_dir():
        return {"slug": slug, "status": "scaffold-incomplete", "detail": reason}
    if not built:
        ticket = (row.get("ticket") or "").strip() or _stable_ticket(env, vuln_type)
        new_task.scaffold(env, vuln_type, task_dir,
                          cwe=(row.get("cwe") or "TODO").strip(),
                          cve=(row.get("cve") or "").strip(), ticket=ticket)
        return {"slug": slug, "status": "scaffolded", "detail": f"needs manual build at {task_dir}"}

    attempts = int(row.get("attempts") or 3)
    tier = (row.get("tier") or "L0").strip()
    model = (row.get("model") or "").strip() or None
    steps = build_hub_task.build_steps(task_dir, attempts, tier, model, hub_task_id)

    if not publish:
        return {"slug": slug, "status": "built-not-published",
                "detail": f"{len(steps)} steps ready; re-run with --publish"}

    status, out = hub.publish_task(hub_task_id, project_id, steps)
    if status not in (200, 201):
        return {"slug": slug, "status": "publish-failed", "detail": f"HTTP {status}: {out}"}
    version = out.get("task_version") if isinstance(out, dict) else None
    return {"slug": slug, "status": "published",
            "detail": f"{hub_task_id} v{version} ({len(steps)} steps)"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheet", type=Path, help="CSV with env,vuln_type[,cwe,cve,ticket,attempts,tier,model]")
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--publish", action="store_true",
                    help="actually publish built rows to the hub; default is print-only")
    args = ap.parse_args()

    with open(args.sheet, newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit(f"{args.sheet}: no rows")
    missing = [i for i, r in enumerate(rows, 1) if not r.get("env") or not r.get("vuln_type")]
    if missing:
        sys.exit(f"{args.sheet}: rows {missing} are missing required 'env' or 'vuln_type'")

    print(f"{'slug':<28} {'status':<20} detail")
    results = []
    for row in rows:
        try:
            result = process_row(row, args.project_id, args.publish)
        except Exception as e:  # noqa: BLE001 -- one bad row must not stop the sheet
            result = {"slug": f"{row.get('env')}-{row.get('vuln_type')}",
                     "status": "error", "detail": f"{type(e).__name__}: {e}"}
        results.append(result)
        print(f"{result['slug']:<28} {result['status']:<20} {result['detail']}")

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\nsummary: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
