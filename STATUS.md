# KU-BO Master Execution Status

Updated: 2026-08-27T08:23:51Z (2026-08-27T11:23:52+03:00, Asia/Kuwait)

```text
RUN_ID: market-ai-20260827T020635Z-kuwait
MARKET: Kuwait
TASK: KU-BO-2026-08-27-DAY1
STAGE: STAGE_5_KUWAIT_RECOVERY_IMPLEMENTED_TESTED_PENDING_PUSH_CI
BASE_SHA: 93e4cab09915a4a4b58455d3cc45eb48be4bd499
WORK_BRANCH: codex/kuwait-market-ai-day1-v1
ROLLBACK_BRANCH: checkpoint/pre-market-ai-20260827-kuwait
WORKTREE_AT_START: CLEAN
STAGE_1_COMMIT: 23895a19f18f87ddb1f61489dd4bcef13fe6e88a
STAGE_2_COMMIT: 2a37ac81e440bd1ce609abdfab61993e118ccb57
STAGE_3_COMMIT: a64ad7c6996ecec354bbf02bfa0b7fcbc048c086
STAGE_4_COMMIT: 810b077cbd56267e897546237c3a354be3838f98
SOURCE_FAILOVER_COMMIT: 1309e52b6396c1ff6218d16d411dfc3d0d8d09a6
RESEARCH_REGISTRY_COMMIT: 9e6db2052b1f8c7a6db0363f1071cec924f72860
RESEARCH_MODE_COMMIT: bdbfb5c55a376f0976cfcf912066d310d88f0f55
RECOVERY_POLICY_COMMIT: cb4808a13489cad0c14e2e41622fdbdeb8644631
RECOVERY_CONTROLLER_COMMIT: 0170fa1549e32d29577aac5f9ef8f8528131247c
RECOVERY_WORKFLOWS_COMMIT: 94e384f297e53019df644312c99c8529deefd7df
```

## Completed and evidenced

- Read the 478-line master execution contract completely and bound this run to
  SHA-256 `2720a8778ade69a7d53a1ac5aa4a12c518ef4f845819601b662b0046773733d2`.
- Recorded operating system, disk, memory, network, tool versions, GitHub
  authentication, repository state, branches, remotes, open PRs, CI state,
  workflow state, and secret/variable presence without exposing credentials.
- Verified clean starting worktrees for both final repositories and all relevant
  local legacy/source checkouts.
- Created local rollback checkpoints for Kuwait and Saudi; no source checkout,
  branch, commit, PR, or user change was deleted or overwritten.
- Verified both contract-designated Drive project folders read-only. Each has
  the same 16 named subfolders. No Drive identifier is stored in this repository.
- Acquired the Termux wake lock. The current build remains in the existing tmux
  process; long-running periodic work is reserved for GitHub Actions.
- Established the Kuwait baseline in an isolated ignored virtual environment:
  2,243 tests ran in 601.170 seconds, with 2,242 passing and one pre-existing
  control-task/branch mismatch failing.
- Activated the strict day-one control surface on the actual work branch. The
  control validator, four focused control tests, JSON parsing, diff whitespace
  checks, private-Drive-link scan, and Secret Guard now pass.
- Completed an exact private-runtime repository audit and bound its sanitized
  public matrix to SHA-256
  `9f23680e65f60d3ffcea1d1c7ad6376aabd367b9cd46b3f68f47c0f4856836e5`.
- The private predecessor passed 937/937 tests and a clean secret scan; the
  private history source passed 48/48 from an isolated exact-HEAD clone; the
  archived Kuwait implementation passed 33/33. Every source worktree is clean.
- Published a staged integration plan. The first selected gap is canonical
  source-evidence lifecycle reconciliation; no bulk source merge is allowed.
- Reimplemented source-evidence lifecycle reconciliation inside canonical
  `kubo`, with strict input/report schemas and an exclusive-output CLI. It binds
  observations to permitted attempts, frozen bytes, parsers, timestamps, and an
  expected-cell denominator; rejects temporal leakage and blocked bytes; handles
  revisions, duplicates, conflicts, missing cells, parser drift, and source
  failures; and never authorizes fitting, backtesting, recommendations, or trades.
- Added a non-reflective quarantine boundary: rejected rows are represented only
  by bounded identifiers and a digest so rejected signed URLs or credentials are
  not copied into reports.
- Final candidate suite passed 2,273/2,273 tests in 490.736 seconds. The new
  lifecycle suite passed 30/30 tests, and control, migration-control, JSON,
  compile, whitespace, and Secret Guard checks pass.
- Repeated synthetic reconciliation produced byte-identical reports. File SHA-256
  is `5ae248159d5e60a15184ffee978a3e1bd92e8faf5460ff8149fbbbc81f12125f`;
  internal report SHA-256 is
  `74514ea6d6fbf6b36f9a74de59582817720ddcc626bbf9aba8c01e8f9a954b5f`.
