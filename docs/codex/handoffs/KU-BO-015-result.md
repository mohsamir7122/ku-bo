# KU-BO-015 — Source-access recipes and capability-probe planning

```text
FINAL_STATUS: PARTIAL
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: 59833bf73510b3aa3901f628cbf2c13c0d01cf79
TASK_BRANCH: agent/ku-bo-015-source-access-recipes
FINAL_SHA: PENDING_FIRST_PUBLICATION
DRAFT_PR: PENDING
PR_BASE: main
CI_RUN: PENDING_EXACT_HEAD_GITHUB_ACTIONS
STARTED_AT: 2026-08-24
COMPLETED_AT: IN_PROGRESS
```

## User goal

Inspect the current repository and convert the practical lessons from reviewed
Kuwait market sources into a concrete repository improvement, while preserving
the existing evidence, authorization, privacy, and non-forecast boundaries.

## Verified starting state

The task started from `main` at
`59833bf73510b3aa3901f628cbf2c13c0d01cf79` on a new isolated branch. Draft PR
#17 (`KU-BO-014`) and Draft PR #18 (HUMANSOFT data-domain separation) were open;
PRs #2 and #3 were stale older work. None was modified or merged. The starting
tree was clean, and no pre-existing failure was encountered. The previous
handoff did not encode the reviewed public-page, rendered-page, authorized
export, account, archive, licensed-access, and terminal-state rules as one
machine-readable contract.

## Changes made

- Added `config/source_access_recipes.json`: 14 `DEFINED_ONLY` recipes covering
  30 priority source definitions, with 38 catalog sources explicitly uncovered.
- Added `src/kubo/source_access_recipes.py`: strict duplicate-key JSON loading,
  route/access/capture/rights matrices, deterministic registry-hash-bound plans,
  aggregate task/byte/timeout gates, and plan-bound access-receipt validation.
- Bound readable probe states to raw artifacts and SHA-256 through the existing
  access-probe contract; terminal states require controlled reasons and never
  prove successful access.
- Registered the reviewed Investing user-export importer with the hard
  `PRICE_IMPORT_READY_ONLY` ceiling and added the same ceiling to its report.
- Added two JSON Schemas, three CLI flows, Arabic operations documentation, and
  18 focused normal/adversarial source-access tests.

## Validation performed

```text
COMMAND_OR_JOB: focused source-access, user-export, and Schema tests
RESULT: PASS
DETAIL: 30/30 with jsonschema 4.25.1

COMMAND_OR_JOB: complete unittest suite
RESULT: PASS
DETAIL: 2,104/2,104 in 192.823 seconds

COMMAND_OR_JOB: compileall, diff check, strict config and Schema validation
RESULT: PASS
DETAIL: source-access recipe report PASS_CONTRACT; validate-config PASS

COMMAND_OR_JOB: Codex control integrity
RESULT: PASS
DETAIL: KU-BO-015 and expected branch matched with 0 errors and 0 warnings

COMMAND_OR_JOB: KU-BO-011 deterministic corpus generation and audit
RESULT: PASS
DETAIL: 1,280 cases; SHA-256 e7e84f75feae5ea72a5d4f67af50da24f5d46e5a9cba49030ff8547a41b50288

COMMAND_OR_JOB: synthetic smoke and Secret Guard
RESULT: PASS
DETAIL: no secret pattern; smoke retained 0 LIVE_OPERATIONAL sources

COMMAND_OR_JOB: final wheel build, isolated install, and installed CLI
RESULT: PASS
DETAIL: 459184 bytes; SHA-256 d3f2257f1dc4de154033a84c3e36fe4df852cb3f7b5c8a8ec8c95fa9e8e1ac06; installed validate, two-source plan, plan revalidation, and importer help passed

COMMAND_OR_JOB: exact-head GitHub Actions
RESULT: SKIPPED
DETAIL: pending first publication of the isolated branch and Draft PR
```

## Evidence and data status

`SYNTHETIC_ONLY` applies to generated test artifacts. `LIVE_DEPENDENT` applies
to every later public or account access attempt. `LICENSED_FEED_DEPENDENT`
applies to the ICE recipe and any future broker/vendor source. No real source
probe, market row, historical corpus, licensed byte, or operational entitlement
was used or created.

## Claims allowed

- The repository can validate 14 access-recipe definitions covering 30 catalog
  sources and identify 38 uncovered definitions.
- It can deterministically create metadata-only plans bound to the exact recipe
  file hash and registered Start URL.
- It can validate whether a later access receipt matches the plan and controlled
  access-state contract.
- The full current plan stays within 30 tasks, 120 MiB, and 300 seconds.

## Claims still forbidden

Real backtest readiness, forecast accuracy, probability, recommendation,
full-market coverage, complete historical coverage, connector or parser success,
official EOD, execution tape, entitlement, and `LIVE_OPERATIONAL` source status
remain forbidden.

## Privacy and repository safety

NO credentials or sessions, private Drive IDs, raw conversations, real runtime
market data, licensed data, private account identifiers, access-control bypass,
force-push, merge, destructive cleanup, or deletion are present in this branch.

## User decisions required

`KU-BO-015-D01` authorized this code/contract implementation and Draft
publication. A separate recorded decision is required before any authenticated,
licensed, or systematic live probe and before any merge. No additional decision
is required to publish the current Draft PR.

## Items classified for retention

```text
KEEP: KU-BO-015 code, recipe registry, Schemas, tests, CLI, and documentation
KEEP: existing source-network and live-probe contracts reused by this task
REFACTOR: none
ARCHIVE: none
SUPERSEDE: none
DELETE_CANDIDATE: none
PRIVATE_ONLY: credentials, sessions, account exports, entitlement records, and any real captured bytes
```

## Known limitations and risks

Thirty-eight catalog sources still have no reviewed recipe. A recipe is a
declared path, not evidence that a site is reachable or that access is legally
authorized. The first registered Start URL may later move. Protected and
licensed paths require external authorization and trust. A valid blocked receipt
proves only that the failure state was recorded correctly. The existing two
fixture-tested parsers are not live capability.

## Smallest logical next task

```text
TASK_ID: KU-BO-016
PROPOSED_BRANCH: agent/ku-bo-016-authorized-access-probe-pilot
DEPENDENCY: reviewed probe scope plus explicit rights/runtime authorization and any required user exports or entitlement
GOAL: Execute a small source-access pilot against selected recipes and preserve hash-bound access-state receipts without parsing or capability promotion.
ENTRY_GATE: exact source list, rights class, operator identity, time/byte budget, stop conditions, and no-bypass approval
EXIT_GATE: plan-bound receipts for every selected source, controlled terminal reasons, raw hashes only where readable, no market-evidence or LIVE_OPERATIONAL claim, and exact-head CI
```
