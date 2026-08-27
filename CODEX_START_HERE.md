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
7. only when `CURRENT_TASK.md` explicitly activates `KU-BO-MIG-001`, read
   `docs/codex/PRIVATE_PREDECESSOR_MIGRATION_EXECPLAN.md`,
   `docs/codex/migrations/private-predecessor-to-ku-bo/STATUS.md`, and
   `docs/codex/migrations/private-predecessor-to-ku-bo/PRIVATE_SOURCE_ORIENTATION.md`,
   then run `python scripts/validate_private_predecessor_migration_control.py --project-root . --json`; otherwise skip this historical migration block
8. `docs/PROJECT_CONVERSATION_SYNTHESIS_AR.md`
9. `docs/FACTOR9_DRIVE_ADMISSION_AR.md`
10. `docs/CODEX_LIVE_HANDOFF_AR.md`
11. `docs/codex/ACCEPTANCE_GATES.md`
12. `docs/codex/CONVERSATION_IMPORT_POLICY.md`
13. `docs/codex/USER_DECISIONS.md`

Do not edit code before the bootstrap passes and the remote, base branch, current
HEAD, open PR dependency chain, and current CI state have been verified.

## Operating context

Repository:

```text
mohsamir7122/ku-bo
```

Current task branch:

```text
codex/kuwait-market-ai-day1-v1
```

The last validated implementation head before this mobile-control handoff is
`d31911940ab9970d4409189f58db1d75b85be5b3`; always verify it, the remote,
the later control head, `main`, every PR/branch, and CI live before acting. The
mobile-control commit requires its own fresh exact-head CI before any merge. Do
not create a duplicate branch or assume that every unmerged historical branch
contains unique work.

## Active task meaning

- Complete the current Day-One task and reconcile the repository before opening
  a later real-security task.
- Audit `main`, every remote branch, and every PR. Preserve unique work, but mark
  already integrated or superseded branches truthfully instead of blindly merging.
- The security queue uses official numeric `security_code`, one active security,
  29 source attempts in seven waves, and a terminal security seal before the next
  security starts.
- KU-BO remains the single canonical package, engine, CLI, evidence model, and
  decision boundary.
- Private-predecessor controls remain historical/supplemental unless
  `CURRENT_TASK.md` explicitly activates `KU-BO-MIG-001` again.

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

Codex may merge only under an approved decision such as
`KU-BO-MOBILE-CODEX-D01`, and only after the exact candidate head passes every
applicable gate and a final dependency/mergeability review. It may not enable
auto-merge; force-push; rewrite shared history; delete branches, tags, evidence,
conversations, or user files; commit credentials, Drive identifiers, raw private
conversations, licensed/private datasets, freezes, or daily market evidence; or
claim backtest readiness, accuracy, probability, recommendation, or
`LIVE_OPERATIONAL` status without the applicable gates.

## Completion behavior

Continue through inspect, edit, test, fix, rerun, package, and Draft PR publication
until every active acceptance gate passes or a genuine external dependency is
recorded. Never fabricate evidence or weaken a gate. Use
`docs/codex/HANDOFF_TEMPLATE.md` for the result and propose the smallest next task.

## Home activation prompt

The user can start the next Codex session with:

```text
Open `mohsamir7122/ku-bo`, fetch without force, and read `AGENTS.md`,
`CODEX_START_HERE.md`, and `docs/codex/CURRENT_TASK.md` in the required order.
Begin with a read-only audit of `main`, every remote branch, every PR, exact SHAs,
dependencies, mergeability, and CI. Use `KU-BO-MOBILE-CODEX-D01`: preserve and
repair unique useful work, run targeted and full tests plus exact-head CI, and
merge only validated non-duplicated heads in dependency order. Never blindly
merge a stale branch. Then create the next bounded task from exact merged `main`
and continue the security-by-security mission with durable private checkpoints
and terminal receipts. Never force-push, delete, weaken gates, publish private or
licensed data, bypass access controls, fabricate evidence, or perform financial
execution.
```
