# CURRENT TASK - KU-BO-017

```text
TASK_ID: KU-BO-017
STATUS: READY
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: agent/ku-bo-016-codex-live-bootstrap
CONTROL_BASE_SHA: VERIFY_REMOTE_BRANCH_HEAD_AT_START
EXPECTED_NEW_BRANCH: agent/ku-bo-017-live-dry-run-orchestrator
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
LIVE_SOURCE_COLLECTION_REQUESTED: PRIVATE_DRIVE_INVENTORY_AND_AUTHORIZED_ACCESS_PROBE_ONLY
BLOCKED_ON: FACTOR9_ADMISSION; OFFICIAL_POINT_IN_TIME_DATA; RIGHTS_REVIEW; APPROVED_CHAMPION_FREEZE; MODEL_VALIDATION
```

## Mission

Turn the locked Codex handoff into a resumable private-data inventory and a
fail-closed daily **dry-run** orchestrator. Inspect `AI Rebuild` through the
authorized connector, admit no Factor 9 artifact without its gates, and prove the
run order and previous-freeze controls without training a model, collecting an
unauthorized site, or issuing a stock recommendation.

## Required sequence

1. Verify remote/base/HEAD/PR/CI and run the bootstrap validator before editing.
2. Discover `AI Rebuild` at runtime without persisting private IDs in Git.
3. Inventory the KU-BO-relevant Drive candidates privately by hash, size,
   provenance, source role, rights state, and point-in-time review state.
4. Write a private Factor 9 admission manifest/report. Preserve existing artifacts;
   do not recrawl Mubasher or recompute the old Factor 9 score.
5. Implement a no-network Daily dry-run orchestrator with run locking, explicit
   stage receipts, resumable checkpoints, no-overwrite output, and fail-closed
   stage dependencies.
6. Require `schemas/champion-freeze-manifest.schema.json` and
   `kubo.champion_freeze` before the Champion stage; reject same-day approval,
   same-day Challenger use, product/horizon mismatch, and unbound hashes.
7. Keep source probes inside the existing authorized access-recipe workflow. A
   probe is access evidence only and never market evidence.
8. Keep the 15:07/15:37 scheduled shadow disabled by default. Manual dry-run may
   validate contracts but cannot collect data, train, rank stocks, or publish a
   daily recommendation.
9. Produce the proposed KU-BO-018 event-admission/trial-registry task for the 50
   major plus 200 control events; do not start training in KU-BO-017.

## User-authorized scope extension - 2026-08-25

1. Lock KU-BO to Boursa Kuwait only. Do not include an additional market adapter,
   corpus, methodology entry, training path, evaluation path, or runtime override.
2. Inspect the private predecessor read-only and translate useful user jobs into
   the canonical `kubo` package. Do not merge its Git history, execute its engine,
   copy private data, or publish its locator or revision details.
3. Bind the admitted user jobs through a sanitized capability-parity manifest and
   callable-resolution tests.
4. Add semantic source fallback that separates transport success from usable
   evidence, preserves access controls, and queues original-source verification.
5. Add point-in-time portfolio and order validation with evidence-byte hashes,
   freshness, and reconciliation. Keep it structurally non-actionable.
6. Add one repository-local Codex routing skill rather than parallel copies of
   predecessor skills.

## Acceptance gates

1. Bootstrap, schema, strict semantic, privacy, and control checks pass.
2. Private Drive inventory is resumable and hash-bound, with no private identifier
   or byte committed to Git.
3. Factor 9 report reconciles 534,135 raw, 533,997 clean, and 138 excluded rows,
   and keeps 243 issue flags distinct from excluded-row count.
4. Every Factor 9 blocker and seven admission gates has an explicit status; unknown
   or failed status cannot promote an artifact.
5. Dry-run stage order is exact, append-only/no-overwrite, and restart-safe.
6. A missing, same-day, future-effective, Challenger, or forged freeze stops the
   Champion stage and yields no research candidate.
7. Four product/horizon bindings exactly match `config/products.json`.
8. Adversarial tests cover duplicate keys, stage reordering, path escape, replay,
   lock conflict, same-day leakage, claim weakening, and private locator leakage.
9. Compile, complete tests, smoke, control, Secret Guard, schema validation, wheel
   build/install, installed-module exercise, and exact-head CI pass.
10. A sanitized handoff and Draft PR are published from the declared task branch.

## Safety and non-claims

- A Drive file is not admitted merely because it exists.
- Telegram and IndexSignal remain routing/sentiment; Investing requires an
  authorized user export or valid account path and no access-control bypass.
- Do not buy, change, or extend a subscription.
- Do not create entry/exit prices from delayed public pages.
- No model training, real backtest, forecast, probability, accuracy, buy/sell
  recommendation, automatic promotion, or `LIVE_OPERATIONAL` claim is allowed.
- Do not enable the scheduled workflow or merge this task.

Do not merge. Record any later authority in `docs/codex/USER_DECISIONS.md` and
write the result using `docs/codex/HANDOFF_TEMPLATE.md`.