- Built and installed the candidate wheel in a fresh temporary environment and
  ran `validate-config` plus reconciliation from outside the checkout. Wheel
  SHA-256 is `18054cfb35c547d78ca137dbf10ea38615ed9aedfb49127f9d46d466ded29cad`.
- Existing live dry work was replayed fail-closed with zero candidates and no
  sealed output because authorized source access is not configured. This is the
  expected `ABSTAIN / NO-TRADE` result, not live readiness.
- Stage 1 is preserved in commit
  `23895a19f18f87ddb1f61489dd4bcef13fe6e88a`; it has not been merged.
- Implemented Stage 2 effective-dated issuer-universe and company-dossier
  contracts above the existing identity/history foundation. The validator
  enforces exact security/issuer denominators, interval/ISIN/ticker collision
  checks, eight required dossier sections, point-in-time evidence, explicit
  missing cells and gaps, source-quality reconciliation, and immutable reports.
- Stage 2 focused tests pass 34/34. The full candidate suite passes
  2,307/2,307 tests in 565.428 seconds; 145 JSON files, 89 schemas, control,
  compile, whitespace, and Secret Guard gates pass.
- The repeated Stage 2 synthetic dry run produced byte-identical reports with
  status `STRUCTURE_VALID_ONLY`, one explicitly synthetic issuer/security, and
  21/21 synthetic fields. File SHA-256 is
  `569a22be51d9ba52c36f538253d831cfd220017aaa6cd218938d480e20d4d9e4`;
  internal report SHA-256 is
  `8445a279acb562382795d7be7645f1248549ebcad2e358081975f954c6e4fba9`.
- A fresh wheel/install/CLI smoke passed for the new command. Wheel SHA-256 is
  `86851b0f7bf284271b72fd683755e8f2aed1fa64d9eb54e86cf99c18454842f9`.
- Stage 2 is preserved in commit
  `2a37ac81e440bd1ce609abdfab61993e118ccb57`; it has not been merged.
- Pushed the work branch without opening a PR or merging. Exact-head GitHub CI
  run `33039583311` passed for head
  `3a100ac220b7545e438dc0ee8afae2bbcf7da2c7` on Python 3.11, 3.12, 3.13,
  and 3.14.
- Registered the official Kuwait Clearing Company surface as
  `kcc_maqasa_official` after verifying the public `maqasa.com` domain. The
  catalog now contains 69 definitions in 63 independence groups; capabilities
  remain 67 `DEFINED_ONLY`, 2 fixture-only `END_TO_END_TESTED`, and 0
  `LIVE_OPERATIONAL`.
- Added a one-off public source-access executor. It accepts only validated
  `PUBLIC_ACCESS_ONLY`/`HTTP_GET` plans, reserves a fresh output root before
  network access, enforces HTTPS/domain/robots/timeout/byte limits, sends no
  credentials, stores readable bytes content-addressed, reopens every receipt,
  and isolates per-source connector exceptions.
- The first real KCC command exposed a Python 3.12 TLS-handler compatibility
  defect before network access. The defect was fixed without weakening TLS
  hostname/certificate verification and is covered by a regression test.
- Two completed real one-off capability probes were executed: Kuwait Clearing
  Company and the Boursa Kuwait reports archive. Both receipts passed the
  access-only audit but ended `ERROR / ROBOTS_POLICY_UNAVAILABLE` with 0 raw
  artifacts. They prove bounded attempts and a blocker only; they do not prove
  source availability, market data, historical coverage, or collection.
- Stage 3 focused source/ingestion validation passes, and the full candidate
  suite passes 2,316/2,316 tests in 617.951 seconds. Config, control, compile,
  whitespace, Secret Guard, and installed-wheel CLI gates pass. Candidate wheel
  SHA-256 is
  `d5b13cac1c998c5b6884665883429776b27c7f88248d985231a46ab7a4e67aff`.
- Stage 3 is preserved in commit
  `a64ad7c6996ecec354bbf02bfa0b7fcbc048c086`; receipt head
  `cfd0f4858f9fc3a0a35484b8dafa2bd8a60a0578` passed exact-head CI run
  `33041621326` on Python 3.11 through 3.14. It has not been merged.
- Implemented a locked seven-slot Kuwait automation schedule: 15:00 daily and
  04:00, 07:00, 09:00 market-open, 11:00, 12:00, and 13:00 on Kuwait trading
  weekdays, converted respectively to 12:00, 01:00, 04:00, 06:00, 08:00,
  09:00, and 10:00 UTC.
- Bound the schedule to Boursa Kuwait's current official 09:00–13:00 continuous
  session, 13:15 trade-at-last end, Sunday–Thursday week, and the verified 2026
  holiday list. The 27 August 2026 market-open dry run produced
  `MAINTENANCE_ONLY_NO_TRADE` because today is an official holiday.
