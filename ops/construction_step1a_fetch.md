# Construction stage 1a/7: fetch starting materials

You are the construction agent for one black-box web-security task in the project's
B/R (behavior + report) format. You have full shell access on this VM. Work
autonomously end to end; do not stop to ask questions. This is stage 1a of a
multi-stage construction process -- fetch the base application source only. Do
NOT inject the vulnerability, write any scaffold file, or boot docker-compose in
this stage; later stages do that.

**If this turn times out, you will be re-invoked as a brand-new conversation with
no memory of this one.** Before doing any work, check `/app/task/environment`
for directories already fetched by an earlier attempt and skip re-fetching ones
that already exist and look complete.

**Application**: {APP_DESCRIPTION}

```
mkdir -p /app/task/environment
cd /app/task/environment || { echo "FATAL: /app/task/environment does not exist after mkdir -- do not continue, investigate why (permissions? /app not writable? a pre-existing file at /app?) and report the real error"; exit 1; }
pwd   # MUST print /app/task/environment -- if it doesn't, stop and fix this before going any further
{BASE_CONTEXT_FETCH_COMMANDS}
```

**Every remaining stage in this pipeline hardcodes the absolute path
`/app/task/...`.** If the `pwd` above doesn't print `/app/task/environment`,
every later stage (including ones run by a completely different, fresh agent
with no memory of this conversation) will silently look in the wrong place
and fail. Do not improvise a different location and continue anyway -- if
`/app` genuinely cannot be created or written to, STOP and state that exact
error in your final chat response instead of working around it silently.

Each directory you just populated is one service's **pre-injection** source (no
vulnerability yet) and its own Dockerfile -- treat it as a real application you
are auditing, not a toy.

**If you add a brand-new service** (not one you fetched above -- e.g. a gateway
this application didn't already have), its Dockerfile's `COPY` instructions must
use a `*/` wildcard prefix for anything copied from the build context root, e.g.
`COPY */requirements.txt .` and `COPY */ .` instead of `COPY requirements.txt .` /
`COPY . .`. This is not a style preference: a later pipeline stage packages each
service as a GitHub archive zip to build it on real hub infrastructure, and
GitHub's archive format always wraps the content in one extra directory -- a
plain (non-wildcard) `COPY` can't see past that wrapper and the build fails with
"file not found". The directories you fetched above already have this fix; only
apply it yourself for services you create from scratch.

When every base-context directory exists and looks complete, state so in your
final chat response. Do not do anything else this stage.
