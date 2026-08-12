# KU-BO-010 — Authenticated tri-security run receipt and stage binding

```text
FINAL_STATUS: COMPLETED
REPOSITORY: https://github.com/mohsamir7122/ku-bo
BASE_BRANCH: build/tri-security-pilot-v0.3
STARTING_SHA: 7d032c98b0ef9f27e913199487ad4577119c2631
TASK_BRANCH: build/tri-security-run-receipt-v0.1
FINAL_SHA: 9c72e0d89f46ee846cb453087b00f7e6b64ace7a
DRAFT_PR: https://github.com/mohsamir7122/ku-bo/pull/11
PR_BASE: build/tri-security-pilot-v0.3
CI_RUN: https://github.com/mohsamir7122/ku-bo/actions/runs/31626453749
STARTED_AT: 2026-08-12 (Asia/Kuwait)
COMPLETED_AT: 2026-08-12T21:16:01+03:00
```

`FINAL_SHA` is the published implementation/test commit. Its tree SHA is
`d8b8ffd58bc0f716bcb542fbeb2c1c060db49eca`. The following documentation-only
commit records this handoff and changes no runtime, schema, configuration,
script, or test bytes. The live Draft PR and final user handoff identify that
documentation head and its own exact-head CI run.

## User goal

Locate and publish the smallest safe KU-BO-010 implementation on its own Draft
PR, preserving all prior work and financial/evidence gates. Because no existing
KU-BO-010 branch, commit, PR, issue, stash, local worktree, or unreachable
implementation was found, implement the standalone Run Receipt and Stage
Binding contract without broadening it into the KU-BO-011 importer rollout.

## Verified starting state

- `main` was `be5fe3883016dedf07fa680905f7199f3906b4d8`; PRs #4 through #9 were
  merged.
- The exact dependency was Draft PR #10 at
  `build/tri-security-pilot-v0.3@7d032c98b0ef9f27e913199487ad4577119c2631`.
  GitHub Actions run `31571987659` passed Python 3.11 through 3.14.
- PR #10 had no review request, approval, blocking review, unresolved review
  thread, merge action, or auto-merge. It remained Draft.
- PRs #2 and #3 were stale and conflicting against current `main`; neither was
  used as a base. Their older branches and review history were preserved.
- No remote or local KU-BO-010 implementation existed before this task. The
  only occurrence was the next-task proposal in the KU-BO-009 handoff.
- The starting Windows suite executed 528 tests. The only two errors were the
  known `WinError 1314` symlink-creation privilege limitation in adversarial
  tests; eight tests were skipped and there were no assertion failures. The
  exact dependency head passed the authoritative Linux CI matrix.
- An older dirty local clone contained one modified source file and untracked
  capture/debug material. It was inventoried and left untouched. Work proceeded
  in a fresh clone and branch.

## Access inventory

| Surface | Access result | Evidence found | Authority consequence |
|---|---|---|---|
| `mohsamir7122/ku-bo` GitHub repository | VERIFIED: authenticated repository, PR, branch, Actions, and push access | Live main, all open PRs, branches, and exact-head CI inspected | Safe publication path available; no merge permission inferred |
| Draft PR #10 | VERIFIED | Exact dependency SHA and green CI; no blocking review state | Accepted only as the stacked Draft base for KU-BO-010 |
| Related GitHub repositories | VERIFIED where present | AI-Mincy, Research, KW, KW2, Factor9-saudiai, and adjacent legacy repository inspected at metadata/code level | No artifact qualified as current KU-BO evidence; exact repository named `Factor9` was not found |
| Shared July prediction/results page | VERIFIED reachable | Presence and legacy claim shape confirmed without copying the conversation | `UNTRUSTED_LEGACY_CLAIM / QUARANTINED`; unusable for truth, training, backtest, or accuracy |
| Connected Drive control folder | VERIFIED readable | Control documents were stale at KU-BO-008 relative to GitHub KU-BO-009 | GitHub repository-native control remained authoritative |
| Drive Price Collection Pilot | ACCESSIBLE BUT INCOMPLETE | Reports, manifests, and quarantine areas had no qualifying run/capture/authority receipt; diagnostic provider files were metadata-only | Rights, provenance, capture authority, and completeness unresolved; no import |
| Private conversation archive | INTENTIONALLY NOT OPENED | None | Privacy boundary preserved; no raw conversation copied |
| Local clones/worktrees | VERIFIED | Fresh task clone plus older clean and dirty historical clones inventoried | Existing changes preserved; only the fresh task branch was modified |
| Authenticated capture receipt, final authority receipt, outcome ledger | NOT FOUND | No qualifying runtime artifact in inspected surfaces | Real qualification, later batch, backtest, forecast, and recommendation remain blocked |

