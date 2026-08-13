# CURRENT TASK — KU-BO-011

```text
TASK_ID: KU-BO-011
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: c621fcf88034c4571aa08aee2e54e2e026a4f651
EXPECTED_NEW_BRANCH: build/tri-security-receipt-enforcement-v0.2
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
APPROVED_MERGE_DECISION: KU-BO-MERGE-003
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
TEST_SPEC_PR: https://github.com/mohsamir7122/ku-bo/pull/12
IMPLEMENTATION_PR: https://github.com/mohsamir7122/ku-bo/pull/13
IMPLEMENTATION_PR_SHA: 6dc821f8342bf2041ac3bed983c6805ff0a2c3fc
IMPLEMENTATION_CI_RUN: https://github.com/mohsamir7122/ku-bo/actions/runs/31695010037
BLOCKED_ON: REAL_MARKET_EVIDENCE; AUTHENTICATED_CAPTURE_AUTHORITY; KU-BO-008-D01; BENCHMARK_SCOPE_COMPATIBILITY
```

## Mission

Implement mandatory fail-closed Run Receipt and semantic stage-admission
enforcement at every scoped importer pre-write boundary and carry one
authenticated run/stage/predecessor chain into final Data Foundation
reconciliation. Reject every invalid admission before protected output is
created, recheck security-sensitive state immediately before atomic commit,
and preserve all current evidence, rights, policy, Benchmark, and financial
non-claim boundaries.

Do not merge the implementation during active validation. The PR #12 portion
of the user's ordered approval has been exercised and passed post-merge CI.
The remaining implementation-merge authority is recorded in
`docs/codex/USER_DECISIONS.md` as `KU-BO-MERGE-003`; it may be exercised only
after the production Adapter, complete suite, publication, and exact-head CI
gates pass.

## Verified dependency state

```text
main@c621fcf88034c4571aa08aee2e54e2e026a4f651
PR #12 merged as TEST_SPEC_ONLY
Post-merge GitHub Actions 31684299396 / PASS

build/tri-security-receipt-enforcement-v0.2
@6dc821f8342bf2041ac3bed983c6805ff0a2c3fc
Draft PR #13 / GitHub Actions 31695010037 PASS
Python 3.11 / 3.12 / 3.13 / 3.14 jobs PASS
```

Merged PR #12 contains 1,280 deterministic synthetic Test Specifications and
a strict Adapter harness. It carries
`TEST_SPEC_ONLY_NO_KU_BO_011_RUNTIME_ENFORCEMENT_CLAIM`; it is not an
implementation dependency that may be treated as proof merely because its
self-audit passes.

The implementation branch now contains semantic admission v2, mandatory
Direct API and CLI admission construction for all eight boundaries, atomic
no-overwrite staging with pre-commit revalidation, exact input-role binding,
the predecessor DAG, strict Schema, and a non-oracle production Adapter. The
Adapter owns an independent materialization contract and dispatches the
synthetic attacks through the named public production boundary. These
delivered code surfaces are published and exact-head CI-proven at `6dc821f`.
KU-BO-011 remains active until this later control-record head passes its own
exact-head CI and the ordered merge boundary is rechecked.

## Verified published implementation proof

The following results are published in Draft PR #13 at implementation head
`6dc821f8342bf2041ac3bed983c6805ff0a2c3fc`:

```text
Complete local unit/adversarial suite                 1,916 PASS
Strict source-tree Adapter corpus                     1,280/1,280 PASS
Clean-installed-wheel Adapter corpus                  1,280/1,280 PASS
Installed authenticated boundary DAG                 8/8 PASS
Installed semantic admissions                        8
Installed lineage artifacts                          8
Corpus v3 deterministic generator/audit              PASS
Corpus v3 SHA-256                                     e7e84f75feae5ea72a5d4f67af50da24f5d46e5a9cba49030ff8547a41b50288
Compile / Codex control / smoke / secret / diff       PASS
Exact-head GitHub Actions run 31695010037             PASS
Python 3.11 / 3.12 / 3.13 / 3.14 jobs                PASS
```

This proves published `CODE_AND_SYNTHETIC_ADVERSARIAL_ENFORCEMENT` and remains
`SYNTHETIC_ONLY`. PR #12 remains historically `TEST_SPEC_ONLY`; the branch
result does not convert its merged Test Specification into runtime proof. No
market bytes, provider or capture authority, rights, real backtest, forecast,
probability, accuracy, recommendation, or production operation is proven.
`KU-BO-008-D01` remains `OPEN`.