- Added the sequential `gate → collection → validation → live_scoring`
  workflow with one Kuwait concurrency group, job timeouts, bounded transient
  retry policy, actual execution timestamps, secret-presence booleans, pinned
  Actions, and permanent safety tripwires. The legacy 15:07/15:37 schedule is
  retained as manual-only compatibility so it cannot overlap.
- Stage 4 schedule tests pass 13/13; seven contract dry runs, the holiday dry
  run, and the expected missing-control exit-2 dry run pass. Actionlint 1.7.12,
  JSON/Schema, control, compile, whitespace, and Secret Guard checks pass.
- The full candidate suite passes 2,329/2,329 tests in 621.603 seconds. A fresh
  installed wheel revalidated the schedule contract; wheel SHA-256 is
  `28911ded022223a57436ddd619c48216bfa132209eb0d2b0fa1764054414b8cc`.
- Stage 4 remains intentionally disabled: `implementation_ready=false`, source
  admission is incomplete, required repository controls are absent, scheduled
  workflows run only from the default branch, and no PR or merge exists.
- Stage 4 is preserved in commit
  `810b077cbd56267e897546237c3a354be3838f98`; exact-head CI is pending.
- Replaced source-level waiting with immediate rights-aware failover. Timeout,
  DNS, and 5xx receive at most two quick attempts with jitter; 429 opens a
  source circuit and records `Retry-After` without blocking the critical path;
  access/policy blockers are not retried; parser/schema failures quarantine one
  adapter while sibling sources continue.
- Added the trusted research source registry, full observation provenance,
  field-level evidence credibility, copied-news origin clustering, and a
  conflict ledger that never averages contradictory prices. IndexSignal remains
  capped community discovery only.
- Split modes explicitly: `research_network` software is operational and
  currently returns `ABSTAIN` with zero real observations; `strict_forecast`
  remains locked because training, temporal validation, and the Blind Test have
  not occurred.
- Upgraded recovery incidents with recomputed idempotency keys, immediate due
  time, a two-attempt budget, existing safe lease/heartbeat/TTL controls, secret
  redaction, active-run suppression, and six-hour alert deduplication.
- Added the canonical Kuwait pipeline and recovery controller. A completed
  `workflow_run` uses GitHub's failed-jobs rerun endpoint immediately; a
  five-minute watchdog handles missed events only. Both workflows share one
  non-cancelling concurrency group and every Action is pinned to a full SHA.
- Recovery, adversarial, controller, workflow, and schedule suites pass 64/64.
  Source resilience, orchestrator, source-quality, research-network, and
  research-workflow suites pass 88/88. Saudi design-only gates pass 2/2.
  Actionlint and Secret Guard pass.
- Saudi runtime work did not start. Five review invariants are frozen in a
  design-only schema/config/test contract and remain blocked behind Kuwait's
  training, locked Blind Test, and measurement report.

## Next active stage

- Push the current branch and require exact-head CI, then read Issue #24 and all
  comments as binding additions. Perform Delta PRE-FLIGHT and extend the current
  modules with the requested priority/checkpoint/backfill layer; do not duplicate
  the source, provenance, or recovery systems.

## Not started or not yet evidenced

- Real Kuwait company collection: 0 verified companies.
- Historical event library: 0 admitted unique events.
- Training, validation, locked blind test, and before/after investment metrics.
- Live research candidates. Current output is `ABSTAIN / NO-TRADE`.
- Saudi implementation. It remains sequenced after Kuwait gates pass.
- Real research observations: 0. The implemented research network is software-
  operational but not live-evidence operational.

## Active blockers and safeguards

- Required GitHub Secrets and repository variables are absent in both final
  repositories. Scheduled collection/live workflows must remain disabled or
  fail closed until exact contracts are supplied and validated.
- Direct safe HTTP probes could not retrieve a usable robots policy from the
  KCC or Boursa reports hosts. No bypass, proxy credential, browser session, or
  alternate scraped route was used; both sources remain unadmitted.
- Existing migration control artifacts disagree: one catalog describes fourteen
  jobs as bound/reimplemented while the preparation manifest and parity matrix
  still say all fourteen are not started. Filesystem audit confirms canonical
  gaps, so predecessor migration completion is not claimed.
- Exact-head CI run `33041621326` passed for the Stage 3 receipt head, and Stage
  4 CI run `33043529715` passed at its reviewed head. The current recovery head
  has not yet been pushed or validated by exact-head CI; activation and merge
  remain forbidden.
- The official holiday contract is verified only through 2026. A later live
  slot fails closed if official calendar coverage is absent or stale.
- PRoot exposes phone storage through existing binds. All writes in this run are
  restricted to the project workspace; no external storage is used.
- Synthetic fixtures are software evidence only. No return, accuracy,
  improvement, recommendation, or profit claim is authorized.

See `workouts/2026-08-27/` for the dated evidence and `NEXT_ACTIONS.md` for the
ordered continuation.
