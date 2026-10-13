# Construction stage 3c/4: final oracle/noop reverification

An earlier stage already fixed every real QC finding. Your only job this
stage: make sure none of those fixes broke what stage 2 already proved. Skip
this if the QC stage made no changes to `environment/`, `tests/test.sh`, or
`solution/` (say so and move on) -- it only matters when a fix could plausibly
affect the vulnerability path.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Check `/logs/verifier/reward.txt` for a result
already produced by an earlier attempt before re-running from scratch.

From a fresh boot (**always use the exact `-p construction` project flag**,
never a bare `docker compose down`/`up` without it):

```
cd /work/task/environment
docker compose -p construction down -v --remove-orphans
docker compose -p construction up -d --build --wait
cd /work/task
bash solution/solve.sh
SKIP_REPORT_RUBRIC=1 bash tests/test.sh
cat /logs/verifier/reward.txt   # must read 1
docker compose -p construction down -v --remove-orphans
docker compose -p construction up -d --build --wait
SKIP_REPORT_RUBRIC=1 bash tests/test.sh
cat /logs/verifier/reward.txt   # must read 0
```

If either check now fails, your QC-stage fix broke something -- go back and
fix the real regression (don't just revert the QC fix; find a change that
satisfies both the QC finding and oracle/noop). Repeat until both pass.

Leave the environment running when you finish. State in your final chat
response whether oracle/noop still both pass after the QC fixes.
