# Validation Report

## Baseline

```text
COMMAND: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
RESULT: FAIL
TOTAL: 2243
PASS: 2242
FAILURES: 1
ERRORS: 0
DURATION_SECONDS: 601.170
```

Failure: the completed task's `EXPECTED_NEW_BRANCH` had become `main`, while the
strict test still expected `codex/kuwait-engine-integration-v1`. This is a
pre-existing control consistency failure, not evidence of a model, data, or
market-logic regression.

## Candidate focused validation

```text
CONTROL_VALIDATOR: PASS — 10 required files, 30 control text files, 0 errors
TARGETED_CONTROL/PARITY/LIFECYCLE TESTS: PASS — 57/57
SOURCE_EVIDENCE_LIFECYCLE TESTS: PASS — 30/30
JSON_PARSE: PASS
GIT_DIFF_CHECK: PASS
PRIVATE_DRIVE_LINK_SCAN: PASS
SECRET_GUARD: PASS
COMPILEALL: PASS
```

## Candidate full-suite progression

The first Stage 1 full run executed 2,272 tests in 510.706 seconds and correctly
failed with one error and one failure: the active task omitted two frozen legacy
migration markers, and a CLI test still expected fourteen resolved capabilities.
The markers were restored as historical references without changing the current
base or work branch, and the expected capability count was updated to fifteen.

The next full run passed 2,272/2,272 tests in 514.661 seconds. Review then found
that an invalid input row could be reflected in a quarantine report. The report
was changed to retain only bounded identifiers plus a SHA-256 digest, and a
negative non-reflection test was added.

```text
FINAL_COMMAND: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
FINAL_RESULT: PASS
TOTAL: 2273
PASS: 2273
FAILURES: 0
ERRORS: 0
DURATION_SECONDS: 490.736
```

## Dry-work and packaging

- Two independent synthetic reconciliation outputs were byte-identical.
- Status: `STRUCTURE_AND_RECONCILIATION_VALID_ONLY`.
- Evidence class: `SYNTHETIC_FIXTURE`.
- Report file SHA-256:
  `5ae248159d5e60a15184ffee978a3e1bd92e8faf5460ff8149fbbbc81f12125f`.
- Internal report SHA-256:
  `74514ea6d6fbf6b36f9a74de59582817720ddcc626bbf9aba8c01e8f9a954b5f`.
- Existing live dry-run replay remained fail-closed at
  `PROBE_AUTHORIZED_SOURCE_ACCESS`, with 10 receipts, zero candidates, and no
  sealed output.
- The first local wheel attempt failed because the test virtual environment did
  not contain `setuptools.build_meta`; it is recorded as an environment/setup
  failure. A corrected isolated build using the pinned build dependency passed.
- Final wheel SHA-256:
  `18054cfb35c547d78ca137dbf10ea38615ed9aedfb49127f9d46d466ded29cad`.
- Fresh-environment install, `validate-config`, and reconciliation CLI smoke: PASS.

The branch was later pushed without a PR or merge. Exact-head GitHub CI run
`33039583311` passed on Python 3.11 through 3.14 for head
`3a100ac220b7545e438dc0ee8afae2bbcf7da2c7`. These results prove software
behavior only, not real source access, company coverage, model training,
blind-test validity, market readiness, or investment performance.

## Stage 2 issuer universe and company dossier

```text
FOCUSED_COMPANY_DOSSIER_TESTS: PASS — 34/34
JSON_PARSE: PASS — 145 files
SCHEMA_METASCHEMA: PASS — 89 schemas
CONTROL_VALIDATOR: PASS
SECRET_GUARD: PASS
COMPILEALL: PASS
GIT_DIFF_CHECK: PASS
FULL_COMMAND: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
FULL_RESULT: PASS — 2307/2307
FULL_DURATION_SECONDS: 565.428
```

Two independent CLI dry runs on the Stage 2 examples were byte-identical:

- status: `STRUCTURE_VALID_ONLY`;
- evidence class: `SYNTHETIC_FIXTURE`;
- synthetic denominator: one issuer, one security, 21 expected/resolved fields;
- report file SHA-256:
  `569a22be51d9ba52c36f538253d831cfd220017aaa6cd218938d480e20d4d9e4`;
- internal report SHA-256:
  `8445a279acb562382795d7be7645f1248549ebcad2e358081975f954c6e4fba9`.

A fresh wheel was built and installed outside the checkout, then the new dossier
CLI completed successfully. Wheel SHA-256:
`86851b0f7bf284271b72fd683755e8f2aed1fa64d9eb54e86cf99c18454842f9`.

The fixture company is intentionally fictional and excluded from real coverage.
Stage 2 does not prove an exact Kuwait issuer universe, source admission, current
prices, training data, blind-test performance, or readiness for live research.

