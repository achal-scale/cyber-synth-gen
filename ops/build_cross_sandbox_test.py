#!/usr/bin/env python3
"""Cheap test: can an agent on sandbox B reach a plain HTTP server running on
sandbox A, in the same task run, given A's `sandbox_name` (DNS-style) vs its
public tunnel_url? Answers the open design question for the "separate sandbox
per pentest agent" fix (see build_full_pipeline_task.py's module docstring and
VmSandbox.container_name's "one agent per VM" constraint) -- if sandbox_name
resolves cross-sandbox, the pentest prompt can just say "http://target-vm:8080"
unchanged; if not, we need the two-phase/runtime-discovered-tunnel-url route.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

MODEL = "anthropic/claude-sonnet-5"


def build_steps() -> list[dict]:
    return [
        {
            "id": "deploy-target-vm", "type": "deploy_sandbox",
            "sandbox_name": "target-vm", "sandbox_mode": "vm",
            "cpu": 1.0, "memory_mb": 2048, "disk_size_gb": 10,
            "exposed_ports": [8080, 8000], "ttl_seconds": 1800,
        },
        {
            "id": "deploy-target-agent", "type": "deploy_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": "target-agent",
            "sandbox_name": "target-vm",
            "depends_on": [{"task_step_id": "deploy-target-vm"}],
        },
        {
            "id": "start-http-server", "type": "prompt_agent", "agent_name": "target-agent",
            "depends_on": [{"task_step_id": "deploy-target-agent"}],
            "timeout_seconds": 120, "max_turns": 5,
            "prompt_id": "start-http-server", "model": MODEL,
            "prompt": (
                "Run `nohup python3 -m http.server 8080 >/tmp/http.log 2>&1 & "
                "sleep 1 && curl -s localhost:8080 | head -3`. Reply with exactly "
                "its output, nothing more."
            ),
        },
        {
            "id": "deploy-attacker-vm", "type": "deploy_sandbox",
            "sandbox_name": "attacker-vm", "sandbox_mode": "vm",
            "cpu": 1.0, "memory_mb": 2048, "disk_size_gb": 10,
            "exposed_ports": [8000], "ttl_seconds": 1800,
            "depends_on": [{"task_step_id": "start-http-server"}],
        },
        {
            "id": "deploy-attacker-agent", "type": "deploy_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": "attacker-agent",
            "sandbox_name": "attacker-vm",
            "depends_on": [{"task_step_id": "deploy-attacker-vm"}],
        },
        {
            "id": "try-cross-sandbox", "type": "prompt_agent", "agent_name": "attacker-agent",
            "depends_on": [{"task_step_id": "deploy-attacker-agent"}],
            "timeout_seconds": 120, "max_turns": 5,
            "prompt_id": "try-cross-sandbox", "model": MODEL,
            "prompt": (
                "Run exactly these two commands and reply with the raw combined "
                "output of both, nothing more, nothing interpreted: "
                "`curl -s --max-time 5 http://target-vm:8080 || echo CURL_FAILED` "
                "and `getent hosts target-vm || nslookup target-vm || echo NO_DNS_ENTRY`."
            ),
        },
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-id", default=f"test-cross-sandbox-{int(time.time())}")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--litellm-api-key", default=None)
    args = ap.parse_args()

    steps = build_steps()
    print(f"built {len(steps)} steps for {args.task_id!r}")
    for s in steps:
        print(f"  {s['id']:<28} {s['type']}")

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
