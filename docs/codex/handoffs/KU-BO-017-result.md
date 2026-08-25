# KU-BO-017 - Guarded daily research orchestration

```text
FINAL_STATUS: COMPLETED
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: agent/ku-bo-016-codex-live-bootstrap
STARTING_SHA: VERIFIED_REMOTE_BASE
TASK_BRANCH: agent/ku-bo-017-live-dry-run-orchestrator
FINAL_SHA: PUBLISHED_TASK_HEAD
DRAFT_PR: DRAFT_PR_CREATED
PR_BASE: agent/ku-bo-016-codex-live-bootstrap
CI_RUN: exact published task head / PASS / Python 3.11-3.14
STARTED_AT: 2026-08-25
COMPLETED_AT: 2026-08-25
```

## User goal

Understand the private Investing project history and the read-only predecessor,
retain only capabilities useful to KU-BO, keep the repository exclusively scoped
to Boursa Kuwait, and continue the project as a secure research system with source
development, daily dry runs, portfolio-state validation, and explicit training and
test admission gates.

## Verified starting state

The task started from the exact published KU-BO-016 branch head. The prior tree
contained a disabled live-bootstrap contract and Champion-freeze controls, but it
did not contain the KU-BO-017 market firewall, semantic source fallback,
predecessor capability-parity registry, point-in-time portfolio contract, Factor 9
admission validator, or resumable daily dry-run orchestrator. The repository was
kept on a new task branch; no prior PR was merged, rewritten, or force-pushed.

The private conversations, Drive inventory, and predecessor were reviewed outside
Git. They were treated as requirements and capability evidence, not as permission
to copy private bytes, merge another history, execute another engine, or publish a
private locator.

## Changes made

- Added `config/market_scope.json`, schema validation, and runtime checks that bind
  the engine to Boursa Kuwait, Kuwait, KWD, and `Asia/Kuwait`, with no alternate
  market adapter, runtime override, or cross-market training/evaluation path.
- Added source-quality and ordered source-fallback contracts. Transport success is
  distinct from semantic evidence, access controls cannot be bypassed, verified
  zero observations need receipts, and unresolved claims enter an original-source
  verification queue.
- Reimplemented useful jobs from `PRIVATE_PREDECESSOR_SOURCE` through one canonical
  `kubo` package and a strict parity registry. No second engine, Git-history merge,
  direct private script, raw dataset, or private locator was imported.
- Added point-in-time portfolio and order schemas with evidence hashes, byte sizes,
  freshness, reconciliation, and fail-closed partial-state handling. The resulting
  structure is deliberately non-actionable and cannot place an order.
- Added a private-manifest-driven Factor 9 admission validator. Artifact roles,
  gates, blockers, rights, provenance, and count reconciliation are required before
  admission; the current corpus remains blocked and cannot start training.
- Added the disabled KU-BO live-program contract for the four requested Kuwait-time
  cycles and a no-network, lock-protected, append-only, resumable dry-run with exact
  stage receipts, prior-session Champion enforcement, and sealed `ABSTAIN` output.
- Added the proposed KU-BO-018 event-admission contract for development events,
  controls, a disjoint locked test, purging, embargo, and walk-forward evaluation.
  No event collection or model training was started in KU-BO-017.
- Added one repository-local Codex research skill, schemas, CLI surfaces,
  adversarial tests, installed-wheel checks, CI gates, and sanitized documentation.

## Validation performed

```text
COMMAND_OR_JOB: focused KU-BO-017 contract and adversarial suite
RESULT: PASS
DETAIL: 122 tests passed; 4 environment-dependent tests skipped

COMMAND_OR_JOB: compile, config, control, diff, and privacy checks
RESULT: PASS
DETAIL: compileall, source and installed config validation, control integrity, diff check, skill validation, and Secret Guard passed

COMMAND_OR_JOB: installed local wheel
RESULT: PASS
DETAIL: repository-bound wheel built, installed in an isolated environment, and exercised through its public CLI and Factor 9 admission validator

COMMAND_OR_JOB: complete Linux CI matrix
RESULT: PASS
DETAIL: all jobs passed on Python 3.11, 3.12, 3.13, and 3.14; the main suite ran 2,229 tests and all KU-BO-017, smoke, privacy, reconciliation, and installed-wheel gates passed

COMMAND_OR_JOB: remote publication integrity
RESULT: PASS
DETAIL: the published branch tree exactly matched the locally validated tree and the pull request remained a draft with merge disabled
```

