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
| P-012 | RESOLVED | First real KCC probe crashed before access because the pinned HTTPS handler forwarded a removed `check_hostname` argument on Python 3.12. | Removed the obsolete argument while retaining default certificate/hostname verification; regression and full-suite tests pass. |
| P-013 | BLOCKED | Safe direct probes for KCC and the Boursa reports archive could not retrieve a usable robots policy and returned `ROBOTS_POLICY_UNAVAILABLE`. | Keep both sources unadmitted; use only an explicitly authorized route or user-supplied authorized export, never a bypass. |
| P-014 | RESOLVED | A post-documentation focused check was first invoked with `pytest`, but the isolated runtime intentionally has no pytest module (`No module named pytest`). No test was started by that command. | Re-ran the same six files with the repository's canonical `unittest` runner; 109/109 tests passed. |
