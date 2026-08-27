# KU-BO-ONE-SECURITY-CHECKPOINT-V2 — One-security durable checkpoint v2

```text
FINAL_STATUS: PARTIAL
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: 8514438ab2011dcabfabbe5e0439ac6caf33f276
TASK_BRANCH: codex/one-security-checkpoint-v2
FINAL_SHA: PENDING — working tree is not yet a validated committed head
DRAFT_PR: #26
PR_BASE: main
CI_RUN: PENDING — no new exact-head CI run exists for the in-progress implementation
STARTED_AT: NOT_RECORDED
COMPLETED_AT: NOT_APPLICABLE — task remains in progress
```

## User goal

Implement a separate, fail-closed checkpoint v2 for one numeric Kuwait
`security_code`, preserving the exact 29-source/seven-wave sequence, durable
resume and reconciliation semantics, and an authenticated terminal seal without
changing legacy checkpoint v1 behavior or enabling live/private-runtime access.

## Verified starting state

- `main` was fixed at merged PR #25 SHA
  `8860989f6a2affdc66bc790f639757c9a897f353`, with post-merge CI run
  `33102246889` passing.
- Draft PR #26 started at head
  `8514438ab2011dcabfabbe5e0439ac6caf33f276` on
  `codex/one-security-checkpoint-v2`, directly above that `main` base.
- The starting PR head contained task/control scaffolding, not the complete
  checkpoint-v2 implementation or its terminal handoff.
- Starting-head CI run `33104453671` failed on Python 3.11-3.14 because required
  historical migration-control compatibility fields were absent from
  `CURRENT_TASK`; this was a control mismatch, not proof of a checkpoint-runtime
  failure.
- The frozen working tree passed 2,568/2,568 local tests; commit/push and a clean
  exact-head GitHub CI result remain `PENDING`.
- Issue #27 (`KU-BO-HYBRID-001`) remains queued behind the PR #26 readiness gate;
  it has not been started by this partial handoff.

## Changes made

The working tree currently contains an in-progress synthetic checkpoint-v2
candidate:

- a separate `issuer_checkpoint_v2` implementation with proposed CAS/fencing,
  resume, reopening, reconciliation, and HMAC terminal-seal behavior;
- six versioned checkpoint-v2 JSON Schemas, including the retained source manifest;
- focused functional, adversarial, and installed-CLI test candidates;
- a bounded installed CLI validation command and corresponding CI/README wiring;
- restored historical migration-control compatibility metadata and task-agnostic
  control-test repairs.

These changes are not yet represented by a final commit SHA and are not claimed
as accepted until the validation gates below complete.

## Validation performed

```text
COMMAND_OR_JOB: python scripts/validate_codex_live_bootstrap.py --project-root . --json
RESULT: PASS
DETAIL: Bootstrap contract passed during the current work session; this is not final exact-head CI.
```

```text
COMMAND_OR_JOB: python scripts/validate_private_predecessor_migration_control.py --project-root . --json
RESULT: PASS
DETAIL: Preparation control passed after restoration of the historical compatibility fields.
```

```text
COMMAND_OR_JOB: python scripts/codex_control_check.py
RESULT: PASS
DETAIL: Control selected KU-BO-ONE-SECURITY-CHECKPOINT-V2 on codex/one-security-checkpoint-v2.
```

```text
COMMAND_OR_JOB: focused legacy control/runtime regression group
RESULT: PASS
DETAIL: 64/64 tests passed before final checkpoint-v2 validation; this is not the final suite count.
```

```text
COMMAND_OR_JOB: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest -q tests.test_issuer_checkpoint_v2 tests.test_issuer_checkpoint_v2_adversarial tests.test_issuer_checkpoint_v2_cli
RESULT: PASS
DETAIL: 56/56 functional, adversarial, schema, recovery, temporal-causality, and CLI tests passed on the frozen working tree.
```

```text
COMMAND_OR_JOB: v1/v2 compatibility group
RESULT: PASS
DETAIL: 98/98 tests passed: priority checkpoint v1, issuer-sequential v1, checkpoint v2, adversarial recovery, and CLI.
```

```text
COMMAND_OR_JOB: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests -q
RESULT: PASS
DETAIL: 2,568/2,568 tests passed in 243.880 seconds on the frozen working tree.
```

