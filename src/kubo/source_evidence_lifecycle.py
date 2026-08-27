from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from .hashing import canonical_json_bytes, hash_json
from .strict import https_url, parse_aware, require_sha256


INPUT_SCHEMA_VERSION = "source-evidence-lifecycle-v1"
REPORT_SCHEMA_VERSION = "source-evidence-reconciliation-report-v1"
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_RECORDS_PER_SECTION = 100_000
MAX_TEXT_CHARS = 65_536
MAX_QUARANTINE_IDENTIFIER_CHARS = 256

CAPTURE_MODES = frozenset({"PROSPECTIVE", "HISTORICAL_POINT_IN_TIME"})
EVIDENCE_CLASSES = frozenset(
    {"SYNTHETIC_FIXTURE", "RECORDED_AUTHORIZED_FIXTURE", "PROVEN_REAL_EVIDENCE"}
)
ACCESS_MODES = frozenset(
    {
        "OFFICIAL_API",
        "OFFICIAL_DOWNLOAD",
        "PUBLIC_WEB",
        "USER_AUTHORIZED_EXPORT",
        "RECORDED_FIXTURE",
    }
)
ATTEMPT_OUTCOMES = frozenset(
    {
        "COLLECTED",
        "EMPTY",
        "BLOCKED_ACCESS",
        "ROBOTS_DENIED",
        "PAYWALL",
        "RATE_LIMITED",
        "NETWORK_ERROR",
        "PARSER_DRIFT",
        "SKIPPED_DISABLED",
    }
)
CONTENT_CLASSES = frozenset(
    {
        "DATA",
        "EMPTY",
        "ACCESS_DENIED",
        "CHALLENGE",
        "PAYWALL",
        "ERROR_PAGE",
        "NOT_FETCHED",
    }
)
RIGHTS_STATUSES = frozenset({"PERMITTED", "USER_AUTHORIZED", "UNKNOWN", "FORBIDDEN"})
ROBOTS_STATUSES = frozenset({"ALLOWED", "DISALLOWED", "NOT_APPLICABLE", "UNKNOWN"})
SOURCE_GRADES = {"A": 0, "B": 1, "C": 2, "D": 3}
VERIFICATION_STATUSES = frozenset({"CONFIRMED", "UNVERIFIED", "INFERRED", "REJECTED"})
EVIDENCE_ROLES = frozenset(
    {
        "EXCHANGE_OFFICIAL",
        "REGULATOR_OFFICIAL",
        "CLEARING_OFFICIAL",
        "ISSUER_PRIMARY",
        "FINANCIAL_CONTEXT",
        "NEWS_CONTEXT",
        "SOCIAL_CONTEXT_LEAD_ONLY",
        "ROUTING_ONLY",
    }
)
PRIMARY_FACT_ROLES = frozenset(
    {
        "EXCHANGE_OFFICIAL",
        "REGULATOR_OFFICIAL",
        "CLEARING_OFFICIAL",
        "ISSUER_PRIMARY",
    }
)
AVAILABILITY_EVIDENCE_STATUSES = frozenset(
    {"CAPTURED_BEFORE_CUTOFF", "VERIFIED_ARCHIVE", "UNVERIFIED"}
)
ZERO_YIELD_OUTCOMES = frozenset(
    {
        "EMPTY",
        "BLOCKED_ACCESS",
        "ROBOTS_DENIED",
        "PAYWALL",
        "RATE_LIMITED",
        "NETWORK_ERROR",
        "PARSER_DRIFT",
    }
)

ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "evidence_class",
        "capture_mode",
        "decision_at",
        "max_zero_yield_attempts_per_family",
        "critical_fields",
        "expected_cells",
        "attempts",
        "observations",
    }
)
ATTEMPT_FIELDS = frozenset(
    {
        "attempt_id",
        "source_id",
        "publisher",
        "source_family",
        "source_url",
        "access_mode",
        "started_at",
        "finished_at",
        "http_status",
        "outcome",
        "content_class",
        "qualified_rows",
        "byte_count",
        "raw_sha256",
        "parser_version",
        "schema_fingerprint",
        "expected_schema_fingerprint",
        "rights_status",
        "robots_status",
    }
)
OBSERVATION_FIELDS = frozenset(
    {
        "observation_id",
        "attempt_id",
        "artifact_id",
        "source_id",
        "publisher",
        "source_family",
        "origin_id",
        "source_record_id",
        "entity_id",
        "field_name",
        "value",
        "unit",
        "effective_at",
        "published_at",
        "available_at",
        "retrieved_at",
        "availability_evidence_status",
        "revision",
        "source_grade",
        "verification_status",
        "evidence_role",
        "source_url",
        "raw_sha256",
        "parser_version",
    }
)
QUARANTINE_IDENTIFIER_FIELDS = (
    "attempt_id",
    "observation_id",
    "source_id",
    "source_family",
    "origin_id",
    "source_record_id",
    "entity_id",
    "field_name",
    "outcome",
    "content_class",
)


