# Ordered Next Actions

Updated: 2026-08-27T04:24:26Z

1. Build a source-admission ledger and bounded dry probes in official-first
   order. Do not bypass robots, paywalls, sessions, rate limits, licensing, or
   access controls.
2. Design the sequential UTC GitHub Actions schedule with concurrency, timeout,
   bounded retries, market calendars, and a hard activation gate. Do not enable
   it while required Secrets/variables are absent.
3. Commit Stage 2 independently after the final cached diff review, then push
   the work branch and use exact-head CI. Keep any PR draft-only and do not merge
   while gates remain open.
4. Begin real Kuwait collection only after source admission succeeds. Record the
   actual company and unique-event counts; never fill gaps with invented data.
5. Build the deduplicated historical event library and purged train/validation/
   locked-test split only from admitted point-in-time evidence.
6. Keep Saudi implementation unchanged until Kuwait tests, dry work, a locked
   blind test, and a measurement report satisfy the contract gates.

Resume command:

```bash
cd /root/codexphone/workspaces/ku-bo
git switch codex/kuwait-market-ai-day1-v1
git status --short --branch
PYTHONPATH=src .venv/bin/python scripts/codex_control_check.py --root .
```