```text
COMMAND_OR_JOB: schema, smoke, compile, Secret Guard, corpus, control, bootstrap, and migration gates
RESULT: PASS
DETAIL: Six schemas parsed and passed Draft 2020-12/generated-document checks; Compile, Smoke, Secret Guard, corpus audit, control, bootstrap, and migration preparation exited 0.
```

```text
COMMAND_OR_JOB: build/install wheel and exercise installed kubo validate-issuer-checkpoint-v2
RESULT: PASS
DETAIL: Wheel SHA-256 86d5965fbccaad3b76b649488b47e00afc0d01b74b1d38af47bef399099a79bf installed in an isolated venv; installed CLI authenticated and reopened a generated 29-receipt/seven-wave terminal seal.
```

```text
COMMAND_OR_JOB: GitHub Actions exact-head CI on Python 3.11-3.14
RESULT: SKIPPED
DETAIL: PENDING until a clean final head is committed and pushed to Draft PR #26.
```

## Evidence and data status

```text
SYNTHETIC_ONLY
```

Only generated temporary fixtures are permitted. No public-market collection,
private runtime, Google Drive write, licensed feed, or real checkpoint evidence
is part of this task. The current deliverable is `PARTIAL` because its acceptance
and exact-head validation gates remain open.

## Claims allowed

- PR #26 remains a Draft, unmerged software task.
- The checkpoint-v2 candidate is separate from legacy checkpoint v1 and issuer
  sequential v1 contracts by design.
- The task boundary is synthetic-only and enables no live source or private
  runtime operation.
- Final implementation correctness and durability are not yet claimed.

## Claims still forbidden

- real backtest readiness;
- forecast accuracy;
- probability;
- recommendation;
- full-market coverage;
- `LIVE_OPERATIONAL` source status;
- production-durable checkpoint operation;
- real evidence admission or Google Drive publication.

## Privacy and repository safety

```text
credentials or sessions:       NO — Secret Guard PASS
private Drive IDs:              NO — Secret Guard PASS
raw conversations:              NO — Secret Guard PASS
real runtime market data:       NO — synthetic fixtures only
licensed data:                  NO
destructive cleanup:            NO
```

No exception is authorized. This partial handoff does not grant runtime access
or weaken the final repository-safety gates.

## User decisions required

- `KU-BO-CHK-D01` remains `OPEN`: no private-runtime or Google Drive checkpoint
  write is authorized.
- `KU-BO-MIG-D02` remains `OPEN`: PR #21 remains Draft and unmerged.

Neither decision blocks completing and validating this synthetic-only PR #26.

## Items classified for retention

```text
KEEP: separate checkpoint-v2 module, versioned schemas, focused/adversarial tests, bounded validator CLI, task control metadata
REFACTOR: none classified at this partial boundary
ARCHIVE: none
SUPERSEDE: starting-head control mismatch once a new validated head replaces it
DELETE_CANDIDATE: none
PRIVATE_ONLY: any future real checkpoint roots, raw evidence, runtime grants, HMAC key bytes, and Drive identifiers
```

## Known limitations and risks

- The implementation is locally validated and frozen but remains uncommitted;
  its final SHA and exact-head GitHub CI do not exist yet.
- The local targeted/adversarial, full-suite, schema, Secret Guard, and
  installed-wheel/CLI gates pass; commit/push and exact-head GitHub CI remain pending.
- No final SHA can be recorded until the implementation is committed; recording
  the starting SHA as a final head would be false.
- Synthetic temporary-filesystem success, when established, will not prove
  production storage durability or authorize private-runtime writes.
- PR #26 must remain Draft and must not be merged under the current task contract.

## Smallest logical next task

```text
TASK_ID: KU-BO-HYBRID-001 (Issue #27)
PROPOSED_BRANCH: codex/kuwait-hybrid-full-market-collection-v1
DEPENDENCY: Draft PR #26 at its exact final green head
GOAL: Begin the bounded Kuwait hybrid full-market collection task under Issue #27's rights, reuse, append-only, test, and acceptance gates.
ENTRY_GATE: PR #26 has a terminal handoff, a clean pushed exact head, all applicable exact-head GitHub CI green, and no unresolved control mismatch; then create the stacked branch from that exact green head and record PR #26 as its dependency before marking Issue #27 STARTED.
EXIT_GATE: Defined by Issue #27; this partial handoff makes no completion claim for it.
```

Issue #27 remains gated and queued. This document does not start it.