## Stage 3 official source access

```text
SOURCE/WORKFLOW FOCUSED TESTS: PASS — 110/110
ACCESS EXECUTOR TESTS: PASS — 7/7
INGESTION + EXECUTOR TESTS: PASS — 40/40
VALIDATE_CONFIG: PASS
CONTROL_VALIDATOR: PASS
SECRET_GUARD: PASS
COMPILEALL: PASS
GIT_DIFF_CHECK: PASS
FULL_COMMAND: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
FULL_RESULT: PASS — 2316/2316
FULL_DURATION_SECONDS: 617.951
```

The first KCC execution exposed a Python 3.12 `HTTPSConnection` compatibility
exception before network access. TLS context certificate and hostname checks
remain enabled; the obsolete forwarded keyword was removed and regression
tested. Connector exceptions are now converted into bounded audit receipts, and
a two-source test proves a failed source does not stop a readable sibling.

Two subsequent real, one-off, public capability probes were completed and
reopened successfully by the access validator:

- `kcc_maqasa_official`: `ERROR / ROBOTS_POLICY_UNAVAILABLE`, 0 artifacts;
- `boursa_reports_archive`: `ERROR / ROBOTS_POLICY_UNAVAILABLE`, 0 artifacts.

Both reports are `PASS_ACCESS_ONLY`: the pass means the failed attempts are
auditable, not that access succeeded. Market data, evidence, parsers, historical
coverage, and forecasts all remain false. Private bundles are outside Git.

An isolated wheel was built and installed, `validate-source-access-recipes`
passed from the installed command, and CLI help exposed
`execute-public-source-access-probe`. Wheel SHA-256:
`d5b13cac1c998c5b6884665883429776b27c7f88248d985231a46ab7a4e67aff`.

Post-documentation gates were rerun at `2026-08-27T05:07:48Z`. The first
focused command selected `pytest`, which is not installed in the isolated
runtime, and exited before collecting any test with `No module named pytest`.
The canonical repository runner was then used:

```text
COMMAND: PYTHONPATH=src .venv/bin/python -m unittest tests/test_ingestion.py tests/test_source_access_executor.py tests/test_source_access_recipes.py tests/test_source_network.py tests/test_research_workflow.py tests/test_kuwait_workflow_cli.py
RESULT: PASS — 109/109
CONTROL_VALIDATOR: PASS
SECRET_GUARD: PASS
COMPILEALL: PASS
GIT_DIFF_CHECK: PASS
```

Stage 3 receipt head `cfd0f4858f9fc3a0a35484b8dafa2bd8a60a0578`
subsequently passed exact-head GitHub CI run `33041621326` on Python 3.11,
3.12, 3.13, and 3.14. No PR was opened and no merge occurred.

## Stage 4 fail-closed Kuwait automation schedule

```text
SCHEDULE_CONTRACT: PASS
SCHEDULE_FOCUSED_TESTS: PASS — 13/13
SEVEN_SLOT_CONTRACT_DRY_RUNS: PASS — 7/7
OFFICIAL_HOLIDAY_NO_TRADE_DRY_RUN: PASS
MISSING_CONTROLS_EXIT_2_DRY_RUN: PASS
ACTIONLINT: PASS — 1.7.12, all workflows
ACTIONLINT_ARCHIVE_SHA256: 325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6
JSON_SCHEMA: PASS
CONTROL_VALIDATOR: PASS
SECRET_GUARD: PASS
COMPILEALL: PASS
GIT_DIFF_CHECK: PASS
FULL_COMMAND: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
FULL_RESULT: PASS — 2329/2329
FULL_DURATION_SECONDS: 621.603
```

The schedule SHA-256 is
`ac27b55b30465b80090762b86badf74c1b54e2d322066391007923f4b484d093`;
the workflow SHA-256 is
`89f77e55fc59a36f04979d0e02c4eae65fa973e30b8b88e24cefcd7ea12f8293`;
and its JSON Schema SHA-256 is
`58e5c6c15f717b2f18c77b05cd40d4943a3aebfc9e93b28b01ced54819a2e18f`.

A fresh wheel was built and installed outside the checkout. The installed module
reopened the repository schedule and workflow and returned
`PASS_SCHEDULE_CONTRACT`; wheel SHA-256 is
`28911ded022223a57436ddd619c48216bfa132209eb0d2b0fa1764054414b8cc`.

The 2026-08-27 market-open `EXECUTE` dry run returned
`MAINTENANCE_ONLY_NO_TRADE` because the date is in the official holiday list.
The enabled-but-missing-controls dry run exited 2. Every `CONTRACT_CHECK` run
kept collection, validation, and live scoring false. These results prove
schedule behavior only: market data, company/event coverage, model validation,
and candidate generation remain zero/false.

