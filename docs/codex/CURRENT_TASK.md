# CURRENT TASK — KU-BO-010

```text
TASK_ID: KU-BO-010
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: build/tri-security-pilot-v0.3
EXPECTED_NEW_BRANCH: build/tri-security-run-receipt-v0.1
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
RESULT_HANDOFF: docs/codex/handoffs/KU-BO-010-result.md
BLOCKED_ON: DOWNSTREAM_RECEIPT_ENFORCEMENT; REAL_MARKET_EVIDENCE; AUTHENTICATED_CAPTURE_AUTHORITY; KU-BO-008-D01
```

## Mission

Implement and publish a standalone, fail-closed authenticated contract that
binds the exact first tri-security batch plan, scoped configuration, cohort,
qualification window, and complete stage artifact tree. Use independently
keyed runtime-only Run Receipt and Stage Binding HMAC authorities. Preserve the
known Benchmark scope incompatibility and every non-claim boundary.

This task defines issuance and verification primitives only. Mandatory checks
inside all downstream importers and final reconciliation belong to KU-BO-011.

## Verified dependency base

```text
build/tri-security-pilot-v0.3@7d032c98b0ef9f27e913199487ad4577119c2631
Draft PR #10
GitHub Actions run 31571987659 / PASS
```

The branch is based on the exact head of the open KU-BO-009 Draft PR, not on
stale PR #2 or #3 and not on a reconstructed legacy workspace. KU-BO-009 keeps
KFH/SHIP/AZNOULA as `UNVERIFIED_SEED`, all twelve gates pending, and later
batches locked.

## Completed deliverables

1. Add strict Canonical JSON contracts and Draft 2020-12 schemas for a Run
   Receipt and Stage Binding with no unknown fields.
2. Require externally supplied expected batch-plan and scoped-manifest hashes;
   rehash the plan, manifest, scoped files, workspace report, registry, cohort,
   window, and pending gate state before signing or accepting a receipt.
3. Lock the receipt to batch one and exactly three unique Security Code/Ticker/
   ISIN rows without promoting `UNVERIFIED_SEED` identity.
4. Derive `run_date` from the aware issue instant in `Asia/Kuwait`, cap validity
   at seven days, and reject stale, future, forged, wrong-audience, wrong-key,
   wrong-key-id, or cross-run receipts.
5. Require independent runtime-only HMAC keys and key IDs for run and stage
   authentication; never persist or print the key or authentication tag.
6. Bind the stage Manifest, declared artifacts, and complete file-tree
   inventory so additions, deletions, byte changes, symlinks, special files,
   traversal, or time-of-check/time-of-use drift fail closed.
7. Keep receipt and binding roots disjoint from the prepared workspace and
   stage output, with safe non-overwriting creation.
8. Preserve the explicit
   `CONFIGURED_SERIES_INCOMPATIBLE_WITH_TRI_COHORT` Benchmark state. Missing
   Industrials and Utilities sector series block Benchmark qualification and
   prohibit reuse of the five-security or full-market denominator.
9. Add four installed CLI commands, adversarial tests, wheel coverage, and an
   Arabic operating contract.
10. Publish only as a Draft PR against the exact dependency branch. Do not
    merge, auto-merge, force-push, or rewrite history.

## Required safety boundaries

- `AUTHENTICATED_BINDING_NOT_MARKET_EVIDENCE` is the only receipt claim.
- A valid Run Receipt does not prove official identity or data qualification.
- A valid Stage Binding does not prove that its bytes are official, licensed,
  complete, or suitable for a real backtest.
- Three bound securities do not prove the five-security Pilot or full market.
- Benchmark registry incompatibility must remain visible and fail closed.
- No later batch is authorized.
- No real market bytes, licensed artifacts, credentials, HMAC keys, Drive IDs,
  browser sessions, or raw conversations may enter Git.
- July legacy prediction/results claims remain quarantined and cannot support
  truth, training, backtest, accuracy, or recommendation claims.
- No Forecast, Accuracy, Probability, Buy/Sell, Entry/Exit, Backtest, or
  production-execution claim is allowed.
- `KU-BO-008-D01` remains OPEN and must not be silently selected or frozen.
- Do not merge this Draft PR without a new explicit user decision.

## Validation and publication loop

Before final handoff, run and record:

```text
compileall
targeted receipt, stage-binding, CLI, and schema tests
complete unit and adversarial suite
Codex control check
synthetic smoke check
secret_guard
wheel build
wheel reinstall in an isolated environment
installed kubo commands
installed kubo-data-foundation receipt commands
git diff and committed-tree inspection
exact-head GitHub Actions on Python 3.11 through 3.14
```

Use `docs/codex/HANDOFF_TEMPLATE.md` for the result and preserve all policy
choices in `docs/codex/USER_DECISIONS.md`. This task grants no deletion,
licensing, credential, data-source, merge, policy, or financial decision.

## Publication gate

The standalone Run Receipt and Stage Binding contract is implemented in the
task branch. The task remains `IN_PROGRESS` until its implementation commit is
published to a Draft PR against the exact dependency branch and passes the
exact-head CI matrix. Only then may the sanitized result handoff mark the task
complete.

KU-BO-011 is not included in this completion. It must make these authenticated
bindings mandatory at the pre-write boundary of every relevant importer and
carry the same run/stage chain into final Data Foundation reconciliation.
