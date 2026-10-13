# Construction stage 2c/4: noop check

Earlier stages already booted the stack and confirmed the oracle (golden path)
passes. Your only job this stage: prove that doing NOTHING does not
accidentally pass -- the vulnerability must require real exploitation, not be
trivially satisfied by a fresh boot alone.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Check `/logs/verifier/reward.txt` for a result
already produced by an earlier attempt before re-running from scratch.

This check needs a FRESH reboot (the marker/verifier token must be
regenerated, and any state the oracle check's own exploitation left behind
must be cleared) -- always use the exact `-p construction` project flag, never
a bare `docker compose down`/`up` without it, since this VM's Docker daemon is
shared with other infrastructure outside your task's own containers:

```
cd /work/task/environment
docker compose -p construction down -v --remove-orphans
docker compose -p construction up -d --build --wait
cd /work/task
SKIP_REPORT_RUBRIC=1 bash tests/test.sh
cat /logs/verifier/reward.txt
```

Take NO exploitation action between the reboot and running `tests/test.sh`.
Confirm `reward.txt` reads `0`. If it doesn't (the task is passing without any
real work), diagnose and fix the actual bug -- a leaked default value, a
too-permissive initial state, or a verifier/test.sh logic error -- then re-run
the full reboot-and-check sequence above until it reads `0`. If your fix could
plausibly affect the oracle path too (e.g. you changed `tests/test.sh` or the
vulnerable endpoint itself, not just an unrelated default), also re-run
`solution/solve.sh` + `SKIP_REPORT_RUBRIC=1 bash tests/test.sh` once more from
this same fresh boot and confirm `reward.txt` reads `1` before moving on --
don't let a noop fix silently break the oracle stage 2b already proved.

Leave the environment running when you finish (do not tear it down after this
check) -- a later stage attacks it directly. State in your final chat response
whether the noop check passed, and anything you had to fix to get there.
