from __future__ import annotations

import argparse
import base64
import binascii
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

from . import __version__
from .capability_parity import validate_predecessor_capability_parity
from .catalog import Catalog
from .capture_plan import execute_capture_plan
from .company_dossier import (
    validate_company_research_bundle_files,
    write_company_dossier_report,
)
from .foundation_io import prepare_output_root, safe_regular_file
from .hashing import canonical_json_bytes, sha256_file
from .historical_knowledge import HistoricalKnowledgeCatalog, compile_research_plan, parse_as_of
from .issuer_sequential_collection import (
    compile_issuer_sequential_collection_plan,
    validate_issuer_sequential_collection_plan,
    validate_issuer_sequential_collection_policy,
    validate_issuer_sequential_collection_run,
    write_issuer_sequential_collection_plan,
)
from .ingestion import PublicHttpConnector
from .ledger import ForecastLedger
from .outcome_sessions import OutcomeSessionAuthority
from .pack import PackValidator
from .parser_materialization import materialize_parser_run
from .pipeline import ResearchPipeline
from .provenance import runtime_package_hash, source_tree_hash
from .research_ledger import ResearchDecisionLedger
from .reporting import build_report, render_report
from .request_contracts import AnalysisRequest
from .runtime_trust import RuntimeTrustRegistry, load_runtime_trust_registry
from .forty_session_replay import evaluate_forty_session_replay
from .factor9_admission import (
    validate_factor9_admission_manifest,
    write_factor9_admission_report,
)
from .exit_status import is_blocking_status
from .ku_bo_live_program import validate_ku_bo_live_program
from .kuwait_research_pipeline import build_integrated_research_bundle
from .live_dry_run import run_daily_dry_run, validate_live_dry_run
from .market_scope import validate_market_scope
from .portfolio_state import validate_portfolio_state
from .research_workflow import load_research_workflow
from .source_network import SourceNetworkCatalog, SourceNetworkRunValidator, validate_live_probe
from .source_access_recipes import (
    SourceAccessRecipeCatalog,
    compile_source_probe_plan,
    validate_access_probe_against_plan,
)
from .source_access_executor import execute_public_source_probe
from .source_quality import validate_source_quality_policy
from .source_fallback import plan_source_fallback, validate_source_fallback_policy
from .source_orchestrator import (
    SourceSearchOrchestrator,
    validate_source_search_report,
    validate_source_search_run,
)
from .source_evidence_lifecycle import (
    reconcile_source_evidence_file,
    write_reconciliation_report,
)
from .strict import parse_aware


BLOCKING_STATUSES = {
    "BLOCKED",
    "FAIL",
    "PACK_BLOCKED",
    "STOP_BACKTEST",
    "STOP_INFERENCE",
    "SOURCE_NETWORK_BLOCKED",
    "EXECUTION_BLOCKED",
    "PARTIAL",
    "RESEARCH_PARTIAL",
    "SOURCE_NETWORK_REQUIRED",
    "REQUEST_SCOPE_UNSATISFIED",
    "EVIDENCE_REQUIRED",
    "CAPABILITY_BLOCKED",
    "DATA_READY_MODEL_UNBOUND",
    "EVIDENCE_CONTRACT_VALIDATED_MODEL_UNBOUND",
    "EVIDENCE_AND_MODEL_CONTRACT_VALIDATED",
    "SYNTHETIC_CONTRACT_ONLY",
    "MODEL_CARD_BLOCKED",
    "UNVALIDATED_RESEARCH_ONLY",
    "DEGRADED",
    "CAPABILITY_FALLBACK_REQUIRED",
    "CAPABILITY_EXHAUSTED_ABSTAIN",
    "PARTIAL_STRUCTURAL_NON_ACTIONABLE",
    "DEGRADED_STRUCTURE_VALID_ONLY",
}

PROJECT_CONFIG_COMMANDS = frozenset(
    {
        "capture",
        "materialize-parser-run",
        "plan",
        "run-request",
        "run-source-search",
        "build-kuwait-research-bundle",
        "validate-config",
        "validate-live-probe",
        "validate-network-run",
        "validate-pack",
        "validate-research-workflow",
        "validate-source-network",
        "validate-source-access-recipes",
        "plan-source-access-probe",
        "execute-public-source-access-probe",
        "validate-source-access-probe",
        "validate-source-quality-policy",
        "validate-source-fallback-policy",
        "plan-source-fallback",
        "validate-market-scope",
        "validate-predecessor-capability-parity",
        "validate-portfolio-state",
        "validate-ku-bo-live-program",
        "validate-factor9-admission",
        "run-live-dry-run",
        "evaluate-forty-session-replay",
        "validate-historical-knowledge",
        "plan-historical-research",
        "reconcile-source-evidence",
        "validate-company-dossier-bundle",
        "validate-issuer-sequential-collection-policy",
        "validate-issuer-sequential-collection-plan",
        "validate-issuer-sequential-collection-run",
        "plan-issuer-sequential-collection",
    }
)

