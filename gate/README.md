# Gates

Four gates, run in this order. Each is a GATE: a deliberate stop raises a `GATE-STOP:`-prefixed
message, told apart from an ordinary exception the same way synth-gen's `gate_reject.py` does it
— a stop is a verdict about the task, not breakage in the pipeline itself.

| Order | Gate | Fails on |
| --- | --- | --- |
| 1 | `contract_gate.py` | Any of the structural rubric checks (house instruction template present at all 3 tiers, `unintended_findings.json` present, no bolted-on synthetic endpoint, digest-pinned images, vendored tarballs with sha256, credential hygiene, no debug/stack-trace exposure) |
| 2 | `oracle_noop_gate.py` | Oracle (`solution/solve.sh`) does not score reward=1, or noop scores anything but reward=0, or a documented alternate path in `unintended_findings.json` turns out to score |
| 3 | `sandbox_escape_gate.py` | Any task-container hardening check fails (see below) — this is the gate synth-gen has no equivalent of |
| 4 | `fleet_gate.py` | The single-model pass@5 fleet run is short, capped, or the task itself got flagged blocked mid-run (see `fleet_gate.py` docstring) |

A failure at gate 1 or 2 means the task is broken and goes back to the construction loop, not to
review. A failure at gate 3 is a hardening defect in the environment definition, fixed the same
way. Gate 4 failing with `bundle-blocked` also routes back to construction — only `attempt-cap`
is a genuine difficulty signal, not a defect.

## Status

`contract_gate.py` and `oracle_noop_gate.py` wrap the existing checks from
`cyber-sample-tasks/tools/rubric_pipeline.py` — logic is reused, not rewritten. `sandbox_escape_gate.py`
is new. `fleet_gate.py` is adapted from synth-gen's `gate_fleet.py` shape, reduced to v1's
single-model, non-resumable scope — `--continue-legs`-style resumption is not implemented yet.
