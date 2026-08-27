# Problems and Blockers

| ID | Status | Evidence and likely cause | Safe next action |
| --- | --- | --- | --- |
| P-001 | RESOLVED | Kuwait `main` baseline had one stale control branch expectation after the previous task was marked complete. | Today's task uses the actual work branch; control and full-suite gates pass without weakening the assertion. |
| P-002 | RESOLVED_FOR_LOCAL_TEST | System Python lacked `jsonschema`, causing eight environment errors in an exploratory run. | Use ignored `.venv` with declared test extras; do not change dependency contracts without need. |
| P-003 | BLOCKED | Final repositories expose no required GitHub Secrets or variables. | Build fail-closed workflows and document exact required names; owner supplies values later. |
| P-004 | OPEN_RISK | PRoot cannot access the existing tmux socket although the process is visible. | Keep the current process and wake lock; do not create competing build sessions. |
| P-005 | OPEN_RISK | Existing PRoot binds expose phone storage. | Restrict writes to workspace and keep credentials/runtime evidence out of Git. |
| P-006 | DOCUMENTED | Contract says 15 Drive subfolders but enumerates and currently contains 16. | Treat the 16 exact names as authoritative; do not delete any folder. |
| P-007 | BLOCKED | No reconciled Kuwait issuer universe or admitted historical event corpus exists yet. | Complete schema/source admission before collection or evaluation. |
| P-008 | OPEN | Public migration artifacts disagree: a 14-job catalog says bound/reimplemented while the preparation parity files say all jobs are not started; canonical filesystem gaps remain. | Treat the exact runtime audit as the new denominator and reimplement/test each missing user job incrementally. |
| P-009 | DOCUMENTED | A private-history test copying `.git` packs failed under the original PRoot worktree. | Isolated exact-HEAD clone passed all 48 tests; retain both results as environment evidence. |
| P-010 | RESOLVED | Initial wheel command lacked `setuptools.build_meta`, then continued because shell fail-fast was absent. | Re-ran with `set -euo pipefail` and isolated pinned build dependencies; build/install/CLI smoke passed. |
| P-011 | RESOLVED | Review found rejected rows could be reflected verbatim in quarantine reports, potentially echoing a signed URL or credential. | Quarantine now emits bounded identifiers and a digest only; negative test and Secret Guard pass. |
