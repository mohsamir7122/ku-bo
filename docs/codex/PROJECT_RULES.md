# KU-BO Codex Project Rules

## Authority order

When instructions conflict, use this order:

1. explicit user instruction in the active Codex session;
2. `AGENTS.md`;
3. `docs/codex/CURRENT_TASK.md`;
4. repository contracts, schemas, tests, and claim boundaries;
5. this file;
6. older handoffs, archived prompts, and historical discussion.

Archived or superseded prompts never override the single active task.

## Repository and branch safety

- Work only in `mohsamir7122/ku-bo` unless the user explicitly names another repository.
- Verify the remote, default branch, base branch, HEAD SHA, open PRs, and CI before editing.
- Never modify `main` directly.
- Start a new phase on the exact branch declared in `CURRENT_TASK.md`, after verifying it still exists and is the intended head.
- Keep stacked PR dependencies explicit in every PR body.
- Default every new PR to Draft.
- Never merge, enable auto-merge, force-push, delete tags, or delete historical branches.
- Never hide failures by weakening tests, changing expected values to match bad output, or marking a source operational without evidence.

## Data boundaries

GitHub may contain:

- source code;
- tests and recorded synthetic or authorized contract fixtures;
- JSON Schemas and data contracts;
- documentation and sanitized handoff summaries;
- empty templates and workspace generators.

GitHub must not contain:

- credentials, API keys, cookies, sessions, browser profiles, OAuth files, or signed URLs;
- Drive folder IDs or private connector identifiers;
- licensed or confidential market datasets;
- real runtime evidence that policy says must remain outside Git;
- raw private conversations, personal correspondence, or unrelated personal data;
- documents copied from private Drive merely because Codex can access them.

Local/Drive Runtime may contain official evidence and market files. Storage is not a source of truth: every accepted fact must still bind to its original source, timestamps, rights, and hashes.

## Financial and research claim boundaries

Do not produce or claim any of the following unless the corresponding repository gates explicitly pass on real evidence:

```text
REAL_BACKTEST_READY
PROSPECTIVE_VALIDATED
LIVE_OPERATIONAL
forecast probability
buy or sell recommendation
headline accuracy
full-market coverage
historical point-in-time universe completeness
```

A score is not a probability. A current snapshot is not historical coverage. A mechanical formula is not an official factor. A search result is not evidence. A rendered page shell is not a zero result.

## Work-cycle rules

For each coherent change:

1. inspect the governing contract and nearby tests;
2. implement the smallest complete change;
3. run targeted tests;
4. run the full relevant suite after the coherent unit passes;
5. inspect failures rather than rerunning blindly;
6. fix failures caused by the change;
7. update documentation and claim boundaries;
8. record what remains blocked.

Do not ask the user to approve ordinary implementation choices already governed by the active task. Stop for a user decision only when the choice is destructive, changes project scope, weakens a gate, spends money, uses credentials, changes licensing, publishes private data, or has materially different alternatives.

## Deletion and cleanup rules

Codex may classify an item as:

```text
KEEP
REFACTOR
ARCHIVE
SUPERSEDE
DELETE_CANDIDATE
PRIVATE_ONLY
```

Codex may move a file into a repository archive when the active task explicitly authorizes it and tests prove no live dependency. Codex may not permanently delete repository files, Drive files, branches, conversations, or evidence merely because they appear obsolete.

All permanent deletion proposals go to `docs/codex/USER_DECISIONS.md` with:

- exact target;
- why it appears obsolete;
- references or dependencies checked;
- consequence of deletion;
- safer alternative;
- Codex recommendation;
- user decision field.

## Handoff rules

At task completion, write a result using `docs/codex/HANDOFF_TEMPLATE.md`. The handoff must distinguish:

```text
PROVEN
PARTIAL
BLOCKED
SYNTHETIC_ONLY
RECORDED_FIXTURE_ONLY
LIVE_DEPENDENT
USER_DECISION_REQUIRED
```

Include exact branch, commit, PR, tests, CI, changed files, unresolved risks, and the smallest logical next task. Never describe future work as already completed.
