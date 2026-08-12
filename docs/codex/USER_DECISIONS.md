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
CURRENT_STATE: The product catalog declares horizon_sessions but does not freeze how an outcome window advances through SUSPENDED or HALTED sessions.
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
DECISION_ID: KU-BO-MERGE-002
STATUS: APPROVED
DATE_RAISED: 2026-08-12
TARGET: Stacked PR chain #10 -> #11
CATEGORY: MERGE
CURRENT_STATE: PR #10 and PR #11 were inspected at heads 7d032c98b0ef9f27e913199487ad4577119c2631 and 1a2cfeb390e7e17f029a07f326a75a1bc70d07a6. Both stacked Draft PRs were clean and their exact-head Linux CI matrices passed Python 3.11 through 3.14. The audit found one documentation-only discrepancy in PR #11: the installed-wheel checker exercised 16 selected distinct CLI flows, not 17.
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
