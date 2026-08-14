# KU-BO Current Codex Status

Status date: 2026-08-15

Repository: `mohsamir7122/ku-bo`

## Verified baseline

```text
main / origin/main: 59833bf73510b3aa3901f628cbf2c13c0d01cf79
PR #15: merged historical-knowledge planning layer
PR #16: merged historical evidence-gate hardening
active task: KU-BO-014
active branch: agent/bootstrap-archive-v0.1
merge authority for KU-BO-014: NONE
```

The baseline contains the KU-BO-013 planning foundation and its follow-up
hardening: 28 historical source definitions, six historical layers, strict
official-primary confirmation, explicit procedural states for legal events,
hash-bound complete-search receipts for `NO_VERIFIED_EVENT_FOUND`, and separate
Facebook, Instagram, and TikTok start years.

## Active work — KU-BO-014

KU-BO-014 is building a separate `Bootstrap Archive` scaffold that reuses the
KU-BO-013 catalog and plan. The intended workspace contains only deterministic
control artifacts, input hashes, stage descriptors, and empty reserved
directories. It must not contain a historical corpus or imply that collection
has begun.

The ordered stage contract is:

```text
BOOTSTRAP_ARCHIVE
  └── COMPANY_INTELLIGENCE
      └── SOURCE_WAVES
          └── BOURSA_OFFICIAL_RECONCILIATION
```

`COMPANY_INTELLIGENCE` additionally requires an official listed-universe
identity anchor. The final Boursa stage remains the comprehensive official
reconciliation after the source waves.

## Current contract checkpoint

- isolated archive configuration and directory policy;
- a declared-only source crosswalk between all 28 historical source IDs and
  existing Source Network IDs where an honest semantic bridge exists;
- explicit unmapped/partial states instead of invented equivalence;
- atomic, no-overwrite scaffold publication;
- deterministic plan and control-artifact hashes;
- zero initial Evidence, companies, and events;
- tamper-aware reopening and verification;
- collection and all three downstream stages remain blocked until their real prerequisites pass.

## Validation status

```text
KU-BO-014-only tests: 34/34 PASS
targeted archive + historical + control tests: 57/57 PASS
complete local suite: 2,120/2,120 PASS in 158.371s
compile/smoke/Secret Guard/Schema/control: PASS
KU-BO-011 deterministic corpus: 1,280 cases PASS
wheel and isolated install/prepare/verify: PASS
Draft PR: #17 OPEN / DRAFT
implementation exact-head CI: Run 31840391449 PASS at c8b41b23e5ebe4f4243b42506862c36149d481c8
final control-record head CI: PENDING
```

The local implementation tree passes the requested validation. The installed
wheel prepared and independently verified the same 756-task, zero-Evidence
scaffold from outside the checkout. Draft PR #17 publishes the identical tree,
and exact-head Run 31840391449 passed on Python 3.11 through 3.14. This control
record creates a later documentation-only head that still requires exact-head CI.

## Evidence and capability status

```text
bootstrap_archive_status:       DRAFT_PUBLISHED_IMPLEMENTATION_CI_PASS
archive_readiness:              PLANNED_NOT_EXECUTED
historical_evidence_artifacts:  0
historical_events_collected:    0
companies_enumerated:           0
crosswalk_collection_allowed:   false
LIVE_OPERATIONAL:               0
```

This proves the local empty-scaffold contract and tamper checks only. It does
not prove historical completeness, company-universe completeness, live source
access, Parser coverage, or investment readiness.

## Still required

- publish the control-record update and require exact-head CI on that later head;
- keep merge blocked until a later explicit merge decision;
- before any future collection, approve source-specific access and rights and
  bind an official company universe.
