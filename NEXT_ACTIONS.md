# Ordered Next Actions

Updated: 2026-08-27T03:51:15Z

1. Commit the completed, tested Stage 1 source-evidence lifecycle as an isolated
   commit; retain the rollback branch and do not merge to `main`.
2. Define effective-dated Kuwait issuer identities and a strict company dossier
   schema covering business, financials, price/liquidity/volatility, events,
   corporate actions, ownership where lawful, risks, gaps, source quality, and
   last update.
3. Add schema, missing-data, provenance, temporal, duplicate-identity, and
   corporate-action tests before admitting any real company record.
4. Build a source-admission ledger and dry probes in official-first order. Do not
   bypass robots, paywalls, sessions, rate limits, licensing, or access controls.
5. Design the sequential UTC GitHub Actions schedule with concurrency, timeout,
   bounded retries, market calendars, and a hard activation gate. Do not enable
   it while required Secrets/variables are absent.
6. Begin real Kuwait collection only after source admission succeeds. Record the
   actual company and unique-event counts; never fill gaps with invented data.
7. Keep Saudi implementation unchanged until Kuwait tests, dry work, a locked
   blind test, and a measurement report satisfy the contract gates.

Resume command:

```bash
cd /root/codexphone/workspaces/ku-bo
git switch codex/kuwait-market-ai-day1-v1
git status --short --branch
PYTHONPATH=src .venv/bin/python scripts/codex_control_check.py --root .
```
