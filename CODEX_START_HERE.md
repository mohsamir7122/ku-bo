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
7. `docs/PROJECT_CONVERSATION_SYNTHESIS_AR.md`
8. `docs/FACTOR9_DRIVE_ADMISSION_AR.md`
9. `docs/CODEX_LIVE_HANDOFF_AR.md`
10. `docs/codex/ACCEPTANCE_GATES.md`
11. `docs/codex/CONVERSATION_IMPORT_POLICY.md`
12. `docs/codex/USER_DECISIONS.md`

Do not edit code before the bootstrap passes and the remote, base branch, current
HEAD, open PR dependency chain, and current CI state have been verified.

## Operating context

Repository:

```text
mohsamir7122/ku-bo
```

Active bootstrap branch:

```text
agent/ku-bo-016-codex-live-bootstrap
```

The exact head and Draft PR state are recorded in `docs/codex/CURRENT_STATUS.md`.
Always verify them live. `KU-BO-015` is the dependency for this bootstrap, and the
active next task is defined in `docs/codex/CURRENT_TASK.md`.

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
Read CODEX_START_HERE.md and execute CURRENT_TASK end to end. Start with the locked
bootstrap validator, keep AI Rebuild private, preserve and admit Factor 9, build the
daily dry-run and previous-freeze controls, run all gates, and open a Draft PR. Do
not merge or publish private data.
```
