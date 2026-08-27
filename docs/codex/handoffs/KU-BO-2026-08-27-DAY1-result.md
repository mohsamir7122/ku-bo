# KU-BO-2026-08-27-DAY1 — Security-by-security Kuwait collection contract

```text
FINAL_STATUS: PARTIAL
REPOSITORY: mohsamir7122/ku-bo
BASE_BRANCH: main
STARTING_SHA: 93e4cab09915a4a4b58455d3cc45eb48be4bd499
TASK_BRANCH: codex/kuwait-market-ai-day1-v1
FINAL_SHA: PUBLISHED_TASK_HEAD
DRAFT_PR: NONE
PR_BASE: main
CI_RUN: PENDING_AFTER_PUSH
STARTED_AT: 2026-08-27T02:06:35Z
COMPLETED_AT: 2026-08-27T11:56:00Z
```

## User goal

Change Kuwait collection from grouped/multi-security processing to an exact
security-by-security queue: finish every planned source for one security before
starting the next, expand and enumerate the source set requested by the owner,
and require the official company website as a first-class source for every
security.

## Verified starting state

- `main` remained at `93e4cab09915a4a4b58455d3cc45eb48be4bd499`.
- The task branch and its remote-tracking branch both started this change at
  `4cba33eb2e138475f747931332e4802929bfa169`.
- No PR or merge was authorized. The active task forbids force-push, permanent
  deletion, committed real data, training, and real backtesting.
- Prior work had a 990-shard market/source/date backfill contract, but it did not
  encode `security_code` as the outer work unit and remained blocked on a
  production checkpoint store.
- Real Kuwait security coverage, readable raw artifacts, observations, admitted
  events, training rows, and predictions were all zero and remain zero.

## Changes made

### Deterministic one-security coordinator

- Added `config/issuer_sequential_collection_policy.json` and
  `kubo.issuer_sequential_collection`.
- The policy fixes `security_grain=SECURITY`,
  `security_execution_mode=SECURITY_SEQUENTIAL`, numeric `security_code` order,
  and `max_active_securities=1`.
- Every security has exactly 29 source attempts in seven waves. All attempts
  must end with explicit terminal receipts before a security seal can release
  the next queue item. There is no first-success shortcut.
- Multiple securities issued by one company remain independent queue entries.
- Plans are rebound to an externally reopened issuer universe and canonical
  source configuration; recomputing a forged plan hash cannot replace security
  identities or source obligations.

### Sources and official company website

- Expanded the catalog to 71 source definitions in 65 independence groups.
  Capability status remains 69 `DEFINED_ONLY`, two fixture-only
  `END_TO_END_TESTED`, and zero `LIVE_OPERATIONAL`.
- Added rights-gated LSEG Workspace and runtime/entitlement-gated AlphaStocks
  definitions. The per-security denominator also includes Boursa Kuwait, CMA /
  iFSAH, KCC/Maqasa, Investing, Yahoo, Reuters, KUNA, AlQabas, Alanba, other
  structured/editorial sources, IndexSignal, three Telegram channels, and a web
  search router.
- `issuer_ir_verified` is mandatory for every security. No domain is inferred.
  A positive or verified-zero result requires a reopened HMAC-SHA256 runtime
  trust registry matching issuer, security, domain, validity interval, key ID,
  and registry digest.
- Reuters/LSEG copied material keeps Reuters as the publisher origin so it is
  not counted as a second independent confirmation. Community and search sources
  remain discovery-only.

### Receipts, schemas, CLI, and safety

- Added strict policy, plan, and run JSON schemas plus safe exclusive/no-
  overwrite writers.
- Added CLI commands to validate the policy, compile and reopen a plan, and
  reopen a run receipt. No live execution CLI is exposed before adapters are
  admitted.
- Run validation recomputes receipt hashes, per-security hash chains, counts,
  identities, and time bounds. Its success status explicitly proves internal
  consistency only; artifact manifests still require independent reopening by
  the ingestion layer.
- Hardened source-role matching and preserved fail-closed recovery behavior in
  runtimes where the current process's `/proc` entry is unavailable.

## Validation performed

```text
COMMAND_OR_JOB: PYTHONPATH=src python3 -m unittest -q tests.test_issuer_sequential_collection tests.test_source_network tests.test_source_access_recipes tests.test_kuwait_workflow_cli
RESULT: PASS
DETAIL: 84/84 in 0.687 seconds; the dedicated sequential module contributes 26 tests.

COMMAND_OR_JOB: PYTHONPATH=src python3 -m unittest -q tests.test_recovery tests.test_recovery_adversarial tests.test_cli_research_ledger
RESULT: PASS
DETAIL: 38/38 in 0.178 seconds.

COMMAND_OR_JOB: PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -q
RESULT: PASS
DETAIL: 2502/2502 in 195.597 seconds; 0 failures and 0 errors.

COMMAND_OR_JOB: compile, strict JSON/schema, control, bootstrap, migration-control, smoke, whitespace, and Secret Guard gates
RESULT: PASS
DETAIL: 170 JSON files; 107 schema metaschemas; 31 control text files; 10 required control files; 0 control warnings/errors; PASS_HANDOFF_CONTRACT; PASS_PREPARATION_CONTROL; Secret Guard PASS.

COMMAND_OR_JOB: isolated wheel build/install and installed CLI smoke
RESULT: PASS
DETAIL: 605193-byte wheel; validate-config, policy validation, one-security/29-attempt synthetic plan generation, and external plan reopening passed. SHA-256 fb6625fc8f6f4eb930366d5c149a6000e444e59cede34db6cf76b0e577954b72.

COMMAND_OR_JOB: GitHub exact-head CI on PUBLISHED_TASK_HEAD
RESULT: SKIPPED
DETAIL: pending until the candidate commit is pushed; Python 3.11–3.14 are required before merge consideration.
```

