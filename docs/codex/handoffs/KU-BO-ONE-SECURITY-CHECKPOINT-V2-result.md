# KU-BO-ONE-SECURITY-CHECKPOINT-V2 — One-security checkpoint v2

```text
FINAL_STATUS: PARTIAL
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: 8860989f6a2affdc66bc790f639757c9a897f353
TASK_BRANCH: codex/one-security-checkpoint-v2
FINAL_SHA: PENDING_EXACT_HEAD
DRAFT_PR: #26
PR_BASE: main
CI_RUN: PENDING_EXACT_HEAD
STARTED_AT: 2026-08-27
COMPLETED_AT: PENDING
```

## User goal

Continue the validated Mobile Codex delegation after Day One: audit and merge only the exact authorized Day One head, leave migration PR #21 unmerged, then build a bounded one-security checkpoint with 29 terminal source receipts in seven waves, durable compare-and-swap generations, reconciliation, and a terminal seal. Continue only while gates and runtime authority permit.

## Verified starting state

- Day One Draft PR #25 exact head `a9879b5c9a2eb63c553a3ba05035d9a6d05ff7f4` was CLEAN/MERGEABLE with green push and PR matrices and was merged under `KU-BO-MOBILE-CODEX-D01` as main `8860989f6a2affdc66bc790f639757c9a897f353`.
- Post-merge main CI run `33102246889` passed on Python 3.11 through 3.14.
- PR #21 remains OPEN Draft at `459fb45cd162b0acb967fad8d783b5f68ef7424e`; `KU-BO-MIG-D02` remains OPEN and grants no merge authority.
- PRs #2/#3 are `SUPERSEDED`; #17 is `USER_DECISION_REQUIRED`; #18 is `BLOCKED`; #19/#20/#22 are `ALREADY_INTEGRATED` duplicates through PR #23. Historical zero-ahead branch heads are `ALREADY_INTEGRATED`.
- The new task began from exact green main on `codex/one-security-checkpoint-v2`; Draft PR #26 was opened against main.
- Initial PR #26 CI exposed a stale migration-control reference. The reference was restored without reactivating migration or private-source access.

## Changes made

### Synthetic checkpoint v2

- Added a separate append-only checkpoint policy and schemas without altering legacy DATE/PAGE priority checkpoint v1 or issuer-sequential run v1.
- Bound exactly one numeric Kuwait `security_code`, the reopened one-security plan/universe, 29 ordered source slots, and seven waves.
- Added revision/generation/fence/owner/prior-digest CAS, preempt/resume fencing, terminal receipt immutability, manifest/raw byte reopening, exact reconciliation, and a runtime-key HMAC terminal seal.
- Added fail-closed filesystem checks for traversal, symlinks, hard links, root replacement, unmanifested files, and overwrite attempts.

### Runtime storage authority

- Added an HMAC-authenticated, logical-root-only authority contract for one security and the exact `READ_REOPEN`, `CREATE_EXCLUSIVE`, and `APPEND_GENERATION` operations.
- The authority validator never resolves a physical private path or performs a write. Its existence does not approve `KU-BO-CHK-D01`.

### Integration and controls

- Added a read-only policy validator to the canonical CLI and `validate-config`.
- Added focused CI and installed-wheel import/help gates.
- Preserved the historical migration control references while keeping migration inactive and PR #21 unmerged.

## Validation performed

```text
COMMAND_OR_JOB: focused checkpoint/authentication/legacy/schema/release/control suite
RESULT: PASS before independent-review hardening; final rerun pending
DETAIL: 102/102 passed; independent review then found additional required adversarial gaps, which are being fixed before final status.

COMMAND_OR_JOB: compile, Codex control, migration-preparation control, live bootstrap, smoke, Secret Guard, diff
RESULT: PASS before final hardening rerun
DETAIL: All returned PASS; no live collection or private write occurred.

COMMAND_OR_JOB: full unit/adversarial suite
RESULT: PENDING
DETAIL: Must run after the independent security-review fixes.

COMMAND_OR_JOB: installed wheel and exact-head CI
RESULT: PENDING
DETAIL: Must pass on the final exact branch head before this handoff becomes complete.
```

## Evidence and data status

```text
SYNTHETIC_ONLY: generated one-security plan, checkpoint revisions, one retained raw packet, 29 terminal source receipts, reconciliation, and terminal HMAC seal under TemporaryDirectory.
BLOCKED: private runtime checkpoint, official one-security universe, live adapters, external source/runtime trust and entitlements, physical durable store, and live evidence collection.
LIVE_DEPENDENT: every real source result and any second-security continuation.
LICENSED_FEED_DEPENDENT: licensed/broker connector attempts.
```

## Claims allowed

- The branch may claim only software-contract and generated-fixture enforcement after final gates pass.
- Content digests provide integrity chaining; only the terminal runtime-key HMAC authenticates its sealed material.
- The policy validator is non-mutating and reports production authorization as false.

## Claims still forbidden

Real backtest readiness, forecast accuracy, probability, recommendation, full-market coverage, `LIVE_OPERATIONAL` source status, live collection, private-runtime durability, a real terminal receipt, or financial execution are forbidden.

## Privacy and repository safety

The branch contains no credentials or sessions, private Drive IDs, raw conversations, real runtime market data, licensed data, or destructive cleanup. No force-push, branch deletion, overwrite, access-control bypass, paid activation, or financial execution occurred.

## User decisions required

- `KU-BO-CHK-D01` remains OPEN. No private-runtime or Google Drive checkpoint write is authorized.
- `KU-BO-MIG-D02` remains OPEN. PR #21 remains Draft and unmerged.
- `KU-BO-008-D01` remains OPEN and continues to block a real latest-40 outcome policy.

## Items classified for retention

```text
KEEP: merged Day One source-quality repair and control handoff.
KEEP: checkpoint-v2 policy, schemas, canonical module, tests, CLI validator, and CI gates after final review.
KEEP: PR #17 unique bootstrap archive work pending user decision.
KEEP: PR #18 unique disclosure-domain work pending repair and authority.
SUPERSEDE: PR #2 and PR #3.
SUPERSEDE: patch-duplicated PR #19, PR #20, and PR #22, whose useful capabilities are already integrated through PR #23.
PRIVATE_ONLY: any future private runtime grant, checkpoint bytes, source evidence, connector locators, and HMAC keys.
```

No item is classified `DELETE_CANDIDATE`.

## Known limitations and risks

- The synthetic filesystem store is not connected to a physical authorized private store. External evidence bytes do not share an immutable snapshot/fence with checkpoint publication; production needs a content-addressed durable generation or common store transaction.
- No official point-in-time one-security universe, live adapter set, external trust/entitlement registry, or physical durable store is admitted.
- A terminal synthetic seal explicitly authorizes neither production nor a second security.

## Smallest logical next task

```text
TASK_ID: KU-BO-ONE-SECURITY-RUNTIME-ADMISSION-001
PROPOSED_BRANCH: codex/one-security-runtime-admission-001
DEPENDENCY: checkpoint-v2 Draft PR #26 validated; KU-BO-CHK-D01 explicitly decided; official one-security universe, live adapters, authenticated trust/entitlements, and physical durable store admitted
GOAL: Validate one exact external runtime grant and one immutable physical store generation, then execute and seal exactly one real security without starting a second.
ENTRY_GATE: explicit owner authorization for the exact logical root and operations plus all external runtime prerequisites
EXIT_GATE: 29 reopened terminal receipts in seven waves, exact reconciliation, authenticated terminal seal, independent reopen, no second security, and exact-head green CI
```
