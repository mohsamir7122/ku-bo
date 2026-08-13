# KU-BO User Decision Queue

Codex must not execute a permanent deletion, scope expansion, gate weakening, licensing decision, credential use, paid service action, or merge without an explicit user decision.

## Decision format

Copy this block for every required decision:

```text
DECISION_ID:
STATUS: OPEN | APPROVED | REJECTED | DEFERRED
DATE_RAISED:
TARGET:
CATEGORY: DELETE | ARCHIVE | SCOPE | LICENSING | CREDENTIALS | MERGE | DATA_SOURCE | OTHER
CURRENT_STATE:
WHY_A_DECISION_IS_REQUIRED:
OPTIONS:
1.
2.
3.
CODEX_RECOMMENDATION:
CONSEQUENCE_OF_APPROVAL:
CONSEQUENCE_OF_REJECTION:
SAFER_REVERSIBLE_ALTERNATIVE:
USER_DECISION:
DECIDED_AT:
DECIDED_BY:
IMPLEMENTED_IN_BRANCH_OR_PR:
```

## Open decisions

```text
DECISION_ID: KU-BO-008-D01
STATUS: OPEN
DATE_RAISED: 2026-08-10
TARGET: config/pilot/outcome_session_policy.json
CATEGORY: OTHER
CURRENT_STATE: The product catalog declares horizon_sessions but does not freeze how an outcome window advances through SUSPENDED or HALTED sessions. KU-BO-012 now preserves every non-trading security in the denominator and returns STOP_BACKTEST with OUTCOME_SESSION_POLICY_NOT_FROZEN rather than dropping the row, synthesizing a close, or silently choosing an extension policy.
WHY_A_DECISION_IS_REQUIRED: Different policies materially change outcome timing and measured returns. Civil-day arithmetic is forbidden, and Codex cannot select an investment-evaluation policy merely to make the data-foundation gate pass.
OPTIONS:
1. Advance through the official calendar to the next eligible official session, extending the horizon across suspended or halted sessions.
2. Keep the scheduled official-session horizon and record a non-fill/no-outcome state when the security cannot trade.
3. Freeze a product-specific policy with explicit maximum extension and terminal treatment.
CODEX_RECOMMENDATION: Option 3, using an explicit product-specific maximum extension and fail-closed terminal state; until then keep the shared policy UNFROZEN.
CONSEQUENCE_OF_APPROVAL: The selected policy can be encoded, tested across holidays/suspensions/actions, and the CLAIM_BOUNDARIES gate can be reevaluated.
IMPLEMENTATION_GUARD: Policy schema v1 intentionally rejects every FROZEN value. Merely committing global Option 1 does not approve this decision. Approval requires a later product-specific contract with maximum extension, terminal treatment, and a decision receipt bound to the approved choice.
CONSEQUENCE_OF_REJECTION: Final data-foundation reconciliation remains blocked from baseline-backtest readiness, while benchmark/EOD contracts remain usable for evidence collection.
SAFER_REVERSIBLE_ALTERNATIVE: Preserve the current UNFROZEN template and emit OUTCOME_SESSION_POLICY_NOT_FROZEN without producing outcome dates.
USER_DECISION:
DECIDED_AT:
DECIDED_BY:
IMPLEMENTED_IN_BRANCH_OR_PR: build/benchmark-official-eod-v0.2
```

## Approved decisions