The complete local Windows baseline ran 2,225 tests. Its remaining 58 errors are
unchanged platform limitations: two require symlink privileges and the others
exercise safe directory-relative creation that is unavailable on Windows. The
authoritative Linux matrix passed those paths.

## Evidence and data status

`SYNTHETIC_ONLY` applies to repository fixtures and dry-run examples. `PARTIAL`
applies to the private Factor 9 inventory because storage and reconciliation do not
prove rights, identity, timestamp, Corporate Action, or outcome admission.
`LIVE_DEPENDENT` applies to future authorized market collection and source probes.
`LICENSED_FEED_DEPENDENT` applies to executable entry/exit quotes. The predecessor
capability registry proves software coverage only and is not financial evidence.

## Claims allowed

- KU-BO is fail-closed to Boursa Kuwait in its new market-scope contract.
- Ordered source fallback separates access, transport, parsing, and semantic use.
- The canonical package resolves every admitted predecessor user job without a
  second runtime or copied private implementation.
- Portfolio snapshots and dry-run receipts are hash-bound, point-in-time,
  no-overwrite, and non-actionable.
- Same-day, future-effective, unapproved, mismatched, or forged Champion freezes
  cannot enter the research-candidate stage.
- The four requested daily cycle contracts exist and remain disabled.

## Claims still forbidden

Real backtest readiness, model-training readiness, forecast accuracy, probability,
buy/sell recommendation, executable entry/exit prices, full-market coverage,
automatic promotion, guaranteed scheduling, and `LIVE_OPERATIONAL` source status
remain forbidden. No stock list or investment-facing result was generated.

## Privacy and repository safety

NO credentials or sessions, private Drive IDs, raw conversations, private source
locators, real runtime market bytes, licensed datasets, destructive cleanup,
force-push, merge, scheduler enablement, or email credentials are in the branch.
Private inventory and admission reports remain outside Git.

## User decisions required

`KU-BO-017-D01` authorized the Kuwait-only scope extension and guarded capability
translation. A new explicit decision is required before merge, scheduler
enablement, authenticated or paid source changes, training on admitted real data,
or any investment-facing output.

## Items classified for retention

```text
KEEP: market firewall, source policy, capability parity, portfolio contracts, Factor 9 admission, dry-run orchestrator, schemas, tests, CI, and sanitized docs
REFACTOR: none
ARCHIVE: raw conversations and predecessor inspection notes in private storage only
SUPERSEDE: any earlier idea of a second market or second runtime inside KU-BO
DELETE_CANDIDATE: none
PRIVATE_ONLY: Drive identifiers, raw source bytes, evidence manifests, reports, authorized exports, and future Champion freezes
```

## Known limitations and risks

Factor 9 is not admitted, no approved Champion freeze exists, and official
point-in-time identity, prices, Corporate Actions, rights, outcomes, and execution
evidence remain external gates. The daily schedules, live collection, training,
recommendation, and automatic email path are intentionally disabled. Public web
sources can fail or return semantically empty pages, so transport success alone can
never unlock analysis.

## Smallest logical next task

```text
TASK_ID: KU-BO-018
PROPOSED_BRANCH: agent/ku-bo-018-event-admission-registry
DEPENDENCY: exact published KU-BO-017 head plus privately admitted rights and point-in-time evidence
GOAL: materialize and validate the development-event, control, and locked-test registries without training a model
ENTRY_GATE: Factor 9 roles and admission gates pass; rights, identity, timestamps, Corporate Actions, and outcomes are hash-bound
EXIT_GATE: deduplicated and leakage-controlled registries, purged and embargoed walk-forward partitions, adversarial tests, wheel, Draft PR, and no recommendation
```
