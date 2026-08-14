# KU-BO-013 — Kuwait historical knowledge planning layer

```text
FINAL_STATUS: PARTIAL
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: bafdda86b44b7603fe4adfa62dcc2a49bff8ae15
TASK_BRANCH: agent/kuwait-historical-knowledge-layer
FINAL_SHA: 27dedec792b7f057a975131562898a325fa372a1 (published implementation head; later merge-authority control head pending exact CI)
DRAFT_PR: #15 / https://github.com/mohsamir7122/ku-bo/pull/15
PR_BASE: main
CI_RUN: 31785060069 / PASS / implementation head / Python 3.11-3.14; later authorization head pending
STARTED_AT: 2026-08-14
COMPLETED_AT: IN_PROGRESS
```

## User goal

Merge and prepare the existing project, then program six source-backed Kuwait
historical research layers without attempting the full centuries-long collection
in this coding stage.

## Verified starting state

PR #14 exact head `73dc3daa994ffd4d41317cf486820264227a85f2`
passed CI run `31782243633` on Python 3.11 through 3.14. It was then merged to
main as `bafdda86b44b7603fe4adfa62dcc2a49bff8ae15`; post-merge main CI run
`31783361999` also passed on all four Python versions. PR #2 and PR #3 remain
stale and superseded, not merged. KU-BO-013 was published as Draft PR #15 at
implementation head `27dedec792b7f057a975131562898a325fa372a1`; exact-head CI
run `31785060069` passed on Python 3.11 through 3.14 and GitHub reported the PR
clean and mergeable before the later authorization-record change.

## Changes made

- Added a strict registry of 26 source definitions with authority, role,
  earliest-year, access, rights, automation, and `DEFINED_ONLY` metadata.
- Added six deterministic annual layers and bilingual/alternate query templates.
- Added a planner that emits 756 gap-free `NOT_COLLECTED` tasks at cutoff
  2026-08-14, preserving company-name placeholders until official enumeration.
- Added primary-source gates for company identity/status and official/procedural
  gates for allegations, regulatory actions, and court outcomes.
- Added plan, historical-event, and company-annual-history Schemas.
- Added `validate-historical-knowledge` and `plan-historical-research` CLI flows.
- Added Arabic architecture/operations documentation and 15 focused tests.

## Validation performed

```text
COMMAND_OR_JOB: targeted historical and control tests
RESULT: PASS
DETAIL: 19/19

COMMAND_OR_JOB: complete unittest suite
RESULT: PASS
DETAIL: 2,082/2,082 in 436.936s on the merge-authorization tree

COMMAND_OR_JOB: compile, smoke, JSON/Schema, config/CLI, diff, control
RESULT: PASS
DETAIL: no contract or control errors

COMMAND_OR_JOB: Secret Guard, wheel build, isolated install, installed CLI
RESULT: PASS
DETAIL: wheel 450075 bytes; SHA-256 d74516550c72eaed7e998f59287b2de6721ab97bedf51ad93a178a6fdcb51b4f; installed validate, plan, and validate-config flows passed

COMMAND_OR_JOB: PR exact-head GitHub Actions
RESULT: PASS
DETAIL: run 31785060069 at implementation head 27dedec792b7f057a975131562898a325fa372a1 passed Python 3.11 through 3.14; the later authorization-record head requires fresh exact-head CI before merge
```

## Evidence and data status

`SYNTHETIC_ONLY` for executable contract tests and `LIVE_DEPENDENT` for all
future collection. The branch commits no historical corpus, company-universe
export, court dataset, social content, or market bytes. Every historical source
remains `DEFINED_ONLY`; all 756 tasks remain `NOT_COLLECTED`.

## Claims allowed

- The code validates and plans the six requested year ranges deterministically.
- The source registry and claim-role restrictions are implemented and tested.
- At cutoff 2026-08-14 the plan contains 756 annual work units without year gaps.

## Claims still forbidden

Real historical completeness, full company-universe coverage, live connector
operation, guilt inference, direct use of social posts as factual confirmation,
real backtest readiness, forecast accuracy, probability, recommendation, and
production readiness remain forbidden.

## Privacy and repository safety

NO credentials, sessions, private Drive IDs, raw conversations, real runtime
market data, licensed data, access-control bypass, or destructive cleanup were
committed.

## User decisions required

`KU-BO-013-D01` authorized development and Draft publication.
`KU-BO-MERGE-005` now authorizes merging PR #15 only after the later
authorization-record head passes exact-head CI and the final mergeability
boundary is rechecked. No further user decision is currently required.

## Items classified for retention

```text
KEEP: all KU-BO-013 code, config, Schemas, tests, and documentation
KEEP: existing KU-BO-012 research and stop gates
SUPERSEDE: no files
DELETE_CANDIDATE: none
PRIVATE_ONLY: any later authenticated registry export or private social material
```

## Known limitations and risks

The source registry is a starting map, not an exhaustive proof of archive
coverage. MOCI, court, gazette, press, and platform access may require manual,
authenticated, licensed, or rights-reviewed acquisition. Listed companies do
not equal all Kuwait companies. Old archives carry provenance and viewpoint
bias. Search absence never proves event absence.

## Smallest logical next task

```text
TASK_ID: KU-BO-014
PROPOSED_BRANCH: agent/kuwait-history-capture-pilot
DEPENDENCY: KU-BO-013 review plus source-specific rights/access decision
GOAL: Execute a small official-source pilot for selected years and companies, preserving raw evidence and coverage gaps.
ENTRY_GATE: approved pilot scope, rights, public-access method, and official company enumeration source
EXIT_GATE: rehashable pilot artifacts, parser validation, no completeness claim, and exact-head CI
```