## Stage 5 immediate failover, evidence network, and recovery controller

```text
RECOVERY/ADVERSARIAL/CONTROLLER/WORKFLOW/SCHEDULE: PASS — 64/64
SOURCE_RESILIENCE/ORCHESTRATOR/QUALITY/RESEARCH_NETWORK/WORKFLOW: PASS — 88/88
SAUDI_DEFERRED_DESIGN_GATES: PASS — 2/2
WORKFLOW_YAML_PARSE: PASS — PyYAML 6.0.3
ACTIONLINT: PASS — all current workflows
SECRET_GUARD: PASS
GIT_DIFF_CHECK: PASS
```

Controlled recovery checks prove immediate failed-job reruns, a two-attempt cap,
stable fingerprint plus recomputed idempotency, duplicate-event suppression,
active-run suppression, missing-secret probes, deterministic-code gating,
security blocking, stale-lease safety, ZIP/path/symlink rejection, alert
deduplication, and a missed-event-only watchdog. No test disables provenance,
temporal, rights, or NO-TRADE gates.

Controlled source checks prove two fast transient attempts with jitter, immediate
fallback, 429 circuit behavior without critical-path sleep, hard-block adapter
disablement, parser/schema quarantine, source-role registry resolution,
field-level provenance/credibility, copied-news clustering, conflict abstention,
IndexSignal caps, and temporal leakage rejection.

Real evidence counts are unchanged: two prior source attempts, zero readable raw
artifacts, zero real observations, zero unique admitted events, zero training-
admitted records, and zero locked predictions. Consequently the research network
can only return `ABSTAIN`, and strict forecast remains `LOCKED`. Workflow
schedules are not active because the reviewed files have not reached the default
branch.

## Stage 6 Issue #24 Delta PRE-FLIGHT and priority checkpoints

The requested `gh issue view 24 --comments` command failed because GitHub removed
the Projects Classic `projectCards` GraphQL field. The issue and its one comment
were then read through the official REST API and recorded with content digests in
`workouts/2026-08-27/delta-preflight-issue-24.md`. No web instructions or code
were executed.

```text
PRIORITY/CHECKPOINT UNIT + ADVERSARIAL: PASS — 16/16
RECOVERY/LEASE UNIT + ADVERSARIAL: PASS — 35/35
CHECKPOINT POLICY SCHEMA: PASS
CHECKPOINT DOCUMENT SCHEMA: PASS
INCLUSIVE WINDOW: PASS — 2026-05-30..2026-08-27, 90 days
SYNTHETIC PREEMPT/RESUME: PASS — completed attempts [1,1], resumed attempt 2
CHAMPION MUTATION IN SYNTHETIC TEST: 0 bytes
COMPILE: PASS
SECRET_GUARD: PASS
GIT_DIFF_CHECK: PASS
```

The test-only atomic store reopens shard artifacts and validates SHA-256 before
completion, rejects path traversal and symlinks, uses generation/fencing CAS and
atomic writes, and resumes only non-completed shards. It is not proof of a
durable production backend. The trusted policy deliberately returns
`BLOCKED_CHECKPOINT_STORE`, and no scheduled backfill was executed.

CI run `33054455755` at recovery documentation head `bd17767` failed one release
metadata assertion after PyYAML was added for workflow parsing. Commit `ee07f00`
updates the locked expected test extras; its focused metadata tests pass 3/3 and
Secret Guard passes. Corrected CI run `33056375121` is still in progress.
Priority commit `3195ba7` is pushed; exact-head CI run `33056857748` is in
progress and therefore is not yet claimed as validated.

Evidence counts did not change in this stage: 2 source attempts, 0 readable
artifacts, 0 real observations, 0 unique admitted events, 0 training-admitted
records, and 0 locked predictions. No forecast, return, or investment-improvement
claim is made.

## Stage 7 rights-aware 90-day package and scheduler extension

Implementation commits:

- package/schema/runtime/tests: `e9d1a7fde8fde98d131c61c8aef97eb0619b6d0d`;
- backfill/recovery workflow extension: `85a9068d05b9c015d2044f78d0bdc9b1558d569e`.

```text
RIGHTS_AWARE_BACKFILL UNIT + ADVERSARIAL: PASS — 18/18
COMBINED BACKFILL/SCHEDULE/RECOVERY/LEASE/PRIORITY/WORKFLOW: PASS — 106/106
REAL RECEIPT BUNDLE REOPEN: PASS
JSON SCHEMA VALIDATION: PASS
WORKFLOW YAML PARSE: PASS
ACTIONLINT: PASS — 1.7.12
PRODUCTION BLOCKER DRY RUN: PASS — exit 2, no output created
COMPILE: PASS
SECRET_GUARD: PASS
GIT_DIFF_CHECK: PASS
```

