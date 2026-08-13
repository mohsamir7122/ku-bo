# KU-BO Current Codex Status

Status date: 2026-08-13

Repository:

```text
mohsamir7122/ku-bo
```

## Verified live chain

```text
main@c621fcf88034c4571aa08aee2e54e2e026a4f651
  └── Merge PR #12 as TEST_SPEC_ONLY
        └── GitHub Actions 31684299396 / PASS
              └── build/tri-security-receipt-enforcement-v0.2
                    @6dc821f8342bf2041ac3bed983c6805ff0a2c3fc
                      └── Draft PR #13
                            └── GitHub Actions 31695010037 / PASS
```

PRs #4 through #12 are merged into `main`. PR #12 entered `main` at merge
commit `c621fcf` and post-merge CI run `31684299396` passed, but its status
remains `TEST_SPEC_ONLY`: it contributes the deterministic KU-BO-011
acceptance corpus, not runtime enforcement. Open PRs #2 and #3 remain stale,
conflicting, and based on pre-stack history; neither is an authority or a safe
base for current work.

The KU-BO-011 implementation branch
`build/tri-security-receipt-enforcement-v0.2` now includes merged `main` and is
published as Draft PR #13 at remote implementation head
`6dc821f8342bf2041ac3bed983c6805ff0a2c3fc`. Exact-head GitHub Actions run
`31695010037` completed successfully, including the Python 3.11, 3.12, 3.13,
and 3.14 jobs.

## Proven on merged main

- deterministic three-security batches beginning with KFH/SHIP/AZNOULA;
- exact scoped configuration and non-overwriting qualification workspaces;
- every candidate identity remains `UNVERIFIED_SEED`;
- every final Data Foundation gate remains `PENDING_EXTERNAL_EVIDENCE`;
- authenticated Run Receipt and Stage Binding v1 primitives use independent
  runtime-only HMAC authorities and fail closed on byte or scope drift;
- the merged PR #12 corpus locks 1,280 deterministic synthetic adversarial
  Test Specifications while retaining its explicit non-claim;
- the inherited five-security Benchmark registry remains explicitly
  incompatible with the tri-security cohort because Industrials and Utilities
  sector series are missing;
- PRs #10 and #11 were merged in dependency order, and exact post-merge `main`
  CI passed on Python 3.11 through 3.14.

The merged KU-BO-010 contract is an authenticated binding, not market evidence.
Stage Binding v1 proves byte integrity and association with the authenticated
run, but its explicit claim remains
`binding_proves_stage_matches_run_scope=false`. It has no authenticated
predecessor graph and must not be reinterpreted as semantic admission.

## Merged PR #12 — KU-BO-011 acceptance specification only

PR #12 publishes:

```text
8 importer/reconciliation boundaries
x 40 mutation families
x 4 concrete attack channels/timings
= 1,280 deterministic case specifications
```

The corpus SHA-256 is
`53c95afbdf4174a5c3e74c2bfb798beddc650841f1301d4b8d99bc4a54af2b03`.
Its exact-head CI ran 1,841 repository tests and passed the deterministic
generator, Schema, semantic-fingerprint, wheel, installed-CLI, smoke, control,
and secret checks on Python 3.11 through 3.14. PR #12 then merged as `c621fcf`,
and post-merge `main` CI run `31684299396` passed.

This proves the structure and reproducibility of the synthetic test
specification only. Without an implementation Adapter, strict mode returns
`TARGET_ADAPTER_UNAVAILABLE`. Even after an Adapter exists, it must exercise
real production paths and cannot merely echo each case's expected rejection.
PR #12 therefore carries the non-claim:

```text
TEST_SPEC_ONLY_NO_KU_BO_011_RUNTIME_ENFORCEMENT_CLAIM
```

## Active KU-BO-011 implementation

KU-BO-011 remains `IN_PROGRESS`. At published implementation head
`6dc821f8342bf2041ac3bed983c6805ff0a2c3fc`, Draft PR #13 now delivers:

