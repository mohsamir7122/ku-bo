# KU-BO-009 — Staged tri-security data qualification preparation

```text
FINAL_STATUS: COMPLETED
REPOSITORY: https://github.com/mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: be5fe3883016dedf07fa680905f7199f3906b4d8
TASK_BRANCH: build/tri-security-pilot-v0.3
FINAL_SHA: 0c4d5a6b71137ec5719195ea749ed9bedf863a72
DRAFT_PR: https://github.com/mohsamir7122/ku-bo/pull/10
PR_BASE: main
CI_RUN: https://github.com/mohsamir7122/ku-bo/actions/runs/31571590903
STARTED_AT: 2026-08-12 (Asia/Kuwait)
COMPLETED_AT: 2026-08-12T09:55:04+03:00
```

`FINAL_SHA` is the published implementation/test commit. Its tree SHA is
`8fd1235c83db3fde22f1064a69d97fe7a9ea71c5`, exactly matching the locally
validated implementation tree. The following publication-only commit records
this handoff and does not change runtime, schema, configuration, or test bytes.

## User goal

Audit the live KU-BO and related Kuwait-market repositories, preserve useful
history without destructive cleanup, and begin a safe three-security testing
path with KFH, SHIP, and AZNOULA without inventing evidence or issuing an
investment claim.

## Verified starting state

- `main` was `be5fe3883016dedf07fa680905f7199f3906b4d8`; PRs #4 through #9 were
  merged and GitHub Actions run `31402435102` passed.
- The starting local suite ran 513 tests successfully.
- Old Draft PRs #2 and #3 were based on pre-stack history and were not used.
- `Research@ec570513...` contained no committed Boursa evidence or valid Factor9
  result pipeline. Its PR #4 used look-ahead ranking, zero-filled confidence,
  and fabricated fundamental fields; none of those outputs was copied.
- The archived repositories contained useful negative controls and governance
  ideas, but no artifact qualified as current KU-BO market evidence.
- `kubo-data-foundation import-status-history` had a pre-existing CLI dispatch
  defect: it passed an undefined and unsupported `imported_at` argument.

## Changes made

### Repository audit and preservation map

- Added `docs/RELATED_REPOSITORY_AUDIT_2026_08_12_AR.md` with explicit
  KEEP/ARCHIVE/NO-SALVAGE decisions for KU-BO, Research, AI-Mincy, KW, KW2,
  Factor9-saudiai, and adjacent repositories.
- Preserved the need to snapshot `KW2/mohx-fresh-rebuild` and the large archived
  Factor9 ZIPs before any future deletion. No repository, branch, PR, file, or
  conversation was deleted or closed.
- Recorded the archived Factor9 AUC results only as a negative control; they are
  not imported as training evidence or a performance claim.

### Tri-security registry and scoped configuration

- Added a strict deterministic registry with three securities per batch and
  globally unique Security Code, Ticker, and checksum-valid ISIN candidates.
- Fixed batch one at KFH/SHIP/AZNOULA while leaving every identity
  `UNVERIFIED_SEED`.
- Added separately governed candidate vendor mappings. The observed SHIP route
  legitimately contains three consecutive hyphens; runtime and JSON Schema
  accept that safe path form without weakening slash/query/fragment checks.
- Added a scoped six-file Pilot configuration and exact manifest. Every CLI use
  of `--pilot-config-dir` requires an externally supplied expected manifest SHA
  and rehashes the exact file set before downstream preparation.

### Fail-closed workspace and progression

- Added a non-overwriting, symlink-safe workspace generator with a bounded
  single-year qualification window, hash-bound batch plan, one evidence
  directory per security, Arabic checklist, and explicit pending gate report.
- Reused the final twelve Data Foundation gates in exact order. Preparation
  leaves all of them `PENDING_EXTERNAL_EVIDENCE`.
- Hard-rejected batch two and batch three before output creation until an
  independently verifiable predecessor qualification receipt exists.
- Added strict Draft 2020-12 schemas that reject gate substitution, predecessor
  forgery, later-batch reports, and scoped-manifest drift.

### CLI and packaging correction

- Added installed commands to validate the tri registry and prepare the first
  workspace, and integrated scoped configuration with the existing Pilot CLI.
- Removed the invalid `args.imported_at` dispatch from `import-status-history`.
- Added direct dispatch regression coverage and a real successful invocation
  from the force-installed wheel.
- Corrected the installed-wheel checker so a virtual-environment interpreter
  symlink does not resolve away from its sibling entry-point scripts.

## Validation performed

```text
COMMAND_OR_JOB: python -m unittest discover -s tests -q
RESULT: PASS
DETAIL: 528 tests completed successfully on the final implementation tree.
```

```text
COMMAND_OR_JOB: python -m compileall -q src tests scripts
RESULT: PASS
DETAIL: Runtime, tests, and repository scripts compiled successfully.
```

```text
COMMAND_OR_JOB: codex_control_check.py; smoke_check.py; secret_guard.py
RESULT: PASS
DETAIL: Control metadata, synthetic non-claiming smoke, and secret-pattern scan passed.
```

