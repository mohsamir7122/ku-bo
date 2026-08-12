# KU-BO Current Codex Status

Status date: 2026-08-12

Repository:

```text
mohsamir7122/ku-bo
```

## Verified live chain

```text
main@be5fe3883016dedf07fa680905f7199f3906b4d8
  └── build/tri-security-pilot-v0.3@7d032c98b0ef9f27e913199487ad4577119c2631
        └── Draft PR #10 / GitHub Actions 31571987659 PASS
              └── build/tri-security-run-receipt-v0.1@9c72e0d89f46ee846cb453087b00f7e6b64ace7a
                    └── Draft PR #11 / GitHub Actions 31626453749 PASS
```

PRs #4 through #9 are merged into `main`. PR #10 is the verified dependency
candidate for the tri-security preparation layer and remains Draft. Open PRs
#2 and #3 are stale, conflicting, and based on pre-stack history; they are not
an authority or safe base for current work. No merge, force push, auto-merge,
PR closure, or destructive cleanup is authorized by the current task.

## Proven by the KU-BO-009 dependency

- deterministic three-security batches, beginning with KFH/SHIP/AZNOULA;
- exact scoped configuration and a non-overwriting qualification workspace;
- every candidate identity remains `UNVERIFIED_SEED`;
- every final Data Foundation gate remains `PENDING_EXTERNAL_EVIDENCE`;
- later batches remain locked and preparation does not collect market bytes;
- exact-head Linux CI passed on Python 3.11 through 3.14.

## KU-BO-010 contract published as a green Draft

The task adds a standalone authenticated Run Receipt and Stage Binding layer:

- the Run Receipt rehashes and binds the exact batch plan, scoped manifest,
  workspace report, run, batch-one cohort of exactly three securities,
  qualification window, registry, and pending gate state;
- `run_date` is derived from the issue instant in `Asia/Kuwait`, and receipt
  validity is bounded to seven days;
- the Stage Binding authenticates with a second independent runtime-only HMAC
  key and binds both the declared artifact inventory and the complete stage
  file tree;
- run and stage outputs must remain in disjoint external roots, and existing
  output roots, symlinks, special files, traversal, drift, cross-run mixing,
  expired receipts, unknown fields, or changed bytes fail closed;
- the inherited five-security Benchmark registry is explicitly incompatible
  with the tri-security cohort because Industrials and Utilities sector series
  are missing. The receipt preserves that incompatibility and forbids
  Benchmark qualification, a five-security denominator, and a full-market
  claim.

The contract is an authenticated binding, not market evidence. KU-BO-010 does
not yet force existing identity, status, price, Benchmark, EOD, or final
reconciliation commands to consume these receipts. That mandatory downstream
enforcement is the sole boundary of KU-BO-011.

The implementation is published in stacked Draft PR #11. Exact-head GitHub
Actions run `31626453749` passed Python 3.11 through 3.14; no merge or
auto-merge was requested. The sanitized result is
`docs/codex/handoffs/KU-BO-010-result.md`.

## External and legacy evidence status

- GitHub repository, PR, Actions, and related-repository access were verified.
- The connected Drive control folder was readable but stale at KU-BO-008
  compared with the GitHub KU-BO-009 authority. Price-collection reports,
  manifests, and quarantine folders contained no qualifying run receipt.
- Diagnostic Yahoo/yfinance artifacts were metadata-only and were not promoted
  because authority, provenance, capture receipts, and rights remain unresolved.
- The shared July prediction/results page was reachable and its presence was
  verified, but it is classified `UNTRUSTED_LEGACY_CLAIM / QUARANTINED`.
  No raw conversation was imported. It lacks authenticated market-byte
  manifests, point-in-time lineage, denominator and status evidence, approved
  outcome policy, and a reproducible authenticated run; it cannot support
  training, backtest, accuracy, or recommendation claims.
- The private conversation archive was deliberately not opened or copied.

## Still not proven

- complete effective-dated historical market universe;
- real rights-compatible Benchmark and Official Complete EOD packets;
- complete historical Corporate Actions and suspension/resumption evidence;
- authenticated provider capture authority or an independent final Data
  Foundation authority receipt;
- mandatory Run Receipt/Stage Binding checks in every downstream importer and
  final reconciliation;
- an approved product-specific outcome-session policy for `KU-BO-008-D01`;
- real Data Foundation qualification or baseline-backtest readiness;
- forecast skill, probability calibration, prospective accuracy, or any
  trading recommendation;
- production execution or authorization of a later tri-security batch.

## Active instruction

The only repository-native task record is:

```text
docs/codex/CURRENT_TASK.md
```

Historic handoffs, Drive copies, legacy conversations, and related repository
claims are context only. None can weaken current evidence, rights, receipt,
policy, or financial-safety gates.
