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

```text
DECISION_ID: KU-BO-2026-08-26-MERGE-COND-001
STATUS: APPROVED
DATE_RAISED: 2026-08-26
TARGET: Kuwait integration of PRs #19, #20, #21, and #22, followed by later gated engineering merges
CATEGORY: MERGE
CURRENT_STATE: The owner has authorized Codex to merge engineering changes without asking again, but only after every merge gate in the master Kuwait/Saudi execution contract passes on the exact head SHA.
WHY_A_DECISION_IS_REQUIRED: Repository-local controls require the merge authority and its limits to be recorded before the first merge.
OPTIONS:
1. Permit conditional merge after all section-8 gates pass on the exact head SHA.
2. Require a new owner confirmation for every otherwise-gated engineering merge.
3. Permit unconditional merge.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: Codex may merge only the validated exact head after provenance, diff, tests, dry-run, CI, privacy/licensing, rollback, changelog, decision, and status gates pass.
CONSEQUENCE_OF_REJECTION: Validated work remains in a branch/Draft PR until a later decision.
SAFER_REVERSIBLE_ALTERNATIVE: Keep every change unmerged and publish receipts only.
USER_DECISION: APPROVED by the active master execution contract.
DECIDED_AT: 2026-08-26
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: This authority is conditional, not absolute. It excludes force-push, protected-history rewrite, deletion, secret disclosure, paid access, private/licensed publication, trading or money movement, credential-scope expansion, and gate weakening. No merge has occurred under this record yet.
IMPLEMENTED_IN_BRANCH_OR_PR: PR #23 exact head 3fc478f4b656c80e4951e70410884efebb2bd09e; merged to main as 0f64d322ad7f1d089c05fbd75ad6b7020986d91c on 2026-08-26
```

## Current approved mobile delegation

```text
DECISION_ID: KU-BO-MOBILE-CODEX-D01
STATUS: APPROVED
DATE_RAISED: 2026-08-27
TARGET: Codex CLI repository consolidation and resumable security-by-security continuation
CATEGORY: SCOPE; MERGE; OTHER
CURRENT_STATE: The exact task head d31911940ab9970d4409189f58db1d75b85be5b3 passed CI, but it is not merged into main; repository controls are partly stale; real collection remains unadmitted and the security-aware durable checkpoint v2 remains absent.
WHY_A_DECISION_IS_REQUIRED: The owner wants ChatGPT to perform only the minimum handoff and wants Codex CLI on the phone to own the remaining branch audit, repairs, conditional merges, checkpoints, and project continuation.
OPTIONS:
1. Delegate the work to Codex CLI with exact-head gates and bounded conditional merge authority.
2. Keep every branch unmerged and require ChatGPT to supervise each step.
3. Permit unconditional merging and unrestricted runtime actions.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: Codex CLI may inspect all repository refs and PRs, preserve unique work, repair useful branches, run all gates, and merge only validated non-duplicated exact heads in dependency order. It may then create the next bounded task and continue security-by-security work with private runtime checkpoints.
CONSEQUENCE_OF_REJECTION: Work remains on task branches and the mobile Codex continuation cannot cross a merge boundary.
SAFER_REVERSIBLE_ALTERNATIVE: Publish repaired Draft PRs and handoffs without merging.
USER_DECISION: APPROVED by the active instruction to minimize work in ChatGPT and make Codex CLI perform the remaining GitHub repair, gated merging, and project continuation.
DECIDED_AT: 2026-08-27
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: This is conditional authority, not blanket merge authority. It never overrides a narrower OPEN/REJECTED/DEFERRED decision or an applicable task-specific no-merge gate. `KU-BO-MIG-001` remains USER_DECISION_REQUIRED and unmerged while `KU-BO-MIG-D02` is OPEN and Gate 12 requires a Draft PR plus MERGE_NOT_PERFORMED. Never merge obsolete, duplicated, failing, unaudited, or incorrectly based work. No force-push, protected-history rewrite, deletion, secret disclosure, credential export, access-control bypass, paid/licensed activation, private-data publication, gate weakening, automatic scheduler activation, unadmitted training, real-money action, or buy/sell recommendation is authorized. Stop and record a blocker when a required entitlement, credential, destructive action, or material policy choice is missing.
IMPLEMENTED_IN_BRANCH_OR_PR: Exercised only for PR #25 exact head a9879b5c9a2eb63c553a3ba05035d9a6d05ff7f4; merged to main as 8860989f6a2affdc66bc790f639757c9a897f353; post-merge CI 33102246889 PASS.
```

