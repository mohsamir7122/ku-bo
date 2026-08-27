# Ordered Next Actions

Updated: 2026-08-27T08:23:51Z

1. Push the completed recovery commits to
   `codex/kuwait-market-ai-day1-v1`, run exact-head CI, and keep all schedules
   inactive. Do not create a PR or merge to `main`.
2. Read GitHub Issue #24 and every comment as binding contract additions. Record
   a Delta PRE-FLIGHT (repository, branch, HEAD, upstream, worktree, modules,
   workflows) without repeating completed pre-flight work.
3. Extend the existing source/recovery/provenance modules with one priority
   scheduler: `LIVE_DAILY_1500=100`, `LIVE_RECOVERY=90`,
   `VALIDATION_AND_PUBLISH=70`, `CHALLENGER_TRAINING=40`, and
   `BACKFILL_90D=10`. Use durable atomic checkpoints, lease heartbeat/TTL,
   generation fencing, and resumable market/source/date-or-page shards.
4. Build the rights-aware Kuwait 90-day backfill for the inclusive window
   2026-05-30 through 2026-08-27. The initial bundle must remain named
   `INCOMPLETE_RIGHTS_AWARE_RESEARCH_CONTEXT`; blocked commercial or official
   sources must be recorded and skipped without bypass.
5. Produce the required per-market manifests/JSONL ledgers and coverage reports.
   Report source attempts, actual records, unique records, training-admitted
   records, and blocked-source reasons; do not call the bundle a training dataset
   before rights/provenance/point-in-time/leakage/split gates pass.
6. Continue official-first Kuwait source admission. KCC and Boursa remain blocked
   from prior public probes; try only documented official exports, alternate
   official surfaces, issuer/regulator records, or a user-authorized export.
7. Keep `research_network` at `ABSTAIN` until real admissible observations exist.
   Keep `strict_forecast` locked through dataset release, challenger training,
   temporal validation, locked Blind Test, prospective shadow, and explicit
   promote/reject/rollback. Champion cannot self-update.
8. Saudi remains design-only behind the five frozen gates in
   `config/saudi-deferred-design-gates.json`. Research staging may be considered
   only under the Issue #24 contract; Saudi training/promotion cannot start until
   Kuwait training and Blind Test gates pass.

Resume command:

```bash
cd /root/codexphone/workspaces/ku-bo
git status --short --branch
test "$(git branch --show-current)" = "codex/kuwait-market-ai-day1-v1"
PYTHONPATH=src .venv/bin/python scripts/codex_control_check.py --root .
```