## Evidence and data status

- `SYNTHETIC_ONLY`: queue order, one-active-security enforcement, 29 terminal
  receipts, seals, hash chains, official-site trust binding, entitlement gates,
  plan/run reopening, and adversarial rejection behavior.
- `PARTIAL`: source catalog and access definitions. Four planned sources still
  lack complete access recipes: `issuer_ir_verified`,
  `authorized_broker_feed`, `alphastocks_authorized_connector`, and
  `web_search_router`.
- `BLOCKED`: real complete issuer/security universe, populated official-site
  authority registry, admitted live adapter set, security-aware durable
  checkpoint v2, and exact-head CI.
- `LIVE_DEPENDENT`: source access, raw bytes, real observations, company
  dossiers, Drive publication, and scheduled execution.
- `LICENSED_FEED_DEPENDENT`: LSEG, AlphaStocks, ICE, and broker-feed results.
- `PROVEN_REAL_EVIDENCE`: none added by this stage.

## Claims allowed

- The branch implements and locally tests a deterministic one-security-at-a-time
  collection contract.
- Each input-universe security receives the same exact 29-source, seven-wave
  attempt denominator.
- The official issuer website is mandatory and cannot be positively accepted
  without a signed runtime authority binding.
- The software fails closed on missing sources, missing rights, incomplete
  receipts, and an attempt to start the next security early.

## Claims still forbidden

- Real backtest readiness: forbidden; no admitted dataset exists.
- Forecast accuracy or probability: forbidden; no training or locked test ran.
- Recommendation: forbidden; no buy/sell output is authorized.
- Full-market coverage: forbidden; no real complete Boursa Kuwait universe has
  been admitted.
- `LIVE_OPERATIONAL` source status: forbidden; the count remains zero.
- Complete company dossier or artifact authenticity: forbidden; receipt content
  hashes alone do not prove either.

## Privacy and repository safety

The branch contains no credentials or sessions, private Drive IDs, raw
conversations, real runtime market data, or licensed bytes. No destructive
cleanup, force-push, PR creation, or merge was performed.

## User decisions required

None for this software-contract stage. Real execution requires separately
authorized source access, licensed entitlements where applicable, an admitted
issuer/security universe, and private runtime trust material.

## Items classified for retention

- `KEEP`: sequential policy, coordinator, schemas, CLI validators, tests, Arabic
  operator guide, source definitions, and this handoff.
- `REFACTOR`: connect admitted live adapters and a security-aware checkpoint v2
  behind the existing injected boundaries.
- `SUPERSEDE`: treat legacy 990 market/source/date shards as a historical audit
  package, not evidence of security-by-security collection.
- `PRIVATE_ONLY`: real source files, official-domain registry, HMAC key,
  entitlements, checkpoints, and Drive publication receipts.
- `DELETE_CANDIDATE`: none.

## Known limitations and risks

- The exact input universe may itself be incomplete; `EXACT` means exact against
  its declared codes, not proof of all Boursa Kuwait securities.
- No live adapter is included for the 29-source denominator. A planned source
  can therefore only be marked with an explicit blocked receipt until admitted.
- The existing production workflow still fails closed at
  `COLLECTION_ADAPTER_NOT_ADMITTED` or `BLOCKED_CHECKPOINT_STORE`.
- The official-domain registry is intentionally external and currently has no
  public entries. No issuer website can be claimed bound from this repository.
- Exact-head CI is pending after push, so this result remains `PARTIAL`.

## Smallest logical next task

```text
TASK_ID: KU-BO-M0-REAL-SECURITY-PROOF
PROPOSED_BRANCH: codex/kuwait-one-security-real-proof-v1
DEPENDENCY: Stage 8 exact-head CI; one real admitted issuer/security universe; authorized source access; signed official-domain registry; durable security-aware checkpoint store.
GOAL: Execute one real Kuwait security through all 29 planned source attempts, preserving every terminal receipt and at least one rights-admitted raw artifact, then seal and independently reopen the package without starting a second security.
ENTRY_GATE: rights, provenance, runtime trust, source adapter, checkpoint, Secret Guard, and no-real-data-in-Git gates pass.
EXIT_GATE: one real security; 29/29 terminal receipts; official-site binding verified; raw artifact reopened with SHA-256; per-security seal valid; durable reopen PASS; zero training/backtest/forecast actions.
```

`MERGE_NOT_PERFORMED`.
