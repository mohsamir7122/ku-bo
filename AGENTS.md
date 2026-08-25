# KU-BO Research Engine instructions

Open this directory as the project root.

## Codex control entrypoint

- In every new Codex session, read `CODEX_START_HERE.md` and the files under `docs/codex/` in the declared order before changing code.
- `docs/codex/CURRENT_TASK.md` is the single active task. Old conversations, archived prompts, and prior handoffs are historical context only.
- Continue through implementation, test, inspect, fix, and rerun cycles until the active acceptance gates pass or a genuine external/user-decision blocker is recorded.
- Never merge, force-push, permanently delete files/branches/conversations, or weaken a gate without explicit user authorization recorded in `docs/codex/USER_DECISIONS.md`.
- Raw private conversations stay outside Git. Only sanitized, non-personal technical summaries may enter the repository under `docs/codex/CONVERSATION_IMPORT_POLICY.md`.
- When a task ends, write a handoff using `docs/codex/HANDOFF_TEMPLATE.md` and distinguish `PROVEN`, `PARTIAL`, `BLOCKED`, `SYNTHETIC_ONLY`, `RECORDED_FIXTURE_ONLY`, and external-data dependencies.

## Codex live bootstrap

- Before every new task, run `python scripts/validate_codex_live_bootstrap.py --project-root . --json`. A failure blocks implementation; do not weaken the contract to continue.
- Treat `AI Rebuild` as private runtime storage. The repository may contain only its logical paths and sanitized aggregate conclusions, never folder/file IDs, connector identifiers, signed URLs, or private bytes.
- The canonical private KU-BO root is logically `AI Rebuild/04_Curated_Core/KU_BO`. Index and hash before admission, version instead of overwriting, and quarantine duplicates before any deletion proposal.
- Preserve Factor 9 raw, clean, excluded, failure, company-master, factor, event-library, and review artifacts. Its current state is `RESEARCH_ASSET_PENDING_ADMISSION`; do not repeat extraction, recompute the old score, train on auto-labels, or call it a validated model.
- Keep the 50 major plus 200 control events in development only. The locked 500-600-event test is disjoint; development events may appear only in regression replay, never in headline test performance.
- The default training budget is 30 rounds. Rounds 31-50 require a preregistered new hypothesis; a failed result is not permission to tune on the locked test.
- At 15:07 Kuwait, a daily research run may use only a previous-session `APPROVED_CHAMPION` freeze that passes `kubo.champion_freeze`. Same-day training happens after output sealing and cannot affect that day's output.
- Continuous improvement produces a separate Challenger, test evidence, Task branch, and Draft PR. It does not self-promote, auto-merge, rewrite prior outputs, or alter the current Champion in place.
- Keep the scheduled shadow workflow disabled unless the separate runtime authorization variable is deliberately enabled. The workflow validates contracts only; it does not collect market data or emit stock recommendations.

## Private predecessor capability migration

- The single active task is the complete private-predecessor capability migration defined in `docs/codex/CURRENT_TASK.md`; the previous KU-BO-017 dry-run task is preserved in `docs/codex/backlog/` and is not active.
- Read `docs/codex/PRIVATE_PREDECESSOR_MIGRATION_EXECPLAN.md` and validate the machine-readable preparation controls before editing implementation code.
- KU-BO is the only canonical target engine. Do not merge private-source Git history, copy a second engine/package, or preserve unsafe behavior merely for textual parity.
- Read-only inspection of the configured private source repository code and Git metadata is authorized. Do not access unrelated private/runtime data or export credentials, tokens, sessions, connector locators, or secret material.
- Inventory every relevant private source ref and file before porting. Keep exact repository/ref/commit/tree locators, counts, sensitive paths, findings, and reversible opaque mappings in uncommitted private runtime storage. Public rows require privacy review.
- Skills are thin Codex-facing wrappers. Shared business logic belongs under `src/kubo`, with one canonical CLI and no duplicated source, evidence, factor, evaluation, or portfolio engines.
- Capability parity and operational readiness are separate. `PARITY_PROVEN` never implies `LIVE_OPERATIONAL`, real backtest readiness, predictive accuracy, probability, recommendation, or execution authorization.
- The private predecessor is read-only during this task. Do not archive, delete, rewrite, or modify it, and do not merge this task without a new explicit user decision.
- The preparation validator can never claim migration completion. Add a dedicated validator that reopens private source receipts and verifies exact target/test/package/CI/PR/handoff evidence before any completion claim.

