# Construction stage 3a/4: fetch QC tooling, run the first check

Earlier stages already wrote the task scaffold at `/work/task/` and confirmed
it boots with oracle=1/noop=0 (the environment is still running -- do not tear
it down or reboot it). Your only job this stage: fetch the quality-check
tooling and run it once to see where things stand. Fixing anything it finds is
a separate later stage.

**If this turn times out, you will be re-invoked as a brand-new conversation
with no memory of this one.** Check whether `/work/qc-skill/` already exists
before re-fetching it.

```
mkdir -p /work/qc-skill
curl -fsSL "{QC_SKILL_ZIP_URL}" -o /tmp/qc-skill.zip && unzip -q /tmp/qc-skill.zip -d /tmp/qc-skill-extract
cp -r /tmp/qc-skill-extract/*/. /work/qc-skill/
```

Run it once, under a hard wall-clock timeout (some of its checks call out to an
LLM judge, and if that call hangs or can't authenticate for any reason, the
bare command would otherwise block indefinitely):

```
cd /work/qc-skill/skills/blackbox-pentest-qa/scripts
timeout 300 python3 task_qc_check.py /work/task; echo "exit code: $?"
```

Exit code `124` means it hit the 5-minute timeout, not that it actually
finished -- note that explicitly. The script does not require
`ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL` to be set yourself -- check your own
environment (`env | grep -i anthropic`) first; if they're genuinely absent,
that's fine to note and move on with static checks only.

Do NOT fix anything yet. State in your final chat response the exact exit code
and every `[FAIL]`/`[WARN]` line this first run produced (or "none" if it
passed clean).
