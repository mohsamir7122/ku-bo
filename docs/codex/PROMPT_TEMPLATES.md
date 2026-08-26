# KU-BO Codex Prompt Templates

These are reusable fallbacks. The single active instruction remains `CURRENT_TASK.md`.

## Audit template

```text
Open mohsamir7122/ku-bo. Read AGENTS.md, CODEX_START_HERE.md, and docs/codex in the required order. Verify the live branch, HEAD SHA, open stacked PRs, and CI. Run the full test suite. Audit the requested capability against code, tests, schemas, runtime evidence, and claim boundaries. Do not modify, merge, delete, or weaken gates. Report PROVEN, PARTIAL, BLOCKED, SYNTHETIC_ONLY, and LIVE_DEPENDENT findings with exact evidence.
```

## Implement template

```text
Open mohsamir7122/ku-bo. Read the control files and execute docs/codex/CURRENT_TASK.md only. Verify the base branch and create the declared task branch. Implement in coherent units, run targeted tests after each unit, then the complete required suite. Fix failures caused by your changes. Push the branch and open a Draft PR against the correct stacked base. Do not merge, force-push, delete, commit private data, or fabricate evidence. Write the required handoff.
```

## Resume template

```text
Resume the active KU-BO task. First inspect git status, current branch, remote HEAD, Draft PR, CI, and docs/codex/CURRENT_TASK.md. Read the latest handoff and identify the last proven checkpoint. Preserve valid existing work, do not restart blindly, and continue through test/fix cycles until the acceptance gates pass or a genuine blocker is recorded. Do not merge or delete.
```

## Fix CI template

```text
Inspect the failing GitHub Actions checks for the active KU-BO task branch. Reproduce each failure locally when possible, identify root cause, and distinguish branch-caused failures from external/transient failures. Apply the smallest correct fix without weakening tests or claim boundaries. Run targeted and full relevant tests, push to the same task branch, update the Draft PR, and update the handoff. Do not merge.
```

## Review template

```text
Review the active KU-BO Draft PR against its CURRENT_TASK, AGENTS.md, acceptance gates, actual changed files, tests, CI, and evidence boundaries. Check temporal leakage, denominator completeness, source and hash binding, corporate-action semantics, status history, privacy, secrets, destructive behavior, and overclaiming. Give PASS/FAIL evidence for each exit gate. Do not merge or modify unless the user explicitly requests fixes.
```

## Conversation migration template

```text
Inspect the named private conversation or command document under the Drive control folder. Do not copy it into GitHub. Extract only unique technical decisions or requirements, compare them with current code/docs/tests, classify each item under the conversation policy, and prepare a sanitized summary. Put deletion or ambiguous retention proposals in USER_DECISIONS.md. Never expose personal or unrelated material.
```

## Private predecessor complete-capability migration template

```text
Open mohsamir7122/ku-bo and continue the existing branch agent/private-predecessor-capability-migration-v1. Read CODEX_START_HERE.md, run the locked bootstrap and preparation-control validators, and resolve PRIVATE_PREDECESSOR_SOURCE only from the private locator supplied in this ChatGPT session. Keep exact source metadata in uncommitted private runtime storage. Execute CURRENT_TASK plus PRIVATE_PREDECESSOR_MIGRATION_EXECPLAN.md: reconcile every Git-blob occurrence privately, derive every user job, publish only privacy-reviewed sanitized target contracts and opaque bindings, reimplement safe behavior under src/kubo, keep Skills thin, add semantic/negative tests and the dedicated evidence-verifying completion validator, and update the one Draft PR. Do not merge, force-push, modify/archive the source, broaden private access, publish private metadata, train, run a real backtest, or promote anything to LIVE_OPERATIONAL.
```
