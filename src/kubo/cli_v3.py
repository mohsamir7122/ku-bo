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
from .pack import PackValidator
from .pipeline import ResearchPipeline
from .provenance import source_tree_hash
from .research_ledger import ResearchDecisionLedger
from .reporting import build_report, render_report
from .request_contracts import AnalysisRequest
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
    "MODEL_CARD_BLOCKED",
    "UNVALIDATED_RESEARCH_ONLY",
}

PROJECT_CONFIG_COMMANDS = frozenset(
    {
        "capture",
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

    request = sub.add_parser("run-request")
    request.add_argument("--request", type=Path, required=True)
    request.add_argument("--network-run", type=Path)
    request.add_argument("--pack", type=Path)
    request.add_argument("--source-access", type=Path)
    request.add_argument("--model-card", type=Path)
    request.add_argument("--output", type=Path)
    request.add_argument("--research-ledger-dir", type=Path)
    request.add_argument("--ledger-id")

    capture = sub.add_parser("capture")
    capture.add_argument("--plan", type=Path, required=True)
    capture.add_argument("--output-root", type=Path, required=True)
    capture.add_argument("--fixture-root", type=Path)

    verify_research = sub.add_parser("verify-research-ledger")
    verify_research.add_argument("--ledger-dir", type=Path, required=True)
    verify_research.add_argument("--ledger-id", required=True)
    verify_research.add_argument("--seal", type=Path)

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
    outcome.add_argument("--evidence-hash", action="append", required=True)
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
        report = SourceNetworkRunValidator(args.run, network_catalog, args.product).validate().to_dict()
    elif args.command == "validate-live-probe":
        assert network_catalog is not None
        report = validate_live_probe(args.probe, network_catalog)
    elif args.command == "validate-pack":
        report = PackValidator(args.pack, Catalog(project_root / "config")).validate().to_dict()
    elif args.command == "plan":
        report = ResearchPipeline(project_root).plan(
            args.product,
            mode=args.mode,
            network_run_root=args.network_run,
            top_k=args.top_k,
            pack_root=args.pack,
            source_access_path=args.source_access,
            model_card_path=args.model_card,
        )
    elif args.command == "run-request":
        payload = json.loads(args.request.read_text(encoding="utf-8"))
        request_contract = AnalysisRequest.from_dict(payload)
        plan_report = ResearchPipeline(project_root).plan(
            request_contract.product_id,
            mode=request_contract.mode,
            network_run_root=args.network_run,
            top_k=request_contract.top_k,
            pack_root=args.pack,
            source_access_path=args.source_access,
            model_card_path=args.model_card,
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
                code_hash=source_tree_hash(project_root),
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
    elif args.command == "verify-research-ledger":
        ledger = _research_ledger(args.ledger_dir, args.ledger_id)
        report = ledger.verify_seal(args.seal, hmac_key=_runtime_hmac_key()) if args.seal else ledger.verify()
    elif args.command == "seal-research-ledger":
        key = _runtime_hmac_key()
        if key is not None and not args.key_id:
            raise ValueError("--key-id is required when KUBO_LEDGER_HMAC_KEY is set")
        seal = _research_ledger(args.ledger_dir, args.ledger_id).seal(
            args.seal,
            hmac_key=key,
            key_id=args.key_id if key is not None else None,
        )
        report = {"status": "PASS", "seal": seal}
    elif args.command == "append-research-outcome":
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        event = _research_ledger(args.ledger_dir, args.ledger_id).append_outcome(
            outcome_id=args.outcome_id,
            decision_id=args.decision_id,
            observed_at=args.observed_at,
            payload=payload,
            evidence_hashes=args.evidence_hash,
            actor_or_model_id=args.actor,
        )
        report = {"status": "PASS", "event": event}
    else:
        ledger = ForecastLedger(args.ledger, args.ledger_id)
        report = ledger.verify_seal(args.seal) if args.seal else ledger.verify()

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 1 if report.get("status") in BLOCKING_STATUSES | {"FAILED"} else 0


if __name__ == "__main__":
    sys.exit(main())
