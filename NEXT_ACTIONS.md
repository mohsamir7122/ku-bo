# Ordered Next Actions

Updated: 2026-08-27T09:04:10Z

1. Commit this Stage 6 status evidence, push only
   `codex/kuwait-market-ai-day1-v1`, and require exact-head CI for the resulting
   documentation head. Priority-head CI run `33056857748` is in progress. Do not
   create a PR, merge to `main`, or claim schedules are active.
2. Extend the existing source/evidence modules with the rights-aware Kuwait
   backfill for the inclusive 2026-05-30 through 2026-08-27 window. Keep the
   package name exactly `INCOMPLETE_RIGHTS_AWARE_RESEARCH_CONTEXT`.
3. Materialize and validate the required Kuwait files: `run-manifest.json`,
   `source-attempts.jsonl`, `provenance-records.jsonl`, `events-unique.jsonl`,
   `research-context-90d.jsonl`, `training-candidates.jsonl`,
   `blocked-records.jsonl`, `contradictions.jsonl`, `coverage-report.json`, and
   `coverage-report.md`.
4. Use only trusted source-registry roles and the existing canonical validators.
   Record `ADMITTED_RESEARCH_CONTEXT`, `ADMITTED_TRAINING`, `BLOCKED_RIGHTS`,
   `BLOCKED_ROBOTS`, `BLOCKED_ACCESS`, `MISSING`, or `UNVERIFIED` per record.
   Never bypass 403, robots, paywall, login, Terms, or license controls.
5. Keep production backfill execution at `BLOCKED_CHECKPOINT_STORE` until an
   allowlisted authorized durable store is configured. Local filesystem tests
   prove coordination mechanics only, not GitHub-runner durability.
6. Add bounded background/recovery schedules only by extending current
   workflows: minute 23 every two hours for backfill and minutes 13/43 for
   recovery, with priority checks, one Kuwait concurrency policy, no sleeps, and
   no infinite retry. Schedules remain inactive until reviewed files reach the
   default branch.
7. Continue official-first Kuwait source admission. KCC and Boursa remain
   blocked from the two prior public probes; try only documented official
   exports, alternate official surfaces, issuer/regulator records, or a
   user-authorized export.
8. Keep `research_network` at `ABSTAIN` until real admissible observations exist.
   Keep `strict_forecast` locked through dataset release, challenger training,
   temporal validation, locked Blind Test, prospective shadow, and explicit
   promote/reject/rollback. Champion cannot self-update.
9. Saudi remains design-only behind the five frozen gates in
   `config/saudi-deferred-design-gates.json`. Isolated research staging may be
   built only without Saudi training or promotion before Kuwait's locked Blind
   Test succeeds.

Resume command:

```bash
cd /root/codexphone/workspaces/ku-bo
git status --short --branch
test "$(git branch --show-current)" = "codex/kuwait-market-ai-day1-v1"
PYTHONPATH=src .venv/bin/python scripts/codex_control_check.py --root .
```
