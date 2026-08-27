# PRE-FLIGHT — 2026-08-27

```text
RUN_ID: market-ai-20260827T020635Z-kuwait
STARTED_UTC: 2026-08-27T02:06:35Z
STARTED_ASIA_KUWAIT: 2026-08-27T05:06:35+03:00
STATUS: COMPLETED_WITH_RECORDED_BLOCKERS
```

## Contract integrity

- Read completely: 478 lines.
- SHA-256: `2720a8778ade69a7d53a1ac5aa4a12c518ef4f845819601b662b0046773733d2`.
- Runtime contract path is outside the repository; only its filename and digest
  are recorded here.

## Host and resources

| Check | Verified result |
| --- | --- |
| OS | Ubuntu 24.04, PRoot environment |
| Kernel/arch | Linux 6.17.0-PRoot-Distro, aarch64 |
| Disk | 464 GiB total, 297 GiB available, 37% used |
| Memory at check | 11 GiB total, 4.3 GiB available |
| Swap at check | 11 GiB total, 8.6 GiB available |
| Network | HTTPS request to GitHub returned HTTP 200 |
| Wake lock | `termux-wake-lock` succeeded |
| tmux | Existing `market-ai` process observed; PRoot could not access its tmux socket |

The PRoot process has existing phone-storage binds. This is a security/isolation
risk; this run writes only under the project workspace.

## Tools

| Tool | Version/result |
| --- | --- |
| Codex | codex-cli 0.148.0 |
| Git | 2.43.0 |
| GitHub CLI | 2.45.0 |
| Python | 3.12.3 |
| pip (system) | 24.0 |
| Node.js | v26.4.0 |
| npm | 11.18.0 |
| tmux | 3.4 |
| rclone | v1.74.4-termux |
| curl | 8.5.0 |

An ignored `.venv` was created for reproducible local tests and installed the
project's declared test extras, including `jsonschema 4.25.1`. No dependency
files were changed.

## GitHub and repository state

- GitHub CLI is authenticated as repository owner `mohsamir7122` over HTTPS;
  authentication scopes were checked without logging the token.
- Kuwait final repository: public, default `main`, unarchived, clean at
  `93e4cab09915a4a4b58455d3cc45eb48be4bd499`.
- Saudi final repository: public, default `main`, unarchived, clean at
  `8fd334e866c7917b3c4e15ece3f91166a0b5d99f`.
- Relevant private and archived source checkouts were clean and have local push
  URLs disabled. Private remote locators are intentionally omitted here.
- Kuwait and Saudi local rollback checkpoint branches were created at their
  exact starting SHAs. Kuwait work continues on a fresh branch; Saudi remains
  on `main` and is not modified.
- No GitHub repository Secrets or variables were listed for either final
  repository. Secret values were never requested or logged.

## Existing PR and CI observations

- Kuwait has eight open historical PRs. Three recent integration-source PRs are
  mergeable and five older PRs report conflicts. They are audit inputs only;
  none was merged or closed.
- The latest Kuwait `main` CI failed only in the unit/adversarial job.
- The latest Saudi documentation heads also failed unit/adversarial tests; its
  earlier integration merge head was green.
- Local Kuwait baseline reproduced the issue: 2,243 tests in 601.170 seconds,
  2,242 pass, one failure, zero errors. The failure is the stale expected branch
  in `test_codex_control`; there is no observed market-logic regression.

## Drive structure verification

The two project folders named by the runtime contract were listed read-only.
Both contain all 16 enumerated subfolders (`00` through `13`, plus `98` and
`99`). The contract text calls them 15 in one sentence but lists 16 names. No
Drive ID, URL, credential, or file bytes are persisted in Git.

## PRE-FLIGHT decision

Proceed on the reversible Kuwait task branch. Keep collection, model training,
real backtesting, live scoring, schedules, and merge fail-closed until their
specific evidence gates pass. Saudi remains second in sequence.
