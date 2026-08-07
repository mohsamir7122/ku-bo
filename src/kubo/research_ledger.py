from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterator, Sequence

from .hashing import canonical_json_bytes, sha256_bytes, sha256_file
from .reporting import DEEP_RESEARCH_CANDIDATE_FIELDS
from .request_contracts import is_forbidden_research_output_field
from .strict import parse_aware, require_sha256


try:  # pragma: no cover - the Windows branch is exercised only on Windows.
    import fcntl as _fcntl
except ImportError:  # pragma: no cover
    _fcntl = None

try:  # pragma: no cover - the POSIX branch is exercised in CI.
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover
    _msvcrt = None


DECISION_STREAM = "research_decisions"
OUTCOME_STREAM = "research_outcomes"
DECISION_EVENT_TYPE = "REPORT_RECORDED"
OUTCOME_EVENT_TYPE = "OUTCOME_RECORDED"

# These fields describe information learned after a research decision.  They
# belong in the outcome stream even when nested inside an otherwise valid
# build_report result.
_OUTCOME_EXACT_FIELDS = frozenset(
    {
        "actual_return",
        "benchmark_return",
        "event_realized",
        "exit_price",
        "exit_price_fils",
        "fill_status",
        "future_return",
        "gross_return",
        "max_adverse_excursion",
        "max_favorable_excursion",
        "net_excess_return",
        "net_return",
        "outcome",
        "outcome_at",
        "outcome_evidence_hash",
        "outcomes",
        "realized_positive",
        "target_hit",
    }
)
_OUTCOME_FIELD_PREFIXES = (
    "actual_",
    "exit_price",
    "future_",
    "outcome_",
    "realized_",
)
_OUTCOME_FIELD_SUFFIXES = ("_target_hit", "_realized_return")
_OUTCOME_RESERVED_PAYLOAD_FIELDS = frozenset(
    {
        "decision_id",
        "event_hash",
        "event_seq",
        "evidence_hashes",
        "ledger_id",
        "observed_at",
        "outcome_id",
        "payload_hash",
        "previous_event_hash",
        "recorded_at",
        "stream",
    }
)


def _nonempty(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _json_snapshot(value: Any, field: str) -> Any:
    """Return a detached, strict-JSON copy (NaN and custom objects rejected)."""

    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field} must be strict JSON") from exc


def _normalized_field_name(value: Any) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value).strip())
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def _find_outcome_field(value: Any, path: str = "report") -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = _normalized_field_name(key)
            if (
                normalized in _OUTCOME_EXACT_FIELDS
                or normalized.startswith(_OUTCOME_FIELD_PREFIXES)
                or normalized.endswith(_OUTCOME_FIELD_SUFFIXES)
            ):
                return f"{path}.{key}"
            hit = _find_outcome_field(nested, f"{path}.{key}")
            if hit:
                return hit
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            hit = _find_outcome_field(nested, f"{path}[{index}]")
            if hit:
                return hit
    return None


def _find_forbidden_candidate_field(value: Any, path: str) -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if is_forbidden_research_output_field(key):
                return f"{path}.{key}"
            hit = _find_forbidden_candidate_field(nested, f"{path}.{key}")
            if hit:
                return hit
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            hit = _find_forbidden_candidate_field(nested, f"{path}[{index}]")
            if hit:
                return hit
    return None


