# KU-BO Current Codex Status

Status date: 2026-08-13

Repository:

```text
mohsamir7122/ku-bo
```

## Verified live chain

```text
main@6bcfbabf840e6876a878dfd692afbf746780d731
  └── GitHub Actions 31629909113 / PASS
        └── test/ku-bo-011-adversarial-corpus-v0.1
              @3d773448b78ca99f6761a43b852f53967fdbb095
              └── Draft PR #12 / GitHub Actions 31631077911 / PASS
```

PRs #4 through #11 are merged into `main`. PR #12 is clean and mergeable
against that exact `main` head, but it contains a deterministic KU-BO-011
acceptance-spec corpus only. It does not implement mandatory downstream Run
Receipt or Stage Binding enforcement. Open PRs #2 and #3 remain stale,
conflicting, and based on pre-stack history; neither is an authority or a safe
base for current work.

The local KU-BO-011 implementation branch
`build/tri-security-receipt-enforcement-v0.2` was created from the exact PR #12
head. At this status snapshot it has no implementation commit or published PR.

## Proven on merged main

- deterministic three-security batches beginning with KFH/SHIP/AZNOULA;
- exact scoped configuration and non-overwriting qualification workspaces;
- every candidate identity remains `UNVERIFIED_SEED`;
- every final Data Foundation gate remains `PENDING_EXTERNAL_EVIDENCE`;
- authenticated Run Receipt and Stage Binding v1 primitives use independent
  runtime-only HMAC authorities and fail closed on byte or scope drift;
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

## PR #12 — KU-BO-011 acceptance specification only

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
and secret checks on Python 3.11 through 3.14.

This proves the structure and reproducibility of the synthetic test
specification only. Without an implementation Adapter, strict mode returns
`TARGET_ADAPTER_UNAVAILABLE`. Even after an Adapter exists, it must exercise
real production paths and cannot merely echo each case's expected rejection.
PR #12 therefore carries the non-claim:

```text
TEST_SPEC_ONLY_NO_KU_BO_011_RUNTIME_ENFORCEMENT_CLAIM
```

## Active KU-BO-011 boundary

KU-BO-011 is `IN_PROGRESS`. It must:

- add versioned semantic admission without changing the v1 byte-integrity
  claim;
- make the authenticated Run Receipt and correct stage admission mandatory at
  all seven importer boundaries and final Data Foundation reconciliation;
- bind the exact run, batch, three-security cohort, qualification window,
  stage identity, and required predecessor graph;
- reject missing, altered, stale, replayed, cross-run, wrong-stage,
  wrong-cohort, wrong-window, scope-promoting, or Benchmark-incompatible input
  before any protected output write;
- revalidate security-sensitive state before atomic commit to detect TOCTOU;
- prove the rejection paths through production APIs and CLIs, not through an
  expectation-echoing test double.

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

- production-path receipt and semantic-stage enforcement at all eight
  KU-BO-011 boundaries;
- an authenticated and complete predecessor graph carried into final
  reconciliation;
- zero-write rejection for all 1,280 cases against the real implementation;
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