## Research-engine rules

- Treat this checkout as version `0.1.0`: an auditable, non-production research foundation, not a live recommendation or execution service.
- Read `README.md` and the relevant contract in `docs/` before changing code.
- Keep raw evidence, normalized observations, features, forecasts, process assessments, and outcomes in separate artifacts.
- Use `research_network` as the default research mode. It requires a fresh per-run source packet, but not a complete historical archive or validated model.
- Keep `validated_forecast` as a separate strict mode. Never let a source-mosaic rank bypass its evidence-pack, model-card, sealing, or prospective-validation gates.
- Count independent publisher/origin groups, not URLs or reposts. The catalog currently contains 68 source definitions that resolve to 62 independence groups. It contains 59 non-search/non-storage candidate domains, 53 declared enabled-public catalog domains, and 52 distinct executable start-URL domains before fair reservation. The default plan attempts exactly 50 distinct domains with incremental wave contributions `17/0/29/4`; it reserves the final four for Archive/Community, including `t.me` and `indexsignal.com`. None of these counts is a confirmation count.
- Keep source capability claims separate from catalog presence. The current capability inventory is 66 `DEFINED_ONLY`, 2 `END_TO_END_TESTED` on generated fixtures, and 0 `LIVE_OPERATIONAL`.
- For `KUWAIT_120D_NEXT_SESSION_RESEARCH`, keep the 120-day context, 30-day active-event, 7-day community, and 72-hour fresh-catalyst windows distinct. Bound the search at up to 50 registrable domains, three transient attempts per strategy, and four materially distinct strategies for a valid empty result.
- Reopen and validate every persisted Source Search run before integration: rehash its report, append-only attempt ledger, and referenced raw artifacts. Raw bytes become research inputs only through the strict parsed-input contract and `build-kuwait-research-bundle`; this bridge does not invent parsing, exposure, factors, dispositions, or scores.
- Treat retries fail-closed: hard blocks are never retried, HTTP 429 exhausts at three attempts on the same strategy without rotating around the denial, `Retry-After` is honored only within the remaining wall budget, and a failed sleeper or exhausted retry budget stops that route. Preserve these outcomes and all material limitations in the hash-chained attempt ledger; its hash chain is not an external seal.
- Telegram and IndexSignal are community-sentiment or routing surfaces only. They cannot establish official identity, price, Corporate Action, or factual catalyst.
- Bind every Factor Snapshot's complete canonical rows, factors, evidence hashes, dispositions, and scores to `factor_snapshot_sha256`; derive `snapshot_id` from that digest. Enforce each registry freshness window against `available_at` and `decision_at`, including the 24-hour current-status window, and never let a `SUPERSEDED` event create factor-eligible exposure.
- A latest-40 evaluation requires 41 consecutive official sessions and 40 point-in-time decision packets with a reconciled full denominator. The KU-BO-012 replay exposes only `PASS_BACKTEST` and `STOP_BACKTEST`; missing, incomplete, ambiguous, or unauthoritative real evidence must yield `STOP_BACKTEST` with `metrics=null`, `agreement_rate=null/NOT_APPLICABLE`, `authority_verified=false`, and `accuracy_claim_allowed=false`. Present the agreement as `N/A`, never as `0%`; `STOP_INFERENCE` is not an advertised or reachable runtime status.
- `KUWAIT_120D_NEXT_SESSION_RESEARCH` is execution-grade. Preserve every non-trading member in the denominator; while `KU-BO-008-D01` remains open, any non-trading outcome stops the backtest rather than silently advancing, dropping the row, or synthesizing a close. Selected rows require a verified `FILLED` execution.
- The primary replay label is adjusted gross next-session return above zero before execution costs. Fees, spread, and slippage apply to actionable net and market/sector net-excess metrics; do not relabel the primary gross metric as cost-adjusted.
- A blocked Boursa Kuwait surface may leave research available only when a fresh, contributing official identity receipt from an independent fallback remains valid. Otherwise identity failure is structural. In either case, remove unavailable official confirmation and demote unconfirmed directional catalyst claims to `WATCH`.
- Treat all surfaces owned by one platform as one publisher group. Require each finding to declare valid `evidence_roles` and an eligible `fact_type`, bind its raw hash to the same source, match its `source_url` exactly to the referenced artifact URL, and match official catalyst confirmation by event key and direction.
- Restrict community sources to sentiment/risk and web archives to archive context. Search results and storage cannot create findings.
- A caller-provided capability name is never proof that the capability exists. Capabilities must be supported by a validated evidence manifest and capability report.
- Never bypass login, CAPTCHA, paywalls, rate limits, robots controls, or protected APIs.
- Treat public Boursa Kuwait trading pages as delayed. They may support delayed detection, but not live execution.
- Keep the six KU-BO-013 historical layers `CONTEXT_ONLY`. Every planned year begins `NOT_COLLECTED`; company-year work requires official universe enumeration, legal claims require an explicit procedural state and official legal/regulatory evidence, and social/community/Wikipedia sources remain routing or sentiment only.
- Join securities by official `security_code` and effective-dated identity; ticker-only joins are invalid.
- Never rewrite an issued forecast. Append a forward-timed event to the ledger.
- A score is not a probability. `SOURCE_MOSAIC_EVIDENCE_SCORE_NOT_PROBABILITY` can produce only a research candidate, `WATCH`, or `ABSTAIN`. `HIGH_BUY_OPPORTUNITY` requires a bound `PROSPECTIVE_VALIDATED` model card and all applicable gates.
- Never calculate a headline accuracy result unless the full point-in-time denominator reconciles.
- Raw capture is never a Finding. Preserve `RAW_CAPTURE_PENDING_PARSER_VALIDATION` until parsing, identity, time, role, and evidence validation pass.
- Enforce source quorum per security. `ZERO_RESULT`, neutral findings, and zero-strength/materiality rows do not manufacture evidence coverage.
- Reject a capture plan before connector construction or output writes when it exceeds 32 tasks, 128 MiB total declared `max_bytes`, or 300 seconds total declared `timeout_seconds`.
- Packet-contained runtime-authority, activation, or entitlement receipts are claims, not roots of trust. Version `0.1.0` fails closed for sensitive sources unless a separately configured external trust registry passes HMAC-SHA256 authentication with a runtime-only key and key ID, and uniquely binds source, subject/account, domain, security codes, activation/entitlement, and validity. A caller boolean or self-authored packet receipt is never authorization.
- Keep research decisions and realized outcomes in separate append-only ledger streams. An outcome must resolve to a strict Manifest/Raw evidence packet below the ledger root and be rehashed during append, verify, and seal; never accept caller-asserted evidence hashes. Secrets used for HMAC seals come only from runtime environment bytes.
- Every source-network scope requires `universe.json`, a fresh official/licensed identity artifact, and effective-dated bindings for every covered `security_code`. Interpret the membership date in `Asia/Kuwait`; `FULL_MARKET` additionally requires complete expected-universe reconciliation and substantive coverage for every expected member.
- Run `PYTHONPATH=src python3 scripts/smoke_check.py` and `PYTHONPATH=src python3 -m unittest discover -s tests -v` after changes.
