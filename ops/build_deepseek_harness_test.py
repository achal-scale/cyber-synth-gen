#!/usr/bin/env python3
"""Cheap test of which harness (if any) can actually carry
"openai/azure_ai/DeepSeek-V4-Flash" on THIS hub platform before trusting it
in a real pass@10 run. Same pattern as build_model_string_test.py's qwen
harness discovery (claude-code-cli's `claude` CLI sends an Anthropic-beta
`context_management` param litellm can't forward to a non-Anthropic-routed
model -- codex-cli/opencode-cli, being OpenAI-completions-style harnesses,
should avoid that specific incompatibility, but this has NOT been confirmed
for DeepSeek/azure_ai specifically, only for qwen/fireworks_ai).

Each candidate harness gets its OWN sandbox+agent, both fail_task_on_error
so both get tried regardless of the other's outcome.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

MODEL = "openai/azure_ai/DeepSeek-V4-Flash"

CANDIDATES = [
    ("ds-a-claudecode", "claude-code-cli"),
    ("ds-b-opencode", "opencode-cli"),
    ("ds-c-codex", "codex-cli"),
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
            "fail_task_on_error": False,
        })
        steps.append({
            "id": f"try-{label}", "type": "prompt_agent", "agent_name": agent_name,
            "depends_on": [{"task_step_id": deploy_id}],
            "timeout_seconds": 90, "max_turns": 2,
            "prompt_id": f"try-{label}",
            "model": MODEL,
            "prompt": "Reply with exactly the text OK, nothing more.",
            "fail_task_on_error": False,
        })
    return steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-id", default=f"test-deepseek-harness-{int(time.time())}")
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
