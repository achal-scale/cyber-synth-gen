# Construction stage 2/3: boot and validate

A previous stage (a separate turn, same machine) already wrote the full task
scaffold at `/work/task/` — read `/work/task/task.toml` and
`/work/task/tests/test.sh` now to re-orient yourself before doing anything else.
Do not re-do the vulnerability injection or re-write the scaffold; your job this
stage is purely to boot it and prove oracle=1/noop=0. Do not run any quality-check
tooling in this stage — that is a separate later stage.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Check `docker compose -p construction ps` first
to see if the stack is already built/running from an earlier attempt before
re-running `up --build` from scratch.

```
cd /work/task/environment
docker compose -p construction up -d --build --wait
```

Confirm every service reports healthy before proceeding — if the build or the
`--wait` health check hangs or fails, read the actual docker/compose error output
and fix the real cause (a bad Dockerfile, a missing env var, a healthcheck command
that can never pass) rather than waiting indefinitely or guessing blind.

From a position equivalent to the `main` container (you have direct network access
to `http://web:8080` on this VM):

- **Oracle**: run `solution/solve.sh` against the booted stack, then run
  `tests/test.sh` with `SKIP_REPORT_RUBRIC=1`. Confirm `reward.txt` reads `1`.
- **Noop**: reboot the stack fresh (`docker compose -p construction down -v
  --remove-orphans` then `docker compose -p construction up -d --build --wait`
  again, so the marker is regenerated), take no action, run `tests/test.sh` with
  `SKIP_REPORT_RUBRIC=1`. Confirm `reward.txt` reads `0`.
- **Negative control**: confirm the sibling endpoint(s) you documented in
  `unintended_findings.json` do *not* disclose the flag.

If either check fails, fix the task (environment, test.sh, or solve.py — whichever
is actually wrong) and re-run both from a fresh boot until they pass. Do not fake a
passing result. **Always include the exact `-p construction` project flag** on
every `docker compose` call, never a bare `docker compose down`/`up` without it —
this VM's Docker daemon is shared with other infrastructure outside your task's
own containers, and omitting `-p` lets Compose fall back to an ambient default
project name that can collide with and disrupt containers you don't own.

Leave the environment running when you finish (do not tear down docker compose) --
a later stage attacks it directly. State in your final chat response whether
oracle/noop/negative-control all passed, and anything you had to fix to get there.
