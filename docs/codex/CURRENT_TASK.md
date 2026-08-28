# CURRENT TASK — KU-BO-2026-08-28-READINESS-CANARY

Canonical machine-readable control:
`config/codex_control_state.json`.

```text
TASK_ID: KU-BO-2026-08-28-READINESS-CANARY
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_STATE_FILE: config/codex_control_state.json
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: 8860989f6a2affdc66bc790f639757c9a897f353
EXPECTED_NEW_BRANCH: codex/ku-bo-readiness-live-canary-v1
EXPECTED_PR_BASE: main
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
AUTOMATIC_SCHEDULES_ALLOWED: NO
MANUAL_CANARY_ALLOWED: YES
FINANCIAL_EXECUTION_ALLOWED: NO
LIVE_OPERATIONAL_CLAIM_ALLOWED: NO
PREDICTIVE_CLAIM_ALLOWED: NO
PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: NO
PRIVATE_RUNTIME_DATA_ACCESS_ALLOWED: NO
GOOGLE_DRIVE_RUNTIME_ACCESS: NO
MIGRATION_CONTROL_REFERENCE: KU-BO-MIG-001
MIGRATION_CONTROL_BRANCH_REFERENCE: agent/private-predecessor-capability-migration-v1
MIGRATION_CONTROL_EXPECTED_PR_BASE: agent/ku-bo-016-codex-live-bootstrap
MIGRATION_FIELDS_APPLICABILITY: HISTORICAL_REFERENCE_ONLY_UNLESS_TASK_ID_IS_KU-BO-MIG-001
BLOCKED_ON: BLOCKED_CHECKPOINT_STORE; ADMITTED_OFFICIAL_POINT_IN_TIME_UNIVERSE_MISSING; SIGNED_ISSUER_DOMAIN_TRUST_REGISTRY_MISSING; ADMITTED_LIVE_ADAPTERS_MISSING; SOURCE_RIGHTS_AND_RUNTIME_AUTHORITY_INCOMPLETE
CONTROL_FILES: docs/codex/HANDOFF_TEMPLATE.md; docs/codex/USER_DECISIONS.md
MERGE_GUARD: Do not merge until the exact candidate head passes every applicable gate and a separate merge boundary is authorized.
```

## Mission

Repair the repository-readiness and control defects observed after PR #25 merged,
harden and prove the bounded `GITHUB_ARTIFACT_JOURNAL` checkpoint canary path, and
attempt one credential-free, access-only canary after its own narrow safety
contract passes. The probe is not admitted market evidence and does not bypass
any production admission gate. This work does not by itself provide a
production-durable store or close Issue #28. `BLOCKED_CHECKPOINT_STORE` remains
until production wiring and cross-run evidence pass a separate review.

This task may prove software behavior and bounded runtime evidence. It may not
activate an automatic schedule, commit real data, train a model, run a real
backtest, claim `LIVE_OPERATIONAL` or predictive performance, issue a financial
recommendation, or execute a trade.

## Required sequence

1. Validate `config/codex_control_state.json`, the exact Git branch, current
   `HEAD`, frozen base branch/SHA, ancestry, and cross-file status before changing
   implementation code.
2. Keep changes on `codex/ku-bo-readiness-live-canary-v1` and publish only a
   Draft PR against `main`. Do not merge, force-push, delete history, or weaken a
   fail-closed gate.
3. Reconcile Issue #28 against the checkpoint artifact-journal canary contract.
   Prove only the bounded canary behavior implemented here; a temporary runner
   directory or uploaded test artifact must never be represented as a
   production-durable store or as closure of Issue #28.
4. Keep automatic schedules disabled or absent. The production market pipeline
   must stop before admitted source collection whenever checkpoint, identity,
   authority, rights, secrets, calendar, or adapter gates are incomplete.
   Separately, the user-invoked Draft-PR opening may trigger one credential-free
   access-only probe to the fixed public allowlist. It must not parse the response
   into market evidence, create candidates, publish data, or invoke trading.
5. The access-only canary must preserve exact receipt provenance and an explicit
   `ABSTAIN / NO-TRADE` boundary. Raw bytes remain private and ephemeral; only a
   sanitized receipt/audit may be uploaded, and no real artifact may enter Git.
6. Run targeted tests, the complete relevant suite, control/bootstrap/security
   checks, package validation, and exact-head CI. Record the exact outcomes
   without converting a blocked canary into success.
7. Write the final result with `docs/codex/HANDOFF_TEMPLATE.md` and keep
   `docs/codex/USER_DECISIONS.md` as the decision authority.

## Acceptance gates

- The canonical JSON control and every active Markdown/JSON mirror agree.
- The control validator rejects the wrong branch, a moved base ref, invalid
  ancestry, unsafe permissions, and stale cross-file task identity.
- The checkpoint artifact-journal canary passes its integrity, corruption,
  concurrency, fencing, restore, and fail-closed configuration tests without a
  production-durability claim.
- Issue #28 remains open unless separately reviewed production wiring and genuine
  cross-run persistence evidence are available.
- Automatic schedules are disabled or absent and remain unauthorized.
- At most one user-invoked access-only canary is attempted through the Draft-PR
  opening. Its evidence states exactly where it stopped and never implies source
  admission, market-wide, predictive, recommendation, or trading readiness.
- No private source locator, credential, licensed byte, raw conversation, or real
  runtime artifact enters Git.
- The Draft PR exact head passes all applicable local checks and GitHub CI before
  any later merge decision.

## Safety and non-claims

- `MANUAL_CANARY_ALLOWED: YES` authorizes only the bounded fail-closed attempt
  described above; it is not automatic-scheduler authorization.
- A green synthetic or canary run proves neither predictive skill nor an accuracy
  rate.
- Missing official identity, authority, rights, durable state, or usable source
  evidence must remain a blocker or yield `ABSTAIN / NO-TRADE`.
- Do not merge while this control surface says `MERGE_ALLOWED: NO`.
