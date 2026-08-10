# KU-BO Codex Acceptance Gates

These gates apply to every Codex task unless the active task defines stricter requirements.

## Gate 1 — Repository orientation

Pass only when the handoff records:

- repository and remote;
- verified base branch and starting SHA;
- open stacked PR chain and dependencies;
- current CI state;
- clean or intentionally scoped working tree;
- active task ID.

## Gate 2 — Scope integrity

Pass only when:

- changed files are within the active task;
- unrelated user changes are not staged;
- no old prompt or private conversation expanded the task silently;
- no acceptance criterion was weakened to make the branch pass;
- the PR base preserves the stacked dependency.

## Gate 3 — Privacy and secret safety

Pass only when:

- `secret_guard` passes;
- no credential, cookie, token, session, signed URL, private Drive ID, or browser profile is committed;
- no raw private conversation or personal correspondence is committed;
- no licensed or confidential dataset is committed without explicit rights and task authorization;
- runtime evidence remains under ignored local/private storage.

## Gate 4 — Evidence integrity

Pass only when every accepted normalized fact:

- resolves to raw evidence bytes and SHA-256;
- identifies source and capture time;
- uses official identity or effective-dated binding;
- distinguishes primary from supporting evidence;
- records query/pagination completeness where relevant;
- rejects parser drift, access blockers, and unreviewed zero results;
- does not silently substitute another provider.

Synthetic and recorded fixtures may prove code contracts only. They may not promote real-data readiness.

## Gate 5 — Temporal integrity

Pass only when:

- no feature, status, identity, event, price, benchmark, or action term is available before its real availability time;
- current snapshots are not copied backward;
- training/evaluation logic uses causal time ordering;
- official sessions, suspensions, halts, and corporate actions determine outcome windows;
- no civil-day shortcut replaces session-based horizons.

## Gate 6 — Denominator completeness

Pass only when the declared scope reconciles:

- expected securities;
- expected official sessions;
- one explicit state per eligible security-session;
- no duplicate or missing security-session keys;
- no survivorship substitution;
- no silent omission of non-traded, suspended, or halted sessions.

A named-security pilot must not be described as full market.

## Gate 7 — Price and benchmark quality

Pass only when:

- units and currency are explicit;
- raw and adjusted bases are not mixed;
- OHLC constraints pass;
- non-traded rows contain no synthetic OHLC or positive activity;
- official fields are not derived and relabeled as official;
- benchmark type is explicit: price, total return, sector, or broad market;
- benchmark dates reconcile to the official calendar;
- market totals reconcile where the source provides them;
- conflicts are quarantined or blocked.

## Gate 8 — Corporate-action and status integrity

Pass only when:

- action schedule identity matches official Security Code, Ticker, and ISIN;
- action type and terms come from reviewed official disclosure evidence;
- reference-price factor, continuity factor, quantity multiplier, return multiplier, and cash component remain distinct;
- rights and complex actions remain blocked until their return policy is frozen;
- status history has opening evidence, complete query receipts, valid transitions, and current-snapshot reconciliation;
- affected outcomes are blocked when factors or status intervals are incomplete.

## Gate 9 — Test and package integrity

Before publication, pass:

```text
compileall
full unit/adversarial suite
all task-specific gates
synthetic smoke check
secret_guard
wheel build
wheel reinstall
installed CLI exercise
```

The handoff must report exact commands and results. A skipped check must have a concrete reason and impact.

## Gate 10 — Claim boundaries

The PR and reports must say what is:

```text
PROVEN
PARTIAL
BLOCKED
SYNTHETIC_ONLY
RECORDED_FIXTURE_ONLY
LIVE_DEPENDENT
LICENSED_FEED_DEPENDENT
USER_DECISION_REQUIRED
```

Do not claim:

```text
REAL_BACKTEST_READY
PROSPECTIVE_VALIDATED
LIVE_OPERATIONAL
probability
recommendation
accuracy
full-market coverage
```

unless the corresponding real-evidence gates pass.

## Gate 11 — Publication safety

Pass only when:

- branch is pushed without force;
- Draft PR is opened against the correct base;
- PR body documents dependencies, tests, claims, and non-claims;
- no merge or auto-merge occurs;
- a handoff result is written;
- deletion candidates and user decisions are recorded rather than executed.

## Final decision

A task is `COMPLETED` only when all applicable gates pass.

Use `PARTIAL` when useful work is valid but one or more noncritical deliverables remain incomplete.

Use `BLOCKED` when a critical evidence, privacy, denominator, temporal, test, or user-decision gate fails.
