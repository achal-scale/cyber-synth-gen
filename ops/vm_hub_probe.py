#!/usr/bin/env python3
"""Hub-side VM-concurrency probe -- the counterpart to ops/vm_concurrency_probe.py.

Publishes a MINIMAL hub task of N independent ``deploy_sandbox`` steps (no agent,
no bundle, no boot, no pentest) and runs it on AgentEnvHub. This tests the REAL
hub path (hub scheduler + its deployed Modal environment), which the local probe
cannot -- the local probe runs in whatever env the token defaults to (main),
while the hub runs in whatever env ITS deployment configures.

Read the result three ways:
  * run-status COMPLETED vs TERMINATED  -> does 10-way creation work on the hub?
  * each deploy-sandbox-* step's log     -> the app name / any real error
  * Modal dashboard                      -> WHICH environment the VMs landed in

Short TTL + close_vm_on_completion so nothing lingers.

Setup: VPN + AWS SSO (hub REST auth), same as the other ops/ scripts.

Example:
  python ops/vm_hub_probe.py can-vmprobe-hub-1 --project-id 6a97344cdf04bf9f053a4098 \
      --n 10 --publish --run --litellm-api-key <key>
  # then poll:
  python ops/hub.py GET "/api/v1/tasks/can-vmprobe-hub-1/run-status?workflow_id=<workflow_id>"
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402


def build_steps(n: int, project_id: str, cpu: float, memory: int, ttl: int) -> list[dict]:
    """N independent deploy_sandbox steps -> the hub schedules all N creations at once."""
    steps = []
    for i in range(1, n + 1):
        steps.append({
            "id": f"deploy-sandbox-probe-{i}",
            "type": "deploy_sandbox",
            "sandbox_name": f"vmprobe-{int(time.time())}-{i}",
            "sandbox_mode": "vm",
            "cpu": cpu,
            "memory_mb": memory,
            "disk_size_gb": 30,
            "exposed_ports": [8080, 8000],
            "ttl_seconds": ttl,
            # Attribute the probe VMs (same shape as the real fix) so Modal tags them.
            "metadata": {"attribution": {"project_id": project_id}} if project_id else {},
            # EXPLICIT empty list = no dependencies -> all N deploy CONCURRENTLY.
            # (Omitting depends_on is NOT independent: the scheduler reads depends_on=None
            #  as "depends on all prior steps", which serializes them -- the real pass@k
            #  branches hit exactly this and run one-at-a-time. Empty list opts into parallel.)
            "depends_on": [],
            "fail_task_on_error": False,
        })
    return steps


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hub_task_id")
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--n", type=int, default=10, help="concurrent deploy_sandbox steps (default 10)")
    ap.add_argument("--cpu", type=float, default=4.0, help="vCPU per VM (hub pentest uses 4.0)")
    ap.add_argument("--memory", type=int, default=8192, help="MB per VM (hub pentest uses 8192)")
    ap.add_argument("--ttl", type=int, default=300, help="sandbox TTL seconds (short so VMs self-reap)")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--no-close-vm", dest="close_vm", action="store_false", default=True,
                    help="leave VMs up after the task (default: close on completion)")
    ap.add_argument("--litellm-api-key", default=None, help="required by run_task even with no LLM steps")
    args = ap.parse_args()

    steps = build_steps(args.n, args.project_id, args.cpu, args.memory, args.ttl)
    print(f"built {len(steps)} deploy_sandbox steps for {args.hub_task_id!r} "
          f"(n={args.n}, cpu={args.cpu}, mem={args.memory}MB, ttl={args.ttl}s)")
    for s in steps:
        print(f"  {s['id']:<26} {s['type']}")

    if not args.publish:
        print("\n--publish not given: nothing sent.")
        return

    status, out = hub.publish_task(args.hub_task_id, args.project_id, steps)
    print(f"\npublish -> HTTP {status}")
    if status not in (200, 201):
        raise SystemExit(out)

    if args.run:
        if not args.litellm_api_key:
            raise SystemExit("--run needs --litellm-api-key (run_task requires one even with no LLM steps)")
        status, out = hub.run_task(args.hub_task_id, args.project_id,
                                   litellm_api_key=args.litellm_api_key,
                                   close_vm_on_completion=args.close_vm)
        print(f"\nrun_task -> HTTP {status}")
        print(out)
        if isinstance(out, dict) and out.get("workflow_id"):
            wf = out["workflow_id"]
            print(f"\npoll with:\n  python ops/hub.py GET "
                  f"\"/api/v1/tasks/{args.hub_task_id}/run-status?workflow_id={wf}\"")


if __name__ == "__main__":
    main()
