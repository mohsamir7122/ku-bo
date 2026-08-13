# CURRENT TASK — KU-BO-012

```text
TASK_ID: KU-BO-012
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: 92b2bdd2460a7508922297a12d85f13264d43acb
EXPECTED_NEW_BRANCH: agent/kuwait-120d-next-session
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
APPROVED_MERGE_DECISION: KU-BO-MERGE-004
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
HISTORICAL_EVALUATION_REQUESTED: YES
BLOCKED_ON: REAL_POINT_IN_TIME_DATA; FULL_UNIVERSE_RECONCILIATION; OUTCOME_SESSION_POLICY; EXTERNAL_PUBLICATION_TOOLING
```

## Mission

Build a fail-closed Kuwait-market research and next-session evaluation layer
that can:

- maintain a rolling 120-day Kuwait context corpus;
- query many independent public-source families in bounded waves;
- preserve every attempt, empty response, access denial, retry, and recovery;
- reopen and rehash persisted search reports, attempt ledgers, and raw artifacts
  before any parser-to-research integration;
- distinguish official facts from news, community sentiment, and search routing;
- map dated events to securities through explicit exposure evidence;
- compute versioned factors for every security in the frozen eligible universe;
- rank or abstain without treating missing information as a reason to stop the run;
- audit the last 40 completed official sessions only when point-in-time inputs,
  outcomes, Corporate Actions, and the full denominator are admissible.

The user requested implementation, integration, branch reconciliation, and a
40-day retrospective result. This authorizes development and an evidence-gated
historical evaluation. It does not authorize invention of missing market data,
publication of licensed/private bytes, weakening of gates, model training, or
presenting zero scoreable observations as a zero-percent result.

## Branch and merge state

The task branch is based on merged `main@92b2bdd2460a7508922297a12d85f13264d43acb`.
PR #1 and PRs #4 through #13 are already ancestors of `main`; they require no
additional merge. PR #2 and PR #3 are 127 commits behind, non-mergeable, and
explicitly superseded by the current stack. Do not merge or wholesale
cherry-pick them. Reimplement a useful idea from them only if it satisfies the
current contracts and tests.

Do not merge this task branch until the complete suite, installed-wheel checks,
real-evidence stop gates, Draft PR review, and exact-head GitHub Actions pass.
The recorded approval in `docs/codex/USER_DECISIONS.md` is conditional and does
not change `MERGE_ALLOWED: NO` during implementation.

## Required product contract

The product ID is `KUWAIT_120D_NEXT_SESSION_RESEARCH`.

Use separate windows:

```text
CONTEXT_LOOKBACK: 120 calendar days
ACTIVE_EVENT_LOOKBACK: 30 calendar days
COMMUNITY_SENTIMENT_LOOKBACK: 7 calendar days
FRESH_CATALYST_LOOKBACK: 72 hours
PRIMARY_OUTCOME_HORIZON: next completed official trading session
```

The 120-day corpus is incremental. A normal run updates it and records its
watermark; it must not redownload four months from every source for every user
question.

## Source-search requirements

1. Treat “50 sites” as up to 50 distinct registrable domains attempted, not as
   50 independent confirmations.
2. Query sources in waves: official/regulatory first, issuer and government
   next, reputable news and market-data support next, community/search routing
   last.
3. Retry transient timeout, DNS, TLS, HTTP 429, and HTTP 5xx failures up to
   three bounded attempts with backoff and `Retry-After` handling.
4. For a valid but empty response, try up to four materially different query
   strategies. Repeating the same URL four times does not count.
5. Do not bypass robots, CAPTCHA, paywalls, authentication, Telegram access
   controls, or explicit HTTP denial. Record the exact status and recovery
   action instead.
6. Preserve an append-only attempt ledger containing request strategy, source,
   timestamps, status, final URL, error class, response hash, and outcome.
7. Deduplicate syndication and reposts by origin/content hash before counting
   independent evidence.
8. Telegram and IndexSignal are community-sentiment or routing sources only;
   they cannot establish official identity, price, Corporate Action, or a
   factual catalyst by themselves.
9. Missing information degrades coverage/confidence or produces an abstention;
   it does not abort unrelated securities or the whole market run.
10. A persisted Source Search run must pass a fresh report/ledger/raw-byte
    validation before integration. The parsed-input bridge may bind supplied
    events, exposures, factors, dispositions, and scores to verified bytes, but
    it must never invent them from a raw capture.

## Event, exposure, and factor requirements

Normalize dated events into `KUWAIT_MACRO`, `SECTOR`, or `SECURITY` scope.
Every security link must be one of:

