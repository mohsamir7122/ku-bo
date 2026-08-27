# CURRENT TASK — KU-BO-ONE-SECURITY-CHECKPOINT-V2

```text
TASK_ID: KU-BO-ONE-SECURITY-CHECKPOINT-V2
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: 8860989f6a2affdc66bc790f639757c9a897f353
EXPECTED_NEW_BRANCH: codex/one-security-checkpoint-v2
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
PRIVATE_RUNTIME_DATA_ACCESS_ALLOWED: NO
PRIVATE_RUNTIME_CHECKPOINT_WRITE_ALLOWED: NO
GOOGLE_DRIVE_RUNTIME_ACCESS: NO
LIVE_SOURCE_ACCESS_ALLOWED: NO
FINANCIAL_EXECUTION_ALLOWED: NO
BLOCKED_ON: EXPLICIT_PRIVATE_RUNTIME_WRITE_AUTHORITY_MISSING; ADMITTED_OFFICIAL_ONE_SECURITY_UNIVERSE_MISSING; LIVE_ADAPTER_REGISTRY_MISSING; RUNTIME_TRUST_AND_ENTITLEMENTS_MISSING; PHYSICAL_DURABLE_STORE_NOT_CONFIGURED
CONTROL_FILES: docs/codex/HANDOFF_TEMPLATE.md; docs/codex/USER_DECISIONS.md
DEPENDENCY: merged PR #25 at main 8860989f6a2affdc66bc790f639757c9a897f353; post-merge CI 33102246889 PASS
MIGRATION_EXCLUSION: KU-BO-MIG-D02 remains OPEN; PR #21 remains Draft and unmerged
```

## Mission

Implement and test a separate security-aware checkpoint v2 for exactly one
official numeric Kuwait `security_code`. The software must persist the frozen
29-source/seven-wave sequence, reopen retained manifests and raw bytes,
reconcile the exact denominator, and authenticate a terminal seal. This task is
synthetic-only because private-runtime writes and live source access are not
authorized.

The v2 contract extends the canonical `kubo` engine without changing the
serialized legacy DATE/PAGE priority-checkpoint v1 contract or existing
issuer-sequential run v1 behavior.

## Runtime boundary

No private-runtime or Google Drive write is authorized. Tests may use generated
fixtures under temporary directories only. The repository may contain schemas,
code, generated fixtures, and sanitized aggregate conclusions, never physical
private paths, folder/file identifiers, HMAC keys, connector locators, raw
private evidence, or licensed bytes.

`KU-BO-CHK-D01` is OPEN. A real checkpoint remains blocked until the owner
explicitly approves its exact logical root and operations and a separately
authenticated runtime grant, physical durable store, admitted universe, adapter
registry, source authorities, and entitlements exist.

## Required behavior

1. Reopen the exact sequential plan and issuer-universe binding.
2. Reject any execution selection other than exactly one numeric security.
3. Freeze exactly 29 ordered sources in seven waves and begin only the next
   expected source ordinal.
4. Persist every mutation through generation, revision, fencing token, owner,
   and prior-checkpoint-digest compare-and-swap.
5. Resume only a preempted/incomplete generated fixture, increment generation,
   and preserve every terminal source receipt immutably.
6. Continue after source-local blocks until all 29 terminal receipts exist.
7. Reopen each retained generated manifest and every referenced raw fixture
   before counting it.
8. Build reconciliation only after all 29 receipts and all seven waves reconcile.
9. Create an HMAC-SHA256 terminal seal from test-only injected key bytes and
   reopen the full generated bundle before validation.
10. Reject any second security until the prior terminal seal authenticates.

## Acceptance gates

1. The separate v2 contract leaves priority checkpoint v1 and issuer sequential
   run v1 byte-compatible.
2. Exactly one numeric `security_code`, 29 sources, seven waves, and one active
   source are enforced.
3. Crash/resume preserves terminal work and rejects stale generation, fence,
   owner, revision, and prior digest.
4. Skipped, duplicate, reordered, substituted, cross-security, and wrong-wave
   receipts fail closed.
5. Traversal, symlink, hard-link, root-swap, manifest mutation, raw mutation,
   unlisted bytes, and overwrite attempts fail closed.
6. Reconciliation at 28 receipts, early sealing, altered reconciliation,
   missing/wrong HMAC key, and post-seal mutation fail closed.
7. A generated one-security fixture reaches one terminal seal with exactly 29
   terminal receipts across seven waves and reopens successfully.
8. Smoke, full unit/adversarial, control, bootstrap, configuration, schema,
   diff, installed-wheel, and Secret Guard gates pass.
9. A Draft PR is opened and exact-head CI is green. Do not merge this task.

## Safety and non-claims

- Do not merge, force-push, delete, overwrite, weaken gates, expose secrets,
  bypass access controls, activate paid/licensed access, or perform financial
  execution.
- A generated sealed fixture proves checkpoint software only, not durable
  production operation, live access, real evidence, full-market coverage,
  forecast accuracy, probability, recommendation quality, or execution readiness.
- PR #21 remains `USER_DECISION_REQUIRED` and unmerged while
  `KU-BO-MIG-D02` is open.
- Record the missing private-runtime write authority as a genuine blocker; do
  not infer it from silence or this software task.

Use `docs/codex/HANDOFF_TEMPLATE.md` and
`docs/codex/USER_DECISIONS.md`. Do not merge.
