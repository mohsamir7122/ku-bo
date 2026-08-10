# KU-BO User Decision Queue

Codex must not execute a permanent deletion, scope expansion, gate weakening, licensing decision, credential use, paid service action, or merge without an explicit user decision.

## Decision format

Copy this block for every required decision:

```text
DECISION_ID:
STATUS: OPEN | APPROVED | REJECTED | DEFERRED
DATE_RAISED:
TARGET:
CATEGORY: DELETE | ARCHIVE | SCOPE | LICENSING | CREDENTIALS | MERGE | DATA_SOURCE | OTHER
CURRENT_STATE:
WHY_A_DECISION_IS_REQUIRED:
OPTIONS:
1.
2.
3.
CODEX_RECOMMENDATION:
CONSEQUENCE_OF_APPROVAL:
CONSEQUENCE_OF_REJECTION:
SAFER_REVERSIBLE_ALTERNATIVE:
USER_DECISION:
DECIDED_AT:
DECIDED_BY:
IMPLEMENTED_IN_BRANCH_OR_PR:
```

## Open decisions

No open decisions were recorded when this control layer was created.

## Rules

- Do not convert silence into approval.
- Do not delete a conversation merely because a summary was imported.
- Do not delete a repository file until references and tests have been checked.
- Prefer reversible archive or deprecation before deletion.
- Do not merge stacked PRs out of order.
- If a decision becomes unnecessary because the implementation changed, mark it `DEFERRED` or explain why it was withdrawn; do not erase the history.
