from __future__ import annotations

import csv
import json
import os
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .atomic_output import run_atomic_output
from .hashing import canonical_json_bytes, sha256_bytes
from .status_history import build_status_intervals, parse_status_notice
from .status_history_workspace import STATUS_HISTORY_MANIFEST_SCHEMA_VERSION
from .strict import parse_aware, parse_iso_date, require_sha256
from .tri_security_admission import (
    BoundaryAdmissionRequest,
    admit_boundary,
    build_boundary_operation_binding,
)


MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
_ALLOWED_UPSTREAM_STATUSES = frozenset(
    {
        "CURRENT_STATUS_AND_CA_SCHEDULE_READY",
        "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY",
    }
)
_ALLOWED_OFFICIAL_HOSTS = frozenset(
    {
        "boursakuwait.com.kw",
        "www.boursakuwait.com.kw",
        "ifsah.boursakuwait.com.kw",
        "cma.gov.kw",
        "www.cma.gov.kw",
    }
)
_TEXT_DERIVATIONS = frozenset(
    {
        "OFFICIAL_HTML_VISIBLE_TEXT",
        "REVIEWED_PDF_TEXT_EXPORT",
        "OFFICIAL_XBRL_VISIBLE_TEXT",
    }
)
STATUS_NOTICE_HEADERS = (
    "notice_id",
    "security_code",
    "ticker",
    "event_type",
    "effective_date",
    "published_date",
    "source_id",
    "source_url",
    "raw_sha256",
    "text_sha256",
    "query_id",
    "classification_phrase",
)
STATUS_INTERVAL_HEADERS = (
    "security_code",
    "ticker",
    "status",
    "effective_from",
    "effective_to",
    "opening_evidence_sha256",
    "start_notice_id",
    "end_notice_id",
    "evidence_hashes",
)
STATUS_QUERY_HEADERS = (
    "query_id",
    "security_code",
    "ticker",
    "window_from",
    "window_to",
    "pages_declared",
    "pages_received",
    "result_count_declared",
    "rows_normalized",
    "zero_result",
    "raw_sha256",
    "source_url",
)
OPENING_STATE_HEADERS = (
    "security_code",
    "ticker",
    "status",
    "effective_date",
    "source_id",
    "source_url",
    "raw_sha256",
    "evidence_excerpt",
)


def _safe_regular_file(path: Path, *, field: str, max_bytes: int) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            metadata = os.lstat(current)
        except OSError as exc:
            raise ValueError(f"{field} is missing or unreadable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{field} must not contain symlinks")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise ValueError(f"{field} cannot be opened safely") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"{field} must be a regular file")
        if before.st_size > max_bytes:
            raise ValueError(f"{field} exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"{field} exceeds {max_bytes} bytes")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError(f"{field} changed while being read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _strict_json_object(content: bytes, field: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{field} contains duplicate key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"{field} contains non-finite JSON: {value}")
            ),
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{field} must be strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return payload


def _read_current_status(content: bytes) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("upstream security status evidence must be UTF-8 CSV") from exc
    reader = csv.DictReader(text.splitlines())
    headers = tuple(reader.fieldnames or ())
    required = {"security_code", "ticker", "status", "effective_from", "temporal_scope"}
    if not required.issubset(headers):
        raise ValueError("upstream security status evidence lacks required columns")
    rows = [
        {key: str(value or "").strip() for key, value in row.items()}
        for row in reader
    ]
    if not rows:
        raise ValueError("upstream security status evidence is empty")
    return rows


def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def _prepare_output_root(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:-1]:
        current /= component
        if current.exists() and current.is_symlink():
            raise ValueError("output_root parent must not contain symlinks")
    if absolute.exists() or absolute.is_symlink():
        if absolute.is_symlink() or not absolute.is_dir():
            raise ValueError("output_root must be a real directory")
        if any(absolute.iterdir()):
            raise ValueError("output_root must be empty to preserve prior evidence")
    else:
        absolute.mkdir(parents=True, exist_ok=False)
    return absolute


def _official_url(value: Any, field: str) -> str:
    url = str(value or "")
    parsed = urlsplit(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError(f"{field} contains unsafe URL components")
    if (parsed.hostname or "").casefold() not in _ALLOWED_OFFICIAL_HOSTS:
        raise ValueError(f"{field} must use a supported official domain")
    return url


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().replace("\xa0", " ").split())


