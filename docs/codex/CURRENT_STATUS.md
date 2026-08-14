# KU-BO Current Codex Status

Status date: 2026-08-14

Repository: `mohsamir7122/ku-bo`

## Active work

```text
KU-BO-012 / PR #14 / exact head 73dc3daa994ffd4d41317cf486820264227a85f2
  └── exact-head CI 31782243633 PASS
      └── merged to main as bafdda86b44b7603fe4adfa62dcc2a49bff8ae15
          └── post-merge main CI 31783361999 PASS
          └── KU-BO-013 / agent/kuwait-historical-knowledge-layer / IN_PROGRESS
```

The user explicitly authorized the KU-BO-012 merge, which completed after its
exact-head CI passed. KU-BO-013 begins from merged main and remains a separate
Draft-PR task with no merge authority.

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

- publication as a Draft PR;
- exact-head GitHub Actions;
- a separate user decision before any KU-BO-013 merge;
- later source-by-source rights/access review before collection.

## Local validation checkpoint

- historical and control targeted tests: 19/19 PASS;
- complete suite: 2,082/2,082 PASS in 278.335s;
- compile, smoke, strict JSON/Schema, config/CLI, diff, and control checks: PASS;
- Secret Guard, wheel build, isolated wheel install, and the installed
  `validate-historical-knowledge` CLI: PASS; wheel size 450075 bytes, SHA-256
  `3bf841d569e00a06646c72d7f9f82d3e3dcbec7fe27d1cd331fa89d68e97726c`.
