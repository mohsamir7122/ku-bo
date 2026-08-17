# CURRENT TASK — KU-BO-014

```text
TASK_ID: KU-BO-014
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: 59833bf73510b3aa3901f628cbf2c13c0d01cf79
EXPECTED_NEW_BRANCH: agent/humansoft-event-factor-panel-v1
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
BLOCKED_ON: COMPLETE_OFFICIAL_DISCLOSURE_ARCHIVE; COMPLETE_CORPORATE_ACTION_LEDGER; AUTHORITATIVE_HISTORICAL_TOTAL_RETURN_SERIES; POINT_IN_TIME_MARKET_AND_SECTOR_BENCHMARKS; SOURCE_BACKED_PUBLIC_OPINION_ARCHIVE
```

## Mission

Separate the HUMANSOFT disclosure-reaction product into independent data domains:

1. append-only historical official disclosure records, including corrections and supplements as separately linked records;
2. frozen historical event market windows used only for the relevant disclosure;
3. a rolling recent daily market series used only for current context;
4. a replaceable latest financial snapshot used only for current financial context;
5. a frozen, source-backed public-opinion archive linked to the disclosure cluster.

The user-facing result answers only whether a rise began before the official disclosure, immediately after it, later after it, continued across it, faded, or did not appear clearly, plus the documented public-opinion direction. It exposes no market numbers.

## Acceptance gates

1. Historical disclosure artifacts reject price, daily-market, and financial-snapshot fields.
2. Historical market-window artifacts reject disclosure text, current financial metrics, and public-opinion material.
3. Recent daily market data cannot reference a disclosure or recompute a frozen historical result.
4. Latest financial snapshots cannot contain daily price fields or enter historical disclosure reaction analysis.
5. Corrections, supplements, and withdrawals are append-only records with explicit lineage; they never overwrite the original archived disclosure.
6. Reaction requests accept only historical disclosure, frozen historical market window, and frozen public-opinion archive domains.
7. Output is qualitative only, contains no price/return values, and makes no causality or leakage claim.
8. Missing official evidence, Corporate Actions, market/sector benchmarks, or complete windows produces STOP rather than inference.
9. Targeted tests, complete repository suite, compile, control, smoke, schema, Secret Guard, wheel, and exact-head CI must pass.
10. PR #18 remains Draft. Do not merge.

Record scope decisions in `docs/codex/USER_DECISIONS.md`. Write the final handoff using `docs/codex/HANDOFF_TEMPLATE.md`.

## Safety and non-claims

- No live collector is started by this task.
- No private, licensed, or raw row-level market data are committed.
- No model is trained and no forecast, probability, accuracy, rank, recommendation, or execution instruction is emitted.
- A pre-disclosure discussion does not prove leakage.
- A post-disclosure rise does not prove that the disclosure was the sole cause.
