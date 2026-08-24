# KU-BO Current Codex Status

Status date: 2026-08-24

Repository: `mohsamir7122/ku-bo`

## Active work

```text
main 59833bf73510b3aa3901f628cbf2c13c0d01cf79
  └── KU-BO-015 / Draft PR #19 / COMPLETED
      └── implementation head 4da4e03276e105f161cbfdc3d4d7b07b3f2a814c
          └── exact-head CI 32735784463 PASS / Python 3.11-3.14
```

Open PRs observed at task start were Draft PR #17 (`KU-BO-014`), Draft PR #18
(HUMANSOFT data-domain separation), and the stale/superseded PRs #2 and #3. This
task starts directly from current `main` and does not modify or merge those PRs.

## KU-BO-015 checkpoint

- 14 `DEFINED_ONLY` source-access recipes;
- 30 priority sources covered out of the 68-source network catalog;
- 38 sources explicitly uncovered by this recipe set;
- one reviewed manual importer registration capped at `PRICE_IMPORT_READY_ONLY`;
- deterministic metadata-only probe plans bound to registry SHA-256 and catalog URL;
- plan-bound validation layered over the existing raw-hash-bound access probe;
- 0 live probes, 0 market rows, 0 capability promotions, and 0
  `LIVE_OPERATIONAL` sources.

## Evidence and capability status

```text
recipe_contract:             CODE_AND_CONTRACT
recipe_capability:           DEFINED_ONLY
covered_source_definitions:  30
live_site_probes:             0
market_evidence_rows:         0
LIVE_OPERATIONAL:             0
```

## External follow-up gates

- perform real probes only in a separate authorized runtime task;
- register an actual broker/vendor domain and entitlement before planning an
  execution-source probe;
- obtain a separate recorded user decision before merge.

## Local validation checkpoint

- focused source-access, user-export, and Schema tests: 30/30 PASS;
- complete unit and adversarial suite: 2,104/2,104 PASS in 192.823 seconds;
- compile, strict JSON/Schema, config/CLI, diff, control, corpus, smoke, and
  Secret Guard: PASS;
- final wheel build and isolated install: PASS; wheel size 459184 bytes,
  SHA-256 `d3f2257f1dc4de154033a84c3e36fe4df852cb3f7b5c8a8ec8c95fa9e8e1ac06`;
- installed recipe validation, two-source plan generation, plan revalidation,
  and Investing importer help: PASS;
- Draft PR #19 exact-head GitHub Actions run `32735784463`: PASS on Python 3.11
  through 3.14 at implementation head
  `4da4e03276e105f161cbfdc3d4d7b07b3f2a814c`.
