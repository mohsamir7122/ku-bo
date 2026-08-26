# CURRENT TASK — KU-BO-2026-08-26-INTEGRATION

```text
TASK_ID: KU-BO-2026-08-26-INTEGRATION
STATUS: COMPLETED
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: 59833bf73510b3aa3901f628cbf2c13c0d01cf79
EXPECTED_NEW_BRANCH: main
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
HISTORICAL_CORPUS_COLLECTION_REQUESTED: NO
BLOCKED_ON: NONE; TASK_COMPLETED_IN_MAIN
CONTROL_FILES: docs/codex/HANDOFF_TEMPLATE.md; docs/codex/USER_DECISIONS.md
MERGE_GUARD: Do not merge until exact-head CI and every Section 8 gate pass.
MIGRATION_CONTROL_REFERENCE: KU-BO-MIG-001
LEGACY_MIGRATION_CONTROL_BRANCH: agent/private-predecessor-capability-migration-v1
EXPECTED_PR_BASE: agent/ku-bo-016-codex-live-bootstrap
PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: YES
PRIVATE_RUNTIME_DATA_ACCESS_ALLOWED: NO
```

## Mission

Integrate the unique, auditable capabilities of Kuwait PRs #19 and #20, then
the migration controls in #21 and guarded orchestration in #22, into one
canonical KU-BO branch above the verified `main` SHA. Preserve the existing
fail-closed research boundaries and leave old repositories as migration-only
sources.

## Required integration

1. Recreate the clean #19 → #20 path.
2. Compare #21 and #22 against #20 and retain only unique, non-conflicting
   capabilities; do not perform a blind PR merge.
3. Review PRs #17, #18, #2, and #3 for unique capability only and leave them
   unchanged.
4. Keep private source locators, credentials, raw market evidence, and Drive
   identifiers outside this public repository.
5. Run deterministic synthetic dry-run, unit/integration/property tests,
   package checks, Secret Guard, and exact-head CI.

## Acceptance gates

1. Every migrated capability is locked to repository, branch, PR, and exact
   source SHA in private runtime evidence and summarized without secrets.
2. `git diff` is reviewed and contains no unintended files or credentials.
3. Baseline and candidate tests are recorded; no gate is weakened.
4. The dry-run produces a valid, replayable receipt and preserves failures.
5. Exact-head CI is green on the candidate SHA.
6. Privacy, licensing, robots/access, and claim-boundary checks pass.
7. A rollback path, changelog/status update, and merge receipt are prepared.

## Safety and non-claims

- This remains a research and analysis system; it does not place orders or
  move money.
- No live source is promoted merely because it is catalogued or reachable.
- Synthetic fixtures prove software behavior only, not prediction quality,
  accuracy, full-market coverage, or live readiness.
- Do not bypass login, CAPTCHA, paywalls, robots controls, rate limits, or
  licensing restrictions.
- Do not merge, force-push, delete, expose secrets, or weaken gates while this
  control surface says `MERGE_ALLOWED: NO`; the separate user decision permits
  only a conditional merge after all contract gates pass.

Write the final result using `docs/codex/HANDOFF_TEMPLATE.md` and record the
exact candidate SHA, CI, receipts, unresolved blockers, and status.