def _phrase_present(text: str, phrase: str) -> bool:
    normalized_phrase = _normalized_text(phrase)
    return bool(normalized_phrase) and normalized_phrase in _normalized_text(text)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise ValueError(f"{field} must be a positive integer")
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise ValueError(f"{field} must be a non-negative integer")
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative")
    return parsed


def _load_upstream(status_corporate_root: Path) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, str]]:
    root = Path(status_corporate_root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("status_corporate_root must be a real directory")
    report_bytes = _safe_regular_file(
        root / "reports" / "status_corporate_import_report.json",
        field="upstream status/corporate report",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    report = _strict_json_object(report_bytes, "upstream status/corporate report")
    if report.get("status") not in _ALLOWED_UPSTREAM_STATUSES:
        raise ValueError("upstream status/corporate stage is not ready")
    status_bytes = _safe_regular_file(
        root / "normalized" / "security_status_evidence.csv",
        field="upstream security_status_evidence.csv",
        max_bytes=MAX_ARTIFACT_BYTES,
    )
    rows = _read_current_status(status_bytes)
    hashes = {
        "report_sha256": sha256_bytes(report_bytes),
        "status_evidence_sha256": sha256_bytes(status_bytes),
    }
    return report, rows, hashes


def _copy_artifact(
    source: Path,
    destination: Path,
    *,
    expected_hash: str,
    field: str,
) -> bytes:
    content = _safe_regular_file(source, field=field, max_bytes=MAX_ARTIFACT_BYTES)
    actual = sha256_bytes(content)
    if actual != require_sha256(expected_hash, f"{field}.sha256"):
        raise ValueError(f"{field} hash mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return content


def import_status_history(
    *,
    status_corporate_root: Path,
    workspace: Path,
    output_root: Path,
    admission_request: BoundaryAdmissionRequest,
) -> dict[str, Any]:
    requested_output = Path(os.path.abspath(output_root))
    operation_binding = build_boundary_operation_binding(
        "import_status_history",
        decision_at=admission_request.decision_at,
    )
    token = admit_boundary(
        admission_request,
        boundary_id="import_status_history",
        output_root=requested_output,
        boundary_inputs={
            "status_corporate_root": Path(status_corporate_root),
            "workspace": Path(workspace),
        },
        operation_binding=operation_binding,
    )

    def worker(staging: Path) -> dict[str, Any]:
        report = _import_status_history_unchecked(
            status_corporate_root=status_corporate_root,
            workspace=workspace,
            output_root=staging,
            logical_output_root=requested_output,
        )
        token.materialize_receipt(staging)
        token.materialize_lineage(staging)
        return report

    return run_atomic_output(
        requested_output,
        worker,
        before_commit=lambda _staging: token.revalidate_before_commit(),
    )


def _import_status_history_unchecked(
    *,
    status_corporate_root: Path,
    workspace: Path,
    output_root: Path,
    logical_output_root: Path | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("workspace must be a real directory")
    upstream_report, current_rows, upstream_hashes = _load_upstream(
        status_corporate_root
    )
    manifest_bytes = _safe_regular_file(
        workspace / "manifests" / "status_history_manifest.json",
        field="status history manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    manifest = _strict_json_object(manifest_bytes, "status history manifest")
    expected_top = {
        "schema_version",
        "run_id",
        "history_window_from",
        "history_window_to",
        "upstream",
        "queries",
        "opening_states",
        "notices",
    }
    if set(manifest) != expected_top:
        raise ValueError("status history manifest has unknown or missing fields")
    if manifest["schema_version"] != STATUS_HISTORY_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported status history manifest schema_version")
    window_from = parse_iso_date(manifest["history_window_from"], "history_window_from")
    window_to = parse_iso_date(manifest["history_window_to"], "history_window_to")
    if window_from > window_to:
        raise ValueError("status history window is reversed")
    upstream = manifest["upstream"]
    expected_upstream = {
        "status": upstream_report["status"],
        "run_id": upstream_report.get("run_id"),
        "status_snapshot_effective_date": upstream_report[
            "status_snapshot_effective_date"
        ],
        **upstream_hashes,
    }
    if upstream != expected_upstream:
        raise ValueError("status history upstream receipt is stale")
    if window_to != parse_iso_date(
        upstream_report["status_snapshot_effective_date"],
        "status_snapshot_effective_date",
    ):
        raise ValueError("history_window_to differs from current snapshot date")

    expected_identity: dict[str, str] = {}
    current_states: dict[str, str] = {}
    for row in current_rows:
        code = row["security_code"]
        ticker = row["ticker"].upper()
        if code in expected_identity:
            raise ValueError("duplicate upstream current security_code")
        expected_identity[code] = ticker
        current_states[code] = row["status"]

    output = _prepare_output_root(Path(output_root))
    raw_output = output / "raw"
    text_output = output / "text"
    normalized_output = output / "normalized"
    report_output = output / "reports"
    manifest_output = output / "manifests"
    for directory in (
        raw_output,
        text_output,
        normalized_output,
        report_output,
        manifest_output,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    queries = manifest["queries"]
    openings = manifest["opening_states"]
    notices = manifest["notices"]
    if not isinstance(queries, list) or not isinstance(openings, list) or not isinstance(notices, list):
        raise ValueError("status history queries, opening_states, and notices must be lists")
    if len(queries) != len(expected_identity) or len(openings) != len(expected_identity):
        raise ValueError("status history denominator differs from current pilot identity")

    artifacts: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    query_by_id: dict[str, dict[str, Any]] = {}
    query_errors: list[str] = []
    query_expected_fields = {
        "query_id",
        "security_code",
        "ticker",
        "source_url",
        "raw_file_name",
        "raw_sha256",
        "pages_declared",
        "pages_received",
        "result_count_declared",
        "rows_normalized",
        "zero_result",
        "observed_at",
        "captured_by",
        "review_status",
        "review_notes",
    }
    for index, query in enumerate(queries):
        try:
            if not isinstance(query, dict) or set(query) != query_expected_fields:
                raise ValueError("query has unknown or missing fields")
            query_id = str(query["query_id"])
            code = str(query["security_code"])
            ticker = str(query["ticker"]).upper()
            if query_id in query_by_id or expected_identity.get(code) != ticker:
                raise ValueError("query identity is invalid or duplicate")
            if query["review_status"] != "ACCEPTED":
                raise ValueError("query must be accepted")
            source_url = _official_url(query["source_url"], "query.source_url")
            pages_declared = _positive_int(query["pages_declared"], "pages_declared")
            pages_received = _positive_int(query["pages_received"], "pages_received")
            result_count = _nonnegative_int(
                query["result_count_declared"],
                "result_count_declared",
            )
            rows_normalized = _nonnegative_int(
                query["rows_normalized"],
                "rows_normalized",
            )
            if pages_declared != pages_received:
                raise ValueError("query pagination is incomplete")
            if type(query["zero_result"]) is not bool:
                raise ValueError("query zero_result must be a JSON boolean")
            if query["zero_result"] != (result_count == 0 and rows_normalized == 0):
                raise ValueError("query zero_result does not match counts")
            observed = parse_aware(query["observed_at"], "query.observed_at")
            if not str(query["captured_by"]).strip():
                raise ValueError("query captured_by is required")
            raw_name = Path(str(query["raw_file_name"]))
            if raw_name.is_absolute() or ".." in raw_name.parts or len(raw_name.parts) != 1:
                raise ValueError("query raw_file_name must be one safe component")
            content = _copy_artifact(
                workspace / "raw_exports" / "queries" / raw_name,
                raw_output / "queries" / raw_name,
                expected_hash=query["raw_sha256"],
                field=f"status query artifact {query_id}",
            )
            digest = require_sha256(query["raw_sha256"], "query.raw_sha256")
            query_by_id[query_id] = query
            query_rows.append(
                {
                    "query_id": query_id,
                    "security_code": code,
                    "ticker": ticker,
                    "window_from": window_from.isoformat(),
                    "window_to": window_to.isoformat(),
                    "pages_declared": pages_declared,
                    "pages_received": pages_received,
                    "result_count_declared": result_count,
                    "rows_normalized": rows_normalized,
                    "zero_result": "true" if query["zero_result"] else "false",
                    "raw_sha256": digest,
                    "source_url": source_url,
                }
            )
            artifacts.append(
                {
                    "path": (Path("raw") / "queries" / raw_name).as_posix(),
                    "sha256": digest,
                    "size_bytes": len(content),
                    "source_id": "boursa_historical_disclosures",
                    "source_url": source_url,
                    "observed_at": observed.isoformat(),
                    "capture_kind": "USER_EXPORT",
                    "artifact_role": "STATUS_HISTORY_QUERY_RECEIPT",
                }
            )
        except (OSError, TypeError, ValueError) as exc:
            query_errors.append(f"query_{index}:{exc}")

    opening_rows: list[dict[str, Any]] = []
    opening_by_code: dict[str, dict[str, Any]] = {}
    opening_errors: list[str] = []
    opening_expected_fields = {
        "security_code",
        "ticker",
        "status",
        "effective_date",
        "source_id",
        "source_url",
        "raw_file_name",
        "raw_sha256",
        "evidence_excerpt",
        "observed_at",
        "captured_by",
        "review_status",
        "review_notes",
    }
    for index, opening in enumerate(openings):
        try:
            if not isinstance(opening, dict) or set(opening) != opening_expected_fields:
                raise ValueError("opening state has unknown or missing fields")
            code = str(opening["security_code"])
            ticker = str(opening["ticker"]).upper()
            status = str(opening["status"]).upper()
            if code in opening_by_code or expected_identity.get(code) != ticker:
                raise ValueError("opening state identity is invalid or duplicate")
            if status not in {"TRADING", "SUSPENDED", "DELISTED"}:
                raise ValueError("opening status is invalid")
            if parse_iso_date(opening["effective_date"], "opening.effective_date") != window_from:
                raise ValueError("opening state effective_date must equal history_window_from")
            if opening["source_id"] not in {"boursa_historical_disclosures", "cma_announcement"}:
                raise ValueError("opening state source_id is unsupported")
            source_url = _official_url(opening["source_url"], "opening.source_url")
            if opening["review_status"] != "ACCEPTED":
                raise ValueError("opening state must be accepted")
            observed = parse_aware(opening["observed_at"], "opening.observed_at")
            if not str(opening["captured_by"]).strip():
                raise ValueError("opening captured_by is required")
            raw_name = Path(str(opening["raw_file_name"]))
            if raw_name.is_absolute() or ".." in raw_name.parts or len(raw_name.parts) != 1:
                raise ValueError("opening raw_file_name must be one safe component")
            content = _copy_artifact(
                workspace / "raw_exports" / "opening_states" / raw_name,
                raw_output / "opening_states" / raw_name,
                expected_hash=opening["raw_sha256"],
                field=f"opening state artifact {code}",
            )
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("opening state evidence must be UTF-8") from exc
            excerpt = str(opening["evidence_excerpt"])
            if not _phrase_present(text, excerpt):
                raise ValueError("opening-state evidence excerpt is absent")
            digest = require_sha256(opening["raw_sha256"], "opening.raw_sha256")
            opening_by_code[code] = {
                "ticker": ticker,
                "status": status,
                "raw_sha256": digest,
            }
            opening_rows.append(
                {
                    "security_code": code,
                    "ticker": ticker,
                    "status": status,
                    "effective_date": window_from.isoformat(),
                    "source_id": opening["source_id"],
                    "source_url": source_url,
                    "raw_sha256": digest,
                    "evidence_excerpt": excerpt,
                }
            )
            artifacts.append(
                {
                    "path": (Path("raw") / "opening_states" / raw_name).as_posix(),
                    "sha256": digest,
                    "size_bytes": len(content),
                    "source_id": opening["source_id"],
                    "source_url": source_url,
                    "observed_at": observed.isoformat(),
                    "capture_kind": "USER_EXPORT",
                    "artifact_role": "STATUS_HISTORY_OPENING_STATE",
                }
            )
        except (OSError, TypeError, ValueError) as exc:
            opening_errors.append(f"opening_{index}:{exc}")

    notice_rows_for_parser: list[dict[str, Any]] = []
    notice_csv_rows: list[dict[str, Any]] = []
    notice_errors: list[str] = []
    notices_by_query: dict[str, int] = {}
    seen_notice_ids: set[str] = set()
    notice_expected_fields = {
        "notice_id",
        "security_code",
        "ticker",
        "event_type",
        "effective_date",
        "published_date",
        "source_id",
        "source_url",
        "raw_file_name",
        "raw_sha256",
        "text_file_name",
        "text_sha256",
        "text_derivation",
        "query_id",
        "classification_phrase",
        "captured_at",
        "captured_by",
        "review_status",
        "review_notes",
    }
    for index, notice in enumerate(notices):
        try:
            if not isinstance(notice, dict) or set(notice) != notice_expected_fields:
                raise ValueError("notice has unknown or missing fields")
            notice_id = str(notice["notice_id"])
            if not notice_id or notice_id in seen_notice_ids:
                raise ValueError("notice_id is missing or duplicate")
            seen_notice_ids.add(notice_id)
            if notice["review_status"] != "ACCEPTED":
                raise ValueError("notice must be accepted")
            if notice["text_derivation"] not in _TEXT_DERIVATIONS:
                raise ValueError("unsupported notice text_derivation")
            source_url = _official_url(notice["source_url"], "notice.source_url")
            captured = parse_aware(notice["captured_at"], "notice.captured_at")
            if not str(notice["captured_by"]).strip():
                raise ValueError("notice captured_by is required")
            raw_name = Path(str(notice["raw_file_name"]))
            text_name = Path(str(notice["text_file_name"]))
            if raw_name.is_absolute() or text_name.is_absolute() or ".." in raw_name.parts or ".." in text_name.parts or len(raw_name.parts) != 1 or len(text_name.parts) != 1:
                raise ValueError("notice file names must be single safe components")
            raw_content = _copy_artifact(
                workspace / "raw_exports" / "notices" / raw_name,
                raw_output / "notices" / raw_name,
                expected_hash=notice["raw_sha256"],
                field=f"status notice raw artifact {notice_id}",
            )
            text_content = _copy_artifact(
                workspace / "text_exports" / "notices" / text_name,
                text_output / "notices" / text_name,
                expected_hash=notice["text_sha256"],
                field=f"status notice text artifact {notice_id}",
            )
            try:
                visible_text = text_content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("notice text export must be UTF-8") from exc
            phrase = str(notice["classification_phrase"])
            if not _phrase_present(visible_text, phrase):
                raise ValueError("notice classification phrase is absent from text export")
            raw_hash = require_sha256(notice["raw_sha256"], "notice.raw_sha256")
            text_hash = require_sha256(notice["text_sha256"], "notice.text_sha256")
            parser_row = {
                "notice_id": notice_id,
                "security_code": str(notice["security_code"]),
                "ticker": str(notice["ticker"]).upper(),
                "event_type": str(notice["event_type"]).upper(),
                "effective_date": str(notice["effective_date"]),
                "published_date": str(notice["published_date"]),
                "source_id": str(notice["source_id"]),
                "source_url": source_url,
                "raw_sha256": raw_hash,
                "text_sha256": text_hash,
                "query_id": str(notice["query_id"]),
                "classification_phrase": phrase,
            }
            notice_rows_for_parser.append(parser_row)
            notice_csv_rows.append(parser_row)
            notices_by_query[parser_row["query_id"]] = notices_by_query.get(parser_row["query_id"], 0) + 1
            artifacts.extend(
                [
                    {
                        "path": (Path("raw") / "notices" / raw_name).as_posix(),
                        "sha256": raw_hash,
                        "size_bytes": len(raw_content),
                        "source_id": parser_row["source_id"],
                        "source_url": source_url,
                        "observed_at": captured.isoformat(),
                        "capture_kind": "USER_EXPORT",
                        "artifact_role": "HISTORICAL_STATUS_NOTICE",
                    },
                    {
                        "path": (Path("text") / "notices" / text_name).as_posix(),
                        "sha256": text_hash,
                        "size_bytes": len(text_content),
                        "source_id": parser_row["source_id"],
                        "source_url": source_url,
                        "observed_at": captured.isoformat(),
                        "capture_kind": "DERIVED_TEXT",
                        "artifact_role": "REVIEWED_STATUS_NOTICE_TEXT_EXPORT",
                    },
                ]
            )
        except (OSError, TypeError, ValueError) as exc:
            notice_errors.append(f"notice_{index}:{exc}")

    for query_id, query in query_by_id.items():
        expected_count = _nonnegative_int(query["rows_normalized"], "rows_normalized")
        actual_count = notices_by_query.get(query_id, 0)
        if actual_count != expected_count:
            query_errors.append(
                f"QUERY_NOTICE_RECONCILIATION:{query_id}:declared={expected_count}:actual={actual_count}"
            )

    manifest_hashes = frozenset(item["sha256"] for item in artifacts)
    parsed_notices = []
    for index, row in enumerate(notice_rows_for_parser):
        try:
            parsed_notices.append(
                parse_status_notice(
                    row,
                    expected_identity=expected_identity,
                    manifest_hashes=manifest_hashes,
                    allowed_query_ids=frozenset(query_by_id),
                    window_from=window_from,
                    window_to=window_to,
                )
            )
        except ValueError as exc:
            notice_errors.append(f"notice_contract_{index}:{exc}")

    intervals, history_report = build_status_intervals(
        expected_identity=expected_identity,
        opening_states=opening_by_code,
        current_states=current_states,
        notices=parsed_notices,
        window_from=window_from,
        window_to=window_to,
    )
    combined_errors = sorted(
        set(
            [
                *query_errors,
                *opening_errors,
                *notice_errors,
                *history_report["errors"],
            ]
        )
    )
    if combined_errors:
        history_report["status"] = "BLOCKED"
        history_report["status_history_ready"] = False
        history_report["errors"] = combined_errors

    notice_path = normalized_output / "status_notice_ledger.csv"
    _write_csv(notice_path, STATUS_NOTICE_HEADERS, notice_csv_rows)
    interval_path = normalized_output / "status_intervals.csv"
    _write_csv(
        interval_path,
        STATUS_INTERVAL_HEADERS,
        [item.to_dict() for item in intervals],
    )
    query_path = manifest_output / "status_query_ledger.csv"
    _write_csv(query_path, STATUS_QUERY_HEADERS, query_rows)
    opening_path = normalized_output / "opening_status_evidence.csv"
    _write_csv(opening_path, OPENING_STATE_HEADERS, opening_rows)

    evidence_manifest = {
        "schema_version": "3.0",
        "artifacts": sorted(artifacts, key=lambda item: (item["path"], item["sha256"])),
    }
    (output / "manifest.json").write_bytes(canonical_json_bytes(evidence_manifest))
    (output / "status_history_manifest.json").write_bytes(manifest_bytes)
    (report_output / "status_history_validation_report.json").write_bytes(
        canonical_json_bytes(history_report)
    )

    status = (
        "HISTORICAL_STATUS_INTERVALS_READY"
        if history_report["status_history_ready"]
        else "BLOCKED"
    )
    logical_output = (
        Path(os.path.abspath(logical_output_root))
        if logical_output_root is not None
        else output
    )
    report = {
        "schema_version": "1.0",
        "status": status,
        "run_id": manifest["run_id"],
        "output_root": str(logical_output),
        "history_window_from": window_from.isoformat(),
        "history_window_to": window_to.isoformat(),
        "security_count": len(expected_identity),
        "query_count": len(query_rows),
        "notice_count": len(notice_csv_rows),
        "interval_count": len(intervals),
        "errors": combined_errors,
        "status_notice_ledger": str(
            logical_output / notice_path.relative_to(output)
        ),
        "status_intervals": str(
            logical_output / interval_path.relative_to(output)
        ),
        "status_query_ledger": str(
            logical_output / query_path.relative_to(output)
        ),
        "opening_status_evidence": str(
            logical_output / opening_path.relative_to(output)
        ),
        "validation_report": str(
            logical_output
            / (report_output / "status_history_validation_report.json").relative_to(
                output
            )
        ),
        "remaining_gates": [
            "CORPORATE_ACTION_RETURN_POLICIES",
            "BENCHMARK_HISTORY",
            "OFFICIAL_COMPLETE_DAILY_EOD",
        ],
        "claim_boundaries": {
            "query_receipt_is_official_market_fact": False,
            "reviewed_text_export_is_original_notice": False,
            "history_outside_declared_window_ready": False,
            "status_history_ready_for_declared_window": history_report[
                "status_history_ready"
            ],
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }
    report_path = report_output / "status_history_import_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "OPENING_STATE_HEADERS",
    "STATUS_INTERVAL_HEADERS",
    "STATUS_NOTICE_HEADERS",
    "STATUS_QUERY_HEADERS",
    "import_status_history",
]