No authentication or network blocker prevented the permitted repository and
metadata inspection. Access to an artifact did not convert it into authorized
market evidence.

## Changes made

### Standalone Run Receipt

- Added a strict Canonical JSON Run Receipt authenticated with runtime-only
  `HMAC-SHA256` material.
- Required externally supplied expected hashes for the exact batch plan and
  scoped configuration manifest.
- Rehashed the plan, scoped manifest and files, workspace report, registry,
  first batch, exact KFH/SHIP/AZNOULA cohort, qualification window, and all
  pending gate states before issuance and verification.
- Locked the contract to batch one, exactly three unique identities, and
  `UNVERIFIED_SEED`; no predecessor or later-batch authority can be inferred.
- Derived `run_date` from `issued_at` in `Asia/Kuwait`, limited validity to seven
  days, and re-read critical files to detect validation-time drift.

### Independent Stage Binding

- Added a second authenticated contract whose HMAC key and key ID must both
  differ from the Run Receipt authority.
- Bound the Run Receipt plus the stage Manifest, declared artifacts, and the
  complete stage-tree inventory. Added, deleted, undeclared, mutated, symlinked,
  special, traversing, stale, or cross-run content fails closed.
- Preserved `binding_proves_stage_matches_run_scope=false`: KU-BO-010 proves
  byte integrity and receipt association only. Stage-specific cohort/window
  semantics become mandatory at importer pre-write boundaries in KU-BO-011.
- Required disjoint external roots for workspace, stage output, Run Receipt,
  and Stage Binding, and refused overwrite of a pre-existing output root.
- Supported the eight existing Data Foundation stage identifiers without
  creating a parallel readiness or gate model.

### Benchmark and claim boundaries

- Derived Benchmark comparison scope from the exact three-security cohort.
- Preserved the inherited registry defect as
  `CONFIGURED_SERIES_INCOMPATIBLE_WITH_TRI_COHORT`: the tri cohort requires
  Industrials and Utilities sector series that the five-security registry does
  not contain.
- Made Benchmark qualification, five-security scope, full-market scope, data
  qualification, next-batch authorization, backtest, and forecast claims
  explicit `false` constants in runtime and schema contracts.

### CLI, schema, tests, and documentation

- Added issue/verify commands for Run Receipt and Stage Binding. Keys are read
  only from four runtime environment variables, and printed reports remove
  authentication material and absolute paths.
- Added strict Draft 2020-12 JSON Schemas and adversarial tests for tampering,
  stale validity, wrong keys and IDs, cross-receipt mixing, scope promotion,
  unsafe roots, stage mutation, and schema drift.
- Extended the isolated installed-wheel exercise to cover the new command
  surface without persisting secrets.
- Added `docs/TRI_SECURITY_RUN_RECEIPT_V0_1_AR.md` and updated repository-native
  status and task control. An additional parallel master plan was not created;
  the existing CURRENT_TASK/status/handoff control chain was current and
  authoritative.

## Validation performed

```text
COMMAND_OR_JOB: dependency GitHub Actions run 31571987659 at 7d032c98b0ef9f27e913199487ad4577119c2631
RESULT: PASS
DETAIL: All Python 3.11, 3.12, 3.13, and 3.14 jobs passed before KU-BO-010 changes.
```

```text
COMMAND_OR_JOB: starting python -m unittest discover -s tests -q on Windows
RESULT: FAIL
DETAIL: 528 tests executed; only two pre-existing WinError 1314 symlink privilege errors, eight skips, and no assertion failures. Exact dependency Linux CI was green.
```

