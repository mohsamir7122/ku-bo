# KU-BO — Codex Start Here

This file is the repository-native entrypoint for a new Codex session.

## One-sentence instruction

Inspect `mohsamir7122/ku-bo`, read the control files below in order, execute the single active task to its acceptance gates, push only a task branch, open or update a Draft PR, and never merge or delete without an explicit recorded user decision.

## Required read order

1. `AGENTS.md`
2. `docs/codex/PROJECT_RULES.md`
3. `docs/codex/CURRENT_STATUS.md`
4. `docs/codex/CURRENT_TASK.md`
5. `docs/codex/ACCEPTANCE_GATES.md`
6. `docs/codex/CONVERSATION_IMPORT_POLICY.md`
7. `docs/codex/USER_DECISIONS.md`

Do not start implementation before resolving the repository, base branch, current HEAD SHA, stacked PR chain, and current CI state.

## Operating context

Repository:

```text
mohsamir7122/ku-bo
```

Current development chain at the time this control layer was created:

```text
PR #4  Research Price History
PR #5  Current Official Identity + 2026 Trading Calendar
PR #6  Current Security Status + Corporate Action Schedule
PR #7  Corporate Action Enrichment + Historical Status Intervals
```

PR #7 head when this file was created:

```text
build/ca-enrichment-status-history-v0.2
570cfda44eedfea91220a500c494f493eed49763
```

The control layer branch is:

```text
ops/codex-control-center-v0.1
```

Always verify live GitHub state; never treat the values above as current merely because they appear in this file.

## Git permissions

Codex may:

- fetch and inspect the repository and open PRs;
- create a task branch from the verified active control/development head;
- edit code, tests, schemas, and documentation within the declared task;
- run local checks and inspect GitHub Actions;
- commit and push the task branch;
- open or update a Draft PR;
- write a sanitized handoff report.

Codex may not:

- merge any PR;
- force-push;
- rewrite shared history;
- delete `main`, tags, PR branches, evidence, or user files;
- run broad destructive commands such as unscoped `git clean`, `git reset --hard`, or recursive deletion;
- commit credentials, cookies, sessions, tokens, Drive identifiers, licensed datasets, raw private conversations, or runtime market evidence;
- claim real backtest readiness, forecast accuracy, probability, recommendation, or `LIVE_OPERATIONAL` status without the required gates and evidence.

## Completion behavior

Continue through edit, test, inspect, fix, and rerun cycles until one of these applies:

- every acceptance gate for `CURRENT_TASK.md` passes;
- an external dependency is genuinely unavailable;
- the task would require credentials, licensed data, destructive action, or a user decision.

When blocked, do not fabricate or silently weaken a gate. Record the blocker, exact evidence, the smallest recovery action, and any decision required in `docs/codex/USER_DECISIONS.md` and the handoff report.

## Drive control center

A private Google Drive folder named `KU-BO Codex Control` contains the user-facing command archive and private conversation area. The repository copy is sufficient to start work if Drive is not connected. Raw conversations remain private on Drive; only sanitized technical summaries may enter GitHub under the policy in `docs/codex/CONVERSATION_IMPORT_POLICY.md`.
