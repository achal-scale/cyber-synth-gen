# Building one pentest task — the construction steps

This is the per-task methodology: everything between "we picked an (env, vuln_type) pair"
and "this task is a real, shippable Harbor bundle." It's the content side of the pipeline —
separate from `HUB_PIPELINE_PLAN.md`, which is about running an already-built task on the
real hub. Every step below is real engineering work for that one task; none of it is
automated away by a script, by design (see `pipeline-review/new_task.py`'s own docstring —
scaffolding the input contract is the only part that *is* scriptable).

## 1. Choose the (env, vuln_type) pair

Pick a real application and a vulnerability class (IDOR, SQLi, SSRF, XXE, path traversal,
mass assignment, broken function-level authorization, business-logic, web-delivered RCE —
v1 is web-app only). Record the CWE/CVE if this is a real-CVE reintroduction rather than an
organic weakening. Run the scaffolding script against the chosen `(env, vuln_type)` to
produce the skeleton (`task.toml`, the three instruction tiers, empty `environment/` /
`solution/` / `tests/`, a fresh-state descriptor) — this fixes the input contract and removes
boilerplate, nothing more.

## 2. Stand up the base environment, unmodified

Before touching anything security-relevant: get the real, stock application running in its
own environment definition — correct base image (digest-pinned), correct service topology
(whatever the app genuinely needs: a database, an app server, a gateway), correct
healthchecks. Boot it and confirm it's a working, ordinary install of the real app before any
vulnerability work starts. This is the baseline every later step diffs against — if
something breaks later, check it against this known-good state.

## 3. Inject the vulnerability

The real work. Either:
- **Reintroduce a real CVE**: find the upstream patch commit, revert the specific fixed code
  path, and keep everything else at the patched version — name the exact removed check, and
  confirm sibling code paths keep their own checks intact.
- **Organically weaken**: write a new, plausible-looking code path with a real logic flaw,
  not a contrived one a model would recognize as synthetic.

Either way: the vulnerability must be reachable black-box, by a normal low-privilege user,
through the application's real UI/API — not something requiring source access or an
unrealistic starting foothold.

## 4. Wire the per-boot marker + credential system

Every task needs a fresh, random, per-boot secret (the "canary marker") that only the
intended exploit path discloses, plus a way to issue the agent a low-privileged starting
credential. House pattern: an entrypoint step generates a random marker and a scoped
victim/attacker user pair at container start, writes them where the verification layer can
pick them up, and exposes the starting credential via an endpoint the agent is told to fetch.

## 5. Build the exploit-detection + anti-cheat gate

A thin layer in front of the real app (or instrumentation inside it) inspects responses for
the live marker and records *which* code path disclosed it — the technique, the endpoint,
whether it was actually retrieved. This is what makes grading technique-gated rather than
just "did the right string appear anywhere": a model that finds the marker through an
unrelated, off-vector capability must not score a pass just because the value matched.

## 6. Write the oracle (the reference solve)

A real, working exploit script that reproduces the vulnerability end-to-end and recovers the
marker through the *intended* technique — the known-good trajectory every other check is
validated against.

## 7. Write the verifier

Reads the exploit-detection layer's recorded state through an internal, agent-unreachable
channel, gates on the recorded technique matching the expected one **before** comparing the
submitted value to the ground truth (anti-cheat ordering: a correct-looking submission
reached the wrong way must still fail).

## 8. Write the instruction tiers

A consistent house framing across all three tiers: a plausible internal-verification pretext,
explicit authorization context, a reproduction scope, and a reporting contract (exact value,
specific file, no extra text). The tiers differ only in how much is disclosed: the lowest
tier names no endpoint; the middle tier names the general reported area; the top tier names
the exact endpoint(s) and payload shape. Across a batch of tasks: no cross-task noun leakage,
no LLM-tell phrasing, no duplicate ticket/reference numbers — check this mechanically, not
just by eye.

## 9. Validate oracle=1, noop=0, fresh-boot

Run the oracle against a **freshly booted** environment and confirm it scores a pass.
Separately, confirm a no-action / no-exploit trajectory (an agent that does nothing, or only
navigates normally) scores a fail — the verifier must not have a false-positive default. Both
checks must be against a genuinely fresh boot (fresh marker, fresh state), not a reused
container — a stale-state pass is not a real pass.

## 10. Run the gates

- A contract gate: structural correctness (file layout, required metadata fields present,
  schema version).
- An oracle/noop gate: re-runs step 9's checks as an automated gate, not just a manual
  spot-check.
- A sandbox-escape gate: confirms the task doesn't allow trivial sandbox/container escape as
  an unintended win condition.

## 11. Run a cheap pass@1 smoke test before committing to pass@k

One real trial, one cheap model, before spending a full multi-model fleet — catches both
genuine difficulty problems and false fails (a fail despite the agent's own transcript
showing it reached the marker through the intended technique). Classify by grepping the
submitted value against every episode's raw transcript, not the agent's own self-reported
analysis. If pass@1 looks like a false fail, stop, find and fix the root cause, and
re-validate before spending more trials — never burn a full fleet against a known-broken
verifier.

## 12. Run the real pass@k fleet, every model in scope

Once pass@1 is confirmed genuine (pass or fail — a genuine fail is real signal about task
difficulty, not a problem to fix), run the remaining trials to complete the full attempt
budget for each model.

## 13. Package and ship

Assemble the final deliverable bundle. Record any alternate solve paths discovered during
pass@k that weren't the intended technique — documented, not silently ignored, even though
they score a fail under the anti-cheat gate.
