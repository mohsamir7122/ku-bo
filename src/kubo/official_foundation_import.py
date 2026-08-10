from __future__ import annotations

import csv
import json
import os
import re
import stat
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .evidence_hashes import format_supporting_hashes, parse_supporting_hashes
from .hashing import canonical_json_bytes, sha256_bytes
from .identity import validate_security_master
from .market import validate_trading_calendar
from .official_foundation_workspace import (
    OFFICIAL_ARTIFACT_SPECS,
    OFFICIAL_FOUNDATION_MANIFEST_SCHEMA_VERSION,
)
from .official_parsers import (
    ListedCompanyRecord,
    parse_boursa_contact_weekdays_html,
    parse_boursa_listed_companies_html,
    parse_boursa_market_holidays_html,
    parse_boursa_trading_extension_html,
)
from .source_parsers import parse_boursa_identity_html
from .strict import https_url, parse_aware, parse_iso_date, require_sha256
from .vendor_symbol_mapping import PilotIdentitySeedCatalog


KUWAIT = ZoneInfo("Asia/Kuwait")
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_OFFICIAL_ARTIFACT_BYTES = 10 * 1024 * 1024
SECURITY_MASTER_HEADERS = (
    "security_code",
    "ticker",
    "isin",
    "name_ar",
    "name_en",
    "board",
    "market_segment",
    "currency",
    "valid_from",
    "valid_to",
    "listing_status",
    "raw_sha256",
    "supporting_raw_sha256s",
    "listing_date",
    "identity_scope",
)
TRADING_CALENDAR_HEADERS = (
    "trade_date",
    "is_trading_day",
    "session_type",
    "session_regime_id",
    "continuous_start",
    "continuous_end",
    "trade_at_last_end",
    "raw_sha256",
    "supporting_raw_sha256s",
    "holiday_name",
)



