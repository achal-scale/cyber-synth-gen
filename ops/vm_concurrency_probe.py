#!/usr/bin/env python3
"""VM-concurrency probe -- find WHERE and WHY >5-way pass@k TERMINATEs.

Fires N concurrent ``ModalVmSandboxProvider.create_vm()`` calls -- the EXACT path
the hub's ``deploy_sandbox`` step uses (same provider, same vm_runtime, same args) --
captures each call's success / latency / real exception, then terminates every
sandbox it created.

Why local: the hub swallows the failure as a silent ``TERMINATED`` with no error.
Driving ``create_vm`` directly surfaces the real exception (RateLimit? Resource
Exhausted? timeout?) and lets us sweep concurrency and VM size to tell a count
ceiling apart from a resource/quota ceiling -- WITHOUT the hub, Temporal, a task
bundle, or a 7h run.

Interpreting it against a matching hub run (minimal deploy_sandbox x N task):
  local fails  + hub fails  -> Modal itself (creation limit)
  local works  + hub fails  -> the hub / Temporal orchestration, NOT Modal
  local works  + hub works  -> not creation; it's something in the full task (boot)

Setup:
  * ``aws sso login`` first: agentenvhub_sdk's prod config resolves the Modal token
    from secret ``team/frontier-data/agent-env`` -- the SAME Modal workspace the hub
    uses, so a local pass/fail is comparable to the hub (avoids a wrong-workspace
    false negative).
  * run with a python that has ``agent_env``, ``agentenvhub_sdk`` and ``modal``
    installed (e.g. the agent-env venv with the sdk added).

Examples:
  # Faithful 10-way reproduction (the suspected failure):
  python ops/vm_concurrency_probe.py --n 10

  # Concurrency sweep + repeats (sharp ceiling vs probabilistic flakiness):
  python ops/vm_concurrency_probe.py --sweep 1,3,5,6,7,8,9,10,12 --repeat 3

  # Resource-vs-count: 10 small VMs vs 10 large (if small works, it's a quota, fix=right-size):
  python ops/vm_concurrency_probe.py --n 10 --cpu 1 --memory 2048
  python ops/vm_concurrency_probe.py --n 10 --cpu 4 --memory 8192

  # Isolate PURE creation from the in-VM gateway/dockerd setup:
  python ops/vm_concurrency_probe.py --n 10 --no-setup-gateway
"""
from __future__ import annotations

import argparse
import asyncio
import time
from collections import Counter

# Point agent_env at the hub's PROD config (Modal creds + same workspace) BEFORE
# importing agent_env. Best-effort: if the sdk isn't installed we still run, relying
# on an externally-set AGENT_ENV_CONFIG / Modal env -- but then you may be on a
# different workspace, so a local "it works" is not comparable to the hub.
try:
    import agentenvhub_sdk.bootstrap  # noqa: F401  (sets AGENT_ENV_CONFIG=config.prod.toml on import)

    _CFG = "agentenvhub_sdk.bootstrap (prod config -> hub's Modal workspace)"
except Exception as e:  # noqa: BLE001
    _CFG = (f"WARNING: agentenvhub_sdk NOT loaded ({type(e).__name__}: {e}); "
            "relying on AGENT_ENV_CONFIG/env -- may be a DIFFERENT Modal workspace than the hub")

try:  # 0.9.1300 (what the hub deploys) nests the provider under sandbox_providers/
    from agent_env.providers.sandbox_providers.modal_vm_sandbox import ModalVmSandboxProvider  # noqa: E402
except ModuleNotFoundError:  # bleeding-edge main flattened it to providers/
    from agent_env.providers.modal_vm_sandbox import ModalVmSandboxProvider  # noqa: E402


async def _create_one(provider: ModalVmSandboxProvider, idx: int, args) -> dict:
    """One create_vm call, timed, never raising -- returns its outcome dict."""
    ports = [int(p) for p in args.ports.split(",") if p.strip()] if args.ports else None
    t0 = time.monotonic()
    try:
        sb = await provider.create_vm(
            cpu=args.cpu,
            memory=args.memory,
            timeout=args.timeout,
            exposed_ports=ports,
            setup_for_gateway=args.setup_gateway,
            attribution={"project_id": args.project_id} if args.project_id else None,
        )
        return {"idx": idx, "ok": True, "latency": time.monotonic() - t0,
                "sandbox": sb, "detail": sb.sandbox_id}
    except BaseException as e:  # noqa: BLE001  create_vm self-cleans a half-made sandbox on failure
        return {"idx": idx, "ok": False, "latency": time.monotonic() - t0,
                "sandbox": None, "detail": f"{type(e).__name__}: {e}"}


