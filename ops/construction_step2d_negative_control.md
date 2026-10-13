# Construction stage 2d/4: negative control check

Earlier stages already booted the stack and confirmed oracle=1/noop=0. Your
only job this stage: confirm the sibling endpoint(s) you documented in
`unintended_findings.json` as "checked and closed" really are closed, not just
documented as such.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Check your own earlier notes/test output under
`/work/task/` for a result already produced by an earlier attempt before
re-running from scratch.

Read `/work/task/unintended_findings.json`, then exercise each documented
negative-control endpoint directly (the same way the real vulnerability is
exercised, but against the sibling path) and confirm none of them disclose the
protected value.

If one of them DOES leak (the negative control is wrong, or the access control
on that sibling path has the same flaw), fix the actual access-control bug on
that endpoint, re-verify it's closed, and re-run the oracle check
(`solution/solve.sh` + `SKIP_REPORT_RUBRIC=1 bash tests/test.sh`, confirm
`reward.txt` reads `1`) to make sure your fix didn't also break the real
vulnerability path.

State in your final chat response whether every negative control is
confirmed closed, and anything you had to fix to get there.
