#!/usr/bin/env python3
"""Cheap, isolated test of ONE specific question about the real hub platform: can
TWO `deploy_agent` steps (different agent_name, same sandbox) coexist, and can a
THIRD deploy after the first pentest turn finishes, all WITHOUT any manual docker
cleanup in between?

History: v12/v13 of wpii-full-pipeline-1 both failed with "container name
/agent-api already in use". The first theory (concurrent deploy-agent-qwen /
deploy-agent-muse racing) led to a "fix" -- serialize them via a
`docker rm -f agent-api` prompt_agent turn on the construction agent, between the
two branches. Testing that fix in isolation (v1/v2 of this smoke test) DISPROVED
it: deploy-construction-agent + deploy-agent-a coexisted on one sandbox with NO
conflict, and the conflict only appeared right after the `docker rm -f` ran, when
deploy-agent-b tried to redeploy -- strong evidence `agent-api` is a
platform-managed, auto-restarted sidecar, and forcibly removing it is what
*causes* the race, not what fixes it. This version drops the cleanup step
entirely and just sequences agent-b after agent-a's pentest turn finishes
(`depends_on`, no docker command at all):

    deploy-sandbox -> deploy-construction-agent -> deploy-agent-a -> pentest-a
    -> deploy-agent-b -> pentest-b

Both pentest turns are trivial one-shot prompts (run a harmless shell command, echo
the output). If `deploy-agent-b` succeeds cleanly, the real fix for the full
pipeline is just "don't ever run `docker rm -f agent-api`, just serialize the two
branches" -- no cleanup step needed at all.

Usage: python3 ops/build_serialization_smoketest.py --project-id <id> [--publish] [--run --litellm-api-key <key>]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

SANDBOX_NAME = "serialization-test-vm"
CONSTRUCTION_AGENT = "construction-agent"
MODEL = "anthropic/claude-sonnet-5"


def build_steps() -> list[dict]:
    return [
        {
            "id": "deploy-sandbox", "type": "deploy_sandbox",
            "sandbox_name": SANDBOX_NAME, "sandbox_mode": "vm",
            "cpu": 1.0, "memory_mb": 2048, "disk_size_gb": 10,
            "exposed_ports": [8080, 8000], "ttl_seconds": 1800,
        },
        {
            "id": "deploy-construction-agent", "type": "deploy_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": CONSTRUCTION_AGENT,
            "sandbox_name": SANDBOX_NAME, "enable_docker": True,
            "depends_on": [{"task_step_id": "deploy-sandbox"}],
        },
        {
            "id": "deploy-agent-a", "type": "deploy_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": "pentest-a",
            "sandbox_name": SANDBOX_NAME,
            "depends_on": [{"task_step_id": "deploy-construction-agent"}],
        },
        {
            "id": "pentest-a", "type": "prompt_agent", "agent_name": "pentest-a",
            "depends_on": [{"task_step_id": "deploy-agent-a"}],
            "timeout_seconds": 180, "max_turns": 5,
            "prompt_id": "pentest-a", "model": MODEL,
            "prompt": "Run `echo hello-from-a` in your shell and reply with exactly its output, nothing more.",
        },
        {
            "id": "deploy-agent-b", "type": "deploy_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": "pentest-b",
            "sandbox_name": SANDBOX_NAME,
            "depends_on": [{"task_step_id": "pentest-a"}],
        },
        {
            "id": "pentest-b", "type": "prompt_agent", "agent_name": "pentest-b",
            "depends_on": [{"task_step_id": "deploy-agent-b"}],
            "timeout_seconds": 180, "max_turns": 5,
            "prompt_id": "pentest-b", "model": MODEL,
            "prompt": "Run `echo hello-from-b` in your shell and reply with exactly its output, nothing more.",
        },
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-id", default=f"test-pentest-serialization-{int(time.time())}")
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
    print(out)
    if status not in (200, 201):
        raise SystemExit("publish failed")

    if args.run:
        if not args.litellm_api_key:
            raise SystemExit("--run needs --litellm-api-key")
        status, out = hub.run_task(args.task_id, args.project_id, litellm_api_key=args.litellm_api_key)
        print(f"\nrun_task -> HTTP {status}")
        print(out)


if __name__ == "__main__":
    main()
