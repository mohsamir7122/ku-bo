# CURRENT TASK — KU-BO-014

```text
TASK_ID: KU-BO-014
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: 59833bf73510b3aa3901f628cbf2c13c0d01cf79
EXPECTED_NEW_BRANCH: agent/bootstrap-archive-v0.1
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
HISTORICAL_CORPUS_COLLECTION_REQUESTED: NO
BOOTSTRAP_ARCHIVE_MODE: EMPTY_SCAFFOLD_ONLY
BLOCKED_ON: FINAL_CONTROL_RECORD_HEAD_EXACT_CI
FUTURE_COLLECTION_BLOCKED_ON: OFFICIAL_COMPANY_UNIVERSE_ENUMERATION; LIVE_COLLECTION_CONTRACT; SOURCE_RIGHTS_REVIEW
```

## Mission

Build an isolated, no-overwrite `Bootstrap Archive` scaffold inside the KU-BO
architecture. Reuse the six KU-BO-013 historical layers and their 28-source
catalog without duplicating year, query, authority, or source definitions. The
stage prepares control artifacts, deterministic plans, directories, hashes,
and explicit gates only; it does not collect the historical corpus.

The scaffold must preserve the requested future order:

1. historical Bootstrap Archive;
2. Company Intelligence;
3. source waves;
4. final Boursa Kuwait official reconciliation.

Company Intelligence still requires a thin official listed-universe identity
anchor before it can begin. This prerequisite does not move the full Boursa
reconciliation stage forward; it prevents an unofficial company list from
becoming the denominator.

## Required capability

1. A strict archive contract defines five archive sections and the ordered
   four-stage dependency chain.
2. A complete crosswalk covers every KU-BO-013 historical source and references
   existing Source Network IDs where a semantic bridge exists. A mapping is not
   a Connector, Parser, live capability, or collection authorization.
3. The scaffold reuses `HistoricalKnowledgeCatalog` and
   `compile_research_plan`; it must not reimplement the six ranges or duplicate
   the resulting annual tasks.
4. Workspace creation is atomic and no-overwrite. A failure must not publish a
   partial target or replace an existing archive.
5. The published scaffold contains control artifacts only. Evidence count,
   event count, and company count all begin at zero.
6. Verification reopens the workspace, checks the exact allowed inventory,
   rehashes every control artifact, rejects path escapes and mutable-tree drift,
   and proves that no Evidence artifact was smuggled into the empty scaffold.
7. Stage states begin fail-closed:

```text
BOOTSTRAP_ARCHIVE: EMPTY_ARCHIVE_PREPARED_COLLECTION_BLOCKED
COMPANY_INTELLIGENCE: BLOCKED_PENDING_BOOTSTRAP_VALIDATION_AND_OFFICIAL_UNIVERSE
SOURCE_WAVES: BLOCKED_PENDING_COMPANY_INTELLIGENCE
BOURSA_OFFICIAL_RECONCILIATION: BLOCKED_PENDING_SOURCE_WAVES
```

## Acceptance gates

1. Strict config validation rejects duplicate, missing, unknown, reordered, or
   unsafe archive definitions.
2. The crosswalk covers all 28 historical source IDs exactly once; referenced
   network IDs must exist, while unmapped sources remain explicitly blocked.
3. The historical plan remains deterministic and gap-free at the supplied
   `as_of`; at `2026-08-14` it reuses the 756 KU-BO-013 tasks.
4. Archive and Manifest identities bind canonical content and configuration
   hashes. A runtime timestamp must not silently change the deterministic plan
   identity.
5. Workspace publication is atomic, no-overwrite, symlink-safe, and rejects
   partial output.
6. The empty Manifest contains zero Evidence artifacts and cannot prove that a
   historical event did not occur.
7. Company Intelligence, source waves, and final Boursa reconciliation cannot
   become ready through caller booleans or stage labels alone.
8. Targeted tests, complete suite, compile, smoke, Secret Guard, strict
   JSON/Schema, control check, wheel, isolated install, and exact-head CI pass.
9. Documentation and an `IN_PROGRESS` handoff distinguish scaffold validity
   from corpus collection, source operation, or investment readiness.
10. Publish only a Draft PR. Do not merge without a separate explicit merge
    decision recorded after the final exact head passes all gates.

## Safety and non-claims

- No historical page, PDF, newspaper article, social post, court record,
  company record, or market byte is collected or committed in this stage.
- Runtime archive output remains outside Git; Git contains only code, contracts,
  Schemas, tests, and documentation.
- Crosswalk rows remain `DEFINED_ONLY` and `collection_allowed=false`.
- An empty archive is not evidence of historical silence.
- Historical material remains `CONTEXT_ONLY`; it cannot directly create a
  Factor, Score, Forecast, probability, recommendation, or execution action.
- Community and social sources remain routing or sentiment only.
- Authentication, CAPTCHA, paywalls, robots controls, platform terms, privacy,
  copyright, and licensing restrictions must not be bypassed.
- `MERGE_ALLOWED` remains `NO` throughout implementation and validation.

## Decision authority

Development authority is recorded in `KU-BO-014-D01`. It authorizes only the
reversible scaffold implementation and a Draft PR. It does not authorize live
collection, rights decisions, credentials, real-data publication, or merge.
Record the result using `docs/codex/HANDOFF_TEMPLATE.md`; all later authority
must be written explicitly in `docs/codex/USER_DECISIONS.md`. Do not merge
KU-BO-014 under the development-only decision.
