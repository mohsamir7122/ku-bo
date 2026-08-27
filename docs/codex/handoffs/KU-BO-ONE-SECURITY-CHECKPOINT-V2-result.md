# KU-BO-ONE-SECURITY-CHECKPOINT-V2 — One-security durable checkpoint v2

```text
FINAL_STATUS: COMPLETED
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: 8514438ab2011dcabfabbe5e0439ac6caf33f276
TASK_BRANCH: codex/one-security-checkpoint-v2
FINAL_SHA: f39e19df76f2fb15f7a7801bf3874fc3e5455a23 — validated implementation head
DRAFT_PR: #26
PR_BASE: main
CI_RUN: 33124534059 — PASS on Python 3.11-3.14 for the validated implementation head
STARTED_AT: 2026-08-27T18:37:57Z
COMPLETED_AT: 2026-08-28T02:15:13+03:00
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
- The frozen tree passed 2,568/2,568 local tests, was pushed as `f39e19d`, and
  exact-head GitHub CI run `33124534059` passed on Python 3.11-3.14.
- Issue #27 (`KU-BO-HYBRID-001`) remains queued until the terminal status commit
  receives its own exact-head CI; it is not started by this handoff alone.

## Changes made

Validated implementation head `f39e19d` contains the completed synthetic
checkpoint-v2 software contract:

- a separate `issuer_checkpoint_v2` implementation with proposed CAS/fencing,
  resume, reopening, reconciliation, and HMAC terminal-seal behavior;
- six versioned checkpoint-v2 JSON Schemas, including the retained source manifest;
- focused functional, adversarial, and installed-CLI test candidates;
- a bounded installed CLI validation command and corresponding CI/README wiring;
- restored historical migration-control compatibility metadata and task-agnostic
  control-test repairs.

These changes are represented by validated implementation head `f39e19d`; the
validation gates below completed successfully.

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
RESULT: PASS
DETAIL: Run 33124534059 passed for implementation head f39e19df76f2fb15f7a7801bf3874fc3e5455a23. The terminal docs/control commit is intentionally followed by one fresh CI run before Issue #27 begins.
```

## Evidence and data status

```text
SYNTHETIC_ONLY
```

Only generated temporary fixtures are permitted. No public-market collection,
private runtime, Google Drive write, licensed feed, or real checkpoint evidence
is part of this task. The completed deliverable proves the synthetic software
contract only.

## Claims allowed

- PR #26 remains a Draft, unmerged software task.
- The checkpoint-v2 candidate is separate from legacy checkpoint v1 and issuer
  sequential v1 contracts by design.
- The task boundary is synthetic-only and enables no live source or private
  runtime operation.
- The synthetic checkpoint-v2 implementation passed its functional,
  adversarial, installed-wheel, and exact-head CI gates.

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

No exception is authorized. This terminal handoff does not grant runtime access
or weaken the final repository-safety gates.

## User decisions required

- `KU-BO-CHK-D01` remains `OPEN`: no private-runtime or Google Drive checkpoint
  write is authorized.
- `KU-BO-MIG-D02` remains `OPEN`: PR #21 remains Draft and unmerged.

Neither decision blocks completing and validating this synthetic-only PR #26.

## Items classified for retention

```text
KEEP: separate checkpoint-v2 module, versioned schemas, focused/adversarial tests, bounded validator CLI, task control metadata
REFACTOR: none classified at this terminal boundary
ARCHIVE: none
SUPERSEDE: starting-head control mismatch once a new validated head replaces it
DELETE_CANDIDATE: none
PRIVATE_ONLY: any future real checkpoint roots, raw evidence, runtime grants, HMAC key bytes, and Drive identifiers
```

## Known limitations and risks

- The validated implementation is pushed at `f39e19d` with exact-head CI green.
- The terminal docs/control commit must also receive fresh exact-head CI before
  the queued Issue #27 branch is created.
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
EXIT_GATE: Defined by Issue #27; this terminal handoff makes no completion claim for it.
```

Issue #27 remains gated and queued. This document does not start it.
