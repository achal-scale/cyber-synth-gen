#!/usr/bin/env python3
"""Cheap test of whether a non-claude-code-cli harness avoids the
`context_management`/fireworks_ai incompatibility seen with claude-code-cli.

Context: pentest-qwen (via claude-code-cli) fails with
    litellm.UnsupportedParamsError: fireworks_ai does not support parameters:
    ['context_management']
This is the Anthropic beta "context management"/auto-compact feature the
`claude` CLI binary always sends when talking to its configured
ANTHROPIC_BASE_URL, regardless of which model is actually behind it --
litellm then tries (and fails) to forward it to Fireworks. codex-cli and
opencode-cli are OpenAI-completions-style harnesses (not Anthropic-native),
so they should never add this Anthropic-specific beta param in the first
place. Each harness gets its OWN VM sandbox (one agent per VM -- see
build_full_pipeline_task.py's _pentest_attempt_steps docstring), so this
publishes 2 independent sandbox+agent+prompt chains, both fail_task_on_error
so both get tried regardless of the other's outcome.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

MODEL = "fireworks_ai/qwen3p8-2p4t-a95b"

CANDIDATES = [
    ("qwen-f-codex", "codex-cli"),
    ("qwen-g-opencode", "opencode-cli"),
]


def build_steps() -> list[dict]:
    steps = []
    for label, harness in CANDIDATES:
        sandbox_id = f"deploy-sandbox-{label}"
        deploy_id = f"deploy-agent-{label}"
        sandbox_name = f"vm-{label}"
        agent_name = f"agent-{label}"
        steps.append({
            "id": sandbox_id, "type": "deploy_sandbox",
            "sandbox_name": sandbox_name, "sandbox_mode": "vm",
            "cpu": 1.0, "memory_mb": 2048, "disk_size_gb": 10,
            "exposed_ports": [8080, 8000], "ttl_seconds": 1800,
        })
        steps.append({
            "id": deploy_id, "type": "deploy_agent",
            "a2a_agent_id": harness, "agent_name": agent_name,
            "sandbox_name": sandbox_name,
            "depends_on": [{"task_step_id": sandbox_id}],
        })
        steps.append({
            "id": f"try-{label}", "type": "prompt_agent", "agent_name": agent_name,
            "depends_on": [{"task_step_id": deploy_id}],
            "timeout_seconds": 90, "max_turns": 2,
            "prompt_id": f"try-{label}",
            "model": MODEL,
            "effort": "xhigh",
            "prompt": "Reply with exactly the text OK, nothing more.",
            "fail_task_on_error": False,
        })
    return steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-id", default=f"test-harness-strings-{int(time.time())}")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--litellm-api-key", default=None)
    args = ap.parse_args()

    steps = build_steps()
    print(f"built {len(steps)} steps for {args.task_id!r}")
    for s in steps:
        print(f"  {s['id']:<24} {s['type']:<14} model={s.get('model','')}")

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