async def _burst(provider: ModalVmSandboxProvider, n: int, args, label: str) -> tuple[int, int]:
    print(f"\n=== burst {label}: {n} concurrent create_vm "
          f"(cpu={args.cpu}, mem={args.memory}MB, ports={args.ports or 'none'}, "
          f"setup_gateway={args.setup_gateway}, ttl={args.timeout}s) ===")
    results = await asyncio.gather(*[_create_one(provider, i, args) for i in range(n)])
    created = [r["sandbox"] for r in results if r["ok"] and r["sandbox"] is not None]
    try:
        for r in sorted(results, key=lambda r: r["idx"]):
            print(f"  [{r['idx']:>2}] {'OK  ' if r['ok'] else 'FAIL'}  "
                  f"{r['latency']:6.1f}s  {r['detail']}")
        ok = sum(1 for r in results if r["ok"])
        print(f"  -> {ok}/{n} succeeded")
        if ok < n:
            errs = Counter(r["detail"].split(":", 1)[0] for r in results if not r["ok"])
            print(f"  -> failure types: {dict(errs)}")
        return ok, n
    finally:
        # ALWAYS clean up, even on partial failure, so nothing keeps billing.
        if created and not args.keep:
            print(f"  terminating {len(created)} sandbox(es)...")
            res = await asyncio.gather(*[c.terminate() for c in created], return_exceptions=True)
            bad = [r for r in res if isinstance(r, BaseException)]
            if bad:
                print(f"  WARN: {len(bad)} terminate error(s) -- check Modal for orphans: "
                      f"{[c.sandbox_id for c in created]}")
        elif created:  # --keep
            print("  --keep: leaving alive:", [c.sandbox_id for c in created])


async def _main(args) -> None:
    print(f"config: {_CFG}")
    provider = ModalVmSandboxProvider()
    ns = [int(x) for x in args.sweep.split(",")] if args.sweep else [args.n]
    summary: list[tuple[int, int, int, int]] = []
    try:
        for n in ns:
            for rep in range(args.repeat):
                label = f"N={n}" + (f" rep={rep + 1}/{args.repeat}" if args.repeat > 1 else "")
                ok, total = await _burst(provider, n, args, label)
                summary.append((n, rep + 1, ok, total))
    finally:
        try:
            await provider.close()
        except Exception:  # noqa: BLE001
            pass
    print("\n=== SUMMARY (ok/total per burst) ===")
    for n, rep, ok, total in summary:
        flag = "" if ok == total else "   <-- FAILURES"
        print(f"  N={n:>2} rep={rep}: {ok}/{total}{flag}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=10, help="concurrent sandboxes in one burst (default 10)")
    ap.add_argument("--sweep", default=None,
                    help="comma list of N to sweep, e.g. 1,3,5,6,7,8,9,10,12 (overrides --n)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="repeat each burst R times to catch probabilistic failures (default 1)")
    ap.add_argument("--cpu", type=float, default=4.0, help="vCPU per VM (hub uses 4.0)")
    ap.add_argument("--memory", type=int, default=8192, help="MB per VM (hub uses 8192)")
    ap.add_argument("--timeout", type=int, default=300,
                    help="sandbox TTL seconds -- short so any orphan self-reaps fast "
                         "(hub uses 21600; TTL does not affect creation concurrency)")
    ap.add_argument("--ports", default="8080,8000", help="exposed ports CSV (hub uses 8080,8000; '' for none)")
    ap.add_argument("--setup-gateway", dest="setup_gateway", action="store_true", default=True,
                    help="run create_vm's in-VM gateway/dockerd setup (faithful to the hub; default)")
    ap.add_argument("--no-setup-gateway", dest="setup_gateway", action="store_false",
                    help="skip gateway setup to isolate PURE sandbox creation")
    ap.add_argument("--project-id", default="6a97344cdf04bf9f053a4098",
                    help="cost-attribution project id (default: OTS pentest project)")
    ap.add_argument("--keep", action="store_true",
                    help="do NOT terminate created sandboxes (debug; they self-reap at --timeout)")
    args = ap.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
