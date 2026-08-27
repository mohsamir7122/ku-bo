# Delta PRE-FLIGHT — Issue #24

Recorded at: `2026-08-27T08:35:00Z` / `2026-08-27T11:35:00+03:00`

This is a delta from the completed master pre-flight. It does not repeat the OS,
disk, memory, Drive, or repository inventory already recorded today.

## Binding input

- Issue: `mohsamir7122/ku-bo#24`, open, one owner comment.
- Issue title: `Implement priority-controlled KW/SA 90-day research backfill`.
- Issue body SHA-256:
  `d2770b7c0c1365f7f94f6dc33ce8bb06547f04fc9f98bc457fb9cfddb9171856`.
- Concatenated comment-body SHA-256:
  `b60747db5fc78afd4523b58649f065a98076a36601174e35b68f38bdf37e335f`.
- `gh issue view 24 --repo mohsamir7122/ku-bo --comments` was executed first
  and exited 1 because this installed `gh` queried deprecated Projects Classic
  `projectCards`. No repository state changed. The issue and all comments were
  then read successfully through the official paginated GitHub REST API.

## Repository delta

```text
repository: mohsamir7122/ku-bo
branch: codex/kuwait-market-ai-day1-v1
HEAD: bd17767e992b57d5833a0bf92c7045294c7633fc
upstream: origin/codex/kuwait-market-ai-day1-v1
worktree: CLEAN
relative to origin/main: 0 behind / 21 ahead
main checked out: false
PR created: false
merge performed: false
```

Exact-head CI run `33054455755` started for this HEAD and was still in progress
when this delta was recorded. The prior branch CI `33043529715` is successful.

No checkout, reset, stash, deletion, PR, or merge occurred. The current branch
was already the required branch, so no branch transition or additional safety
checkpoint was necessary. `bd17767e...` is pushed and is the pre-Issue-24 code
checkpoint.

## Runtime delta

- No repository test, Git operation, backfill worker, lease, or checkpoint run
  was active before the new stage.
- Existing tmux/Codex and the unrelated `smart_newsbot` process remain untouched.
- No runtime lease/checkpoint file exists in the repository.
- The focused baseline covering source orchestration, source quality,
  provenance, evidence lifecycle, source access, schedule, recovery, leases,
  controller, and workflows passed `163/163` tests in `3.839s`.

## Verified integration decision

The existing implementation is authoritative and will be extended:

- `source_orchestrator.py`: bounded attempts, immediate failover, attempt ledger,
  watermarks, and source circuits; extend its invocation with shard/checkpoint
  coordination rather than adding another source fetch engine.
- `source_quality.py` plus `source_quality_policy.json`: authority, rights,
  temporal, identity, parser, coverage, independence gates; retain independent
  gates and add the Issue #24 admission labels outside the scalar score.
- `research_source_registry.json` and `research_network.py`: trusted source-role
  resolution, full observation provenance, copied-news lineage, conflicts,
  research-only outputs; reuse for the 90-day context.
- `provenance.py`: existing tree/package/evidence hashes; extend for immutable
  shard/bundle manifests and transformation lineage.
- `source_evidence_lifecycle.py`: existing point-in-time, duplicate, conflict,
  gap, parser, and source reconciliation; use it for training eligibility.
- `source_access_executor.py`: one-off rights-aware public canary only; it does
  not become a general crawler.
- `recovery.py`: existing incident fingerprint/idempotency and safe lease
  heartbeat/TTL/stale recovery; extend the same lease with priority, generation,
  fencing token, checkpoint identity, and CAS semantics.
- `automation_schedule.py` and current workflows: extend their schedules and
  concurrency; do not create a competing live scheduler.

## Fail-closed gaps before execution

- There is no configured trusted cross-run checkpoint store. GitHub execution
  must report `BLOCKED_CHECKPOINT_STORE` until one is explicitly configured;
  an ephemeral runner directory cannot be described as durable.
- Priority/fencing/checkpoint schemas and the preemption integration test do not
  yet exist.
- The required KW/SA 90-day package ledgers and coverage reports do not exist.
- Real counts remain: 2 source attempts, 0 readable artifacts, 0 observations,
  0 unique admitted events, 0 training candidates.
- Commercial sources and systematic Boursa/Saudi Exchange storage remain
  rights/license gated. No route will bypass robots, access controls, paywalls,
  login, or anti-bot controls.

## Safe execution order

1. Extend recovery lease/checkpoint primitives and implement priority/fencing
   tests, including the mandatory background → live → resume integration case.
2. Add closed schemas and a backfill coordinator that composes the existing
   source, quality, provenance, and lifecycle modules.
3. Materialize structure-only offline dry runs, clearly marked synthetic, then
   perform bounded read-only canaries only on admitted public routes.
4. Add non-overlapping workflows: live remains 12:00 UTC, background shards run
   at minute 23 in idle windows, and priority recovery runs at minutes 13/43;
   the five-minute missed-event watchdog remains a separate safety mechanism.
5. Keep all schedules `NOT_YET_SCHEDULE_ACTIVE` until reviewed files reach the
   default branch through an authorized merge.
