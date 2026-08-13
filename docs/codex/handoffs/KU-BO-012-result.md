# KU-BO-012 — Kuwait 120-day context and next-session replay

```text
FINAL_STATUS: PARTIAL
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: 92b2bdd2460a7508922297a12d85f13264d43acb
TASK_BRANCH: agent/kuwait-120d-next-session
FINAL_SHA: 58a78042d5d509e599d2e273d793856b1dee14dd (published implementation evidence; later control-record head pending)
DRAFT_PR: #14 / https://github.com/mohsamir7122/ku-bo/pull/14
PR_BASE: main
CI_RUN: 31733924569 / PASS / implementation SHA / Python 3.11-3.14
STARTED_AT: 2026-08-13
COMPLETED_AT: IN_PROGRESS
```

## User goal

Implement a bounded, multi-source Kuwait research workflow that builds a rolling four-month context, continues through individual source failures, maps events and factors across the eligible market, verifies branch integration, and evaluates the latest forty next-session decisions without inventing an agreement percentage when real point-in-time evidence is missing.

## Verified starting state

- `main` was verified at `92b2bdd2460a7508922297a12d85f13264d43acb`.
- PR #1 and PRs #4 through #13 are already ancestors of `main` and require no further merge.
- PR #2 and PR #3 are 127 commits behind, non-mergeable, and superseded; whole merge or wholesale cherry-pick is forbidden.
- The clean baseline local suite passed 1,916 tests before KU-BO-012 edits.
- The task branch began with no real full-market point-in-time packet, no 40-decision forecast ledger, and no admissible outcome denominator.
- `KU-BO-008-D01` was and remains `OPEN`.

## Changes made

### Product and source-search contract

- Added `KUWAIT_120D_NEXT_SESSION_RESEARCH` with separate 120-day, 30-day, 7-day, and 72-hour windows.
- Expanded the catalog to 68 source definitions and 62 independence groups, with 59 non-search/non-storage candidate domains, 53 declared enabled-public catalog domains, and 52 distinct executable start-URL domains.
- Kept capabilities explicit: 66 `DEFINED_ONLY`, 2 `END_TO_END_TESTED` on generated fixtures, and 0 `LIVE_OPERATIONAL`.
- Added a fair 50-domain default plan with incremental wave contributions `17/0/29/4`, reserving Archive/Community domains so Telegram (`t.me`) and IndexSignal are reached. The Search Router remains catalog-only and is not executed.
- Added fail-stop retry handling: hard blocks never retry; 429 remains on the same strategy and stops after three attempts; `Retry-After` is honored within the wall budget; an excessive delay or sleeper failure stops the route.
- Added bounded empty-query and access-denial handling plus an append-only attempt ledger that records Retry-After, material-route proof, disposition, and limitations. Its declared limitations prohibit treating the hash chain as an external seal, capture time as publication time, or low-level HTTP as fully metered.
- Added persisted Source Search validation that reopens and rehashes the report,
  append-only ledger, and referenced raw artifacts before integration.
- Added `parsed-research-inputs.schema.json`,
  `src/kubo/kuwait_research_pipeline.py`, and the
  `build-kuwait-research-bundle` CLI. The bridge binds caller-supplied parsed
  events, exposures, factors, dispositions, and scores to verified source bytes
  and writes the integrated artifacts atomically; it does not pretend to be a
  general parser or derive missing semantics.

### Context, exposure, factors, and denominator

- Added schemas and code contracts for normalized context events, evidence-bound security exposure, versioned factor snapshots, and explicit full-denominator dispositions.
- Preserved `MISSING`, `NOT_APPLICABLE`, and `REJECTED` rather than manufacturing neutral zeroes.
- Bound complete canonical snapshot rows, factors, evidence, dispositions, and
  scores to `factor_snapshot_sha256`, with `snapshot_id` derived from that
  digest. Enforced registry freshness windows, including 24 hours for current
  trading status, and rejected `SUPERSEDED` events from factor-eligible
  exposure while retaining current corrective events.
- Restricted Telegram and IndexSignal to community sentiment or routing.

### Forty-session replay

