"""Priority, fencing, and resumable checkpoint coordination for market work.

This module coordinates existing collection and validation components. It does
not fetch sources, infer rights, parse market data, train models, or publish a
candidate. Production use fails closed until the trusted policy names a durable
checkpoint-store kind.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
import fcntl
import hashlib
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Callable, Iterator, Mapping, Sequence

from .foundation_io import load_strict_json_object, safe_regular_file, strict_json_object
from .hashing import canonical_json_bytes, sha256_bytes
from .strict import parse_aware, require_sha256, safe_relative_path


POLICY_PATH = Path("config/execution-priority-policy.json")
PRIORITIES = {
    "LIVE_DAILY_1500": 100,
    "LIVE_RECOVERY": 90,
    "VALIDATION_AND_PUBLISH": 70,
    "CHALLENGER_TRAINING": 40,
    "BACKFILL_90D": 10,
}
MARKETS = frozenset({"KUWAIT", "SAUDI_ARABIA"})
SHARD_STATUSES = frozenset({"PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED"})
CHECKPOINT_STATUSES = frozenset(
    {"RUNNING", "PREEMPTED", "COMPLETED", "COMPLETED_WITH_BLOCKS", "BLOCKED"}
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CHECKPOINT_KEYS = frozenset(
    {
        "schema_version",
        "checkpoint_id",
        "workload_id",
        "workload_class",
        "priority",
        "window_from",
        "window_to",
        "scheduled_at",
        "actual_started_at",
        "finished_at",
        "status",
        "generation",
        "fencing_token",
        "owner_run_id",
        "created_at",
        "updated_at",
        "shards",
        "checkpoint_digest",
    }
)
_SHARD_KEYS = frozenset(
    {
        "shard_id",
        "market",
        "source_id",
        "partition_kind",
        "partition_value",
        "status",
        "attempt_count",
        "idempotency_key",
        "started_at",
        "finished_at",
        "output",
        "failure_code",
    }
)


class PriorityRuntimeError(ValueError):
    """Raised when priority or checkpoint state violates the contract."""


class BlockedCheckpointStore(PriorityRuntimeError):
    """Raised when a production durable store is not trusted/configured."""


class CheckpointCasError(PriorityRuntimeError):
    """Raised when expected generation differs from durable state."""


class FencingViolation(PriorityRuntimeError):
    """Raised when an old worker tries to mutate a newer generation."""


def _canonical(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _identifier(value: Any, field: str) -> str:
    text = str(value or "")
    if not _ID_RE.fullmatch(text):
        raise PriorityRuntimeError(f"{field} must be a safe identifier")
    return text


def _utc(value: datetime | str, field: str) -> datetime:
    parsed = value if isinstance(value, datetime) else parse_aware(value, field)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PriorityRuntimeError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _exact(value: Any, keys: frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PriorityRuntimeError(f"{field} must be an object")
    actual = frozenset(value)
    if actual != keys:
        raise PriorityRuntimeError(
            f"{field} has missing={sorted(keys - actual)} unknown={sorted(actual - keys)}"
        )
    return value


def _expected_policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "policy_id": "ku-bo-market-execution-priority-v1",
        "status": "FAIL_CLOSED",
        "priorities": dict(PRIORITIES),
        "preemption": {
            "strictly_higher_priority_required": True,
            "cooperative_shard_boundary": True,
            "completed_shards_are_immutable": True,
            "in_progress_shard_returns_to_pending": True,
            "champion_mutation_during_live": False,
        },
        "checkpoint_store": {
            "production_status": "BLOCKED_CHECKPOINT_STORE",
            "configured_production_kind": None,
            "allowed_production_kinds": [
                "AUTHORIZED_FILESYSTEM",
                "AUTHORIZED_OBJECT_STORE",
                "GITHUB_ARTIFACT_JOURNAL",
            ],
            "ephemeral_runner_directory_is_durable": False,
            "atomic_replace_required": True,
            "compare_and_swap_required": True,
            "fencing_token_required": True,
        },
        "lease": {
            "ttl_seconds": 900,
            "heartbeat_seconds": 60,
            "generation_starts_at": 1,
        },
        "sharding": {
            "dimensions": ["market", "source", "date_or_page"],
            "maximum_attempts_per_shard": 2,
            "completed_requires_reopened_output_hash": True,
            "resume_only_non_completed": True,
        },
        "backfill_window": {
            "inclusive_from": "2026-05-30",
            "inclusive_to": "2026-08-27",
            "day_count": 90,
        },
        "timestamps": ["scheduled_at", "actual_started_at", "finished_at"],
        "claim_boundaries": {
            "checkpoint_structure_proves_durable_production_store": False,
            "completed_checkpoint_proves_source_rights": False,
            "backfill_checkpoint_unlocks_training": False,
            "priority_scheduler_may_update_champion": False,
            "workflow_schedule_is_active_on_feature_branch": False,
        },
    }


def load_priority_policy(project_root: Path | str) -> tuple[dict[str, Any], bytes]:
    path = Path(project_root).resolve() / POLICY_PATH
    try:
        payload, content = load_strict_json_object(
            path, field="execution priority policy", max_bytes=512 * 1024
        )
    except ValueError as exc:
        raise PriorityRuntimeError(str(exc)) from exc
    if payload != _expected_policy():
        raise PriorityRuntimeError("execution priority policy differs from locked contract")
    return payload, content


def validate_priority_policy(project_root: Path | str) -> dict[str, Any]:
    policy, content = load_priority_policy(project_root)
    return {
        "schema_version": "1.0",
        "status": "PASS_FAIL_CLOSED_PRIORITY_POLICY",
        "policy_sha256": sha256_bytes(content),
        "priorities": dict(policy["priorities"]),
        "production_checkpoint_store_status": policy["checkpoint_store"][
            "production_status"
        ],
        "production_checkpoint_store_configured": False,
        "schedule_active": False,
    }


def require_production_checkpoint_store(project_root: Path | str) -> str:
    policy, _ = load_priority_policy(project_root)
    configured = policy["checkpoint_store"]["configured_production_kind"]
    if configured is None:
        raise BlockedCheckpointStore("BLOCKED_CHECKPOINT_STORE")
    if configured not in policy["checkpoint_store"]["allowed_production_kinds"]:
        raise BlockedCheckpointStore("checkpoint store kind is not allowlisted")
    return str(configured)


def _partition_date(value: Any) -> date:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise PriorityRuntimeError("partition_date must be an ISO date") from exc
    if not date(2026, 5, 30) <= parsed <= date(2026, 8, 27):
        raise PriorityRuntimeError("partition_date is outside the inclusive 90-day window")
    return parsed


def shard_id(
    *, market: Any, source_id: Any, partition_kind: Any, partition_value: Any
) -> str:
    normalized_market = str(market or "").upper()
    if normalized_market not in MARKETS:
        raise PriorityRuntimeError("market is invalid")
    source = _identifier(source_id, "source_id")
    kind = str(partition_kind or "").upper()
    if kind not in {"DATE", "PAGE"}:
        raise PriorityRuntimeError("partition_kind must be DATE or PAGE")
    value = (
        _partition_date(partition_value).isoformat()
        if kind == "DATE"
        else _identifier(partition_value, "partition_value")
    )
    identity = {
        "market": normalized_market,
        "source_id": source,
        "partition_kind": kind,
        "partition_value": value,
    }
    return hashlib.sha256(_canonical(identity)).hexdigest()


def shard_idempotency_key(identity: Mapping[str, Any], attempt_count: Any) -> str:
    if type(attempt_count) is not int or not 0 <= attempt_count <= 2:
        raise PriorityRuntimeError("attempt_count must be an integer from 0 through 2")
    basis = {
        "shard_id": require_sha256(identity["shard_id"], "shard_id"),
        "attempt_count": attempt_count,
    }
    return hashlib.sha256(_canonical(basis)).hexdigest()


def make_shard(
    *,
    market: Any,
    source_id: Any,
    partition_date: Any = None,
    page_id: Any = None,
) -> dict[str, Any]:
    if (partition_date is None) == (page_id is None):
        raise PriorityRuntimeError("exactly one of partition_date or page_id is required")
    kind = "DATE" if partition_date is not None else "PAGE"
    value = partition_date if partition_date is not None else page_id
    identifier = shard_id(
        market=market,
        source_id=source_id,
        partition_kind=kind,
        partition_value=value,
    )
    row = {
        "shard_id": identifier,
        "market": str(market).upper(),
        "source_id": _identifier(source_id, "source_id"),
        "partition_kind": kind,
        "partition_value": (
            _partition_date(value).isoformat()
            if kind == "DATE"
            else _identifier(value, "page_id")
        ),
        "status": "PENDING",
        "attempt_count": 0,
        "idempotency_key": "",
        "started_at": None,
        "finished_at": None,
        "output": None,
        "failure_code": None,
    }
    row["idempotency_key"] = shard_idempotency_key(row, 0)
    return _validate_shard(row)


def _validate_shard(value: Any) -> dict[str, Any]:
    row = dict(_exact(value, _SHARD_KEYS, "shard"))
    expected_id = shard_id(
        market=row["market"],
        source_id=row["source_id"],
        partition_kind=row["partition_kind"],
        partition_value=row["partition_value"],
    )
    if require_sha256(row["shard_id"], "shard_id") != expected_id:
        raise PriorityRuntimeError("shard_id differs from canonical shard identity")
    if row["status"] not in SHARD_STATUSES:
        raise PriorityRuntimeError("shard status is invalid")
    attempts = row["attempt_count"]
    if type(attempts) is not int or not 0 <= attempts <= 2:
        raise PriorityRuntimeError("shard attempt_count is invalid")
    if require_sha256(row["idempotency_key"], "idempotency_key") != shard_idempotency_key(
        row, attempts
    ):
        raise PriorityRuntimeError("shard idempotency_key is invalid")
    started = None if row["started_at"] is None else _utc(row["started_at"], "started_at")
    finished = None if row["finished_at"] is None else _utc(
        row["finished_at"], "finished_at"
    )
    if started is not None and finished is not None and finished < started:
        raise PriorityRuntimeError("shard finished_at precedes started_at")
    output = row["output"]
    if row["status"] == "PENDING":
        if (
            started is not None
            or output is not None
            or row["finished_at"] is not None
            or row["failure_code"] is not None
        ):
            raise PriorityRuntimeError("pending shard contains terminal fields")
    elif row["status"] == "IN_PROGRESS":
        if (
            attempts < 1
            or started is None
            or output is not None
            or finished is not None
            or row["failure_code"] is not None
        ):
            raise PriorityRuntimeError("in-progress shard fields are inconsistent")
    elif row["status"] == "COMPLETED":
        if attempts < 1 or started is None or finished is None or not isinstance(output, Mapping):
            raise PriorityRuntimeError("completed shard lacks verified output")
        if frozenset(output) != {"path", "sha256", "size_bytes"}:
            raise PriorityRuntimeError("completed shard output fields are invalid")
        safe_relative_path(output["path"], "output.path")
        require_sha256(output["sha256"], "output.sha256")
        if type(output["size_bytes"]) is not int or output["size_bytes"] < 0:
            raise PriorityRuntimeError("output.size_bytes is invalid")
        if row["failure_code"] is not None:
            raise PriorityRuntimeError("completed shard cannot have a failure code")
    elif row["status"] == "BLOCKED":
        if attempts < 1 or started is None or finished is None or output is not None:
            raise PriorityRuntimeError("blocked shard fields are inconsistent")
        _identifier(row["failure_code"], "failure_code")
    return row


def _checkpoint_fencing_token(
    checkpoint_id: str, generation: int, owner_run_id: str
) -> str:
    basis = {
        "checkpoint_id": _identifier(checkpoint_id, "checkpoint_id"),
        "generation": generation,
        "owner_run_id": _identifier(owner_run_id, "owner_run_id"),
    }
    return hashlib.sha256(_canonical(basis)).hexdigest()


def _checkpoint_digest(value: Mapping[str, Any]) -> str:
    material = {key: item for key, item in value.items() if key != "checkpoint_digest"}
    return hashlib.sha256(_canonical(material)).hexdigest()


def _advance_updated_at(row: dict[str, Any], current: datetime) -> None:
    if current < _utc(row["updated_at"], "updated_at"):
        raise PriorityRuntimeError("checkpoint time cannot move backwards")
    row["updated_at"] = _timestamp(current)


def _validate_checkpoint(value: Any) -> dict[str, Any]:
    row = dict(_exact(value, _CHECKPOINT_KEYS, "checkpoint"))
    if row["schema_version"] != "1.0":
        raise PriorityRuntimeError("checkpoint schema_version is invalid")
    checkpoint_id = _identifier(row["checkpoint_id"], "checkpoint_id")
    _identifier(row["workload_id"], "workload_id")
    workload_class = str(row["workload_class"])
    if workload_class not in PRIORITIES or row["priority"] != PRIORITIES[workload_class]:
        raise PriorityRuntimeError("checkpoint priority differs from trusted class")
    window_from = _partition_date(row["window_from"])
    window_to = _partition_date(row["window_to"])
    if window_from > window_to:
        raise PriorityRuntimeError("checkpoint window is reversed")
    scheduled = _utc(row["scheduled_at"], "scheduled_at")
    started = _utc(row["actual_started_at"], "actual_started_at")
    created = _utc(row["created_at"], "created_at")
    updated = _utc(row["updated_at"], "updated_at")
    finished = None if row["finished_at"] is None else _utc(
        row["finished_at"], "finished_at"
    )
    if started < scheduled or created != started or updated < created:
        raise PriorityRuntimeError("checkpoint timestamps are inconsistent")
    if finished is not None and finished < updated:
        raise PriorityRuntimeError("checkpoint finished_at precedes updated_at")
    if row["status"] not in CHECKPOINT_STATUSES:
        raise PriorityRuntimeError("checkpoint status is invalid")
    generation = row["generation"]
    if type(generation) is not int or generation < 1:
        raise PriorityRuntimeError("checkpoint generation is invalid")
    owner = _identifier(row["owner_run_id"], "owner_run_id")
    fencing = require_sha256(row["fencing_token"], "fencing_token")
    if fencing != _checkpoint_fencing_token(checkpoint_id, generation, owner):
        raise PriorityRuntimeError("checkpoint fencing token is invalid")
    shards = row["shards"]
    if not isinstance(shards, list) or not shards or len(shards) > 20000:
        raise PriorityRuntimeError("checkpoint shards must be a bounded non-empty list")
    validated_shards = [_validate_shard(item) for item in shards]
    ids = [item["shard_id"] for item in validated_shards]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise PriorityRuntimeError("checkpoint shards must be sorted and unique")
    expected_checkpoint_id = "CP-" + hashlib.sha256(
        _canonical(
            {
                "workload_id": row["workload_id"],
                "window_from": window_from.isoformat(),
                "window_to": window_to.isoformat(),
                "shard_ids": ids,
            }
        )
    ).hexdigest()[:24].upper()
    if checkpoint_id != expected_checkpoint_id:
        raise PriorityRuntimeError("checkpoint_id differs from canonical workload")
    submitted_digest = require_sha256(row["checkpoint_digest"], "checkpoint_digest")
    if submitted_digest != _checkpoint_digest(row):
        raise PriorityRuntimeError("checkpoint digest mismatch")
    if row["status"] in {"COMPLETED", "COMPLETED_WITH_BLOCKS"}:
        if finished is None or any(
            shard["status"] not in {"COMPLETED", "BLOCKED"}
            for shard in validated_shards
        ):
            raise PriorityRuntimeError("terminal checkpoint contains unfinished shards")
    elif finished is not None:
        raise PriorityRuntimeError("non-terminal checkpoint cannot have finished_at")
    row["shards"] = validated_shards
    return row


def _safe_store_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            current.mkdir(mode=0o700)
            metadata = os.lstat(current)
        except OSError as exc:
            raise PriorityRuntimeError("checkpoint store path is unreadable") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise PriorityRuntimeError("checkpoint store must use real directories")
    return absolute


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise PriorityRuntimeError("cannot open checkpoint guard safely") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PriorityRuntimeError("checkpoint guard must be a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise PriorityRuntimeError("cannot inspect checkpoint target safely") from exc
    if existing is not None and (
        stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)
    ):
        raise PriorityRuntimeError("checkpoint target must be a real regular file")
    content = _canonical(value) + b"\n"
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(temporary, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise PriorityRuntimeError("checkpoint temporary target is not regular")
            offset = 0
            while offset < len(content):
                offset += os.write(descriptor, content[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
        directory = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except (OSError, PriorityRuntimeError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, PriorityRuntimeError):
            raise
        raise PriorityRuntimeError("checkpoint atomic write failed") from exc


class AtomicCheckpointStore:
    """Local durable-store primitive used by tests and authorized filesystems.

    Callers must separately pass the trusted production-store gate. Merely
    constructing this class never proves that an ephemeral GitHub workspace is
    durable.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = _safe_store_root(Path(root))

    def _paths(self, workload_id: str) -> tuple[Path, Path]:
        checked = _identifier(workload_id, "workload_id")
        return self.root / f"{checked}.checkpoint.json", self.root / f"{checked}.guard"

    def load(self, workload_id: str) -> dict[str, Any] | None:
        path, guard = self._paths(workload_id)
        with _locked(guard):
            return self._load_unlocked(path)

    def _load_unlocked(self, path: Path) -> dict[str, Any] | None:
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise PriorityRuntimeError("cannot inspect priority checkpoint") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise PriorityRuntimeError("priority checkpoint must be a real regular file")
        try:
            content = safe_regular_file(
                path,
                field="priority checkpoint",
                max_bytes=16 * 1024 * 1024,
            )
            payload = strict_json_object(content, "priority checkpoint")
        except ValueError as exc:
            raise PriorityRuntimeError(str(exc)) from exc
        return _validate_checkpoint(payload)

    def create(
        self,
        *,
        workload_id: Any,
        workload_class: str,
        owner_run_id: Any,
        scheduled_at: datetime,
        actual_started_at: datetime,
        shards: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        checked_workload = _identifier(workload_id, "workload_id")
        checked_owner = _identifier(owner_run_id, "owner_run_id")
        if workload_class not in PRIORITIES:
            raise PriorityRuntimeError("workload_class is invalid")
        scheduled = _utc(scheduled_at, "scheduled_at")
        started = _utc(actual_started_at, "actual_started_at")
        if started < scheduled:
            raise PriorityRuntimeError("actual_started_at precedes scheduled_at")
        checked_shards = sorted(
            (_validate_shard(item) for item in shards), key=lambda item: item["shard_id"]
        )
        if not checked_shards:
            raise PriorityRuntimeError("checkpoint requires at least one shard")
        window_dates = [
            _partition_date(item["partition_value"])
            for item in checked_shards
            if item["partition_kind"] == "DATE"
        ]
        window_from = min(window_dates, default=date(2026, 5, 30)).isoformat()
        window_to = max(window_dates, default=date(2026, 8, 27)).isoformat()
        checkpoint_id = "CP-" + hashlib.sha256(
            _canonical(
                {
                    "workload_id": checked_workload,
                    "window_from": window_from,
                    "window_to": window_to,
                    "shard_ids": [item["shard_id"] for item in checked_shards],
                }
            )
        ).hexdigest()[:24].upper()
        row = {
            "schema_version": "1.0",
            "checkpoint_id": checkpoint_id,
            "workload_id": checked_workload,
            "workload_class": workload_class,
            "priority": PRIORITIES[workload_class],
            "window_from": window_from,
            "window_to": window_to,
            "scheduled_at": _timestamp(scheduled),
            "actual_started_at": _timestamp(started),
            "finished_at": None,
            "status": "RUNNING",
            "generation": 1,
            "fencing_token": _checkpoint_fencing_token(checkpoint_id, 1, checked_owner),
            "owner_run_id": checked_owner,
            "created_at": _timestamp(started),
            "updated_at": _timestamp(started),
            "shards": checked_shards,
            "checkpoint_digest": "",
        }
        row["checkpoint_digest"] = _checkpoint_digest(row)
        validated = _validate_checkpoint(row)
        path, guard = self._paths(checked_workload)
        with _locked(guard):
            try:
                os.lstat(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise CheckpointCasError("cannot inspect checkpoint target") from exc
            else:
                raise CheckpointCasError("checkpoint already exists")
            _atomic_write(path, validated)
        return validated

    def _mutate(
        self,
        workload_id: str,
        *,
        expected_generation: int,
        fencing_token: str,
        mutate: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        path, guard = self._paths(workload_id)
        with _locked(guard):
            row = self._load_unlocked(path)
            if row is None:
                raise CheckpointCasError("checkpoint is missing")
            if row["generation"] != expected_generation:
                raise CheckpointCasError("checkpoint generation CAS mismatch")
            if row["fencing_token"] != require_sha256(fencing_token, "fencing_token"):
                raise FencingViolation("checkpoint fencing token is stale")
            mutate(row)
            row["checkpoint_digest"] = _checkpoint_digest(row)
            validated = _validate_checkpoint(row)
            _atomic_write(path, validated)
            return validated

    def claim_resume(
        self,
        workload_id: str,
        *,
        expected_generation: int,
        owner_run_id: Any,
        now: datetime,
    ) -> dict[str, Any]:
        path, guard = self._paths(workload_id)
        current = _utc(now, "now")
        owner = _identifier(owner_run_id, "owner_run_id")
        with _locked(guard):
            row = self._load_unlocked(path)
            if row is None or row["generation"] != expected_generation:
                raise CheckpointCasError("checkpoint generation CAS mismatch")
            if row["status"] not in {"PREEMPTED", "BLOCKED"}:
                raise CheckpointCasError("only a stopped checkpoint may be resumed")
            _advance_updated_at(row, current)
            row["generation"] += 1
            row["owner_run_id"] = owner
            row["fencing_token"] = _checkpoint_fencing_token(
                row["checkpoint_id"], row["generation"], owner
            )
            row["status"] = "RUNNING"
            row["finished_at"] = None
            for shard in row["shards"]:
                if shard["status"] == "IN_PROGRESS":
                    shard["status"] = "PENDING"
                    shard["started_at"] = None
                    shard["finished_at"] = None
                    shard["output"] = None
                    shard["failure_code"] = None
            row["checkpoint_digest"] = _checkpoint_digest(row)
            validated = _validate_checkpoint(row)
            _atomic_write(path, validated)
            return validated

    def start_shard(
        self,
        workload_id: str,
        *,
        shard_id_value: str,
        expected_generation: int,
        fencing_token: str,
        now: datetime,
    ) -> tuple[dict[str, Any], bool]:
        current = _utc(now, "now")
        target = require_sha256(shard_id_value, "shard_id")
        changed = False

        def mutate(row: dict[str, Any]) -> None:
            nonlocal changed
            if row["status"] != "RUNNING":
                raise PriorityRuntimeError("checkpoint is not running")
            for shard in row["shards"]:
                if shard["shard_id"] != target:
                    continue
                if shard["status"] == "COMPLETED":
                    return
                if shard["status"] == "IN_PROGRESS":
                    return
                if shard["status"] != "PENDING":
                    raise PriorityRuntimeError("blocked shard cannot be restarted")
                if shard["attempt_count"] >= 2:
                    raise PriorityRuntimeError("shard attempt budget is exhausted")
                _advance_updated_at(row, current)
                shard["attempt_count"] += 1
                shard["idempotency_key"] = shard_idempotency_key(
                    shard, shard["attempt_count"]
                )
                shard["status"] = "IN_PROGRESS"
                shard["started_at"] = _timestamp(current)
                changed = True
                return
            raise PriorityRuntimeError("shard_id was not found")

        row = self._mutate(
            workload_id,
            expected_generation=expected_generation,
            fencing_token=fencing_token,
            mutate=mutate,
        )
        return row, changed

    def complete_shard(
        self,
        workload_id: str,
        *,
        shard_id_value: str,
        expected_generation: int,
        fencing_token: str,
        artifact_root: Path,
        output_path: str,
        now: datetime,
    ) -> dict[str, Any]:
        current = _utc(now, "now")
        target = require_sha256(shard_id_value, "shard_id")
        relative = safe_relative_path(output_path, "output_path")
        try:
            content = safe_regular_file(
                Path(os.path.abspath(artifact_root)) / relative,
                field="shard output",
                max_bytes=64 * 1024 * 1024,
            )
        except ValueError as exc:
            raise PriorityRuntimeError(str(exc)) from exc
        output = {
            "path": relative.as_posix(),
            "sha256": sha256_bytes(content),
            "size_bytes": len(content),
        }

        def mutate(row: dict[str, Any]) -> None:
            for shard in row["shards"]:
                if shard["shard_id"] != target:
                    continue
                if shard["status"] == "COMPLETED":
                    if shard["output"] != output:
                        raise PriorityRuntimeError("completed shard output is immutable")
                    return
                if shard["status"] != "IN_PROGRESS":
                    raise PriorityRuntimeError("only an in-progress shard may complete")
                _advance_updated_at(row, current)
                shard["status"] = "COMPLETED"
                shard["finished_at"] = _timestamp(current)
                shard["output"] = output
                shard["failure_code"] = None
                return
            raise PriorityRuntimeError("shard_id was not found")

        return self._mutate(
            workload_id,
            expected_generation=expected_generation,
            fencing_token=fencing_token,
            mutate=mutate,
        )

    def verify_completed_outputs(
        self,
        workload_id: str,
        *,
        artifact_root: Path,
    ) -> dict[str, Any]:
        """Reopen every completed artifact and verify size and SHA-256."""

        row = self.load(workload_id)
        if row is None:
            raise CheckpointCasError("checkpoint is missing")
        verified = 0
        for shard in row["shards"]:
            if shard["status"] != "COMPLETED":
                continue
            output = shard["output"]
            relative = safe_relative_path(output["path"], "output.path")
            try:
                content = safe_regular_file(
                    Path(os.path.abspath(artifact_root)) / relative,
                    field="completed shard output",
                    max_bytes=64 * 1024 * 1024,
                )
            except ValueError as exc:
                raise PriorityRuntimeError(str(exc)) from exc
            if len(content) != output["size_bytes"]:
                raise PriorityRuntimeError("completed shard output size mismatch")
            if sha256_bytes(content) != output["sha256"]:
                raise PriorityRuntimeError("completed shard output digest mismatch")
            verified += 1
        return {
            "schema_version": "1.0",
            "status": "PASS_COMPLETED_OUTPUT_VERIFICATION",
            "checkpoint_id": row["checkpoint_id"],
            "checkpoint_digest": row["checkpoint_digest"],
            "verified_completed_shards": verified,
        }

    def block_shard(
        self,
        workload_id: str,
        *,
        shard_id_value: str,
        failure_code: Any,
        expected_generation: int,
        fencing_token: str,
        now: datetime,
    ) -> dict[str, Any]:
        current = _utc(now, "now")
        target = require_sha256(shard_id_value, "shard_id")
        code = _identifier(failure_code, "failure_code")

        def mutate(row: dict[str, Any]) -> None:
            for shard in row["shards"]:
                if shard["shard_id"] != target:
                    continue
                if shard["status"] != "IN_PROGRESS":
                    raise PriorityRuntimeError("only an in-progress shard may be blocked")
                _advance_updated_at(row, current)
                shard["status"] = "BLOCKED"
                shard["finished_at"] = _timestamp(current)
                shard["failure_code"] = code
                shard["output"] = None
                return
            raise PriorityRuntimeError("shard_id was not found")

        return self._mutate(
            workload_id,
            expected_generation=expected_generation,
            fencing_token=fencing_token,
            mutate=mutate,
        )

    def preempt(
        self,
        workload_id: str,
        *,
        expected_generation: int,
        fencing_token: str,
        now: datetime,
    ) -> dict[str, Any]:
        current = _utc(now, "now")

        def mutate(row: dict[str, Any]) -> None:
            if row["status"] != "RUNNING":
                raise PriorityRuntimeError("only a running checkpoint may be preempted")
            _advance_updated_at(row, current)
            row["status"] = "PREEMPTED"
            for shard in row["shards"]:
                if shard["status"] == "IN_PROGRESS":
                    shard["status"] = "PENDING"
                    shard["started_at"] = None
                    shard["finished_at"] = None
                    shard["output"] = None
                    shard["failure_code"] = None

        return self._mutate(
            workload_id,
            expected_generation=expected_generation,
            fencing_token=fencing_token,
            mutate=mutate,
        )

    def finish(
        self,
        workload_id: str,
        *,
        expected_generation: int,
        fencing_token: str,
        now: datetime,
    ) -> dict[str, Any]:
        current = _utc(now, "now")

        def mutate(row: dict[str, Any]) -> None:
            statuses = {shard["status"] for shard in row["shards"]}
            if not statuses <= {"COMPLETED", "BLOCKED"}:
                raise PriorityRuntimeError("checkpoint still contains unfinished shards")
            _advance_updated_at(row, current)
            row["status"] = (
                "COMPLETED_WITH_BLOCKS" if "BLOCKED" in statuses else "COMPLETED"
            )
            row["finished_at"] = _timestamp(current)

        return self._mutate(
            workload_id,
            expected_generation=expected_generation,
            fencing_token=fencing_token,
            mutate=mutate,
        )


__all__ = [
    "AtomicCheckpointStore",
    "BlockedCheckpointStore",
    "CheckpointCasError",
    "FencingViolation",
    "MARKETS",
    "POLICY_PATH",
    "PRIORITIES",
    "PriorityRuntimeError",
    "load_priority_policy",
    "make_shard",
    "require_production_checkpoint_store",
    "shard_id",
    "shard_idempotency_key",
    "validate_priority_policy",
]
