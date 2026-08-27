# Validation Report

## Baseline

```text
COMMAND: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
RESULT: FAIL
TOTAL: 2243
PASS: 2242
FAILURES: 1
ERRORS: 0
DURATION_SECONDS: 601.170
```

Failure: the completed task's `EXPECTED_NEW_BRANCH` had become `main`, while the
strict test still expected `codex/kuwait-engine-integration-v1`. This is a
pre-existing control consistency failure, not evidence of a model, data, or
market-logic regression.

## Candidate focused validation

```text
CONTROL_VALIDATOR: PASS — 10 required files, 30 control text files, 0 errors
TARGETED_CONTROL/PARITY/LIFECYCLE TESTS: PASS — 57/57
SOURCE_EVIDENCE_LIFECYCLE TESTS: PASS — 30/30
JSON_PARSE: PASS
GIT_DIFF_CHECK: PASS
PRIVATE_DRIVE_LINK_SCAN: PASS
SECRET_GUARD: PASS
COMPILEALL: PASS
```

## Candidate full-suite progression

The first Stage 1 full run executed 2,272 tests in 510.706 seconds and correctly
failed with one error and one failure: the active task omitted two frozen legacy
migration markers, and a CLI test still expected fourteen resolved capabilities.
The markers were restored as historical references without changing the current
base or work branch, and the expected capability count was updated to fifteen.

The next full run passed 2,272/2,272 tests in 514.661 seconds. Review then found
that an invalid input row could be reflected in a quarantine report. The report
was changed to retain only bounded identifiers plus a SHA-256 digest, and a
negative non-reflection test was added.

```text
FINAL_COMMAND: PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
FINAL_RESULT: PASS
TOTAL: 2273
PASS: 2273
FAILURES: 0
ERRORS: 0
DURATION_SECONDS: 490.736
```

## Dry-work and packaging

- Two independent synthetic reconciliation outputs were byte-identical.
- Status: `STRUCTURE_AND_RECONCILIATION_VALID_ONLY`.
- Evidence class: `SYNTHETIC_FIXTURE`.
- Report file SHA-256:
  `5ae248159d5e60a15184ffee978a3e1bd92e8faf5460ff8149fbbbc81f12125f`.
- Internal report SHA-256:
  `74514ea6d6fbf6b36f9a74de59582817720ddcc626bbf9aba8c01e8f9a954b5f`.
- Existing live dry-run replay remained fail-closed at
  `PROBE_AUTHORIZED_SOURCE_ACCESS`, with 10 receipts, zero candidates, and no
  sealed output.
- The first local wheel attempt failed because the test virtual environment did
  not contain `setuptools.build_meta`; it is recorded as an environment/setup
  failure. A corrected isolated build using the pinned build dependency passed.
- Final wheel SHA-256:
  `18054cfb35c547d78ca137dbf10ea38615ed9aedfb49127f9d46d466ded29cad`.
- Fresh-environment install, `validate-config`, and reconciliation CLI smoke: PASS.

Exact-head GitHub CI has not run because the Stage 1 commit has not yet been
pushed. These results prove local software behavior only, not real source access,
company coverage, model training, blind-test validity, market readiness, or
investment performance.
