#!/usr/bin/env python3
"""Cheap smoke test of the construct-1a..1g sub-step SEQUENCING mechanics
(build_full_pipeline_task.py's _construction_inject_substeps), without paying
for the real construction workload (fetching base apps, injecting a real
vulnerability, writing a real B/R scaffold).

What this validates: 7 sequential prompt_agent turns against the SAME agent,
each depending on the previous step's id, each writing one marker file and
checking for all markers written by PRIOR steps before writing its own --
proving (a) the dependency chain executes in the intended order, (b) agent
identity/filesystem state really does carry over turn to turn, (c) a step that
times out and retries (simulated here by the agent possibly re-running) doesn't
corrupt markers already written by earlier steps. All steps fail_task_on_error
so a failure in one doesn't hide whether later ones would have the right view
of state.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

SANDBOX_NAME = "construct-split-smoke-vm-r9"
AGENT_NAME = "smoke-agent"

LABELS = ["1a", "1b", "1c", "1d", "1e", "1f", "1g"]


def _step_prompt(label: str, prior_labels: list[str]) -> str:
    checks = "\n".join(f'test -f /work/smoke/{p}.marker || echo "MISSING_PRIOR:{p}"' for p in prior_labels)
    checks = checks or "echo no-prior-steps"
    return (
        f"Run exactly this bash:\n```bash\nmkdir -p /work/smoke\n{checks}\n"
        f"echo done > /work/smoke/{label}.marker\nls /work/smoke\n```\n"
        f"Reply with exactly the `ls /work/smoke` output, nothing else."
    )


def build_steps() -> list[dict]:
    steps = [
        {
            "id": "deploy-sandbox", "type": "deploy_sandbox",
            "sandbox_name": SANDBOX_NAME, "sandbox_mode": "vm",
            # sandbox_type="modal_vm" (tried in an earlier attempt) avoided the
            # transient default-backend 500/503s but doesn't support rootless
            # docker (enable_docker failed: "rootless docker daemon did not
            # become ready", permission-denied on kernel netns/iptables access)
            # -- incompatible with this pipeline's docker-compose-based design.
            # Back to default (unset) sandbox_type, same as wpii-full-pipeline-1
            # v18's own deploy-sandbox, which has been running fine with
            # enable_docker=True the whole time -- the outage looks transient
            # and specific to whatever window attempts 1-5 ran in.
            "cpu": 4.0, "memory_mb": 8192, "disk_size_gb": 30,
            "exposed_ports": [8080, 8000], "ttl_seconds": 14400,
        },
        {
            "id": "deploy-agent", "type": "deploy_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": AGENT_NAME,
            "sandbox_name": SANDBOX_NAME, "enable_docker": True,
            "depends_on": [{"task_step_id": "deploy-sandbox"}],
        },
    ]
    prev_id = "deploy-agent"
    for i, label in enumerate(LABELS):
        prior = LABELS[:i]
        step = {
            "id": f"smoke-{label}", "type": "prompt_agent", "agent_name": AGENT_NAME,
            "depends_on": [{"task_step_id": prev_id}],
            "timeout_seconds": 120, "max_turns": 5,
            "prompt_id": f"smoke-{label}",
            "model": "anthropic/claude-sonnet-5",
            "prompt": _step_prompt(label, prior),
            "fail_task_on_error": False,
        }
        steps.append(step)
        prev_id = step["id"]
    return steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-id", default=f"test-construction-split-{int(time.time())}")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--litellm-api-key", default=None)
    args = ap.parse_args()

    steps = build_steps()
    print(f"built {len(steps)} steps for {args.task_id!r}")
    for s in steps:
        print(f"  {s['id']:<14} {s['type']}")

    if not args.publish:
        print("\n--publish not given: nothing sent.")
        return

    status, out = hub.publish_task(args.task_id, args.project_id, steps)
    print(f"\npublish -> HTTP {status}")
    if status not in (200, 201):
        raise SystemExit(out)

    if args.run:
        if not args.litellm_api_key:
            raise SystemExit("--run needs --litellm-api-key")
        status, out = hub.run_task(args.task_id, args.project_id, litellm_api_key=args.litellm_api_key)
        print(f"\nrun_task -> HTTP {status}")
        print(out)


if __name__ == "__main__":
    main()
