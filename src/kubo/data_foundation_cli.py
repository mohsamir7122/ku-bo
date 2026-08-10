from __future__ import annotations

import argparse
import base64
import binascii
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
from .foundation_io import load_strict_json_object
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
from .user_price_export import import_investing_user_exports
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

    return any(
        report.get(field) in BLOCKING_STATUSES
        for field in ("status", "validation_status", "contract_status")
    )


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
    sub = value.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-pilot-config")
    sub.add_parser("validate-ca-formulas")

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
    import_exports.add_argument("--decision-at")

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

    print_report = sub.add_parser("print-data-foundation-gate-report")
    print_report.add_argument("--path", type=Path, required=True)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project_root = args.project_root.resolve()
    config_dir = project_root / "config"
    if not (config_dir / "pilot" / "security_master_seed.json").is_file():
        raise SystemExit(
            "invalid KU-BO project root: config/pilot/security_master_seed.json is missing"
        )

    report: dict[str, Any]
    if args.command == "validate-pilot-config":
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
        report = import_investing_user_exports(
            config_dir=config_dir,
            input_dir=args.input_dir,
            output_root=args.output_root,
            observed_at=args.observed_at,
            decision_at=args.decision_at,
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
        report = import_official_foundation(
            config_dir=config_dir,
            workspace=args.workspace,
            output_root=args.output_root,
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
        report = import_status_corporate(
            config_dir=config_dir,
            official_foundation_root=args.official_foundation_root,
            workspace=args.workspace,
            output_root=args.output_root,
        )
    elif args.command == "prepare-ca-enrichment":
        report = prepare_ca_enrichment_workspace(
            status_corporate_root=args.status_corporate_root,
            output_root=args.output_root,
            run_id=args.run_id,
            prepared_by=args.prepared_by,
        )
    elif args.command == "import-ca-enrichment":
        report = import_ca_enrichment(
            status_corporate_root=args.status_corporate_root,
            workspace=args.workspace,
            output_root=args.output_root,
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
        report = import_status_history(
            status_corporate_root=args.status_corporate_root,
            workspace=args.workspace,
            output_root=args.output_root,
            imported_at=args.imported_at,
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
        report = import_benchmark_history(
            config_dir=config_dir,
            official_foundation_root=args.official_foundation_root,
            workspace=args.workspace,
            output_root=args.output_root,
            imported_at=args.imported_at,
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
        report = import_official_daily_eod(
            workspace_root=args.workspace,
            official_foundation_root=args.official_foundation_root,
            status_history_root=args.status_history_root,
            output_root=args.output_root,
            run_id=args.run_id,
            imported_at=args.imported_at,
            runtime_trust_registry=registry,
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
        )
    elif args.command == "print-data-foundation-gate-report":
        report = print_data_foundation_gate_report(args.path)
        return 1 if _report_is_blocking(report) else 0
    else:  # pragma: no cover - argparse constrains this branch
        raise AssertionError(f"unhandled command: {args.command}")

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if _report_is_blocking(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
