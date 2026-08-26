---
name: operate-ku-bo-research
description: Use when operating or extending KU-BO evidence, source fallback, portfolio validation, daily dry-runs, Factor9 admission, event-program contracts, or replay evaluation for Boursa Kuwait.
---

# Operate KU-BO Research

## Start With The Boundary

- Work only inside the locked `KW` / `BOURSA_KUWAIT` / `KWD` / `Asia/Kuwait` scope.
- Run `python -m kubo.cli_v3 --project-root . validate-config` before an operational workflow.
- Keep private evidence and run outputs outside Git. Commit only contracts, schemas, code, tests, and sanitized reports.
- Treat `PRIVATE_PREDECESSOR_SOURCE` as read-only research input. Never merge its Git history, execute its scripts, publish its locator, or create a second engine.
- Reimplement admitted behavior only through `src/kubo`, then add semantic and negative tests.

## Route The User Job

| User job | Canonical route |
| --- | --- |
| Check source quality | `validate-source-quality-policy` and `validate-source-network` |
| Recover from a weak or blocked source | `validate-source-fallback-policy`, then `plan-source-fallback --request REQUEST.json` |
| Validate a portfolio export | `validate-portfolio-state --snapshot SNAPSHOT.json --orders ORDERS.json --evidence-root PRIVATE_ROOT --decision-at ISO_TIME` |
| Admit Factor9 material | `validate-factor9-admission --manifest MANIFEST.json` |
| Check the 50+200 development and locked-test contract | `validate-ku-bo-live-program` |
| Run the daily pipeline | `run-live-dry-run` with private evidence bindings and previous-session champion freezes |
| Recheck an interrupted run | `validate-live-dry-run --run-root PRIVATE_RUN_ROOT` |
| Evaluate frozen replay decisions | `evaluate-forty-session-replay --packet PACKET.json --runtime-root PRIVATE_ROOT` |
| Audit migrated user jobs | `validate-predecessor-capability-parity` |

## Preserve Evidence Semantics

1. Separate transport success from semantic success. HTTP success with zero rows is unusable unless a bounded zero-result receipt verifies the query and pagination.
2. A blocked source ends only that source attempt. Continue through the registered capability chain without bypassing access controls.
3. Trace secondary, community, and search leads back to the original publisher. Search results route; they do not prove facts.
4. Keep source certainty separate from analytical certainty. Never convert source availability into a probability.
5. Bind every portfolio, event, factor, and replay input to point-in-time evidence bytes and SHA-256 receipts.
6. If a required gate or previous-session champion is missing, emit the sealed abstention path. Do not improvise candidates, entry or exit prices, probabilities, training, recommendations, or execution.

## Completion Standard

- Validate the affected schema and CLI route.
- Run focused negative tests, then the full suite.
- Re-run the repository secret guard and the locked-market text audit.
- Claim software parity only. Operational readiness requires separate live evidence, rights, coverage, and model gates.
