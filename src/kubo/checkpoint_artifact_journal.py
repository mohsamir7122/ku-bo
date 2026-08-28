"""Cross-runner checkpoint journal canary for GitHub Actions artifacts.

This module proves only that an immutable workflow artifact can carry one
``AtomicCheckpointStore`` checkpoint from one runner to another runner and
that the second runner can reopen it, exercise CAS/fencing, and publish a new
generation.  It is not a production coordinator and it never changes the
production checkpoint-store policy.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping

from .atomic_output import run_atomic_output
from .foundation_io import snapshot_regular_tree, strict_json_object
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .priority_runtime import (
    AtomicCheckpointStore,
    CheckpointCasError,
    FencingViolation,
    make_shard,
)
from .strict import parse_aware, require_sha256


SCHEMA_VERSION = "1.0"
JOURNAL_KIND = "GITHUB_ARTIFACT_JOURNAL"
CANARY_STATUS = "CANARY_ONLY"
COORDINATOR_STATUS = "NOT_PRODUCTION_COORDINATOR"
WORKFLOW_NAME = "checkpoint-artifact-journal-canary.yml"
WORKLOAD_ID = "artifact-journal-canary"
CHECKPOINT_RELATIVE_PATH = f"checkpoint-store/{WORKLOAD_ID}.checkpoint.json"
MANIFEST_PATH = "journal-manifest.json"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_CHECKPOINT_BYTES = 16 * 1024 * 1024

CLAIM_BOUNDARIES = {
    "artifact_transfer_proves_production_durability": False,
    "canary_is_production_coordinator": False,
    "canary_authorizes_collection": False,
    "canary_authorizes_training_or_backtest": False,
    "canary_authorizes_forecast_or_recommendation": False,
    "canary_resolves_blocked_checkpoint_store": False,
}

_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "journal_kind",
        "status",
        "production_coordinator_status",
        "repository",
        "workflow",
        "workflow_ref",
        "workflow_sha",
        "run_id",
        "run_attempt",
        "head_sha",
        "job_stage",
        "generation",
        "checkpoint_relative_path",
        "checkpoint_sha256",
        "checkpoint_id",
        "checkpoint_digest",
        "workload_id",
        "owner_run_id",
        "checkpoint_status",
        "previous_manifest_sha256",
        "cas_rejection_verified",
        "fencing_rejection_verified",
        "created_at",
        "claim_boundaries",
        "manifest_sha256",
    }
)
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_RUN_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")
_HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ArtifactJournalCanaryError(ValueError):
    """Raised when a canary bundle or cross-runner transition is invalid."""


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactJournalCanaryError(f"{label} must be an object")
    row = dict(value)
    actual = frozenset(row)
    if actual != fields:
        raise ArtifactJournalCanaryError(
            f"{label} has missing={sorted(fields - actual)} "
            f"unknown={sorted(actual - fields)}"
        )
    return row


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ArtifactJournalCanaryError(f"{label} must be a positive integer")
    return value


def _repository(value: Any) -> str:
    text = str(value or "")
    if _REPOSITORY_RE.fullmatch(text) is None or text.startswith((".", "-")):
        raise ArtifactJournalCanaryError("repository must be an owner/name slug")
    return text


def _run_id(value: Any) -> str:
    text = str(value or "")
    if _RUN_ID_RE.fullmatch(text) is None:
        raise ArtifactJournalCanaryError("run_id must be a positive decimal identifier")
    return text


def _git_sha(value: Any, label: str) -> str:
    text = str(value or "")
    if _HEAD_SHA_RE.fullmatch(text) is None:
        raise ArtifactJournalCanaryError(f"{label} must be a lowercase Git SHA")
    return text


def _head_sha(value: Any) -> str:
    return _git_sha(value, "head_sha")


def _workflow_ref(value: Any, repository: str) -> str:
    text = str(value or "")
    prefix = f"{repository}/.github/workflows/{WORKFLOW_NAME}@"
    if not text.startswith(prefix) or len(text) > 512:
        raise ArtifactJournalCanaryError(
            "workflow_ref must bind the repository canary workflow path"
        )
    ref = text[len(prefix) :]
    if (
        re.fullmatch(r"refs/(?:heads|pull)/[A-Za-z0-9._/-]+", ref) is None
        or "//" in ref
        or ".." in ref
        or ref.endswith(("/", ".lock"))
    ):
        raise ArtifactJournalCanaryError("workflow_ref contains an invalid Git ref")
    return text


def _owner(value: Any) -> str:
    text = str(value or "")
    if _OWNER_RE.fullmatch(text) is None:
        raise ArtifactJournalCanaryError("owner_run_id must be a safe identifier")
    return text


def artifact_journal_manifest_sha256(value: Mapping[str, Any]) -> str:
    """Return the canonical self-excluding digest for one journal manifest."""

    return hash_json({key: item for key, item in value.items() if key != "manifest_sha256"})


def _write_exclusive(path: Path, content: bytes, *, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(path, flags, 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ArtifactJournalCanaryError(f"{label} target is not a private regular file")
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
    except (OSError, ArtifactJournalCanaryError) as exc:
        if isinstance(exc, ArtifactJournalCanaryError):
            raise
        raise ArtifactJournalCanaryError(f"failed to write {label} exclusively") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _checkpoint_from_bytes(content: bytes) -> dict[str, Any]:
    if len(content) > MAX_CHECKPOINT_BYTES:
        raise ArtifactJournalCanaryError("checkpoint exceeds the canary byte budget")
    with tempfile.TemporaryDirectory() as directory:
        store_root = Path(directory) / "checkpoint-store"
        store_root.mkdir()
        _write_exclusive(
            store_root / f"{WORKLOAD_ID}.checkpoint.json",
            content,
            label="temporary checkpoint",
        )
        try:
            row = AtomicCheckpointStore(store_root).load(WORKLOAD_ID)
        except ValueError as exc:
            raise ArtifactJournalCanaryError(str(exc)) from exc
    if row is None:
        raise ArtifactJournalCanaryError("checkpoint is missing")
    if canonical_json_bytes(row) + b"\n" != content:
        raise ArtifactJournalCanaryError("checkpoint is not canonical JSON")
    return row


def _bundle_files(root: Path | str) -> tuple[bytes, bytes]:
    try:
        snapshot = snapshot_regular_tree(
            Path(root),
            field="artifact journal canary bundle",
            max_files=2,
            max_entries=4,
            max_depth=3,
            max_file_bytes=MAX_CHECKPOINT_BYTES,
            max_total_bytes=MAX_CHECKPOINT_BYTES + MAX_MANIFEST_BYTES,
        )
    except ValueError as exc:
        raise ArtifactJournalCanaryError(str(exc)) from exc
    files = snapshot.by_path()
    expected = {CHECKPOINT_RELATIVE_PATH, MANIFEST_PATH}
    if set(files) != expected:
        raise ArtifactJournalCanaryError(
            "canary bundle must contain exactly the checkpoint and journal manifest"
        )
    if files[MANIFEST_PATH].size_bytes > MAX_MANIFEST_BYTES:
        raise ArtifactJournalCanaryError("journal manifest exceeds the byte budget")
    return files[CHECKPOINT_RELATIVE_PATH].content, files[MANIFEST_PATH].content


def _disjoint_bundle_roots(
    previous_root: Path | str, output_root: Path | str
) -> tuple[Path, Path]:
    try:
        previous = Path(previous_root).resolve(strict=False)
        output = Path(output_root).resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ArtifactJournalCanaryError("canary bundle paths cannot be resolved") from exc
    if (
        previous == output
        or previous in output.parents
        or output in previous.parents
    ):
        raise ArtifactJournalCanaryError(
            "previous and output canary bundle roots must be disjoint"
        )
    return previous, output


def _validate_manifest(
    manifest_content: bytes,
    checkpoint_content: bytes,
    checkpoint: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        payload = strict_json_object(manifest_content, "artifact journal manifest")
    except ValueError as exc:
        raise ArtifactJournalCanaryError(str(exc)) from exc
    row = _exact(payload, _MANIFEST_FIELDS, "artifact journal manifest")
    if manifest_content != canonical_json_bytes(row) + b"\n":
        raise ArtifactJournalCanaryError("artifact journal manifest is not canonical JSON")
    if row["schema_version"] != SCHEMA_VERSION:
        raise ArtifactJournalCanaryError("unsupported journal manifest schema")
    if row["journal_kind"] != JOURNAL_KIND:
        raise ArtifactJournalCanaryError("journal kind is not GITHUB_ARTIFACT_JOURNAL")
    if row["status"] != CANARY_STATUS:
        raise ArtifactJournalCanaryError("journal status must remain CANARY_ONLY")
    if row["production_coordinator_status"] != COORDINATOR_STATUS:
        raise ArtifactJournalCanaryError(
            "journal must remain NOT_PRODUCTION_COORDINATOR"
        )
    repository = _repository(row["repository"])
    if row["workflow"] != WORKFLOW_NAME:
        raise ArtifactJournalCanaryError("journal workflow binding is invalid")
    _workflow_ref(row["workflow_ref"], repository)
    _git_sha(row["workflow_sha"], "workflow_sha")
    run_id = _run_id(row["run_id"])
    run_attempt = _positive_int(row["run_attempt"], "run_attempt")
    _head_sha(row["head_sha"])
    generation = _positive_int(row["generation"], "generation")
    if row["checkpoint_relative_path"] != CHECKPOINT_RELATIVE_PATH:
        raise ArtifactJournalCanaryError("checkpoint relative path changed")
    if row["checkpoint_sha256"] != sha256_bytes(checkpoint_content):
        raise ArtifactJournalCanaryError("checkpoint file digest mismatch")
    try:
        require_sha256(row["checkpoint_sha256"], "checkpoint_sha256")
        require_sha256(row["checkpoint_digest"], "checkpoint_digest")
        require_sha256(row["manifest_sha256"], "manifest_sha256")
    except ValueError as exc:
        raise ArtifactJournalCanaryError(str(exc)) from exc
    if row["previous_manifest_sha256"] is not None:
        try:
            require_sha256(
                row["previous_manifest_sha256"], "previous_manifest_sha256"
            )
        except ValueError as exc:
            raise ArtifactJournalCanaryError(str(exc)) from exc
    if row["manifest_sha256"] != artifact_journal_manifest_sha256(row):
        raise ArtifactJournalCanaryError("journal manifest digest mismatch")
    if row["claim_boundaries"] != CLAIM_BOUNDARIES:
        raise ArtifactJournalCanaryError("journal claim boundaries changed")
    try:
        created_at = parse_aware(row["created_at"], "created_at")
    except ValueError as exc:
        raise ArtifactJournalCanaryError(str(exc)) from exc
    if created_at.isoformat() == "":  # pragma: no cover - parse_aware is authoritative.
        raise AssertionError("unreachable empty timestamp")
    if (
        row["workload_id"] != WORKLOAD_ID
        or checkpoint["workload_id"] != WORKLOAD_ID
        or row["checkpoint_id"] != checkpoint["checkpoint_id"]
        or row["checkpoint_digest"] != checkpoint["checkpoint_digest"]
        or row["generation"] != checkpoint["generation"]
        or row["owner_run_id"] != checkpoint["owner_run_id"]
        or row["checkpoint_status"] != checkpoint["status"]
        or row["created_at"] != checkpoint["updated_at"]
    ):
        raise ArtifactJournalCanaryError("journal differs from reopened checkpoint")
    owner_run_id = _owner(row["owner_run_id"])
    if owner_run_id != f"gh-{run_id}-{run_attempt}-g{generation}":
        raise ArtifactJournalCanaryError(
            "checkpoint owner differs from the bound workflow run generation"
        )
    if generation == 1:
        if (
            row["job_stage"] != "GENERATION_1_CREATE_PREEMPT"
            or row["checkpoint_status"] != "PREEMPTED"
            or row["previous_manifest_sha256"] is not None
            or row["cas_rejection_verified"] is not False
            or row["fencing_rejection_verified"] is not False
        ):
            raise ArtifactJournalCanaryError("generation 1 canary contract changed")
    elif generation == 2:
        if (
            row["job_stage"] != "GENERATION_2_REOPEN_RESUME_CAS_FENCING"
            or row["checkpoint_status"] != "RUNNING"
            or row["previous_manifest_sha256"] is None
            or row["cas_rejection_verified"] is not True
            or row["fencing_rejection_verified"] is not True
        ):
            raise ArtifactJournalCanaryError("generation 2 canary contract changed")
    else:
        raise ArtifactJournalCanaryError("canary permits exactly generations 1 and 2")
    return row


def validate_artifact_journal_bundle(
    root: Path | str,
    *,
    expected_repository: str | None = None,
    expected_workflow: str | None = None,
    expected_workflow_ref: str | None = None,
    expected_workflow_sha: str | None = None,
    expected_run_id: str | None = None,
    expected_run_attempt: int | None = None,
    expected_head_sha: str | None = None,
) -> dict[str, Any]:
    """Reopen and validate one bounded canary artifact bundle."""

    checkpoint_content, manifest_content = _bundle_files(root)
    checkpoint = _checkpoint_from_bytes(checkpoint_content)
    manifest = _validate_manifest(manifest_content, checkpoint_content, checkpoint)
    expected = {
        "repository": expected_repository,
        "workflow": expected_workflow,
        "workflow_ref": expected_workflow_ref,
        "workflow_sha": expected_workflow_sha,
        "run_id": expected_run_id,
        "run_attempt": expected_run_attempt,
        "head_sha": expected_head_sha,
    }
    for field, value in expected.items():
        if value is not None and manifest[field] != value:
            raise ArtifactJournalCanaryError(
                f"journal {field} differs from the expected workflow context"
            )
    return {
        "status": CANARY_STATUS,
        "production_coordinator_status": COORDINATOR_STATUS,
        "journal_kind": JOURNAL_KIND,
        "repository": manifest["repository"],
        "workflow": manifest["workflow"],
        "workflow_ref": manifest["workflow_ref"],
        "workflow_sha": manifest["workflow_sha"],
        "run_id": manifest["run_id"],
        "run_attempt": manifest["run_attempt"],
        "head_sha": manifest["head_sha"],
        "generation": manifest["generation"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "checkpoint_digest": checkpoint["checkpoint_digest"],
        "manifest_sha256": manifest["manifest_sha256"],
        "cas_rejection_verified": manifest["cas_rejection_verified"],
        "fencing_rejection_verified": manifest["fencing_rejection_verified"],
        "claim_boundaries": dict(CLAIM_BOUNDARIES),
    }


def _manifest(
    *,
    repository: str,
    workflow: str,
    workflow_ref: str,
    workflow_sha: str,
    run_id: str,
    run_attempt: int,
    head_sha: str,
    checkpoint_content: bytes,
    checkpoint: Mapping[str, Any],
    job_stage: str,
    previous_manifest_sha256: str | None,
    cas_rejection_verified: bool,
    fencing_rejection_verified: bool,
) -> dict[str, Any]:
    checked_repository = _repository(repository)
    row: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "journal_kind": JOURNAL_KIND,
        "status": CANARY_STATUS,
        "production_coordinator_status": COORDINATOR_STATUS,
        "repository": checked_repository,
        "workflow": workflow,
        "workflow_ref": _workflow_ref(workflow_ref, checked_repository),
        "workflow_sha": _git_sha(workflow_sha, "workflow_sha"),
        "run_id": _run_id(run_id),
        "run_attempt": _positive_int(run_attempt, "run_attempt"),
        "head_sha": _head_sha(head_sha),
        "job_stage": job_stage,
        "generation": checkpoint["generation"],
        "checkpoint_relative_path": CHECKPOINT_RELATIVE_PATH,
        "checkpoint_sha256": sha256_bytes(checkpoint_content),
        "checkpoint_id": checkpoint["checkpoint_id"],
        "checkpoint_digest": checkpoint["checkpoint_digest"],
        "workload_id": checkpoint["workload_id"],
        "owner_run_id": checkpoint["owner_run_id"],
        "checkpoint_status": checkpoint["status"],
        "previous_manifest_sha256": previous_manifest_sha256,
        "cas_rejection_verified": cas_rejection_verified,
        "fencing_rejection_verified": fencing_rejection_verified,
        "created_at": checkpoint["updated_at"],
        "claim_boundaries": dict(CLAIM_BOUNDARIES),
        "manifest_sha256": "0" * 64,
    }
    if workflow != WORKFLOW_NAME:
        raise ArtifactJournalCanaryError("workflow must bind the canary workflow file")
    row["manifest_sha256"] = artifact_journal_manifest_sha256(row)
    return row


def create_generation_one(
    output_root: Path | str,
    *,
    repository: str,
    workflow: str,
    workflow_ref: str,
    workflow_sha: str,
    run_id: str,
    run_attempt: int,
    head_sha: str,
    now: datetime | str,
) -> dict[str, Any]:
    """Create and preempt a generation-1 checkpoint in an immutable bundle."""

    instant = parse_aware(now, "now") if isinstance(now, str) else now
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ArtifactJournalCanaryError("now must be timezone-aware")
    checked_run_id = _run_id(run_id)
    checked_attempt = _positive_int(run_attempt, "run_attempt")

    def worker(staging: Path) -> None:
        store_root = staging / "checkpoint-store"
        store = AtomicCheckpointStore(store_root)
        checkpoint = store.create(
            workload_id=WORKLOAD_ID,
            workload_class="BACKFILL_90D",
            owner_run_id=f"gh-{checked_run_id}-{checked_attempt}-g1",
            scheduled_at=instant,
            actual_started_at=instant,
            shards=[
                make_shard(
                    market="KUWAIT",
                    source_id="checkpoint_canary",
                    partition_date="2026-08-27",
                )
            ],
        )
        shard = checkpoint["shards"][0]
        running, changed = store.start_shard(
            WORKLOAD_ID,
            shard_id_value=shard["shard_id"],
            expected_generation=1,
            fencing_token=checkpoint["fencing_token"],
            now=instant,
        )
        if not changed:
            raise ArtifactJournalCanaryError("generation 1 did not start its shard")
        checkpoint = store.preempt(
            WORKLOAD_ID,
            expected_generation=1,
            fencing_token=running["fencing_token"],
            now=instant,
        )
        guard = store_root / f"{WORKLOAD_ID}.guard"
        guard.unlink(missing_ok=True)
        checkpoint_path = staging / CHECKPOINT_RELATIVE_PATH
        checkpoint_content = checkpoint_path.read_bytes()
        manifest = _manifest(
            repository=repository,
            workflow=workflow,
            workflow_ref=workflow_ref,
            workflow_sha=workflow_sha,
            run_id=checked_run_id,
            run_attempt=checked_attempt,
            head_sha=head_sha,
            checkpoint_content=checkpoint_content,
            checkpoint=checkpoint,
            job_stage="GENERATION_1_CREATE_PREEMPT",
            previous_manifest_sha256=None,
            cas_rejection_verified=False,
            fencing_rejection_verified=False,
        )
        _write_exclusive(
            staging / MANIFEST_PATH,
            canonical_json_bytes(manifest) + b"\n",
            label="generation 1 journal manifest",
        )

    def before_commit(staging: Path) -> None:
        validate_artifact_journal_bundle(
            staging,
            expected_repository=repository,
            expected_workflow=workflow,
            expected_workflow_ref=workflow_ref,
            expected_workflow_sha=workflow_sha,
            expected_run_id=checked_run_id,
            expected_run_attempt=checked_attempt,
            expected_head_sha=head_sha,
        )

    run_atomic_output(output_root, worker, before_commit)
    return validate_artifact_journal_bundle(
        output_root,
        expected_repository=repository,
        expected_workflow=workflow,
        expected_workflow_ref=workflow_ref,
        expected_workflow_sha=workflow_sha,
        expected_run_id=checked_run_id,
        expected_run_attempt=checked_attempt,
        expected_head_sha=head_sha,
    )


def create_generation_two(
    previous_root: Path | str,
    output_root: Path | str,
    *,
    repository: str,
    workflow: str,
    workflow_ref: str,
    workflow_sha: str,
    run_id: str,
    run_attempt: int,
    head_sha: str,
    now: datetime | str,
) -> dict[str, Any]:
    """Reopen generation 1, prove stale CAS/fencing rejection, and resume."""

    previous_path, output_path = _disjoint_bundle_roots(previous_root, output_root)
    previous_report = validate_artifact_journal_bundle(
        previous_path,
        expected_repository=repository,
        expected_workflow=workflow,
        expected_workflow_ref=workflow_ref,
        expected_workflow_sha=workflow_sha,
        expected_run_id=run_id,
        expected_run_attempt=run_attempt,
        expected_head_sha=head_sha,
    )
    if previous_report["generation"] != 1:
        raise ArtifactJournalCanaryError("generation 2 requires a generation 1 bundle")
    previous_checkpoint_content, _previous_manifest_content = _bundle_files(previous_path)
    instant = parse_aware(now, "now") if isinstance(now, str) else now
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ArtifactJournalCanaryError("now must be timezone-aware")
    checked_run_id = _run_id(run_id)
    checked_attempt = _positive_int(run_attempt, "run_attempt")

    def worker(staging: Path) -> None:
        checkpoint_path = staging / CHECKPOINT_RELATIVE_PATH
        _write_exclusive(
            checkpoint_path,
            previous_checkpoint_content,
            label="downloaded generation 1 checkpoint",
        )
        store = AtomicCheckpointStore(checkpoint_path.parent)
        previous = store.load(WORKLOAD_ID)
        if previous is None:
            raise ArtifactJournalCanaryError("downloaded generation 1 checkpoint is missing")
        stale_generation = previous["generation"]
        stale_digest = previous["checkpoint_digest"]
        stale_fencing_token = previous["fencing_token"]
        resumed = store.claim_resume(
            WORKLOAD_ID,
            expected_generation=stale_generation,
            owner_run_id=f"gh-{checked_run_id}-{checked_attempt}-g2",
            now=instant,
        )
        shard = resumed["shards"][0]
        try:
            store.start_shard(
                WORKLOAD_ID,
                shard_id_value=shard["shard_id"],
                expected_generation=stale_generation,
                fencing_token=resumed["fencing_token"],
                now=instant,
            )
        except CheckpointCasError:
            cas_rejection_verified = True
        else:  # pragma: no cover - guarded by adversarial tests.
            raise ArtifactJournalCanaryError("stale generation CAS was accepted")
        if store.load(WORKLOAD_ID) != resumed:
            raise ArtifactJournalCanaryError("failed CAS mutated the checkpoint")
        try:
            store.start_shard(
                WORKLOAD_ID,
                shard_id_value=shard["shard_id"],
                expected_generation=resumed["generation"],
                fencing_token=stale_fencing_token,
                now=instant,
            )
        except FencingViolation:
            fencing_rejection_verified = True
        else:  # pragma: no cover - guarded by adversarial tests.
            raise ArtifactJournalCanaryError("stale fencing token was accepted")
        if store.load(WORKLOAD_ID) != resumed:
            raise ArtifactJournalCanaryError("failed fencing check mutated the checkpoint")
        if resumed["checkpoint_digest"] == stale_digest:
            raise ArtifactJournalCanaryError("resume did not advance checkpoint digest")
        guard = checkpoint_path.parent / f"{WORKLOAD_ID}.guard"
        guard.unlink(missing_ok=True)
        checkpoint_content = checkpoint_path.read_bytes()
        manifest = _manifest(
            repository=repository,
            workflow=workflow,
            workflow_ref=workflow_ref,
            workflow_sha=workflow_sha,
            run_id=checked_run_id,
            run_attempt=checked_attempt,
            head_sha=head_sha,
            checkpoint_content=checkpoint_content,
            checkpoint=resumed,
            job_stage="GENERATION_2_REOPEN_RESUME_CAS_FENCING",
            previous_manifest_sha256=previous_report["manifest_sha256"],
            cas_rejection_verified=cas_rejection_verified,
            fencing_rejection_verified=fencing_rejection_verified,
        )
        _write_exclusive(
            staging / MANIFEST_PATH,
            canonical_json_bytes(manifest) + b"\n",
            label="generation 2 journal manifest",
        )

    def before_commit(staging: Path) -> None:
        validate_artifact_journal_chain(
            previous_path,
            staging,
            expected_repository=repository,
            expected_workflow=workflow,
            expected_workflow_ref=workflow_ref,
            expected_workflow_sha=workflow_sha,
            expected_run_id=checked_run_id,
            expected_run_attempt=checked_attempt,
            expected_head_sha=head_sha,
        )

    run_atomic_output(output_path, worker, before_commit)
    validate_artifact_journal_chain(
        previous_path,
        output_path,
        expected_repository=repository,
        expected_workflow=workflow,
        expected_workflow_ref=workflow_ref,
        expected_workflow_sha=workflow_sha,
        expected_run_id=checked_run_id,
        expected_run_attempt=checked_attempt,
        expected_head_sha=head_sha,
    )
    return validate_artifact_journal_bundle(
        output_path,
        expected_repository=repository,
        expected_workflow=workflow,
        expected_workflow_ref=workflow_ref,
        expected_workflow_sha=workflow_sha,
        expected_run_id=checked_run_id,
        expected_run_attempt=checked_attempt,
        expected_head_sha=head_sha,
    )


def validate_artifact_journal_chain(
    previous_root: Path | str,
    current_root: Path | str,
    *,
    expected_repository: str | None = None,
    expected_workflow: str | None = None,
    expected_workflow_ref: str | None = None,
    expected_workflow_sha: str | None = None,
    expected_run_id: str | None = None,
    expected_run_attempt: int | None = None,
    expected_head_sha: str | None = None,
) -> dict[str, Any]:
    """Validate the exact generation-1 to generation-2 canary transition."""

    previous_checkpoint_content, previous_manifest_content = _bundle_files(previous_root)
    current_checkpoint_content, current_manifest_content = _bundle_files(current_root)
    previous_checkpoint = _checkpoint_from_bytes(previous_checkpoint_content)
    current_checkpoint = _checkpoint_from_bytes(current_checkpoint_content)
    previous = _validate_manifest(
        previous_manifest_content, previous_checkpoint_content, previous_checkpoint
    )
    current = _validate_manifest(
        current_manifest_content, current_checkpoint_content, current_checkpoint
    )
    context_fields = (
        "repository",
        "workflow",
        "workflow_ref",
        "workflow_sha",
        "run_id",
        "run_attempt",
        "head_sha",
    )
    if any(previous[field] != current[field] for field in context_fields):
        raise ArtifactJournalCanaryError("journal generations cross workflow context")
    expected = {
        "repository": expected_repository,
        "workflow": expected_workflow,
        "workflow_ref": expected_workflow_ref,
        "workflow_sha": expected_workflow_sha,
        "run_id": expected_run_id,
        "run_attempt": expected_run_attempt,
        "head_sha": expected_head_sha,
    }
    for field, value in expected.items():
        if value is not None and current[field] != value:
            raise ArtifactJournalCanaryError(
                f"journal chain {field} differs from the expected workflow context"
            )
    if (
        previous["generation"] != 1
        or current["generation"] != 2
        or previous["checkpoint_id"] != current["checkpoint_id"]
        or previous["workload_id"] != current["workload_id"]
        or current["previous_manifest_sha256"] != previous["manifest_sha256"]
    ):
        raise ArtifactJournalCanaryError("journal generation chain is invalid")
    with tempfile.TemporaryDirectory() as directory:
        store_root = Path(directory) / "checkpoint-store"
        store_root.mkdir()
        _write_exclusive(
            store_root / f"{WORKLOAD_ID}.checkpoint.json",
            previous_checkpoint_content,
            label="chain replay checkpoint",
        )
        store = AtomicCheckpointStore(store_root)
        replayed = store.claim_resume(
            WORKLOAD_ID,
            expected_generation=1,
            owner_run_id=current_checkpoint["owner_run_id"],
            now=parse_aware(current["created_at"], "current created_at"),
        )
        shard = replayed["shards"][0]
        try:
            store.start_shard(
                WORKLOAD_ID,
                shard_id_value=shard["shard_id"],
                expected_generation=previous_checkpoint["generation"],
                fencing_token=replayed["fencing_token"],
                now=parse_aware(current["created_at"], "current created_at"),
            )
        except CheckpointCasError:
            pass
        else:  # pragma: no cover - the runtime contract is tested independently.
            raise ArtifactJournalCanaryError(
                "chain replay accepted the stale checkpoint generation"
            )
        if store.load(WORKLOAD_ID) != replayed:
            raise ArtifactJournalCanaryError("chain replay CAS rejection mutated state")
        try:
            store.start_shard(
                WORKLOAD_ID,
                shard_id_value=shard["shard_id"],
                expected_generation=replayed["generation"],
                fencing_token=previous_checkpoint["fencing_token"],
                now=parse_aware(current["created_at"], "current created_at"),
            )
        except FencingViolation:
            pass
        else:  # pragma: no cover - the runtime contract is tested independently.
            raise ArtifactJournalCanaryError(
                "chain replay accepted the stale checkpoint fencing token"
            )
        if store.load(WORKLOAD_ID) != replayed:
            raise ArtifactJournalCanaryError(
                "chain replay fencing rejection mutated state"
            )
    if replayed != current_checkpoint:
        raise ArtifactJournalCanaryError(
            "generation 2 is not the canonical AtomicCheckpointStore resume"
        )
    return {
        "status": CANARY_STATUS,
        "production_coordinator_status": COORDINATOR_STATUS,
        "journal_kind": JOURNAL_KIND,
        "repository": current["repository"],
        "workflow": current["workflow"],
        "workflow_ref": current["workflow_ref"],
        "workflow_sha": current["workflow_sha"],
        "run_id": current["run_id"],
        "run_attempt": current["run_attempt"],
        "head_sha": current["head_sha"],
        "previous_generation": 1,
        "current_generation": 2,
        "checkpoint_id": current["checkpoint_id"],
        "checkpoint_digest": current["checkpoint_digest"],
        "cas_rejection_verified": True,
        "fencing_rejection_verified": True,
        "claim_boundaries": dict(CLAIM_BOUNDARIES),
    }


__all__ = [
    "ArtifactJournalCanaryError",
    "CANARY_STATUS",
    "CHECKPOINT_RELATIVE_PATH",
    "CLAIM_BOUNDARIES",
    "COORDINATOR_STATUS",
    "JOURNAL_KIND",
    "MANIFEST_PATH",
    "WORKFLOW_NAME",
    "artifact_journal_manifest_sha256",
    "create_generation_one",
    "create_generation_two",
    "validate_artifact_journal_bundle",
    "validate_artifact_journal_chain",
]
