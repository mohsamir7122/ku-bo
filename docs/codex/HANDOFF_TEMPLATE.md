# KU-BO Codex Handoff Template

Use this template for every completed, partial, or blocked task. Save the result under:

```text
docs/codex/handoffs/<TASK_ID>-result.md
```

# <TASK_ID> — <Task title>

```text
FINAL_STATUS: COMPLETED | PARTIAL | BLOCKED
REPOSITORY:
BASE_BRANCH:
STARTING_SHA:
TASK_BRANCH:
FINAL_SHA:
DRAFT_PR:
PR_BASE:
CI_RUN:
STARTED_AT:
COMPLETED_AT:
```

## User goal

State the requested outcome in one precise paragraph.

## Verified starting state

Record:

- open PR chain;
- base and head SHAs;
- test count and CI status;
- material drift from the previous handoff;
- any pre-existing failures.

## Changes made

Group by coherent capability. Include exact important files and contracts, not a raw dump of every line changed.

## Validation performed

For each command or CI job, record:

```text
COMMAND_OR_JOB:
RESULT: PASS | FAIL | SKIPPED
DETAIL:
```

Include exact test counts where available.

## Evidence and data status

Classify every material deliverable:

```text
PROVEN_REAL_EVIDENCE
RECORDED_AUTHORIZED_FIXTURE
SYNTHETIC_ONLY
PARTIAL
BLOCKED
LIVE_DEPENDENT
LICENSED_FEED_DEPENDENT
```

Explain why.

## Claims allowed

List only claims supported by the branch and evidence.

## Claims still forbidden

Explicitly address:

```text
real backtest readiness
forecast accuracy
probability
recommendation
full-market coverage
LIVE_OPERATIONAL source status
```

## Privacy and repository safety

Confirm whether the branch contains:

- credentials or sessions;
- private Drive IDs;
- raw conversations;
- real runtime market data;
- licensed data;
- destructive cleanup.

Expected safe answer is `NO`, with any exception fully explained and authorized.

## User decisions required

Reference exact `DECISION_ID` entries from `docs/codex/USER_DECISIONS.md`. Write `None` when no user decision is required.

## Items classified for retention

Use:

```text
KEEP
REFACTOR
ARCHIVE
SUPERSEDE
DELETE_CANDIDATE
PRIVATE_ONLY
```

For every `DELETE_CANDIDATE`, provide the decision ID. Do not delete it.

## Known limitations and risks

State concrete limitations, affected scope, and failure mode.

## Smallest logical next task

Specify one next task with:

```text
TASK_ID:
PROPOSED_BRANCH:
DEPENDENCY:
GOAL:
ENTRY_GATE:
EXIT_GATE:
```

Do not describe the next task as completed.