```text
DIRECT_NAMED
CONTRACT_COUNTERPARTY
SECTOR_EXPOSURE
INFERRED_EXPOSURE
UNRESOLVED
```

Preserve evidence, cutoff time, confidence, and contradiction status for every
link. Run versioned factors over the full frozen universe, including official
price/momentum, liquidity, volatility, disclosures, Corporate Actions,
security status, sector/market regime, event exposure, and bounded community
sentiment. A factor may be `MISSING` or `NOT_APPLICABLE`; it may not fabricate a
neutral numeric value.

Bind the complete canonical Factor Snapshot—including every row, factor,
evidence hash, disposition, and score—to `factor_snapshot_sha256`, and derive
`snapshot_id` from it. Enforce each registry window against factor
`available_at` and `decision_at`, including a current 24-hour status window.
`SUPERSEDED` events must not feed factor-eligible exposure.

Produce one denominator row per eligible security and decision cutoff. Every
row must be selected, rejected, abstained, or unresolved with its first failed
stage and reason.

## Historical evaluation contract

Interpret the requested forty-day test as the latest 40 completed official
trading sessions for the next-session product. Also report the corresponding
calendar date span. If fewer than 40 scoreable sessions exist, preserve the
available count and return `STOP_BACKTEST` without metrics.

Freeze the protocol before opening outcome prices. The primary label is the
Corporate-Action-adjusted gross close-to-close return above zero, before
execution costs. Actionable net-up plus market- and sector-net-excess labels
apply the recorded entry/exit, fees, spread, and slippage separately. Use point-in-time universe membership,
status, Corporate Actions, executable prices, benchmark, and decision-time
features. Never use future news, revised filings, current membership, or later
prices in earlier snapshots.

This is an execution-grade product. Derive rank deterministically from score
descending and Security Code ascending, select exactly Top-K, and require a
verified `FILLED` execution for every selected row. Keep non-trading securities
in the denominator. While `KU-BO-008-D01` is open, a non-trading outcome stops
the backtest rather than advancing the horizon, dropping the row, or creating a
synthetic close.

Required run outcomes:

```text
PASS_BACKTEST
STOP_BACKTEST
```

`STOP_BACKTEST` applies to missing/unsealed forecasts, unresolved leakage,
unreconciled denominator, failed market-data or Corporate Action QA, or zero
process-valid observations. The replay does not advertise an unreachable
`STOP_INFERENCE` state. `STOP_BACKTEST` is not an accuracy percentage.

Only after all gates pass may the report calculate the predeclared agreement
rate, coverage, abstention rate, precision/recall, benchmark-relative outcomes,
and uncertainty. Forty sessions are a pilot, not prospective validation.

## Acceptance gates

1. Versioned Schemas/configuration cover source attempts, query strategies,
   persisted-run validation, parsed integration inputs, context events,
   exposure links, factor snapshots, denominator rows, and the 40-session
   evaluation report.
2. Multi-wave collection and bounded retry/empty-result behavior have unit,
   integration, adversarial, and chaos tests.
3. The source catalog never promotes a connector or parser beyond observed
   evidence; `DEFINED_ONLY`, `RECORDED_FIXTURE_ONLY`, `LIVE_DEPENDENT`, and
   `LIVE_OPERATIONAL` remain distinct.
4. Every enabled security receives a deterministic factor and disposition row
   without aborting on a different security's missing source; complete snapshot
   content and freshness are revalidated against its registry.
5. Telegram/IndexSignal failures are preserved and do not become factual
   confirmations or total-run blockers.
6. The evaluation runner is leakage-safe, uses 40 decisions over 41 official
   sessions, derives rank/Top-K deterministically, enforces execution evidence,
   reconciles the full denominator, and emits an explicit stop result when
   evidence or the non-trading outcome policy is incomplete.
7. Complete tests, compile, Schema checks, control check, smoke, secret guard,
   wheel build, isolated reinstall, and installed CLI exercise pass.
8. A sanitized result is written from `docs/codex/HANDOFF_TEMPLATE.md` to
   `docs/codex/handoffs/KU-BO-012-result.md`.
9. Draft PR exact-head CI passes before any merge-boundary review.

## Safety and non-claims

- Real market bytes and private Telegram/session material remain outside Git.
- Search snippets are routing aids, not final evidence.
- Public page reachability is not connector support or evidence qualification.
- A deterministic score is not a probability or a recommendation.
- No claim of full-market coverage, accuracy, or `REAL_BACKTEST_READY` is
  permitted until the real-evidence gates pass.
- Keep `KU-BO-008-D01` open unless a separately approved outcome-session policy
  resolves it.
- Use `docs/codex/HANDOFF_TEMPLATE.md` and record decisions in
  `docs/codex/USER_DECISIONS.md`.
