# KU-BO-013 review follow-up result

Status: `PROVEN` for code, Schema, and synthetic-contract enforcement; `LIVE_DEPENDENT` for all historical collection.

## Repository boundary

- Repository: `mohsamir7122/ku-bo`
- Base: `main` at `32e048b234c73809b6f5119ae16937980184296c`
- Branch: `agent/fix-pr15-historical-evidence-gates`
- Implementation commit: `d16b1c50727d66ff4d7f3fbe24c75fe91749a79a`
- Trigger: four unresolved P2 review threads added to merged PR #15 on 2026-08-14
- Merge, auto-merge, force-push, deletion, and gate weakening: not performed

## Findings and fixes

All four P2 findings were valid.

1. `OFFICIAL_CONFIRMED` previously accepted routing-only evidence. The event
   Schema now requires at least one `PRIMARY` item from an enumerated
   `PRIMARY_OFFICIAL` source, and the Runtime validator resolves source IDs
   against the validated catalog before accepting the status.
2. Legal event types previously accepted `NOT_APPLICABLE`. The Schema and
   Runtime validator now require an explicit procedural state for
   `LEGAL_ALLEGATION`, `COURT_OUTCOME`, and `REGULATORY_ACTION`.
3. `NO_VERIFIED_EVENT_FOUND` previously required no proof of search. The annual
   history contract now requires declared sources, complete query and
   pagination receipts, evidence hashes, and no event IDs. Runtime validation
   requires exact declared-source coverage and binds each receipt capture hash
   to `source_evidence_hashes`.
4. Facebook, Instagram, and TikTok previously shared a 2004 start year. They
   are separate routing-only definitions with start years 2004, 2010, and 2017
   respectively, so temporal source planning cannot route to a platform before
   it existed.

## Validation

- Historical targeted suite: 19/19 PASS with Schema checks enabled.
- Complete unit and adversarial suite: 2,086/2,086 PASS in 150.257 seconds.
- Compile, Codex control, synthetic smoke, Secret Guard, strict JSON, and diff
  checks: PASS.
- KU-BO-011 corpus generation and audit: 1,280/1,280 PASS.
- Wheel: 450884 bytes; SHA-256
  `0b488f86814536da097a488d533eb9afccf5ac3d62ecd90a03400579d9589c46`.
- Isolated wheel install and installed `validate-historical-knowledge`: PASS.

## Claim boundaries

- No historical event or company universe was collected.
- All 28 historical source definitions remain `DEFINED_ONLY`.
- All planned annual tasks remain `NOT_COLLECTED`.
- Social and community sources remain routing or sentiment only.
- Historical layers remain `CONTEXT_ONLY` and cannot emit a forecast,
  probability, rank, recommendation, or execution instruction.
- Exact-head GitHub Actions remains pending until the branch is published.

