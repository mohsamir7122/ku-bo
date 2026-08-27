# Ordered Next Actions

Updated: 2026-08-27T05:44:55Z

1. Commit and push the completed fail-closed Kuwait schedule stage, then require
   exact-head CI. Do not activate schedules or merge to `main`.
2. Implement the unified recovery incident, sanitization, retry/resume,
   lease-lock, robots classification, controlled fallback, and alert-deduplication
   contracts requested in the 2026-08-27 recovery review.
3. Re-audit and repair Kuwait review findings: nonzero blocked exits; verified
   zero-result receipts; Factor 9 artifact rehashing; canonical live-dry-run
   validators; and stale-lock recovery. Preserve every provenance and temporal
   gate and add adversarial tests.
4. Replace overlapping workflow concepts with one Kuwait market pipeline plus a
   bounded recovery controller. Keep scheduled activation blocked until the files
   are reviewed and explicitly merged to the default branch.
5. Continue official-first source admission through an explicitly authorized
   route. The direct KCC and Boursa reports probes remain blocked; do not bypass
   access controls or reinterpret an access receipt as collection.
6. Begin real Kuwait collection only after source admission succeeds. Record the
   actual company/event counts, then build purged train/validation/locked-test
   splits without invented data.
7. Record Saudi review invariants and design tests only: trusted registry role/
   rights resolution, suspended members retained in denominators, global temporal
   cutoffs, missing-calendar blocking, and `observed_at <= known_at`. Do not start
   Saudi runtime work before Kuwait's contractual gates pass.

Resume command:

```bash
cd /root/codexphone/workspaces/ku-bo
git switch codex/kuwait-market-ai-day1-v1
git status --short --branch
PYTHONPATH=src .venv/bin/python scripts/codex_control_check.py --root .
```
