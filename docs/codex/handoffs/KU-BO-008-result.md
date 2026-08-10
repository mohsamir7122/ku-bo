# KU-BO-008 — Benchmark History, Official Complete Daily EOD, and Final Reconciliation

```text
FINAL_STATUS: BLOCKED
REPOSITORY: https://github.com/mohsamir7122/ku-bo
BASE_BRANCH: ops/codex-control-center-v0.1
STARTING_SHA: cba8fc1c57365343f497e1859733e0ae03087bfe
TASK_BRANCH: build/benchmark-official-eod-v0.2
FINAL_SHA: dfbf0e35a063b5ac8ce69421b4dc87343b702cd7
DRAFT_PR: https://github.com/mohsamir7122/ku-bo/pull/9
PR_BASE: ops/codex-control-center-v0.1
CI_RUN: https://github.com/mohsamir7122/ku-bo/actions/runs/31374698712
STARTED_AT: 2026-08-10 (Asia/Kuwait)
COMPLETED_AT: 2026-08-10T12:30:52+03:00
```

`FINAL_SHA` is the implementation/test commit verified by the cited four-version
CI run. The following publication-only commit records these immutable links and
does not change runtime, schema, test, or fixture bytes.

## User goal

Verify the live stacked repository state and implement KU-BO-008 through code, adversarial tests, packaging, push, and a Draft PR, while preserving evidence truthfulness and stopping only on a genuine evidence, licensing, or user-policy blocker.

## Verified starting state

