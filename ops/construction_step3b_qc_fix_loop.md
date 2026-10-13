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
cd /work/qc-skill/skills/blackbox-pentest-qa/scripts
timeout 300 python3 task_qc_check.py /work/task; echo "exit code: $?"
```

Read every `[FAIL]` line and its `Fix:` hint. Fix the actual underlying issue
(not just the symptom) and re-run (same `timeout 300 ...` wrapper every time).
Loop until `task_qc_check.py` exits 0 with zero `[FAIL]` lines, or until you
are confident a remaining `[FAIL]`/`[WARN]` is a false positive -- in which
case say so explicitly in your final report, with your reasoning, rather than
silently suppressing it.

Any fix that touches `environment/` requires a fresh reboot to take effect --
**always use the exact `-p construction` project flag**, never a bare
`docker compose down`/`up` without it (this VM's Docker daemon is shared with
other infrastructure outside your task's own containers):

```
cd /work/task/environment
docker compose -p construction down -v --remove-orphans
docker compose -p construction up -d --build --wait
```

Leave the environment running when you finish. State in your final chat
response the final exit code and fail count, and exactly what you fixed (or
confirm it was already clean).
