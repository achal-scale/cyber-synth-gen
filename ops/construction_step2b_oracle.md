# Construction stage 2b/4: oracle check

An earlier stage already booted the stack (`docker compose -p construction ps`
to confirm it's still up -- reboot with `up -d --build --wait` if it isn't).
Your only job this stage: prove the golden path actually reaches the
vulnerability and is graded as a pass.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Check whether `/logs/verifier/reward.txt` already
reads `1` from an earlier attempt before re-running from scratch.

From a position equivalent to the `main` container (you have direct network
access to `http://web:8080` on this VM):

```
cd /work/task
bash solution/solve.sh
SKIP_REPORT_RUBRIC=1 bash tests/test.sh
cat /logs/verifier/reward.txt
```

Confirm it reads `1`. If it doesn't, diagnose the real cause (a bug in
`solution/solve.py`/`solve.sh`, a bug in `tests/test.sh`, or a bug in the
injected vulnerability itself) and fix it, then re-run the same three commands
above until `reward.txt` reads `1`. Do not fake a passing result.

State in your final chat response whether the oracle check passed, and
anything you had to fix to get there.