## Required boundary map

The implementation must enforce the following exact map in both Direct API and
installed CLI paths:

```text
import_user_price_exports      -> RESEARCH_PRICE_HISTORY
import_official_foundation     -> OFFICIAL_FOUNDATION
import_status_corporate        -> STATUS_CORPORATE
import_ca_enrichment           -> CA_ENRICHMENT
import_status_history          -> STATUS_HISTORY
import_benchmark_history       -> BENCHMARK_HISTORY
import_official_eod            -> OFFICIAL_EOD
build_data_foundation_packet   -> FINAL_DATA_FOUNDATION_RECONCILIATION
```

## Required predecessor graph

The versioned semantic-admission contract must make root/run authority and the
stage-specific predecessor set explicit. At minimum, it must preserve these
real data-flow dependencies:

```text
OFFICIAL_FOUNDATION       <- authenticated run/root admission
RESEARCH_PRICE_HISTORY    <- authenticated run/root admission
STATUS_CORPORATE          <- OFFICIAL_FOUNDATION
CA_ENRICHMENT             <- STATUS_CORPORATE
STATUS_HISTORY            <- STATUS_CORPORATE
BENCHMARK_HISTORY         <- OFFICIAL_FOUNDATION
OFFICIAL_EOD              <- OFFICIAL_FOUNDATION + STATUS_HISTORY
FINAL_DATA_FOUNDATION_RECONCILIATION
                          <- OFFICIAL_FOUNDATION
                           + STATUS_HISTORY
                           + CA_ENRICHMENT
                           + RESEARCH_PRICE_HISTORY
                           + BENCHMARK_HISTORY
                           + OFFICIAL_EOD
```

An omitted, duplicated, replayed, wrong-run, wrong-stage, skipped, reversed, or
unbound predecessor must fail closed.

## Versioning and semantic-admission guard

`Stage Binding v1.0` is immutable as a byte-integrity contract and retains:

```text
binding_proves_stage_matches_run_scope=false
```

KU-BO-011 must add a documented versioned contract or Schema for semantic
admission and the predecessor graph. It must not flip the existing v1 claim to
`true`, silently broaden v1, or accept caller Booleans as proof.

The implementation contract is Schema `2.0` at
`schemas/tri-security-semantic-admission.schema.json`; it is separate from the
unchanged `tri-security-stage-binding.schema.json` v1 contract and rejects
unknown fields, wrong boundary/stage pairs, wrong ordered input roles, and
wrong ordered predecessor stage sets structurally. Runtime verification remains
authoritative for authentication, hashes, same-run equality, safe filesystem
identity, and TOCTOU revalidation.

The new admission must authenticate and bind at least:

- exact Run Receipt, run ID, batch ID, and independent authority identities;
- batch plan and scoped configuration hashes;
- the three-security KFH/SHIP/AZNOULA cohort and its Security Codes;
- qualification window and `Asia/Kuwait` date basis;
- expected stage ID and exact predecessor set;
- input manifest and complete safe file-tree inventory;
- explicit Benchmark incompatibility and the three-security denominator;
- all pending gates and financial non-claim flags.

## Pre-write and commit requirements

For all eight boundaries:

1. require admission arguments in the Direct API, not only in CLI parsing;
2. authenticate and semantically validate before calling output-root creation
   or writing any normalized, report, manifest, temporary, or quarantine file;
3. reject pre-existing, aliased, overlapping, symlinked, traversal, or unsafe
   roots;
4. preserve zero protected-output writes on rejection;
5. write a valid result through a private temporary location and commit it
   atomically where the current platform contract permits;
6. rehash and reauthenticate the receipt, admission, predecessor artifacts,
   input tree, and destination identity immediately before commit;
7. emit stable failure codes matching the KU-BO-011 Corpus;
8. carry authenticated predecessor references into the output report and final
   reconciliation without converting binding integrity into market truth.

## Adapter integrity gate

The PR #12 harness currently validates returned fields and protected-output
state; a trivial Adapter could otherwise echo `case["expected"]`. KU-BO-011
completion therefore requires an Adapter and tests that:

- create a valid signed baseline with runtime-only fixture keys;
- apply the declared mutation to a real CLI argument, Direct API object,
  serialized artifact, or controlled filesystem-race hook;