```text
COMMAND_OR_JOB: isolated wheel build/install plus installed_data_foundation_check.py
RESULT: PASS
DETAIL: kubo resolved from isolated site-packages and 12 installed handlers ran, including scoped three-symbol price preparation and import-status-history.
```

```text
COMMAND_OR_JOB: independent final tri-pilot review
RESULT: PASS
DETAIL: 34 focused tests, diff check, compile, smoke, manifest anchoring, batch lock, window, gate order, scoped denominator, and SHIP route checks passed with no blocking finding.
```

```text
COMMAND_OR_JOB: GitHub Actions run 31571590903 at 0c4d5a6b71137ec5719195ea749ed9bedf863a72
RESULT: PASS
DETAIL: All contracts-and-tests jobs passed on Python 3.11, 3.12, 3.13, and 3.14, including the installed-wheel exercise.
```

## Evidence and data status

- Registry, schemas, CLI, and workspaces: `PARTIAL`; they prove configuration
  behavior, not market truth.
- KFH/SHIP/AZNOULA identity rows: `BLOCKED` as official evidence and explicitly
  `UNVERIFIED_SEED`.
- Vendor routes: `LIVE_DEPENDENT` candidate mappings; URL observation is not an
  authorized capture receipt or official identity.
- Test artifacts: `RECORDED_AUTHORIZED_FIXTURE` or `SYNTHETIC_ONLY`; they cannot
  promote a real gate.
- Real price, status, action, Benchmark, and EOD packets: `BLOCKED`; none was
  collected or committed.
- Archived Factor9 data/results: `PARTIAL` historical negative control only,
  with incomplete receipts, rights, PIT lineage, and reproducibility.

## Claims allowed

- The branch deterministically prepares an empty, hash-bound workspace for
  exactly KFH, SHIP, and AZNOULA.
- Scoped Pilot preparation retains the exact three-security denominator and
  detects file or manifest tampering when anchored to the workspace receipt SHA.
- Later batches fail closed, and all twelve final gates remain visibly pending.
- The installed CLI regression is fixed and tested from the built wheel.
- The related-repository audit identifies what to keep or archive before any
  future destructive decision.

## Claims still forbidden

- Real backtest readiness: forbidden.
- Forecast accuracy or prospective performance: forbidden.
- Probability or calibrated confidence: forbidden.
- Buy/sell, entry/exit, position, or execution recommendation: forbidden.
- Full-market coverage: forbidden; one three-security batch is not a market
  universe and the other batches are locked.
- `LIVE_OPERATIONAL` source status: forbidden; no real capture was accepted.

## Privacy and repository safety

```text
credentials or sessions: NO
private Drive IDs: NO
raw conversations: NO
real runtime market data: NO
licensed data: NO
destructive cleanup: NO
force push: NO
merge or auto-merge: NO
```

The result is an open Draft PR. `main`, old PRs, archived repositories, and
unmerged legacy branches remain untouched.

## User decisions required

- `KU-BO-008-D01` remains OPEN. It must be resolved by an explicit
  product-specific maximum extension and terminal treatment before a real
  outcome-session/backtest claim can pass.
- No new deletion, merge, licensing, credential, or data-source decision was
  inferred or executed by KU-BO-009.

## Items classified for retention

```text
KEEP: KU-BO tri registry, scoped manifest verifier, schemas, adversarial tests, and Arabic operating guide
KEEP: Research/legacy audit and the explicit no-salvage findings
REFACTOR: selected provider, provenance, and negative-test patterns only after rewriting against KU-BO contracts
ARCHIVE: KW history; KW2 unmerged branch; Research PR heads; complete Factor9-saudiai ZIP history
PRIVATE_ONLY: any future authenticated, licensed, or real runtime evidence packet
DELETE_CANDIDATE: None
```

## Known limitations and risks

- The scoped manifest binds configuration membership, but the batch plan SHA,
  exact window, and cohort are not yet carried through every identity, status,
  price, EOD, and final reconciliation output. End-to-end qualification can
  drift unless the next receipt layer is implemented.
- Batch two and batch three are intentionally unusable until an independent
  predecessor receipt contract exists.
- Current official-source coverage does not yet prove AZNOULA code 826 through
  all existing official-foundation routes; fail-closed identity import is the
  expected result until broader official bytes are supplied.
- Candidate Investing routes do not prove availability, licensing, complete
  pagination, or semantic parser success.
- `main` is not protected at the repository setting level; continued merge
  discipline depends on repository policy and explicit user approval.
- Open PRs #2 and #3 remain stale and must not be used as current bases.

## Smallest logical next task

```text
TASK_ID: KU-BO-010
PROPOSED_BRANCH: build/tri-security-run-receipt-v0.1
DEPENDENCY: Draft PR #10 reviewed as the accepted base; no merge is performed by this handoff
GOAL: Bind the exact batch-plan SHA, scoped-manifest SHA, cohort, and qualification window through every downstream component and final report.
ENTRY_GATE: A versioned external receipt authority and exact expected-plan argument are specified without self-authored promotion.
EXIT_GATE: Cohort/window/plan tampering fails closed in identity, status, price, EOD, and reconciliation paths; installed-wheel and adversarial tests pass; later batches remain locked.
```

This next task still would not authorize real market capture, a real backtest,
model training, forecast, probability, recommendation, or merge.
