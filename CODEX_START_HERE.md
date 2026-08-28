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
4. `config/codex_control_state.json`
5. `docs/codex/PROJECT_RULES.md`
6. `docs/codex/CURRENT_STATUS.md`
7. `docs/codex/CURRENT_TASK.md`
8. only when `CURRENT_TASK.md` explicitly activates `KU-BO-MIG-001`, read
   `docs/codex/PRIVATE_PREDECESSOR_MIGRATION_EXECPLAN.md`,
   `docs/codex/migrations/private-predecessor-to-ku-bo/STATUS.md`, and
   `docs/codex/migrations/private-predecessor-to-ku-bo/PRIVATE_SOURCE_ORIENTATION.md`,
   then run `python scripts/validate_private_predecessor_migration_control.py --project-root . --json`; otherwise skip this historical migration block
9. `docs/PROJECT_CONVERSATION_SYNTHESIS_AR.md`
10. `docs/FACTOR9_DRIVE_ADMISSION_AR.md`
11. `docs/CODEX_LIVE_HANDOFF_AR.md`
12. `docs/codex/ACCEPTANCE_GATES.md`
13. `docs/codex/CONVERSATION_IMPORT_POLICY.md`
14. `docs/codex/USER_DECISIONS.md`

Do not edit code before the bootstrap passes and the remote, base branch, current
HEAD, open PR dependency chain, and current CI state have been verified.

## Operating context

Repository:

```text
mohsamir7122/ku-bo
```

Canonical machine-readable control:

```text
config/codex_control_state.json
```

Current bounded task:

```text
task:        KU-BO-2026-08-28-READINESS-CANARY
base:        main at 8860989f6a2affdc66bc790f639757c9a897f353
work branch: codex/ku-bo-readiness-live-canary-v1
PR mode:     DRAFT
```

PR #25 is already merged. Verify the canonical control against the actual Git
branch, `HEAD`, frozen base ref/SHA, ancestry, remote, open PRs, and CI before
acting. Do not create a duplicate branch or assume that every unmerged historical
branch contains unique work.

## Active task meaning

- Repair repository readiness and prove the bounded checkpoint artifact-journal
  canary path, then attempt at most one manually invoked, fail-closed access
  canary. This does not close Issue #28 without production wiring and cross-run
  persistence evidence.
- Audit `main`, every remote branch, and every PR. Preserve unique work, but mark
  already integrated or superseded branches truthfully instead of blindly merging.
- The security queue uses official numeric `security_code`, one active security,
  29 source attempts in seven waves, and a terminal security seal before the next
  security starts.
- Automatic schedules are not authorized by this task. The manual canary cannot
  create a live, predictive, accuracy, recommendation, or trading claim.
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
`CODEX_START_HERE.md`, `config/codex_control_state.json`, and
`docs/codex/CURRENT_TASK.md` in the required order. Validate the exact branch,
HEAD, frozen base SHA, ancestry, open PRs, and CI. Continue only
`KU-BO-2026-08-28-READINESS-CANARY` on
`codex/ku-bo-readiness-live-canary-v1`: repair readiness, prove only the bounded
checkpoint artifact-journal canary path, keep automatic schedules disabled or
absent, and attempt no more than one manual fail-closed access canary. Keep Issue
#28 open unless production wiring and cross-run persistence are separately
proven. Publish a Draft PR only. Never merge,
force-push, delete, weaken gates, commit real/private/licensed data, claim live or
predictive performance, fabricate evidence, recommend a trade, or perform
financial execution.
```
