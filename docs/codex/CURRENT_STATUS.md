# KU-BO Current Codex Status

Status date: 2026-08-10

Repository:

```text
mohsamir7122/ku-bo
```

## Verified development chain when this file was created

```text
PR #4
build/data-foundation-v0.2
Research Price History

PR #5
build/official-identity-calendar-v0.2
Current Official Identity + 2026 Trading Calendar

PR #6
build/security-status-corporate-actions-v0.2
Current Security Status + Corporate Action Schedule

PR #7
build/ca-enrichment-status-history-v0.2
Corporate Action Disclosure Enrichment + Historical Status Intervals
```

PR #7 metadata at control-layer creation:

```text
state: OPEN
mode: DRAFT
mergeable: true
merged: false
head SHA: 570cfda44eedfea91220a500c494f493eed49763
CI run: 31356885100
Python 3.11–3.14: PASS
full unit/adversarial tests inspected: 376 PASS
```

This status is a handoff snapshot, not a substitute for live verification.

## Proven in code and CI

- strict source/evidence and claim-boundary framework;
- research price-history import contracts for the five-security pilot;
- separation of vendor mapping from official identity;
- current official identity and 2026 calendar framework;
- current security-status and delisting/corporate-action schedule framework;
- disclosure-backed corporate-action enrichment framework;
- separation of reference-price, continuity, quantity, and return treatments;
- historical status-notice and interval reconstruction framework;
- secret guard, wheel build, installed CLI checks, and broad adversarial testing.

## Not proven by real market evidence

- complete real price files for the full requested period;
- complete historical point-in-time universe;
- complete official daily EOD for every eligible security-session;
- complete benchmark history;
- complete corporate-action factors and return policies for every real event;
- complete historical suspension/resumption evidence for every pilot security;
- final data-foundation reconciliation on real evidence;
- real backtest performance;
- forecasting skill or prospective validation;
- any trading recommendation.

## Active control branch

```text
ops/codex-control-center-v0.1
```

The control branch is stacked on PR #7 and adds only operating instructions, handoff policy, and the active Codex task. It does not itself complete a market-data stage.

## KU-BO-008 task-branch result

The task branch is:

```text
build/benchmark-official-eod-v0.2
```

It starts at the verified control head `cba8fc1c57365343f497e1859733e0ae03087bfe` and adds strict Benchmark History, Official Complete Daily EOD, and final twelve-gate reconciliation contracts. Recorded fixtures exercise code paths only; no real Benchmark or EOD export is committed.

Real baseline-backtest readiness remains unavailable because:

- the configured Benchmark codes are internal unverified requirements and full history needs authorized official or licensed exports;
- legacy upstream manifests do not contain hash-bound evidence classification and rights metadata, so the reconciler refuses to infer real evidence;
- caller-authored `PROVEN_REAL_EVIDENCE` labels are not authority roots: the external runtime registry proves source/entitlement authority only, not capture bytes; Benchmark and EOD remain `LIVE_DEPENDENT` or `LICENSED_FEED_DEPENDENT` until an independently authenticated receipt binds the exact artifact SHA-256, capture event, window/query counts, source, and rights;
- `KU-BO-008-D01` is open and `outcome_session_policy` remains `UNFROZEN`;
- schema v1 rejects every FROZEN value; committing global Option 1 cannot approve
  D01, whose future implementation requires a product-specific extension/terminal
  contract and an approved decision receipt;
- session-horizon forecasts therefore fail closed at ledger append/verify and at
  evaluation; civil-day due dates, legacy stop gates, and caller hash sets cannot
  produce a real evaluation or metrics without approved product-specific policy, official
  calendar/status resolution, artifact-bound capture authority, and an independent
  final data-foundation receipt;
- no rights-compatible real pilot Benchmark/EOD packet was supplied to this repository task.

These are evidence and user-policy blockers, not code-test substitutions. Exact branch tests, CI, Draft PR, and publication metadata belong in `docs/codex/handoffs/KU-BO-008-result.md`.

## Next engineering stage

The active task is defined only in:

```text
docs/codex/CURRENT_TASK.md
```

Do not infer a new task from this status file or from old chat summaries.