def _validate_research_candidate(candidate: Any, index: int) -> list[str]:
    prefix = f"report.candidates[{index}]"
    if not isinstance(candidate, dict):
        return [f"CANDIDATE_NOT_OBJECT:{prefix}"]
    errors: list[str] = []
    forbidden = _find_forbidden_candidate_field(candidate, prefix)
    if forbidden:
        errors.append(f"FORBIDDEN_RESEARCH_CLAIM_FIELD:{forbidden}")
    unknown = sorted(set(candidate) - DEEP_RESEARCH_CANDIDATE_FIELDS)
    if unknown:
        errors.append(f"CANDIDATE_FIELDS_NOT_ALLOWED:{prefix}:" + ",".join(unknown))

    code = str(candidate.get("security_code", "")).strip()
    ticker = str(candidate.get("ticker", "")).strip()
    if not code.isdigit() or not ticker:
        errors.append(f"CANDIDATE_IDENTITY_INVALID:{prefix}")
    rank = candidate.get("rank")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
        errors.append(f"CANDIDATE_RANK_INVALID:{prefix}")
    score = candidate.get("research_score")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
        or not 0 <= float(score) <= 100
    ):
        errors.append(f"CANDIDATE_RESEARCH_SCORE_INVALID:{prefix}")
    if candidate.get("score_kind") != "SOURCE_MOSAIC_EVIDENCE_SCORE_NOT_PROBABILITY":
        errors.append(f"CANDIDATE_SCORE_KIND_INVALID:{prefix}")
    status = candidate.get("decision_status")
    if status not in {"RESEARCH_CANDIDATE", "WATCH", "ABSTAIN"}:
        errors.append(f"CANDIDATE_DECISION_STATUS_INVALID:{prefix}")
    selected = candidate.get("selected")
    if selected is not None and not isinstance(selected, bool):
        errors.append(f"CANDIDATE_SELECTED_INVALID:{prefix}")
    if selected is True and status != "RESEARCH_CANDIDATE":
        errors.append(f"CANDIDATE_SELECTION_CONTRADICTS_STATUS:{prefix}")
    for field in (
        "official_catalyst_confirmed",
        "all_directional_catalysts_primary_confirmed",
        "source_conflict",
    ):
        if field in candidate and not isinstance(candidate[field], bool):
            errors.append(f"CANDIDATE_BOOLEAN_FIELD_INVALID:{prefix}.{field}")
    for field in (
        "independent_source_groups",
        "minimum_independent_source_groups",
    ):
        value = candidate.get(field)
        if field in candidate and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            errors.append(f"CANDIDATE_COUNT_FIELD_INVALID:{prefix}.{field}")
    for field, minimum, maximum in (
        ("evidence_coverage", 0.0, 1.0),
        ("source_quality_factor", 0.0, 1.0),
        ("evidence_direction_alignment", -1.0, 1.0),
        ("community_contribution_total", -1.0, 1.0),
        ("community_contribution_cap", 0.0, 1.0),
    ):
        value = candidate.get(field)
        if field in candidate and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not minimum <= float(value) <= maximum
        ):
            errors.append(f"CANDIDATE_METRIC_FIELD_INVALID:{prefix}.{field}")
    role_coverage = candidate.get("per_security_role_coverage")
    if "per_security_role_coverage" in candidate and (
        not isinstance(role_coverage, dict)
        or any(
            not isinstance(role, str)
            or not role
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for role, value in role_coverage.items()
        )
    ):
        errors.append(f"CANDIDATE_ROLE_COVERAGE_INVALID:{prefix}")
    role_gaps = candidate.get("per_security_role_gaps")
    if "per_security_role_gaps" in candidate and (
        not isinstance(role_gaps, dict)
        or any(
            not isinstance(role, str)
            or not role
            or not isinstance(gap, dict)
            or set(gap) != {"actual", "required"}
            or any(
                isinstance(gap.get(field), bool)
                or not isinstance(gap.get(field), int)
                or gap[field] < 0
                for field in ("actual", "required")
            )
            for role, gap in role_gaps.items()
        )
    ):
        errors.append(f"CANDIDATE_ROLE_GAPS_INVALID:{prefix}")
    contributions = candidate.get("signal_contributions")
    if "signal_contributions" in candidate and (
        not isinstance(contributions, dict)
        or any(
            not isinstance(signal, str)
            or not signal
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not -1 <= float(value) <= 1
            for signal, value in contributions.items()
        )
    ):
        errors.append(f"CANDIDATE_SIGNAL_CONTRIBUTIONS_INVALID:{prefix}")
    scope_label = candidate.get("scope_label")
    if scope_label is not None and scope_label not in {
        "CANDIDATE_SET_RESEARCH_RANK",
        "FULL_MARKET_RESEARCH_RANK",
    }:
        errors.append(f"CANDIDATE_SCOPE_LABEL_INVALID:{prefix}")
    reasons = candidate.get("reason_codes")
    if (
        not isinstance(reasons, list)
        or any(not isinstance(item, str) or not item.strip() for item in reasons)
        or len(reasons) != len(set(reasons))
    ):
        errors.append(f"CANDIDATE_REASON_CODES_INVALID:{prefix}")
    elif any(is_forbidden_research_output_field(item) for item in reasons):
        errors.append(f"FORBIDDEN_RESEARCH_CLAIM_VALUE:{prefix}.reason_codes")
    return errors