- Added a strict replay contract for 40 decision sessions and 41 consecutive official sessions.
- Made every structural, evidence, denominator, or authority gap return `STOP_BACKTEST` with `metrics=null`; removed the unreachable `STOP_INFERENCE` status from this replay contract.
- Made the product execution-grade: ranks must derive from score descending
  with Security Code as the deterministic tie-break, selected rows must equal
  Top-K, and every selected row requires a verified `FILLED` execution.
- Kept non-trading securities in the denominator, but made them stop the replay
  while `KU-BO-008-D01` remains open; no row is dropped and no close is
  synthesized.
- Kept `GROSS_ADJUSTED_RETURN_GT_0` primary **before** execution costs. Fees,
  spread, and slippage affect actionable-net and market/sector net-excess
  secondary metrics.
- Added a strict replay-result Schema. A stopped result requires `agreement_rate=null`, `agreement_rate_status=NOT_APPLICABLE`, `authority_receipt_sha256=null`, `authority_verified=false`, and `accuracy_claim_allowed=false`.

### Documentation and control status

- Updated `README.md`, `AGENTS.md`, architecture, build status, source policy, Data Foundation status, and the Codex current-status record.
- Added `docs/KUWAIT_120D_NEXT_SESSION_AR.md` with the operational and claim-boundary contract.
- Added focused KU-BO-012 CI tests and installed-wheel checks for workflow
  validation and the Source Search/Integration/Replay command surfaces.
- Draft PR #14 and its successful implementation-head CI are recorded. No
  merge, live capability, or real backtest completion is claimed.

## Validation performed

```text
COMMAND_OR_JOB: clean baseline python -m unittest discover
RESULT: PASS
DETAIL: 1,916 tests passed before KU-BO-012 edits.
```

```text
COMMAND_OR_JOB: python scripts/codex_control_check.py --root .
RESULT: PASS
DETAIL: 15 control text files and 10 required files checked; zero errors and zero warnings. Claim boundaries remained false for deletion, merge, market data, and backtest readiness.
```

```text
COMMAND_OR_JOB: git diff --check
RESULT: PASS
DETAIL: No whitespace error was reported on the shared task-branch diff at the documentation checkpoint.
```

```text
COMMAND_OR_JOB: workflow/source-orchestrator/context/integration/replay/CLI targeted tests
RESULT: PASS
DETAIL: 183/183 tests passed on the final focused integration checkpoint.
```

```text
COMMAND_OR_JOB: final current-tree full unit/adversarial suite
RESULT: PASS
DETAIL: 2,067/2,067 tests passed in 164.347s.
```

```text
COMMAND_OR_JOB: compileall / JSON checks / git diff --check / smoke / secret guard
RESULT: PASS
DETAIL: Every listed local gate passed. Corpus generation and audit also passed for all 1,280 cases.
```

```text
COMMAND_OR_JOB: final wheel build
RESULT: PASS
DETAIL: 444351 bytes; SHA-256 ee089ec3a7e100e81e1ef4a0378824c2b3e817db7d4c23d2d197b728b400c3a3. This is a local artifact, not a GitHub Actions result.
```

```text
COMMAND_OR_JOB: isolated install / imports / CLI help / validate-research-workflow
RESULT: PASS
DETAIL: The final wheel installed and the listed installed-package exercises passed.
```

```text
COMMAND_OR_JOB: installed_data_foundation_check
RESULT: PASS
DETAIL: 8 semantic admissions and 8 lineages were verified through the installed package.
```

```text
COMMAND_OR_JOB: latest-40 real point-in-time input-readiness audit
RESULT: FAIL
DETAIL: STOP_BACKTEST; 0 process-valid scoreable sessions out of 40 expected; metrics=null; agreement_rate=null; agreement_rate_status=NOT_APPLICABLE; authority_verified=false; accuracy_claim_allowed=false. Human presentation is N/A. No admissible real full-market packet exists in the repository.
```

## Evidence and data status

```text
SOURCE CATALOG AND WORKFLOW CONTRACTS: PARTIAL / SYNTHETIC_ONLY
TWO PARSER PATHS: SYNTHETIC_ONLY (GENERATED FIXTURES ONLY)
LIVE SOURCE OPERATION: LIVE_DEPENDENT / BLOCKED
PERSISTED SEARCH/PARSED INPUT/CONTEXT/EXPOSURE/FACTOR/REPLAY CONTRACTS: SYNTHETIC_ONLY; LOCAL ACCEPTANCE GATES PASS
LATEST-40 REAL REPLAY: BLOCKED / LIVE_DEPENDENT
REAL MARKET EVIDENCE: NOT PRESENT
```

