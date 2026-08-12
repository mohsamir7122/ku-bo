from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import hmac
import os
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .benchmark_registry import load_benchmark_registry
from .data_foundation_reconciliation import GATE_ORDER
from .foundation_io import (
    load_strict_json_object,
    nonnegative_int,
    prepare_output_root,
    require_real_directory,
    safe_regular_file,
    snapshot_regular_tree,
    strict_json_object,
)
from .hashing import canonical_json_bytes, hash_json, sha256_bytes
from .strict import parse_aware, parse_iso_date, require_sha256
from .tri_security_pilot import (
    TRI_SECURITY_ALLOWED_OUTPUT,
    TRI_SECURITY_BATCH_SIZE,
    TRI_SECURITY_CLAIM_BOUNDARY,
    TRI_SECURITY_MODE,
    load_tri_security_registry,
    verify_tri_security_scoped_config,
)


RUN_RECEIPT_SCHEMA_VERSION = "1.0"
STAGE_BINDING_SCHEMA_VERSION = "1.0"
RUN_RECEIPT_AUDIENCE = "kubo-tri-security-run"
STAGE_BINDING_AUDIENCE = "kubo-tri-security-stage"
RECEIPT_ALGORITHM = "HMAC-SHA256"
RUN_RECEIPT_FILE = "tri_security_run_receipt.json"
STAGE_BINDING_FILE = "tri_security_stage_binding.json"
RECEIPT_CLAIM_BOUNDARY = "AUTHENTICATED_BINDING_NOT_MARKET_EVIDENCE"
BENCHMARK_SCOPE_STATE = "CONFIGURED_SERIES_INCOMPATIBLE_WITH_TRI_COHORT"
MAX_RECEIPT_LIFETIME = timedelta(days=7)

STAGE_IDS = (
    "OFFICIAL_FOUNDATION",
    "STATUS_CORPORATE",
    "CA_ENRICHMENT",
    "STATUS_HISTORY",
    "RESEARCH_PRICE_HISTORY",
    "BENCHMARK_HISTORY",
    "OFFICIAL_EOD",
    "FINAL_DATA_FOUNDATION_RECONCILIATION",
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,254}$")
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_BATCH_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SECURITY_CODE_RE = re.compile(r"^[0-9]{1,12}$")
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,31}$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_KUWAIT = ZoneInfo("Asia/Kuwait")


class TriSecurityReceiptError(ValueError):
    """Raised when a run receipt or stage binding fails closed."""