REQUIRED_PROJECT_CONFIG = (
    Path("config/ku_bo_018_event_admission_task.json"),
    Path("config/ku_bo_live_program.json"),
    Path("config/methods.json"),
    Path("config/market_scope.json"),
    Path("config/predecessor_capability_parity.json"),
    Path("config/products.json"),
    Path("config/research_policies.json"),
    Path("config/research_workflows.json"),
    Path("config/source_capabilities.json"),
    Path("config/source_network.json"),
    Path("config/source_access_recipes.json"),
    Path("config/source_fallback_policy.json"),
    Path("config/issuer_sequential_collection_policy.json"),
    Path("config/source_quality_policy.json"),
    Path("config/source_query_strategies.json"),
    Path("config/sources.json"),
    Path("config/historical_research_layers.json"),
    Path("config/historical_sources.json"),
)


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _require_project_root(project_root: Path) -> None:
    missing = [path.as_posix() for path in REQUIRED_PROJECT_CONFIG if not (project_root / path).is_file()]
    if missing:
        details = ", ".join(missing)
        raise SystemExit(
            "KU-BO project root is invalid: expected a checkout containing config/. "
            "Run from the repository root or pass --project-root /path/to/ku-bo before the command. "
            f"Missing: {details}"
        )


def _research_ledger(directory: Path, ledger_id: str) -> ResearchDecisionLedger:
    return ResearchDecisionLedger(
        directory / "research_decisions.jsonl",
        directory / "research_outcomes.jsonl",
        ledger_id,
    )


def _runtime_hmac_key() -> bytes | None:
    value = os.environ.get("KUBO_LEDGER_HMAC_KEY", "")
    if not value:
        return None
    try:
        if value.startswith("hex:"):
            return bytes.fromhex(value[4:])
        if value.startswith("base64:"):
            return base64.b64decode(value[7:], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("KUBO_LEDGER_HMAC_KEY is not valid encoded bytes") from exc
    raise ValueError("KUBO_LEDGER_HMAC_KEY must start with hex: or base64:")


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"outcome payload contains duplicate object key: {key}")
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"outcome payload contains non-JSON numeric constant: {value}")


def _load_strict_json_object(path: Path, field: str) -> dict[str, object]:
    try:
        content = safe_regular_file(path, field=field)
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_non_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"{field} must be strict UTF-8 JSON") from exc
    except ValueError:
        raise
    if not isinstance(payload, dict):
        raise ValueError(f"{field} must be a JSON object")
    return payload


def _parse_champion_freezes(values: list[str] | None) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values or []:
        product_id, separator, path = value.partition("=")
        if not separator or not product_id or not path or product_id in result:
            raise ValueError(
                "--champion-freeze must be a unique PRODUCT_ID=PRIVATE_RELATIVE_PATH binding"
            )
        result[product_id] = Path(path)
    return result