## Open one-security checkpoint authority decision

```text
DECISION_ID: KU-BO-CHK-D01
STATUS: OPEN
DATE_RAISED: 2026-08-27
TARGET: Any private-runtime checkpoint write under logical AI Rebuild/04_Curated_Core/KU_BO
CATEGORY: PRIVATE_RUNTIME_WRITE; SCOPE; OTHER
CURRENT_STATE: Day One PR #25 is merged at main 8860989f6a2affdc66bc790f639757c9a897f353 with green post-merge CI. Checkpoint-v2 software may be tested only with generated temporary fixtures; private-runtime and Google Drive writes remain prohibited.
WHY_A_DECISION_IS_REQUIRED: The previous task explicitly prohibited private-runtime writes and required a later explicit decision before creating any private checkpoint or artifact. The permission reviewer did not accept the current instruction as that authorization.
OPTIONS:
1. Explicitly authorize CREATE_EXCLUSIVE, READ_REOPEN, and APPEND_GENERATION for exactly one bound security under the canonical logical private root.
2. Keep checkpoint work synthetic and prohibit every private-runtime write.
3. Authorize broad Drive/source writes or overwrites.
CODEX_RECOMMENDATION: Option 1 only after the owner explicitly approves the exact logical root and three operations; until then enforce Option 2.
CONSEQUENCE_OF_APPROVAL: A later task may validate a separately authenticated runtime grant and create versioned one-security checkpoint, reconciliation, and terminal-seal artifacts.
CONSEQUENCE_OF_REJECTION: Software remains testable with generated temporary fixtures, but no real durable checkpoint may be created.
SAFER_REVERSIBLE_ALTERNATIVE: Complete and test the software contract using temporary generated fixtures while leaving production BLOCKED_CHECKPOINT_STORE.
USER_DECISION:
DECIDED_AT:
DECIDED_BY:
IMPLEMENTATION_GUARD: No private-runtime or Google Drive write is authorized while this decision is OPEN. No physical private path, folder/file identifier, HMAC key, connector locator, raw private byte, or licensed byte may enter Git. No overwrite, deletion, source access, access-control bypass, entitlement activation, paid action, training, backtest, recommendation, or financial execution.
IMPLEMENTED_IN_BRANCH_OR_PR: NOT AUTHORIZED
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
DECISION_ID: KU-BO-013-D01
STATUS: APPROVED
DATE_RAISED: 2026-08-14
TARGET: KU-BO-013 historical knowledge planning layer
CATEGORY: SCOPE; DEVELOPMENT; DATA_SOURCE
CURRENT_STATE: The user requested code and ready source definitions for six Kuwait historical research layers, while explicitly stating that the giant collection itself is not the present coding task.
WHY_A_DECISION_IS_REQUIRED: The requested scope expands beyond KU-BO-012's 120-day market context into annual national, commercial, company, media, and legal history.
OPTIONS:
1. Implement planning contracts, source registry, schemas, tests, and documentation without executing the collection.
2. Attempt to scrape and commit the full corpus now.
3. Defer the historical layer.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: Codex may implement and publish a Draft PR for the bounded planning foundation while all live collection, completeness, privacy, rights, and decision gates remain closed.
CONSEQUENCE_OF_REJECTION: No historical planning layer is added.
SAFER_REVERSIBLE_ALTERNATIVE: Documentation-only source list.
USER_DECISION: APPROVED by the active instruction to program the layers, understand their requirements, and gather ready internet sources without performing the full collection now.
DECIDED_AT: 2026-08-14
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: No corpus scrape, private data, access-control bypass, copyrighted bulk republication, completeness claim, guilt inference, model training, forecast, recommendation, or merge of KU-BO-013. Publish as Draft until a later explicit merge decision.
IMPLEMENTED_IN_BRANCH_OR_PR: COMPLETED DEVELOPMENT — PR #15 / agent/kuwait-historical-knowledge-layer / exact implementation head 27dedec792b7f057a975131562898a325fa372a1 / CI run 31785060069 PASS. Merge authority is recorded separately in KU-BO-MERGE-005.
```

