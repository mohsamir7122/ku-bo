# CURRENT TASK — KU-BO-008

```text
TASK_ID: KU-BO-008
STATUS: BLOCKED
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: ops/codex-control-center-v0.1
EXPECTED_NEW_BRANCH: build/benchmark-official-eod-v0.2
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
RESULT_PR: https://github.com/mohsamir7122/ku-bo/pull/9
RESULT_HANDOFF: docs/codex/handoffs/KU-BO-008-result.md
BLOCKED_ON: AUTHENTICATED_BENCHMARK_AND_EOD_RECEIPTS; KU-BO-008-D01
```

## Current result

Implementation is complete on `build/benchmark-official-eod-v0.2` and published in Draft PR #9. The task is now blocked only at the declared real-evidence, licensing, authenticated-receipt, and `KU-BO-008-D01` policy boundaries. Do not recreate the task branch or repeat KU-BO-008. Resume only through a newly approved recovery task or an explicit user decision that supplies the missing authority.

The implementation and validation record is `docs/codex/handoffs/KU-BO-008-result.md`.

## Mission

Take over the repository from the current control/development head, verify all prior work, and implement the next engineering stage:

```text
Benchmark History
+
Official Complete Daily EOD
+
Final Data Foundation Reconciliation
```

Continue through implementation, testing, failure analysis, fixes, documentation, push, and Draft PR creation. Do not stop merely because the task is large. Stop only for a genuine external dependency, credentials/licensing requirement, destructive choice, or unresolved user decision.

## Phase 0 — Orientation and proof before edits

1. Confirm GitHub access to `mohsamir7122/ku-bo`.
2. Fetch all relevant branches and open PRs.
3. Verify live state of PRs #4, #5, #6, #7, and the control-layer PR if present.
4. Confirm the live HEAD SHA of `ops/codex-control-center-v0.1`.
5. Read, in order:
   - `AGENTS.md`
   - `CODEX_START_HERE.md`
   - `docs/codex/PROJECT_RULES.md`
   - `docs/codex/CURRENT_STATUS.md`
   - this file
   - `docs/codex/ACCEPTANCE_GATES.md`
   - `docs/codex/CONVERSATION_IMPORT_POLICY.md`
   - `docs/codex/USER_DECISIONS.md`
6. Inspect current CI and run the full local suite before editing.
7. Record the verified starting branch, SHA, PR chain, test count, and any drift from this handoff.
8. If the control branch no longer represents the latest approved development head, do not guess. Choose the verified safe base, record why, and keep the new PR dependency explicit.

## Branch strategy

Create:

```text
build/benchmark-official-eod-v0.2
```

from the verified active control/development head.

Do not edit `main`. Do not merge any stacked PR. Do not delete prior branches.

## Deliverable A — Benchmark History

Build a strict, evidence-bound benchmark pipeline for the five-security pilot and future expansion.

At minimum, add:

- a benchmark registry that identifies benchmark code, name, currency, provider/source, calculation basis, and effective dates;
- a workspace generator for authorized official or licensed benchmark exports;
- a raw manifest with SHA-256, source URL, observed time, rights/allowed-use status, window, row count, and review status;
- a normalized benchmark-history contract;
- explicit distinction between price index, total-return index, sector benchmark, and broad-market benchmark;
- complete trading-date reconciliation against the official calendar;
- duplicate, gap, unit, currency, monotonic-time, and impossible-value validation;
- no forward fill and no invented benchmark rows;
- a zero-result or unavailable state that fails closed rather than substituting another index silently;
- report and schemas that state exactly which benchmark comparisons are possible.

Do not call a price index a total-return benchmark. Do not use the same benchmark for every product unless the product contract explicitly permits it.

## Deliverable B — Official Complete Daily EOD

Build an Official Complete Daily EOD pipeline separate from `research_price_history`.

The contract must represent every eligible security-session denominator and distinguish:

```text
TRADED
NO_TRADE
SUSPENDED
HALTED
TRADED_THEN_SUSPENDED
NOT_LISTED_OR_NOT_ELIGIBLE
```

Requirements:

- use official `security_code` and effective-dated identity; ticker-only joins remain invalid;
- use the official trading calendar;
- use historical status intervals when available;
- create exactly one row for every eligible security and official trading session inside the declared window;
- preserve non-traded rows without synthetic OHLC;
- reject positive activity on non-traded rows;
- require OHLC, volume, value traded, and trade count only when the official source supplies them;
- never derive official `trade_count`, `value_traded_kwd`, `reference_price_fils`, or trading status from incomplete secondary data;
- bind every normalized row to resolvable raw evidence hashes;
- declare price unit and currency explicitly;
- declare raw versus officially adjusted basis explicitly;
- reconcile daily market totals where official totals are available;
- quarantine provider disagreements rather than picking the convenient value;
- support partial source availability without allowing a complete-EOD claim.

