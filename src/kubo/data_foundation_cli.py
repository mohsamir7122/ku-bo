from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import json
import os
from pathlib import Path
from typing import Any

from .benchmark_import import import_benchmark_history
from .benchmark_registry import load_benchmark_registry
from .benchmark_workspace import prepare_benchmark_workspace
from .ca_adjustments import formula_self_check
from .ca_enrichment_import import import_ca_enrichment
from .ca_enrichment_workspace import prepare_ca_enrichment_workspace
from .data_foundation_reconciliation import (
    build_data_foundation_packet,
    print_data_foundation_gate_report,
)
from .foundation_io import load_strict_json_object, require_real_directory
from .official_eod_import import (
    import_official_daily_eod,
    validate_official_eod_output,
)
from .official_eod_workspace import prepare_official_eod_workspace
from .official_foundation_import import import_official_foundation
from .official_foundation_workspace import prepare_official_foundation_workspace
from .price_collection_workspace import prepare_price_collection_workspace
from .research_price_history import read_research_price_history
from .runtime_trust import RuntimeTrustRegistry, load_runtime_trust_registry
from .status_corporate_import import import_status_corporate
from .status_corporate_workspace import prepare_status_corporate_workspace
from .status_history_import import import_status_history
from .status_history_workspace import prepare_status_history_workspace
from .tri_security_pilot import (
    load_tri_security_registry,
    load_tri_security_vendor_mappings,
    prepare_tri_security_batch_workspace,
    verify_tri_security_scoped_config,
)
from .tri_security_admission import (
    BOUNDARY_STAGE_MAP,
    BoundaryAdmissionRequest,
    build_boundary_operation_binding,
    issue_semantic_boundary_admission,
)
from .tri_security_receipts import (
    STAGE_IDS,
    issue_tri_security_run_receipt,
    issue_tri_security_stage_binding,
    verify_tri_security_run_receipt,
    verify_tri_security_stage_binding,
)
from .user_price_export import import_investing_user_exports
from .exit_status import is_blocking_status
from .vendor_symbol_mapping import (
    PilotIdentitySeedCatalog,
    VendorSymbolMappingCatalog,
)


BLOCKING_STATUSES = frozenset(
    {
        "BLOCKED",
        "PARTIAL",
        "BLOCKED_OFFICIAL_IDENTITY",
        "FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED",
        "DATA_FOUNDATION_PARTIAL",
        "DATA_FOUNDATION_BLOCKED",
        "FAIL",
    }
)

TRI_SECURITY_RECEIPT_COMMANDS = frozenset(
    {
        "issue-tri-security-run-receipt",
        "verify-tri-security-run-receipt",
        "issue-tri-security-stage-binding",
        "verify-tri-security-stage-binding",
        "issue-tri-security-semantic-admission",
    }
)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_hashes(path: Path | None) -> frozenset[str] | None:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest must be UTF-8 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("artifacts"), list):
        raise ValueError("manifest must contain an artifacts list")
    hashes: set[str] = set()
    for index, row in enumerate(payload["artifacts"]):
        if not isinstance(row, dict) or not isinstance(row.get("sha256"), str):
            raise ValueError(f"manifest artifact {index} lacks sha256")
        hashes.add(row["sha256"])
    return frozenset(hashes)


