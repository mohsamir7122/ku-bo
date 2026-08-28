# KU-BO Current Codex Status

Status date: 2026-08-28

Canonical machine-readable control:
`config/codex_control_state.json`.

## Active control

```text
task:                 KU-BO-2026-08-28-READINESS-CANARY
status:               COMPLETED
repository:           mohsamir7122/ku-bo
base branch:          main
base SHA:             8860989f6a2affdc66bc790f639757c9a897f353
working branch:       codex/ku-bo-readiness-live-canary-v1
PR mode:              DRAFT
merge allowed:        NO
automatic schedules: NOT AUTHORIZED
manual canary:        AUTHORIZED, ONE SECURITY, FAIL-CLOSED
```

PR #25 is merged. Commit
`8860989f6a2affdc66bc790f639757c9a897f353` is the frozen base of this task; the
older Day-One branch, pre-merge SHA, and Draft-PR status are historical and no
longer active control.

## Proven baseline

- The merged Day-One implementation passed its recorded 2,512-test local suite
  and exact-head CI before merge.
- It implements the one-security/29-source sequence, checkpoint and recovery
  contracts, source provenance, and fail-closed research boundaries.
- These results are software and synthetic evidence. They do not prove live
  collection, model training, prediction quality, a recommendation, or trade
  readiness.

## Current operational truth

- The latest scheduled pipeline stopped at `BLOCKED_CHECKPOINT_STORE`; Issue #28
  remains the operational incident being remediated.
- Admitted official point-in-time universe: missing.
- Signed issuer-domain trust registry: missing.
- Admitted live adapters: missing.
- Verified real observations, events, training rows, predictions, and live
  candidates: zero.
- Current safe research boundary: `ABSTAIN / NO-TRADE`.

## Active scope

The bounded readiness-remediation task is complete in Draft PR #29. Implementation
head `8b47a4c2a73c002e8f9d2f4deb8437c2677a663b` passed exact-head CI run
`33180204416` across Python 3.11, 3.12, 3.13, and 3.14. Local validation passed
2,596 tests, the clean installed-wheel eight-boundary check, bootstrap/control,
schema, compile, secret, automation, and migration-preparation gates.

Checkpoint canary run `33178972634` passed its bounded two-runner artifact-journal
contract. The single authorized access-only canary run `33178972676` stopped at
`BLOCKED_ACCESS_ONLY_CANARY` with `SOURCE_STATE_ERROR`; it emitted a sanitized
receipt and `ABSTAIN / NO-TRADE`, not admitted market evidence. No retry was
performed. Automatic schedules remain disabled or absent. Issue #28 remains open
until separately reviewed production wiring and genuine cross-run persistence
evidence exist. These outcomes do not prove `LIVE_OPERATIONAL` status.

## Governance state

- `config/codex_control_state.json` is the one active machine-readable source of
  truth. Markdown and `PROGRESS.json` are checked mirrors or historical evidence.
- The control validator must bind this state to the actual Git branch, `HEAD`,
  frozen base ref/SHA, ancestry, and cross-file identifiers.
- GitHub currently reports `main` as unprotected and no repository ruleset is
  installed. That external setting remains a repository-owner governance action;
  this branch cannot claim it is enforced.
- Draft PR #26 is separate checkpoint-v2 work and is not merged merely because it
  is clean or its CI is green.
- Draft PR #29 contains this completed bounded task. It remains unmerged because
  `MERGE_ALLOWED: NO`; completion closes the task record, not the merge boundary.