```text
DECISION_ID: KU-BO-MERGE-004
STATUS: APPROVED_CONDITIONAL
DATE_RAISED: 2026-08-13
TARGET: KU-BO-012 on agent/kuwait-120d-next-session
CATEGORY: DEVELOPMENT; HISTORICAL_EVALUATION; MERGE
CURRENT_STATE: The user requested implementation of the multi-source Kuwait research expansion, verification that all relevant branches are integrated, a retrospective test over the latest forty days, and the resulting agreement percentage. Main is 92b2bdd2460a7508922297a12d85f13264d43acb. PR #1 and PRs #4 through #13 are already ancestors of main. PR #2 and PR #3 are stale, non-mergeable, 127 commits behind, and superseded; they are excluded from literal merge. The task branch now contains the bounded fair source search, persisted-run validator, parsed-input integration bridge, content-bound/fresh factor snapshot, execution-grade score-derived replay, and CLI stop result. The latest-40 result remains STOP_BACKTEST with 0/40 scoreable sessions and agreement N/A. Local acceptance passed: targeted 183/183, final current-tree suite 2,067/2,067 in 164.347s, compile/JSON/diff/control/smoke/secret/corpus gates, final wheel, isolated installation, installed CLI, and an installed Data Foundation check with 8 semantic admissions and 8 lineages. Draft PR, remote exact-head CI, merge-boundary review, and merge are still pending.
WHY_A_DECISION_IS_REQUIRED: Repository rules require explicit authority for merging and for any historical evaluation that could be misconstrued as a performance claim.
CODEX_RECOMMENDATION: Implement on a fresh branch, preserve all evidence and stop gates, run a 40-completed-session historical walk-forward only if point-in-time data are admissible, publish a Draft PR, require exact-head CI, then merge the new task branch only if every gate passes. Do not merge PR #2 or PR #3 wholesale.
CONSEQUENCE_OF_APPROVAL: Codex may develop and test the research/evaluation infrastructure and may calculate a descriptive agreement rate only from a fully reconciled real-evidence run. Missing evidence must produce STOP_BACKTEST with withheld metrics rather than an invented percentage; KU-BO-012 does not expose an unreachable STOP_INFERENCE status.
CONSEQUENCE_OF_REJECTION: The current main remains unchanged and no historical outcome is calculated.
SAFER_REVERSIBLE_ALTERNATIVE: Keep the implementation and evidence report in a Draft PR without merging.
USER_DECISION: APPROVED in the active user session with the instruction to add the requested capabilities, verify integration of all branches, run a retrospective test over the latest forty days, and report the agreement percentage.
DECIDED_AT: 2026-08-13
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: No force-push, deletion, credentials, private or licensed data publication, gate weakening, model training, or fabricated accuracy. The merge approval applies only to the new KU-BO-012 branch after complete tests and exact-head CI. PR #2 and PR #3 remain excluded as stale/superseded.
IMPLEMENTED_IN_BRANCH_OR_PR: agent/kuwait-120d-next-session / pending Draft PR
```

```text
DECISION_ID: KU-BO-MERGE-003
STATUS: APPROVED
DATE_RAISED: 2026-08-13
TARGET: PR #12 followed by the KU-BO-011 implementation PR
CATEGORY: MERGE
CURRENT_STATE: The first ordered action is complete. PR #12 merged into main as c621fcf88034c4571aa08aee2e54e2e026a4f651 with its historical TEST_SPEC_ONLY non-claim intact, and post-merge CI run 31684299396 passed. The implementation is published as Draft PR #13 at remote head 6dc821f8342bf2041ac3bed983c6805ff0a2c3fc. Exact-head GitHub Actions run 31695010037 completed successfully, including Python 3.11, 3.12, 3.13, and 3.14. Local validation passed 1,916 tests, strict source-tree and clean-installed-wheel Adapter runs at 1,280/1,280 each, and an installed authenticated eight-boundary DAG with eight semantic admissions and eight lineages. This proves CODE_AND_SYNTHETIC_ADVERSARIAL_ENFORCEMENT / SYNTHETIC_ONLY, not market evidence. KU-BO-011 remains IN_PROGRESS and MERGE_ALLOWED remains NO because this control-record update creates a later head that requires exact-head CI and an ordered merge-boundary recheck.
WHY_A_DECISION_IS_REQUIRED: Repository rules prohibit any merge without an explicit user decision. The Test Spec and implementation must enter main in dependency order, and each changed or retargeted exact head must pass its applicable acceptance and CI gates before merge.
OPTIONS:
1. Update the control records, run fresh CI, merge PR #12 as TEST_SPEC_ONLY, create or retarget the implementation PR to updated main, prove production-path enforcement, rerun exact-head CI, then merge the implementation PR.
2. Merge PR #12 only and leave the implementation as a Draft.
3. Merge both without production-path Adapter proof or fresh post-retarget CI.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: The locked synthetic Test Specification and the separately reviewed runtime implementation may enter main in dependency order while every real-data, rights, outcome-policy, Benchmark, backtest, forecast, probability, accuracy, recommendation, and production gate remains fail-closed.
CONSEQUENCE_OF_REJECTION: PR #12 remains merged as TEST_SPEC_ONLY; the separate implementation remains available only on its task branch and is not merged.
SAFER_REVERSIBLE_ALTERNATIVE: Keep PR #12 and the implementation PR open as Drafts without merging.
USER_DECISION: APPROVED in the active user session with the instruction "قم بعمل التعديل والدمج اللازم" after receiving the repository audit, non-merged-item reasons, and ordered development plan.
DECIDED_AT: 2026-08-13
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: This approval is limited to PR #12 and the KU-BO-011 implementation PR, in that order, after their applicable exact-head gates pass. It does not authorize PR #2, PR #3, force-push, auto-merge, deletion, gate weakening, credentials, real-data publication, a later batch, model training, real backtest, forecast, probability, accuracy, recommendation, or production execution. CURRENT_TASK remains conservatively MERGE_ALLOWED: NO during implementation; the approval is rechecked only at the ordered merge boundary.
IMPLEMENTED_IN_BRANCH_OR_PR: PR #12 merge portion completed at c621fcf88034c4571aa08aee2e54e2e026a4f651. KU-BO-011 implementation is published as Draft PR #13 at 6dc821f8342bf2041ac3bed983c6805ff0a2c3fc with exact-head run 31695010037 PASS; its merge portion remains PENDING until this control-record head passes CI and the ordered merge boundary is rechecked.
```

