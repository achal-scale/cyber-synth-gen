# Construction stage 3b/4: fix every QC finding

An earlier stage already fetched the QC tooling and ran it once (see its own
report for the findings). Your only job this stage: fix everything it found
and keep re-running until clean. Final reverification and writing the report
are separate later stages.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Re-run `task_qc_check.py` immediately to see the
CURRENT fail count before redoing any fix -- an earlier attempt's fixes
persist on disk even though its conversation doesn't, so don't re-fix
something already fixed.

```
cd /app/qc-skill/skills/blackbox-pentest-qa/scripts
timeout 300 python3 task_qc_check.py /app/task; echo "exit code: $?"
```

Read every `[FAIL]` AND every `[WARN]` line and its `Fix:` hint -- **do not
only act on `[FAIL]`s.** A `[WARN]` is not optional polish, it is frequently a
real bug the tool simply isn't confident enough to hard-fail on -- examples of
real bugs that surface only as `[WARN]`: hardcoded non-scored service
credentials, a match variable computed but never used in the actual gating
conditional, `reject_when` missing a required calibration category,
`evidence_binding` not tied to the current boot's live state. Fix the actual
underlying issue (not just the symptom) and re-run (same `timeout 300 ...`
wrapper every time). Loop until `task_qc_check.py` exits 0 with zero `[FAIL]`
lines AND you have individually addressed every `[WARN]` line (fixed it, or
are genuinely confident it's a false positive for THIS specific task) -- in
either case, say so explicitly in your final report, with your reasoning per
warning, rather than silently ignoring or suppressing any of them.

Any fix that touches `environment/` requires a fresh reboot to take effect --
**always use the exact `-p construction` project flag**, never a bare
`docker compose down`/`up` without it (this VM's Docker daemon is shared with
other infrastructure outside your task's own containers):

```
cd /app/task/environment
docker compose -p construction down -v --remove-orphans
docker compose -p construction up -d --build --wait
```

The SUPPLEMENTARY section (e.g. MJ12/MJ13 negative/segmentation live-tests)
tells you to probe "from main" -- you're on the VM host, not inside any
container, so run any such live-probe via
`docker compose -p construction exec -T main curl --max-time 3 http://<...>`,
not a bare `curl` (the host isn't on the task's docker networks, so a bare
curl's result there doesn't reflect what `main` actually sees).

Leave the environment running when you finish. State in your final chat
response the final exit code and fail count, and exactly what you fixed (or
confirm it was already clean).
