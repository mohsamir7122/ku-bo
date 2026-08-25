# CURRENT TASK — KU-BO-MIG-001

```text
TASK_ID: KU-BO-MIG-001
STATUS: READY
REPOSITORY: mohsamir7122/ku-bo
CANONICAL_REPOSITORY: mohsamir7122/ku-bo
PRIVATE_SOURCE_ALIAS: PRIVATE_PREDECESSOR_SOURCE
CONTROL_BASE_BRANCH: agent/ku-bo-016-codex-live-bootstrap
CONTROL_BASE_SHA: 6e9ab870e727494d5eb9e1ec9fa98829d6391d68
EXPECTED_NEW_BRANCH: agent/private-predecessor-capability-migration-v1
EXPECTED_PR_BASE: agent/ku-bo-016-codex-live-bootstrap
EXPECTED_PR_MODE: DRAFT
MIGRATION_MODE: COMPLETE_CAPABILITY_REIMPLEMENTATION
PRIVATE_SOURCE_REPOSITORY_READ_ALLOWED: YES
PRIVATE_SOURCE_READ_SCOPE: CODE_AND_GIT_METADATA_ONLY
SOURCE_REPOSITORY_WRITE_ALLOWED: NO
PRIVATE_RUNTIME_DATA_ACCESS_ALLOWED: NO
CREDENTIAL_EXPORT_ALLOWED: NO
MERGE_ALLOWED: NO
FORCE_PUSH_ALLOWED: NO
PERMANENT_DELETE_ALLOWED: NO
REAL_DATA_COMMIT_ALLOWED: NO
PRIVATE_CONVERSATION_COMMIT_ALLOWED: NO
MODEL_TRAINING_ALLOWED: NO
REAL_BACKTEST_ALLOWED: NO
LIVE_ACTIVATION_ALLOWED: NO
FINANCIAL_EXECUTION_ALLOWED: NO
BLOCKED_ON: PRIVATE_SOURCE_CENSUS; VERIFIED_COMPLETION_RECEIPTS; SEMANTIC_PARITY
```

## User goal

Make KU-BO the single canonical software-capability superset of the configured
private predecessor. Every legitimate task available through that source must
gain a safe, documented, tested KU-BO path. This is a capability
reimplementation, not a blind Git merge or preservation of unsafe behavior.

## Start and resume contract

1. Open KU-BO at the Git root and read `CODEX_START_HERE.md` in order.
2. Run the locked live-bootstrap and private-predecessor preparation validators.
3. Verify the public KU-BO PR chain, exact task branch, and CI live.
4. Continue the existing expected branch; never create a parallel migration.
5. Resolve the private source alias only from the user-provided authorized
   connector context. Keep repository/ref/commit/tree locators private.
6. Read and execute `docs/codex/PRIVATE_PREDECESSOR_MIGRATION_EXECPLAN.md` phase by
   phase.

If the public branch chain differs, preserve work and record drift. Integrate an
updated KU-BO base only through normal non-force task-branch history when existing
policy permits; otherwise record a decision request. Never rewrite published
history, merge private-source history, merge the Draft PR, or silently discard a
user change.

## Authorized source boundary

Read-only access to private source repository code and Git metadata is explicitly
authorized for this task. This narrow grant does not include unrelated private
storage, conversations, personal data, broker material, licensed datasets,
runtime databases, credentials, tokens, cookies, sessions, connector locators,
or secret keys. It does not authorize any source write, branch change, archive,
delete, or history merge.

Exact source metadata and reversible opaque mappings live only in uncommitted
private runtime storage. Public KU-BO receives sanitized target contracts and
opaque bindings only after privacy review.

## Mission requirements

### Private exhaustive census before broad implementation

- Inventory every Git-blob path occurrence across every materially unique source
  ref, including Skills, packages, scripts, tools, tests, fixtures, policies,
  configuration, catalogs, workflows, knowledge, agent instructions, and archives.
- Reconcile exact source commit/tree/blob identities, counts, duplicate links, and
  content hashes in a private runtime receipt.
- Derive user jobs from behavior and tests, not only folder names. The fourteen
  public opaque seeds are a minimum, not a capability definition or denominator.
- Privacy-review every locator before public output. Sensitive locators stay
  private and receive opaque public IDs.
- Do not begin broad implementation until the private census has zero unaccounted
  items and the receipt can be reopened and revalidated.

### One KU-BO architecture

- KU-BO owns the canonical package, CLI, contracts, evidence model, source policy,
  evaluation logic, and decision boundaries.
- Shared business logic belongs under `src/kubo`. Project Skills are thin wrappers
  under `.agents/skills` and contain no duplicate engine.
- Do not merge source Git history, vendor a second package, or create conflicting
  source/capability registries.
- Prefer stronger existing KU-BO implementations and safely rewrite any source
  behavior that would weaken provenance, temporal, denominator, privacy, or claim
  integrity.

### Verified user-job and capability parity

- Every legitimate user job gets a canonical target API/CLI, optional thin Skill,
  explicit input/output/failure/evidence/time contract, and tests.
- Prove semantic behavior, including malformed or missing input, blocked source,
  zero result, parser drift, identity mismatch, Point-in-Time leakage,
  self-asserted authorization, resume/idempotency, privacy, and claim boundaries.
- Unsafe behavior becomes a sanitized negative control plus safe replacement.
- External operational blockers never excuse an unresolved software job.

### Evidence-verifying completion

The current validator proves preparation only. Before any completion claim, add a
dedicated validator that reopens the private source receipt, checks target/test
paths at exact HEAD, runs package and installed-CLI gates, verifies exact-head CI
and Draft-PR state, and confirms the sanitized handoff. Self-reported OIDs, counts,
status strings, evidence IDs, or blockers are insufficient.

### Separate parity from live readiness

Software parity does not imply source access, data rights, universe completeness,
predictive skill, accuracy, probability, recommendation, or execution readiness.
This task may reach at most `END_TO_END_TESTED` on synthetic or explicitly
authorized recorded fixtures; no row may become `LIVE_OPERATIONAL`.

## Acceptance gates

1. Public KU-BO orientation records exact branch/base/PR/CI state.
2. Private source receipt revalidates every ref/tree/blob occurrence with zero
   unaccounted items and no public private-metadata leakage.
3. Sanitized user-job denominator is explicit and complete.
4. No second engine/package/CLI or conflicting registry exists.
5. Every legitimate job has a safe KU-BO path and behavioral/negative evidence.
6. Opaque seeds and every discovered required capability have final dispositions.
7. Skills remain thin and discoverable over KU-BO core.
8. Existing KU-BO gates and tests do not regress.
9. Compile, full tests, adversarial tests, smoke, Secret Guard, schemas, wheel,
   installed CLI, and exact-head CI pass.
10. A dedicated completion validator verifies the private receipt, exact target
    evidence, package receipts, CI, Draft-PR state, and handoff.
11. The private source and KU-BO `main` remain unchanged; no credentials, private
    locators/data, licensed/runtime evidence, or sensitive counts are published.
12. The single PR remains Draft and the handoff states `MERGE_NOT_PERFORMED`.

## Phase authority and stop conditions

Codex may continue automatically between implementation phases when gates pass.
Stop and record a decision only for merge, force-push, permanent deletion/archive,
source mutation, access beyond repository code/Git metadata, credentials/private
runtime data, paid/licensed activation, material product-behavior choice, live
activation, training, real backtest, or financial execution.

Do not merge. Record any later authority in `docs/codex/USER_DECISIONS.md` and use
`docs/codex/HANDOFF_TEMPLATE.md` for the final sanitized result.
