# KU-BO-013 — Kuwait historical knowledge planning layer

```text
FINAL_STATUS: PARTIAL
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: bafdda86b44b7603fe4adfa62dcc2a49bff8ae15
TASK_BRANCH: agent/kuwait-historical-knowledge-layer
FINAL_SHA: PENDING_PUBLICATION
DRAFT_PR: PENDING_PUBLICATION
PR_BASE: main
CI_RUN: PENDING_PUBLICATION
STARTED_AT: 2026-08-14
COMPLETED_AT: PENDING_EXACT_HEAD_CI
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
stale and superseded, not merged.

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
DETAIL: 2,082/2,082 in 278.335s

COMMAND_OR_JOB: compile, smoke, JSON/Schema, config/CLI, diff, control
RESULT: PASS
DETAIL: no contract or control errors

COMMAND_OR_JOB: Secret Guard, wheel build, isolated install, installed CLI
RESULT: PASS
DETAIL: wheel 450075 bytes; SHA-256 3bf841d569e00a06646c72d7f9f82d3e3dcbec7fe27d1cd331fa89d68e97726c

COMMAND_OR_JOB: PR exact-head GitHub Actions
RESULT: SKIPPED
DETAIL: pending Draft PR publication
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

`KU-BO-013-D01` authorizes this development and Draft PR. A new explicit merge
decision is required before merging KU-BO-013.

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
