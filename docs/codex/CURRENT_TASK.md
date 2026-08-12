# CURRENT TASK — KU-BO-009

```text
TASK_ID: KU-BO-009
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
EXPECTED_NEW_BRANCH: build/tri-security-pilot-v0.3
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
RESULT_PR: PENDING
RESULT_HANDOFF: docs/codex/handoffs/KU-BO-009-result.md
BLOCKED_ON: REAL_MARKET_EVIDENCE; AUTHENTICATED_CAPTURE_RECEIPTS; KU-BO-008-D01
```

## Mission

Audit the live `ku-bo` state and the related Research/legacy repositories, then
implement a fail-closed staged pilot that prepares data qualification three
securities at a time. The first batch is:

```text
KFH / SHIP / AZNOULA
```

The implementation may validate configuration and prepare an empty evidence
workspace. It must not collect or commit real market data, run a real backtest,
train a model, issue a probability, or produce a trading recommendation.

## Verified base

```text
main@be5fe3883016dedf07fa680905f7199f3906b4d8
```

The starting full local suite passed `513` tests after installing the declared
test dependency. GitHub Actions run `31402435102` passed on the same main head.
Open Draft PRs #2 and #3 predate the merged implementation chain and are not a
safe base for this task.

## Required deliverables

1. Record an evidence-backed audit of `ku-bo`, `Research`, and relevant legacy
   Kuwait repositories, including KEEP/REFACTOR/ARCHIVE/NO-SALVAGE decisions.
2. Add a strict machine-readable registry whose batches contain exactly three
   unique identities and whose execution order is deterministic.
3. Begin with KFH, SHIP, and AZNOULA, while keeping every configured identity
   `UNVERIFIED_SEED` until raw official evidence is imported.
4. Add a safe non-overwriting workspace generator with one evidence directory
   per security, a hash-bound batch plan, and explicit pending gates.
5. Reuse the final twelve Data Foundation gates; do not create a weaker parallel
   readiness definition.
6. Make later batches declare their predecessor requirement and keep
   `next_batch_authorized=false` during workspace preparation.
7. Add strict JSON Schemas, adversarial tests, CLI commands, and Arabic operating
   documentation.
8. Fix only material defects discovered during the audit when the correction is
   bounded, regression-tested, and does not expand external authority.
9. Publish the result as a Draft PR against `main`; do not merge it.

## Required safety boundaries

- A valid registry is not official identity evidence.
- A prepared workspace contains no market evidence.
- Three qualified securities do not prove full-market coverage.
- Synthetic or recorded fixtures do not prove real-data readiness.
- Scores are not probabilities.
- No Forecast, Accuracy, Buy/Sell, Entry/Exit, or Backtest claim is allowed.
- `KU-BO-008-D01` remains open and must not be silently resolved.
- Do not copy scores, backtests, fabricated fundamentals, or recommendations
  from `mohsamir7122/Research` or archived projects.
- Do not merge, force-push, permanently delete, or rewrite repository history.

## Validation loop

Before handoff, run:

```text
compileall
targeted tri-security and schema tests
complete unit and adversarial suite
synthetic smoke check
secret_guard
wheel build
wheel reinstall in an isolated environment
installed kubo commands
installed kubo-data-foundation commands
git diff inspection
```

Use `docs/codex/HANDOFF_TEMPLATE.md` for the final handoff. Record any future
destructive or policy choice in `docs/codex/USER_DECISIONS.md`; this task grants
none.
