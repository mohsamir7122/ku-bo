from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
from pathlib import Path
import sys

from . import __version__
from .catalog import Catalog
from .capture_plan import execute_capture_plan
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
from .hashing import sha256_file
from .source_network import SourceNetworkCatalog, SourceNetworkRunValidator, validate_live_probe


BLOCKING_STATUSES = {
    "BLOCKED",
    "FAIL",
    "PACK_BLOCKED",
    "STOP_BACKTEST",
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
}

PROJECT_CONFIG_COMMANDS = frozenset(
    {
        "capture",
        "materialize-parser-run",
        "plan",
        "run-request",
        "validate-config",
        "validate-live-probe",
        "validate-network-run",
        "validate-pack",
        "validate-source-network",
    }
)

REQUIRED_PROJECT_CONFIG = (
    Path("config/methods.json"),
    Path("config/products.json"),
    Path("config/research_policies.json"),
    Path("config/source_capabilities.json"),
    Path("config/source_network.json"),
    Path("config/sources.json"),
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
        payload = json.loads(
            path.read_text(encoding="utf-8"),
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
    value = argparse.ArgumentParser(description="KU-BO Research Engine — auditable multi-source research")
    value.add_argument(
        "--project-root",
        type=Path,
        default=root,
        help="KU-BO checkout containing config/ (required for an installed wheel outside the checkout)",
    )
    sub = value.add_subparsers(dest="command", required=True)

    sub.add_parser("validate-config")
    sub.add_parser("validate-source-network")

    validate_run = sub.add_parser("validate-network-run")
    validate_run.add_argument("--run", type=Path, required=True)
    validate_run.add_argument("--product", required=True)
    validate_run.add_argument("--runtime-trust-registry", type=Path)

    probe = sub.add_parser("validate-live-probe")
    probe.add_argument("--probe", type=Path, required=True)

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
        "validate-network-run",
        "validate-live-probe",
        "plan",
        "run-request",
        "capture",
        "materialize-parser-run",
    }:
        network_catalog = SourceNetworkCatalog(project_root / "config")

    if args.command == "validate-config":
        assert network_catalog is not None
        report = {
            "status": "PASS",
            "legacy_catalog": Catalog(project_root / "config").report(),
            "source_network": network_catalog.report(),
        }
    elif args.command == "validate-source-network":
        assert network_catalog is not None
        report = network_catalog.report()
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
        return 1 if report.get("status") in BLOCKING_STATUSES else 0
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
    return 1 if report.get("status") in BLOCKING_STATUSES | {"FAILED"} else 0


if __name__ == "__main__":
    sys.exit(main())
