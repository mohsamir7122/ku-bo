from __future__ import annotations

import csv
import json
import os
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .ca_adjustments import calculate_adjustment
from .ca_enrichment_workspace import CA_ENRICHMENT_MANIFEST_SCHEMA_VERSION
from .hashing import canonical_json_bytes, sha256_bytes
from .strict import parse_aware, parse_iso_date, require_sha256


MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
_ALLOWED_OFFICIAL_HOSTS = frozenset(
    {
        "boursakuwait.com.kw",
        "www.boursakuwait.com.kw",
        "reports.boursakuwait.com.kw",
        "ifsah.boursakuwait.com.kw",
        "cma.gov.kw",
        "www.cma.gov.kw",
    }
)
_ALLOWED_UPSTREAM_STATUSES = frozenset(
    {
        "CURRENT_STATUS_AND_CA_SCHEDULE_READY",
        "CURRENT_STATUS_AND_CA_ZERO_RESULT_READY",
    }
)
_TEXT_DERIVATIONS = frozenset(
    {
        "OFFICIAL_HTML_VISIBLE_TEXT",
        "REVIEWED_PDF_TEXT_EXPORT",
        "OFFICIAL_XBRL_VISIBLE_TEXT",
    }
)
FACTOR_LEDGER_HEADERS = (
    "action_id",
    "security_code",
    "ticker",
    "isin",
    "cum_date",
    "ex_date",
    "record_date",
    "payment_date",
    "action_type",
    "formula_mode",
    "factor_status",
    "formula_id",
    "previous_close_fils",
    "theoretical_ex_price_fils",
    "reference_price_factor",
    "historical_continuity_factor",
    "position_quantity_multiplier",
    "return_price_multiplier",
    "cash_distribution_per_pre_action_share_fils",
    "rights_cash_contribution_per_pre_action_share_fils",
    "return_engine_treatment",
    "return_engine_ready",
    "reference_price_use",
    "limitations",
    "schedule_row_sha256",
    "disclosure_raw_sha256",
    "disclosure_text_sha256",
    "price_reference_raw_sha256",
    "disclosure_source_url",
    "price_source_url",
    "published_at",
    "review_status",
)
RETURN_POLICY_QUEUE_HEADERS = (
    "action_id",
    "security_code",
    "ticker",
    "action_type",
    "ex_date",
    "return_engine_treatment",
    "required_policy",
    "factor_status",
    "review_status",
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


def _read_csv(content: bytes, field: str) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{field} must be UTF-8 CSV") from exc
    reader = csv.DictReader(text.splitlines())
    headers = tuple(reader.fieldnames or ())
    if not headers or len(headers) != len(set(headers)):
        raise ValueError(f"{field} has missing or duplicate headers")
    return headers, [
        {key: str(value or "").strip() for key, value in row.items()}
        for row in reader
    ]


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


def _load_upstream(status_corporate_root: Path) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
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
    schedule_bytes = _safe_regular_file(
        root / "normalized" / "corporate_action_schedule.csv",
        field="upstream corporate_action_schedule.csv",
        max_bytes=MAX_ARTIFACT_BYTES,
    )
    queue_bytes = _safe_regular_file(
        root / "normalized" / "corporate_action_enrichment_queue.csv",
        field="upstream corporate_action_enrichment_queue.csv",
        max_bytes=MAX_ARTIFACT_BYTES,
    )
    _, schedule_rows = _read_csv(schedule_bytes, "upstream corporate action schedule")
    _, queue_rows = _read_csv(queue_bytes, "upstream corporate action enrichment queue")
    if len({row.get("action_id") for row in schedule_rows}) != len(schedule_rows):
        raise ValueError("upstream schedule action IDs must be unique")
    if len({row.get("action_id") for row in queue_rows}) != len(queue_rows):
        raise ValueError("upstream queue action IDs must be unique")
    hashes = {
        "report_sha256": sha256_bytes(report_bytes),
        "schedule_sha256": sha256_bytes(schedule_bytes),
        "enrichment_queue_sha256": sha256_bytes(queue_bytes),
    }
    return report, schedule_rows, queue_rows, hashes


def _validate_manifest(
    workspace: Path,
    *,
    upstream_report: dict[str, Any],
    schedule_rows: list[dict[str, str]],
    queue_rows: list[dict[str, str]],
    upstream_hashes: dict[str, str],
) -> tuple[dict[str, Any], bytes]:
    content = _safe_regular_file(
        workspace / "manifests" / "ca_enrichment_manifest.json",
        field="corporate action enrichment manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    payload = _strict_json_object(content, "corporate action enrichment manifest")
    if set(payload) != {"schema_version", "run_id", "upstream", "actions"}:
        raise ValueError("corporate action enrichment manifest has unknown or missing fields")
    if payload["schema_version"] != CA_ENRICHMENT_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported corporate action enrichment schema_version")
    upstream = payload["upstream"]
    if not isinstance(upstream, dict) or set(upstream) != {
        "status",
        "run_id",
        "report_sha256",
        "schedule_sha256",
        "enrichment_queue_sha256",
    }:
        raise ValueError("corporate action enrichment upstream receipt is invalid")
    expected_upstream = {
        "status": upstream_report["status"],
        "run_id": upstream_report.get("run_id"),
        **upstream_hashes,
    }
    if upstream != expected_upstream:
        raise ValueError("corporate action enrichment upstream receipt is stale")
    actions = payload["actions"]
    if not isinstance(actions, list):
        raise ValueError("corporate action enrichment actions must be a list")
    schedule_by_id = {row["action_id"]: row for row in schedule_rows}
    queue_by_id = {row["action_id"]: row for row in queue_rows}
    if len(actions) != len(schedule_by_id):
        raise ValueError("corporate action enrichment denominator mismatch")
    seen: set[str] = set()
    expected_action_fields = {
        "action_id",
        "security_code",
        "ticker",
        "isin",
        "cum_date",
        "ex_date",
        "record_date",
        "payment_date",
        "schedule_row_sha256",
        "required_enrichment",
        "disclosure",
        "price_reference",
        "terms",
    }
    for index, action in enumerate(actions):
        if not isinstance(action, dict) or set(action) != expected_action_fields:
            raise ValueError(f"enrichment action {index} has unknown or missing fields")
        action_id = str(action["action_id"])
        if not action_id or action_id in seen or action_id not in schedule_by_id:
            raise ValueError(f"enrichment action {index} has invalid action_id")
        seen.add(action_id)
        schedule = schedule_by_id[action_id]
        queue = queue_by_id[action_id]
        for field in (
            "security_code",
            "ticker",
            "isin",
            "cum_date",
            "ex_date",
            "record_date",
            "payment_date",
        ):
            if action[field] != schedule[field]:
                raise ValueError(f"enrichment action {action_id}.{field} differs from upstream schedule")
        if action["required_enrichment"] != queue["required_enrichment"]:
            raise ValueError(f"enrichment requirement differs from upstream queue: {action_id}")
        expected_row_hash = sha256_bytes(canonical_json_bytes(schedule))
        if action["schedule_row_sha256"] != expected_row_hash:
            raise ValueError(f"enrichment action has stale schedule row hash: {action_id}")
    if seen != set(schedule_by_id):
        raise ValueError("corporate action enrichment action set is incomplete")
    return payload, content


def _copy_validated_artifact(
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


def import_ca_enrichment(
    *,
    status_corporate_root: Path,
    workspace: Path,
    output_root: Path,
) -> dict[str, Any]:
    workspace = Path(workspace)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("workspace must be a real directory")
    upstream_report, schedule_rows, queue_rows, upstream_hashes = _load_upstream(
        status_corporate_root
    )
    manifest, manifest_bytes = _validate_manifest(
        workspace,
        upstream_report=upstream_report,
        schedule_rows=schedule_rows,
        queue_rows=queue_rows,
        upstream_hashes=upstream_hashes,
    )
    output = _prepare_output_root(Path(output_root))
    raw_output = output / "raw"
    text_output = output / "text"
    normalized_output = output / "normalized"
    report_output = output / "reports"
    for directory in (raw_output, text_output, normalized_output, report_output):
        directory.mkdir(parents=True, exist_ok=True)

    factor_rows: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    errors: list[str] = []
    pending_actions: list[str] = []
    accepted_actions: list[str] = []
    factor_ready_actions: list[str] = []
    return_ready_actions: list[str] = []

    for action in manifest["actions"]:
        action_id = action["action_id"]
        disclosure = action["disclosure"]
        price_reference = action["price_reference"]
        terms = action["terms"]
        try:
            if not isinstance(disclosure, dict) or not isinstance(price_reference, dict) or not isinstance(terms, dict):
                raise ValueError("disclosure, price_reference, and terms must be objects")
            if disclosure.get("review_status") != "ACCEPTED":
                pending_actions.append(action_id)
                factor_rows.append(
                    {
                        "action_id": action_id,
                        "security_code": action["security_code"],
                        "ticker": action["ticker"],
                        "isin": action["isin"],
                        "cum_date": action["cum_date"],
                        "ex_date": action["ex_date"],
                        "record_date": action["record_date"],
                        "payment_date": action["payment_date"],
                        "action_type": terms.get("action_type", "OTHER"),
                        "formula_mode": "NO_AUTOMATIC_FORMULA",
                        "factor_status": "pending",
                        "formula_id": "pending_official_disclosure_v1",
                        "return_engine_treatment": "BLOCKED_PENDING_OFFICIAL_DISCLOSURE",
                        "return_engine_ready": "false",
                        "limitations": "OFFICIAL_DISCLOSURE_REVIEW_REQUIRED",
                        "schedule_row_sha256": action["schedule_row_sha256"],
                        "review_status": "PENDING",
                    }
                )
                continue

            expected_disclosure_fields = {
                "source_url",
                "raw_file_name",
                "raw_sha256",
                "text_file_name",
                "text_sha256",
                "text_derivation",
                "published_at",
                "captured_at",
                "captured_by",
                "evidence_phrases",
                "review_status",
                "review_notes",
            }
            if set(disclosure) != expected_disclosure_fields:
                raise ValueError("disclosure object has unknown or missing fields")
            disclosure_url = _official_url(disclosure["source_url"], "disclosure.source_url")
            if disclosure["text_derivation"] not in _TEXT_DERIVATIONS:
                raise ValueError("unsupported disclosure text_derivation")
            published = parse_aware(disclosure["published_at"], "disclosure.published_at")
            captured = parse_aware(disclosure["captured_at"], "disclosure.captured_at")
            if captured < published:
                raise ValueError("disclosure captured_at precedes published_at")
            if not str(disclosure["captured_by"]).strip():
                raise ValueError("disclosure captured_by is required")
            phrases = disclosure["evidence_phrases"]
            if not isinstance(phrases, list) or not 1 <= len(phrases) <= 20:
                raise ValueError("disclosure evidence_phrases must contain 1..20 phrases")
            if any(not isinstance(item, str) or not item.strip() for item in phrases):
                raise ValueError("disclosure evidence phrases must be non-empty strings")
            raw_name = Path(str(disclosure["raw_file_name"]))
            text_name = Path(str(disclosure["text_file_name"]))
            if raw_name.is_absolute() or text_name.is_absolute() or ".." in raw_name.parts or ".." in text_name.parts or len(raw_name.parts) != 1 or len(text_name.parts) != 1:
                raise ValueError("disclosure file names must be single safe path components")
            raw_content = _copy_validated_artifact(
                workspace / "raw_exports" / "disclosures" / raw_name,
                raw_output / "disclosures" / raw_name,
                expected_hash=disclosure["raw_sha256"],
                field=f"disclosure raw artifact {action_id}",
            )
            text_content = _copy_validated_artifact(
                workspace / "text_exports" / "disclosures" / text_name,
                text_output / "disclosures" / text_name,
                expected_hash=disclosure["text_sha256"],
                field=f"disclosure text artifact {action_id}",
            )
            try:
                visible_text = text_content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("disclosure text export must be UTF-8") from exc
            missing_phrases = [item for item in phrases if not _phrase_present(visible_text, item)]
            if missing_phrases:
                raise ValueError("disclosure evidence phrase is absent from text export")

            terms_expected = {
                "action_type",
                "formula_mode",
                "previous_close_fils",
                "cash_per_share_fils",
                "new_shares_per_old_share",
                "rights_new_shares_per_old_share",
                "subscription_price_fils",
                "official_reference_price_fils",
                "official_factor",
                "official_position_quantity_multiplier",
                "fractional_entitlement_policy",
                "formula_notes",
            }
            if set(terms) != terms_expected:
                raise ValueError("corporate-action terms have unknown or missing fields")

            requires_price = terms["formula_mode"] in {
                "OFFICIAL_REFERENCE_PRICE",
                "REPRODUCIBLE_MECHANICAL",
            } or terms.get("previous_close_fils") not in (None, "")
            price_raw_hash = ""
            price_url = ""
            if requires_price:
                expected_price_fields = {
                    "source_url",
                    "raw_file_name",
                    "raw_sha256",
                    "trade_date",
                    "previous_close_fils",
                    "evidence_excerpt",
                    "captured_at",
                    "captured_by",
                    "review_status",
                    "review_notes",
                }
                if set(price_reference) != expected_price_fields:
                    raise ValueError("price_reference object has unknown or missing fields")
                if price_reference["review_status"] != "ACCEPTED":
                    raise ValueError("price_reference must be accepted when formula uses previous close")
                price_url = _official_url(price_reference["source_url"], "price_reference.source_url")
                trade_date = parse_iso_date(price_reference["trade_date"], "price_reference.trade_date")
                if trade_date >= parse_iso_date(action["ex_date"], "ex_date"):
                    raise ValueError("price reference trade_date must precede ex_date")
                if str(price_reference["previous_close_fils"]) != str(terms["previous_close_fils"]):
                    raise ValueError("price_reference previous close differs from formula terms")
                price_name = Path(str(price_reference["raw_file_name"]))
                if price_name.is_absolute() or ".." in price_name.parts or len(price_name.parts) != 1:
                    raise ValueError("price reference file name must be one safe component")
                price_content = _copy_validated_artifact(
                    workspace / "raw_exports" / "reference_prices" / price_name,
                    raw_output / "reference_prices" / price_name,
                    expected_hash=price_reference["raw_sha256"],
                    field=f"price reference artifact {action_id}",
                )
                try:
                    price_text = price_content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError("price reference artifact must be UTF-8") from exc
                excerpt = str(price_reference["evidence_excerpt"])
                if not _phrase_present(price_text, excerpt):
                    raise ValueError("price evidence excerpt is absent from official artifact")
                price_raw_hash = require_sha256(price_reference["raw_sha256"], "price_reference.raw_sha256")
                artifacts.append(
                    {
                        "path": (Path("raw") / "reference_prices" / price_name).as_posix(),
                        "sha256": price_raw_hash,
                        "size_bytes": len(price_content),
                        "source_id": "boursa_reference_price",
                        "source_url": price_url,
                        "observed_at": parse_aware(price_reference["captured_at"], "price_reference.captured_at").isoformat(),
                        "capture_kind": "USER_EXPORT",
                        "artifact_role": "OFFICIAL_REFERENCE_PRICE_EVIDENCE",
                    }
                )

            result = calculate_adjustment(terms)
            result_dict = result.to_dict()
            accepted_actions.append(action_id)
            if result.factor_status in {"official", "reproducible"}:
                factor_ready_actions.append(action_id)
            if result.return_engine_ready:
                return_ready_actions.append(action_id)
            limitations = "|".join(result_dict["limitations"])
            factor_rows.append(
                {
                    "action_id": action_id,
                    "security_code": action["security_code"],
                    "ticker": action["ticker"],
                    "isin": action["isin"],
                    "cum_date": action["cum_date"],
                    "ex_date": action["ex_date"],
                    "record_date": action["record_date"],
                    "payment_date": action["payment_date"],
                    "action_type": result.action_type,
                    "formula_mode": result.formula_mode,
                    "factor_status": result.factor_status,
                    "formula_id": result.formula_id,
                    "previous_close_fils": result_dict["previous_close_fils"] or "",
                    "theoretical_ex_price_fils": result_dict["theoretical_ex_price_fils"] or "",
                    "reference_price_factor": result_dict["reference_price_factor"] or "",
                    "historical_continuity_factor": result_dict["historical_continuity_factor"] or "",
                    "position_quantity_multiplier": result_dict["position_quantity_multiplier"] or "",
                    "return_price_multiplier": result_dict["return_price_multiplier"] or "",
                    "cash_distribution_per_pre_action_share_fils": result_dict["cash_distribution_per_pre_action_share_fils"] or "",
                    "rights_cash_contribution_per_pre_action_share_fils": result_dict["rights_cash_contribution_per_pre_action_share_fils"] or "",
                    "return_engine_treatment": result.return_engine_treatment,
                    "return_engine_ready": "true" if result.return_engine_ready else "false",
                    "reference_price_use": result.reference_price_use,
                    "limitations": limitations,
                    "schedule_row_sha256": action["schedule_row_sha256"],
                    "disclosure_raw_sha256": require_sha256(disclosure["raw_sha256"], "disclosure.raw_sha256"),
                    "disclosure_text_sha256": require_sha256(disclosure["text_sha256"], "disclosure.text_sha256"),
                    "price_reference_raw_sha256": price_raw_hash,
                    "disclosure_source_url": disclosure_url,
                    "price_source_url": price_url,
                    "published_at": published.isoformat(),
                    "review_status": "ACCEPTED",
                }
            )
            if not result.return_engine_ready:
                policy_rows.append(
                    {
                        "action_id": action_id,
                        "security_code": action["security_code"],
                        "ticker": action["ticker"],
                        "action_type": result.action_type,
                        "ex_date": action["ex_date"],
                        "return_engine_treatment": result.return_engine_treatment,
                        "required_policy": limitations or "ACTION_SPECIFIC_RETURN_POLICY",
                        "factor_status": result.factor_status,
                        "review_status": "PENDING",
                    }
                )
            artifacts.extend(
                [
                    {
                        "path": (Path("raw") / "disclosures" / raw_name).as_posix(),
                        "sha256": require_sha256(disclosure["raw_sha256"], "disclosure.raw_sha256"),
                        "size_bytes": len(raw_content),
                        "source_id": "official_disclosure",
                        "source_url": disclosure_url,
                        "observed_at": captured.isoformat(),
                        "capture_kind": "USER_EXPORT",
                        "artifact_role": "CORPORATE_ACTION_DISCLOSURE",
                    },
                    {
                        "path": (Path("text") / "disclosures" / text_name).as_posix(),
                        "sha256": require_sha256(disclosure["text_sha256"], "disclosure.text_sha256"),
                        "size_bytes": len(text_content),
                        "source_id": "official_disclosure",
                        "source_url": disclosure_url,
                        "observed_at": captured.isoformat(),
                        "capture_kind": "DERIVED_TEXT",
                        "artifact_role": "REVIEWED_DISCLOSURE_TEXT_EXPORT",
                    },
                ]
            )
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"{action_id}:{exc}")

    factor_path = normalized_output / "corporate_action_factor_ledger.csv"
    _write_csv(factor_path, FACTOR_LEDGER_HEADERS, factor_rows)
    policy_path = normalized_output / "corporate_action_return_policy_queue.csv"
    _write_csv(policy_path, RETURN_POLICY_QUEUE_HEADERS, policy_rows)
    evidence_manifest = {
        "schema_version": "3.0",
        "artifacts": sorted(artifacts, key=lambda item: (item["path"], item["sha256"])),
    }
    (output / "manifest.json").write_bytes(canonical_json_bytes(evidence_manifest))
    (output / "ca_enrichment_manifest.json").write_bytes(manifest_bytes)

    total = len(manifest["actions"])
    accepted = len(accepted_actions)
    reference_ready = len(factor_ready_actions)
    return_ready = len(return_ready_actions)
    if errors:
        status = "BLOCKED"
    elif total == 0:
        status = "CA_ENRICHMENT_ZERO_RESULT_READY"
    elif accepted < total or pending_actions:
        status = "PARTIAL"
    elif reference_ready < total:
        status = "PARTIAL"
    elif return_ready < total:
        status = "CA_REFERENCE_FACTORS_READY_RETURN_POLICY_PENDING"
    else:
        status = "CA_ENRICHMENT_READY"
    report = {
        "schema_version": "1.0",
        "status": status,
        "run_id": manifest["run_id"],
        "output_root": str(output),
        "action_count": total,
        "accepted_action_count": accepted,
        "reference_factor_ready_count": reference_ready,
        "return_engine_ready_count": return_ready,
        "pending_actions": sorted(set(pending_actions)),
        "errors": sorted(set(errors)),
        "corporate_action_factor_ledger": str(factor_path),
        "corporate_action_return_policy_queue": str(policy_path),
        "remaining_gates": [
            "RETURN_POLICY_FOR_RIGHTS_AND_COMPLEX_ACTIONS",
            "HISTORICAL_STATUS_INTERVALS",
            "BENCHMARK_HISTORY",
            "OFFICIAL_COMPLETE_DAILY_EOD",
        ],
        "claim_boundaries": {
            "mechanical_factor_is_official_factor": False,
            "reference_price_factor_is_return_engine_multiplier": False,
            "reviewed_text_export_is_original_disclosure": False,
            "rights_terp_is_execution_receipt": False,
            "all_return_engine_policies_ready": total == return_ready,
            "data_foundation_ready": False,
            "backtest_ready": False,
            "forecast_generated": False,
            "recommendation_generated": False,
        },
    }
    report_path = report_output / "ca_enrichment_import_report.json"
    report_path.write_bytes(canonical_json_bytes(report))
    return report


__all__ = [
    "FACTOR_LEDGER_HEADERS",
    "RETURN_POLICY_QUEUE_HEADERS",
    "import_ca_enrichment",
]