```text
COMMAND_OR_JOB: targeted tri-security receipt, schema, and CLI tests
RESULT: PASS
DETAIL: 59 focused receipt, foundation I/O, schema, tri-pilot, CLI, and control tests passed; four platform-dependent tests skipped on Windows.
```

```text
COMMAND_OR_JOB: python -m compileall -q src tests scripts; codex_control_check.py; smoke_check.py; secret_guard.py
RESULT: PASS
DETAIL: Compilation, repository-native control integrity, synthetic smoke contracts, secret-pattern guard, and git diff checks all passed.
```

```text
COMMAND_OR_JOB: complete unit and adversarial suite
RESULT: ENVIRONMENT_LIMITED
DETAIL: 548 tests ran in 208.016 seconds with no assertion failure. Ten tests skipped; the only two errors were the pre-existing WinError 1314 inability to create symlinks in test_ingestion and test_live_probe. The exact Linux CI matrix passed the same committed tree.
```

```text
COMMAND_OR_JOB: isolated wheel build, forced reinstall, and installed_data_foundation_check.py
RESULT: PASS
DETAIL: A fresh Python 3.13 environment installed the 337439-byte wheel (SHA-256 3adf9c611fc8c83d0a654b6d42f34743bc209b1362d8dc34a69334401af6a730) and exercised 16 selected distinct installed CLI flows, including the four receipt/binding commands. The installed CLI exposes additional commands that this fixture-driven wheel check does not claim to exercise.
```

```text
COMMAND_OR_JOB: exact-head GitHub Actions run 31626453749 for 9c72e0d89f46ee846cb453087b00f7e6b64ace7a
RESULT: PASS
DETAIL: Draft PR #11 passed contracts-and-tests on Python 3.11, 3.12, 3.13, and 3.14, including the repository-bound wheel exercise.
```

## Evidence and data status

- Runtime, schemas, CLI, and tests: `SYNTHETIC_ONLY` as evidence; they prove
  engineering behavior, not market truth.
- Issuance and verification contract: `PARTIAL`; it can authenticate binding
  integrity when supplied real external keys, but no production authority
  receipt was issued or committed.
- KFH/SHIP/AZNOULA identities: `BLOCKED` as official evidence and remain
  `UNVERIFIED_SEED`.
- Benchmark registry: `BLOCKED` for tri-cohort qualification because required
  sector coverage is incompatible.
- Real identity, status, Corporate Action, price, Benchmark, EOD, and
  reconciliation bytes: `BLOCKED`; none was collected or committed.
- July prediction/results material: `UNTRUSTED_LEGACY_CLAIM / QUARANTINED`, not
  a training or performance artifact.
- Provider diagnostic artifacts: `LIVE_DEPENDENT` and
  `LICENSED_FEED_DEPENDENT` until authority, provenance, rights, query, window,
  and exact captured-byte receipts are independently verified.

## July legacy claim quarantine

The reachable shared page contains historical prediction/results assertions,
but this task records only the classification and reasons, not its raw text.
The claim lacks an authenticated capture Manifest, point-in-time feature
lineage, complete official-session denominator, effective status and Corporate
Action treatment, approved product-specific outcome policy, reproducible code
and environment, and independent run/final authority receipts. It therefore
cannot be accepted as a result, used for training, entered into an outcome
ledger, or described as July accuracy.

## Claims allowed

- A correctly keyed Run Receipt can authenticate the exact prepared batch-one
  plan, scoped config, cohort, and window while it remains valid.
- A correctly keyed Stage Binding can detect any change to its currently bound
  complete stage file tree.
- A Stage Binding alone does not prove that the stage semantics match the run
  scope; that remains an explicit false non-claim until KU-BO-011 wiring.
- The two authorities are independently keyed and external to Git and bound
  workspaces.
- The current Benchmark registry is visibly incompatible with the exact tri
  cohort and therefore cannot pass Benchmark qualification.
- The implementation does not authorize a later batch or any market claim.

## Claims still forbidden