def _runtime_trust_hmac_key() -> bytes:
    value = os.environ.get("KUBO_RUNTIME_TRUST_HMAC_KEY", "")
    if not value:
        raise ValueError(
            "KUBO_RUNTIME_TRUST_HMAC_KEY is required with --runtime-trust-registry"
        )
    try:
        if value.startswith("hex:"):
            return bytes.fromhex(value[4:])
        if value.startswith("base64:"):
            return base64.b64decode(value[7:], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(
            "KUBO_RUNTIME_TRUST_HMAC_KEY is not valid encoded bytes"
        ) from exc
    raise ValueError("KUBO_RUNTIME_TRUST_HMAC_KEY must start with hex: or base64:")


def _runtime_encoded_hmac_key(variable: str) -> bytes:
    value = os.environ.get(variable, "")
    if not value:
        raise ValueError(f"{variable} is required")
    if value.startswith("hex:"):
        encoded = value[4:]
        decoder = bytes.fromhex
    elif value.startswith("base64:"):
        encoded = value[7:]
        decoder = lambda item: base64.b64decode(item, validate=True)
    else:
        raise ValueError(f"{variable} must start with hex: or base64:")
    try:
        key = decoder(encoded)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(f"{variable} is not valid encoded bytes") from exc
    if len(key) < 32:
        raise ValueError(f"{variable} must decode to at least 32 bytes")
    return key


def _runtime_hmac_key_id(variable: str) -> str:
    key_id = os.environ.get(variable, "").strip()
    if not key_id:
        raise ValueError(f"{variable} is required")
    return key_id


def _runtime_tri_run_hmac() -> tuple[bytes, str]:
    return (
        _runtime_encoded_hmac_key("KUBO_TRI_RUN_HMAC_KEY"),
        _runtime_hmac_key_id("KUBO_TRI_RUN_HMAC_KEY_ID"),
    )


def _runtime_tri_stage_hmac() -> tuple[bytes, str]:
    return (
        _runtime_encoded_hmac_key("KUBO_TRI_STAGE_HMAC_KEY"),
        _runtime_hmac_key_id("KUBO_TRI_STAGE_HMAC_KEY_ID"),
    )


def _runtime_tri_semantic_hmac() -> tuple[bytes, str]:
    return (
        _runtime_encoded_hmac_key("KUBO_TRI_SEMANTIC_HMAC_KEY"),
        _runtime_hmac_key_id("KUBO_TRI_SEMANTIC_HMAC_KEY_ID"),
    )


def _runtime_independent_tri_hmacs() -> tuple[bytes, str, bytes, str]:
    run_key, run_key_id = _runtime_tri_run_hmac()
    stage_key, stage_key_id = _runtime_tri_stage_hmac()
    if run_key_id == stage_key_id:
        raise ValueError("tri-security run and stage HMAC key IDs must be independent")
    if hmac.compare_digest(run_key, stage_key):
        raise ValueError("tri-security run and stage HMAC keys must be independent")
    return run_key, run_key_id, stage_key, stage_key_id


def _runtime_independent_tri_admission_hmacs() -> tuple[
    bytes,
    str,
    bytes,
    str,
    bytes,
    str,
]:
    run_key, run_key_id, stage_key, stage_key_id = (
        _runtime_independent_tri_hmacs()
    )
    semantic_key, semantic_key_id = _runtime_tri_semantic_hmac()
    if semantic_key_id in {run_key_id, stage_key_id}:
        raise ValueError(
            "tri-security run, stage, and semantic HMAC key IDs must be independent"
        )
    if hmac.compare_digest(semantic_key, run_key) or hmac.compare_digest(
        semantic_key, stage_key
    ):
        raise ValueError(
            "tri-security run, stage, and semantic HMAC keys must be independent"
        )
    return (
        run_key,
        run_key_id,
        stage_key,
        stage_key_id,
        semantic_key,
        semantic_key_id,
    )


def _parse_boundary_inputs(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        role, separator, raw_path = value.partition("=")
        if (
            separator != "="
            or not role
            or role != role.strip()
            or not raw_path
            or raw_path != raw_path.strip()
        ):
            raise ValueError("--boundary-input must use canonical ROLE=PATH syntax")
        if role in result:
            raise ValueError(f"duplicate --boundary-input role: {role}")
        result[role] = Path(raw_path)
    return result


def _add_boundary_admission_arguments(
    command: argparse.ArgumentParser,
    *,
    add_decision_at: bool = True,
) -> None:
    command.add_argument("--admission-path", type=Path, required=True)
    # Admission, rather than argparse, owns the stable fail-closed identity for
    # missing authorities.  Keeping these options optional at syntax level
    # lets CLI, direct-API, and serialized ingestion report the same structured
    # RUN_RECEIPT_REQUIRED/STAGE_BINDING_REQUIRED contract before any write.
    command.add_argument("--receipt-path", type=Path)
    command.add_argument("--stage-binding-path", type=Path)
    command.add_argument("--workspace-root", type=Path, required=True)
    command.add_argument("--input-root", type=Path, required=True)
    command.add_argument("--expected-batch-plan-sha256", required=True)
    command.add_argument(
        "--expected-scoped-config-manifest-sha256",
        required=True,
    )
    command.add_argument("--expected-stage-manifest-sha256", required=True)
    if add_decision_at:
        command.add_argument("--decision-at", required=True)
    command.add_argument("--expected-run-id", required=True)
    command.add_argument("--expected-batch-id", required=True)
    command.add_argument(
        "--predecessor-admission",
        dest="predecessor_admission_paths",
        action="append",
        type=Path,
        default=[],
        help="Repeat once for each exact semantic predecessor admission.",
    )


def _boundary_admission_request(
    args: argparse.Namespace,
    *,
    boundary_inputs: dict[str, Path],
    operation_binding: dict[str, Any],
) -> BoundaryAdmissionRequest:
    (
        run_key,
        run_key_id,
        stage_key,
        stage_key_id,
        semantic_key,
        semantic_key_id,
    ) = _runtime_independent_tri_admission_hmacs()
    return BoundaryAdmissionRequest(
        admission_path=args.admission_path,
        receipt_path=args.receipt_path,
        stage_binding_path=args.stage_binding_path,
        workspace_root=args.workspace_root,
        input_root=args.input_root,
        expected_batch_plan_sha256=args.expected_batch_plan_sha256,
        expected_scoped_config_manifest_sha256=(
            args.expected_scoped_config_manifest_sha256
        ),
        expected_stage_manifest_sha256=args.expected_stage_manifest_sha256,
        decision_at=args.decision_at,
        expected_run_id=args.expected_run_id,
        expected_batch_id=args.expected_batch_id,
        run_key=run_key,
        run_key_id=run_key_id,
        v1_stage_key=stage_key,
        v1_stage_key_id=stage_key_id,
        semantic_key=semantic_key,
        semantic_key_id=semantic_key_id,
        boundary_inputs=boundary_inputs,
        operation_binding=operation_binding,
        predecessor_admission_paths=tuple(args.predecessor_admission_paths),
    )


def _command_operation_binding(
    args: argparse.Namespace,
    boundary_id: str,
    *,
    runtime_trust_registry: RuntimeTrustRegistry | None = None,
) -> dict[str, Any]:
    return build_boundary_operation_binding(
        boundary_id,
        decision_at=args.decision_at,
        observed_at=getattr(args, "observed_at", None),
        imported_at=getattr(args, "imported_at", None),
        run_id=getattr(args, "run_id", None),
        runtime_trust_registry=runtime_trust_registry,
    )


def _load_eod_runtime_trust_registry(
    registry_path: Path | None,
    *,
    workspace_root: Path,
    output_root: Path,
    decision_at: str,
) -> RuntimeTrustRegistry | None:
    if registry_path is None:
        return None
    resolved_registry = registry_path.resolve()
    for packet_root in (workspace_root.resolve(), output_root.resolve()):
        if resolved_registry == packet_root or packet_root in resolved_registry.parents:
            raise ValueError(
                "runtime trust registry must remain outside EOD workspaces and outputs"
            )
    key_id = os.environ.get("KUBO_RUNTIME_TRUST_HMAC_KEY_ID", "").strip()
    if not key_id:
        raise ValueError(
            "KUBO_RUNTIME_TRUST_HMAC_KEY_ID is required with --runtime-trust-registry"
        )
    return load_runtime_trust_registry(
        resolved_registry,
        key=_runtime_trust_hmac_key(),
        expected_key_id=key_id,
        decision_at=decision_at,
    )


def _report_is_blocking(report: dict[str, Any]) -> bool:
    """Honor independent validation results, not only a saved stage status."""

    if "status" not in report:
        return True
    return any(
        is_blocking_status(report.get(field), known=BLOCKING_STATUSES)
        for field in ("status", "validation_status", "contract_status")
        if field == "status" or field in report
    )


def _sanitized_receipt_report(value: Any) -> Any:
    """Remove authentication material and absolute paths from CLI output."""

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for field, item in value.items():
            if field in {"authentication", "key", "tag"}:
                continue
            if field.endswith("_path") and isinstance(item, str):
                path = Path(item)
                sanitized[field] = path.name if path.is_absolute() else item
            else:
                sanitized[field] = _sanitized_receipt_report(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitized_receipt_report(item) for item in value]
    if isinstance(value, str):
        path = Path(value)
        return path.name if path.is_absolute() else value
    return value


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=(
            "KU-BO Data Foundation Pilot — auditable price, identity, calendar, "
            "status history, and corporate-action evidence without forecasts"
        )
    )
    value.add_argument(
        "--project-root",
        type=Path,
        default=_root(),
        help="KU-BO checkout containing config/pilot",
    )
    value.add_argument(
        "--pilot-config-dir",
        type=Path,
        help=(
            "Optional scoped configuration directory containing pilot/. "
            "Use the tri-security workspace scoped_config directory to keep "
            "identity and price denominators at exactly three securities."
        ),
    )
    value.add_argument(
        "--expected-pilot-config-manifest-sha256",
        help=(
            "Required with --pilot-config-dir: expected SHA-256 for the scoped "
            "tri-security manifest."
        ),
    )
    sub = value.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-pilot-config")
    sub.add_parser("validate-tri-security-pilot")
    sub.add_parser("validate-ca-formulas")

    prepare_tri = sub.add_parser("prepare-tri-security-batch")
    prepare_tri.add_argument("--output-root", type=Path, required=True)
    prepare_tri.add_argument("--batch-id", required=True)
    prepare_tri.add_argument("--run-id", required=True)
    prepare_tri.add_argument("--window-from", required=True)
    prepare_tri.add_argument("--window-to", required=True)
    prepare_tri.add_argument("--prepared-by", default="")

    prepare = sub.add_parser("prepare-price-collection")
    prepare.add_argument("--output-root", type=Path, required=True)
    prepare.add_argument("--source-name", default="investing")
    prepare.add_argument("--downloaded-by", default="")
    prepare.add_argument(
        "--expected-scope",
        choices=("mapped", "all_market"),
        default="mapped",
    )
    prepare.add_argument("--drive-folder-url", default="")

    import_exports = sub.add_parser("import-user-price-exports")
    import_exports.add_argument("--input-dir", type=Path, required=True)
    import_exports.add_argument("--output-root", type=Path, required=True)
    import_exports.add_argument("--observed-at", required=True)
    import_exports.add_argument("--decision-at", required=True)
    _add_boundary_admission_arguments(import_exports, add_decision_at=False)

    validate_history = sub.add_parser("validate-research-price-history")
    validate_history.add_argument("--path", type=Path, required=True)
    validate_history.add_argument("--manifest", type=Path)

    prepare_official = sub.add_parser("prepare-official-foundation")
    prepare_official.add_argument("--output-root", type=Path, required=True)
    prepare_official.add_argument("--run-id", required=True)
    prepare_official.add_argument("--calendar-year", type=int, default=2026)
    prepare_official.add_argument("--prepared-by", default="")

    import_official = sub.add_parser("import-official-foundation")
    import_official.add_argument("--workspace", type=Path, required=True)
    import_official.add_argument("--output-root", type=Path, required=True)
    _add_boundary_admission_arguments(import_official)

    prepare_status = sub.add_parser("prepare-status-corporate")
    prepare_status.add_argument("--output-root", type=Path, required=True)
    prepare_status.add_argument("--run-id", required=True)
    prepare_status.add_argument("--action-window-from", required=True)
    prepare_status.add_argument("--action-window-to", required=True)
    prepare_status.add_argument("--prepared-by", default="")

    import_status = sub.add_parser("import-status-corporate")
    import_status.add_argument("--workspace", type=Path, required=True)
    import_status.add_argument(
        "--official-foundation-root",
        type=Path,
        required=True,
    )
    import_status.add_argument("--output-root", type=Path, required=True)
    _add_boundary_admission_arguments(import_status)

    prepare_ca = sub.add_parser("prepare-ca-enrichment")
    prepare_ca.add_argument(
        "--status-corporate-root",
        type=Path,
        required=True,
    )
    prepare_ca.add_argument("--output-root", type=Path, required=True)
    prepare_ca.add_argument("--run-id", required=True)
    prepare_ca.add_argument("--prepared-by", default="")

    import_ca = sub.add_parser("import-ca-enrichment")
    import_ca.add_argument(
        "--status-corporate-root",
        type=Path,
        required=True,
    )
    import_ca.add_argument("--workspace", type=Path, required=True)
    import_ca.add_argument("--output-root", type=Path, required=True)
    _add_boundary_admission_arguments(import_ca)

    prepare_history = sub.add_parser("prepare-status-history")
    prepare_history.add_argument(
        "--status-corporate-root",
        type=Path,
        required=True,
    )
    prepare_history.add_argument("--output-root", type=Path, required=True)
    prepare_history.add_argument("--run-id", required=True)
    prepare_history.add_argument("--history-window-from", required=True)
    prepare_history.add_argument("--history-window-to", required=True)
    prepare_history.add_argument("--prepared-by", default="")

    import_history = sub.add_parser("import-status-history")
    import_history.add_argument(
        "--status-corporate-root",
        type=Path,
        required=True,
    )
    import_history.add_argument("--workspace", type=Path, required=True)
    import_history.add_argument("--output-root", type=Path, required=True)
    _add_boundary_admission_arguments(import_history)

    sub.add_parser("validate-benchmark-registry")

    prepare_benchmark = sub.add_parser("prepare-benchmark-history")
    prepare_benchmark.add_argument(
        "--official-foundation-root", type=Path, required=True
    )
    prepare_benchmark.add_argument("--output-root", type=Path, required=True)
    prepare_benchmark.add_argument("--run-id", required=True)
    prepare_benchmark.add_argument("--window-from", required=True)
    prepare_benchmark.add_argument("--window-to", required=True)
    prepare_benchmark.add_argument("--prepared-by", default="")

    import_benchmark = sub.add_parser("import-benchmark-history")
    import_benchmark.add_argument(
        "--official-foundation-root", type=Path, required=True
    )
    import_benchmark.add_argument("--workspace", type=Path, required=True)
    import_benchmark.add_argument("--output-root", type=Path, required=True)
    import_benchmark.add_argument("--imported-at", required=True)
    _add_boundary_admission_arguments(import_benchmark)

    prepare_eod = sub.add_parser("prepare-official-eod")
    prepare_eod.add_argument("--official-foundation-root", type=Path, required=True)
    prepare_eod.add_argument("--status-history-root", type=Path, required=True)
    prepare_eod.add_argument("--output-root", type=Path, required=True)
    prepare_eod.add_argument("--run-id", required=True)
    prepare_eod.add_argument("--window-from", required=True)
    prepare_eod.add_argument("--window-to", required=True)
    prepare_eod.add_argument("--prepared-by", default="")

    import_eod = sub.add_parser("import-official-eod")
    import_eod.add_argument("--workspace", type=Path, required=True)
    import_eod.add_argument("--official-foundation-root", type=Path, required=True)
    import_eod.add_argument("--status-history-root", type=Path, required=True)
    import_eod.add_argument("--output-root", type=Path, required=True)
    import_eod.add_argument("--run-id", required=True)
    import_eod.add_argument("--imported-at", required=True)
    import_eod.add_argument("--runtime-trust-registry", type=Path)
    _add_boundary_admission_arguments(import_eod)

    validate_eod = sub.add_parser("validate-official-eod")
    validate_eod.add_argument("--official-eod-root", type=Path, required=True)
    validate_eod.add_argument(
        "--official-foundation-root", type=Path, required=True
    )
    validate_eod.add_argument("--status-history-root", type=Path, required=True)
    validate_eod.add_argument("--runtime-trust-registry", type=Path)

    build_packet = sub.add_parser("build-data-foundation-packet")
    build_packet.add_argument("--official-foundation-root", type=Path, required=True)
    build_packet.add_argument("--status-history-root", type=Path, required=True)
    build_packet.add_argument("--ca-enrichment-root", type=Path, required=True)
    build_packet.add_argument(
        "--research-price-history-root", type=Path, required=True
    )
    build_packet.add_argument("--benchmark-root", type=Path, required=True)
    build_packet.add_argument("--official-eod-root", type=Path, required=True)
    build_packet.add_argument("--output-root", type=Path, required=True)
    build_packet.add_argument("--outcome-session-policy", type=Path)
    _add_boundary_admission_arguments(build_packet)

    print_report = sub.add_parser("print-data-foundation-gate-report")
    print_report.add_argument("--path", type=Path, required=True)

    issue_run_receipt = sub.add_parser(
        "issue-tri-security-run-receipt",
        help=(
            "Issue an external authenticated receipt for one prepared "
            "tri-security batch workspace"
        ),
        description=(
            "Requires runtime-only KUBO_TRI_RUN_HMAC_KEY and "
            "KUBO_TRI_RUN_HMAC_KEY_ID environment variables."
        ),
    )
    issue_run_receipt.add_argument(
        "--workspace-root",
        "--workspace",
        dest="workspace_root",
        type=Path,
        required=True,
    )
    issue_run_receipt.add_argument("--output-root", type=Path, required=True)
    issue_run_receipt.add_argument("--expected-batch-plan-sha256", required=True)
    issue_run_receipt.add_argument(
        "--expected-scoped-config-manifest-sha256", required=True
    )
    issue_run_receipt.add_argument("--receipt-id", required=True)
    issue_run_receipt.add_argument("--issuer-id", required=True)
    issue_run_receipt.add_argument("--issued-at", required=True)
    issue_run_receipt.add_argument("--expires-at", required=True)

    verify_run_receipt = sub.add_parser(
        "verify-tri-security-run-receipt",
        help=(
            "Authenticate an external run receipt and revalidate its exact "
            "tri-security workspace binding"
        ),
        description=(
            "Requires runtime-only KUBO_TRI_RUN_HMAC_KEY and "
            "KUBO_TRI_RUN_HMAC_KEY_ID environment variables."
        ),
    )
    verify_run_receipt.add_argument(
        "--receipt-path",
        "--receipt",
        dest="receipt_path",
        type=Path,
        required=True,
    )
    verify_run_receipt.add_argument(
        "--workspace-root",
        "--workspace",
        dest="workspace_root",
        type=Path,
        required=True,
    )
    verify_run_receipt.add_argument("--expected-batch-plan-sha256", required=True)
    verify_run_receipt.add_argument(
        "--expected-scoped-config-manifest-sha256", required=True
    )
    verify_run_receipt.add_argument("--decision-at", required=True)
    verify_run_receipt.add_argument("--expected-run-id", required=True)
    verify_run_receipt.add_argument("--expected-batch-id", required=True)

    issue_stage_binding = sub.add_parser(
        "issue-tri-security-stage-binding",
        help=(
            "Bind an immutable stage artifact manifest to an independently "
            "authenticated tri-security run receipt"
        ),
        description=(
            "Requires independent runtime-only KUBO_TRI_RUN_HMAC_KEY, "
            "KUBO_TRI_RUN_HMAC_KEY_ID, KUBO_TRI_STAGE_HMAC_KEY, and "
            "KUBO_TRI_STAGE_HMAC_KEY_ID credentials."
        ),
    )
    issue_stage_binding.add_argument(
        "--receipt-path",
        "--receipt",
        dest="receipt_path",
        type=Path,
        required=True,
    )
    issue_stage_binding.add_argument(
        "--workspace-root",
        "--workspace",
        dest="workspace_root",
        type=Path,
        required=True,
    )
    issue_stage_binding.add_argument("--stage-root", type=Path, required=True)
    issue_stage_binding.add_argument("--output-root", type=Path, required=True)
    issue_stage_binding.add_argument("--expected-batch-plan-sha256", required=True)
    issue_stage_binding.add_argument(
        "--expected-scoped-config-manifest-sha256", required=True
    )
    issue_stage_binding.add_argument("--expected-stage-manifest-sha256", required=True)
    issue_stage_binding.add_argument("--expected-run-id", required=True)
    issue_stage_binding.add_argument("--expected-batch-id", required=True)
    issue_stage_binding.add_argument("--binding-id", required=True)
    issue_stage_binding.add_argument("--stage-id", choices=STAGE_IDS, required=True)
    issue_stage_binding.add_argument("--bound-at", required=True)

    verify_stage_binding = sub.add_parser(
        "verify-tri-security-stage-binding",
        help=(
            "Authenticate independent run and stage credentials and revalidate "
            "the current stage artifacts"
        ),
        description=(
            "Requires independent runtime-only KUBO_TRI_RUN_HMAC_KEY, "
            "KUBO_TRI_RUN_HMAC_KEY_ID, KUBO_TRI_STAGE_HMAC_KEY, and "
            "KUBO_TRI_STAGE_HMAC_KEY_ID credentials."
        ),
    )
    verify_stage_binding.add_argument(
        "--binding-path",
        "--binding",
        dest="binding_path",
        type=Path,
        required=True,
    )
    verify_stage_binding.add_argument(
        "--receipt-path",
        "--receipt",
        dest="receipt_path",
        type=Path,
        required=True,
    )
    verify_stage_binding.add_argument(
        "--workspace-root",
        "--workspace",
        dest="workspace_root",
        type=Path,
        required=True,
    )
    verify_stage_binding.add_argument("--stage-root", type=Path, required=True)
    verify_stage_binding.add_argument("--expected-batch-plan-sha256", required=True)
    verify_stage_binding.add_argument(
        "--expected-scoped-config-manifest-sha256", required=True
    )
    verify_stage_binding.add_argument("--expected-stage-manifest-sha256", required=True)
    verify_stage_binding.add_argument("--decision-at", required=True)
    verify_stage_binding.add_argument(
        "--expected-stage-id", choices=STAGE_IDS, required=True
    )
    verify_stage_binding.add_argument("--expected-run-id", required=True)
    verify_stage_binding.add_argument("--expected-batch-id", required=True)

    issue_semantic_admission = sub.add_parser(
        "issue-tri-security-semantic-admission",
        help=(
            "Issue an authenticated semantic admission for one exact production "
            "boundary and predecessor set"
        ),
        description=(
            "Requires independent runtime-only run, stage, and semantic HMAC "
            "keys and key IDs. Repeat --boundary-input ROLE=PATH for the exact "
            "boundary input map."
        ),
    )
    issue_semantic_admission.add_argument(
        "--boundary-id",
        choices=tuple(sorted(BOUNDARY_STAGE_MAP)),
        required=True,
    )
    issue_semantic_admission.add_argument("--receipt-path", type=Path, required=True)
    issue_semantic_admission.add_argument(
        "--stage-binding-path", type=Path, required=True
    )
    issue_semantic_admission.add_argument(
        "--workspace-root", type=Path, required=True
    )
    issue_semantic_admission.add_argument("--input-root", type=Path, required=True)
    issue_semantic_admission.add_argument("--output-path", type=Path, required=True)
    issue_semantic_admission.add_argument(
        "--expected-batch-plan-sha256", required=True
    )
    issue_semantic_admission.add_argument(
        "--expected-scoped-config-manifest-sha256", required=True
    )
    issue_semantic_admission.add_argument(
        "--expected-stage-manifest-sha256", required=True
    )
    issue_semantic_admission.add_argument("--expected-run-id", required=True)
    issue_semantic_admission.add_argument("--expected-batch-id", required=True)
    issue_semantic_admission.add_argument("--admission-id", required=True)
    issue_semantic_admission.add_argument("--issued-at", required=True)
    issue_semantic_admission.add_argument("--operation-decision-at", required=True)
    issue_semantic_admission.add_argument("--operation-observed-at")
    issue_semantic_admission.add_argument("--operation-imported-at")
    issue_semantic_admission.add_argument("--operation-run-id")
    issue_semantic_admission.add_argument(
        "--operation-runtime-trust-registry",
        type=Path,
    )
    issue_semantic_admission.add_argument(
        "--boundary-input",
        dest="boundary_inputs",
        action="append",
        required=True,
        metavar="ROLE=PATH",
    )
    issue_semantic_admission.add_argument(
        "--predecessor-admission",
        dest="predecessor_admission_paths",
        action="append",
        type=Path,
        default=[],
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project_root = args.project_root.resolve()
    receipt_command = args.command in TRI_SECURITY_RECEIPT_COMMANDS
    scoped_config_report = None
    if receipt_command:
        if (
            args.pilot_config_dir is not None
            or args.expected_pilot_config_manifest_sha256 is not None
        ):
            raise ValueError(
                "receipt commands derive scoped configuration only from the "
                "prepared workspace; omit global --pilot-config-dir options"
            )
        config_dir = project_root / "config"
    else:
        config_dir = (
            require_real_directory(
                args.pilot_config_dir,
                field="pilot_config_dir",
            )
            if args.pilot_config_dir is not None
            else project_root / "config"
        )
        if args.pilot_config_dir is not None:
            if args.expected_pilot_config_manifest_sha256 is None:
                raise ValueError(
                    "--pilot-config-dir requires "
                    "--expected-pilot-config-manifest-sha256 to anchor the scoped "
                    "configuration outside its self-authored manifest"
                )
            scoped_config_report = verify_tri_security_scoped_config(
                config_dir,
                expected_manifest_sha256=args.expected_pilot_config_manifest_sha256,
            )
        elif args.expected_pilot_config_manifest_sha256 is not None:
            raise ValueError(
                "--expected-pilot-config-manifest-sha256 requires --pilot-config-dir"
            )
        if not (config_dir / "pilot" / "security_master_seed.json").is_file():
            raise SystemExit(
                "invalid KU-BO project root: "
                "config/pilot/security_master_seed.json is missing"
            )

    report: dict[str, Any]
    if args.command == "issue-tri-security-run-receipt":
        run_key, run_key_id = _runtime_tri_run_hmac()
        report = issue_tri_security_run_receipt(
            workspace_root=args.workspace_root,
            output_root=args.output_root,
            expected_batch_plan_sha256=args.expected_batch_plan_sha256,
            expected_scoped_config_manifest_sha256=(
                args.expected_scoped_config_manifest_sha256
            ),
            receipt_id=args.receipt_id,
            issuer_id=args.issuer_id,
            issued_at=args.issued_at,
            expires_at=args.expires_at,
            key=run_key,
            key_id=run_key_id,
        )
        report = _sanitized_receipt_report(report)
    elif args.command == "verify-tri-security-run-receipt":
        run_key, run_key_id = _runtime_tri_run_hmac()
        verified_receipt = verify_tri_security_run_receipt(
            receipt_path=args.receipt_path,
            workspace_root=args.workspace_root,
            expected_batch_plan_sha256=args.expected_batch_plan_sha256,
            expected_scoped_config_manifest_sha256=(
                args.expected_scoped_config_manifest_sha256
            ),
            decision_at=args.decision_at,
            key=run_key,
            expected_key_id=run_key_id,
            expected_run_id=args.expected_run_id,
            expected_batch_id=args.expected_batch_id,
        )
        report = _sanitized_receipt_report(verified_receipt.report())
    elif args.command == "issue-tri-security-stage-binding":
        run_key, run_key_id, stage_key, stage_key_id = (
            _runtime_independent_tri_hmacs()
        )
        verified_receipt = verify_tri_security_run_receipt(
            receipt_path=args.receipt_path,
            workspace_root=args.workspace_root,
            expected_batch_plan_sha256=args.expected_batch_plan_sha256,
            expected_scoped_config_manifest_sha256=(
                args.expected_scoped_config_manifest_sha256
            ),
            decision_at=args.bound_at,
            key=run_key,
            expected_key_id=run_key_id,
            expected_run_id=args.expected_run_id,
            expected_batch_id=args.expected_batch_id,
        )
        report = issue_tri_security_stage_binding(
            verified_receipt=verified_receipt,
            workspace_root=args.workspace_root,
            stage_root=args.stage_root,
            output_root=args.output_root,
            expected_stage_manifest_sha256=args.expected_stage_manifest_sha256,
            binding_id=args.binding_id,
            stage_id=args.stage_id,
            bound_at=args.bound_at,
            key=stage_key,
            key_id=stage_key_id,
        )
        report = _sanitized_receipt_report(report)
    elif args.command == "verify-tri-security-stage-binding":
        run_key, run_key_id, stage_key, stage_key_id = (
            _runtime_independent_tri_hmacs()
        )
        verified_stage = verify_tri_security_stage_binding(
            binding_path=args.binding_path,
            receipt_path=args.receipt_path,
            workspace_root=args.workspace_root,
            stage_root=args.stage_root,
            expected_batch_plan_sha256=args.expected_batch_plan_sha256,
            expected_scoped_config_manifest_sha256=(
                args.expected_scoped_config_manifest_sha256
            ),
            expected_stage_manifest_sha256=args.expected_stage_manifest_sha256,
            decision_at=args.decision_at,
            key=stage_key,
            expected_key_id=stage_key_id,
            receipt_key=run_key,
            expected_receipt_key_id=run_key_id,
            expected_stage_id=args.expected_stage_id,
            expected_run_id=args.expected_run_id,
            expected_batch_id=args.expected_batch_id,
        )
        report = verified_stage.report()
        report = _sanitized_receipt_report(report)
    elif args.command == "issue-tri-security-semantic-admission":
        (
            run_key,
            run_key_id,
            stage_key,
            stage_key_id,
            semantic_key,
            semantic_key_id,
        ) = _runtime_independent_tri_admission_hmacs()
        verified_receipt = verify_tri_security_run_receipt(
            receipt_path=args.receipt_path,
            workspace_root=args.workspace_root,
            expected_batch_plan_sha256=args.expected_batch_plan_sha256,
            expected_scoped_config_manifest_sha256=(
                args.expected_scoped_config_manifest_sha256
            ),
            decision_at=args.issued_at,
            key=run_key,
            expected_key_id=run_key_id,
            expected_run_id=args.expected_run_id,
            expected_batch_id=args.expected_batch_id,
        )
        verified_stage = verify_tri_security_stage_binding(
            binding_path=args.stage_binding_path,
            receipt_path=args.receipt_path,
            workspace_root=args.workspace_root,
            stage_root=args.input_root,
            expected_batch_plan_sha256=args.expected_batch_plan_sha256,
            expected_scoped_config_manifest_sha256=(
                args.expected_scoped_config_manifest_sha256
            ),
            expected_stage_manifest_sha256=args.expected_stage_manifest_sha256,
            decision_at=args.issued_at,
            key=stage_key,
            expected_key_id=stage_key_id,
            receipt_key=run_key,
            expected_receipt_key_id=run_key_id,
            expected_stage_id=BOUNDARY_STAGE_MAP[args.boundary_id],
            expected_run_id=args.expected_run_id,
            expected_batch_id=args.expected_batch_id,
        )
        stage_report = verified_stage.report()
        parsed_boundary_inputs = _parse_boundary_inputs(args.boundary_inputs)
        operation_registry = None
        if args.operation_runtime_trust_registry is not None:
            if args.boundary_id != "import_official_eod":
                raise ValueError(
                    "--operation-runtime-trust-registry is valid only for import_official_eod"
                )
            eod_workspace = parsed_boundary_inputs.get("workspace_root")
            if eod_workspace is None:
                raise ValueError(
                    "import_official_eod operation requires boundary input workspace_root"
                )
            if args.operation_imported_at is None:
                raise ValueError(
                    "--operation-imported-at is required with runtime trust registry"
                )
            operation_registry = _load_eod_runtime_trust_registry(
                args.operation_runtime_trust_registry,
                workspace_root=eod_workspace,
                output_root=args.output_path,
                decision_at=args.operation_imported_at,
            )
        operation_binding = build_boundary_operation_binding(
            args.boundary_id,
            decision_at=args.operation_decision_at,
            observed_at=args.operation_observed_at,
            imported_at=args.operation_imported_at,
            run_id=args.operation_run_id,
            runtime_trust_registry=operation_registry,
        )
        report = issue_semantic_boundary_admission(
            output_path=args.output_path,
            boundary_id=args.boundary_id,
            verified_receipt=verified_receipt,
            v1_stage_report=stage_report,
            v1_stage_binding_sha256=stage_report["binding_sha256"],
            input_root=args.input_root,
            boundary_inputs=parsed_boundary_inputs,
            operation_binding=operation_binding,
            predecessor_admission_paths=tuple(args.predecessor_admission_paths),
            admission_id=args.admission_id,
            issued_at=args.issued_at,
            key=semantic_key,
            key_id=semantic_key_id,
        )
        report = _sanitized_receipt_report(report)
    elif args.command == "validate-pilot-config":
        identities = PilotIdentitySeedCatalog(config_dir)
        mappings = VendorSymbolMappingCatalog(config_dir, identities)
        report = {
            "status": "PASS",
            "identity_seed": identities.report(),
            "vendor_mappings": mappings.report(),
            "claim_boundaries": {
                "seed_identity_is_official_evidence": False,
                "vendor_mapping_is_official_identity": False,
                "forecast_generated": False,
                "backtest_ready": False,
            },
        }
    elif args.command == "validate-tri-security-pilot":
        registry = load_tri_security_registry(config_dir)
        mappings = load_tri_security_vendor_mappings(config_dir, registry)
        report = registry.report()
        report["vendor_mappings"] = {
            "status": "PASS",
            "schema_version": "1.0",
            "mapping_count": len(mappings.mappings),
            "mappings_sha256": mappings.sha256,
            "claim_boundary": "VENDOR_MAPPING_IS_NOT_OFFICIAL_SECURITY_IDENTITY",
        }
    elif args.command == "prepare-tri-security-batch":
        report = prepare_tri_security_batch_workspace(
            config_dir=config_dir,
            output_root=args.output_root,
            batch_id=args.batch_id,
            run_id=args.run_id,
            window_from=args.window_from,
            window_to=args.window_to,
            prepared_by=args.prepared_by,
        )
    elif args.command == "validate-ca-formulas":
        report = formula_self_check()
    elif args.command == "prepare-price-collection":
        report = prepare_price_collection_workspace(
            config_dir=config_dir,
            output_root=args.output_root,
            source_name=args.source_name,
            downloaded_by=args.downloaded_by,
            expected_scope=args.expected_scope,
            drive_folder_url=args.drive_folder_url,
        )
    elif args.command == "import-user-price-exports":
        admission_request = _boundary_admission_request(
            args,
            boundary_inputs={
                "config_dir": config_dir,
                "input_dir": args.input_dir,
            },
            operation_binding=_command_operation_binding(
                args,
                "import_user_price_exports",
            ),
        )
        report = import_investing_user_exports(
            config_dir=config_dir,
            input_dir=args.input_dir,
            output_root=args.output_root,
            observed_at=args.observed_at,
            decision_at=args.decision_at,
            admission_request=admission_request,
        )
    elif args.command == "validate-research-price-history":
        _, validation = read_research_price_history(
            args.path,
            manifest_hashes=_manifest_hashes(args.manifest),
        )
        report = validation.to_dict()
    elif args.command == "prepare-official-foundation":
        report = prepare_official_foundation_workspace(
            output_root=args.output_root,
            run_id=args.run_id,
            calendar_year=args.calendar_year,
            prepared_by=args.prepared_by,
        )
    elif args.command == "import-official-foundation":
        admission_request = _boundary_admission_request(
            args,
            boundary_inputs={
                "config_dir": config_dir,
                "workspace": args.workspace,
            },
            operation_binding=_command_operation_binding(
                args,
                "import_official_foundation",
            ),
        )
        report = import_official_foundation(
            config_dir=config_dir,
            workspace=args.workspace,
            output_root=args.output_root,
            admission_request=admission_request,
        )
    elif args.command == "prepare-status-corporate":
        report = prepare_status_corporate_workspace(
            output_root=args.output_root,
            run_id=args.run_id,
            action_window_from=args.action_window_from,
            action_window_to=args.action_window_to,
            prepared_by=args.prepared_by,
        )
    elif args.command == "import-status-corporate":
        admission_request = _boundary_admission_request(
            args,
            boundary_inputs={
                "official_foundation_root": args.official_foundation_root,
                "workspace": args.workspace,
            },
            operation_binding=_command_operation_binding(
                args,
                "import_status_corporate",
            ),
        )
        report = import_status_corporate(
            config_dir=config_dir,
            official_foundation_root=args.official_foundation_root,
            workspace=args.workspace,
            output_root=args.output_root,
            admission_request=admission_request,
        )
    elif args.command == "prepare-ca-enrichment":
        report = prepare_ca_enrichment_workspace(
            status_corporate_root=args.status_corporate_root,
            output_root=args.output_root,
            run_id=args.run_id,
            prepared_by=args.prepared_by,
        )
    elif args.command == "import-ca-enrichment":
        admission_request = _boundary_admission_request(
            args,
            boundary_inputs={
                "status_corporate_root": args.status_corporate_root,
                "workspace": args.workspace,
            },
            operation_binding=_command_operation_binding(
                args,
                "import_ca_enrichment",
            ),
        )
        report = import_ca_enrichment(
            status_corporate_root=args.status_corporate_root,
            workspace=args.workspace,
            output_root=args.output_root,
            admission_request=admission_request,
        )
    elif args.command == "prepare-status-history":
        report = prepare_status_history_workspace(
            status_corporate_root=args.status_corporate_root,
            output_root=args.output_root,
            run_id=args.run_id,
            history_window_from=args.history_window_from,
            history_window_to=args.history_window_to,
            prepared_by=args.prepared_by,
        )
    elif args.command == "import-status-history":
        admission_request = _boundary_admission_request(
            args,
            boundary_inputs={
                "status_corporate_root": args.status_corporate_root,
                "workspace": args.workspace,
            },
            operation_binding=_command_operation_binding(
                args,
                "import_status_history",
            ),
        )
        report = import_status_history(
            status_corporate_root=args.status_corporate_root,
            workspace=args.workspace,
            output_root=args.output_root,
            admission_request=admission_request,
        )
    elif args.command == "validate-benchmark-registry":
        registry = load_benchmark_registry(config_dir)
        report = {
            "status": "PASS",
            "registry_id": registry.registry_id,
            "registry_sha256": registry.sha256,
            "benchmark_count": len(registry.benchmarks),
            "required_benchmark_count": len(registry.required_codes),
            "claim_boundaries": [registry.claim_boundary],
        }
    elif args.command == "prepare-benchmark-history":
        report = prepare_benchmark_workspace(
            config_dir=config_dir,
            official_foundation_root=args.official_foundation_root,
            output_root=args.output_root,
            run_id=args.run_id,
            window_from=args.window_from,
            window_to=args.window_to,
            prepared_by=args.prepared_by,
        )
    elif args.command == "import-benchmark-history":
        admission_request = _boundary_admission_request(
            args,
            boundary_inputs={
                "config_dir": config_dir,
                "official_foundation_root": args.official_foundation_root,
                "workspace": args.workspace,
            },
            operation_binding=_command_operation_binding(
                args,
                "import_benchmark_history",
            ),
        )
        report = import_benchmark_history(
            config_dir=config_dir,
            official_foundation_root=args.official_foundation_root,
            workspace=args.workspace,
            output_root=args.output_root,
            imported_at=args.imported_at,
            admission_request=admission_request,
        )
    elif args.command == "prepare-official-eod":
        report = prepare_official_eod_workspace(
            official_foundation_root=args.official_foundation_root,
            status_history_root=args.status_history_root,
            output_root=args.output_root,
            run_id=args.run_id,
            window_from=args.window_from,
            window_to=args.window_to,
            prepared_by=args.prepared_by,
        )
    elif args.command == "import-official-eod":
        registry = _load_eod_runtime_trust_registry(
            args.runtime_trust_registry,
            workspace_root=args.workspace,
            output_root=args.output_root,
            decision_at=args.imported_at,
        )
        admission_request = _boundary_admission_request(
            args,
            boundary_inputs={
                "workspace_root": args.workspace,
                "official_foundation_root": args.official_foundation_root,
                "status_history_root": args.status_history_root,
            },
            operation_binding=_command_operation_binding(
                args,
                "import_official_eod",
                runtime_trust_registry=registry,
            ),
        )
        report = import_official_daily_eod(
            workspace_root=args.workspace,
            official_foundation_root=args.official_foundation_root,
            status_history_root=args.status_history_root,
            output_root=args.output_root,
            run_id=args.run_id,
            imported_at=args.imported_at,
            runtime_trust_registry=registry,
            admission_request=admission_request,
        )
    elif args.command == "validate-official-eod":
        registry = None
        if args.runtime_trust_registry is not None:
            saved_report, _ = load_strict_json_object(
                args.official_eod_root
                / "reports"
                / "official_eod_import_report.json",
                field="official EOD import report",
            )
            imported_at = saved_report.get("imported_at")
            if not isinstance(imported_at, str) or not imported_at:
                raise ValueError(
                    "official EOD import report lacks imported_at for trust validation"
                )
            registry = _load_eod_runtime_trust_registry(
                args.runtime_trust_registry,
                workspace_root=args.official_eod_root,
                output_root=args.official_eod_root,
                decision_at=imported_at,
            )
        report = validate_official_eod_output(
            official_eod_root=args.official_eod_root,
            official_foundation_root=args.official_foundation_root,
            status_history_root=args.status_history_root,
            runtime_trust_registry=registry,
        )
    elif args.command == "build-data-foundation-packet":
        policy_path = (
            args.outcome_session_policy
            if args.outcome_session_policy is not None
            else config_dir / "pilot" / "outcome_session_policy.json"
        )
        admission_request = _boundary_admission_request(
            args,
            boundary_inputs={
                "official_foundation_root": args.official_foundation_root,
                "status_history_root": args.status_history_root,
                "ca_enrichment_root": args.ca_enrichment_root,
                "research_price_history_root": args.research_price_history_root,
                "benchmark_root": args.benchmark_root,
                "official_eod_root": args.official_eod_root,
                "project_root": project_root,
                "outcome_session_policy_path": policy_path,
            },
            operation_binding=_command_operation_binding(
                args,
                "build_data_foundation_packet",
            ),
        )
        report = build_data_foundation_packet(
            official_foundation_root=args.official_foundation_root,
            status_history_root=args.status_history_root,
            ca_enrichment_root=args.ca_enrichment_root,
            research_price_history_root=args.research_price_history_root,
            benchmark_root=args.benchmark_root,
            official_eod_root=args.official_eod_root,
            project_root=project_root,
            output_root=args.output_root,
            outcome_session_policy_path=policy_path,
            admission_request=admission_request,
        )
    elif args.command == "print-data-foundation-gate-report":
        report = print_data_foundation_gate_report(args.path)
        return 1 if _report_is_blocking(report) else 0
    else:  # pragma: no cover - argparse constrains this branch
        raise AssertionError(f"unhandled command: {args.command}")

    if scoped_config_report is not None:
        report["scoped_configuration"] = scoped_config_report

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if _report_is_blocking(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