def validate_research_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["REPORT_NOT_OBJECT"]
    try:
        snapshot = _json_snapshot(report, "report")
    except ValueError as exc:
        return [str(exc)]
    forbidden = _find_outcome_field(snapshot)
    if forbidden:
        errors.append(f"FORBIDDEN_OUTCOME_FIELD:{forbidden}")
    if snapshot.get("mode") != "research_network":
        errors.append("REPORT_MODE_NOT_RESEARCH_NETWORK")
    request = snapshot.get("request")
    if not isinstance(request, dict):
        errors.append("REPORT_REQUEST_NOT_OBJECT")
    else:
        if not str(request.get("request_id", "")).strip():
            errors.append("MISSING_REQUEST_ID")
        if request.get("mode") != "research_network":
            errors.append("REQUEST_MODE_NOT_RESEARCH_NETWORK")
        if not str(request.get("product_id", "")).strip():
            errors.append("MISSING_PRODUCT_ID")
    if not str(snapshot.get("status", "")).strip():
        errors.append("MISSING_REPORT_STATUS")
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list):
        errors.append("CANDIDATES_NOT_LIST")
    else:
        for index, candidate in enumerate(candidates):
            errors.extend(_validate_research_candidate(candidate, index))
    try:
        parse_aware(snapshot.get("decision_at"), "decision_at")
    except ValueError as exc:
        errors.append(str(exc))
    try:
        require_sha256(snapshot.get("evidence_packet_hash"), "evidence_packet_hash")
    except ValueError:
        errors.append("MISSING_OR_INVALID_EVIDENCE_PACKET_HASH")
    if isinstance(request, dict):
        request_scope = request.get("scope")
        packet_scope = snapshot.get("scope")
        compatible_packet_scopes = {
            "CANDIDATE_SET": {"CANDIDATE_SET", "FULL_MARKET"},
            "NAMED_SECURITIES": {"NAMED_SECURITIES", "FULL_MARKET"},
            "FULL_MARKET": {"FULL_MARKET"},
        }
        if (
            request_scope not in compatible_packet_scopes
            or packet_scope not in compatible_packet_scopes.get(request_scope, set())
        ):
            errors.append(
                f"REPORT_SCOPE_INCOMPATIBLE_WITH_REQUEST:{request_scope}:{packet_scope}"
            )
        requested_codes = {
            str(item) for item in request.get("security_codes", [])
        }
        if requested_codes and isinstance(candidates, list):
            candidate_codes = {
                str(item.get("security_code"))
                for item in candidates
                if isinstance(item, dict)
            }
            if candidate_codes - requested_codes:
                errors.append("REPORT_CONTAINS_UNREQUESTED_SECURITIES")
    boundaries = snapshot.get("claim_boundaries")
    if not isinstance(boundaries, dict):
        errors.append("CLAIM_BOUNDARIES_NOT_OBJECT")
    else:
        if boundaries.get("research_score_is_probability") is not False:
            errors.append("RESEARCH_SCORE_PROBABILITY_BOUNDARY_MISSING")
        if boundaries.get("probability_allowed") not in (None, False):
            errors.append("PROBABILITY_ALLOWED_IN_RESEARCH_REPORT")
        if boundaries.get("recommendation_allowed") not in (None, False):
            errors.append("RECOMMENDATION_ALLOWED_IN_RESEARCH_REPORT")
    return sorted(set(errors))


def _lock_path(stream_path: Path) -> Path:
    return stream_path.with_name(stream_path.name + ".lock")