```text
DECISION_ID: KU-BO-MERGE-002
STATUS: APPROVED
DATE_RAISED: 2026-08-12
TARGET: Stacked PR chain #10 -> #11
CATEGORY: MERGE
CURRENT_STATE: COMPLETED. PR #10 was merged as 2f51c88 and PR #11 was merged as 6bcfbab after the documentation correction and fresh dependency-order validation. Post-merge main CI run 31629909113 passed on Python 3.11 through 3.14. The original reviewed heads were 7d032c98b0ef9f27e913199487ad4577119c2631 and 1a2cfeb390e7e17f029a07f326a75a1bc70d07a6; the audit correction recorded that the installed-wheel checker exercised 16 selected distinct CLI flows, not 17.
WHY_A_DECISION_IS_REQUIRED: Repository rules prohibit any merge without explicit user approval and require stacked PRs to merge in dependency order. The documentation correction and any merge-authority commits must receive fresh exact-head CI before merge.
OPTIONS:
1. Record this approval, correct the CLI-flow count, run fresh CI, merge PR #10 into main, retarget and revalidate PR #11 against main, then merge PR #11.
2. Leave both PRs open as Drafts.
3. Merge PR #11 first or bypass fresh post-retarget CI.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: The two reviewed engineering stages enter main in dependency order while every real-data, Benchmark-scope, outcome-policy, backtest, forecast, and recommendation gate remains fail-closed.
CONSEQUENCE_OF_REJECTION: The validated implementation remains available only on the stacked branches.
SAFER_REVERSIBLE_ALTERNATIVE: Keep both PRs open without merging.
USER_DECISION: APPROVED in the active user session with the instruction to verify the reported result, perform the merge, and prepare at least 1,000 distinct tests for later Codex evaluation.
DECIDED_AT: 2026-08-12
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTED_IN_BRANCH_OR_PR: build/tri-security-pilot-v0.3 / PR #10 and build/tri-security-run-receipt-v0.1 / PR #11
```

```text
DECISION_ID: KU-BO-MERGE-001
STATUS: APPROVED
DATE_RAISED: 2026-08-10
TARGET: Stacked PR chain #4 -> #5 -> #6 -> #7 -> #8 -> #9
CATEGORY: MERGE
CURRENT_STATE: The approved sequence was completed on 2026-08-12: PRs #4 through #9 are merged into main. The older PRs #2 and #3 remain open and stale on pre-stack bases. PR #9 closed KU-BO-008 as a fail-closed contract stage while real Benchmark/EOD evidence and KU-BO-008-D01 remain blocked.
WHY_A_DECISION_IS_REQUIRED: Repository rules prohibit any merge without explicit user approval and require stacked PRs to merge in dependency order.
OPTIONS:
1. Merge sequentially into main, retargeting each successor to main and requiring fresh green CI after every retarget.
2. Leave the complete stack open as Draft.
3. Retarget only PR #9 to main and collapse the whole stack into one oversized review.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: The reviewed engineering foundation enters main while all real-data, licensing, receipt, policy, backtest, forecast, and recommendation gates remain fail-closed.
CONSEQUENCE_OF_REJECTION: The validated implementation remains available only on the stacked branches.
SAFER_REVERSIBLE_ALTERNATIVE: Keep all PRs open and Draft without merging.
USER_DECISION: APPROVED in the active user session after review of the exact staged merge plan.
DECIDED_AT: 2026-08-10
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTED_IN_BRANCH_OR_PR: build/benchmark-official-eod-v0.2 / PR #9
```

## Rules

- Do not convert silence into approval.
- Do not delete a conversation merely because a summary was imported.
- Do not delete a repository file until references and tests have been checked.
- Prefer reversible archive or deprecation before deletion.
- Do not merge stacked PRs out of order.
- If a decision becomes unnecessary because the implementation changed, mark it `DEFERRED` or explain why it was withdrawn; do not erase the history.