The private non-Git audit package is named
`INCOMPLETE_RIGHTS_AWARE_RESEARCH_CONTEXT`; its reopened manifest digest is
`d5c07df65a7b80ed8a332b3e472eadfd6a7633a6718bff07e498b0ba14a96069`.
It covers the inclusive 2026-05-30 through 2026-08-27 plan: 11 trusted source
groups × 90 dates = 990 planned date shards. Two source attempts were audited,
both were blocked before fetch, 180 shards are blocked, 810 are unattempted, and
0 are completed. Readable artifacts, observations, provenance rows, unique
events, research-context rows, training candidates, and contradictions are all
zero.

The local schedule Dry Run resolved nominal time
`2026-08-27T04:23:00Z`, recorded actual start `2026-08-27T04:31:00Z`, and
therefore recorded a 480-second delay. It failed closed at
`BLOCKED_CHECKPOINT_STORE`; this is scheduling/gating evidence only.

Exact-head CI run `33059176971` passed package head `e9d1a7f` on Python 3.11,
3.12, 3.13, and 3.14. CI run `33060045908` passed workflow head `85a9068` on
the same four Python versions. A final local pre-commit rerun passed the 106-test
combined gate, 102/102 source/research/control/secret-unit tests, and standalone
Secret Guard. The schedules remain inactive because no reviewed workflow has
been merged to the default branch.

## Stage 8 security-by-security collection contract

The owner-directed correction is implemented at `security_code` grain. The
outer queue is deterministic, numeric-code ordered, and permits exactly one
active security. A security cannot release the next queue item until all 29
planned source attempts across seven waves have terminal receipts and the
security receipt has been sealed. Two securities issued by one company remain
two independent queue entries.

The issuer's official website is a mandatory per-security source. It is never
guessed from a company name: a positive or verified-zero result requires a
reopened HMAC-authenticated runtime trust registry binding issuer, security,
domain, validity interval, registry digest, and key ID. Licensed LSEG and
AlphaStocks results similarly require reopened entitlement/authority evidence.

```text
ISSUER_SEQUENTIAL_COLLECTION_TESTS: PASS — 26/26
SEQUENTIAL/SOURCE/CLI FOCUSED GATE: PASS — 84/84
RECOVERY/LEDGER REGRESSION GATE: PASS — 38/38
FULL_COMMAND: PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -q
FULL_RESULT: PASS — 2512/2512
FULL_DURATION_SECONDS: 855.702
COMPILEALL: PASS
STRICT_JSON: PASS — 170 files
SCHEMA_METASCHEMA: PASS — 107 schemas
CODEX_CONTROL: PASS — 31 control text files, 10 required files, 0 warnings/errors
LIVE_BOOTSTRAP: PASS_HANDOFF_CONTRACT
MIGRATION_CONTROL: PASS_PREPARATION_CONTROL
SMOKE: PASS — synthetic only
SECRET_GUARD: PASS
GIT_DIFF_CHECK: PASS
WHEEL_BUILD_INSTALL: PASS — 605602 bytes
INSTALLED_VALIDATE_CONFIG: PASS
INSTALLED_POLICY_VALIDATE: PASS_CONTRACT_NOT_EXECUTED
INSTALLED_PLAN/REOPEN: PASS_PLAN_NOT_EXECUTED — 1 synthetic security, 29 attempts
WHEEL_SHA256: f5536d4621081c269ca525e9e253491bc247e48ea214ef177f52dec11ecb6c13
EXACT_IMPLEMENTATION_HEAD: 48d139ca7d7f496228f2909b3c2549c6a5cd96ad
EXACT_PUSH_CI: PASS — run 33098426912, Python 3.11-3.14
EXACT_PR_CI: PASS — run 33098464383, Python 3.11-3.14
DRAFT_PR: #25
```

Adversarial validation rejects grouped execution, a second active security,
partial or replaced universes, source substitution, forged plan identities,
missing terminal receipts, replayed run/plan IDs, mutated authoritative flags,
untrusted issuer domains, and licensed positive results without entitlement.
The run validator proves internal receipt/hash-chain consistency only; it does
not authenticate raw artifacts or prove complete company coverage.

The hardened head also passes 37/37 source-quality/network tests and 41/41
combined market/source tests; it binds quality roles to the trusted registry and
normalizes malformed catalog failures. No network source was executed in this
stage. The repository still contains no
real complete Kuwait issuer/security universe, no populated official-domain
runtime registry, no admitted 29-source adapter set, and no security-aware
durable checkpoint v2. Real artifacts, observations, issuer dossiers, events,
training rows, predictions, and Drive publications remain zero. Exact
implementation-head CI passed and Draft PR #25 is open; merge is not performed.
