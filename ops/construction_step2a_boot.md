# Construction stage 2a/4: boot the environment

A previous stage (a separate turn, same machine) already wrote the full task
scaffold at `/work/task/` — read `/work/task/task.toml` now to re-orient
yourself before doing anything else. Do not re-do the vulnerability injection
or re-write the scaffold; your only job this stage is getting the stack
booted and healthy. Oracle/noop/negative-control checks are separate later
stages.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Check `docker compose -p construction ps` first
to see if the stack is already built/running from an earlier attempt before
re-running `up --build` from scratch.

```
cd /work/task/environment
docker compose -p construction up -d --build --wait
```

Confirm every service reports healthy before finishing — if the build or the
`--wait` health check hangs or fails, read the actual docker/compose error
output and fix the real cause (a bad Dockerfile, a missing env var, a
healthcheck command that can never pass) rather than waiting indefinitely or
guessing blind. **Always include the exact `-p construction` project flag** on
every `docker compose` call, never a bare `docker compose down`/`up` without it
-- this VM's Docker daemon is shared with other infrastructure outside your
task's own containers, and omitting `-p` lets Compose fall back to an ambient
default project name that can collide with and disrupt containers you don't
own.

Leave the environment running when you finish. State in your final chat
response whether every service is healthy, and anything you had to fix to get
there.
