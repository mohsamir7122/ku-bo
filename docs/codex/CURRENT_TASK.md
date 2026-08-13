# CURRENT TASK — KU-BO-011

```text
TASK_ID: KU-BO-011
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: test/ku-bo-011-adversarial-corpus-v0.1
CONTROL_BASE_SHA: 3d773448b78ca99f6761a43b852f53967fdbb095
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

Do not merge during implementation. The user's conditional ordered-merge
approval is recorded in `docs/codex/USER_DECISIONS.md` as
`KU-BO-MERGE-003`; it may be exercised only after the applicable exact-head
acceptance and CI gates pass.

## Verified dependency state

```text
main@6bcfbabf840e6876a878dfd692afbf746780d731
GitHub Actions 31629909113 / PASS

test/ku-bo-011-adversarial-corpus-v0.1
@3d773448b78ca99f6761a43b852f53967fdbb095
Draft PR #12 / GitHub Actions 31631077911 / PASS
```

PR #12 contains 1,280 deterministic synthetic Test Specifications and a strict
Adapter harness. It carries
`TEST_SPEC_ONLY_NO_KU_BO_011_RUNTIME_ENFORCEMENT_CLAIM`; it is not an
implementation dependency that may be treated as proof merely because its
self-audit passes.

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

- Publish the implementation first as a Draft PR.
- Preserve PR #12 as a `TEST_SPEC_ONLY` dependency.
- Before exercising `KU-BO-MERGE-003`, recheck the exact head, changed files,
  review state, mergeability, secret/privacy scan, and exact-head CI.
- Merge PR #12 first. Then update or retarget the implementation PR to the new
  `main` without force-pushing, rerun exact-head CI, and merge it only if every
  applicable KU-BO-011 gate passes.
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