```text
DECISION_ID: KU-BO-MERGE-005
STATUS: APPROVED
DATE_RAISED: 2026-08-14
TARGET: PR #15 / KU-BO-013 on agent/kuwait-historical-knowledge-layer
CATEGORY: MERGE
CURRENT_STATE: PR #15 is a clean, mergeable Draft against main at bafdda86b44b7603fe4adfa62dcc2a49bff8ae15. Its exact implementation head 27dedec792b7f057a975131562898a325fa372a1 passed CI run 31785060069 on Python 3.11 through 3.14. Local validation passed 2,082 tests plus compile, smoke, strict JSON/Schema, config/CLI, diff, control, Secret Guard, wheel build, isolated wheel install, and the installed historical-knowledge CLI. The branch programs planning contracts and source definitions only: 26 sources remain DEFINED_ONLY, 756 annual tasks remain NOT_COLLECTED, and no live corpus or company universe is claimed.
WHY_A_DECISION_IS_REQUIRED: Repository rules require explicit user authority before merging KU-BO-013. Recording this authority creates a later documentation-only head that must receive fresh exact-head CI before the merge boundary.
OPTIONS:
1. Record the approval, run fresh exact-head CI on the authorization head, mark PR #15 ready, and merge only that exact head if all gates remain green.
2. Leave PR #15 open as a Draft without merging.
3. Merge without fresh CI or weaken the historical evidence and claim boundaries.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: The tested KU-BO-013 planning foundation may enter main while every live-collection, rights, completeness, legal, forecasting, recommendation, and production gate remains fail-closed.
CONSEQUENCE_OF_REJECTION: The implementation remains available only in Draft PR #15.
SAFER_REVERSIBLE_ALTERNATIVE: Keep PR #15 as a validated Draft.
USER_DECISION: APPROVED in the active user session through the explicit instruction to run the necessary tests, verify the updates, and then perform the merge.
DECIDED_AT: 2026-08-14
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: No force-push, deletion, credentials, private or licensed data publication, corpus-completeness claim, guilt inference, gate weakening, model training, forecast, probability, accuracy, recommendation, or production execution. Merge only PR #15 after the later authorization head passes exact-head CI and a final mergeability review.
IMPLEMENTED_IN_BRANCH_OR_PR: PENDING — authorization recorded on the PR #15 branch; exact-head CI and merge-boundary execution remain required.
```