class SourceEvidenceLifecycleError(ValueError):
    """Raised when the frozen reconciliation contract itself is invalid."""


def _reject_non_json_constant(value: str) -> None:
    raise SourceEvidenceLifecycleError(f"non-JSON numeric constant is forbidden: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SourceEvidenceLifecycleError("duplicate JSON key is forbidden")
        result[key] = value
    return result


def load_source_evidence_document(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise SourceEvidenceLifecycleError("input must be a regular non-symlink file")
    try:
        if source.stat().st_size > MAX_INPUT_BYTES:
            raise SourceEvidenceLifecycleError("input exceeds the 16 MiB budget")
        payload = source.read_bytes()
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_non_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise SourceEvidenceLifecycleError("input must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise SourceEvidenceLifecycleError("input must be strict JSON") from exc
    if not isinstance(document, dict):
        raise SourceEvidenceLifecycleError("input root must be an object")
    return document


def _exact_fields(value: Any, expected: frozenset[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SourceEvidenceLifecycleError(f"{field} must be an object")
    actual = set(value)
    if actual != expected:
        raise SourceEvidenceLifecycleError(
            f"{field} fields differ from contract: "
            f"missing_count={len(expected - actual)} extra_count={len(actual - expected)}"
        )
    return dict(value)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise SourceEvidenceLifecycleError(f"{field} must be a string")
    if value != value.strip() or not value or "\x00" in value or len(value) > MAX_TEXT_CHARS:
        raise SourceEvidenceLifecycleError(f"{field} must be a bounded trimmed non-empty string")
    return value


def _enum(value: Any, allowed: Iterable[str], field: str) -> str:
    text = _text(value, field)
    if text not in allowed:
        raise SourceEvidenceLifecycleError(f"{field} has an unsupported value")
    return text


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SourceEvidenceLifecycleError(f"{field} must be an integer >= {minimum}")
    return value


def _optional_hash(value: Any, field: str) -> str | None:
    if value is None:
        return None
    try:
        return require_sha256(value, field)
    except ValueError as exc:
        raise SourceEvidenceLifecycleError(str(exc)) from exc


def _timestamp(value: Any, field: str) -> datetime:
    try:
        return parse_aware(value, field)
    except ValueError as exc:
        raise SourceEvidenceLifecycleError(str(exc)) from exc


def _url(value: Any, field: str) -> str:
    try:
        return https_url(value, field)
    except ValueError as exc:
        raise SourceEvidenceLifecycleError(str(exc)) from exc


def _finite_scalar(value: Any, field: str) -> str | int | float:
    if isinstance(value, bool) or value is None:
        raise SourceEvidenceLifecycleError(f"{field} must be a finite scalar")
    if isinstance(value, str):
        return _text(value, field)
    if type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise SourceEvidenceLifecycleError(f"{field} must be a string, integer, or finite number")


def _normalized_value(value: str | int | float, unit: str) -> str:
    return canonical_json_bytes({"unit": unit, "value": value}).decode("utf-8")


def _public_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _quarantine_row_reference(row: Any) -> dict[str, Any]:
    """Return a bounded reference without reflecting rejected source material."""

    if not isinstance(row, Mapping):
        return {"record_sha256": None, "identifiers": {}}
    public = _public_row(row)
    identifiers: dict[str, str] = {}
    for field in QUARANTINE_IDENTIFIER_FIELDS:
        value = public.get(field)
        if (
            isinstance(value, str)
            and value == value.strip()
            and value
            and "\x00" not in value
            and len(value) <= MAX_QUARANTINE_IDENTIFIER_CHARS
        ):
            identifiers[field] = value
    try:
        record_sha256: str | None = hash_json(public)
    except (TypeError, ValueError):
        record_sha256 = None
    return {"record_sha256": record_sha256, "identifiers": identifiers}


def _quarantine(
    target: list[dict[str, Any]],
    row: Any,
    reason_code: str,
    detail: str,
) -> None:
    target.append(
        {
            "reason_code": reason_code,
            "detail": detail,
            "row": _quarantine_row_reference(row),
        }
    )


def validate_source_attempt(value: Any) -> dict[str, Any]:
    attempt = _exact_fields(value, ATTEMPT_FIELDS, "attempt")
    for field in ("attempt_id", "source_id", "publisher", "source_family", "parser_version"):
        attempt[field] = _text(attempt[field], f"attempt.{field}")
    attempt["source_url"] = _url(attempt["source_url"], "attempt.source_url")
    attempt["access_mode"] = _enum(attempt["access_mode"], ACCESS_MODES, "attempt.access_mode")
    attempt["outcome"] = _enum(attempt["outcome"], ATTEMPT_OUTCOMES, "attempt.outcome")
    attempt["content_class"] = _enum(
        attempt["content_class"], CONTENT_CLASSES, "attempt.content_class"
    )
    attempt["rights_status"] = _enum(
        attempt["rights_status"], RIGHTS_STATUSES, "attempt.rights_status"
    )
    attempt["robots_status"] = _enum(
        attempt["robots_status"], ROBOTS_STATUSES, "attempt.robots_status"
    )
    started = _timestamp(attempt["started_at"], "attempt.started_at")
    finished = _timestamp(attempt["finished_at"], "attempt.finished_at")
    if finished < started:
        raise SourceEvidenceLifecycleError("attempt.finished_at precedes started_at")
    attempt["started_at"] = started.isoformat()
    attempt["finished_at"] = finished.isoformat()
    attempt["_started"] = started
    attempt["_finished"] = finished

    http_status = attempt["http_status"]
    if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
        raise SourceEvidenceLifecycleError("attempt.http_status must be null or 100..599")
    if attempt["access_mode"] in {"OFFICIAL_API", "OFFICIAL_DOWNLOAD", "PUBLIC_WEB"} and http_status is None:
        raise SourceEvidenceLifecycleError("network access modes require an HTTP status")
    attempt["qualified_rows"] = _integer(
        attempt["qualified_rows"], "attempt.qualified_rows"
    )
    attempt["byte_count"] = _integer(attempt["byte_count"], "attempt.byte_count")
    attempt["raw_sha256"] = _optional_hash(attempt["raw_sha256"], "attempt.raw_sha256")
    attempt["schema_fingerprint"] = _optional_hash(
        attempt["schema_fingerprint"], "attempt.schema_fingerprint"
    )
    attempt["expected_schema_fingerprint"] = _optional_hash(
        attempt["expected_schema_fingerprint"], "attempt.expected_schema_fingerprint"
    )

    outcome = attempt["outcome"]
    content_class = attempt["content_class"]
    allowed_content_by_outcome = {
        "COLLECTED": {"DATA"},
        "EMPTY": {"EMPTY"},
        "BLOCKED_ACCESS": {"ACCESS_DENIED", "CHALLENGE", "ERROR_PAGE"},
        "ROBOTS_DENIED": {"NOT_FETCHED"},
        "PAYWALL": {"PAYWALL"},
        "RATE_LIMITED": {"ERROR_PAGE", "NOT_FETCHED"},
        "NETWORK_ERROR": {"NOT_FETCHED"},
        "PARSER_DRIFT": {"DATA"},
        "SKIPPED_DISABLED": {"NOT_FETCHED"},
    }
    if content_class not in allowed_content_by_outcome[outcome]:
        raise SourceEvidenceLifecycleError(
            f"{outcome} cannot use content_class {content_class}"
        )
    if http_status in {401, 403} and outcome != "BLOCKED_ACCESS":
        raise SourceEvidenceLifecycleError("HTTP 401/403 must remain BLOCKED_ACCESS")
    if http_status == 429 and outcome != "RATE_LIMITED":
        raise SourceEvidenceLifecycleError("HTTP 429 must remain RATE_LIMITED")
    if attempt["rights_status"] == "FORBIDDEN" and outcome == "COLLECTED":
        raise SourceEvidenceLifecycleError("FORBIDDEN rights cannot produce collected evidence")
    if attempt["robots_status"] == "DISALLOWED" and outcome == "COLLECTED":
        raise SourceEvidenceLifecycleError("robots DISALLOWED cannot produce collected evidence")
    if outcome == "ROBOTS_DENIED" and attempt["robots_status"] != "DISALLOWED":
        raise SourceEvidenceLifecycleError("ROBOTS_DENIED requires robots_status DISALLOWED")

    if outcome == "COLLECTED":
        if content_class != "DATA" or attempt["qualified_rows"] < 1:
            raise SourceEvidenceLifecycleError("COLLECTED requires DATA and qualified rows")
        if attempt["byte_count"] < 1 or attempt["raw_sha256"] is None:
            raise SourceEvidenceLifecycleError("COLLECTED requires frozen non-empty bytes")
        if attempt["rights_status"] not in {"PERMITTED", "USER_AUTHORIZED"}:
            raise SourceEvidenceLifecycleError("COLLECTED requires explicit permitted rights")
        if attempt["robots_status"] not in {"ALLOWED", "NOT_APPLICABLE"}:
            raise SourceEvidenceLifecycleError("COLLECTED requires an allowed robots disposition")
        if http_status is not None and not 200 <= http_status <= 299:
            raise SourceEvidenceLifecycleError("COLLECTED HTTP evidence requires a 2xx status")
        observed = attempt["schema_fingerprint"]
        expected = attempt["expected_schema_fingerprint"]
        if observed is None or expected is None:
            raise SourceEvidenceLifecycleError("COLLECTED requires both schema fingerprints")
        if observed != expected:
            raise SourceEvidenceLifecycleError("schema drift must stop before normalization")

    if outcome == "PARSER_DRIFT":
        if content_class != "DATA" or attempt["qualified_rows"] != 0:
            raise SourceEvidenceLifecycleError("PARSER_DRIFT requires DATA with zero qualified rows")
        observed = attempt["schema_fingerprint"]
        expected = attempt["expected_schema_fingerprint"]
        if observed is None or expected is None or observed == expected:
            raise SourceEvidenceLifecycleError("PARSER_DRIFT requires distinct schema fingerprints")
        if attempt["byte_count"] < 1 or attempt["raw_sha256"] is None:
            raise SourceEvidenceLifecycleError("PARSER_DRIFT requires quarantined raw bytes")

    if outcome == "EMPTY":
        if content_class != "EMPTY" or attempt["qualified_rows"] != 0:
            raise SourceEvidenceLifecycleError("EMPTY requires EMPTY content and zero rows")

    no_evidence_bytes = {
        "BLOCKED_ACCESS",
        "ROBOTS_DENIED",
        "PAYWALL",
        "RATE_LIMITED",
        "NETWORK_ERROR",
        "SKIPPED_DISABLED",
    }
    if outcome in no_evidence_bytes and (
        attempt["byte_count"] != 0 or attempt["raw_sha256"] is not None
    ):
        raise SourceEvidenceLifecycleError(
            "blocked, denied, limited, failed, or skipped bytes cannot enter evidence"
        )
    if outcome in ZERO_YIELD_OUTCOMES and attempt["qualified_rows"] != 0:
        raise SourceEvidenceLifecycleError("zero-yield outcomes cannot claim qualified rows")
    return attempt


def validate_source_observation(
    value: Any,
    *,
    capture_mode: str,
    decision_at: datetime,
) -> dict[str, Any]:
    row = _exact_fields(value, OBSERVATION_FIELDS, "observation")
    for field in (
        "observation_id",
        "attempt_id",
        "artifact_id",
        "source_id",
        "publisher",
        "source_family",
        "origin_id",
        "source_record_id",
        "entity_id",
        "field_name",
        "unit",
        "parser_version",
    ):
        row[field] = _text(row[field], f"observation.{field}")
    row["source_url"] = _url(row["source_url"], "observation.source_url")
    row["raw_sha256"] = require_sha256(row["raw_sha256"], "observation.raw_sha256")
    row["value"] = _finite_scalar(row["value"], "observation.value")
    row["revision"] = _integer(row["revision"], "observation.revision", minimum=1)
    row["source_grade"] = _enum(
        row["source_grade"], SOURCE_GRADES, "observation.source_grade"
    )
    row["verification_status"] = _enum(
        row["verification_status"],
        VERIFICATION_STATUSES,
        "observation.verification_status",
    )
    row["evidence_role"] = _enum(
        row["evidence_role"], EVIDENCE_ROLES, "observation.evidence_role"
    )
    row["availability_evidence_status"] = _enum(
        row["availability_evidence_status"],
        AVAILABILITY_EVIDENCE_STATUSES,
        "observation.availability_evidence_status",
    )
    if row["verification_status"] == "REJECTED":
        raise SourceEvidenceLifecycleError("REJECTED observations cannot enter reconciliation")

    effective = _timestamp(row["effective_at"], "observation.effective_at")
    published = _timestamp(row["published_at"], "observation.published_at")
    available = _timestamp(row["available_at"], "observation.available_at")
    retrieved = _timestamp(row["retrieved_at"], "observation.retrieved_at")
    if available < published:
        raise SourceEvidenceLifecycleError("observation.available_at precedes published_at")
    if retrieved < available:
        raise SourceEvidenceLifecycleError("observation.retrieved_at precedes available_at")
    if effective > decision_at or available > decision_at:
        raise SourceEvidenceLifecycleError("observation was not effective and available by decision_at")
    if capture_mode == "PROSPECTIVE":
        if retrieved > decision_at:
            raise SourceEvidenceLifecycleError("prospective observation was retrieved after decision_at")
        if row["availability_evidence_status"] != "CAPTURED_BEFORE_CUTOFF":
            raise SourceEvidenceLifecycleError(
                "prospective observations require CAPTURED_BEFORE_CUTOFF evidence"
            )
    elif retrieved > decision_at and row["availability_evidence_status"] != "VERIFIED_ARCHIVE":
        raise SourceEvidenceLifecycleError(
            "historical late retrieval requires VERIFIED_ARCHIVE availability evidence"
        )
    if row["availability_evidence_status"] == "VERIFIED_ARCHIVE" and (
        row["verification_status"] != "CONFIRMED" or row["source_grade"] not in {"A", "B"}
    ):
        raise SourceEvidenceLifecycleError(
            "VERIFIED_ARCHIVE requires confirmed grade A/B evidence"
        )

    row["effective_at"] = effective.isoformat()
    row["published_at"] = published.isoformat()
    row["available_at"] = available.isoformat()
    row["retrieved_at"] = retrieved.isoformat()
    row["_effective"] = effective
    row["_published"] = published
    row["_available"] = available
    row["_retrieved"] = retrieved
    row["_normalized_value"] = _normalized_value(row["value"], row["unit"])
    return row


def _fact_eligible(row: Mapping[str, Any]) -> bool:
    return (
        row["verification_status"] == "CONFIRMED"
        and row["source_grade"] in {"A", "B"}
        and row["evidence_role"] in PRIMARY_FACT_ROLES
    )


def _winner(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return min(
        rows,
        key=lambda row: (
            SOURCE_GRADES[row["source_grade"]],
            row["verification_status"] != "CONFIRMED",
            row["evidence_role"] not in PRIMARY_FACT_ROLES,
            row["_available"],
            row["observation_id"],
        ),
    )


def _fact_status(row: Mapping[str, Any]) -> str:
    return {
        "CONFIRMED": "confirmed",
        "UNVERIFIED": "unverified",
        "INFERRED": "inferred",
    }[str(row["verification_status"])]


def reconcile_source_evidence(document: Any) -> dict[str, Any]:
    root = _exact_fields(document, ROOT_FIELDS, "root")
    if root["schema_version"] != INPUT_SCHEMA_VERSION:
        raise SourceEvidenceLifecycleError("unsupported input schema_version")
    evidence_class = _enum(root["evidence_class"], EVIDENCE_CLASSES, "evidence_class")
    capture_mode = _enum(root["capture_mode"], CAPTURE_MODES, "capture_mode")
    decision_at = _timestamp(root["decision_at"], "decision_at")
    max_zero = _integer(
        root["max_zero_yield_attempts_per_family"],
        "max_zero_yield_attempts_per_family",
        minimum=1,
    )
    if not isinstance(root["critical_fields"], list) or not root["critical_fields"]:
        raise SourceEvidenceLifecycleError("critical_fields must be a non-empty list")
    critical_fields = [_text(value, "critical_fields[]") for value in root["critical_fields"]]
    if len(set(critical_fields)) != len(critical_fields):
        raise SourceEvidenceLifecycleError("critical_fields contains duplicates")
    critical_set = set(critical_fields)

    if not isinstance(root["expected_cells"], list) or not root["expected_cells"]:
        raise SourceEvidenceLifecycleError("expected_cells must freeze a non-empty denominator")
    if len(root["expected_cells"]) > MAX_RECORDS_PER_SECTION:
        raise SourceEvidenceLifecycleError("expected_cells exceeds the record budget")
    expected: dict[tuple[str, str, str], dict[str, Any]] = {}
    scopes: set[tuple[str, str]] = set()
    for index, raw in enumerate(root["expected_cells"]):
        cell = _exact_fields(
            raw,
            frozenset({"entity_id", "field_name", "effective_at"}),
            f"expected_cells[{index}]",
        )
        entity_id = _text(cell["entity_id"], "expected_cell.entity_id")
        field_name = _text(cell["field_name"], "expected_cell.field_name")
        effective = _timestamp(cell["effective_at"], "expected_cell.effective_at")
        if effective > decision_at:
            raise SourceEvidenceLifecycleError("expected cell effective_at exceeds decision_at")
        normalized = {
            "entity_id": entity_id,
            "field_name": field_name,
            "effective_at": effective.isoformat(),
        }
        key = (entity_id, field_name, effective.isoformat())
        if key in expected:
            raise SourceEvidenceLifecycleError("expected_cells contains a duplicate")
        expected[key] = normalized
        scopes.add((entity_id, effective.isoformat()))
    for entity_id, effective_at in scopes:
        omitted = [
            field
            for field in critical_fields
            if (entity_id, field, effective_at) not in expected
        ]
        if omitted:
            raise SourceEvidenceLifecycleError(
                "expected denominator omits critical fields for "
                f"{entity_id}@{effective_at}: {sorted(omitted)}"
            )

    if not isinstance(root["attempts"], list) or not isinstance(root["observations"], list):
        raise SourceEvidenceLifecycleError("attempts and observations must be lists")
    if len(root["attempts"]) > MAX_RECORDS_PER_SECTION or len(root["observations"]) > MAX_RECORDS_PER_SECTION:
        raise SourceEvidenceLifecycleError("attempts or observations exceeds the record budget")

    quarantined: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    attempts_by_id: dict[str, dict[str, Any]] = {}
    zero_yield_by_family: Counter[str] = Counter()
    for raw in root["attempts"]:
        try:
            attempt = validate_source_attempt(raw)
            if attempt["attempt_id"] in attempts_by_id:
                raise SourceEvidenceLifecycleError("duplicate attempt_id")
            if capture_mode == "PROSPECTIVE" and attempt["_finished"] > decision_at:
                raise SourceEvidenceLifecycleError("prospective attempt finished after decision_at")
        except (SourceEvidenceLifecycleError, ValueError) as exc:
            _quarantine(quarantined, raw, "ATTEMPT_INVALID", str(exc))
            continue
        attempts.append(attempt)
        attempts_by_id[attempt["attempt_id"]] = attempt
        if attempt["outcome"] in ZERO_YIELD_OUTCOMES:
            zero_yield_by_family[attempt["source_family"]] += 1

    eligible_attempts = {
        attempt_id: attempt
        for attempt_id, attempt in attempts_by_id.items()
        if attempt["outcome"] == "COLLECTED"
    }
    seen_observation_ids: set[str] = set()
    revision_groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in root["observations"]:
        try:
            row = validate_source_observation(
                raw,
                capture_mode=capture_mode,
                decision_at=decision_at,
            )
            if row["observation_id"] in seen_observation_ids:
                raise SourceEvidenceLifecycleError("duplicate observation_id")
            attempt = eligible_attempts.get(row["attempt_id"])
            if attempt is None:
                raise SourceEvidenceLifecycleError(
                    "observation lineage does not resolve to a COLLECTED attempt"
                )
            for field in (
                "source_id",
                "publisher",
                "source_family",
                "source_url",
                "raw_sha256",
                "parser_version",
            ):
                if row[field] != attempt[field]:
                    raise SourceEvidenceLifecycleError(
                        f"observation.{field} disagrees with its source attempt"
                    )
            if row["_retrieved"] != attempt["_finished"]:
                raise SourceEvidenceLifecycleError(
                    "observation.retrieved_at must equal attempt.finished_at"
                )
        except (SourceEvidenceLifecycleError, ValueError) as exc:
            message = str(exc)
            code = "POST_CUTOFF" if "decision_at" in message else "OBSERVATION_INVALID"
            _quarantine(quarantined, raw, code, message)
            continue
        seen_observation_ids.add(row["observation_id"])
        revision_groups[
            (
                row["origin_id"],
                row["source_record_id"],
                row["entity_id"],
                row["field_name"],
                row["effective_at"],
            )
        ].append(row)

    records_per_attempt: dict[str, set[str]] = defaultdict(set)
    for rows in revision_groups.values():
        for row in rows:
            records_per_attempt[row["attempt_id"]].add(row["source_record_id"])
    for attempt_id, record_ids in records_per_attempt.items():
        if len(record_ids) > eligible_attempts[attempt_id]["qualified_rows"]:
            raise SourceEvidenceLifecycleError(
                "distinct parsed source records exceed attempt.qualified_rows"
            )

    latest_rows: list[dict[str, Any]] = []
    for rows in revision_groups.values():
        ordered = sorted(rows, key=lambda row: row["revision"])
        reasons: list[tuple[dict[str, Any], str, str]] = []
        if ordered[0]["revision"] != 1:
            reasons.append(
                (
                    ordered[0],
                    "REVISION_START_INVALID",
                    "an append-only revision chain must begin at one",
                )
            )
        seen_revisions: set[int] = set()
        previous: dict[str, Any] | None = None
        for row in ordered:
            if row["revision"] in seen_revisions:
                reasons.append((row, "REVISION_COLLISION", "duplicate revision number"))
            seen_revisions.add(row["revision"])
            if previous is not None:
                if row["revision"] != previous["revision"] + 1:
                    reasons.append((row, "REVISION_GAP", "revisions must be consecutive"))
                if (
                    row["_published"] < previous["_published"]
                    or row["_available"] < previous["_available"]
                    or row["_retrieved"] <= previous["_retrieved"]
                ):
                    reasons.append(
                        (
                            row,
                            "REVISION_TIME_REGRESSION",
                            "later revisions cannot move publication, availability, or retrieval backward",
                        )
                    )
            previous = row
        if reasons:
            for row, code, detail in reasons:
                _quarantine(quarantined, row, code, detail)
            continue
        latest_rows.append(ordered[-1])

    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in latest_rows:
        key = (row["entity_id"], row["field_name"], row["effective_at"])
        if key not in expected:
            _quarantine(
                quarantined,
                row,
                "OUTSIDE_EXPECTED_DENOMINATOR",
                "observation is outside the frozen expected-cell denominator",
            )
            continue
        cells[key].append(row)

    accepted: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    resolved: set[tuple[str, str, str]] = set()
    exact_duplicate_count = 0
    same_value_distinct_origin_support = 0
    for key, rows in sorted(cells.items()):
        by_value: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_value[row["_normalized_value"]].append(row)
        for value_rows in by_value.values():
            duplicate_keys = Counter(
                (row["origin_id"], row["raw_sha256"]) for row in value_rows
            )
            exact_duplicate_count += sum(max(0, count - 1) for count in duplicate_keys.values())
            verified_origins = {row["origin_id"] for row in value_rows if _fact_eligible(row)}
            same_value_distinct_origin_support += max(0, len(verified_origins) - 1)

        field_is_critical = key[1] in critical_set
        if len(by_value) == 1:
            candidates = next(iter(by_value.values()))
            eligible = [row for row in candidates if _fact_eligible(row)]
            if field_is_critical and not eligible:
                for row in candidates:
                    _quarantine(
                        quarantined,
                        row,
                        "CRITICAL_FIELD_EVIDENCE_INELIGIBLE",
                        "critical fields require confirmed grade A/B primary evidence",
                    )
                continue
            selection = eligible or candidates
            winner = _winner(selection)
            support = sorted(
                row["observation_id"] for row in candidates if _fact_eligible(row)
            )
            accepted.append(
                {
                    **_public_row(winner),
                    "fact_status": _fact_status(winner),
                    "supporting_observation_ids": support,
                    "independent_origin_count": len(
                        {row["origin_id"] for row in candidates}
                    ),
                    "resolution": "AGREED_OR_SINGLE_VALUE",
                }
            )
            resolved.add(key)
            continue

        authoritative_values = {
            normalized
            for normalized, candidates in by_value.items()
            if any(
                row["source_grade"] == "A"
                and row["verification_status"] == "CONFIRMED"
                and row["evidence_role"] in PRIMARY_FACT_ROLES
                for row in candidates
            )
        }
        base_conflict = {
            "cell": expected[key],
            "candidate_observation_ids": sorted(row["observation_id"] for row in rows),
            "independent_origin_count": len({row["origin_id"] for row in rows}),
        }
        if len(authoritative_values) == 1:
            selected_value = next(iter(authoritative_values))
            candidates = [
                row
                for row in by_value[selected_value]
                if row["source_grade"] == "A"
                and row["verification_status"] == "CONFIRMED"
                and row["evidence_role"] in PRIMARY_FACT_ROLES
            ]
            winner = _winner(candidates)
            accepted.append(
                {
                    **_public_row(winner),
                    "fact_status": "confirmed",
                    "supporting_observation_ids": sorted(
                        row["observation_id"] for row in candidates
                    ),
                    "independent_origin_count": len(
                        {row["origin_id"] for row in candidates}
                    ),
                    "resolution": "UNIQUE_AUTHORITATIVE_VALUE",
                }
            )
            conflicts.append(
                {
                    **base_conflict,
                    "status": "RESOLVED_BY_UNIQUE_AUTHORITATIVE_VALUE",
                    "selected_observation_id": winner["observation_id"],
                }
            )
            resolved.add(key)
        else:
            conflicts.append(
                {
                    **base_conflict,
                    "status": "UNRESOLVED_CONFLICT",
                    "selected_observation_id": None,
                }
            )
            for row in rows:
                _quarantine(
                    quarantined,
                    row,
                    "UNRESOLVED_CONFLICT",
                    "conflicting values cannot be averaged or resolved by copy count",
                )

    missing: list[dict[str, Any]] = []
    for key in sorted(set(expected) - resolved):
        missing.append(
            {
                **expected[key],
                "fact_status": "missing",
                "critical": key[1] in critical_set,
                "reason_code": "NO_ADMISSIBLE_RECONCILED_VALUE",
            }
        )
    missing_critical = [item for item in missing if item["critical"]]
    unresolved_conflicts = [
        conflict for conflict in conflicts if conflict["status"] == "UNRESOLVED_CONFLICT"
    ]
    stop_families = sorted(
        family for family, count in zero_yield_by_family.items() if count >= max_zero
    )
    outcome_counts = Counter(attempt["outcome"] for attempt in attempts)
    source_failure_count = sum(
        count
        for outcome, count in outcome_counts.items()
        if outcome not in {"COLLECTED", "EMPTY"}
    )
    if missing_critical:
        status = "BLOCKED"
    elif (
        missing
        or quarantined
        or unresolved_conflicts
        or source_failure_count
        or stop_families
    ):
        status = "DEGRADED_STRUCTURE_VALID_ONLY"
    else:
        status = "STRUCTURE_AND_RECONCILIATION_VALID_ONLY"

    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": status,
        "evidence_class": evidence_class,
        "capture_mode": capture_mode,
        "decision_at": decision_at.isoformat(),
        "attempt_summary": {
            "submitted_attempts": len(root["attempts"]),
            "valid_attempts": len(attempts),
            "successful_attempts": outcome_counts.get("COLLECTED", 0),
            "outcome_counts": dict(sorted(outcome_counts.items())),
            "source_failure_count": source_failure_count,
            "zero_yield_by_family": dict(sorted(zero_yield_by_family.items())),
            "stop_source_families": stop_families,
        },
        "quality": {
            "expected_cell_count": len(expected),
            "resolved_expected_cell_count": len(resolved),
            "data_coverage_score": len(resolved) / len(expected),
            "accepted_cell_count": len(accepted),
            "missing_cell_count": len(missing),
            "missing_critical_cell_count": len(missing_critical),
            "unresolved_conflict_count": len(unresolved_conflicts),
            "exact_duplicate_observation_count": exact_duplicate_count,
            "same_value_distinct_confirmed_origin_support_count": same_value_distinct_origin_support,
            "quarantine_count": len(quarantined),
        },
        "accepted": sorted(
            accepted,
            key=lambda row: (row["entity_id"], row["field_name"], row["effective_at"]),
        ),
        "conflicts": conflicts,
        "missing_expected_cells": missing,
        "quarantine": quarantined,
        "claim_boundaries": {
            "source_rights_proven_by_reconciliation": False,
            "semantic_truth_proven": False,
            "complete_market_coverage_proven": False,
            "model_fitting_permitted": False,
            "backtest_permitted": False,
            "recommendation_permitted": False,
            "financial_execution_permitted": False,
        },
        "limitations": [
            "reconciliation validates structure and point-in-time lineage, not source licensing or semantic truth",
            "blocked, paywalled, robots-disallowed, and failed sources remain explicit failures",
            "social and routing evidence cannot satisfy critical facts",
            "missing values remain missing and are never synthesized",
            "the report cannot authorize model fitting, backtesting, recommendations, or trades",
        ],
    }
    report["report_sha256"] = hash_json(report)
    return report


def reconcile_source_evidence_file(path: Path | str) -> dict[str, Any]:
    return reconcile_source_evidence(load_source_evidence_document(path))


def write_reconciliation_report(path: Path | str, report: Mapping[str, Any]) -> Path:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise FileExistsError("refusing to overwrite an existing reconciliation report")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise SourceEvidenceLifecycleError("output parent must be a real directory")
    payload = canonical_json_bytes(dict(report))
    with target.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return target


__all__ = [
    "INPUT_SCHEMA_VERSION",
    "REPORT_SCHEMA_VERSION",
    "SourceEvidenceLifecycleError",
    "load_source_evidence_document",
    "reconcile_source_evidence",
    "reconcile_source_evidence_file",
    "validate_source_attempt",
    "validate_source_observation",
    "write_reconciliation_report",
]
