# Ordered Next Actions

Updated: 2026-08-27T02:38:26Z

1. Reimplement the audited source-evidence lifecycle reconciler as a canonical
   `kubo` module and strict schema. Do not copy a parallel tool/database engine.
2. Add happy/adversarial tests for lineage, point-in-time cutoff, parser drift,
   blocked content, revisions, independent origins, duplicates, conflicts,
   missing critical cells, and refusal to overwrite outputs.
3. Exercise the existing Kuwait deterministic synthetic dry-run path, preserve
   its receipt, and run source-failure, provenance, temporal-leakage, duplicate,
   missing-data, and corporate-action tests.
4. Run control, schema/JSON, Secret Guard, full suite, build/install/CLI smoke,
   and exact diff review; commit Stage 1 independently.
5. Design the sequential UTC GitHub Actions schedule with concurrency, timeout,
   bounded retries, market calendars, and a hard activation gate. Do not enable
   it while required Secrets/variables are absent.
6. Define and validate the real Kuwait issuer/company dossier schemas and admission
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