def _exact_object(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise TriSecurityReceiptError(f"{field} has unknown or missing fields")
    return value


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not _IDENTIFIER_RE.fullmatch(value):
        raise TriSecurityReceiptError(f"{field} must be a canonical identifier")
    return value


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise TriSecurityReceiptError("receipt HMAC key must contain at least 32 bytes")
    return value


def _instant(value: Any, field: str) -> datetime:
    try:
        return parse_aware(value, field)
    except ValueError as exc:
        raise TriSecurityReceiptError(str(exc)) from exc


def _validity(issued_at: Any, expires_at: Any) -> tuple[datetime, datetime]:
    issued = _instant(issued_at, "issued_at")
    expires = _instant(expires_at, "expires_at")
    if issued >= expires:
        raise TriSecurityReceiptError("issued_at must precede expires_at")
    if expires - issued > MAX_RECEIPT_LIFETIME:
        raise TriSecurityReceiptError("receipt validity must not exceed seven days")
    return issued, expires


def _canonical_authentication_bytes(payload: Mapping[str, Any]) -> bytes:
    authentication = payload.get("authentication")
    if not isinstance(authentication, Mapping):
        raise TriSecurityReceiptError("authentication must be an object")
    authenticated = {
        "document": {
            key: value for key, value in payload.items() if key != "authentication"
        },
        "algorithm": authentication.get("algorithm"),
        "key_id": authentication.get("key_id"),
    }
    return canonical_json_bytes(authenticated)


def _sign(payload: dict[str, Any], *, key: bytes, key_id: str) -> dict[str, Any]:
    secret = _key(key)
    canonical_key_id = _identifier(key_id, "key_id")
    authentication = payload.get("authentication")
    if authentication != {
        "algorithm": RECEIPT_ALGORITHM,
        "key_id": canonical_key_id,
        "tag": "0" * 64,
    }:
        raise TriSecurityReceiptError("authentication signing template is invalid")
    authentication["tag"] = hmac.new(
        secret,
        _canonical_authentication_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    return payload


def _authenticate(
    payload: dict[str, Any],
    *,
    key: bytes,
    expected_key_id: str,
) -> str:
    secret = _key(key)
    expected = _identifier(expected_key_id, "expected_key_id")
    authentication = _exact_object(
        payload.get("authentication"),
        {"algorithm", "key_id", "tag"},
        "authentication",
    )
    if authentication["algorithm"] != RECEIPT_ALGORITHM:
        raise TriSecurityReceiptError("unsupported receipt authentication algorithm")
    key_id = _identifier(authentication["key_id"], "authentication.key_id")
    if key_id != expected:
        raise TriSecurityReceiptError("receipt authentication key_id mismatch")
    tag = authentication["tag"]
    if not isinstance(tag, str) or not re.fullmatch(r"[0-9a-f]{64}", tag):
        raise TriSecurityReceiptError("receipt authentication tag is invalid")
    calculated = hmac.new(
        secret,
        _canonical_authentication_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(calculated, tag):
        raise TriSecurityReceiptError("receipt authentication failed")
    return key_id


def _canonical_document(path: Path, *, field: str) -> tuple[dict[str, Any], bytes]:
    payload, content = load_strict_json_object(path, field=field)
    if content != canonical_json_bytes(payload):
        raise TriSecurityReceiptError(f"{field} must be canonical JSON")
    return payload, content


def _relative_path(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise TriSecurityReceiptError(f"{field} must be a canonical relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise TriSecurityReceiptError(f"{field} must remain inside its declared root")
    if path.as_posix() != value:
        raise TriSecurityReceiptError(f"{field} must be a canonical relative POSIX path")
    for component in path.parts:
        if (
            component != component.strip()
            or component.endswith((".", " "))
            or component.split(".", 1)[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{index}" for index in range(1, 10)),
                *(f"LPT{index}" for index in range(1, 10)),
            }
        ):
            raise TriSecurityReceiptError(
                f"{field} must be a canonical relative POSIX path"
            )
    return value


def _path_inside(candidate: Path, root: Path) -> bool:
    left = Path(os.path.abspath(candidate))
    right = Path(os.path.abspath(root))
    return left == right or right in left.parents


def _paths_overlap(left: Path, right: Path) -> bool:
    return _path_inside(left, right) or _path_inside(right, left)


def _require_external_path(path: Path, *, excluded_roots: tuple[Path, ...], field: str) -> Path:
    absolute = Path(os.path.abspath(path))
    if any(_paths_overlap(absolute, root) for root in excluded_roots):
        raise TriSecurityReceiptError(f"{field} must remain outside bound workspaces")
    return absolute


def _cohort(batch: Mapping[str, Any]) -> dict[str, Any]:
    raw = batch.get("securities")
    if not isinstance(raw, list) or len(raw) != TRI_SECURITY_BATCH_SIZE:
        raise TriSecurityReceiptError("run receipt cohort must contain exactly three securities")
    securities: list[dict[str, str]] = []
    seen: dict[str, set[str]] = {
        "security_code": set(),
        "ticker": set(),
        "isin": set(),
    }
    for index, value in enumerate(raw):
        row = _exact_object(
            value,
            {
                "security_code",
                "ticker",
                "name_en",
                "name_ar",
                "isin",
                "sector",
                "identity_state",
                "case_tags",
            },
            f"batch.securities[{index}]",
        )
        code = row["security_code"]
        ticker = row["ticker"]
        isin = row["isin"]
        sector = row["sector"]
        if not isinstance(code, str) or not _SECURITY_CODE_RE.fullmatch(code):
            raise TriSecurityReceiptError("cohort security_code is invalid")
        if not isinstance(ticker, str) or not _TICKER_RE.fullmatch(ticker):
            raise TriSecurityReceiptError("cohort ticker is invalid")
        if not isinstance(isin, str) or not _ISIN_RE.fullmatch(isin):
            raise TriSecurityReceiptError("cohort ISIN is invalid")
        if not isinstance(sector, str) or not sector.strip() or sector != sector.strip():
            raise TriSecurityReceiptError("cohort sector is invalid")
        if row["identity_state"] != "UNVERIFIED_SEED":
            raise TriSecurityReceiptError("receipt cannot promote seed identity")
        for field, item in (("security_code", code), ("ticker", ticker), ("isin", isin)):
            if item in seen[field]:
                raise TriSecurityReceiptError(f"cohort contains duplicate {field}")
            seen[field].add(item)
        securities.append(
            {
                "security_code": code,
                "ticker": ticker,
                "isin": isin,
                "sector": sector,
                "identity_state": "UNVERIFIED_SEED",
            }
        )
    digest_payload = {
        "security_count": TRI_SECURITY_BATCH_SIZE,
        "securities": securities,
    }
    return {
        **digest_payload,
        "cohort_sha256": hash_json(digest_payload),
    }


def _benchmark_scope(
    cohort: Mapping[str, Any],
    *,
    registry_id: str,
    registry_sha256: str,
    required_codes: list[str],
    configured_sectors: list[str],
) -> dict[str, Any]:
    securities = cohort["securities"]
    sectors = sorted({row["sector"] for row in securities})
    return {
        "scope_state": BENCHMARK_SCOPE_STATE,
        "comparison_scope": "NAMED_TRI_SECURITY_COHORT",
        "comparison_security_count": TRI_SECURITY_BATCH_SIZE,
        "comparison_security_codes": [row["security_code"] for row in securities],
        "comparison_sectors": sectors,
        "series_registry_id": registry_id,
        "series_registry_sha256": registry_sha256,
        "required_benchmark_codes": required_codes,
        "configured_sector_series": configured_sectors,
        "missing_cohort_sector_series": sorted(set(sectors) - set(configured_sectors)),
        "five_security_scope_allowed": False,
        "full_market_scope_allowed": False,
        "benchmark_qualification_allowed": False,
    }


def _workspace_report(
    root: Path,
    *,
    plan_sha256: str,
    manifest_sha256: str,
    run_id: str,
    batch_id: str,
    qualification_window: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    report_path = root / "reports" / "tri_security_workspace_report.json"
    report, content = _canonical_document(
        report_path,
        field="tri-security workspace report",
    )
    if report.get("run_id") != run_id or report.get("batch_id") != batch_id:
        raise TriSecurityReceiptError("workspace report run or batch mismatch")
    if report.get("batch_plan_path") != "plan/tri_security_batch_plan.json":
        raise TriSecurityReceiptError("workspace report batch plan path mismatch")
    if report.get("batch_plan_sha256") != plan_sha256:
        raise TriSecurityReceiptError("workspace report batch plan hash mismatch")
    if report.get("scoped_config_manifest_path") != "scoped_config/manifest.json":
        raise TriSecurityReceiptError("workspace report scoped manifest path mismatch")
    if report.get("scoped_config_manifest_sha256") != manifest_sha256:
        raise TriSecurityReceiptError("workspace report scoped manifest hash mismatch")
    expected_window = {
        "window_from": qualification_window["window_from"],
        "window_to": qualification_window["window_to"],
        "timezone": qualification_window["timezone"],
    }
    if report.get("qualification_window") != expected_window:
        raise TriSecurityReceiptError("workspace report qualification window mismatch")
    expected_fields = {
        "schema_version",
        "status",
        "readiness_status",
        "workspace_kind",
        "mode",
        "run_id",
        "batch_id",
        "batch_sequence",
        "batch_size",
        "qualification_window",
        "securities",
        "registry_id",
        "registry_sha256",
        "batch_sha256",
        "batch_plan_path",
        "batch_plan_sha256",
        "scoped_config_root",
        "scoped_config_manifest_path",
        "scoped_config_manifest_sha256",
        "checklist_path",
        "predecessor_batch_id",
        "predecessor_qualification_required",
        "required_gates",
        "gate_states",
        "remaining_external_blockers",
        "claim_boundaries",
    }
    _exact_object(report, expected_fields, "tri-security workspace report")
    if report["schema_version"] != "1.0" or report["status"] != "PASS":
        raise TriSecurityReceiptError("workspace report version or status mismatch")
    if report["workspace_kind"] != "TRI_SECURITY_DATA_QUALIFICATION":
        raise TriSecurityReceiptError("workspace report kind mismatch")
    if report["mode"] != TRI_SECURITY_MODE:
        raise TriSecurityReceiptError("workspace report mode mismatch")
    if report["batch_sequence"] != 1 or report["batch_size"] != 3:
        raise TriSecurityReceiptError("workspace report may authorize only batch one")
    if report["predecessor_batch_id"] is not None or report["predecessor_qualification_required"] is not False:
        raise TriSecurityReceiptError("workspace report predecessor fields mismatch")
    if report["required_gates"] != list(GATE_ORDER):
        raise TriSecurityReceiptError("workspace report gate order mismatch")
    if report["gate_states"] != ["PENDING_EXTERNAL_EVIDENCE" for _ in GATE_ORDER]:
        raise TriSecurityReceiptError("workspace report gate states self-promote")
    if report["claim_boundaries"] != {
        "workspace_contains_market_evidence": False,
        "seed_identity_is_official_evidence": False,
        "batch_passed_data_qualification": False,
        "three_security_batch_validates_full_market": False,
        "backtest_ready": False,
        "forecast_generated": False,
        "probability_generated": False,
        "recommendation_generated": False,
        "next_batch_authorized": False,
    }:
        raise TriSecurityReceiptError("workspace report claim boundaries were weakened")
    return content, report


@dataclass(frozen=True)
class TriSecurityWorkspaceContext:
    workspace_root: Path
    binding: dict[str, Any]


def load_tri_security_workspace_context(
    workspace_root: Path,
    *,
    expected_batch_plan_sha256: str,
    expected_scoped_config_manifest_sha256: str,
) -> TriSecurityWorkspaceContext:
    """Rehash one prepared workspace and derive its immutable run context."""

    root = require_real_directory(workspace_root, field="tri-security workspace")
    expected_plan = require_sha256(
        expected_batch_plan_sha256,
        "expected_batch_plan_sha256",
    )
    expected_manifest = require_sha256(
        expected_scoped_config_manifest_sha256,
        "expected_scoped_config_manifest_sha256",
    )
    plan_path = root / "plan" / "tri_security_batch_plan.json"
    plan, plan_bytes = _canonical_document(plan_path, field="tri-security batch plan")
    plan_sha256 = sha256_bytes(plan_bytes)
    if plan_sha256 != expected_plan:
        raise TriSecurityReceiptError("tri-security batch plan SHA-256 mismatch")
    _exact_object(
        plan,
        {
            "schema_version",
            "mode",
            "run_id",
            "prepared_by",
            "registry",
            "batch",
            "batch_sha256",
            "qualification_window",
            "scoped_configuration",
            "execution",
            "gates",
            "allowed_output",
            "claim_boundary",
        },
        "tri-security batch plan",
    )
    if plan["schema_version"] != "1.0" or plan["mode"] != TRI_SECURITY_MODE:
        raise TriSecurityReceiptError("tri-security batch plan version or mode mismatch")
    if plan["allowed_output"] != TRI_SECURITY_ALLOWED_OUTPUT:
        raise TriSecurityReceiptError("tri-security batch plan allowed_output mismatch")
    if plan["claim_boundary"] != TRI_SECURITY_CLAIM_BOUNDARY:
        raise TriSecurityReceiptError("tri-security batch plan claim boundary mismatch")
    run_id = plan["run_id"]
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise TriSecurityReceiptError("tri-security batch plan run_id is invalid")
    registry_row = _exact_object(
        plan["registry"],
        {"registry_id", "registry_sha256", "as_of"},
        "tri-security batch plan registry",
    )
    registry_sha256 = require_sha256(
        registry_row["registry_sha256"],
        "registry_sha256",
    )
    registry_as_of = parse_iso_date(registry_row["as_of"], "registry.as_of")
    batch = plan["batch"]
    if not isinstance(batch, dict):
        raise TriSecurityReceiptError("tri-security batch plan batch is invalid")
    batch_id = batch.get("batch_id")
    if not isinstance(batch_id, str) or not _BATCH_ID_RE.fullmatch(batch_id):
        raise TriSecurityReceiptError("tri-security batch plan batch_id is invalid")
    if plan["batch_sha256"] != hash_json(batch):
        raise TriSecurityReceiptError("tri-security batch payload SHA-256 mismatch")
    batch_sha256 = require_sha256(plan["batch_sha256"], "batch_sha256")
    cohort = _cohort(batch)

    window = _exact_object(
        plan["qualification_window"],
        {"window_from", "window_to", "timezone", "date_basis"},
        "qualification_window",
    )
    start = parse_iso_date(window["window_from"], "qualification_window.window_from")
    end = parse_iso_date(window["window_to"], "qualification_window.window_to")
    if start > end or start.year != end.year or end > registry_as_of:
        raise TriSecurityReceiptError("qualification window is invalid")
    if window["timezone"] != "Asia/Kuwait":
        raise TriSecurityReceiptError("qualification window timezone mismatch")
    if window["date_basis"] != "DECLARED_DATA_QUALIFICATION_WINDOW":
        raise TriSecurityReceiptError("qualification window date basis mismatch")

    scoped = _exact_object(
        plan["scoped_configuration"],
        {"root", "manifest_path", "manifest_sha256", "security_count"},
        "scoped_configuration",
    )
    if scoped != {
        "root": "scoped_config",
        "manifest_path": "scoped_config/manifest.json",
        "manifest_sha256": expected_manifest,
        "security_count": TRI_SECURITY_BATCH_SIZE,
    }:
        raise TriSecurityReceiptError("tri-security scoped configuration binding mismatch")
    manifest_path = root / "scoped_config" / "manifest.json"
    manifest, manifest_bytes = _canonical_document(
        manifest_path,
        field="tri-security scoped configuration manifest",
    )
    if sha256_bytes(manifest_bytes) != expected_manifest:
        raise TriSecurityReceiptError("tri-security scoped manifest SHA-256 mismatch")
    scoped_report = verify_tri_security_scoped_config(
        root / "scoped_config",
        expected_manifest_sha256=expected_manifest,
    )
    if scoped_report["batch_id"] != batch_id or scoped_report["security_count"] != 3:
        raise TriSecurityReceiptError("tri-security scoped cohort mismatch")
    registry = load_tri_security_registry(root / "scoped_config")
    if registry.sha256 != registry_sha256 or registry.registry_id != registry_row["registry_id"]:
        raise TriSecurityReceiptError("tri-security registry binding mismatch")
    if registry.as_of != registry_as_of.isoformat():
        raise TriSecurityReceiptError("tri-security registry as_of mismatch")
    if registry.batch(batch_id).to_dict() != batch:
        raise TriSecurityReceiptError("tri-security batch differs from scoped registry")
    if manifest.get("batch_id") != batch_id or manifest.get("batch_sha256") != batch_sha256:
        raise TriSecurityReceiptError("tri-security scoped manifest batch mismatch")

    execution = _exact_object(
        plan["execution"],
        {"sequence", "predecessor_batch_id", "predecessor_qualification_required"},
        "execution",
    )
    sequence = execution["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise TriSecurityReceiptError("tri-security batch sequence is invalid")
    if (
        sequence != 1
        or batch.get("sequence") != 1
        or batch_id != registry.execution_order[0]
        or execution["predecessor_batch_id"] is not None
        or execution["predecessor_qualification_required"] is not False
    ):
        raise TriSecurityReceiptError(
            "run receipts are locked to batch one until predecessor authority exists"
        )
    gates = plan["gates"]
    if not isinstance(gates, list) or [item.get("gate") if isinstance(item, dict) else None for item in gates] != list(GATE_ORDER):
        raise TriSecurityReceiptError("tri-security batch gate order mismatch")
    if any(
        not isinstance(item, dict)
        or set(item) != {"gate", "status", "required_evidence"}
        or item.get("status") != "PENDING_EXTERNAL_EVIDENCE"
        or not isinstance(item.get("required_evidence"), list)
        or not item["required_evidence"]
        for item in gates
    ):
        raise TriSecurityReceiptError("tri-security batch gate state cannot self-promote")

    report_bytes, report = _workspace_report(
        root,
        plan_sha256=plan_sha256,
        manifest_sha256=expected_manifest,
        run_id=run_id,
        batch_id=batch_id,
        qualification_window=window,
    )
    report_path = root / "reports" / "tri_security_workspace_report.json"
    expected_report_securities = [
        {
            "security_code": item["security_code"],
            "ticker": item["ticker"],
            "isin": item["isin"],
            "identity_state": "UNVERIFIED_SEED",
        }
        for item in batch["securities"]
    ]
    if (
        report["securities"] != expected_report_securities
        or report["registry_id"] != registry.registry_id
        or report["registry_sha256"] != registry_sha256
        or report["batch_sha256"] != batch_sha256
    ):
        raise TriSecurityReceiptError("workspace report cohort or registry mismatch")
    benchmark_registry = load_benchmark_registry(root / "scoped_config")
    required_benchmark_codes = sorted(benchmark_registry.required_codes)
    configured_sector_series = sorted(
        {
            item.sector
            for item in benchmark_registry.benchmarks
            if item.required_for_pilot and item.market_scope == "SECTOR"
        }
    )
    benchmark_scope = _benchmark_scope(
        cohort,
        registry_id=benchmark_registry.registry_id,
        registry_sha256=benchmark_registry.sha256,
        required_codes=required_benchmark_codes,
        configured_sectors=configured_sector_series,
    )
    if not benchmark_scope["missing_cohort_sector_series"]:
        raise TriSecurityReceiptError(
            "expected scoped Benchmark registry incompatibility was not preserved"
        )
    binding = {
        "workspace_kind": "TRI_SECURITY_DATA_QUALIFICATION",
        "run_id": run_id,
        "batch_id": batch_id,
        "batch_sequence": sequence,
        "registry_id": registry.registry_id,
        "registry_sha256": registry_sha256,
        "batch_sha256": batch_sha256,
        "batch_plan": {
            "path": "plan/tri_security_batch_plan.json",
            "sha256": plan_sha256,
            "size_bytes": len(plan_bytes),
        },
        "scoped_configuration": {
            "manifest_path": "scoped_config/manifest.json",
            "manifest_sha256": expected_manifest,
            "manifest_size_bytes": len(manifest_bytes),
        },
        "workspace_report": {
            "path": "reports/tri_security_workspace_report.json",
            "sha256": sha256_bytes(report_bytes),
            "size_bytes": len(report_bytes),
        },
        "qualification_window": {
            "window_from": start.isoformat(),
            "window_to": end.isoformat(),
            "timezone": "Asia/Kuwait",
            "date_basis": "DECLARED_DATA_QUALIFICATION_WINDOW",
        },
        "cohort": cohort,
        "benchmark_scope": benchmark_scope,
    }
    if safe_regular_file(plan_path, field="tri-security batch plan") != plan_bytes:
        raise TriSecurityReceiptError("tri-security batch plan changed during validation")
    if safe_regular_file(manifest_path, field="tri-security scoped manifest") != manifest_bytes:
        raise TriSecurityReceiptError("tri-security scoped manifest changed during validation")
    if safe_regular_file(report_path, field="tri-security workspace report") != report_bytes:
        raise TriSecurityReceiptError("tri-security workspace report changed during validation")
    verify_tri_security_scoped_config(
        root / "scoped_config",
        expected_manifest_sha256=expected_manifest,
    )
    return TriSecurityWorkspaceContext(workspace_root=root, binding=binding)


def _run_claim_boundaries() -> dict[str, bool]:
    return {
        "receipt_is_market_evidence": False,
        "receipt_proves_data_qualification": False,
        "receipt_authorizes_next_batch": False,
        "three_security_cohort": True,
        "five_security_claim_allowed": False,
        "full_market_claim_allowed": False,
        "backtest_ready": False,
        "forecast_allowed": False,
    }


def build_tri_security_run_receipt(
    *,
    workspace_root: Path,
    expected_batch_plan_sha256: str,
    expected_scoped_config_manifest_sha256: str,
    receipt_id: str,
    issuer_id: str,
    issued_at: str,
    expires_at: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any]:
    context = load_tri_security_workspace_context(
        workspace_root,
        expected_batch_plan_sha256=expected_batch_plan_sha256,
        expected_scoped_config_manifest_sha256=expected_scoped_config_manifest_sha256,
    )
    issued, expires = _validity(issued_at, expires_at)
    payload = {
        "schema_version": RUN_RECEIPT_SCHEMA_VERSION,
        "audience": RUN_RECEIPT_AUDIENCE,
        "receipt_id": _identifier(receipt_id, "receipt_id"),
        "issuer_id": _identifier(issuer_id, "issuer_id"),
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
        "run_date": issued.astimezone(_KUWAIT).date().isoformat(),
        "binding": context.binding,
        "claim_boundary": RECEIPT_CLAIM_BOUNDARY,
        "claim_boundaries": _run_claim_boundaries(),
        "authentication": {
            "algorithm": RECEIPT_ALGORITHM,
            "key_id": _identifier(key_id, "key_id"),
            "tag": "0" * 64,
        },
    }
    return _sign(payload, key=key, key_id=key_id)


def issue_tri_security_run_receipt(
    *,
    workspace_root: Path,
    output_root: Path,
    expected_batch_plan_sha256: str,
    expected_scoped_config_manifest_sha256: str,
    receipt_id: str,
    issuer_id: str,
    issued_at: str,
    expires_at: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any]:
    output_path = _require_external_path(
        output_root,
        excluded_roots=(workspace_root,),
        field="run receipt output",
    )
    payload = build_tri_security_run_receipt(
        workspace_root=workspace_root,
        expected_batch_plan_sha256=expected_batch_plan_sha256,
        expected_scoped_config_manifest_sha256=expected_scoped_config_manifest_sha256,
        receipt_id=receipt_id,
        issuer_id=issuer_id,
        issued_at=issued_at,
        expires_at=expires_at,
        key=key,
        key_id=key_id,
    )
    root = prepare_output_root(output_path, label="tri-security run receipt output")
    content = canonical_json_bytes(payload)
    with (root / RUN_RECEIPT_FILE).open("xb") as handle:
        handle.write(content)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "receipt_state": "AUTHENTICATED_RUN_RECEIPT_ISSUED",
        "receipt_path": RUN_RECEIPT_FILE,
        "receipt_sha256": sha256_bytes(content),
        "receipt_id": payload["receipt_id"],
        "run_id": payload["binding"]["run_id"],
        "batch_id": payload["binding"]["batch_id"],
        "run_date": payload["run_date"],
        "expires_at": payload["expires_at"],
        "authenticated_key_id": payload["authentication"]["key_id"],
        "claim_boundary": RECEIPT_CLAIM_BOUNDARY,
        "claim_boundaries": payload["claim_boundaries"],
    }


@dataclass(frozen=True)
class VerifiedTriSecurityRunReceipt:
    payload: Mapping[str, Any]
    receipt_sha256: str
    content_sha256: str
    authenticated_key_id: str
    workspace_root: Path
    key_fingerprint: str = ""

    @property
    def binding(self) -> dict[str, Any]:
        return dict(self.payload["binding"])

    def report(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "status": "PASS",
            "verification_state": "AUTHENTICATED_RUN_BINDING_VALID",
            "receipt_id": self.payload["receipt_id"],
            "issuer_id": self.payload["issuer_id"],
            "receipt_sha256": self.receipt_sha256,
            "content_sha256": self.content_sha256,
            "authenticated_key_id": self.authenticated_key_id,
            "run_id": self.binding["run_id"],
            "batch_id": self.binding["batch_id"],
            "batch_sequence": self.binding["batch_sequence"],
            "run_date": self.payload["run_date"],
            "qualification_window": self.binding["qualification_window"],
            "cohort_sha256": self.binding["cohort"]["cohort_sha256"],
            "security_count": self.binding["cohort"]["security_count"],
            "batch_plan_sha256": self.binding["batch_plan"]["sha256"],
            "scoped_config_manifest_sha256": self.binding["scoped_configuration"]["manifest_sha256"],
            "benchmark_scope": self.binding["benchmark_scope"],
            "expires_at": self.payload["expires_at"],
            "claim_boundary": self.payload["claim_boundary"],
            "claim_boundaries": self.payload["claim_boundaries"],
        }


def _validate_run_receipt_structure(payload: dict[str, Any]) -> None:
    _exact_object(
        payload,
        {
            "schema_version",
            "audience",
            "receipt_id",
            "issuer_id",
            "issued_at",
            "expires_at",
            "run_date",
            "binding",
            "claim_boundary",
            "claim_boundaries",
            "authentication",
        },
        "run receipt",
    )
    if payload["schema_version"] != RUN_RECEIPT_SCHEMA_VERSION:
        raise TriSecurityReceiptError("unsupported run receipt schema_version")
    if payload["audience"] != RUN_RECEIPT_AUDIENCE:
        raise TriSecurityReceiptError("run receipt audience mismatch")
    _identifier(payload["receipt_id"], "receipt_id")
    _identifier(payload["issuer_id"], "issuer_id")
    issued, _ = _validity(payload["issued_at"], payload["expires_at"])
    if payload["run_date"] != issued.astimezone(_KUWAIT).date().isoformat():
        raise TriSecurityReceiptError("run receipt run_date is not the dynamic Kuwait issue date")
    if payload["claim_boundary"] != RECEIPT_CLAIM_BOUNDARY:
        raise TriSecurityReceiptError("run receipt claim boundary mismatch")
    if payload["claim_boundaries"] != _run_claim_boundaries():
        raise TriSecurityReceiptError("run receipt claim boundaries were weakened")
    binding = payload["binding"]
    if not isinstance(binding, dict):
        raise TriSecurityReceiptError("run receipt binding is invalid")
    cohort = binding.get("cohort")
    if not isinstance(cohort, dict) or cohort.get("security_count") != 3:
        raise TriSecurityReceiptError("run receipt cohort is not exactly three securities")
    digest_payload = {
        "security_count": cohort.get("security_count"),
        "securities": cohort.get("securities"),
    }
    if cohort.get("cohort_sha256") != hash_json(digest_payload):
        raise TriSecurityReceiptError("run receipt cohort SHA-256 mismatch")
    benchmark = binding.get("benchmark_scope")
    if not isinstance(benchmark, dict):
        raise TriSecurityReceiptError("run receipt Benchmark scope is invalid")
    if benchmark.get("scope_state") != BENCHMARK_SCOPE_STATE:
        raise TriSecurityReceiptError("run receipt Benchmark incompatibility was hidden")
    if benchmark.get("comparison_scope") != "NAMED_TRI_SECURITY_COHORT":
        raise TriSecurityReceiptError("run receipt Benchmark comparison scope mismatch")
    if benchmark.get("comparison_security_count") != 3:
        raise TriSecurityReceiptError("run receipt Benchmark denominator mismatch")
    if benchmark.get("comparison_security_codes") != [
        item["security_code"] for item in cohort["securities"]
    ]:
        raise TriSecurityReceiptError("run receipt Benchmark cohort mismatch")
    if (
        benchmark.get("five_security_scope_allowed") is not False
        or benchmark.get("full_market_scope_allowed") is not False
        or benchmark.get("benchmark_qualification_allowed") is not False
        or not benchmark.get("missing_cohort_sector_series")
    ):
        raise TriSecurityReceiptError("run receipt Benchmark claim was promoted")


def verify_tri_security_run_receipt(
    *,
    receipt_path: Path,
    workspace_root: Path,
    expected_batch_plan_sha256: str,
    expected_scoped_config_manifest_sha256: str,
    decision_at: str,
    key: bytes,
    expected_key_id: str,
    expected_run_id: str | None = None,
    expected_batch_id: str | None = None,
) -> VerifiedTriSecurityRunReceipt:
    path = _require_external_path(
        receipt_path,
        excluded_roots=(workspace_root,),
        field="run receipt",
    )
    payload, content = _canonical_document(path, field="tri-security run receipt")
    _validate_run_receipt_structure(payload)
    authenticated_key_id = _authenticate(
        payload,
        key=key,
        expected_key_id=expected_key_id,
    )
    issued, expires = _validity(payload["issued_at"], payload["expires_at"])
    decision = _instant(decision_at, "decision_at")
    if not issued <= decision < expires:
        raise TriSecurityReceiptError("run receipt is not valid at decision_at")
    context = load_tri_security_workspace_context(
        workspace_root,
        expected_batch_plan_sha256=expected_batch_plan_sha256,
        expected_scoped_config_manifest_sha256=expected_scoped_config_manifest_sha256,
    )
    if payload["binding"] != context.binding:
        raise TriSecurityReceiptError("run receipt differs from the current workspace binding")
    if expected_run_id is not None and payload["binding"]["run_id"] != expected_run_id:
        raise TriSecurityReceiptError("run receipt expected_run_id mismatch")
    if expected_batch_id is not None and payload["binding"]["batch_id"] != expected_batch_id:
        raise TriSecurityReceiptError("run receipt expected_batch_id mismatch")
    unsigned = {key: value for key, value in payload.items() if key != "authentication"}
    return VerifiedTriSecurityRunReceipt(
        payload=MappingProxyType(payload),
        receipt_sha256=sha256_bytes(content),
        content_sha256=sha256_bytes(canonical_json_bytes(unsigned)),
        authenticated_key_id=authenticated_key_id,
        workspace_root=context.workspace_root,
        key_fingerprint=sha256_bytes(_key(key)),
    )


@dataclass(frozen=True)
class VerifiedTriSecurityStageSnapshot:
    verification_report: Mapping[str, Any]
    files: Mapping[str, bytes]

    def report(self) -> dict[str, Any]:
        return dict(self.verification_report)


def _stage_manifest_inventory(
    stage_root: Path,
) -> tuple[dict[str, Any], Mapping[str, bytes]]:
    snapshot = snapshot_regular_tree(stage_root, field="stage output root")
    by_path = snapshot.by_path()
    manifest_snapshot = by_path.get("manifest.json")
    if manifest_snapshot is None:
        raise TriSecurityReceiptError("stage output lacks manifest.json")
    manifest = strict_json_object(
        manifest_snapshot.content,
        "stage evidence manifest",
    )
    content = manifest_snapshot.content
    if content != canonical_json_bytes(manifest):
        raise TriSecurityReceiptError("stage evidence manifest must be canonical JSON")
    if set(manifest) != {"schema_version", "artifacts"} or manifest["schema_version"] != "3.0":
        raise TriSecurityReceiptError("stage evidence manifest contract is invalid")
    rows = manifest["artifacts"]
    if not isinstance(rows, list):
        raise TriSecurityReceiptError("stage evidence manifest artifacts must be a list")
    inventory: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise TriSecurityReceiptError(f"stage artifact {index} must be an object")
        if not {"path", "sha256", "size_bytes"}.issubset(row):
            raise TriSecurityReceiptError(f"stage artifact {index} lacks byte binding")
        relative = _relative_path(row["path"], field=f"stage artifact {index} path")
        if relative in seen:
            raise TriSecurityReceiptError("stage evidence manifest contains duplicate paths")
        seen.add(relative)
        digest = require_sha256(row["sha256"], f"stage artifact {index} sha256")
        size = nonnegative_int(row["size_bytes"], f"stage artifact {index} size_bytes")
        artifact = by_path.get(relative)
        if artifact is None:
            raise TriSecurityReceiptError(f"stage artifact is missing: {relative}")
        if artifact.size_bytes != size or artifact.sha256 != digest:
            raise TriSecurityReceiptError(f"stage artifact changed or mismatched: {relative}")
        inventory.append({"path": relative, "sha256": digest, "size_bytes": size})
    normalized = sorted(inventory, key=lambda item: item["path"])
    complete = snapshot.inventory()
    result = {
        "manifest_path": "manifest.json",
        "manifest_sha256": sha256_bytes(content),
        "manifest_size_bytes": len(content),
        "declared_artifact_count": len(normalized),
        "declared_artifact_inventory_sha256": hash_json(normalized),
        "complete_file_count": len(complete),
        "complete_size_bytes": sum(item["size_bytes"] for item in complete),
        "complete_inventory_sha256": hash_json(complete),
    }
    return result, MappingProxyType(
        {path: item.content for path, item in by_path.items()}
    )


def _stage_claim_boundaries() -> dict[str, bool]:
    return {
        "binding_is_market_evidence": False,
        "binding_proves_data_qualification": False,
        "binding_authorizes_next_batch": False,
        "binding_proves_stage_matches_run_scope": False,
        "five_security_claim_allowed": False,
        "full_market_claim_allowed": False,
        "backtest_ready": False,
        "forecast_allowed": False,
    }


def build_tri_security_stage_binding(
    *,
    verified_receipt: VerifiedTriSecurityRunReceipt,
    stage_root: Path,
    expected_stage_manifest_sha256: str,
    binding_id: str,
    stage_id: str,
    bound_at: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any]:
    if stage_id not in STAGE_IDS:
        raise TriSecurityReceiptError("unsupported tri-security stage_id")
    if _identifier(key_id, "key_id") == verified_receipt.authenticated_key_id:
        raise TriSecurityReceiptError("run and stage HMAC key IDs must be independent")
    if not verified_receipt.key_fingerprint:
        raise TriSecurityReceiptError("verified run receipt lacks key-domain binding")
    if hmac.compare_digest(sha256_bytes(_key(key)), verified_receipt.key_fingerprint):
        raise TriSecurityReceiptError("run and stage HMAC keys must be independent")
    bound = _instant(bound_at, "bound_at")
    issued, expires = _validity(
        verified_receipt.payload["issued_at"],
        verified_receipt.payload["expires_at"],
    )
    if not issued <= bound < expires:
        raise TriSecurityReceiptError("stage binding time is outside the run receipt validity")
    inventory, _ = _stage_manifest_inventory(stage_root)
    expected_manifest = require_sha256(
        expected_stage_manifest_sha256,
        "expected_stage_manifest_sha256",
    )
    if inventory["manifest_sha256"] != expected_manifest:
        raise TriSecurityReceiptError("stage manifest SHA-256 mismatch")
    payload = {
        "schema_version": STAGE_BINDING_SCHEMA_VERSION,
        "audience": STAGE_BINDING_AUDIENCE,
        "binding_id": _identifier(binding_id, "binding_id"),
        "stage_id": stage_id,
        "bound_at": bound.isoformat(),
        "expires_at": expires.isoformat(),
        "run_date": verified_receipt.payload["run_date"],
        "run_receipt": {
            "receipt_id": verified_receipt.payload["receipt_id"],
            "receipt_sha256": verified_receipt.receipt_sha256,
            "content_sha256": verified_receipt.content_sha256,
            "issuer_id": verified_receipt.payload["issuer_id"],
            "authenticated_run_key_id": verified_receipt.authenticated_key_id,
        },
        "run_binding": verified_receipt.binding,
        "stage_artifact": inventory,
        "claim_boundary": RECEIPT_CLAIM_BOUNDARY,
        "claim_boundaries": _stage_claim_boundaries(),
        "authentication": {
            "algorithm": RECEIPT_ALGORITHM,
            "key_id": _identifier(key_id, "key_id"),
            "tag": "0" * 64,
        },
    }
    return _sign(payload, key=key, key_id=key_id)


def issue_tri_security_stage_binding(
    *,
    verified_receipt: VerifiedTriSecurityRunReceipt,
    workspace_root: Path,
    stage_root: Path,
    output_root: Path,
    expected_stage_manifest_sha256: str,
    binding_id: str,
    stage_id: str,
    bound_at: str,
    key: bytes,
    key_id: str,
) -> dict[str, Any]:
    workspace = require_real_directory(
        workspace_root,
        field="tri-security workspace",
    )
    if workspace != verified_receipt.workspace_root:
        raise TriSecurityReceiptError(
            "stage binding workspace differs from the verified run receipt"
        )
    if _paths_overlap(stage_root, workspace):
        raise TriSecurityReceiptError("stage output must remain outside the prepared workspace")
    output_path = _require_external_path(
        output_root,
        excluded_roots=(workspace, stage_root),
        field="stage binding output",
    )
    payload = build_tri_security_stage_binding(
        verified_receipt=verified_receipt,
        stage_root=stage_root,
        expected_stage_manifest_sha256=expected_stage_manifest_sha256,
        binding_id=binding_id,
        stage_id=stage_id,
        bound_at=bound_at,
        key=key,
        key_id=key_id,
    )
    root = prepare_output_root(output_path, label="tri-security stage binding output")
    content = canonical_json_bytes(payload)
    with (root / STAGE_BINDING_FILE).open("xb") as handle:
        handle.write(content)
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "binding_state": "AUTHENTICATED_STAGE_BINDING_ISSUED",
        "binding_path": STAGE_BINDING_FILE,
        "binding_sha256": sha256_bytes(content),
        "binding_id": payload["binding_id"],
        "stage_id": payload["stage_id"],
        "run_id": payload["run_binding"]["run_id"],
        "batch_id": payload["run_binding"]["batch_id"],
        "run_date": payload["run_date"],
        "stage_manifest_sha256": payload["stage_artifact"]["manifest_sha256"],
        "authenticated_key_id": payload["authentication"]["key_id"],
        "claim_boundary": RECEIPT_CLAIM_BOUNDARY,
        "claim_boundaries": payload["claim_boundaries"],
    }


def _validate_stage_binding_structure(payload: dict[str, Any]) -> None:
    _exact_object(
        payload,
        {
            "schema_version",
            "audience",
            "binding_id",
            "stage_id",
            "bound_at",
            "expires_at",
            "run_date",
            "run_receipt",
            "run_binding",
            "stage_artifact",
            "claim_boundary",
            "claim_boundaries",
            "authentication",
        },
        "stage binding",
    )
    if payload["schema_version"] != STAGE_BINDING_SCHEMA_VERSION:
        raise TriSecurityReceiptError("unsupported stage binding schema_version")
    if payload["audience"] != STAGE_BINDING_AUDIENCE:
        raise TriSecurityReceiptError("stage binding audience mismatch")
    _identifier(payload["binding_id"], "binding_id")
    if payload["stage_id"] not in STAGE_IDS:
        raise TriSecurityReceiptError("unsupported tri-security stage_id")
    _instant(payload["bound_at"], "bound_at")
    _instant(payload["expires_at"], "expires_at")
    if payload["claim_boundary"] != RECEIPT_CLAIM_BOUNDARY:
        raise TriSecurityReceiptError("stage binding claim boundary mismatch")
    if payload["claim_boundaries"] != _stage_claim_boundaries():
        raise TriSecurityReceiptError("stage binding claim boundaries were weakened")


def verify_tri_security_stage_binding(
    *,
    binding_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    stage_root: Path,
    expected_batch_plan_sha256: str,
    expected_scoped_config_manifest_sha256: str,
    expected_stage_manifest_sha256: str,
    decision_at: str,
    key: bytes,
    expected_key_id: str,
    receipt_key: bytes,
    expected_receipt_key_id: str,
    expected_stage_id: str,
    expected_run_id: str | None = None,
    expected_batch_id: str | None = None,
) -> VerifiedTriSecurityStageSnapshot:
    if hmac.compare_digest(_key(key), _key(receipt_key)):
        raise TriSecurityReceiptError("run and stage HMAC keys must be independent")
    if _identifier(expected_key_id, "expected_key_id") == _identifier(
        expected_receipt_key_id,
        "expected_receipt_key_id",
    ):
        raise TriSecurityReceiptError("run and stage HMAC key IDs must be independent")
    if _paths_overlap(stage_root, workspace_root):
        raise TriSecurityReceiptError("stage output must remain outside the prepared workspace")
    path = _require_external_path(
        binding_path,
        excluded_roots=(workspace_root, stage_root),
        field="stage binding",
    )
    receipt = verify_tri_security_run_receipt(
        receipt_path=receipt_path,
        workspace_root=workspace_root,
        expected_batch_plan_sha256=expected_batch_plan_sha256,
        expected_scoped_config_manifest_sha256=expected_scoped_config_manifest_sha256,
        decision_at=decision_at,
        key=receipt_key,
        expected_key_id=expected_receipt_key_id,
        expected_run_id=expected_run_id,
        expected_batch_id=expected_batch_id,
    )
    payload, content = _canonical_document(
        path,
        field="tri-security stage binding",
    )
    _validate_stage_binding_structure(payload)
    authenticated_key_id = _authenticate(
        payload,
        key=key,
        expected_key_id=expected_key_id,
    )
    decision = _instant(decision_at, "decision_at")
    bound = _instant(payload["bound_at"], "bound_at")
    expires = _instant(payload["expires_at"], "expires_at")
    receipt_issued = _instant(receipt.payload["issued_at"], "issued_at")
    if not receipt_issued <= bound <= decision < expires:
        raise TriSecurityReceiptError("stage binding is not valid at decision_at")
    if payload["expires_at"] != receipt.payload["expires_at"]:
        raise TriSecurityReceiptError("stage binding validity differs from run receipt")
    if payload["run_date"] != receipt.payload["run_date"]:
        raise TriSecurityReceiptError("stage binding dynamic run_date mismatch")
    if payload["stage_id"] != expected_stage_id:
        raise TriSecurityReceiptError("stage binding expected_stage_id mismatch")
    expected_receipt = {
        "receipt_id": receipt.payload["receipt_id"],
        "receipt_sha256": receipt.receipt_sha256,
        "content_sha256": receipt.content_sha256,
        "issuer_id": receipt.payload["issuer_id"],
        "authenticated_run_key_id": receipt.authenticated_key_id,
    }
    if payload["run_receipt"] != expected_receipt or payload["run_binding"] != receipt.binding:
        raise TriSecurityReceiptError("stage binding mixes a different run receipt or cohort")
    current_inventory, verified_files = _stage_manifest_inventory(stage_root)
    expected_manifest = require_sha256(
        expected_stage_manifest_sha256,
        "expected_stage_manifest_sha256",
    )
    if current_inventory["manifest_sha256"] != expected_manifest:
        raise TriSecurityReceiptError("stage manifest SHA-256 mismatch")
    if payload["stage_artifact"] != current_inventory:
        raise TriSecurityReceiptError("stage artifacts changed after binding")
    report = {
        "schema_version": "1.0",
        "status": "PASS",
        "verification_state": "AUTHENTICATED_STAGE_BINDING_VALID",
        "binding_id": payload["binding_id"],
        "binding_sha256": sha256_bytes(content),
        "stage_id": payload["stage_id"],
        "run_id": receipt.binding["run_id"],
        "batch_id": receipt.binding["batch_id"],
        "run_date": payload["run_date"],
        "cohort_sha256": receipt.binding["cohort"]["cohort_sha256"],
        "stage_manifest_sha256": current_inventory["manifest_sha256"],
        "declared_artifact_inventory_sha256": current_inventory[
            "declared_artifact_inventory_sha256"
        ],
        "complete_inventory_sha256": current_inventory["complete_inventory_sha256"],
        "authenticated_run_key_id": receipt.authenticated_key_id,
        "authenticated_stage_key_id": authenticated_key_id,
        "claim_boundary": RECEIPT_CLAIM_BOUNDARY,
        "claim_boundaries": payload["claim_boundaries"],
    }
    return VerifiedTriSecurityStageSnapshot(
        verification_report=MappingProxyType(report),
        files=verified_files,
    )


__all__ = [
    "MAX_RECEIPT_LIFETIME",
    "RECEIPT_ALGORITHM",
    "RECEIPT_CLAIM_BOUNDARY",
    "RUN_RECEIPT_AUDIENCE",
    "RUN_RECEIPT_FILE",
    "RUN_RECEIPT_SCHEMA_VERSION",
    "STAGE_BINDING_AUDIENCE",
    "STAGE_BINDING_FILE",
    "STAGE_BINDING_SCHEMA_VERSION",
    "STAGE_IDS",
    "TriSecurityReceiptError",
    "TriSecurityWorkspaceContext",
    "VerifiedTriSecurityRunReceipt",
    "VerifiedTriSecurityStageSnapshot",
    "build_tri_security_run_receipt",
    "build_tri_security_stage_binding",
    "issue_tri_security_run_receipt",
    "issue_tri_security_stage_binding",
    "load_tri_security_workspace_context",
    "verify_tri_security_run_receipt",
    "verify_tri_security_stage_binding",
]
