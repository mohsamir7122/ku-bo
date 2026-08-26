# KU-BO - Codex Start Here

This is the repository-native entrypoint for every new Codex session.

## One-sentence instruction

Validate the locked bootstrap, verify the exact Git state, execute the single
active task through its acceptance gates, use `AI Rebuild` only as private runtime
storage, push only a task branch, open a Draft PR, and never merge, delete, or
publish private data without a separately recorded user decision.

## Required read and validation order

1. `AGENTS.md`
2. `config/codex_live_bootstrap.json`
3. run `python scripts/validate_codex_live_bootstrap.py --project-root . --json`
4. `docs/codex/PROJECT_RULES.md`
5. `docs/codex/CURRENT_STATUS.md`
6. `docs/codex/CURRENT_TASK.md`
7. `docs/codex/PRIVATE_PREDECESSOR_MIGRATION_EXECPLAN.md`
8. `docs/codex/migrations/private-predecessor-to-ku-bo/STATUS.md`
9. `docs/codex/migrations/private-predecessor-to-ku-bo/PRIVATE_SOURCE_ORIENTATION.md`
10. run `python scripts/validate_private_predecessor_migration_control.py --project-root . --json`
11. `docs/PROJECT_CONVERSATION_SYNTHESIS_AR.md`
12. `docs/FACTOR9_DRIVE_ADMISSION_AR.md`
13. `docs/CODEX_LIVE_HANDOFF_AR.md`
14. `docs/codex/ACCEPTANCE_GATES.md`
15. `docs/codex/CONVERSATION_IMPORT_POLICY.md`
16. `docs/codex/USER_DECISIONS.md`

Do not edit code before the bootstrap passes and the remote, base branch, current
HEAD, open PR dependency chain, and current CI state have been verified.

## Operating context

Repository:

```text
mohsamir7122/ku-bo
```

Active migration branch:

```text
agent/private-predecessor-capability-migration-v1
```

The branch is stacked on `agent/ku-bo-016-codex-live-bootstrap`, which is stacked
on `agent/ku-bo-015-source-access-recipes`. The exact heads and Draft PR state are
recorded in `docs/codex/CURRENT_STATUS.md`; always verify them live. Continue on
the existing migration branch when it exists. Do not create a duplicate branch.

## Active migration meaning

- The goal is complete user-job and capability parity, not a blind file or Git
  history merge.
- KU-BO remains the single canonical package, engine, CLI, evidence model, and
  decision boundary.
- The configured private predecessor is a read-only source. Resolve its exact
  repository and refs only in uncommitted private runtime storage; inspect every
  materially unique ref before declaring the private census complete.
- Treat source paths as potentially sensitive. Publish normal repository paths
  only after review; represent sensitive ones by opaque IDs and reconcile the
  census with Git-tree/blob counts and object-multiset digests.
- Do not port unsafe self-asserted authorization, fixed confidence, look-ahead,
  fabricated labels, or other behavior that conflicts with KU-BO gates. Preserve
  the user job through safe reimplementation and retain the old behavior only as
  a negative test or documented rejection.
- Keep skills thin and discoverable; put shared logic in `src/kubo`.
- A software migration may be complete while external data capabilities remain
  `LIVE_DEPENDENT` or `LICENSED_FEED_DEPENDENT`.

## Locked runtime meaning

- `READY_FOR_CODEX_EXECUTION` means the handoff contract is ready, not that a live
  collector, model, scheduler, or recommendation service exists.
- `AI Rebuild` is private storage. Discover Drive identifiers at runtime and never
  commit them.
- Factor 9 is `RESEARCH_ASSET_PENDING_ADMISSION`; preserve it and do not repeat its
  extraction or call it training truth.
- A daily report may use only a previous-session `APPROVED_CHAMPION` freeze.
- A same-day Challenger cannot issue that day's output or promote itself.
- Allowed pre-validation decisions are `RESEARCH_CANDIDATE`, `WATCH`, and `ABSTAIN`.
- The 15:07 and 15:37 Kuwait schedules are best-effort and disabled by default.

## Git permissions

Codex may fetch, inspect, create the declared task branch, edit within task scope,
run checks, push without force, and open or update a Draft PR. It may also write
sanitized manifests and reports while private evidence remains in Drive.

Codex may not merge or enable auto-merge; force-push; rewrite shared history;
delete branches, tags, evidence, conversations, or user files; commit credentials,
Drive identifiers, raw private conversations, licensed/private datasets, freezes,
or daily market evidence; or claim backtest readiness, accuracy, probability,
recommendation, or `LIVE_OPERATIONAL` status without the applicable gates.

## Completion behavior

Continue through inspect, edit, test, fix, rerun, package, and Draft PR publication
until every active acceptance gate passes or a genuine external dependency is
recorded. Never fabricate evidence or weaken a gate. Use
`docs/codex/HANDOFF_TEMPLATE.md` for the result and propose the smallest next task.

## Home activation prompt

The user can start the next Codex session with:

```text
Open `mohsamir7122/ku-bo`, check out the existing branch
`agent/private-predecessor-capability-migration-v1`, and read
`CODEX_START_HERE.md`. Resolve `PRIVATE_PREDECESSOR_SOURCE` only from the private
source locator supplied in this ChatGPT session. Run both locked validators,
verify the stacked PR chain, and execute `docs/codex/CURRENT_TASK.md` plus the
migration ExecPlan. Keep exact source metadata private, inventory every source
item and user job, safely reimplement them on KU-BO core, add the dedicated
evidence-verifying completion validator, run all gates, and update the same Draft
PR. Do not merge, modify the source, publish private metadata, train, run a real
backtest, or claim live/financial readiness.
```
