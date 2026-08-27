# Ordered Next Actions

Updated: 2026-08-27T17:45:00Z

1. Commit and push the reconciled evidence-only control head, require exact-head
   CI, and re-audit Draft PR #25 against unchanged `main`. Exercise
   `KU-BO-MOBILE-CODEX-D01` only for that exact validated head; PR #21 remains
   unmerged while `KU-BO-MIG-D02` is open. Verify post-merge `main` CI green.
2. Acquire and reconcile one real, point-in-time Boursa Kuwait issuer/security
   universe before using the phrase “all market securities”. Build the queue by
   official numeric `security_code`; two securities from one issuer remain two
   separate queue items.
3. Implement and admit runtime adapters behind the injected per-source boundary.
   Start exactly one security, attempt all 29 planned sources with terminal
   receipts, seal it, and only then start the next. Four dynamic/external sources
   (`issuer_ir_verified`, `authorized_broker_feed`,
   `alphastocks_authorized_connector`, and `web_search_router`) still lack a
   complete source-access recipe and must return an explicit blocked receipt.
4. Populate the signed runtime trust registry with the verified official website
   domain for every issuer/security. Never infer a domain from a company name;
   an unresolved site must remain `ISSUER_OFFICIAL_SITE_UNRESOLVED`.
5. Make `KU-BO-ONE-SECURITY-CHECKPOINT-V2` the next bounded task from green
   merged `main`, with recorded narrow private-runtime write authority. Keep
   production `BACKFILL_90D` at `BLOCKED_CHECKPOINT_STORE`. Its existing
   990 market/source/date shards are a legacy market-level package, not proof of
   stock-by-stock collection. Add a reviewed checkpoint v2 with `security_code`
   before resuming sequential per-security work; an ephemeral runner directory
   is not sufficient.
6. Continue Kuwait official-first source admission without bypassing robots,
   403, authentication, paywalls, Terms, or licenses. KCC and the Boursa reports
   archive remain `BLOCKED_ROBOTS / ROBOTS_POLICY_UNAVAILABLE`. LSEG and
   AlphaStocks remain disabled until entitlement and runtime authority exist.
7. Extend the incomplete package only with real, rights-admitted, point-in-time
   observations. Reopen hashes, preserve timestamps and per-security lineage,
   deduplicate copied Reuters/LSEG material by publisher origin, and record all
   conflicts and explicit gaps.
8. Current verified-company, real-observation, unique-event, and
   training-candidate counts remain zero. `research_network` therefore remains
   `SOFTWARE_OPERATIONAL_ABSTAIN` and may emit only research/watch/abstain
   outputs, never a strict forecast.
9. Do not begin challenger training until a dataset release passes rights,
   provenance, point-in-time, leakage, duplicate, missing-data, and temporal
   split gates. Then follow: challenger training → temporal validation → locked
   Blind Test → prospective shadow → explicit promote/reject/rollback. Champion
   cannot self-update.
10. Keep Saudi runtime, training, and promotion blocked behind Kuwait's successful
   locked Blind Test and measurement report. Isolated Saudi research staging may
   not weaken the five frozen Saudi design gates.
11. The declared schedules (backfill minute 23 every two hours, recovery minutes
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
