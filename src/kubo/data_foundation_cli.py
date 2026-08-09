from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .price_collection_workspace import prepare_price_collection_workspace
from .research_price_history import read_research_price_history
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



def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=(
            "KU-BO Data Foundation Pilot — authorized price exports and "
            "research-history validation without forecasts"
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
    else:
        _, validation = read_research_price_history(
            args.path,
            manifest_hashes=_manifest_hashes(args.manifest),
        )
        report = validation.to_dict()

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report.get("status") in BLOCKING_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
