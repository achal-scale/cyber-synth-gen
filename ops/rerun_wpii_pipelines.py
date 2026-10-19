#!/usr/bin/env python3
"""Re-publish + re-run wpii-full-pipeline-1 (w-social, w-backend) and
wpii-full-pipeline-2 (Dolibarr), same app_description/base_contexts/vuln_spec
as always, now through the NEW single-model pass@10 architecture (DeepSeek,
azure_ai/DeepSeek-V4-Flash + opencode-cli -- verified live this session via
build_deepseek_harness_test.py's v2 follow-up), with every fix made this
session: collect_artifacts/sandbox_name, no [environment.healthcheck], DNS01
hostname-i self-publish, vendored agent/Dockerfile wheels, presence-based
test.sh behavior gate, fresh-per-boot service credentials, fully-bare
instruction_L0.md, max_turns=100 (not a wall-clock limit) per pass@k attempt.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402
import build_full_pipeline_task as gen  # noqa: E402

PROJECT_ID = "6a97344cdf04bf9f053a4098"

PIPELINES = {
    "wpii-full-pipeline-1": dict(
        app_description=(
            "a first-party FastAPI + SQLAlchemy social platform ('w'), an X-clone "
            "with posts/follows/DMs"
        ),
        base_contexts={
            "w-backend": "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-base-w-backend.zip",
            "gateway": "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-base-gateway.zip",
            "seed-init": "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-wpii-seed-init.zip",
        },
        vuln_spec=(
            "Inject a CWE-213 (Exposure of Sensitive Information Due to Incompatible "
            "Policies) vulnerability into the 'w' social platform: a user-facing API "
            "endpoint that, through an interaction of otherwise-reasonable "
            "access-control decisions, leaks another user's private data (e.g. DMs, "
            "private account details, or deactivated/blocked-account content) to an "
            "unauthorized caller without any single obviously-broken check. The "
            "vulnerability should require chaining 2+ legitimate-looking API "
            "calls/response fields to exploit, not a single missing auth check."
        ),
    ),
    "wpii-full-pipeline-2": dict(
        app_description=(
            "Dolibarr, a real open-source PHP ERP/CRM business-management suite "
            "exposing customer, invoice, and product management through a web "
            "gateway and an internal API service"
        ),
        base_contexts={
            "dolibarr-app": "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-base-dolibarr-app.zip",
            "gateway": "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-base-dolibarr-gateway.zip",
            "internal-service": "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-base-dolibarr-internal.zip",
        },
        vuln_spec=(
            "Inject a CWE-862 (Missing Authorization) vulnerability into Dolibarr's "
            "invoice/customer management API: a user-facing endpoint that, through an "
            "interaction of otherwise-reasonable access-control decisions (e.g. a "
            "correctly-scoped primary lookup endpoint plus a separate "
            "export/pagination/related-records endpoint that re-trusts an identifier "
            "from the first response without re-checking tenant/company ownership), "
            "lets an authenticated low-privilege user read another company's or "
            "user's invoice/customer records without any single obviously-missing "
            "auth check. The vulnerability must require chaining 2+ legitimate-"
            "looking API calls, not a single missing @role check."
        ),
    ),
}

COMMON = dict(
    model=gen.DEEPSEEK_MODEL, model_label="deepseek", harness=gen.DEEPSEEK_HARNESS,
    effort=None, attempts=10, max_turns=100,
    construction_model="anthropic/claude-sonnet-5",
)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--litellm-api-key", required=True)
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--only", choices=["wpii-full-pipeline-1", "wpii-full-pipeline-2"], default=None)
    args = ap.parse_args()

    targets = [args.only] if args.only else list(PIPELINES)
    for task_id in targets:
        cfg = PIPELINES[task_id]
        print(f"\n=== {task_id} ===")
        steps = gen.build_steps(
            task_id, cfg["app_description"], cfg["base_contexts"], cfg["vuln_spec"],
            COMMON["model"], model_label=COMMON["model_label"], harness=COMMON["harness"],
            effort=COMMON["effort"], attempts=COMMON["attempts"], max_turns=COMMON["max_turns"],
            construction_model=COMMON["construction_model"],
            sandbox_suffix=f"{task_id.replace('wpii-full-pipeline-', 'p')}-{int(time.time())}",
        )
        print(f"built {len(steps)} steps")
        for s in steps:
            if s["type"] == "collect_artifacts":
                print(f"  {s['id']:<24} sandbox_name={s.get('sandbox_name')!r} "
                      f"base_path={s.get('base_path')!r} artifact_paths={s.get('artifact_paths')!r}")

        if not args.publish:
            print("--publish not given: nothing sent.")
            continue

        status, out = hub.publish_task(task_id, PROJECT_ID, steps)
        print(f"publish -> HTTP {status}")
        if status not in (200, 201):
            raise SystemExit(out)

        if args.run:
            status, out = hub.run_task(task_id, PROJECT_ID, litellm_api_key=args.litellm_api_key)
            print(f"run_task -> HTTP {status}")
            print(out)


if __name__ == "__main__":
    main()
