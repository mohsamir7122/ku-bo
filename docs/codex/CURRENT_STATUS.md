# KU-BO Current Codex Status

Status date: 2026-08-13

Repository:

```text
mohsamir7122/ku-bo
```

## Verified base and active branch

```text
main@92b2bdd2460a7508922297a12d85f13264d43acb
  └── agent/kuwait-120d-next-session
        └── Draft PR #14 / implementation@58a78042d5d509e599d2e273d793856b1dee14dd
              └── KU-BO-012 / IN_PROGRESS / DRAFT / CI 31733924569 PASS
```

PR #1 and PRs #4 through #13 are strict ancestors of the verified `main` head;
there is no remaining safe branch merge in that chain. PR #2 and PR #3 are 127
commits behind, non-mergeable, and superseded by current contracts. They must
not be merged or wholesale cherry-picked.

`EXPECTED_PR_MODE` remains `DRAFT` and `MERGE_ALLOWED` remains `NO`. The
conditional authority in `KU-BO-MERGE-004` applies only after the complete
local gates, publication of a Draft PR, exact-head GitHub Actions, and a fresh
merge-boundary review. Draft PR #14 is published and its implementation head
passed CI; this later control-record head still requires its own exact-head CI
before the merge-boundary review. No merge is claimed by this status record.

## Active KU-BO-012 implementation

The branch adds the product `KUWAIT_120D_NEXT_SESSION_RESEARCH` with:

- distinct 120-calendar-day context, 30-day active-event, 7-day community,
  and 72-hour fresh-catalyst windows;
- an incremental context corpus with a watermark;
- 59 non-search/non-storage candidate domains, 53 declared enabled-public
  catalog domains, and 52 distinct executable start-URL domains;
- a fair default plan of exactly 50 domains with incremental wave contributions
  `17/0/29/4`, reserving the final four for Archive/Community so `t.me` and
  `indexsignal.com` are attempted;
- official/regulatory, issuer/government, structured/editorial, then
  community/archive/routing waves;
- at most three transient attempts per strategy and four materially distinct
  strategies for a valid empty response; hard blocks never retry, 429 stops on
  the same strategy after exhaustion, and `Retry-After` is honored only within
  the remaining wall budget;
- explicit terminal treatment for login, CAPTCHA, paywall, robots, and access
  denial, with no bypass;
- append-only source-attempt records with Retry-After, disposition, proof, and
  limitation fields, plus deduplication before independence counting; the hash
  chain is not an external seal and the capture timestamp is not publication
  time;
- persisted-run validation that rehashes the Source Search report, attempt
  ledger, and referenced raw artifacts before integration;
- a strict parsed-input Schema and `build-kuwait-research-bundle` bridge that
  materializes context, exposure, and factor artifacts atomically without
  pretending to parse or derive missing semantics from raw bytes;
- normalized context events, evidence-bound security exposure, versioned
  factor snapshots, and one disposition row for every expected security;
- content-bound Factor Snapshots whose `factor_snapshot_sha256` covers complete
  rows, factors, evidence, dispositions, and scores; registry freshness windows
  include a 24-hour trading-status window, and superseded events cannot feed
  factors;
- Telegram and IndexSignal constrained to community sentiment or routing; and
- a strict replay contract for 40 decision sessions and 41 consecutive
  official sessions, with `STOP_BACKTEST` as the only exposed fail-closed
  outcome; unreachable `STOP_INFERENCE` was removed from this contract. The
  execution-grade replay derives ranks from scores, requires selected rows to
  equal Top-K and carry verified fills, keeps non-trading rows in the
  denominator, and stops on them while `KU-BO-008-D01` is open. Its primary
  adjusted-gross label is before costs; costs affect actionable and net-excess
  secondary metrics.

The branch remains `IN_PROGRESS` pending the merge boundary. Presence of these
contracts and modules, the completed local suite, and the successful Draft-PR
CI do not establish a live connector, real market coverage, or merge.

## Source catalog and capability status

