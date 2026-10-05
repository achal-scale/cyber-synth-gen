# tasks_built/

Real tasks built through this repo's own generation process (`pipeline-review/new_task.py` ->
populate -> `ops/qc_recheck.py` / `ops/package_deliverable.py`), as opposed to the
`cyber-sample-tasks` repo's existing, independently-built batch_01/QH1 tasks.

| Task | Status |
| --- | --- |
| `dolibarr-idor` | Built by porting real, already-verified content from `cyber-sample-tasks/batch_01/dolibarr-A1-idor` to prove the generation process end-to-end; re-verified fresh (not trusting the ported trajectories) via a real boot/oracle/noop run. Passes `qc_recheck.py --skip-fleet`. Not yet fleeted (no `--agent-cmd` harness to run pass@k). |
