# CURRENT TASK — KU-BO-015

```text
TASK_ID: KU-BO-015
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: 59833bf73510b3aa3901f628cbf2c13c0d01cf79
EXPECTED_NEW_BRANCH: agent/ku-bo-015-source-access-recipes
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
LIVE_SOURCE_COLLECTION_REQUESTED: NO
BLOCKED_ON: LIVE_SITE_PROBES; SOURCE_RIGHTS_OR_ENTITLEMENT; RUNTIME_AUTHORIZATION; OFFICIAL_FULL_UNIVERSE_DATA
```

## Mission

Translate the reviewed Kuwait-source access lessons into a strict, machine-readable
recipe registry and a hash-bound capability-probe planning workflow. Reuse the
existing live access receipt and manual Investing export importer. Do not create a
parallel source network, run the sites, or promote any source capability.

## Acceptance gates

1. A strict recipe registry binds each covered source to a registered access mode,
   capture method, purpose, frequency, rights status, stop reasons, and budget.
2. Public systematic collection and non-display or execution use with public-only
   rights fail closed.
3. Plans are deterministic, no-overwrite, `PLANNED_NOT_EXECUTED`, and bound to the
   exact recipe registry SHA-256 and source-catalog Start URL.
4. A combined validator revalidates the existing raw-hash-bound probe, requires the
   exact planned source set and window, and requires controlled reasons for blocked,
   authentication-required, or error states.
5. A valid blocked receipt may prove the access-state audit contract only; no recipe,
   plan, or probe becomes market evidence, historical coverage, or live capability.
6. The existing Investing importer is registered with a hard
   `PRICE_IMPORT_READY_ONLY` promotion ceiling.
7. JSON Schemas, adversarial tests, CLI commands, Arabic documentation, and control
   records are included.
8. Compile, targeted and complete tests, smoke, control, Secret Guard, strict JSON
   and Schema validation, wheel build/install, installed CLI, and exact-head CI pass.
9. A sanitized handoff and Draft PR are published from the expected branch.

## Safety and non-claims

- No network collection, credentials, cookies, sessions, private Drive IDs, or real
  market data may enter this task.
- No source is promoted in `config/source_capabilities.json`.
- No connector, parser, official EOD, execution tape, full-market coverage, backtest,
  forecast, probability, accuracy, recommendation, or `LIVE_OPERATIONAL` claim is
  created.
- Sources without a registered Start URL or rights path remain uncovered.

Do not merge this task. Record any later authority in
`docs/codex/USER_DECISIONS.md` and write the result using
`docs/codex/HANDOFF_TEMPLATE.md`.