def _strict_json_object(content: bytes, field: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{field} contains non-finite JSON value: {value}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{field} contains duplicate object key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{field} must be strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return value



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
            raise ValueError(f"{field} changed while it was read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)



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



def _write_csv(path: Path, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})



def _artifact_spec_map() -> dict[str, dict[str, str]]:
    return {item["artifact_id"]: dict(item) for item in OFFICIAL_ARTIFACT_SPECS}



def _load_manifest(workspace: Path) -> tuple[dict[str, Any], bytes, dict[str, dict[str, Any]]]:
    manifest_path = workspace / "manifests" / "official_foundation_manifest.json"
    content = _safe_regular_file(
        manifest_path,
        field="official foundation manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    payload = _strict_json_object(content, "official foundation manifest")
    required_top = {
        "schema_version",
        "run_id",
        "identity_snapshot_effective_date",
        "calendar_window_from",
        "calendar_window_to",
        "artifacts",
    }
    if set(payload) != required_top:
        raise ValueError("official foundation manifest has unknown or missing fields")
    if payload["schema_version"] != OFFICIAL_FOUNDATION_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported official foundation manifest schema_version")
    if not isinstance(payload["run_id"], str) or not payload["run_id"].strip():
        raise ValueError("manifest run_id is required")
    identity_date = parse_iso_date(
        payload["identity_snapshot_effective_date"],
        "identity_snapshot_effective_date",
    )
    window_from = parse_iso_date(payload["calendar_window_from"], "calendar_window_from")
    window_to = parse_iso_date(payload["calendar_window_to"], "calendar_window_to")
    if window_from > window_to:
        raise ValueError("calendar window is reversed")
    if window_from.year != window_to.year:
        raise ValueError("official holiday import supports one calendar year per run")
    payload["identity_snapshot_effective_date"] = identity_date
    payload["calendar_window_from"] = window_from
    payload["calendar_window_to"] = window_to

    rows = payload["artifacts"]
    specs = _artifact_spec_map()
    if not isinstance(rows, list) or len(rows) != len(specs):
        raise ValueError("manifest must contain every required official artifact exactly once")
    expected_fields = {
        "artifact_id",
        "source_id",
        "source_url",
        "file_name",
        "capture_mode",
        "purpose",
        "file_sha256",
        "observed_at",
        "captured_by",
        "review_status",
        "review_notes",
    }
    artifacts: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != expected_fields:
            raise ValueError(f"manifest artifact {index} has unknown or missing fields")
        artifact_id = str(row["artifact_id"])
        spec = specs.get(artifact_id)
        if spec is None or artifact_id in artifacts:
            raise ValueError(f"manifest artifact {index} has unknown or duplicate artifact_id")
        for field in (
            "source_id",
            "source_url",
            "file_name",
            "capture_mode",
            "purpose",
        ):
            if row[field] != spec[field]:
                raise ValueError(f"manifest {artifact_id}.{field} differs from the source contract")
        https_url(row["source_url"], f"{artifact_id}.source_url")
        digest = require_sha256(row["file_sha256"], f"{artifact_id}.file_sha256")
        observed_at = parse_aware(row["observed_at"], f"{artifact_id}.observed_at")
        if row["review_status"] != "ACCEPTED":
            raise ValueError(f"manifest artifact is not accepted: {artifact_id}")
        if not str(row["captured_by"]).strip():
            raise ValueError(f"manifest captured_by is required: {artifact_id}")
        artifacts[artifact_id] = {
            **row,
            "file_sha256": digest,
            "observed_datetime": observed_at,
        }
    if set(artifacts) != set(specs):
        raise ValueError("manifest official artifact set is incomplete")
    identity_observation_days = {
        artifacts[artifact_id]["observed_datetime"].astimezone(KUWAIT).date()
        for artifact_id in ("short_sell_identity", "listed_companies")
    }
    if len(identity_observation_days) != 1:
        raise ValueError("official identity artifacts must be observed on one Kuwait civil date")
    observed_identity_day = next(iter(identity_observation_days))
    if identity_date != observed_identity_day:
        raise ValueError(
            "identity_snapshot_effective_date must equal the official identity capture date"
        )
    return payload, content, artifacts



def _name_key(value: str) -> tuple[str, ...]:
    text = re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()
    aliases = {
        "CO": "COMPANY",
        "CORP": "COMPANY",
        "CORPORATION": "COMPANY",
        "TELECOM": "TELECOMMUNICATIONS",
    }
    ignored = {
        "THE",
        "KSC",
        "KSCP",
        "KPSC",
        "PUBLIC",
        "SHAREHOLDING",
        "CLOSED",
    }
    return tuple(
        aliases.get(token, token)
        for token in text.split()
        if token not in ignored
    )



def _names_compatible(left: str, right: str) -> bool:
    left_tokens = _name_key(left)
    right_tokens = _name_key(right)
    if left_tokens == right_tokens:
        return True
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if not left_set or not right_set:
        return False
    overlap = len(left_set & right_set)
    return overlap / min(len(left_set), len(right_set)) >= 0.8



def _security_master_rows(
    *,
    config_dir: Path,
    snapshot_date: date,
    short_sell_content: bytes,
    listed_content: bytes,
    short_sell_hash: str,
    listed_hash: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    seed_catalog = PilotIdentitySeedCatalog(config_dir)
    short_rows = {
        row.security_code: row for row in parse_boursa_identity_html(short_sell_content)
    }
    listed_rows = {
        row.security_code: row for row in parse_boursa_listed_companies_html(listed_content)
    }
    errors: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []
    for ticker, seed in sorted(seed_catalog.identities.items()):
        if seed.identity_state == "RETIRED":
            continue
        short = short_rows.get(seed.security_code)
        listed = listed_rows.get(seed.security_code)
        if short is None:
            errors.append(f"MISSING_SHORT_SELL_IDENTITY:{seed.security_code}")
            continue
        if listed is None:
            errors.append(f"MISSING_LISTED_COMPANY_IDENTITY:{seed.security_code}")
            continue
        if short.isin != seed.isin:
            errors.append(f"OFFICIAL_ISIN_CONFLICT:{seed.security_code}")
        if listed.ticker != ticker:
            errors.append(f"OFFICIAL_TICKER_CONFLICT:{seed.security_code}")
        if listed.listing_date > snapshot_date:
            errors.append(f"LISTING_DATE_AFTER_IDENTITY_SNAPSHOT:{seed.security_code}")
        if not _names_compatible(short.name, listed.name):
            errors.append(f"OFFICIAL_NAME_CONFLICT:{seed.security_code}")
        elif not _names_compatible(listed.name, seed.name_en):
            warnings.append(f"SEED_NAME_DIFFERS_FROM_OFFICIAL:{seed.security_code}")
        rows.append(
            {
                "security_code": seed.security_code,
                "ticker": listed.ticker,
                "isin": short.isin,
                "name_ar": "",
                "name_en": listed.name,
                "board": "cash",
                "market_segment": listed.market_segment,
                "currency": "KWD",
                "valid_from": snapshot_date.isoformat(),
                "valid_to": "",
                "listing_status": "ACTIVE",
                "raw_sha256": short_sell_hash,
                "supporting_raw_sha256s": format_supporting_hashes([listed_hash]),
                "listing_date": listed.listing_date.isoformat(),
                "identity_scope": "CURRENT_SNAPSHOT_ONLY",
            }
        )
    expected_codes = {
        seed.security_code
        for seed in seed_catalog.identities.values()
        if seed.identity_state != "RETIRED"
    }
    actual_codes = {row["security_code"] for row in rows}
    if actual_codes != expected_codes:
        errors.append(
            f"PILOT_IDENTITY_DENOMINATOR_MISMATCH:missing={len(expected_codes - actual_codes)}:extra={len(actual_codes - expected_codes)}"
        )
    return rows, {
        "status": "PASS" if rows and not errors else "BLOCKED",
        "rows": len(rows),
        "expected_rows": len(expected_codes),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "identity_scope": "CURRENT_SNAPSHOT_ONLY",
        "historical_identity_ready": False,
    }



def _calendar_rows(
    *,
    window_from: date,
    window_to: date,
    holidays_content: bytes,
    extension_content: bytes,
    contact_content: bytes,
    holidays_hash: str,
    extension_hash: str,
    contact_hash: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    holiday_year, holiday_records = parse_boursa_market_holidays_html(holidays_content)
    if window_from.year != holiday_year or window_to.year != holiday_year:
        raise ValueError("calendar window year does not match the official holiday page")
    regime = parse_boursa_trading_extension_html(extension_content)
    weekdays = parse_boursa_contact_weekdays_html(contact_content)
    if window_from < regime.effective_from:
        raise ValueError("calendar window starts before the parsed trading regime")
    holiday_map = {item.holiday_date: item.name for item in holiday_records}
    rows: list[dict[str, Any]] = []
    current = window_from
    while current <= window_to:
        holiday_name = holiday_map.get(current, "")
        if holiday_name:
            is_trading = False
            session_type = "HOLIDAY"
            primary_hash = holidays_hash
            supporting = format_supporting_hashes([contact_hash, extension_hash])
            regime_id = ""
            continuous_start = ""
            continuous_end = ""
            trade_at_last_end = ""
        elif current.weekday() not in weekdays:
            is_trading = False
            session_type = "WEEKEND"
            primary_hash = contact_hash
            supporting = ""
            regime_id = ""
            continuous_start = ""
            continuous_end = ""
            trade_at_last_end = ""
        else:
            is_trading = True
            session_type = "NORMAL"
            primary_hash = extension_hash
            supporting = format_supporting_hashes([contact_hash])
            regime_id = regime.session_regime_id
            continuous_start = regime.continuous_start
            continuous_end = regime.continuous_end
            trade_at_last_end = regime.trade_at_last_end
        rows.append(
            {
                "trade_date": current.isoformat(),
                "is_trading_day": "true" if is_trading else "false",
                "session_type": session_type,
                "session_regime_id": regime_id,
                "continuous_start": continuous_start,
                "continuous_end": continuous_end,
                "trade_at_last_end": trade_at_last_end,
                "raw_sha256": primary_hash,
                "supporting_raw_sha256s": supporting,
                "holiday_name": holiday_name,
            }
        )
        current += timedelta(days=1)
    return rows, {
        "status": "PASS" if rows else "BLOCKED",
        "rows": len(rows),
        "calendar_year": holiday_year,
        "trading_days": sum(row["is_trading_day"] == "true" for row in rows),
        "holiday_days": sum(row["session_type"] == "HOLIDAY" for row in rows),
        "weekend_days": sum(row["session_type"] == "WEEKEND" for row in rows),
        "open_weekdays": sorted(weekdays),
        "session_regime_id": regime.session_regime_id,
        "regime_effective_from": regime.effective_from.isoformat(),
        "holiday_snapshot_subject_to_change": True,
    }



def import_official_foundation(
    *,
    config_dir: Path,
    workspace: Path,
    output_root: Path,
) -> dict[str, Any]:
    workspace = Path(workspace)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("workspace must be a real directory")
    output = _prepare_output_root(Path(output_root))
    raw_output = output / "raw"
    normalized_output = output / "normalized"
    report_output = output / "reports"
    for directory in (raw_output, normalized_output, report_output):
        directory.mkdir(parents=True, exist_ok=True)

    manifest, manifest_bytes, artifact_rows = _load_manifest(workspace)
    raw_input = workspace / "raw_exports" / "boursa"
    contents: dict[str, bytes] = {}
    manifest_artifacts: list[dict[str, Any]] = []
    for artifact_id, row in sorted(artifact_rows.items()):
        source_path = raw_input / row["file_name"]
        content = _safe_regular_file(
            source_path,
            field=f"official artifact {artifact_id}",
            max_bytes=MAX_OFFICIAL_ARTIFACT_BYTES,
        )
        digest = sha256_bytes(content)
        if digest != row["file_sha256"]:
            raise ValueError(f"official artifact hash mismatch: {artifact_id}")
        preserved = raw_output / row["file_name"]
        preserved.write_bytes(content)
        contents[artifact_id] = content
        manifest_artifacts.append(
            {
                "path": preserved.relative_to(output).as_posix(),
                "sha256": digest,
                "size_bytes": len(content),
                "source_id": row["source_id"],
                "source_url": row["source_url"],
                "observed_at": row["observed_datetime"].isoformat(),
                "capture_kind": (
                    "USER_EXPORT"
                    if row["capture_mode"] in {"AUTHORIZED_BROWSER", "USER_EXPORT"}
                    else "RAW_PAGE"
                ),
                "artifact_role": artifact_id.upper(),
            }
        )

    hashes = {item["artifact_role"].lower(): item["sha256"] for item in manifest_artifacts}
    security_rows, identity_report = _security_master_rows(
        config_dir=config_dir,
        snapshot_date=manifest["identity_snapshot_effective_date"],
        short_sell_content=contents["short_sell_identity"],
        listed_content=contents["listed_companies"],
        short_sell_hash=hashes["short_sell_identity"],
        listed_hash=hashes["listed_companies"],
    )
    security_path = normalized_output / "security_master.csv"
    _write_csv(security_path, SECURITY_MASTER_HEADERS, security_rows)
    identity_records, security_errors = validate_security_master(
        security_path,
        manifest_hashes=frozenset(item["sha256"] for item in manifest_artifacts),
    )
    if security_errors:
        identity_report["status"] = "BLOCKED"
        identity_report["errors"] = sorted(
            set([*identity_report["errors"], *security_errors])
        )
    identity_report["validated_rows"] = len(identity_records)

    calendar_rows, calendar_report = _calendar_rows(
        window_from=manifest["calendar_window_from"],
        window_to=manifest["calendar_window_to"],
        holidays_content=contents["market_holidays"],
        extension_content=contents["trading_extension"],
        contact_content=contents["contact_hours"],
        holidays_hash=hashes["market_holidays"],
        extension_hash=hashes["trading_extension"],
        contact_hash=hashes["contact_hours"],
    )
    calendar_path = normalized_output / "trading_calendar.csv"
    _write_csv(calendar_path, TRADING_CALENDAR_HEADERS, calendar_rows)
    manifest_hashes = frozenset(item["sha256"] for item in manifest_artifacts)
    _, calendar_validation = validate_trading_calendar(
        calendar_path,
        manifest_hashes=manifest_hashes,
        window_from=manifest["calendar_window_from"],
        window_to=manifest["calendar_window_to"],
    )
    supporting_errors: list[str] = []
    for index, row in enumerate(calendar_rows):
        try:
            supporting = parse_supporting_hashes(
                row["supporting_raw_sha256s"],
                field="supporting_raw_sha256s",
                manifest_hashes=manifest_hashes,
            )
            if row["raw_sha256"] in supporting:
                raise ValueError("primary hash is duplicated in supporting evidence")
        except ValueError as exc:
            supporting_errors.append(f"calendar_row_{index}:{exc}")
    if calendar_validation.status != "PASS" or supporting_errors:
        calendar_report["status"] = "BLOCKED"
        calendar_report["errors"] = sorted(
            set([*calendar_validation.errors, *supporting_errors])
        )
    else:
        calendar_report["errors"] = []

    evidence_manifest = {
        "schema_version": "3.0",
        "artifacts": manifest_artifacts,
    }
    (output / "manifest.json").write_bytes(canonical_json_bytes(evidence_manifest))
    (output / "official_foundation_manifest.json").write_bytes(manifest_bytes)
    (report_output / "official_identity_report.json").write_bytes(
        canonical_json_bytes(identity_report)
    )
    (report_output / "trading_calendar_report.json").write_bytes(
        canonical_json_bytes(calendar_report)
    )

    identity_pass = identity_report["status"] == "PASS"
    calendar_pass = calendar_report["status"] == "PASS"
    if identity_pass and calendar_pass:
        status = "CURRENT_IDENTITY_AND_CALENDAR_READY"
    elif identity_pass or calendar_pass:
        status = "PARTIAL"
    else:
        status = "BLOCKED"
    report = {
        "schema_version": "1.0",
        "status": status,
        "run_id": manifest["run_id"],
        "output_root": str(output),
        "identity_snapshot_effective_date": manifest[
            "identity_snapshot_effective_date"
        ].isoformat(),
        "calendar_window_from": manifest["calendar_window_from"].isoformat(),
        "calendar_window_to": manifest["calendar_window_to"].isoformat(),
        "security_master": str(security_path),
        "trading_calendar": str(calendar_path),
        "official_identity_report": str(
            report_output / "official_identity_report.json"
        ),
        "trading_calendar_report": str(
            report_output / "trading_calendar_report.json"
        ),
        "identity_status": identity_report["status"],
        "calendar_status": calendar_report["status"],
        "remaining_gates": [
            "HISTORICAL_IDENTITY_AND_RENAMES",
            "SECURITY_STATUS_HISTORY",
            "CORPORATE_ACTION_LEDGER",
            "BENCHMARK_HISTORY",
            "OFFICIAL_COMPLETE_DAILY_EOD",
        ],
        "claim_boundaries": {
            "current_identity_is_historical_identity": False,
            "listed_snapshot_proves_past_membership": False,
            "holiday_snapshot_is_immutable": False,
            "security_status_history_ready": False,
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }
    report_path = report_output / "official_foundation_import_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "SECURITY_MASTER_HEADERS",
    "TRADING_CALENDAR_HEADERS",
    "import_official_foundation",
]
