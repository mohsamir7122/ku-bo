# Ordered Next Actions

Updated: 2026-08-27T02:38:26Z

1. Run the repository control validator and its focused unit tests on
   `codex/kuwait-market-ai-day1-v1`; retain the strict branch assertion.
2. Run `git diff --check`, JSON parsing, secret scanning, and a focused test set,
   then commit the PRE-FLIGHT/control stage as one reversible commit.
3. Finish the exact-SHA private-runtime capability matrix for KU-BO, the
   `PRIVATE_PREDECESSOR_SOURCE`, Saudi, and each relevant archived/source
   checkout. Classify `KEEP`, `REFACTOR`, `ARCHIVE`,
   `SUPERSEDE`, `PRIVATE_ONLY`, and gaps without bulk-merging a legacy tree.
4. Exercise the existing Kuwait deterministic synthetic dry-run path, preserve
   its receipt, and run source-failure, provenance, temporal-leakage, duplicate,
   missing-data, and corporate-action tests.
5. Design the sequential UTC GitHub Actions schedule with concurrency, timeout,
   bounded retries, market calendars, and a hard activation gate. Do not enable
   it while required Secrets/variables are absent.
6. Define and validate the real Kuwait issuer/source schemas and admission
   contracts before collecting any source. Respect robots, paywalls, licensing,
   rate limits, and point-in-time boundaries.
7. Begin real Kuwait collection only after source admission succeeds. Record the
   actual company and unique-event counts; never fill gaps with invented data.
8. Keep Saudi implementation unchanged until Kuwait tests, dry work, a locked
   blind test, and a measurement report satisfy the contract gates.

Resume command:

```bash
cd /root/codexphone/workspaces/ku-bo
git switch codex/kuwait-market-ai-day1-v1
git status --short --branch
PYTHONPATH=src .venv/bin/python scripts/codex_control_check.py --root .
```
