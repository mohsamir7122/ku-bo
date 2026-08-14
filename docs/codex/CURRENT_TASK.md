# CURRENT TASK — KU-BO-013

```text
TASK_ID: KU-BO-013
STATUS: IN_PROGRESS
REPOSITORY: mohsamir7122/ku-bo
CONTROL_BASE_BRANCH: main
CONTROL_BASE_SHA: bafdda86b44b7603fe4adfa62dcc2a49bff8ae15
EXPECTED_NEW_BRANCH: agent/kuwait-historical-knowledge-layer
EXPECTED_PR_MODE: DRAFT
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
HISTORICAL_CORPUS_COLLECTION_REQUESTED: NO
BLOCKED_ON: LIVE_COLLECTION; OFFICIAL_COMPANY_UNIVERSE_ENUMERATION; SOURCE_RIGHTS_REVIEW
```

## Mission

Program, document, and test the planning foundation for six deep Kuwait
historical-research layers. Register credible starting sources and strict claim
roles now; do not execute the centuries-long collection or claim completeness.

## Required layers

1. Annual Kuwait history from 1500 through the as-of year.
2. Annual commercial events and crises from 1927.
3. Effective-dated registered-company lifecycle history from 1970.
4. Company news and media history from 1980, including later-created social
   platforms only after they existed.
5. Company, founder, and owner legal/economic cases for the rolling latest 20
   calendar years.
6. Important Kuwait commercial/economic events for the rolling latest 5
   calendar years.

## Acceptance gates

1. A strict source registry records authority tier, allowed roles, earliest
   year, access method, rights constraint, automation limitation, and explicit
   capability status.
2. All six layers compile into deterministic, gap-free annual tasks through a
   supplied as-of date; every task starts `NOT_COLLECTED`.
3. Company-year work remains blocked on official company-universe enumeration.
4. Founders, registration, and company status require primary identity
   evidence. News can corroborate but cannot replace it.
5. Legal records preserve allegation/procedural/finality status and never infer
   guilt. Social/community/Wikipedia evidence is routing or sentiment only.
6. Schemas cover the plan, historical event, and company annual history.
7. CLI validates the registry and can write a no-overwrite plan artifact.
8. Targeted tests, complete suite, compile, smoke, secret guard, JSON/Schema,
   control check, wheel, and exact-head CI pass.
9. A sanitized KU-BO-013 handoff and Draft PR are published. No merge occurs
   without a new explicit merge decision.

Do not merge this task. Record any later authority in
`docs/codex/USER_DECISIONS.md` and write the result using
`docs/codex/HANDOFF_TEMPLATE.md`.

## Safety and non-claims

- This task writes code, contracts, tests, documentation, and source URLs only.
- It does not scrape or reproduce the historical corpus.
- Source registration is `DEFINED_ONLY`, never `LIVE_OPERATIONAL`.
- No source absence proves that an event did not happen.
- The layer is `CONTEXT_ONLY`; it cannot directly emit a forecast, probability,
  rank, buy/sell recommendation, or execution instruction.
- Authentication, CAPTCHA, paywalls, robots controls, platform terms, privacy,
  and copyright must not be bypassed.
