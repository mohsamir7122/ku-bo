# KU-BO-011 — Eight-boundary semantic admission enforcement

```text
FINAL_STATUS: COMPLETED
REPOSITORY: https://github.com/mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: c621fcf88034c4571aa08aee2e54e2e026a4f651
TASK_BRANCH: build/tri-security-receipt-enforcement-v0.2
FINAL_SHA: 6dc821f8342bf2041ac3bed983c6805ff0a2c3fc (published implementation head; this control-record update creates a later head)
DRAFT_PR: https://github.com/mohsamir7122/ku-bo/pull/13
PR_BASE: main
CI_RUN: https://github.com/mohsamir7122/ku-bo/actions/runs/31695010037 — PASS
STARTED_AT: 2026-08-13 (Asia/Kuwait)
COMPLETED_AT: 2026-08-13 (Asia/Kuwait)
```

`FINAL_STATUS: COMPLETED` classifies the published implementation evidence at
`6dc821f8342bf2041ac3bed983c6805ff0a2c3fc`. It does not authorize merge. This
handoff/control update creates a later commit, which must pass exact-head CI
before the ordered `KU-BO-MERGE-003` boundary is rechecked. Accordingly,
`CURRENT_TASK` remains `IN_PROGRESS` and `MERGE_ALLOWED` remains `NO`.

## User goal

Inspect the repository, identify the unintegrated development work and its
reasons, then implement and integrate the safe KU-BO-011 changes needed to
enforce authenticated Run Receipt, stage, semantic, and predecessor admission
at all eight Data Foundation write boundaries. Preserve every market-evidence,
rights, policy, backtest, forecast, and recommendation non-claim.

## Verified starting state

- `main` was `c621fcf88034c4571aa08aee2e54e2e026a4f651` after PR #12
  merged as `TEST_SPEC_ONLY`; post-merge GitHub Actions run `31684299396`
  passed.
- PR #12 supplied 1,280 deterministic synthetic Test Specifications. It did
  not contain or prove runtime enforcement and retains
  `TEST_SPEC_ONLY_NO_KU_BO_011_RUNTIME_ENFORCEMENT_CLAIM` historically.
- The active implementation branch was
  `build/tri-security-receipt-enforcement-v0.2`. Open PRs #2 and #3 remained
  stale, conflicting, and outside this task.
- Stage Binding v1 was an authenticated byte-integrity binding whose explicit
  semantic non-claim remained
  `binding_proves_stage_matches_run_scope=false`; it had no authenticated
  predecessor graph.
- Real market evidence, provider/capture authority, rights-compatible
  Benchmark/EOD packets, and an approved outcome-session policy were absent.
  `KU-BO-008-D01` was and remains `OPEN`.

## Changes made

### Semantic admission and predecessor graph

- Added a separately versioned semantic admission authenticated by a third
  independent runtime-only HMAC authority.
- Bound exact run, batch, cohort, window, stage, boundary inputs, operation,
  safe input-tree inventory, and ordered predecessor identities.
- Implemented the exact eight-boundary predecessor DAG and persisted the fixed
  semantic-admission and lineage sidecars required by downstream stages.
- Kept Stage Binding v1 unchanged as a byte-integrity-only contract.

### Mandatory production boundaries and atomic output

- Required `BoundaryAdmissionRequest` at every public importer and final
  reconciliation boundary.
- Added CLI construction for the same admission inputs, including structured
  missing-authority rejection rather than argparse-only termination.
- Validated before protected writes, used private atomic staging, rejected
  unsafe or overlapping roots, and revalidated authenticated state and output
  identity immediately before commit.
- Preserved existing output Schemas while adding fixed authenticated sidecars.

### Production adversarial Adapter and Corpus v3

- Added a non-echoing Adapter that dispatches through the named public
  production boundary and obtains rejection codes from production behavior.
- Added an Adapter-owned materialization contract for exact artifact, field,
  action, timing, re-sign policy, and value across all 40 mutation handlers and
  four channels/variants.
- Added AST anti-oracle checks: the Adapter does not import Test-Spec mutators
  or Harness data and does not read the case `expected` result.