```text
DECISION_ID: KU-BO-MERGE-004
STATUS: APPROVED
DATE_RAISED: 2026-08-13
TARGET: KU-BO-012 on agent/kuwait-120d-next-session
CATEGORY: DEVELOPMENT; HISTORICAL_EVALUATION; MERGE
CURRENT_STATE: The user requested implementation of the multi-source Kuwait research expansion, verification that all relevant branches are integrated, a retrospective test over the latest forty days, and the resulting agreement percentage. Main is 92b2bdd2460a7508922297a12d85f13264d43acb. PR #1 and PRs #4 through #13 are already ancestors of main. PR #2 and PR #3 are stale, non-mergeable, 127 commits behind, and superseded; they are excluded from literal merge. The task branch contains the bounded fair source search, persisted-run validator, parsed-input integration bridge, content-bound/fresh factor snapshot, execution-grade score-derived replay, and CLI stop result. The latest-40 result remains STOP_BACKTEST with 0/40 scoreable sessions and agreement N/A. Local acceptance passed again on 2026-08-14: final current-tree suite 2,067/2,067, compile/control/smoke/secret/corpus gates. Exact-head GitHub Actions Run 31735588444 passed at d4759f7840625534ba0f5b91338f1b9c46810a93 on Python 3.11 through 3.14. The user then explicitly ordered the merge and preparation of the project for the next historical-research layer. The merge boundary is therefore approved at this exact validated head.
WHY_A_DECISION_IS_REQUIRED: Repository rules require explicit authority for merging and for any historical evaluation that could be misconstrued as a performance claim.
CODEX_RECOMMENDATION: Implement on a fresh branch, preserve all evidence and stop gates, run a 40-completed-session historical walk-forward only if point-in-time data are admissible, publish a Draft PR, require exact-head CI, then merge the new task branch only if every gate passes. Do not merge PR #2 or PR #3 wholesale.
CONSEQUENCE_OF_APPROVAL: Codex may develop and test the research/evaluation infrastructure and may calculate a descriptive agreement rate only from a fully reconciled real-evidence run. Missing evidence must produce STOP_BACKTEST with withheld metrics rather than an invented percentage; KU-BO-012 does not expose an unreachable STOP_INFERENCE status.
CONSEQUENCE_OF_REJECTION: The current main remains unchanged and no historical outcome is calculated.
SAFER_REVERSIBLE_ALTERNATIVE: Keep the implementation and evidence report in a Draft PR without merging.
USER_DECISION: APPROVED and reconfirmed in the active user session with the explicit instruction to perform the merge, prepare the project for operation, and then build the next historical-research layer. This approval applies to exact validated PR #14 head d4759f7840625534ba0f5b91338f1b9c46810a93.
DECIDED_AT: 2026-08-14
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: No force-push, deletion, credentials, private or licensed data publication, gate weakening, model training, or fabricated accuracy. The merge approval applies only to the new KU-BO-012 branch after complete tests and exact-head CI. PR #2 and PR #3 remain excluded as stale/superseded.
IMPLEMENTED_IN_BRANCH_OR_PR: COMPLETED — PR #14 exact head 73dc3daa994ffd4d41317cf486820264227a85f2 passed CI run 31782243633 and merged to main as bafdda86b44b7603fe4adfa62dcc2a49bff8ae15 on 2026-08-14.
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

```text
DECISION_ID: KU-BO-MERGE-006
STATUS: APPROVED
DATE_RAISED: 2026-08-14
TARGET: PR #16 / Harden PR #15 historical evidence gates
CATEGORY: MERGE
CURRENT_STATE: PR #16 is a clean, mergeable Draft against main at 32e048b234c73809b6f5119ae16937980184296c. Its implementation head 194922f9f5bf13a9332ea1f3d7cc4ae9d9307140 passed GitHub Actions on Python 3.11 through 3.14 and the complete 2,086-test suite. This authorization record creates a later documentation-only head that requires fresh exact-head CI before merge.
WHY_A_DECISION_IS_REQUIRED: Repository rules require explicit user authority recorded in this queue before merging.
OPTIONS:
1. Record approval, run fresh exact-head CI, mark PR #16 ready, and merge only that validated head.
2. Leave PR #16 open as a Draft.
3. Merge without fresh CI or weaken evidence gates.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: The four historical evidence-gate fixes may enter main while live collection, completeness, forecasting, recommendation, and execution gates remain fail-closed.
CONSEQUENCE_OF_REJECTION: The fixes remain available only in Draft PR #16.
SAFER_REVERSIBLE_ALTERNATIVE: Keep PR #16 as a validated Draft.
USER_DECISION: APPROVED in the active user session through the explicit instruction to perform the merge, verify the initial Kuwait-screening steps, run the checks, and send the results by Gmail.
DECIDED_AT: 2026-08-14
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: Merge only PR #16 after its authorization head passes exact-head CI and a final mergeability check. No force-push, deletion, credential use, private or licensed-data publication, corpus-completeness claim, gate weakening, forecast, probability, recommendation, or production execution.
IMPLEMENTED_IN_BRANCH_OR_PR: PENDING — authorization recorded on PR #16 branch; exact-head CI and merge-boundary execution remain required.
```

```text
DECISION_ID: KU-BO-016-D01
STATUS: APPROVED
DATE_RAISED: 2026-08-24
TARGET: Codex live bootstrap, private AI Rebuild inventory, Factor 9 admission preparation, and previous-session freeze policy
CATEGORY: SCOPE
CURRENT_STATE: The user directed KU-BO to be prepared for a later Codex session, authorized private use of the existing AI Rebuild folder and relevant stock-market material, prioritized continuous development and daily work, and required each day to use the prior approved frozen state.
WHY_A_DECISION_IS_REQUIRED: The task crosses repository control, private Drive inspection, future daily scheduling, model-development policy, and financial-research boundaries. The authority and its limits must survive outside the active conversation.
OPTIONS:
1. Build the fail-closed Codex handoff and private inventory/admission path first, then progress through dry-run, data admission, training, locked test, and prospective gates.
2. Begin training and daily stock calls immediately from unadmitted Drive material.
3. Copy the private Drive corpus and raw conversations into GitHub for convenience.
CODEX_RECOMMENDATION: Option 1.
CONSEQUENCE_OF_APPROVAL: Codex may inspect the authorized AI Rebuild tree privately, create logical folders and private manifests, preserve and assess Factor 9, implement contract-only daily/freeze infrastructure, and propose tested changes in Draft PRs. Training and stock outputs remain blocked until their gates pass.
CONSEQUENCE_OF_REJECTION: The repository remains a static research foundation without the new Codex handoff or private data-admission workflow.
SAFER_REVERSIBLE_ALTERNATIVE: Keep scheduling disabled and run only manual contract dry-runs while inventories and rights are reviewed.
USER_DECISION: APPROVED through the active instruction to review the project conversations and Factor 9 evidence, prepare the repository for Codex, use AI Rebuild as the private data repository, collect relevant material privately, prioritize development, and enforce daily freezing from the prior approved state.
DECIDED_AT: 2026-08-24
DECIDED_BY: Mohamed Samir Rashed Shaheen
IMPLEMENTATION_GUARD: No merge, force-push, deletion, paid subscription change, access-control bypass, private-data publication, automatic scheduler enablement, model training on unadmitted data, locked-test tuning, live execution, or buy/sell recommendation is authorized. Drive IDs and raw private bytes remain outside Git. Every code change uses a task branch, tests, and a Draft PR; every model promotion requires locked and prospective gates.
IMPLEMENTED_IN_BRANCH_OR_PR: agent/ku-bo-016-codex-live-bootstrap / Draft PR #20 / published implementation head 7f32b7f9e8e71a55977cf834785e53adf7df086d
```

```text
DECISION_ID: KU-BO-MIG-D01
STATUS: APPROVED
DATE_RAISED: 2026-08-25
TARGET: Complete private-predecessor capability migration into KU-BO on one task branch and Draft PR
CATEGORY: SCOPE; DEVELOPMENT; NARROW_PRIVATE_SOURCE_READ
CURRENT_STATE: KU-BO is the canonical public target. The predecessor source is private and has not been exhaustively inventoried or reimplemented in KU-BO.
WHY_A_DECISION_IS_REQUIRED: The task requires read-only cross-repository inspection, a private census, safe reimplementation, Skill integration, and behavioral parity while preventing private-source metadata from entering public history.
OPTIONS:
1. Execute one capability-migration Draft PR with a private runtime census and privacy-safe public controls.
2. Continue the deferred dry-run task first.
3. Blindly merge files or Git histories.
CODEX_RECOMMENDATION: Option 1 with KU-BO canonical, exhaustive private inventory before broad porting, semantic/negative tests, and evidence-verifying completion gates.
CONSEQUENCE_OF_APPROVAL: Codex may read the configured private source repository code and Git metadata, privately inventory its refs/items/user jobs, reimplement safe capabilities on KU-BO core, add thin Skills and tests, and maintain one Draft PR.
CONSEQUENCE_OF_REJECTION: KU-BO remains on the prior dry-run roadmap and the private predecessor remains separate.
SAFER_REVERSIBLE_ALTERNATIVE: Private read-only inventory without implementation or public metadata.
USER_DECISION: APPROVED by the active user instruction to prepare KU-BO so Codex can begin the complete migration from home.
DECIDED_AT: 2026-08-25
DECIDED_BY: Active repository owner via current ChatGPT instruction
IMPLEMENTATION_GUARD: The read grant is limited to repository code and Git metadata through the normal authorized connector. Exact repository/ref/commit/tree locators, counts, sensitive paths/findings, and reversible opaque mappings remain uncommitted private runtime data. No unrelated private access, credential export, source write/history merge, main write, PR merge/auto-merge, force-push, deletion/archive, paid/licensed activation, training, real backtest, live promotion, recommendation, or execution.
IMPLEMENTED_IN_BRANCH_OR_PR: agent/private-predecessor-capability-migration-v1 / Draft PR #21 / initial published implementation head 435d28503a60ae9316909304537f7c42e937d066 / preparation only; no migration or merge performed
```

```text
DECISION_ID: KU-BO-MIG-D02
STATUS: OPEN
DATE_RAISED: 2026-08-25
TARGET: Final merge of KU-BO-MIG-001 into its dependency chain and ultimately main
CATEGORY: MERGE
CURRENT_STATE: Only a preparation control exists. No verified private census, complete denominator, implementation, dedicated completion receipt, or migration-branch exact-head CI exists.
WHY_A_DECISION_IS_REQUIRED: Development and narrow source-read authority do not imply merge authority.
OPTIONS:
1. After dedicated completion validation and review, authorize a separate dependency-order merge.
2. Keep the completed migration as a Draft PR.
3. Merge early or bypass evidence gates.
CODEX_RECOMMENDATION: Option 2 until a verified sanitized handoff exists, then raise a fresh bounded merge review.
CONSEQUENCE_OF_APPROVAL: No consequence now; this OPEN entry grants no merge authority.
CONSEQUENCE_OF_REJECTION: The migration remains available on its Draft branch.
SAFER_REVERSIBLE_ALTERNATIVE: Keep the Draft PR open without merging.
USER_DECISION:
DECIDED_AT:
DECIDED_BY:
IMPLEMENTED_IN_BRANCH_OR_PR: NOT AUTHORIZED
```

```text
DECISION_ID: KU-BO-MIG-D03
STATUS: OPEN
DATE_RAISED: 2026-08-25
TARGET: Archive, delete, or write to the configured private predecessor after migration
CATEGORY: ARCHIVE; DELETE; SOURCE_WRITE
CURRENT_STATE: The private predecessor remains an independent historical source. This task permits narrow read-only inspection only.
WHY_A_DECISION_IS_REQUIRED: Migration does not prove preservation or recovery completeness, and source mutation is outside development scope.
OPTIONS:
1. Leave the source unchanged.
2. After a separate preservation audit, archive it read-only.
3. Delete or rewrite it.
CODEX_RECOMMENDATION: Option 1. Revisit archive only after verified migration and a new explicit decision.
CONSEQUENCE_OF_APPROVAL: No consequence now; this OPEN entry grants no archive, delete, or write authority.
CONSEQUENCE_OF_REJECTION: The source remains unchanged.
SAFER_REVERSIBLE_ALTERNATIVE: Retain it as a read-only private reference.
USER_DECISION:
DECIDED_AT:
DECIDED_BY:
IMPLEMENTED_IN_BRANCH_OR_PR: NOT AUTHORIZED
```

## Rules

- Do not convert silence into approval.
- Do not delete a conversation merely because a summary was imported.
- Do not delete a repository file until references and tests have been checked.
- Prefer reversible archive or deprecation before deletion.
- Do not merge stacked PRs out of order.
- If a decision becomes unnecessary because the implementation changed, mark it `DEFERRED` or explain why it was withdrawn; do not erase the history.