- GitHub access was authenticated as `mohsamir7122`; the remote is `https://github.com/mohsamir7122/ku-bo`.
- The verified stack was Draft PR [#4](https://github.com/mohsamir7122/ku-bo/pull/4) → [#5](https://github.com/mohsamir7122/ku-bo/pull/5) → [#6](https://github.com/mohsamir7122/ku-bo/pull/6) → [#7](https://github.com/mohsamir7122/ku-bo/pull/7) → control-layer [#8](https://github.com/mohsamir7122/ku-bo/pull/8). All were open, mergeable, and had successful CI when orientation was performed.
- The live control head was `cba8fc1c57365343f497e1859733e0ae03087bfe`. It was 13 commits ahead of PR #7 head `570cfda...`, zero behind, with that exact merge base; therefore it was the safe stacked base required by `CURRENT_TASK.md`.
- Control CI run [31358400450](https://github.com/mohsamir7122/ku-bo/actions/runs/31358400450) passed Python 3.11–3.14. Python 3.11 reported `Ran 380 tests ... OK` and a passing Codex control-integrity check.
- The pre-edit CI-equivalent LF checkout collected 380 tests: 375 passed, 3 skipped, and 2 Windows-only symlink-creation errors (`WinError 1314`), with no assertion failures. The ordinary Windows checkout also exposed two environment deltas: missing external `tzdata` and `core.autocrlf=true` changing hash-bound LF fixtures. External `tzdata` and an LF checkout removed every delta except the two OS symlink-privilege errors.
- The task branch was created exactly as `build/benchmark-official-eod-v0.2` from the verified control SHA. `main` and all prior branches remained untouched.

## Changes made

### Benchmark History

- Added an effective-dated registry with internal requirement codes and explicit `BROAD_MARKET`/`SECTOR`, `PRICE_INDEX`/`TOTAL_RETURN_INDEX`, currency, units, rights, source access, and `UNVERIFIED_SEED` claim boundaries.
- Added non-overwriting workspace, strict manifest/import pipeline, normalized CSV contract, official-calendar and session-close reconciliation, import-time upper bound, source/hash binding, pagination/count checks, duplicate/gap/order/value validation, zero/unavailable states, and comparison eligibility reporting. Packet-local official labels remain `LIVE_DEPENDENT` without an artifact-bound external capture receipt.
- Added `benchmark_history` to the source/product capability catalog and a specialized PackValidator path. Unverified definitions and non-real classifications cannot enter readiness. Structural legacy packs cannot claim data or forecast readiness without the final data-foundation gate, even if packet-local fixture labels are rewritten.

### Official Complete Daily EOD

- Added a pipeline separate from `research_price_history`, with the exact declared security-code × official-session denominator and all six required trading states.
- Added explicit capture modes, effective-dated identity/status checks, exact normalized contracts, supplied-field declarations, OHLC/activity/state rules, pagination/count checks, provider disagreement quarantine, same-scope daily market-total reconciliation, and non-overwrite/hash/stale-upstream protections.
- Complete EOD now requires the complete official field set and observation after the official session close. A state-only source, fixture totals, self-authored real label, missing runtime authority, or saved-report/path tampering fails closed or remains partial. The authenticated runtime registry is necessary for sensitive-source authority/entitlement but cannot promote capture bytes; an artifact-bound external receipt is still required.
- Added strict schemas for workspace, normalized EOD, totals, import report, preserved evidence manifest, and independent validation report.

### Corporate actions, status, and final reconciliation

- Added a frozen-format outcome-session policy file that remains intentionally `UNFROZEN`; no civil-day rule or suspended/halted treatment was invented.
- Schema/runtime v1 reject every FROZEN value while D01 is OPEN. A committed
  global Option 1 is not approval; the calendar traversal used by adversarial
  tests is labeled an unapproved structural exercise only.
- Enforced that boundary in `ForecastLedger`, its CLI verifier, and
  `evaluate_forecasts`: caller chronology and hashes cannot validate a session
  horizon. Real ledger writes require an approved product-specific policy plus exact
  calendar/status resolution and artifact-bound official authority; default real
  evaluation also requires an independent final data-foundation receipt and emits
  no metrics while blocked. Explicit synthetic exercises remain
  `SYNTHETIC_CONTRACT_ONLY`, return `metrics=null` (no IC/return/Brier), are
  non-sealable, and are non-claiming.
- Removed validator bypass surfaces: real due validation requires the exact
  non-subclass authority type and an unbound validator call; the public forecast
  validator cannot disable authority. `IMPORTED`, `WITHDRAW`, and `EXPIRE`
  payloads are exact `{reason}` metadata, so forecast-field smuggling blocks
  append, revalidation, and sealing even after an attacker recomputes hashes.
- Joined each complete corporate-action factor/policy row by action ID, Security
  Code, Ticker, ISIN, and ex-date to effective identity, the official calendar,
  one status interval, in-window EOD, and compatible Benchmark basis. Unknown or
  conflicting identities block; legacy rows with no date remain explicit PARTIAL
  rather than receiving an invented date, and CA multipliers are forbidden on
  Benchmark series.
- Added one reproducible packet builder and one exact twelve-gate report. The reconciler rehashes conventional inputs and raw artifacts, checks upstream receipts, denominator/status/CA/benchmark/totals semantics, enforces evidence and rights classifications, and emits explicit READY/PARTIAL/BLOCKED states.
- Bound policy acceptance to the authoritative committed project file. Bound `RUNTIME_SECRET_GUARD` to the real Git top-level and scans exact blobs from `HEAD`, staged/index changes, and relevant worktree files rather than trusting a caller-selected clean directory. Report read/print rehashes the manifest, packet, and report and rejects forged READY reports, malformed nested fields, packet/report mismatches, and self-consistent rehashed READY forgeries. Persisted READY remains fail-closed until an independently authenticated final authority receipt contract exists.

### CLI, tests, CI, and documentation

- Added installed CLI commands for benchmark prepare/import, official EOD prepare/import/validate, final packet build, and final report print.
- Added strict JSON Schemas with standards-compliant local reference resolution, CSV contracts, unit/adversarial/integration tests, CI-specialized groups, LF attributes for hash-bound fixtures, Arabic operating documentation, and current-status/claim-boundary updates. All readiness-bearing schemas reject current READY until an independently authenticated artifact/final receipt contract is implemented.
- Declared `tzdata==2026.3` as a runtime dependency so installed wheels resolve `Asia/Kuwait` on Windows and minimal containers without system tzdb. CI now executes all seven new Data Foundation handlers from the force-reinstalled wheel instead of checking help text only.
- No model training, forecast, probability, recommendation, real backtest, or market-data capture was performed.

## Validation performed

```text
COMMAND_OR_JOB: python -m compileall -q src tests scripts
RESULT: PASS
DETAIL: Current merged task tree compiled successfully.
```

```text
COMMAND_OR_JOB: focused Benchmark/EOD/catalog/CLI/schema/adversarial groups
RESULT: PASS
DETAIL: The final independent A–E/session/ledger acceptance sweep ran 178 tests successfully with 4 Windows symlink-privilege skips and no P0/P1/P2 finding. The full reconciliation module alone ran 31/31 successfully; mandatory Draft 2020-12 schema validation ran 8/8 successfully.
```

```text
COMMAND_OR_JOB: $env:PYTHONPATH='src;tests'; python -m unittest tests.test_outcome_sessions tests.test_ledger tests.test_stopgates_evaluation tests.test_outcome_session_policy plus four focused D01 reconciliation regressions
RESULT: PASS
DETAIL: 43 tests ran successfully with 1 Windows symlink-privilege skip. Regressions cover UNFROZEN/D01 fail-closed behavior without deriving or disclosing an outcome date, exact non-overridable authority typing, weekend/holiday/suspension structural traversal, imported-event forecast-field smuggling, synthetic-ledger non-sealability, and withholding public evaluation performance metrics without an independently authenticated final authority receipt.
```

```text
COMMAND_OR_JOB: python -m unittest discover -s tests -v (ordinary Windows checkout)
RESULT: FAIL — documented checkout/OS delta, not accepted as final validation
DETAIL: Collected 513 tests: 495 passed, 7 skipped, 2 failed, and 9 errored. Nine failure/error outcomes (2 failures and 7 errors) came from core.autocrlf=true changing hash-bound tracked fixture bytes; the remaining 2 errors were Windows WinError 1314 symlink creation. The final authoritative run is performed in a fresh LF checkout and recorded below.
```

```text
COMMAND_OR_JOB: isolated wheel build/install plus scripts/installed_data_foundation_check.py
RESULT: PASS
DETAIL: A fresh Python 3.13 venv installed the built wheel and its declared tzdata dependency; kubo resolved from venv site-packages, not the checkout. prepare/import Benchmark, prepare/import/validate EOD, build final packet, and print final report all executed successfully; fixture stages remained PARTIAL/BLOCKED as required.
```

```text
COMMAND_OR_JOB: python scripts/smoke_check.py
RESULT: PASS
DETAIL: Synthetic source-network and legacy-contract smoke completed; no prediction was performed and synthetic/relabeled packets did not enter readiness.
```

```text
COMMAND_OR_JOB: python scripts/secret_guard.py
RESULT: PASS
DETAIL: No blocked secret pattern was found before publication.
```

```text
COMMAND_OR_JOB: $env:PYTHONPATH='src;tests'; python -m unittest discover -s tests -q (fresh detached LF worktree at 658ffe85c2520861990478556b5ca41abb3a2aec)
RESULT: ENVIRONMENT-LIMITED PASS
DETAIL: Ran 513 tests: 504 passed, 7 skipped, and 2 errored only because this Windows host denied the tests permission to create symlinks (WinError 1314). There were zero assertion failures, and the nine CRLF/hash failures from the ordinary checkout were eliminated.
```

```text
COMMAND_OR_JOB: GitHub Actions CI run 31374698712 at dfbf0e35a063b5ac8ce69421b4dc87343b702cd7
RESULT: PASS
DETAIL: All four contracts-and-tests jobs completed successfully on Python 3.11, 3.12, 3.13, and 3.14. Each job ran the full suite, specialized Benchmark/EOD/reconciliation/session gates, smoke and secret guards, and the repository-bound installed-wheel exercise.
```

## Evidence and data status

- Benchmark registry and code: `PARTIAL` / `LICENSED_FEED_DEPENDENT`. Definitions are internal unverified requirements, not provider codes or inception dates.
- Benchmark test data: `RECORDED_AUTHORIZED_FIXTURE` and `SYNTHETIC_ONLY`. It proves contracts only.
- Official EOD code: `PARTIAL`, with real execution remaining `LIVE_DEPENDENT` or `LICENSED_FEED_DEPENDENT` until an authorized export and an external authenticated capture receipt bind the exact artifact bytes; source/entitlement registry authentication alone is insufficient.
- Official EOD test data: `RECORDED_AUTHORIZED_FIXTURE` and `SYNTHETIC_ONLY`; it cannot promote Complete EOD readiness.
- Legacy official-foundation/status/CA inputs: `PARTIAL` for final real-evidence purposes because their current manifests do not carry hash-bound evidence-classification and rights authority.
- Final data-foundation state: `BLOCKED`. No rights-compatible real pilot packet was supplied and `KU-BO-008-D01` remains open.

## Claims allowed

- The branch implements strict, deterministic, non-overwriting Benchmark History and Official Daily EOD collection/import/validation contracts.
- The denominator, basis/scope, calendar, source/hash, status, corporate-action, totals, pagination, and final twelve-gate checks are covered by adversarial fixtures.
- Fixtures can demonstrate structural behavior only; saved statuses and caller-authored real labels are not accepted as independent evidence authority.
- The final reconciler correctly reports partial/blocked conditions for the current repository evidence state.

## Claims still forbidden

- Real backtest readiness: forbidden; the final real-evidence and outcome-policy gates do not pass.
- Forecast accuracy or prospective performance: forbidden; no model was trained or evaluated.
- Probability: forbidden.
- Recommendation or buy/sell signal: forbidden.
- Full-market coverage: forbidden; scope is a five-security pilot.
- `LIVE_OPERATIONAL` source status: forbidden; no real source capture was accepted by this task.

## Privacy and repository safety

```text
credentials or sessions: NO
private Drive IDs: NO
raw conversations: NO
real runtime market data: NO
licensed data: NO
destructive cleanup: NO
force push: NO
merge or auto-merge: NO
```

Only sanitized engineering requirements already represented by the active repository task were implemented. No private conversation import or runtime-data directory was committed.

## User decisions required

- `KU-BO-008-D01`: approve a product-specific maximum extension and terminal treatment for suspended/halted securities. Until then v1 remains `UNFROZEN`, rejects every FROZEN edit, and `CLAIM_BOUNDARIES` cannot pass for a real baseline backtest.

## Items classified for retention

```text
KEEP: benchmark registry/workspace/import contracts and schemas
KEEP: official EOD workspace/import/independent validation contracts and schemas
KEEP: final twelve-gate reconciliation and adversarial tests
KEEP: authoritative UNFROZEN outcome-session policy and KU-BO-008-D01
KEEP: Arabic operating and current-status documentation
PRIVATE_ONLY: any future real, licensed, authenticated, or runtime evidence packets
DELETE_CANDIDATE: None
```

## Known limitations and risks

- The Benchmark registry uses `KU_BO_INTERNAL` requirement codes and an unconfigured authorized feed. It deliberately cannot make a real comparison claim until provider definitions, effective dates, rights, and exports are verified.
- Current official identity is `CURRENT_SNAPSHOT_ONLY`; it cannot be backfilled before its snapshot date.
- Legacy upstream manifests lack independent evidence-classification/rights authority, so final READY cannot be inferred from old source IDs or review text.
- Official public or licensed EOD needs external authority appropriate to the source. For sensitive licensed sources, the HMAC-authenticated runtime registry is necessary during import and revalidation, but it only proves source/entitlement authority and is insufficient to prove capture bytes. An artifact-bound authenticated receipt remains an external blocker; secrets and tags are never copied into outputs.
- No independently authenticated final receipt/signature contract currently binds the final report, packet, component raw hashes, policy, and repository scan. Therefore readers and schemas intentionally reject persisted READY even when all packet-local hashes and labels are rewritten consistently.
- There is likewise no artifact-bound official receipt for the exact outcome
  calendar/status bytes. Structural CSV validation and caller manifest hashes are
  deliberately insufficient. A private test-only Option-1 calculator exercises
  weekend, holiday, suspended, and pre-close traversal; public validation never
  invokes it or emits a derived outcome date while D01 remains open.
- Windows without Developer Mode/admin symlink privileges cannot execute symlink-construction test branches locally; Linux CI exercises them.

## Smallest logical next task

```text
TASK_ID: KU-BO-009
PROPOSED_BRANCH: ops/freeze-outcome-session-policy-v0.1
DEPENDENCY: User decision KU-BO-008-D01 and this Draft PR stack
GOAL: Encode the selected product-specific suspended/halted outcome-session policy without adding market data or running a backtest.
ENTRY_GATE: KU-BO-008-D01 contains an explicit approved option, maximum extension, and terminal treatment.
EXIT_GATE: An approved decision receipt and versioned product-specific policy contract encode maximum extension and terminal treatment; holiday/suspension/halt/action tests pass; CLAIM_BOUNDARIES no longer reports the decision blocker for policy reasons alone.
```