The replay result is `STOP_BACKTEST`, not a measured failure rate. The result Schema encodes `agreement_rate=null/NOT_APPLICABLE`, `authority_verified=false`, and `accuracy_claim_allowed=false`; human presentation is `N/A`. Reporting `0%` would falsely reinterpret absent evidence as forty incorrect forecasts.

## Claims allowed

- The branch defines a bounded 120-day Kuwait context and next-session research contract.
- The catalog has 68 definitions, 62 independence groups, 59 non-search/non-storage candidate domains, 53 declared enabled-public catalog domains, and 52 distinct executable start-URL domains.
- The default fair plan covers exactly 50 domains with incremental contributions `17/0/29/4`, including reserved `t.me` and `indexsignal.com` community domains.
- Capability status is 66 `DEFINED_ONLY`, 2 generated-fixture `END_TO_END_TESTED`, and 0 `LIVE_OPERATIONAL`.
- The replay fails closed when point-in-time inputs or the full denominator are absent.
- The parsed-input bridge verifies integration lineage but does not prove live
  parsing, coverage, factor correctness, or predictive skill.
- Factor Snapshot identity binds its complete canonical content and rejects
  stale observations according to the registry.
- The replay derives rank and selection from score and enforces execution and
  non-trading stop policy without changing the primary gross-before-cost label.
- Existing relevant merged work is already in `main`; stale PR #2 and PR #3 are intentionally excluded.

## Claims still forbidden

```text
real backtest readiness: FORBIDDEN
forecast accuracy: FORBIDDEN; agreement_rate is null/NOT_APPLICABLE (N/A)
probability: FORBIDDEN
recommendation: FORBIDDEN
full-market coverage: FORBIDDEN
LIVE_OPERATIONAL source status: FORBIDDEN; count is 0
Draft PR and implementation-head CI: PROVEN; PR #14 / Run 31733924569
merge completion: FORBIDDEN; no merge occurred
```

## Privacy and repository safety

The branch contains no credentials or sessions, private Drive IDs, raw conversations, real runtime market data, licensed data, or destructive cleanup. All such categories are `NO`.

## User decisions required

- `KU-BO-008-D01`: `OPEN`; a product-specific outcome-session policy for suspended or halted securities is still required.
- `KU-BO-MERGE-004`: approved conditionally, but it does not change `MERGE_ALLOWED: NO` before the exact-head gates and merge-boundary review.

## Items classified for retention

```text
KEEP: KU-BO-012 product/workflow, source catalog expansion, schemas, implementation, tests, and current documentation
KEEP: historical KU-BO-011 evidence and non-claims
SUPERSEDE: PR #2 and PR #3 implementation approach; retain branches as history
PRIVATE_ONLY: real runtime market packets, credentials, sessions, and private Telegram material
DELETE_CANDIDATE: none
```

## Known limitations and risks

- Catalog breadth does not create live connectors or parser support.
- Access-controlled and dynamic sources require lawful independent authority and may remain unavailable.
- Missing official point-in-time universe, EOD, benchmark, status, Corporate Actions, and sealed decisions prevents any latest-40 percentage.
- A 40-session replay, if later admissible, remains a descriptive pilot rather than prospective validation.
- The full local suite, local acceptance gates, final wheel, and installed-wheel
  exercises pass. Draft PR #14 implementation-head CI passed, but this later
  control-record head still needs exact-head CI and no merge-boundary review has
  occurred.

## Smallest logical next task

```text
TASK_ID: KU-BO-012-CONTINUE
PROPOSED_BRANCH: agent/kuwait-120d-next-session
DEPENDENCY: preserve KU-BO-008-D01 as OPEN and do not alter the locally accepted integration contracts
GOAL: retain the sanitized STOP_BACKTEST artifact, validate the later control-record head, and perform a fresh merge-boundary review without bypassing MERGE_ALLOWED
ENTRY_GATE: all current-tree local acceptance gates and installed-wheel exercises pass
EXIT_GATE: exact-head CI for the control-record head passes and a fresh merge-boundary review is recorded; merge remains separately gated
```