@contextmanager
def _exclusive_lock(stream_path: Path) -> Iterator[None]:
    """Use a sidecar advisory lock on platforms that expose one."""

    lock_path = _lock_path(stream_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        if _fcntl is not None:
            _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX)
        elif _msvcrt is not None:  # pragma: no cover
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            _msvcrt.locking(handle.fileno(), _msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if _fcntl is not None:
                _fcntl.flock(handle.fileno(), _fcntl.LOCK_UN)
            elif _msvcrt is not None:  # pragma: no cover
                handle.seek(0)
                _msvcrt.locking(handle.fileno(), _msvcrt.LK_UNLCK, 1)


@contextmanager
def _locked_streams(paths: Sequence[Path]) -> Iterator[None]:
    # Sorting makes multi-stream operations deadlock-safe across processes.
    unique = sorted({path.resolve() for path in paths}, key=str)
    with ExitStack() as stack:
        for path in unique:
            stack.enter_context(_exclusive_lock(path))
        yield


def _read_jsonl_unlocked(path: Path, stream_name: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = path.read_bytes()
    if not data:
        return []
    if not data.endswith(b"\n"):
        raise ValueError(f"{stream_name} has a truncated final record")
    events: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(data.splitlines(), start=1):
        if not raw_line:
            raise ValueError(f"{stream_name} has a blank record at line {line_number}")
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid {stream_name} JSON at line {line_number}") from exc
        if not isinstance(event, dict):
            raise ValueError(f"{stream_name} line {line_number} is not an object")
        events.append(event)
    return events


def _append_jsonl_unlocked(path: Path, event: dict[str, Any]) -> None:
    """Append one canonical record with one O_APPEND write while lock is held."""

    data = canonical_json_bytes(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_BINARY"):  # pragma: no cover
        flags |= os.O_BINARY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    original_size = path.stat().st_size if path.exists() else 0
    descriptor = os.open(path, flags, 0o600)
    try:
        written = os.write(descriptor, data)
        if written != len(data):
            raise OSError(f"short atomic append: wrote {written} of {len(data)} bytes")
        os.fsync(descriptor)
    except BaseException:
        # Restore only the uncommitted suffix.  Bytes belonging to previous
        # ledger events are never rewritten.
        try:
            os.ftruncate(descriptor, original_size)
            os.fsync(descriptor)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8"))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:  # pragma: no cover - directory fsync is not universal.
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _event_hash(event: dict[str, Any]) -> str:
    candidate = dict(event)
    candidate.pop("event_hash", None)
    return sha256_bytes(canonical_json_bytes(candidate))


def _recorded_time(recorded_at: str | None, *, test_mode: bool) -> datetime:
    if recorded_at is None:
        return datetime.now(timezone.utc)
    if not test_mode:
        raise ValueError("caller-supplied recorded_at requires test_mode")
    return parse_aware(recorded_at, "recorded_at")


def _runtime_hmac_key(value: bytes | bytearray | memoryview | None) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("hmac_key must be runtime bytes")
    key = bytes(value)
    if len(key) < 32:
        raise ValueError("hmac_key must contain at least 32 runtime bytes")
    return key


class ResearchDecisionLedger:
    """Append-only research reports and separately linked realized outcomes.

    The decision stream contains the exact strict-JSON snapshot returned by
    ``build_report``.  There is intentionally no amend/update API: a later run
    receives a new decision id and cannot rewrite the earlier report.
    """

    def __init__(self, decision_path: Path, outcome_path: Path, ledger_id: str):
        self.decision_path = Path(decision_path)
        self.outcome_path = Path(outcome_path)
        self.ledger_id = _nonempty(ledger_id, "ledger_id")
        if self.decision_path.resolve() == self.outcome_path.resolve():
            raise ValueError("decision and outcome streams must use separate paths")

    def decisions(self) -> list[dict[str, Any]]:
        with _exclusive_lock(self.decision_path):
            return deepcopy(_read_jsonl_unlocked(self.decision_path, DECISION_STREAM))

    def outcomes(self) -> list[dict[str, Any]]:
        with _exclusive_lock(self.outcome_path):
            return deepcopy(_read_jsonl_unlocked(self.outcome_path, OUTCOME_STREAM))

    def record_report(
        self,
        report: dict[str, Any],
        *,
        actor_or_model_id: str,
        policy_hash: str,
        code_hash: str,
        configuration_hash: str,
        decision_id: str | None = None,
        issued_at: str | None = None,
        recorded_at: str | None = None,
        test_mode: bool = False,
    ) -> dict[str, Any]:
        """Freeze one ``build_report`` result in the research decision stream."""

        snapshot = _json_snapshot(report, "report")
        errors = validate_research_report(snapshot)
        if errors:
            raise ValueError(";".join(errors))
        request = snapshot["request"]
        decision_id = _nonempty(decision_id or request["request_id"], "decision_id")
        actor_or_model_id = _nonempty(actor_or_model_id, "actor_or_model_id")
        policy_hash = require_sha256(policy_hash, "policy_hash")
        code_hash = require_sha256(code_hash, "code_hash")
        configuration_hash = require_sha256(configuration_hash, "configuration_hash")
        decision = parse_aware(snapshot["decision_at"], "decision_at")
        supplied_issued = parse_aware(issued_at, "issued_at") if issued_at is not None else None
        supplied_recorded = _recorded_time(recorded_at, test_mode=test_mode) if recorded_at is not None else None

        with _exclusive_lock(self.decision_path):
            # Runtime timestamps are sampled only after taking the lock, so
            # concurrently queued writers remain monotonic in append order.
            issued = supplied_issued or datetime.now(timezone.utc)
            recorded = supplied_recorded or datetime.now(timezone.utc)
            if issued < decision:
                raise ValueError("issued_at cannot precede decision_at")
            if recorded < issued:
                raise ValueError("recorded_at cannot precede issued_at")
            events = _read_jsonl_unlocked(self.decision_path, DECISION_STREAM)
            existing_errors = self._verify_decisions_unlocked(events)
            if existing_errors:
                raise ValueError("cannot append to invalid decision stream: " + ";".join(existing_errors))
            if any(event.get("ledger_id") != self.ledger_id for event in events):
                raise ValueError("existing decision stream contains another ledger_id")
            if any(event.get("decision_id") == decision_id for event in events):
                raise ValueError("decision_id already recorded; past decisions cannot be rewritten")
            if events and recorded < parse_aware(events[-1].get("recorded_at"), "recorded_at"):
                raise ValueError("recorded_at must be monotonic")
            event: dict[str, Any] = {
                "schema_version": "1.0",
                "stream": DECISION_STREAM,
                "ledger_id": self.ledger_id,
                "event_type": DECISION_EVENT_TYPE,
                "event_seq": len(events) + 1,
                "decision_id": decision_id,
                "request_id": str(request["request_id"]),
                "product_id": str(request["product_id"]),
                "decision_at": decision.isoformat(),
                "issued_at": issued.isoformat(),
                "recorded_at": recorded.isoformat(),
                "actor_or_model_id": actor_or_model_id,
                "policy_hash": policy_hash,
                "code_hash": code_hash,
                "configuration_hash": configuration_hash,
                "evidence_packet_hash": snapshot["evidence_packet_hash"],
                "report": snapshot,
                "report_hash": sha256_bytes(canonical_json_bytes(snapshot)),
                "previous_event_hash": events[-1].get("event_hash") if events else None,
            }
            event["event_hash"] = _event_hash(event)
            _append_jsonl_unlocked(self.decision_path, event)
            return deepcopy(event)

    def append_outcome(
        self,
        *,
        outcome_id: str,
        decision_id: str,
        observed_at: str,
        payload: dict[str, Any],
        evidence_hashes: Sequence[str],
        actor_or_model_id: str,
        recorded_at: str | None = None,
        test_mode: bool = False,
    ) -> dict[str, Any]:
        """Append a realized observation to the separate outcome stream."""

        outcome_id = _nonempty(outcome_id, "outcome_id")
        decision_id = _nonempty(decision_id, "decision_id")
        actor_or_model_id = _nonempty(actor_or_model_id, "actor_or_model_id")
        snapshot = _json_snapshot(payload, "outcome payload")
        if not isinstance(snapshot, dict) or not snapshot:
            raise ValueError("outcome payload must be a non-empty object")
        shadowed = sorted(set(snapshot).intersection(_OUTCOME_RESERVED_PAYLOAD_FIELDS))
        if shadowed:
            raise ValueError("outcome payload shadows envelope fields: " + ",".join(shadowed))
        if not isinstance(evidence_hashes, (list, tuple)) or not evidence_hashes:
            raise ValueError("evidence_hashes must be a non-empty sequence")
        normalized_hashes = [require_sha256(value, "evidence_hash") for value in evidence_hashes]
        if len(set(normalized_hashes)) != len(normalized_hashes):
            raise ValueError("evidence_hashes must be unique")
        observed = parse_aware(observed_at, "observed_at")
        supplied_recorded = _recorded_time(recorded_at, test_mode=test_mode) if recorded_at is not None else None

        with _locked_streams((self.decision_path, self.outcome_path)):
            recorded = supplied_recorded or datetime.now(timezone.utc)
            if recorded < observed:
                raise ValueError("recorded_at cannot precede observed_at")
            decisions = _read_jsonl_unlocked(self.decision_path, DECISION_STREAM)
            outcomes = _read_jsonl_unlocked(self.outcome_path, OUTCOME_STREAM)
            existing_errors = self._verify_decisions_unlocked(decisions)
            existing_errors.extend(self._verify_outcomes_unlocked(outcomes, decisions))
            if existing_errors:
                raise ValueError("cannot append to invalid research ledger: " + ";".join(existing_errors))
            matching = [event for event in decisions if event.get("decision_id") == decision_id]
            if len(matching) != 1:
                raise ValueError("outcome requires exactly one existing decision_id")
            if any(event.get("ledger_id") != self.ledger_id for event in [*decisions, *outcomes]):
                raise ValueError("existing stream contains another ledger_id")
            if any(event.get("outcome_id") == outcome_id for event in outcomes):
                raise ValueError("outcome_id already recorded")
            decision_at = parse_aware(matching[0].get("decision_at"), "decision_at")
            if observed < decision_at:
                raise ValueError("observed_at cannot precede decision_at")
            decision_issued_at = parse_aware(matching[0].get("issued_at"), "issued_at")
            if observed < decision_issued_at:
                raise ValueError("observed_at cannot precede decision issued_at")
            decision_recorded_at = parse_aware(matching[0].get("recorded_at"), "recorded_at")
            if observed < decision_recorded_at:
                raise ValueError("observed_at cannot precede decision recorded_at")
            if outcomes and recorded < parse_aware(outcomes[-1].get("recorded_at"), "recorded_at"):
                raise ValueError("recorded_at must be monotonic")
            event: dict[str, Any] = {
                "schema_version": "1.0",
                "stream": OUTCOME_STREAM,
                "ledger_id": self.ledger_id,
                "event_type": OUTCOME_EVENT_TYPE,
                "event_seq": len(outcomes) + 1,
                "outcome_id": outcome_id,
                "decision_id": decision_id,
                "observed_at": observed.isoformat(),
                "recorded_at": recorded.isoformat(),
                "actor_or_model_id": actor_or_model_id,
                "evidence_hashes": normalized_hashes,
                "payload": snapshot,
                "payload_hash": sha256_bytes(canonical_json_bytes(snapshot)),
                "previous_event_hash": outcomes[-1].get("event_hash") if outcomes else None,
            }
            event["event_hash"] = _event_hash(event)
            _append_jsonl_unlocked(self.outcome_path, event)
            return deepcopy(event)

    def _verify_decisions_unlocked(self, events: list[dict[str, Any]]) -> list[str]:
        errors: list[str] = []
        previous: str | None = None
        last_recorded: datetime | None = None
        decision_ids: set[str] = set()
        required = {
            "schema_version",
            "stream",
            "ledger_id",
            "event_type",
            "event_seq",
            "decision_id",
            "request_id",
            "product_id",
            "decision_at",
            "issued_at",
            "recorded_at",
            "actor_or_model_id",
            "policy_hash",
            "code_hash",
            "configuration_hash",
            "evidence_packet_hash",
            "report",
            "report_hash",
            "previous_event_hash",
            "event_hash",
        }
        for expected_seq, event in enumerate(events, start=1):
            prefix = f"decision_{expected_seq}"
            if set(event) != required:
                errors.append(prefix + ":FIELDS")
            if event.get("schema_version") != "1.0":
                errors.append(prefix + ":SCHEMA_VERSION")
            if event.get("stream") != DECISION_STREAM:
                errors.append(prefix + ":STREAM")
            if event.get("ledger_id") != self.ledger_id:
                errors.append(prefix + ":LEDGER_ID")
            if event.get("event_type") != DECISION_EVENT_TYPE:
                errors.append(prefix + ":EVENT_TYPE")
            if event.get("event_seq") != expected_seq:
                errors.append(prefix + ":SEQUENCE")
            if event.get("previous_event_hash") != previous:
                errors.append(prefix + ":PREVIOUS_HASH")
            decision_id = str(event.get("decision_id", ""))
            if not decision_id or decision_id in decision_ids:
                errors.append(prefix + ":DUPLICATE_OR_EMPTY_DECISION_ID")
            decision_ids.add(decision_id)
            try:
                require_sha256(event.get("policy_hash"), "policy_hash")
                require_sha256(event.get("code_hash"), "code_hash")
                require_sha256(event.get("configuration_hash"), "configuration_hash")
                require_sha256(event.get("evidence_packet_hash"), "evidence_packet_hash")
            except ValueError:
                errors.append(prefix + ":ARTIFACT_HASH")
            report = event.get("report")
            if not isinstance(report, dict):
                errors.append(prefix + ":REPORT_NOT_OBJECT")
                report = {}
            report_errors = validate_research_report(report)
            errors.extend(prefix + ":" + error for error in report_errors)
            if event.get("report_hash") != sha256_bytes(canonical_json_bytes(report)):
                errors.append(prefix + ":REPORT_HASH")
            request = report.get("request") if isinstance(report.get("request"), dict) else {}
            if event.get("request_id") != request.get("request_id"):
                errors.append(prefix + ":REQUEST_ID_BINDING")
            if event.get("product_id") != request.get("product_id"):
                errors.append(prefix + ":PRODUCT_ID_BINDING")
            if event.get("decision_at") != report.get("decision_at"):
                errors.append(prefix + ":DECISION_AT_BINDING")
            if event.get("evidence_packet_hash") != report.get("evidence_packet_hash"):
                errors.append(prefix + ":EVIDENCE_PACKET_HASH_BINDING")
            try:
                decision = parse_aware(event.get("decision_at"), "decision_at")
                issued = parse_aware(event.get("issued_at"), "issued_at")
                recorded = parse_aware(event.get("recorded_at"), "recorded_at")
                if issued < decision or recorded < issued or (last_recorded and recorded < last_recorded):
                    errors.append(prefix + ":TIME_ORDER")
                last_recorded = recorded
            except ValueError:
                errors.append(prefix + ":TIMESTAMP")
            expected_hash = _event_hash(event)
            if event.get("event_hash") != expected_hash:
                errors.append(prefix + ":EVENT_HASH")
            previous = event.get("event_hash")
        return errors

    def _verify_outcomes_unlocked(
        self,
        outcomes: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> list[str]:
        errors: list[str] = []
        decision_times: dict[str, tuple[datetime, datetime, datetime]] = {}
        for decision in decisions:
            try:
                decision_times[str(decision.get("decision_id", ""))] = (
                    parse_aware(decision.get("decision_at"), "decision_at"),
                    parse_aware(decision.get("issued_at"), "issued_at"),
                    parse_aware(decision.get("recorded_at"), "recorded_at"),
                )
            except ValueError:
                pass
        previous: str | None = None
        last_recorded: datetime | None = None
        outcome_ids: set[str] = set()
        required = {
            "schema_version",
            "stream",
            "ledger_id",
            "event_type",
            "event_seq",
            "outcome_id",
            "decision_id",
            "observed_at",
            "recorded_at",
            "actor_or_model_id",
            "evidence_hashes",
            "payload",
            "payload_hash",
            "previous_event_hash",
            "event_hash",
        }
        for expected_seq, event in enumerate(outcomes, start=1):
            prefix = f"outcome_{expected_seq}"
            if set(event) != required:
                errors.append(prefix + ":FIELDS")
            if event.get("schema_version") != "1.0":
                errors.append(prefix + ":SCHEMA_VERSION")
            if event.get("stream") != OUTCOME_STREAM:
                errors.append(prefix + ":STREAM")
            if event.get("ledger_id") != self.ledger_id:
                errors.append(prefix + ":LEDGER_ID")
            if event.get("event_type") != OUTCOME_EVENT_TYPE:
                errors.append(prefix + ":EVENT_TYPE")
            if event.get("event_seq") != expected_seq:
                errors.append(prefix + ":SEQUENCE")
            if event.get("previous_event_hash") != previous:
                errors.append(prefix + ":PREVIOUS_HASH")
            outcome_id = str(event.get("outcome_id", ""))
            if not outcome_id or outcome_id in outcome_ids:
                errors.append(prefix + ":DUPLICATE_OR_EMPTY_OUTCOME_ID")
            outcome_ids.add(outcome_id)
            decision_id = str(event.get("decision_id", ""))
            if decision_id not in decision_times:
                errors.append(prefix + ":UNKNOWN_DECISION_ID")
            evidence_hashes = event.get("evidence_hashes")
            if not isinstance(evidence_hashes, list) or not evidence_hashes or len(evidence_hashes) != len(set(evidence_hashes)):
                errors.append(prefix + ":EVIDENCE_HASHES")
            else:
                for digest in evidence_hashes:
                    try:
                        require_sha256(digest, "evidence_hash")
                    except ValueError:
                        errors.append(prefix + ":EVIDENCE_HASH")
            payload = event.get("payload")
            if not isinstance(payload, dict) or not payload:
                errors.append(prefix + ":PAYLOAD_NOT_OBJECT")
                payload = {}
            if event.get("payload_hash") != sha256_bytes(canonical_json_bytes(payload)):
                errors.append(prefix + ":PAYLOAD_HASH")
            try:
                observed = parse_aware(event.get("observed_at"), "observed_at")
                recorded = parse_aware(event.get("recorded_at"), "recorded_at")
                if recorded < observed or (last_recorded and recorded < last_recorded):
                    errors.append(prefix + ":TIME_ORDER")
                if decision_id in decision_times:
                    decision_at, issued_at, decision_recorded_at = decision_times[decision_id]
                    if observed < decision_at:
                        errors.append(prefix + ":OUTCOME_BEFORE_DECISION")
                    if observed < issued_at:
                        errors.append(prefix + ":OUTCOME_BEFORE_ISSUANCE")
                    if observed < decision_recorded_at:
                        errors.append(prefix + ":OUTCOME_BEFORE_DECISION_RECORDING")
                last_recorded = recorded
            except ValueError:
                errors.append(prefix + ":TIMESTAMP")
            expected_hash = _event_hash(event)
            if event.get("event_hash") != expected_hash:
                errors.append(prefix + ":EVENT_HASH")
            previous = event.get("event_hash")
        return errors

    def verify(self) -> dict[str, Any]:
        try:
            with _locked_streams((self.decision_path, self.outcome_path)):
                decisions = _read_jsonl_unlocked(self.decision_path, DECISION_STREAM)
                outcomes = _read_jsonl_unlocked(self.outcome_path, OUTCOME_STREAM)
                errors = self._verify_decisions_unlocked(decisions)
                errors.extend(self._verify_outcomes_unlocked(outcomes, decisions))
        except (OSError, ValueError) as exc:
            return {
                "status": "BLOCKED",
                "decision_events": 0,
                "outcome_events": 0,
                "errors": [str(exc)],
            }
        return {
            "status": "PASS" if decisions and not errors else "BLOCKED",
            "decision_events": len(decisions),
            "outcome_events": len(outcomes),
            "errors": sorted(set(errors)),
            "last_decision_event_hash": decisions[-1].get("event_hash") if decisions else None,
            "last_outcome_event_hash": outcomes[-1].get("event_hash") if outcomes else None,
        }

    @staticmethod
    def _stream_seal(path: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "event_count": len(events),
            "first_event_hash": events[0].get("event_hash") if events else None,
            "last_event_hash": events[-1].get("event_hash") if events else None,
            "content_sha256": sha256_file(path) if path.is_file() else sha256_bytes(b""),
        }

    def seal(
        self,
        path: Path,
        *,
        hmac_key: bytes | bytearray | memoryview | None = None,
        key_id: str | None = None,
        sealed_at: str | None = None,
        test_mode: bool = False,
    ) -> dict[str, Any]:
        key = _runtime_hmac_key(hmac_key)
        if key is None and key_id is not None:
            raise ValueError("key_id requires hmac_key")
        if key is not None:
            key_id = _nonempty(key_id, "key_id")
        if sealed_at is not None:
            if not test_mode:
                raise ValueError("caller-supplied sealed_at requires test_mode")
            supplied_sealed = parse_aware(sealed_at, "sealed_at")
        else:
            supplied_sealed = None

        resolved_seal_path = Path(path).resolve()
        if resolved_seal_path in {self.decision_path.resolve(), self.outcome_path.resolve()}:
            raise ValueError("seal path must be separate from ledger streams")

        with _locked_streams((self.decision_path, self.outcome_path)):
            sealed = supplied_sealed or datetime.now(timezone.utc)
            decisions = _read_jsonl_unlocked(self.decision_path, DECISION_STREAM)
            outcomes = _read_jsonl_unlocked(self.outcome_path, OUTCOME_STREAM)
            errors = self._verify_decisions_unlocked(decisions)
            errors.extend(self._verify_outcomes_unlocked(outcomes, decisions))
            if not decisions or errors:
                raise ValueError("cannot seal an invalid research ledger: " + ";".join(sorted(set(errors))))
            last_recorded = max(
                parse_aware(event["recorded_at"], "recorded_at") for event in [*decisions, *outcomes]
            )
            if sealed < last_recorded:
                raise ValueError("seal cannot predate the last event")
            core: dict[str, Any] = {
                "schema_version": "1.0",
                "ledger_id": self.ledger_id,
                "sealed_at": sealed.isoformat(),
                "decision_stream": self._stream_seal(self.decision_path, decisions),
                "outcome_stream": self._stream_seal(self.outcome_path, outcomes),
            }
            if key is None:
                authentication = {"algorithm": "SHA256-CONTENT"}
            else:
                authenticated_value = {
                    "seal": core,
                    "algorithm": "HMAC-SHA256",
                    "key_id": key_id,
                }
                authentication = {
                    "algorithm": "HMAC-SHA256",
                    "key_id": key_id,
                    "tag": hmac.new(key, canonical_json_bytes(authenticated_value), hashlib.sha256).hexdigest(),
                }
            seal = {**core, "authentication": authentication}
            _atomic_write_json(Path(path), seal)
            return deepcopy(seal)

    def verify_seal(
        self,
        path: Path,
        *,
        hmac_key: bytes | bytearray | memoryview | None = None,
    ) -> dict[str, Any]:
        key = _runtime_hmac_key(hmac_key)
        errors: list[str] = []
        decisions: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        try:
            with _locked_streams((self.decision_path, self.outcome_path)):
                decisions = _read_jsonl_unlocked(self.decision_path, DECISION_STREAM)
                outcomes = _read_jsonl_unlocked(self.outcome_path, OUTCOME_STREAM)
                errors.extend(self._verify_decisions_unlocked(decisions))
                errors.extend(self._verify_outcomes_unlocked(outcomes, decisions))
                if not Path(path).is_file():
                    errors.append("MISSING_SEAL")
                    return {"status": "BLOCKED", "errors": sorted(set(errors))}
                seal = json.loads(Path(path).read_text(encoding="utf-8"))
                if not isinstance(seal, dict):
                    raise ValueError("seal is not an object")
                expected_core = {
                    "schema_version": "1.0",
                    "ledger_id": self.ledger_id,
                    "sealed_at": seal.get("sealed_at"),
                    "decision_stream": self._stream_seal(self.decision_path, decisions),
                    "outcome_stream": self._stream_seal(self.outcome_path, outcomes),
                }
                for field in ("schema_version", "ledger_id", "decision_stream", "outcome_stream"):
                    if seal.get(field) != expected_core[field]:
                        errors.append("SEAL_" + field.upper())
                sealed = parse_aware(seal.get("sealed_at"), "sealed_at")
                if decisions or outcomes:
                    last_recorded = max(
                        parse_aware(event["recorded_at"], "recorded_at")
                        for event in [*decisions, *outcomes]
                    )
                    if sealed < last_recorded:
                        errors.append("SEAL_TIME")
                authentication = seal.get("authentication")
                if not isinstance(authentication, dict):
                    errors.append("SEAL_AUTHENTICATION")
                elif authentication.get("algorithm") == "HMAC-SHA256":
                    if key is None:
                        errors.append("HMAC_KEY_REQUIRED")
                    else:
                        authenticated_value = {
                            "seal": expected_core,
                            "algorithm": "HMAC-SHA256",
                            "key_id": authentication.get("key_id"),
                        }
                        expected_tag = hmac.new(
                            key, canonical_json_bytes(authenticated_value), hashlib.sha256
                        ).hexdigest()
                        if not hmac.compare_digest(str(authentication.get("tag", "")), expected_tag):
                            errors.append("HMAC_MISMATCH")
                        if not str(authentication.get("key_id", "")).strip():
                            errors.append("HMAC_KEY_ID")
                elif authentication.get("algorithm") != "SHA256-CONTENT":
                    errors.append("UNSUPPORTED_SEAL_ALGORITHM")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"INVALID_SEAL:{exc}")
        return {"status": "PASS" if decisions and not errors else "BLOCKED", "errors": sorted(set(errors))}


ResearchLedger = ResearchDecisionLedger


__all__ = [
    "ResearchDecisionLedger",
    "ResearchLedger",
    "validate_research_report",
]
