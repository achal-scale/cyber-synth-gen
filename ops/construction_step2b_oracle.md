# Construction stage 2b/4: oracle check

An earlier stage already booted the stack (`docker compose -p construction ps`
to confirm it's still up -- reboot with `up -d --build --wait` if it isn't).
Your only job this stage: prove the golden path actually reaches the
vulnerability and is graded as a pass.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Check whether `/logs/verifier/reward.txt` already
reads `1` from an earlier attempt before re-running from scratch.

You are on the VM host, NOT inside any task container -- `web`/`main` are not
reachable by hostname and `/vchan`/`/logs/verifier` are not real host paths.
Run everything through `main` instead, which has the real network access and
the right mounts (`environment/docker-compose.yaml` bind-mounts the whole task
dir into `main` at `/app/task` for exactly this):

```
cd /app/task/environment
mkdir -p /app/task/trajectories/oracle
docker compose -p construction exec -T main bash -c "cd /app/task && bash solution/solve.sh"
docker compose -p construction exec -T main bash -c "cd /app/task && SKIP_REPORT_RUBRIC=1 bash tests/test.sh" 2>&1 | tee /app/task/trajectories/oracle/test.log
docker compose -p construction exec -T main cat /logs/verifier/reward.txt | tee /app/task/trajectories/oracle/reward.txt
docker compose -p construction exec -T main cat /logs/verifier/reward.json > /app/task/trajectories/oracle/reward.json
```

Confirm `reward.txt` reads `1`. If it doesn't, diagnose the real cause (a bug in
`solution/solve.py`/`solve.sh`, a bug in `tests/test.sh`, or a bug in the
injected vulnerability itself) and fix it, then re-run the same four commands
above until `reward.txt` reads `1`. Do not fake a passing result. **The
`trajectories/oracle/{test.log,reward.txt,reward.json}` files must end up
non-empty and reflecting this final passing run** -- a QC check on the
finished task requires real evidence of the oracle pass, not just a verbal
claim.

State in your final chat response whether the oracle check passed, and
anything you had to fix to get there.
