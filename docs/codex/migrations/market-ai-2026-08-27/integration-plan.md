# Executable Kuwait-first integration plan

Status: ACTIVE

## Architecture rule

KU-BO remains the single Kuwait package and repository. Predecessor behavior is
reimplemented behind `kubo` contracts; no second engine, duplicate database,
bulk tree copy, private locator, raw market evidence, or source Git history is
merged. Every stage receives a focused test, full applicable gates, a separate
commit, rollback instructions, and exact-head CI before merge consideration.

## Ordered stages

### Stage 0 — PRE-FLIGHT and control repair

Completed on the task branch. Baseline, rollback branches, host/tools/auth,
Drive structure, source worktrees, CI, Secrets/variables, and the pre-existing
control mismatch are recorded. This stage does not claim market capability.

### Stage 1 — source-evidence lifecycle reconciliation

Reimplement the predecessor's unique reconciliation user job as a canonical
`kubo` module and schema. It must:

- validate strict JSON without duplicate keys or non-finite values;
- distinguish HTTP/access outcome from content class and forbid blocked bytes;
- bind every observation to an exact attempt/artifact hash and parser version;
- require an explicit expected-cell denominator and point-in-time cutoff;
- quarantine post-cutoff, malformed revision, lineage, and ineligible-role rows;
- deduplicate exact copies by origin/bytes without turning repetition into
  independent confirmation;
- resolve only a uniquely verified highest-authority value and otherwise block;
- report coverage, unresolved conflicts, zero-yield attempts, and parser drift;
- emit `STRUCTURE_AND_RECONCILIATION_VALID_ONLY` or `BLOCKED`, never authorize
  model fitting, recommendation, or execution.

Entry gate: PRE-FLIGHT commit and private runtime audit digest exist.

Exit gate: focused happy/adversarial tests, schema validation, source/provenance,
temporal leakage, duplicate, missing-data, source-failure, Secret Guard, full
suite, package/CLI smoke, deterministic fixture dry run, and reviewed diff pass.

### Stage 2 — issuer universe and company dossier

Create effective-dated Kuwait issuer identities and a schema per company for
business/sector, official links, financials, prices/liquidity/volatility,
disclosures, actions, management/ownership where lawful, risks, gaps, source
quality/coverage, and last update. Missing values remain null with reason/status.

### Stage 3 — terms-compliant collection and private publication

Build small adapters in official-first order. Run robots/terms/licensing/access
admission before network use. Store raw bytes and exact provenance privately,
normalize only admitted evidence, and publish immutable Drive artifacts only
through runtime credentials and readback receipts. A failed source does not stop
unaffected sources, but never produces replacement facts.

### Stage 4 — auditable event library and temporal splits

Admit unique events toward 20/10-year, 50/5-year, and 300-additional targets.
Record actual unique counts, available-before-event evidence, future outcome
paths, corporate-action adjustments, and source lineage. Create purged/embargoed
train, validation, and locked test splits. Do not invent missing events.

### Stage 5 — locked blind test and improvement cycle

Seal event identity and future outcomes away from prediction inputs, lock every
prediction before reveal, compare with a declared baseline, and report applicable
hit rate, precision, recall, F1, return, drawdown, and calibration. Re-run the
same locked test before/after each change; reject leakage, overfit, or risk harm.

### Stage 6 — live research candidates and schedules

Produce research candidates or `NO-TRADE` for the contracted horizons with
timestamped evidence, reference price, conditional entry, invalidation, risk,
liquidity, gaps, and confidence method. Add sequential UTC Actions with market
calendar guards, concurrency, bounded retries, timeouts, actual-run timestamps,
and hard activation variables. Schedules remain inactive while Secrets/variables
or dry-run gates are missing.

### Stage 7 — Saudi replication

Only after Kuwait tests, blind test, and measurement report pass, repair the
Saudi task control on a new Saudi branch and reuse the architecture with separate
Tadawul sources, symbols, calendar, sessions, regulation, config, data, and
workouts. Do not mix market identifiers or schedules.

## Merge boundary

Do not push directly to `main`. Prepare a Draft PR only after local gates pass.
Merge is conditional on a clean reviewed diff, no secrets/private identifiers,
all applicable tests, deterministic dry-run receipt, exact-head CI, rollback,
status/handoff, and the existing recorded conditional merge authority. Any failed
gate keeps the branch unmerged.