If the public official source does not expose enough fields reliably, build the licensed/import workspace and leave the stage blocked on evidence. Do not scrape around access controls or fabricate missing official fields.

## Deliverable C — Corporate-action and status integration

Integrate, without conflating:

- `corporate_action_factor_ledger.csv`;
- `corporate_action_return_policy_queue.csv`;
- historical `status_intervals.csv`;
- current identity and calendar;
- official EOD and benchmark rows.

Rules:

- reference-price factor is not automatically the investor-return multiplier;
- normal cash dividends use raw prices plus a separate cash component in total-return evaluation;
- rights issues remain blocked until exercise/sale/lapse policy is frozen;
- complex actions with pending factors block affected outcomes;
- suspended or halted sessions must not be treated as ordinary missing prices;
- outcome dates must advance according to the frozen product policy and official sessions, not civil-day arithmetic;
- a current snapshot may not backfill historical status.

## Deliverable D — Final Data Foundation Reconciliation

Create one reproducible command and one final gate report that reconcile the pilot packet.

The final gate must include at least:

```text
POINT_IN_TIME_IDENTITY
TRADING_CALENDAR
SECURITY_STATUS_HISTORY
PRICE_DENOMINATOR
PRICE_EVIDENCE
PRICE_CORPORATE_ACTION_QA
BENCHMARK_HISTORY
BENCHMARK_EVIDENCE
MARKET_TOTAL_RECONCILIATION
QUERY_AND_PAGINATION_COMPLETENESS
RUNTIME_SECRET_GUARD
CLAIM_BOUNDARIES
```

Possible top-level statuses must be explicit, such as:

```text
DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST
DATA_FOUNDATION_PARTIAL
DATA_FOUNDATION_BLOCKED
```

`DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST` is allowed only when every critical gate passes on real, non-synthetic, rights-compatible evidence for the declared pilot window.

The gate report must distinguish:

```text
PROVEN_REAL_EVIDENCE
RECORDED_AUTHORIZED_FIXTURE
SYNTHETIC_ONLY
PARTIAL
BLOCKED
LIVE_DEPENDENT
LICENSED_FEED_DEPENDENT
```

Do not use synthetic fixtures to promote readiness.

## Deliverable E — CLI, schemas, tests, and docs

Add or extend installed CLI commands for:

- preparing benchmark workspace;
- importing benchmark evidence;
- preparing official EOD workspace;
- importing official EOD evidence;
- validating denominator and totals;
- building the final data-foundation packet;
- printing the final gate report.

Add strict JSON Schemas and CSV contracts.

Add unit, adversarial, integration, stale-upstream, hash-mismatch, symlink, non-overwrite, pagination, zero-result, denominator, corporate-action, benchmark-basis, and installed-wheel tests.

Update Arabic operating documentation while keeping technical identifiers in English.

## Conversation and documentation migration

The private Drive folder may contain previous conversations or command documents. Follow `CONVERSATION_IMPORT_POLICY.md`.

You may:

- extract a sanitized technical decision or requirement that is not already represented;
- place it in a concise repository handoff, ADR, rule, or task note;
- classify duplicate or stale material for archive.

You may not:

- commit raw chat transcripts;
- commit personal, medical, relationship, employment, email, or unrelated information;
- permanently delete Drive conversations or repository documents without a recorded user decision;
- let an old conversation override current contracts or the active task.

Put every proposed deletion or ambiguous keep/archive decision in `docs/codex/USER_DECISIONS.md`.

## Required validation loop

Run targeted tests after each coherent unit. Before handoff, run all of the following or the repository-equivalent commands:

```text
compileall
complete unit and adversarial suite
all specialized data-foundation gates
synthetic smoke check
secret_guard
wheel build
wheel reinstall
installed kubo commands
installed kubo-data-foundation commands
```

Inspect and fix failures caused by the branch. Do not merely rerun the same failing command.

## Completion and publication

When the implementation is coherent and tests are green:

1. inspect the complete diff and exclude unrelated files;
2. commit intentionally;
3. push the task branch;
4. open a Draft PR against the verified correct stacked base;
5. include exact claims, non-claims, tests, CI, source dependencies, and remaining gates;
6. write a completed handoff using `docs/codex/HANDOFF_TEMPLATE.md` under:

```text
docs/codex/handoffs/KU-BO-008-result.md
```

7. update `docs/codex/USER_DECISIONS.md` only for decisions genuinely requiring the user;
8. do not merge.

## Final non-claims

This task does not authorize:

```text
model training
forecasting
probability output
buy/sell recommendations
live trading
full-market claim
headline accuracy
real backtest unless the final real-evidence gate passes
```
