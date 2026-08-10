# KU-BO Research Engine instructions

Open this directory as the project root.

## Codex control entrypoint

- In every new Codex session, read `CODEX_START_HERE.md` and the files under `docs/codex/` in the declared order before changing code.
- `docs/codex/CURRENT_TASK.md` is the single active task. Old conversations, archived prompts, and prior handoffs are historical context only.
- Continue through implementation, test, inspect, fix, and rerun cycles until the active acceptance gates pass or a genuine external/user-decision blocker is recorded.
- Never merge, force-push, permanently delete files/branches/conversations, or weaken a gate without explicit user authorization recorded in `docs/codex/USER_DECISIONS.md`.
- Raw private conversations stay outside Git. Only sanitized, non-personal technical summaries may enter the repository under `docs/codex/CONVERSATION_IMPORT_POLICY.md`.
- When a task ends, write a handoff using `docs/codex/HANDOFF_TEMPLATE.md` and distinguish `PROVEN`, `PARTIAL`, `BLOCKED`, `SYNTHETIC_ONLY`, `RECORDED_FIXTURE_ONLY`, and external-data dependencies.

## Research-engine rules

- Treat this checkout as version `0.1.0`: an auditable, non-production research foundation, not a live recommendation or execution service.
- Read `README.md` and the relevant contract in `docs/` before changing code.
- Keep raw evidence, normalized observations, features, forecasts, process assessments, and outcomes in separate artifacts.
- Use `research_network` as the default research mode. It requires a fresh per-run source packet, but not a complete historical archive or validated model.
- Keep `validated_forecast` as a separate strict mode. Never let a source-mosaic rank bypass its evidence-pack, model-card, sealing, or prospective-validation gates.
- Count independent publisher/origin groups, not URLs or reposts. The catalog currently contains 40 source definitions that resolve to 35 independence groups.
- A blocked Boursa Kuwait surface may leave research available only when a fresh, contributing official identity receipt from an independent fallback remains valid. Otherwise identity failure is structural. In either case, remove unavailable official confirmation and demote unconfirmed directional catalyst claims to `WATCH`.
- Treat all surfaces owned by one platform as one publisher group. Require each finding to declare valid `evidence_roles` and an eligible `fact_type`, bind its raw hash to the same source, match its `source_url` exactly to the referenced artifact URL, and match official catalyst confirmation by event key and direction.
- Restrict community sources to sentiment/risk and web archives to archive context. Search results and storage cannot create findings.
- A caller-provided capability name is never proof that the capability exists. Capabilities must be supported by a validated evidence manifest and capability report.
- Never bypass login, CAPTCHA, paywalls, rate limits, robots controls, or protected APIs.
- Treat public Boursa Kuwait trading pages as delayed. They may support delayed detection, but not live execution.
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
