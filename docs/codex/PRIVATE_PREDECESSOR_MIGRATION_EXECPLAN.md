# Private predecessor to KU-BO capability-migration ExecPlan

This is the authoritative execution sequence for `KU-BO-MIG-001`. KU-BO is
public; the predecessor source is private. Public Git history therefore stores
only its logical alias, opaque bindings, sanitized target contracts, and evidence
that has passed an explicit privacy review.

## Architectural decision

KU-BO remains the only canonical codebase, package, engine, CLI, evidence model,
and decision boundary. The configured private predecessor is a read-only source
of software user jobs and implementation lessons. Do not merge its Git history,
vendor a second engine, or preserve unsafe behavior merely for textual parity.

```text
TARGET:                    mohsamir7122/ku-bo
SOURCE_ALIAS:              PRIVATE_PREDECESSOR_SOURCE
SOURCE_READ:               CODE_AND_GIT_METADATA_ONLY
SOURCE_LOCATORS:           PRIVATE_RUNTIME_ONLY
SOURCE_WRITES:             FORBIDDEN
TARGET_PACKAGE:            src/kubo
TARGET_CLI:                kubo
SKILL_POLICY:              THIN_WRAPPERS_OVER_KUBO_CORE
FINAL_PR:                  DRAFT_ONLY
PREPARATION_IS_COMPLETION: NO
```

Software parity and operational evidence are separate. Implementation cannot
infer data rights, source access, predictive skill, accuracy, probability,
recommendation quality, or investment readiness.

## Global invariants

- Read the private source only through the normally authorized connector and only
  for repository code and Git metadata needed by this task.
- Keep exact source repository/ref/commit/tree locators, filenames classified as
  sensitive, counts, audit findings, and reversible opaque mappings in
  uncommitted private runtime storage.
- Never request, expose, export, or commit credentials, tokens, sessions, cookies,
  connector IDs, private URLs, or unrelated private bytes.
- Use one migration branch and one Draft PR with coherent checkpoint commits.
- Preserve the public KU-BO dependency chain and every pre-existing safety gate.
- Continue independent software work when an operational capability is externally
  blocked. Do not turn an access blocker into a software-parity exemption.
- Stop for merge, force-push, deletion/archive, source mutation, broader private
  access, paid/licensed activation, training, real backtest, live activation,
  material product-behavior choice, or financial execution.

## Phase 0 — Safe orientation and public baseline

### Actions

1. Verify the KU-BO remote, task branch, public base SHA, stacked PRs, working
   tree, mergeability, and exact-head CI.
2. Run the live-bootstrap and preparation-control validators.
3. Resolve `PRIVATE_PREDECESSOR_SOURCE` privately from the user-provided connector
   context. Confirm read-only code/Git-metadata access without exporting its
   locator or credentials.
4. Create an uncommitted private orientation record with exact source refs and
   verification method.
5. Run the KU-BO baseline compile, focused controls, full suite, smoke, Secret
   Guard, wheel build/install, and installed CLI.
6. Confirm no source write and no source-history merge occurred.

### Exit gate

- Public base/PR/CI state is exact and current.
- Preparation validators pass.
- Private source orientation exists outside Git and contains no unrelated data.
- Baseline failures are classified as environmental, pre-existing, or task-caused.

## Phase 1 — Private source census and authenticated receipt

### Private actions

1. Enumerate every Git-blob path occurrence across the primary ref, the known
   reference role, and every other materially unique ref.
2. Inspect Skills, entrypoints, packages, scripts, tools, tests, fixtures,
   policies, configuration, catalog entries, workflows, knowledge assets, agent
   instructions, archives, and generated-looking artifacts.
3. Compute commit/tree/blob identities, content hashes, per-ref totals, duplicate
   links, and a deterministic object-multiset reconciliation.
4. Privacy-classify every source locator before producing any public row.
5. Bind every item to opaque capability and user-job IDs and assign one private
   disposition: direct port, KU-BO rewrite, knowledge only, negative control,
   duplicate, private only, unsafe rejection, or unrelated.
6. Create a tamper-evident private runtime receipt binding the source resolution,
   exact refs, reconciliation, opaque mapping, and inspection time.

### Public output

- Store only an opaque receipt ID, sanitized rows that passed `SAFE_TO_PUBLISH`,
  target paths, and non-sensitive reasons.
- Do not publish exact source locators, Git OIDs, private counts, sensitive paths,
  private capability names, weaknesses, or raw source content.

### Exit gate

- The private census reconciles to zero unaccounted Git-blob occurrences.
- Every relevant item has a capability/user-job binding and disposition.
- The private receipt can be reopened and independently revalidated at runtime.
- The public manifest leaks no private metadata.

Broad capability implementation must not begin before this private exit gate.

## Phase 2 — User-job denominator and KU-BO architecture map

### Actions

