# Ordered Next Actions

Updated: 2026-08-27T10:02:25Z

1. Commit and push this status-only checkpoint, then require exact-head CI for
   that new head. Package CI `33059176971` passed `e9d1a7f`; workflow CI
   `33060045908` passed `85a9068`. Do not create a PR, merge to `main`, or claim
   schedules are active.
2. Keep production `BACKFILL_90D` at `BLOCKED_CHECKPOINT_STORE`. A user-reviewed
   allowlisted durable store is required before a GitHub runner may retain and
   resume shard state; an ephemeral runner directory is not sufficient.
3. Continue Kuwait official-first source admission in the frozen fallback order:
   documented official API/export, alternate official surface, issuer official
   disclosure, regulator record, user-authorized export, then secondary
   discovery only. KCC and the Boursa reports archive remain
   `BLOCKED_ROBOTS / ROBOTS_POLICY_UNAVAILABLE`; never bypass robots, 403,
   authentication, paywalls, Terms, or licenses.
4. Extend the incomplete 90-day package only with real, rights-admitted,
   point-in-time observations. Reopen hashes and canonical validators, preserve
   all provenance timestamps, deduplicate copied news/events, record conflicts,
   and resume only non-completed market/source/date-or-page shards.
5. Reconcile the real Kuwait issuer/security denominator and company dossiers.
   Current verified-company, real-observation, unique-event, and
   training-candidate counts are all zero. `research_network` therefore remains
   `SOFTWARE_OPERATIONAL_ABSTAIN` and may emit only research/watch/abstain
   outputs, never a strict forecast.
6. Do not begin challenger training until a dataset release passes rights,
   provenance, point-in-time, leakage, duplicate, missing-data, and temporal
   split gates. Then follow: challenger training → temporal validation → locked
   Blind Test → prospective shadow → explicit promote/reject/rollback. Champion
   cannot self-update.
7. Keep Saudi runtime, training, and promotion blocked behind Kuwait's successful
   locked Blind Test and measurement report. Isolated Saudi research staging may
   not weaken the five frozen Saudi design gates.
8. The declared schedules (backfill minute 23 every two hours, recovery minutes
   13/43, five-minute missed-event watchdog, and the seven Kuwait slots) remain
   inactive until reviewed workflow files are authorized and merged to the
   default branch. The controller cannot modify `main`.

Resume commands:

```bash
cd /root/codexphone/workspaces/ku-bo
git status --short --branch
test "$(git branch --show-current)" = "codex/kuwait-market-ai-day1-v1"
PYTHONPATH=src .venv/bin/python scripts/backfill_90d.py policy
PYTHONPATH=src .venv/bin/python scripts/codex_control_check.py --root .
```
