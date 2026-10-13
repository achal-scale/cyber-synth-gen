#!/usr/bin/env python3
"""Cheap, isolated diagnostic: deploy ONE construction-agent (same config as
the real pipeline's deploy-construction-agent step -- a2a_agent_id=
"claude-code-cli", enable_docker=True) and immediately run a single diagnostic
prompt, to confirm/characterize the "uid=999, no /work, no sudo, dind sidecar"
provisioning regression seen on 3 consecutive real pipeline runs (v1-original,
v2, v1-relaunch), independent of any construction-template content.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

SANDBOX_NAME = f"agent-diag-{int(time.time())}"
AGENT_NAME = "diag-agent"

DIAG_PROMPT = (
    "Run exactly these commands and report the raw output of each, labeled, "
    "nothing else:\n"
    "```\n"
    "whoami && id\n"
    "ls -la /\n"
    "mkdir -p /work/task 2>&1; echo mkdir_exit=$?\n"
    "which docker; echo docker_cli_exit=$?\n"
    "env | grep -i docker\n"
    "docker version 2>&1; echo docker_version_exit=$?\n"
    "which sudo; echo sudo_exit=$?\n"
    "ls -la /app /workspace 2>&1\n"
    "cat /etc/os-release 2>&1 | head -3\n"
    "```"
)


def build_steps() -> list[dict]:
    return [
        {
            "id": "deploy-sandbox", "type": "deploy_sandbox",
            "sandbox_name": SANDBOX_NAME, "sandbox_mode": "vm",
            "cpu": 4.0, "memory_mb": 8192, "disk_size_gb": 30,
            "exposed_ports": [8080, 8000], "ttl_seconds": 1800,
        },
        {
            "id": "deploy-agent", "type": "deploy_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": AGENT_NAME,
            "sandbox_name": SANDBOX_NAME, "enable_docker": True,
            "depends_on": [{"task_step_id": "deploy-sandbox"}],
        },
        {
            "id": "diagnose", "type": "prompt_agent", "agent_name": AGENT_NAME,
            "depends_on": [{"task_step_id": "deploy-agent"}],
            "timeout_seconds": 300, "max_turns": 10,
            "prompt_id": "diagnose",
            "model": "anthropic/claude-sonnet-5",
            "prompt": DIAG_PROMPT,
            "fail_task_on_error": False,
        },
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-id", default=f"test-agent-provisioning-diag-{int(time.time())}")
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