- Corrected the executable Corpus model to v3 and regenerated all 1,280 cases.
  Its deterministic SHA-256 is
  `e7e84f75feae5ea72a5d4f67af50da24f5d46e5a9cba49030ff8547a41b50288`.

### Installed-package proof

- Extended the isolated installed-wheel check to build the authenticated run,
  all eight semantic admissions, the complete predecessor DAG, and eight
  lineage artifacts from installed package code.
- Exercised the strict 1,280-case Adapter against both the source tree and a
  clean installed wheel.

## Validation performed

```text
COMMAND_OR_JOB: python -m compileall -q src tests scripts
RESULT: PASS
DETAIL: Source, tests, and scripts compiled successfully.
```

```text
COMMAND_OR_JOB: python scripts/generate_ku_bo_011_corpus.py --check; python scripts/audit_ku_bo_011_corpus.py --json
RESULT: PASS
DETAIL: Corpus v3 regenerated deterministically and audited at 1,280 unique cases; SHA-256 e7e84f75feae5ea72a5d4f67af50da24f5d46e5a9cba49030ff8547a41b50288.
```

```text
COMMAND_OR_JOB: python -m unittest discover -s tests -v
RESULT: PASS
DETAIL: The complete local unit and adversarial suite passed 1,916 tests.
```

```text
COMMAND_OR_JOB: source-tree tests.ku_bo_011_harness --strict-target-adapter --adapter kubo.ku_bo_011_adapter:production_adapter
RESULT: PASS
DETAIL: All 1,280/1,280 cases passed against production public-boundary dispatch with zero protected-output writes on rejection.
```

```text
COMMAND_OR_JOB: clean installed-wheel tests.ku_bo_011_harness --strict-target-adapter --adapter kubo.ku_bo_011_adapter:production_adapter
RESULT: PASS
DETAIL: All 1,280/1,280 cases passed from the clean installed wheel, independently of the source checkout import path.
```

```text
COMMAND_OR_JOB: installed_data_foundation_check.py from the isolated wheel environment
RESULT: PASS
DETAIL: The installed package built and authenticated the exact eight-boundary DAG, with eight semantic admissions and eight verified lineage artifacts.
```

```text
COMMAND_OR_JOB: codex_control_check.py; smoke_check.py; secret_guard.py; git diff --check
RESULT: PASS
DETAIL: Control metadata, synthetic smoke contracts, secret-pattern safety, and diff hygiene passed locally.
```

```text
COMMAND_OR_JOB: Draft PR #13 exact-head GitHub Actions run 31695010037
RESULT: PASS
DETAIL: Remote implementation head 6dc821f8342bf2041ac3bed983c6805ff0a2c3fc completed successfully; Python 3.11, 3.12, 3.13, and 3.14 jobs all passed.
```

## Evidence and data status

- Semantic-admission runtime, public-boundary enforcement, atomic commit,
  predecessor DAG, Adapter, Schemas, and tests:
  `CODE_AND_SYNTHETIC_ADVERSARIAL_ENFORCEMENT / SYNTHETIC_ONLY`, proven on the
  published Draft PR #13 implementation head.
- Historical merged PR #12: `SYNTHETIC_ONLY / TEST_SPEC_ONLY`; the later branch
  result does not change its historical claim.
- Draft publication and implementation exact-head CI: `PROVEN`.
- This later control-record commit and its required exact-head CI: `PARTIAL`
  until pushed and completed; it affects merge readiness, not the already
  completed implementation-evidence classification.
- Real identity, status, Corporate Action, price, Benchmark, EOD, provider
  capture, and final reconciliation evidence: `BLOCKED` or `LIVE_DEPENDENT`.
- Licensed/provider data and rights: `LICENSED_FEED_DEPENDENT`.
- Outcome-session policy: `USER_DECISION_REQUIRED` under `KU-BO-008-D01`.
- July prediction/results material remains
  `UNTRUSTED_LEGACY_CLAIM / QUARANTINED`.

## Claims allowed

- Draft PR #13 enforces authenticated semantic admission at the eight
  named public boundaries and revalidates it before atomic commit.