- invoke the production boundary named by the case;
- obtain the stable failure code from the production exception/result path;
- prove production dispatch occurred and forbid expectation-only echoing;
- inspect every task-created write surface, not merely the Harness output
  directory.

A strict 1,280-case pass without this proof is insufficient.

The Adapter supplies that dispatch and anti-oracle proof, and both the
source-tree and clean-installed-wheel strict runs passed all 1,280 cases. Draft
PR #13 and exact-head run `31695010037` publish and confirm that implementation
proof at `6dc821f8342bf2041ac3bed983c6805ff0a2c3fc`.

## Acceptance gates

1. All eight Direct APIs and CLIs require and validate the correct admission.
2. Missing, malformed, forged, stale, future, wrong-key, wrong-audience,
   cross-run, wrong-batch, wrong-window, wrong-cohort, wrong-stage, altered-tree,
   unsafe-entry, TOCTOU, and predecessor-graph attacks fail before output.
3. Five-security, Full Market, Benchmark fallback, `KU-BO-008-D01`, and July
   legacy claim promotions remain rejected.
4. Stage Binding v1 remains byte-integrity-only; the semantic contract is
   separately versioned and authenticated.
5. The production-path Adapter passes all 1,280 locked cases with the exact
   stable failure codes and zero protected-output writes.
6. Positive valid-admission paths for every boundary pass and preserve current
   output Schemas and claim boundaries.
7. `compileall`, targeted tests, the complete unit/adversarial suite, Codex
   control check, synthetic smoke check, `secret_guard`, wheel build, isolated
   wheel reinstall, and installed CLI checks pass.
8. Exact-head GitHub Actions pass on Python 3.11 through 3.14.
9. A sanitized result is written using
   `docs/codex/HANDOFF_TEMPLATE.md` at
   `docs/codex/handoffs/KU-BO-011-result.md`.

Implementation gates 1 through 9 passed at published head
`6dc821f8342bf2041ac3bed983c6805ff0a2c3fc`, including run `31695010037` on
Python 3.11 through 3.14. This control-record update creates a later head that
must receive its own exact-head CI before merge-boundary review. `STATUS`
therefore remains `IN_PROGRESS`, `EXPECTED_PR_MODE` remains `DRAFT`, and
`MERGE_ALLOWED` remains `NO`.

## Required safety and non-claim boundaries

- `AUTHENTICATED_BINDING_NOT_MARKET_EVIDENCE` remains true.
- PR #12 remains `SYNTHETIC_ONLY / TEST_SPEC_ONLY`.
- Code and synthetic adversarial tests cannot prove provider authority,
  official identity, rights, completeness, or market truth.
- Every identity remains `UNVERIFIED_SEED` until qualifying official evidence
  passes the existing gates.
- The tri-security cohort does not prove the five-security Pilot or Full
  Market.
- Benchmark qualification remains blocked while Industrials and Utilities
  series are absent.
- `KU-BO-008-D01` remains OPEN and `outcome_session_policy` remains
  `UNFROZEN`.
- No later batch, real capture, real backtest, model training, forecast,
  probability, accuracy, recommendation, or production execution is
  authorized.
- No real market bytes, credentials, HMAC keys, licensed artifacts, Drive IDs,
  browser sessions, raw conversations, or quarantined July material may enter
  Git.
- Do not weaken tests, Schemas, evidence gates, or failure codes to obtain a
  green result.

## Publication and ordered-merge behavior

- PR #12 has already merged first as `TEST_SPEC_ONLY`; preserve that non-claim.
- Preserve Draft PR #13 and its proven implementation head while publishing
  this control-record-only update without broadening implementation claims.
- Before exercising the remaining `KU-BO-MERGE-003` authority, recheck the
  exact implementation head, changed files, review state, mergeability,
  secret/privacy scan, and exact-head CI.
- Merge the implementation only if every applicable KU-BO-011 gate passes.
- Do not merge PR #2 or PR #3, delete branches, enable auto-merge, or perform
  destructive cleanup under this task.

## Completion classification

The KU-BO-011 handoff may classify the accepted implementation only as:

```text
CODE_AND_SYNTHETIC_ADVERSARIAL_ENFORCEMENT_PROVEN
```

Real market evidence remains `LIVE_DEPENDENT` or
`LICENSED_FEED_DEPENDENT`, real Data Foundation readiness remains `BLOCKED`,
and `KU-BO-008-D01` remains `USER_DECISION_REQUIRED`.