- semantic admission v2 authenticated by a third runtime-only HMAC authority,
  separate from Run Receipt and Stage Binding v1;
- an exact eight-boundary stage map, boundary-input role binding, and
  authenticated predecessor DAG;
- mandatory `BoundaryAdmissionRequest` entry arguments for all eight Direct
  APIs and installed CLI commands;
- no-overwrite atomic staging plus admission revalidation immediately before
  commit;
- an issuance CLI for semantic admissions and required predecessor paths;
- focused positive/negative tests for admission, wrapper ordering, exact input
  maps, atomic output, CLI construction, and independent keys;
- a strict JSON Schema 2020-12 contract at
  `schemas/tri-security-semantic-admission.schema.json`;
- a non-echoing production Adapter with an independent executable
  materialization contract for every mutation/channel/variant and AST guards
  against importing the Test-Spec oracle;
- Corpus v3 generation and audit with 1,280 exact executable descriptors and
  corpus SHA-256
  `e7e84f75feae5ea72a5d4f67af50da24f5d46e5a9cba49030ff8547a41b50288`;
- strict source-tree and clean-installed-wheel runs of all 1,280 cases, both
  passing `1,280/1,280` with zero protected-output writes;
- an installed authenticated eight-boundary predecessor DAG that produced and
  verified eight semantic admissions and eight lineage artifacts; and
- a complete local unit/adversarial suite of 1,916 passing tests, plus passing
  compile, deterministic generator/audit, Codex control, synthetic smoke,
  secret, and diff checks.

The implementation evidence is now published and exact-head CI-proven as
`CODE_AND_SYNTHETIC_ADVERSARIAL_ENFORCEMENT / SYNTHETIC_ONLY`. It does not
retroactively change PR #12: its merged evidence remains historically
`TEST_SPEC_ONLY`. It also does not prove market data, provider authority,
capture rights, a real backtest, forecast skill, probability, accuracy,
recommendation, or production readiness.

The implementation-evidence handoff can now be `COMPLETED`. KU-BO-011 remains
`IN_PROGRESS`, `EXPECTED_PR_MODE` remains `DRAFT`, and `MERGE_ALLOWED` remains
`NO`: this control-record update will create a head after `6dc821f`, and that
new exact head must pass CI before the ordered merge-boundary recheck.

The user's current instruction authorizes the necessary ordered changes and
merges only under the conditions recorded in `KU-BO-MERGE-003`. During active
implementation, the task branch remains Draft and the repository-native
`MERGE_ALLOWED` flag remains `NO`; the merges may occur only after the exact
applicable gates pass and the approval record is rechecked.

## External and legacy evidence status

- Diagnostic provider artifacts remain metadata-only and cannot be promoted
  because authority, provenance, capture receipts, and rights are unresolved.
- The July prediction/results material remains
  `UNTRUSTED_LEGACY_CLAIM / QUARANTINED`; it cannot support training, backtest,
  accuracy, or recommendation claims.
- No raw private conversation was imported.
- The private conversation archive remains outside Git.

## Still not proven

- exact-head GitHub Actions for the control-record commit after
  `6dc821f8342bf2041ac3bed983c6805ff0a2c3fc`;
- final merge-boundary review, mergeability recheck, and post-merge `main` CI;
- complete effective-dated historical market universe;
- real rights-compatible Benchmark and Official Complete EOD packets;
- complete historical Corporate Actions and suspension/resumption evidence;
- authenticated provider capture authority or an independent final Data
  Foundation authority receipt;
- an approved product-specific outcome-session policy for `KU-BO-008-D01`;
- real Data Foundation qualification or baseline-backtest readiness;
- forecast skill, probability calibration, prospective accuracy, or any
  trading recommendation;
- production execution or authorization of a later tri-security batch.

## Active instruction

The only repository-native task record is:

```text
docs/codex/CURRENT_TASK.md
```

Historic handoffs, Drive copies, legacy conversations, PR #12 Test Specs, and
related-repository claims are context only. None can weaken current evidence,
rights, receipt, policy, or financial-safety gates.
