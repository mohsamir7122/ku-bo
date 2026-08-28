# Ordered Next Actions

Updated: 2026-08-28T13:22:48Z

Canonical machine-readable control:
`config/codex_control_state.json`.

Active task: `KU-BO-2026-08-28-READINESS-CANARY` on
`codex/ku-bo-readiness-live-canary-v1`, frozen from `main` at
`8860989f6a2affdc66bc790f639757c9a897f353`.

1. Make the control validator bind the canonical task to the actual branch,
   `HEAD`, base ref/SHA, ancestry, and active status mirrors. Keep the PR Draft
   and do not merge.
2. Review the `GITHUB_ARTIFACT_JOURNAL` checkpoint canary support against restore,
   corruption, concurrent writer, fencing, atomicity, and wrong-store fail-closed
   cases. It is not a production-durable backend. Keep Issue #28 open until
   production wiring and genuine cross-run evidence pass a separate review.
3. Keep automatic schedules disabled or absent and unauthorized. Correct
   orchestration defects without using repeated scheduled failures as readiness
   tests.
4. Keep missing official identity, signed issuer-domain authority, source rights,
   runtime authority, and admitted live adapters as production blockers. The
   access-only probe does not satisfy or bypass any of them.
5. Invoke no more than one credential-free access-only canary through the
   deliberate Draft-PR opening. It may fetch only the fixed public allowlist and
   must not create market evidence or candidates. Preserve its exact stop reason
   and sanitized receipt; a blocked or zero-result run remains
   `ABSTAIN / NO-TRADE`.
6. Run targeted tests, the full relevant suite, Secret Guard, schema/bootstrap/
   control checks, package validation, and exact-head GitHub CI. Publish a Draft
   PR only after the local gates pass.
7. Record the handoff with exact SHAs, commands, results, Issue #28 state, and
   remaining external blockers. Do not claim `LIVE_OPERATIONAL`, predictive
   accuracy, recommendation readiness, or financial execution.

Resume checks:

```bash
git status --short --branch
test "$(git branch --show-current)" = "codex/ku-bo-readiness-live-canary-v1"
python scripts/codex_control_check.py --root .
python scripts/validate_codex_live_bootstrap.py --project-root . --json
```