- real Data Foundation qualification or baseline-backtest readiness;
- forecast accuracy, prospective skill, or historical performance;
- probability or calibrated confidence;
- buy/sell, entry/exit, position, execution, or any recommendation;
- five-security or full-market coverage;
- official or licensed status for unverified bytes;
- `LIVE_OPERATIONAL` source status;
- later-batch authorization;
- end-to-end receipt enforcement in importers or reconciliation, which is
  explicitly deferred to KU-BO-011.

## Privacy and repository safety

```text
credentials or sessions: NO
HMAC keys or authentication tags in reports: NO
private Drive IDs: NO
raw conversations: NO
real runtime market data: NO
licensed data: NO
destructive cleanup: NO
force push: NO
merge or auto-merge: NO
```

Existing dirty local work, old PR branches, related repositories, Drive files,
and private archives were preserved. No conversation, repository, branch, PR,
artifact, or file was deleted or closed.

## User decisions required

`KU-BO-008-D01` remains `OPEN`. The existing repository decision record offers:

1. advance to the next eligible official session across a suspension/halt;
2. retain the scheduled official-session horizon and record non-fill/no-outcome;
3. define a product-specific maximum extension and fail-closed terminal
   treatment.

The recorded recommendation is option 3, but **no option was selected**. The
decision must also define terminal treatment, non-fill handling, Corporate
Action interaction, official-calendar/status inputs, and metric impact before
any real outcome evaluation. KU-BO-010 neither freezes nor implements it.

No new deletion, merge, licensing, credential, data-source, or paid-service
decision was inferred or executed.

## Items classified for retention

```text
KEEP: strict Run Receipt and Stage Binding runtime, schemas, CLI, tests, and Arabic contract
KEEP: KU-BO-009 exact three-security workspace and pending gate model
KEEP: explicit Benchmark incompatibility finding and fail-closed non-claims
KEEP: sanitized access inventory and legacy-claim quarantine classification
REFACTOR: downstream importer entry points only in KU-BO-011, preserving their existing evidence gates
ARCHIVE: stale PR #2/#3 and legacy repository history as review context; no closure authorized
PRIVATE_ONLY: production HMAC keys, real receipts, captured bytes, Drive/private conversation material
DELETE_CANDIDATE: None
```

## Known limitations and risks

- The contract is standalone. Existing importers and final reconciliation can
  still be called without it until KU-BO-011 adds mandatory pre-write checks.
- A valid HMAC proves possession of a configured key and integrity of bound
  bytes; it does not prove provider authority, rights, completeness, official
  identity, or economic correctness.
- HMAC trust remains operationally dependent on external key custody, rotation,
  issuer governance, and non-reuse; those secrets are intentionally absent from
  Git.
- Stage Binding understands the existing Manifest v3 byte inventory, not the
  semantics or market truth of each artifact.
- The Benchmark registry denominator mismatch is intentionally unresolved and
  blocks qualification.
- Windows without symlink privilege cannot execute two existing adversarial
  symlink-construction tests; exact-head Linux CI remains authoritative.
- `main` has no repository branch protection; policy and explicit user approval
  remain the merge safety control.

## Smallest logical next task

```text
TASK_ID: KU-BO-011
PROPOSED_BRANCH: build/tri-security-receipt-enforcement-v0.2
DEPENDENCY: KU-BO-010 Draft PR reviewed at its exact green head; no merge is performed by this handoff
GOAL: Require the authenticated Run Receipt and correct Stage Binding at every scoped importer pre-write boundary and carry the same binding chain into final Data Foundation reconciliation.
ENTRY_GATE: Published KU-BO-010 schemas/CLI are green; externally supplied expected plan, scoped-manifest, stage-manifest, run, batch, and key identities are available at runtime.
EXIT_GATE: Wrong, missing, stale, altered, cross-run, cross-stage, wrong-cohort, wrong-window, five-security, or Benchmark-incompatible bindings fail before any importer or reconciliation output is created; installed-wheel and adversarial CI pass.
```

KU-BO-011 must not weaken current identity, evidence, rights, price, Corporate
Action, Benchmark, EOD, final reconciliation, outcome-policy, or financial
claim gates. It still does not authorize real capture, a real backtest, model
training, forecast, probability, recommendation, later batch, or merge.
