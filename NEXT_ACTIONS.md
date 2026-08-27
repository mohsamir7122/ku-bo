# Ordered Next Actions

Updated: 2026-08-27T05:08:49Z

1. Design the sequential UTC GitHub Actions schedule with concurrency, timeout,
   bounded retries, market calendars, and a hard activation gate. Do not enable
   it while required Secrets/variables are absent.
2. Continue official-first source admission through an explicitly authorized
   route. The direct KCC and Boursa reports probes are audit-valid but blocked at
   `ROBOTS_POLICY_UNAVAILABLE`; do not bypass or reinterpret this as access.
3. Push the Stage 3 implementation and receipt commits, then require exact-head
   CI. Do not open or merge a PR while collection and blind-test gates remain
   open.
4. Begin real Kuwait collection only after at least the required official source
   admission succeeds. Record the
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
