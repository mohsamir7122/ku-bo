# KU-BO Current Codex Status

Status date: 2026-08-12

Repository:

```text
mohsamir7122/ku-bo
```

## Verified live base

```text
branch: main
head: be5fe3883016dedf07fa680905f7199f3906b4d8
latest merged task: PR #9 / KU-BO-008
GitHub Actions: run 31402435102 / PASS
starting local suite: 513 tests / PASS
```

PRs #4 through #9 are now merged into `main`; the old stacked-PR snapshot is
historical. Open Draft PRs #2 and #3 branch from an older base, are not mergeable
with the current head, and must not be used as the KU-BO-009 base.

## Proven on main before KU-BO-009

- strict source, identity, time, evidence, rights, and claim-boundary contracts;
- research-price, official-identity/calendar, status/corporate-action,
  status-history, Benchmark, and Official Complete EOD workspaces/importers;
- final twelve-gate Data Foundation reconciliation;
- append-only research and outcome ledgers;
- broad unit/adversarial coverage, smoke checks, secret guard, and wheel tests.

## Material audit defect found on main

`kubo-data-foundation import-status-history` passed an undefined
`args.imported_at` to a function that has no such parameter. The complete suite
did not exercise this installed CLI dispatch. KU-BO-009 removes the invalid
argument and adds a regression test against the actual function contract.

## KU-BO-009 published for review

Task branch:

```text
build/tri-security-pilot-v0.3
implementation head: 0c4d5a6b71137ec5719195ea749ed9bedf863a72
Draft PR: https://github.com/mohsamir7122/ku-bo/pull/10
GitHub Actions: run 31571590903 / PASS (Python 3.11-3.14)
final local suite: 528 tests / PASS
isolated installed-wheel exercise: PASS / 12 handlers
```

The branch adds a staged `DATA_QUALIFICATION_ONLY` registry and workspace. Each
batch has exactly three unique `security_code`/Ticker/ISIN candidates. Batch one
is KFH, SHIP, and AZNOULA. Every identity remains `UNVERIFIED_SEED`; preparation
creates no real evidence and all twelve gates remain
`PENDING_EXTERNAL_EVIDENCE`.

The related repository audit has established that `mohsamir7122/Research` is
not a valid source for scores, forecasts, recommendations, or backtest results.
Its open Factor9 implementation contains look-ahead bias, missingness/confidence
errors, and fabricated fundamentals. Only bounded engineering test ideas may be
rewritten against KU-BO contracts.

KU-BO-009 is complete as an engineering and preparation stage. It did not
collect real market bytes or qualify the first batch. The smallest next stage
is a plan/window/cohort receipt binding every downstream component; no later
batch is authorized by this result.

## Still not proven

- complete effective-dated historical market universe;
- real rights-compatible Benchmark and Official Complete EOD packets;
- complete historical Corporate Actions and suspension/resumption evidence;
- authenticated capture receipts and an independent final authority receipt;
- an approved product-specific outcome-session policy for `KU-BO-008-D01`;
- real baseline-backtest readiness;
- forecast skill, probability calibration, or prospective accuracy;
- any trading recommendation or production execution readiness.

## Active instruction

The only active task is:

```text
docs/codex/CURRENT_TASK.md
```

Historic handoffs and repository audits are context, not authority to weaken
the current gates.
