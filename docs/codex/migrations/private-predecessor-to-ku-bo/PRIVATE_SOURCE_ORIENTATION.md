# Private predecessor source orientation

This public file intentionally contains no private repository locator, ref name,
commit or tree OID, file count, source path, private capability name, or audit
finding. The source is referenced only by the logical alias
`PRIVATE_PREDECESSOR_SOURCE`.

## Authorized read boundary

The active user has authorized read-only inspection of the configured private
source repository for this migration. That authorization is limited to repository
code and Git metadata needed to inventory and reimplement software capabilities.
It does not authorize:

- a write, branch change, archive, delete, or Git-history merge in the source;
- exporting credentials, tokens, cookies, sessions, connector locators, or keys;
- opening unrelated private storage, conversations, broker material, licensed
  datasets, runtime databases, or personal files; or
- copying private bytes or sensitive metadata into public KU-BO history.

If the configured source cannot be read through the normal authorized connector,
record the blocker. Do not broaden access or ask for credentials to be pasted into
the repository.

## Private runtime orientation record

At execution start, Codex must create an uncommitted private runtime record that
resolves the source alias and records:

- exact repository/ref/commit/tree locators;
- the method and time of verification;
- all materially unique refs;
- Git-blob path-occurrence totals and deterministic reconciliation digests;
- a privacy classification for every locator before any public summary; and
- a reversible mapping from opaque public IDs to private source locators.

The reversible mapping and exact private metadata stay outside Git. Public KU-BO
may contain only sanitized target contracts, opaque source IDs, safe aggregate
claims explicitly approved for publication, and non-sensitive evidence receipts.

## Discovery surfaces

The private census must examine source Skills, entrypoints, packages, scripts,
tools, tests, fixtures, policies, configuration, catalog entries, workflows,
knowledge assets, agent instructions, archives, and generated-looking artifacts.
User jobs are derived from behavior and tests, not only folder names.

Repeated implementations must be deduplicated into KU-BO core. Unsafe behavior is
recorded privately and represented publicly only by a sanitized negative control
and safe replacement contract. Source test outcomes never become live-readiness,
accuracy, access-rights, or financial claims.

## Completion evidence separation

`validate_private_predecessor_migration_control.py` validates preparation only. It
cannot claim source inventory, parity, package completion, exact-head CI, Draft-PR
state, live readiness, or migration completion.

Before any completion claim, the migration must add and pass a dedicated
completion validator that verifies, rather than merely accepts:

1. a private runtime source/ref/tree/blob reconciliation receipt;
2. sanitized item and user-job bindings with no sensitive locators;
3. target paths and semantic/negative test evidence that exist at exact HEAD;
4. full repository test, build, installed-wheel, and CLI receipts;
5. exact-head CI and Draft-PR state; and
6. an explicit `MERGE_NOT_PERFORMED` handoff.

The dedicated validator and its adversarial tests must be reviewed in the Draft
PR. This preparation package grants no merge, live activation, real backtest,
training, recommendation, or execution authority.