def _runtime_trust_hmac_key() -> bytes:
    value = os.environ.get("KUBO_RUNTIME_TRUST_HMAC_KEY", "")
    if not value:
        raise ValueError("KUBO_RUNTIME_TRUST_HMAC_KEY is required with --runtime-trust-registry")
    try:
        if value.startswith("hex:"):
            return bytes.fromhex(value[4:])
        if value.startswith("base64:"):
            return base64.b64decode(value[7:], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("KUBO_RUNTIME_TRUST_HMAC_KEY is not valid encoded bytes") from exc
    raise ValueError("KUBO_RUNTIME_TRUST_HMAC_KEY must start with hex: or base64:")


def _load_cli_runtime_trust_registry(
    registry_path: Path | None,
    run_root: Path | None,
) -> RuntimeTrustRegistry | None:
    if registry_path is None:
        return None
    if run_root is None:
        raise ValueError("--runtime-trust-registry requires --network-run or --run")
    resolved_run = run_root.resolve()
    resolved_registry = registry_path.resolve()
    if resolved_registry == resolved_run or resolved_run in resolved_registry.parents:
        raise ValueError("runtime trust registry must remain outside the evidence packet")
    key_id = os.environ.get("KUBO_RUNTIME_TRUST_HMAC_KEY_ID", "").strip()
    if not key_id:
        raise ValueError(
            "KUBO_RUNTIME_TRUST_HMAC_KEY_ID is required with --runtime-trust-registry"
        )
    try:
        run_payload = json.loads(
            (resolved_run / "research_run.json").read_text(encoding="utf-8")
        )
        decision_at = run_payload["decision_at"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("cannot resolve decision_at for runtime trust verification") from exc
    return load_runtime_trust_registry(
        resolved_registry,
        key=_runtime_trust_hmac_key(),
        expected_key_id=key_id,
        decision_at=decision_at,
    )


def parser() -> argparse.ArgumentParser:
    root = _root()
    value = argparse.ArgumentParser(description="KU-BO Research Engine - auditable multi-source research")
    value.add_argument(
        "--project-root",
        type=Path,
        default=root,
        help="KU-BO checkout containing config/ (required for an installed wheel outside the checkout)",
    )
    sub = value.add_subparsers(dest="command", required=True)

    sub.add_parser("validate-config")
    sub.add_parser("validate-source-network")
    sub.add_parser("validate-source-access-recipes")
    sub.add_parser("validate-source-quality-policy")
    sub.add_parser("validate-source-fallback-policy")
    sub.add_parser("validate-market-scope")
    sub.add_parser("validate-predecessor-capability-parity")
    sub.add_parser("validate-ku-bo-live-program")
    sub.add_parser("validate-research-workflow")
    sub.add_parser("validate-historical-knowledge")

    historical_plan = sub.add_parser("plan-historical-research")
    historical_plan.add_argument("--as-of", required=True, help="Research cutoff date (YYYY-MM-DD)")
    historical_plan.add_argument("--output", type=Path)

    evidence_reconciliation = sub.add_parser("reconcile-source-evidence")
    evidence_reconciliation.add_argument("--input", type=Path, required=True)
    evidence_reconciliation.add_argument("--output", type=Path)

    company_dossier = sub.add_parser("validate-company-dossier-bundle")
    company_dossier.add_argument("--universe", type=Path, required=True)
    company_dossier.add_argument(
        "--dossier", type=Path, action="append", dest="dossiers", required=True
    )
    company_dossier.add_argument("--output", type=Path)

    sub.add_parser("validate-issuer-sequential-collection-policy")

    validate_sequential_plan = sub.add_parser(
        "validate-issuer-sequential-collection-plan"
    )
    validate_sequential_plan.add_argument("--plan", type=Path, required=True)
    validate_sequential_plan.add_argument("--universe", type=Path, required=True)
    validate_sequential_plan.add_argument("--runtime-trust-registry", type=Path)

    validate_sequential_run = sub.add_parser(
        "validate-issuer-sequential-collection-run"
    )
    validate_sequential_run.add_argument("--plan", type=Path, required=True)
    validate_sequential_run.add_argument("--run", type=Path, required=True)
    validate_sequential_run.add_argument("--universe", type=Path, required=True)
    validate_sequential_run.add_argument("--runtime-trust-registry", type=Path)

    sequential_plan = sub.add_parser("plan-issuer-sequential-collection")
    sequential_plan.add_argument("--universe", type=Path, required=True)
    sequential_plan.add_argument("--run-id", required=True)
    sequential_plan.add_argument("--generated-at", required=True)
    sequential_plan.add_argument("--runtime-trust-registry", type=Path)
    sequential_plan.add_argument("--output", type=Path)

    replay = sub.add_parser("evaluate-forty-session-replay")
    replay.add_argument("--packet", type=Path, required=True)
    replay.add_argument("--runtime-root", type=Path, required=True)

    source_search = sub.add_parser("run-source-search")
    source_search.add_argument("--run-id", required=True)
    source_search.add_argument("--decision-at", required=True)
    source_search.add_argument("--output-root", type=Path, required=True)
    source_search.add_argument("--query", default="بورصة الكويت")
    source_search.add_argument("--source", action="append", dest="source_ids")
    source_search.add_argument("--watermarks", type=Path)

    integrate = sub.add_parser("build-kuwait-research-bundle")
    integrate.add_argument("--source-search-root", type=Path, required=True)
    integrate.add_argument("--parsed-inputs", type=Path, required=True)
    integrate.add_argument("--output-root", type=Path, required=True)

    validate_run = sub.add_parser("validate-network-run")
    validate_run.add_argument("--run", type=Path, required=True)
    validate_run.add_argument("--product", required=True)
    validate_run.add_argument("--runtime-trust-registry", type=Path)

    probe = sub.add_parser("validate-live-probe")
    probe.add_argument("--probe", type=Path, required=True)

    source_probe_plan = sub.add_parser("plan-source-access-probe")
    source_probe_plan.add_argument("--planned-at", required=True)
    source_probe_plan.add_argument("--source", action="append", dest="source_ids")
    source_probe_plan.add_argument("--output", type=Path)

    source_probe_validate = sub.add_parser("validate-source-access-probe")
    source_probe_validate.add_argument("--plan", type=Path, required=True)
    source_probe_validate.add_argument("--probe", type=Path, required=True)

    source_probe_execute = sub.add_parser("execute-public-source-access-probe")
    source_probe_execute.add_argument("--plan", type=Path, required=True)
    source_probe_execute.add_argument("--output-root", type=Path, required=True)

    factor9 = sub.add_parser("validate-factor9-admission")
    factor9.add_argument("--manifest", type=Path, required=True)
    factor9.add_argument("--artifact-root", type=Path, required=True)
    factor9.add_argument("--output", type=Path)

    fallback = sub.add_parser("plan-source-fallback")
    fallback.add_argument("--request", type=Path, required=True)
    fallback.add_argument("--artifact-root", type=Path)

    portfolio = sub.add_parser("validate-portfolio-state")
    portfolio.add_argument("--snapshot", type=Path, required=True)
    portfolio.add_argument("--orders", type=Path, required=True)
    portfolio.add_argument("--evidence-root", type=Path, required=True)
    portfolio.add_argument("--decision-at", required=True)
    portfolio.add_argument("--max-age-minutes", type=int, default=30)

    live_dry_run = sub.add_parser("run-live-dry-run")
    live_dry_run.add_argument("--private-runtime-root", type=Path, required=True)
    live_dry_run.add_argument("--output-root", type=Path, required=True)
    live_dry_run.add_argument("--run-id", required=True)
    live_dry_run.add_argument("--decision-session-date", required=True)
    live_dry_run.add_argument(
        "--source-probe-receipt", action="append", dest="source_probe_receipts"
    )
    live_dry_run.add_argument("--raw-evidence-manifest", type=Path)
    live_dry_run.add_argument("--normalized-snapshot", type=Path)
    live_dry_run.add_argument("--factor-snapshot", type=Path)
    live_dry_run.add_argument(
        "--champion-freeze",
        action="append",
        dest="champion_freezes",
        help="PRODUCT_ID=PRIVATE_RELATIVE_PATH; repeat once per product",
    )
    live_dry_run.add_argument("--recorded-at")

    validate_dry_run = sub.add_parser("validate-live-dry-run")
    validate_dry_run.add_argument("--run-root", type=Path, required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--product", required=True)
    plan.add_argument(
        "--mode",
        choices=("research_network", "validated_forecast"),
        default="research_network",
    )
    plan.add_argument("--network-run", type=Path)
    plan.add_argument("--top-k", type=int, default=5)
    plan.add_argument("--pack", type=Path)
    plan.add_argument("--source-access", type=Path)
    plan.add_argument("--model-card", type=Path)
    plan.add_argument("--runtime-trust-registry", type=Path)

    request = sub.add_parser("run-request")
    request.add_argument("--request", type=Path, required=True)
    request.add_argument("--network-run", type=Path)
    request.add_argument("--pack", type=Path)
    request.add_argument("--source-access", type=Path)
    request.add_argument("--model-card", type=Path)
    request.add_argument("--output", type=Path)
    request.add_argument("--research-ledger-dir", type=Path)
    request.add_argument("--ledger-id")
    request.add_argument("--runtime-trust-registry", type=Path)

    capture = sub.add_parser("capture")
    capture.add_argument("--plan", type=Path, required=True)
    capture.add_argument("--output-root", type=Path, required=True)
    capture.add_argument("--fixture-root", type=Path)

    materialize = sub.add_parser("materialize-parser-run")
    materialize.add_argument("--capture-root", type=Path, required=True)
    materialize.add_argument("--parser-plan", type=Path, required=True)

    verify_research = sub.add_parser("verify-research-ledger")
    verify_research.add_argument("--ledger-dir", type=Path, required=True)
    verify_research.add_argument("--ledger-id", required=True)
    verify_research.add_argument("--seal", type=Path)
    verify_research.add_argument("--expected-key-id")

    seal_research = sub.add_parser("seal-research-ledger")
    seal_research.add_argument("--ledger-dir", type=Path, required=True)
    seal_research.add_argument("--ledger-id", required=True)
    seal_research.add_argument("--seal", type=Path, required=True)
    seal_research.add_argument("--key-id")

    outcome = sub.add_parser("append-research-outcome")
    outcome.add_argument("--ledger-dir", type=Path, required=True)
    outcome.add_argument("--ledger-id", required=True)
    outcome.add_argument("--outcome-id", required=True)
    outcome.add_argument("--decision-id", required=True)
    outcome.add_argument("--observed-at", required=True)
    outcome.add_argument("--payload", type=Path, required=True)
    outcome.add_argument("--evidence-pack", type=Path, required=True)
    outcome.add_argument("--actor", default=f"kubo-outcome-recorder/{__version__}")

    validate_pack = sub.add_parser("validate-pack")
    validate_pack.add_argument("--pack", type=Path, required=True)

    verify = sub.add_parser("verify-ledger")
    verify.add_argument("--ledger", type=Path, required=True)
    verify.add_argument("--ledger-id", required=True)
    verify.add_argument("--seal", type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project_root = args.project_root.resolve()
    if args.command in PROJECT_CONFIG_COMMANDS:
        _require_project_root(project_root)
    network_catalog = None
    if args.command in {
        "validate-config",
        "validate-source-network",
        "validate-source-access-recipes",
        "plan-source-access-probe",
        "execute-public-source-access-probe",
        "validate-source-access-probe",
        "validate-research-workflow",
        "evaluate-forty-session-replay",
        "run-source-search",
        "build-kuwait-research-bundle",
        "validate-network-run",
        "validate-live-probe",
        "plan",
        "run-request",
        "capture",
        "materialize-parser-run",
    }:
        network_catalog = SourceNetworkCatalog(project_root / "config")

    recipe_catalog = None
    if args.command in {
        "validate-config",
        "validate-source-access-recipes",
        "plan-source-access-probe",
        "execute-public-source-access-probe",
        "validate-source-access-probe",
    }:
        assert network_catalog is not None
        recipe_catalog = SourceAccessRecipeCatalog(
            project_root / "config" / "source_access_recipes.json",
            network_catalog,
        )

    historical_catalog = None
    if args.command in {"validate-config", "validate-historical-knowledge", "plan-historical-research"}:
        historical_catalog = HistoricalKnowledgeCatalog(project_root / "config")

    if args.command == "validate-config":
        assert network_catalog is not None
        assert historical_catalog is not None
        assert recipe_catalog is not None
        workflow = load_research_workflow(project_root / "config")
        report = {
            "status": "PASS",
            "legacy_catalog": Catalog(project_root / "config").report(),
            "market_scope": validate_market_scope(project_root),
            "source_network": network_catalog.report(),
            "source_access_recipes": recipe_catalog.report(network_catalog),
            "source_quality_policy": validate_source_quality_policy(project_root),
            "source_fallback_policy": validate_source_fallback_policy(project_root),
            "issuer_sequential_collection_policy": (
                validate_issuer_sequential_collection_policy(project_root)
            ),
            "predecessor_capability_parity": validate_predecessor_capability_parity(
                project_root
            ),
            "research_workflow": asdict(workflow),
            "historical_knowledge": historical_catalog.report(),
            "live_program": validate_ku_bo_live_program(project_root),
        }
    elif args.command == "validate-source-network":
        assert network_catalog is not None
        report = network_catalog.report()
    elif args.command == "validate-source-access-recipes":
        assert network_catalog is not None
        assert recipe_catalog is not None
        report = recipe_catalog.report(network_catalog)
    elif args.command == "validate-source-quality-policy":
        report = validate_source_quality_policy(project_root)
    elif args.command == "validate-source-fallback-policy":
        report = validate_source_fallback_policy(project_root)
    elif args.command == "plan-source-fallback":
        report = plan_source_fallback(
            project_root, args.request, artifact_root=args.artifact_root
        )
    elif args.command == "validate-market-scope":
        report = validate_market_scope(project_root)
    elif args.command == "validate-predecessor-capability-parity":
        report = validate_predecessor_capability_parity(project_root)
    elif args.command == "validate-portfolio-state":
        validate_market_scope(project_root)
        report = validate_portfolio_state(
            args.snapshot,
            args.orders,
            evidence_root=args.evidence_root,
            decision_at=args.decision_at,
            max_age_minutes=args.max_age_minutes,
        )
    elif args.command == "validate-ku-bo-live-program":
        report = validate_ku_bo_live_program(project_root)
    elif args.command == "validate-research-workflow":
        assert network_catalog is not None
        spec = load_research_workflow(project_root / "config")
        report = {
            "status": "PASS_CONTRACT",
            "readiness_status": "LIVE_DEPENDENT",
            "workflow": asdict(spec),
            "source_capabilities": network_catalog.report()["capability_status_counts"],
            "live_operational_sources": network_catalog.report()["live_operational_sources"],
            "claim_boundaries": {
                "operational_ready": False,
                "backtest_ready": False,
                "probability_allowed": False,
                "recommendation_allowed": False,
            },
        }
    elif args.command == "validate-historical-knowledge":
        assert historical_catalog is not None
        report = historical_catalog.report()
    elif args.command == "plan-historical-research":
        assert historical_catalog is not None
        full_plan = compile_research_plan(historical_catalog, as_of=parse_as_of(args.as_of))
        if args.output is None:
            report = full_plan
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("xb") as handle:
                handle.write(canonical_json_bytes(full_plan))
                handle.flush()
                os.fsync(handle.fileno())
            report = {
                "status": "PLANNED_NOT_EXECUTED",
                "plan_id": full_plan["plan_id"],
                "output": str(args.output),
                "task_count": len(full_plan["tasks"]),
                "claim_boundaries": full_plan["claim_boundaries"],
            }
    elif args.command == "reconcile-source-evidence":
        report = reconcile_source_evidence_file(args.input)
        if args.output is not None:
            write_reconciliation_report(args.output, report)
    elif args.command == "validate-company-dossier-bundle":
        report = validate_company_research_bundle_files(args.universe, args.dossiers)
        if args.output is not None:
            write_company_dossier_report(args.output, report)
    elif args.command == "validate-issuer-sequential-collection-policy":
        report = validate_issuer_sequential_collection_policy(project_root)
    elif args.command == "validate-issuer-sequential-collection-plan":
        plan = _load_strict_json_object(args.plan, "sequential collection plan")
        runtime_trust_registry = None
        if args.runtime_trust_registry is not None:
            key_id = os.environ.get("KUBO_RUNTIME_TRUST_HMAC_KEY_ID", "").strip()
            if not key_id:
                raise ValueError(
                    "KUBO_RUNTIME_TRUST_HMAC_KEY_ID is required with "
                    "--runtime-trust-registry"
                )
            runtime_trust_registry = load_runtime_trust_registry(
                args.runtime_trust_registry,
                key=_runtime_trust_hmac_key(),
                expected_key_id=key_id,
                decision_at=plan.get("generated_at"),
            )
        report = validate_issuer_sequential_collection_plan(
            plan,
            issuer_universe=args.universe,
            project_root=project_root,
            runtime_trust_registry=runtime_trust_registry,
        )
    elif args.command == "validate-issuer-sequential-collection-run":
        plan = _load_strict_json_object(args.plan, "sequential collection plan")
        run = _load_strict_json_object(args.run, "sequential collection run")
        runtime_trust_registry = None
        if args.runtime_trust_registry is not None:
            key_id = os.environ.get("KUBO_RUNTIME_TRUST_HMAC_KEY_ID", "").strip()
            if not key_id:
                raise ValueError(
                    "KUBO_RUNTIME_TRUST_HMAC_KEY_ID is required with "
                    "--runtime-trust-registry"
                )
            runtime_trust_registry = load_runtime_trust_registry(
                args.runtime_trust_registry,
                key=_runtime_trust_hmac_key(),
                expected_key_id=key_id,
                decision_at=plan.get("generated_at"),
            )
        report = validate_issuer_sequential_collection_run(
            run,
            plan,
            project_root=project_root,
            issuer_universe=args.universe,
            runtime_trust_registry=runtime_trust_registry,
        )
    elif args.command == "plan-issuer-sequential-collection":
        runtime_trust_registry = None
        if args.runtime_trust_registry is not None:
            key_id = os.environ.get("KUBO_RUNTIME_TRUST_HMAC_KEY_ID", "").strip()
            if not key_id:
                raise ValueError(
                    "KUBO_RUNTIME_TRUST_HMAC_KEY_ID is required with "
                    "--runtime-trust-registry"
                )
            runtime_trust_registry = load_runtime_trust_registry(
                args.runtime_trust_registry,
                key=_runtime_trust_hmac_key(),
                expected_key_id=key_id,
                decision_at=args.generated_at,
            )
        full_plan = compile_issuer_sequential_collection_plan(
            project_root,
            args.universe,
            run_id=args.run_id,
            generated_at=args.generated_at,
            runtime_trust_registry=runtime_trust_registry,
        )
        if args.output is None:
            report = full_plan
        else:
            write_issuer_sequential_collection_plan(
                args.output,
                full_plan,
                project_root=project_root,
                issuer_universe=args.universe,
                runtime_trust_registry=runtime_trust_registry,
            )
            report = {
                "status": "PLANNED_NOT_EXECUTED",
                "plan_id": full_plan["plan_id"],
                "output": str(args.output),
                "security_count": full_plan["security_count"],
                "planned_source_count_per_security": full_plan[
                    "planned_source_count_per_security"
                ],
                "total_source_attempts_planned": full_plan[
                    "total_source_attempts_planned"
                ],
                "plan_sha256": full_plan["plan_sha256"],
                "claim_boundaries": full_plan["claim_boundaries"],
            }
    elif args.command == "evaluate-forty-session-replay":
        load_research_workflow(project_root / "config")
        report = evaluate_forty_session_replay(
            args.packet,
            runtime_root=args.runtime_root,
        )
    elif args.command == "run-source-search":
        assert network_catalog is not None
        load_research_workflow(project_root / "config")
        output_root = prepare_output_root(
            args.output_root,
            label="SOURCE_SEARCH_OUTPUT_ROOT",
        )
        watermarks = (
            _load_strict_json_object(args.watermarks, "source-search watermarks")
            if args.watermarks is not None
            else None
        )
        run = SourceSearchOrchestrator(
            catalog=network_catalog,
            strategy_path=project_root / "config" / "source_query_strategies.json",
            connector=PublicHttpConnector(),
        ).run(
            run_id=args.run_id,
            decision_at=parse_aware(args.decision_at, "decision_at"),
            attempt_log_path=output_root / "source_attempts.jsonl",
            query_text=args.query,
            source_ids=args.source_ids,
            watermarks=watermarks,
        )
        report = run.to_dict()
        validate_source_search_report(
            report,
            schema_root=project_root / "schemas",
        )
        report_path = output_root / "source_search_run.json"
        with report_path.open("xb") as handle:
            handle.write(canonical_json_bytes(report))
            handle.flush()
            os.fsync(handle.fileno())
        validate_source_search_run(
            output_root,
            schema_root=project_root / "schemas",
        )
    elif args.command == "build-kuwait-research-bundle":
        assert network_catalog is not None
        load_research_workflow(project_root / "config")
        report = build_integrated_research_bundle(
            source_search_root=args.source_search_root,
            parsed_inputs_path=args.parsed_inputs,
            output_root=args.output_root,
            source_catalog=network_catalog,
            schema_root=project_root / "schemas",
        )
    elif args.command == "validate-network-run":
        assert network_catalog is not None
        runtime_trust = _load_cli_runtime_trust_registry(
            args.runtime_trust_registry,
            args.run,
        )
        report = SourceNetworkRunValidator(
            args.run,
            network_catalog,
            args.product,
            runtime_trust_registry=runtime_trust,
        ).validate().to_dict()
    elif args.command == "validate-live-probe":
        assert network_catalog is not None
        report = validate_live_probe(args.probe, network_catalog)
    elif args.command == "plan-source-access-probe":
        assert network_catalog is not None
        assert recipe_catalog is not None
        full_plan = compile_source_probe_plan(
            recipe_catalog,
            network_catalog,
            planned_at=parse_aware(args.planned_at, "planned_at"),
            source_ids=args.source_ids,
        )
        if args.output is None:
            report = full_plan
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("xb") as handle:
                handle.write(canonical_json_bytes(full_plan))
                handle.flush()
                os.fsync(handle.fileno())
            report = {
                "status": "PLANNED_NOT_EXECUTED",
                "plan_id": full_plan["plan_id"],
                "output": str(args.output),
                "task_count": len(full_plan["tasks"]),
                "claim_boundaries": full_plan["claim_boundaries"],
            }
    elif args.command == "validate-source-access-probe":
        assert network_catalog is not None
        assert recipe_catalog is not None
        report = validate_access_probe_against_plan(
            probe_path=args.probe,
            plan_path=args.plan,
            recipes=recipe_catalog,
            source_catalog=network_catalog,
        )
    elif args.command == "execute-public-source-access-probe":
        assert network_catalog is not None
        assert recipe_catalog is not None
        report = execute_public_source_probe(
            plan_path=args.plan,
            output_root=args.output_root,
            recipes=recipe_catalog,
            source_catalog=network_catalog,
        )
    elif args.command == "validate-factor9-admission":
        if args.output is None:
            report = validate_factor9_admission_manifest(args.manifest, args.artifact_root)
        else:
            report = write_factor9_admission_report(
                args.manifest, args.artifact_root, args.output
            )
    elif args.command == "run-live-dry-run":
        validate_market_scope(project_root)
        validate_ku_bo_live_program(project_root)
        report = run_daily_dry_run(
            project_root=project_root,
            private_runtime_root=args.private_runtime_root,
            output_root=args.output_root,
            run_id=args.run_id,
            decision_session_date=args.decision_session_date,
            source_probe_receipts=[Path(value) for value in args.source_probe_receipts or []],
            raw_evidence_manifest=args.raw_evidence_manifest,
            normalized_snapshot=args.normalized_snapshot,
            factor_snapshot=args.factor_snapshot,
            champion_freezes=_parse_champion_freezes(args.champion_freezes),
            recorded_at=args.recorded_at,
        )
    elif args.command == "validate-live-dry-run":
        report = validate_live_dry_run(args.run_root)
    elif args.command == "validate-pack":
        report = PackValidator(args.pack, Catalog(project_root / "config")).validate().to_dict()
    elif args.command == "plan":
        runtime_trust = _load_cli_runtime_trust_registry(
            args.runtime_trust_registry,
            args.network_run,
        )
        report = ResearchPipeline(project_root).plan(
            args.product,
            mode=args.mode,
            network_run_root=args.network_run,
            top_k=args.top_k,
            pack_root=args.pack,
            source_access_path=args.source_access,
            model_card_path=args.model_card,
            runtime_trust_registry=runtime_trust,
        )
    elif args.command == "run-request":
        payload = json.loads(args.request.read_text(encoding="utf-8"))
        request_contract = AnalysisRequest.from_dict(payload)
        runtime_trust = _load_cli_runtime_trust_registry(
            args.runtime_trust_registry,
            args.network_run,
        )
        plan_report = ResearchPipeline(project_root).plan(
            request_contract.product_id,
            mode=request_contract.mode,
            network_run_root=args.network_run,
            top_k=request_contract.top_k,
            pack_root=args.pack,
            source_access_path=args.source_access,
            model_card_path=args.model_card,
            runtime_trust_registry=runtime_trust,
        )
        report = build_report(plan_report, request_contract)
        if args.research_ledger_dir is not None:
            if not args.ledger_id:
                raise ValueError("--ledger-id is required with --research-ledger-dir")
            if request_contract.mode != "research_network" or not report.get("decision_at"):
                raise ValueError("only a time-bound research_network report can be recorded")
            _research_ledger(args.research_ledger_dir, args.ledger_id).record_report(
                report,
                actor_or_model_id=f"kubo-research-engine/{__version__}",
                policy_hash=sha256_file(project_root / "config" / "research_policies.json"),
                code_hash=runtime_package_hash(),
                configuration_hash=source_tree_hash(
                    project_root,
                    ("config", "research"),
                ),
            )
        rendered = render_report(report, request_contract.output_format)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 1 if is_blocking_status(report.get("status"), known=BLOCKING_STATUSES) else 0
    elif args.command == "capture":
        assert network_catalog is not None
        report = execute_capture_plan(
            plan_path=args.plan,
            output_root=args.output_root,
            fixture_root=args.fixture_root,
            catalog=network_catalog,
            user_agent=os.environ.get("KUBO_USER_AGENT") or None,
        )
    elif args.command == "materialize-parser-run":
        assert network_catalog is not None
        report = materialize_parser_run(
            capture_root=args.capture_root,
            parser_plan_path=args.parser_plan,
            catalog=network_catalog,
        )
    elif args.command == "verify-research-ledger":
        ledger = _research_ledger(args.ledger_dir, args.ledger_id)
        report = (
            ledger.verify_seal(
                args.seal,
                hmac_key=_runtime_hmac_key(),
                expected_key_id=args.expected_key_id,
            )
            if args.seal
            else ledger.verify()
        )
    elif args.command == "seal-research-ledger":
        key = _runtime_hmac_key()
        if key is not None and not args.key_id:
            raise ValueError("--key-id is required when KUBO_LEDGER_HMAC_KEY is set")
        if key is None and args.key_id:
            raise ValueError("--key-id requires KUBO_LEDGER_HMAC_KEY")
        seal = _research_ledger(args.ledger_dir, args.ledger_id).seal(
            args.seal,
            hmac_key=key,
            key_id=args.key_id if key is not None else None,
        )
        report = {"status": "PASS", "seal": seal}
    elif args.command == "append-research-outcome":
        payload = _load_strict_json_object(args.payload, "outcome payload")
        event = _research_ledger(args.ledger_dir, args.ledger_id).append_outcome(
            outcome_id=args.outcome_id,
            decision_id=args.decision_id,
            observed_at=args.observed_at,
            payload=payload,
            evidence_pack=args.evidence_pack,
            actor_or_model_id=args.actor,
        )
        report = {"status": "PASS", "event": event}
    else:
        ledger = ForecastLedger(
            args.ledger,
            args.ledger_id,
            outcome_session_authority=OutcomeSessionAuthority.from_structural_files(
                project_root=project_root
            ),
        )
        report = ledger.verify_seal(args.seal) if args.seal else ledger.verify()

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 1 if is_blocking_status(
        report.get("status"), known=BLOCKING_STATUSES | {"FAILED"}
    ) else 0


if __name__ == "__main__":
    sys.exit(main())