```text
source_definitions:             68
independence_groups:            62
candidate_research_domains:              59  # search/storage excluded
declared_enabled_public_catalog_domains: 53
distinct_executable_start_url_domains:   52
default_fair_plan_domains:               50  # 17/0/29/4 incremental
DEFINED_ONLY:                   66
END_TO_END_TESTED:               2  # generated fixtures only
LIVE_OPERATIONAL:                0
```

Catalog presence and public reachability are not capability evidence. The two
end-to-end-tested parsers remain generated-fixture evidence only. Search,
storage, community, and reposts cannot manufacture an independent factual
confirmation.

## Latest-40 historical evaluation status

The requested real retrospective cannot produce a percentage from repository
contents. There is no admissible real point-in-time packet containing the full
historical universe, 41 official sessions, 40 sealed decision snapshots,
official/rights-compatible EOD, benchmark, status, Corporate Actions, and
separate outcomes.

```text
run_status: STOP_BACKTEST
process_valid_scoreable_sessions: 0
expected_decision_sessions: 40
metrics: null
agreement_rate: null
agreement_rate_status: NOT_APPLICABLE
authority_receipt_sha256: null
authority_verified: false
accuracy_claim_allowed: false
```

`agreement_rate=null/NOT_APPLICABLE` is presented to a human as `N/A`, not
`0%`. Zero is the number of eligible observations, so there is no valid
denominator for an accuracy calculation. The synthetic and generated fixtures
cannot be substituted for real market evidence.

## Local validation checkpoint

- Workflow/Source Orchestrator/Context/Integration/Replay/CLI targeted tests:
  `183/183 PASS`.
- Final current-tree full suite: `2,067/2,067 PASS` in `164.347s`.
- `compileall`, JSON checks, `git diff --check`, smoke, and Secret Guard:
  `PASS`; the 1,280-case corpus generation and audit also passed.
- Codex control check: `PASS` across 15 control text files and 10 required
  files, with 0 errors and 0 warnings.
- Final wheel: `PASS`, 444351 bytes, SHA-256
  `ee089ec3a7e100e81e1ef4a0378824c2b3e817db7d4c23d2d197b728b400c3a3`.
- Isolated install, imports, CLI help, and `validate-research-workflow`: `PASS`;
  `installed_data_foundation_check`: `PASS` with 8 semantic admissions and 8
  lineages.
- KU-BO-012 is published as Draft PR #14. Exact-head Run `31733924569` passed
  on implementation SHA `58a78042d5d509e599d2e273d793856b1dee14dd`, including
  Python 3.11, 3.12, 3.13, and 3.14. This later control-record update requires
  fresh exact-head CI; no merge exists.

## External and legacy evidence status

- Diagnostic provider artifacts remain metadata-only; authority, provenance,
  capture receipts, and rights are unresolved.
- July prediction/results material remains
  `UNTRUSTED_LEGACY_CLAIM / QUARANTINED` and cannot support training,
  backtesting, accuracy, or recommendation claims.
- No raw private conversation, real runtime market packet, credential, or
  licensed market byte was imported.
- `KU-BO-008-D01` remains `OPEN`; no product-specific treatment of halted or
  suspended outcome sessions has been approved.

## Still not proven

- exact-head GitHub Actions for this later control-record head, merge-boundary
  review, merge, or post-merge `main` CI;
- complete effective-dated historical market universe and full denominator;
- real rights-compatible Benchmark and Official Complete EOD packets;
- complete historical Corporate Actions and suspension/resumption evidence;
- authenticated provider capture authority or an independent final Data
  Foundation authority receipt;
- an approved product-specific outcome-session policy for `KU-BO-008-D01`;
- real Data Foundation qualification, backtest readiness, forecast skill,
  probability calibration, accuracy, recommendation, or production readiness.

## Active instruction

The only repository-native task record is:

```text
docs/codex/CURRENT_TASK.md
```

Historic handoffs, Drive copies, legacy conversations, PR #12 Test Specs, and
related-repository claims are context only. None can weaken current evidence,
rights, receipt, policy, or financial-safety gates.