- Draft PR #13 detects the 1,280 declared synthetic attacks through
  source-tree and clean-installed-wheel execution.
- The installed synthetic fixture constructs the exact authenticated
  predecessor DAG with eight semantic admissions and eight lineages.
- Run, Stage, and Semantic authorities are independent runtime-only keys in
  the validated contract.
- These claims are code and synthetic adversarial enforcement claims only.

## Claims still forbidden

- real Data Foundation qualification or real backtest readiness;
- forecast accuracy, prospective skill, probability, or calibrated confidence;
- buy/sell, entry/exit, position, execution, or any recommendation;
- five-security or full-market coverage;
- provider authority, capture completeness, or rights to unverified bytes;
- `LIVE_OPERATIONAL` source status;
- production readiness or execution;
- any claim that PR #12 itself proved runtime enforcement.

## Privacy and repository safety

```text
credentials or sessions: NO
private Drive IDs: NO
raw conversations: NO
real runtime market data: NO
licensed data: NO
runtime HMAC keys: NO
destructive cleanup: NO
force push: NO
merge or auto-merge: NO
```

All HMAC keys used by synthetic checks were ephemeral runtime values. No real
market bytes, licensed evidence, browser state, credentials, or private
conversation material entered Git.

## User decisions required

- `KU-BO-008-D01`: `OPEN`. A product-specific outcome-session policy with a
  maximum extension and terminal treatment is still required before real
  outcome evaluation.
- `KU-BO-MERGE-003`: `APPROVED` conditionally for PR #12 followed by the
  implementation PR. The PR #12 portion is complete. The implementation
  evidence is published and exact-head CI-proven at `6dc821f`, but the merge
  portion cannot be exercised until this control-record head receives CI and
  the final merge-boundary recheck passes. Task metadata remains
  `MERGE_ALLOWED: NO`.

## Items classified for retention

```text
KEEP: semantic admission runtime, Schema, CLI, public-boundary wrappers, atomic output, and lineage contract
KEEP: Corpus v3, deterministic generator/audit, production Adapter, anti-oracle tests, and installed-wheel proof
KEEP: explicit Stage Binding v1 non-claim and all market/evidence/rights/policy blockers
KEEP: this COMPLETED implementation-evidence handoff and update it only with later merge/post-merge facts
ARCHIVE: PR #12 as historical TEST_SPEC_ONLY evidence; do not reinterpret it
ARCHIVE: stale PR #2/#3 as historical context; no closure or deletion authorized
PRIVATE_ONLY: runtime keys, real receipts, captured evidence, licensed files, and private conversations
DELETE_CANDIDATE: None
```

## Known limitations and risks

- The published implementation head passed GitHub Actions, but this
  control-record update creates a later head. Merge remains prohibited until
  that later head passes CI and the ordered merge boundary is rechecked.
- The adversarial corpus is synthetic. It cannot prove source availability,
  identity truth, provider authority, rights, denominator completeness, or
  market correctness.
- The installed DAG proves authenticated engineering flow using generated
  fixtures, not a production authority or real Data Foundation packet.
- `KU-BO-008-D01`, Benchmark scope compatibility, capture authority, and real
  market evidence remain independent blockers.

## Smallest logical next task

```text
TASK_ID: KU-BO-011-CONTROL-CI-AND-MERGE-RECHECK
PROPOSED_BRANCH: build/tri-security-receipt-enforcement-v0.2
DEPENDENCY: Draft PR #13 implementation head 6dc821f8342bf2041ac3bed983c6805ff0a2c3fc and CI run 31695010037 PASS, plus this control-record commit
GOAL: publish the control-record update, obtain exact-head GitHub Actions evidence, and perform the ordered KU-BO-MERGE-003 boundary recheck without weakening any non-claim
ENTRY_GATE: PR #13 remains Draft and the implementation evidence at 6dc821f remains green; CURRENT_TASK remains IN_PROGRESS and MERGE_ALLOWED remains NO
EXIT_GATE: the later control-record head passes all required GitHub Actions jobs and mergeability, changed-files, review, privacy/secret, and approval guards are rechecked before any merge action
```
