# KU-BO Current Codex Status

Status date: 2026-08-14

Repository: `mohsamir7122/ku-bo`

## Active work

```text
KU-BO-012 / PR #14 / exact head 73dc3daa994ffd4d41317cf486820264227a85f2
  └── exact-head CI 31782243633 PASS
      └── merged to main as bafdda86b44b7603fe4adfa62dcc2a49bff8ae15
          └── post-merge main CI 31783361999 PASS
          └── KU-BO-013 / PR #15 / implementation head 27dedec792b7f057a975131562898a325fa372a1
              └── exact-head CI 31785060069 PASS
              └── KU-BO-MERGE-005 APPROVED
                  └── later authorization-record head / publication and exact-head CI pending
```

The user explicitly authorized the KU-BO-012 merge, which completed after its
exact-head CI passed. KU-BO-013 begins from merged main and is published as
Draft PR #15. The user explicitly authorized its conditional merge in
`KU-BO-MERGE-005`; the later documentation-only authorization head must still
pass exact-head CI before the merge boundary is executed.

## KU-BO-013 implementation checkpoint

- six annual research-layer definitions;
- 26 source definitions: 12 primary official, 3 primary archive, 2
  intergovernmental, 6 editorial, 2 community, and 1 routing-only;
- deterministic plan generation with 756 annual tasks at as-of 2026-08-14;
- mandatory official company enumeration for every company-year layer;
- primary-source gates for registration, founders, company status, regulatory
  actions, allegations, and court outcomes;
- explicit legal procedural states and no guilt inference;
- social/community/Wikipedia restrictions;
- three JSON Schemas and two CLI commands.

## Evidence and capability status

```text
historical_sources:             26 DEFINED_ONLY
historical_layers:               6
planned_tasks_at_2026-08-14:    756 NOT_COLLECTED
historical_events_collected:      0
companies_enumerated:             0
LIVE_OPERATIONAL:                 0
```

This is code-and-contract progress only. It proves neither historical
completeness nor company-universe completeness nor live source access.

## Still required

- publish the merge-authorization control record to PR #15;
- pass fresh GitHub Actions on that exact later head;
- recheck head, base, reviews, and mergeability, then mark ready and merge only
  the validated SHA;
- later source-by-source rights/access review before collection.

## Local validation checkpoint

- historical and control targeted tests: 19/19 PASS with Schema checks enabled;
- complete suite: 2,082/2,082 PASS in 436.936s on the merge-authorization tree;
- compile, smoke, strict JSON/Schema, config/CLI, diff, and control checks: PASS;
- Secret Guard, wheel build, isolated wheel install, and the installed
  `validate-historical-knowledge` CLI: PASS; wheel size 450075 bytes, SHA-256
  `d74516550c72eaed7e998f59287b2de6721ab97bedf51ad93a178a6fdcb51b4f`;
- PR #15 implementation-head CI run `31785060069`: PASS on Python 3.11 through
  3.14. The later authorization-record head still requires its own run.