1. Derive user jobs privately from behavior, tests, entrypoints, and documentation;
   folder names alone are insufficient.
2. Map opaque seeds and all discoveries to sanitized KU-BO target contracts only
   after privacy review.
3. For every legitimate user job define input, output, failure, evidence, time,
   source-dependency, and operational-ceiling contracts.
4. Assign one canonical KU-BO module and CLI/internal API plus an optional thin
   repository Skill.
5. Bind semantic, malformed-input, blocked-source, zero-result, identity,
   Point-in-Time, resume/idempotency, privacy, and claim-boundary tests.
6. Build an acyclic dependency graph. Shared foundations precede wrappers; a
   parallel package/engine/registry is rejected.

### Exit gate

- The private denominator contains every discovered legitimate user job.
- Every public job row is sanitized and bound to one canonical target or a precise
  operational blocker after software parity.
- No source name/path/ref/OID or sensitive finding appears in Git.

## Phase 3 — Dedicated completion validator

The preparation validator deliberately cannot report migration completion. Before
implementation phases can ultimately close, add a separate completion validator
and adversarial tests that verify evidence rather than trusting status fields.

It must re-open and validate:

1. the private source runtime receipt against the configured source and exact
   commit/tree/blob inventory;
2. every sanitized public item/user-job/capability binding against the private
   opaque mapping without emitting private values;
3. target modules, CLI routes, Skill wrappers, and semantic/negative test IDs at
   exact KU-BO HEAD;
4. full-suite, build, installed-wheel, installed-CLI, smoke, Secret Guard, and
   claim-boundary receipts tied to exact HEAD;
5. exact-head CI conclusion and Draft-PR state from GitHub; and
6. the final sanitized handoff and `MERGE_NOT_PERFORMED` statement.

Self-reported counts, Git OIDs, evidence IDs, statuses, or blockers are not enough.
A missing private receipt, nonexistent target/test, stale SHA, non-Draft PR,
failing CI, or unresolved software blocker must fail closed.

## Phase 4 — Shared migration foundation

Implement shared pieces used across multiple private-discovered user jobs:

- provenance-bound opaque migration registry;
- thin project-Skill discovery under `.agents/skills`;
- canonical CLI routing and installed-wheel entrypoint checks;
- transport-versus-semantic-success separation;
- source certainty versus analytical certainty;
- receipt, retry, cursor, checkpoint, idempotency, and no-overwrite contracts;
- private/runtime/public storage boundaries; and
- common claim-boundary and parity-test helpers.

Do not duplicate stronger KU-BO contracts. Scaffolding cannot promote a source or
capability.

## Phase 5 — Capability reimplementation

Implement privately discovered jobs in dependency order, grouped by their safe
KU-BO target foundations. For every job:

1. preserve its legitimate user outcome, not its old file layout;
2. reimplement unsafe authorization, static confidence, leakage, fabricated
   labels, or evidence promotion as a negative control plus safe replacement;
3. keep raw/parsed/finding, identity, time, source-role, and operational-evidence
   boundaries explicit;
4. add semantic happy-path and adversarial tests;
5. invoke the canonical KU-BO path through the intended API/CLI and thin Skill;
6. update the private receipt and sanitized public matrix without exposing source
   metadata; and
7. keep live/private/licensed dependencies explicit and disabled.

Allowed pre-validation outputs remain research-only states such as `WATCH` and
`ABSTAIN`. No training or real backtest is authorized.

## Phase 6 — Complete parity, packaging, and Draft publication

### Actions

1. Revalidate the private source census and complete user-job denominator.
2. Confirm every legitimate job has a safe tested KU-BO path; operational blockers
   may remain only after software parity is proven.
3. Run the dedicated completion validator and all repository/package gates.
4. Exercise every canonical CLI and applicable thin Skill from source and an
   isolated installed wheel.
5. Update public docs, sanitized manifest/matrix/status, and handoff with only
   privacy-reviewed evidence and consistent counts that are authorized to publish.
6. Push without force and update the same Draft PR.

### Completion gate

`COMPLETE_CAPABILITY_MIGRATION` may be claimed only when the dedicated validator,
not this preparation validator, verifies every Phase 3 receipt at exact HEAD.
AI-source mutation, a second engine, private-data publication, a software blocker,
failing package/CI evidence, or a non-Draft PR blocks completion.

The handoff must state `MERGE_NOT_PERFORMED`. Completion never authorizes merge,
archive/delete, training, real backtesting, live activation, recommendation, or
financial execution.

## Checkpoint reporting

After each phase, update the public status with sanitized facts only. Keep exact
private source locators/counts/findings in the runtime receipt. Public checkpoints
record phase, public KU-BO start/end SHA, opaque receipt ID, sanitized item/job
counts only when approved for publication, tests, allowed/forbidden claims,
decisions required, and the next phase.
