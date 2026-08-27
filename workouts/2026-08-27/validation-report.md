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
CONTROL_VALIDATOR: PASS — 10 required files, 28 control text files, 0 errors
CONTROL_UNIT_TESTS: PASS — 4/4 in 1.441 seconds
JSON_PARSE: PASS
GIT_DIFF_CHECK: PASS
PRIVATE_DRIVE_LINK_SCAN: PASS
SECRET_GUARD: PASS
```

The candidate full suite and exact-head CI have not run yet. Focused validation
repairs the identified control mismatch but is not evidence of market readiness.
