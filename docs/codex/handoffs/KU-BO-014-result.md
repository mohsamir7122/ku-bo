# KU-BO-014 — Isolated Bootstrap Archive scaffold

```text
FINAL_STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: 59833bf73510b3aa3901f628cbf2c13c0d01cf79
TASK_BRANCH: agent/bootstrap-archive-v0.1
FINAL_SHA: c8b41b23e5ebe4f4243b42506862c36149d481c8 (implementation head)
DRAFT_PR: https://github.com/mohsamir7122/ku-bo/pull/17
PR_BASE: main
CI_RUN: 31840391449 PASS (implementation head; later control-record head pending)
STARTED_AT: 2026-08-14
COMPLETED_AT: IN_PROGRESS
```

## User goal

Retain the existing KU-BO repository and build an isolated historical Bootstrap
Archive first, followed later by Company Intelligence, source waves, and final
Boursa Kuwait reconciliation. The present stage prepares the archive scaffold;
testing follows after the scaffold implementation is complete.

## Verified starting state

- `origin/main` and the task starting point resolve to
  `59833bf73510b3aa3901f628cbf2c13c0d01cf79`.
- The baseline contains the merged KU-BO-013 historical planning layer and the
  PR #16 evidence-gate hardening.
- The historical catalog contains 28 `DEFINED_ONLY` source definitions and six
  layers; no historical corpus or official company universe is present.
- KU-BO-014 begins on `agent/bootstrap-archive-v0.1`.
- Draft PR #17 publishes the implementation at `c8b41b23e5ebe4f4243b42506862c36149d481c8`.
- Exact-head GitHub Actions Run `31840391449` passed on Python 3.11–3.14.
- This record creates a later documentation-only head that requires its own CI.

## Changes made

Work is in progress on the following bounded capability:

- isolated archive contract and directory policy;
- declared-only historical-to-network source Crosswalk;
- deterministic reuse of the KU-BO-013 historical plan;
- atomic no-overwrite workspace preparation;
- control-only Manifest and stage descriptors with zero Evidence;
- reopening, hashing, and exact-inventory verification;
- the collection gate and all three downstream stage gates remain blocked until real prerequisites pass;
- task controls and Arabic architecture documentation.

This list describes the active implementation scope. It is not a final claim
that each item has passed acceptance validation.

## Validation performed

```text
COMMAND_OR_JOB: KU-BO-014 targeted tests
RESULT: PASS
DETAIL: 34/34 archive-only; 57/57 with historical and Codex control tests.

COMMAND_OR_JOB: complete unittest suite
RESULT: PASS
DETAIL: 2,120/2,120 in 158.371s on the final local implementation tree.

COMMAND_OR_JOB: compile, smoke, Secret Guard, strict JSON/Schema, control check
RESULT: PASS
DETAIL: Codex control inspected 18 control files and reported zero errors or warnings; KU-BO-011 corpus check/audit passed 1,280 cases.

COMMAND_OR_JOB: wheel build and isolated install
RESULT: PASS
DETAIL: final wheel 465934 bytes, SHA-256 707b351aa546e565826c3372acb78fe95e234b7e61af2a5d4b8009c5d91cbab0; installed CLI validated config, prepared, and independently verified the scaffold outside the checkout.

COMMAND_OR_JOB: exact-head GitHub Actions
RESULT: PASS
DETAIL: Draft PR #17 implementation head c8b41b23e5ebe4f4243b42506862c36149d481c8 passed Run 31840391449 on Python 3.11–3.14. The later control-record head remains subject to exact-head CI.
```

## Evidence and data status

`SYNTHETIC_ONLY` for executable contract tests, `PROVEN` locally for the empty
control scaffold's deterministic generation and tamper verification, and
`LIVE_DEPENDENT` for all future collection. The archive begins with zero
historical Evidence artifacts, zero events, and zero companies. Crosswalk
entries remain declarative and do not authorize collection. Publication and
exact-head CI remain pending.

## Claims allowed

- KU-BO-014 is authorized for development as an empty archive scaffold.
- The local scaffold reuses all 756 KU-BO-013 tasks and verifies zero Evidence,
  companies, and events after atomic publication.
- The task is `IN_PROGRESS` on `agent/bootstrap-archive-v0.1`.
- No merge authority exists for KU-BO-014.

No implementation-readiness claim is allowed until the pending validation is
recorded against an exact commit.

## Claims still forbidden

Historical completeness, official company-universe completeness, live source
operation, Connector orParser readiness inferred from the Crosswalk, real
backtest readiness, forecast accuracy, probability, recommendation,
full-market coverage, `LIVE_OPERATIONAL`, and production readiness remain
forbidden.

## Privacy and repository safety

The task scope authorizes no credentials, sessions, private Drive IDs, raw
conversations, real runtime market data, licensed data, historical corpus,
access-control bypass, destructive cleanup, or merge. Expected result: `NO` for
all such content; final confirmation remains part of acceptance validation.

## User decisions required

`KU-BO-014-D01` authorizes development and a Draft PR only. A separate future
merge decision is required after the final exact head passes every gate.

## Items classified for retention

```text
KEEP: KU-BO-013 historical catalog, layer definitions, schemas, and validators
KEEP: KU-BO-014 archive contracts, tests, and documentation after validation
PRIVATE_ONLY: all future raw historical bytes and protected runtime receipts
SUPERSEDE: none
DELETE_CANDIDATE: none
```

## Known limitations and risks

- Historical and Source Network IDs use different namespaces; the Crosswalk is
  semantic only and cannot be mistaken for an executable source capability.
- Several historical sources have no network equivalent and remain unmapped.
- Company-year plan rows are templates, not enumerated company tasks.
- Company Intelligence cannot begin without official effective-dated universe
  evidence.
- The empty Manifest cannot establish that a year has no verified events.
- Final validation, PR publication, and exact-head CI are still pending.

## Smallest logical next task

```text
TASK_ID: KU-BO-014-PUBLISH-AND-CI
PROPOSED_BRANCH: agent/bootstrap-archive-v0.1
DEPENDENCY: local implementation and acceptance validation pass
GOAL: commit and publish the exact implementation head, open a Draft PR, run exact-head CI, and update this handoff with immutable identifiers
ENTRY_GATE: 2,120-test full suite, smoke, Secret Guard, corpus audit, wheel, and installed CLI pass with no live collection
EXIT_GATE: exact-head CI passes on Python 3.11-3.14 and merge remains blocked
```
