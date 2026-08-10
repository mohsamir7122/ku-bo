from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .catalog import Catalog
from .methods import select_methods
from .modelcard import validate_model_card
from .pack import PackValidation, PackValidator
from .provenance import evidence_packet_hash
from .research_rank import rank_research_candidates
from .runtime_trust import RuntimeTrustRegistry
from .source_access import load_source_access
from .source_network import SourceNetworkCatalog, SourceNetworkRunValidator


class ResearchPipeline:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.catalog = Catalog(self.project_root / "config")
        self.network_catalog = SourceNetworkCatalog(self.project_root / "config")

    def plan(
        self,
        product_id: str,
        *,
        pack_root: Path | None = None,
        source_access_path: Path | None = None,
        model_card_path: Path | None = None,
        network_run_root: Path | None = None,
        mode: str = "research_network",
        top_k: int = 5,
        runtime_trust_registry: RuntimeTrustRegistry | None = None,
    ) -> dict[str, Any]:
        if product_id not in self.catalog.products:
            raise KeyError(product_id)
        if mode == "research_network":
            return self._plan_research_network(
                product_id,
                network_run_root=network_run_root,
                top_k=top_k,
                runtime_trust_registry=runtime_trust_registry,
            )
        if mode != "validated_forecast":
            raise ValueError("mode must be research_network or validated_forecast")
        product = self.catalog.products[product_id]
        access = load_source_access(source_access_path, self.catalog)
        pack: PackValidation | None = PackValidator(pack_root, self.catalog).validate() if pack_root is not None else None
        passed = pack.passed_capabilities if pack and pack.status == "PASS" else frozenset()
        missing = sorted(product.required_capabilities - passed)
        methods = select_methods(self.catalog.methods.values(), product, passed)
        model = validate_model_card(model_card_path, product) if model_card_path is not None else None

        reasons: list[str] = []
        if pack is None:
            status = "EVIDENCE_REQUIRED"
            reasons.append("NO_VALIDATED_EVIDENCE_PACK")
        elif pack.status != "PASS":
            status = "PACK_BLOCKED"
            reasons.extend(pack.errors)
        elif missing:
            status = "EXECUTION_BLOCKED" if product.execution_grade_required else "CAPABILITY_BLOCKED"
            reasons.append("MISSING_CAPABILITIES:" + ",".join(missing))
        elif pack.collection is not None and pack.collection.synthetic:
            status = "SYNTHETIC_CONTRACT_ONLY"
            reasons.append("SYNTHETIC_PACK_CANNOT_PROMOTE_READINESS")
        elif model is None:
            status = "EVIDENCE_CONTRACT_VALIDATED_MODEL_UNBOUND"
            reasons.extend(
                [
                    "NO_BOUND_MODEL_CARD",
                    "FINAL_DATA_FOUNDATION_GATE_REQUIRED_FOR_DATA_READINESS",
                ]
            )
        elif model.status != "PASS":
            status = "MODEL_CARD_BLOCKED"
            reasons.extend(model.errors)
        elif model.validation_status != "PROSPECTIVE_VALIDATED":
            status = "UNVALIDATED_RESEARCH_ONLY"
            reasons.append("MODEL_NOT_PROSPECTIVELY_VALIDATED")
        else:
            status = "EVIDENCE_AND_MODEL_CONTRACT_VALIDATED"
            reasons.append("FINAL_DATA_FOUNDATION_GATE_REQUIRED_FOR_FORECAST_READINESS")

        if access.status == "UNTESTED":
            reasons.append("CURRENT_SOURCE_ACCESS_UNTESTED")
        elif access.status == "BLOCKED":
            reasons.extend(access.errors)

        return {
            "status": status,
            "mode": "validated_forecast",
            "product": {**asdict(product), "required_capabilities": sorted(product.required_capabilities)},
            "pack": None if pack is None else pack.to_dict(),
            "passed_capabilities": sorted(passed),
            "missing_capabilities": missing,
            "methods": methods,
            "model_card": None
            if model is None
            else {
                "status": model.status,
                "validation_status": model.validation_status,
                "model_version": model.model_version,
                "probability_allowed": model.probability_allowed,
                "errors": list(model.errors),
            },
            "source_access": {"status": access.status, "states": access.states, "errors": list(access.errors)},
            "reasons": list(dict.fromkeys(reasons)),
            "claim_boundaries": {
                "source_access_is_not_data_capability": True,
                "test_pass_is_not_source_availability": True,
                "score_is_not_probability": True,
                "detection_is_not_execution": True,
                "structural_pack_pass_is_real_data_readiness": False,
                "final_data_foundation_gate_required_for_real_readiness": True,
            },
        }

    def _plan_research_network(
        self,
        product_id: str,
        *,
        network_run_root: Path | None,
        top_k: int,
        runtime_trust_registry: RuntimeTrustRegistry | None,
    ) -> dict[str, Any]:
        product = self.catalog.products[product_id]
        policy = self.network_catalog.policy_for(product_id)
        if network_run_root is None:
            return {
                "status": "SOURCE_NETWORK_REQUIRED",
                "mode": "research_network",
                "product": {**asdict(product), "required_capabilities": sorted(product.required_capabilities)},
                "policy": policy.profile_id,
                "network_run": None,
                "evidence_packet_hash": None,
                "runtime_trust_registry_id": None,
                "runtime_trust_registry_hash": None,
                "runtime_trust_key_id": None,
                "full_market_claim_allowed": False,
                "ranked_candidates": [],
                "reasons": ["NO_PER_RUN_SOURCE_PACKET"],
                "claim_boundaries": {
                    "historical_archive_required_to_start_research": False,
                    "validated_model_required_to_start_research": False,
                    "per_run_evidence_required": True,
                    "score_is_probability": False,
                    "research_rank_is_buy_recommendation": False,
                },
            }

        validation = SourceNetworkRunValidator(
            network_run_root,
            self.network_catalog,
            product_id,
            runtime_trust_registry=runtime_trust_registry,
        ).validate()
        if validation.status == "BLOCKED":
            status = "SOURCE_NETWORK_BLOCKED"
            reasons = list(validation.structural_errors)
        elif validation.status == "PARTIAL":
            status = "EXECUTION_BLOCKED" if product.execution_grade_required else "RESEARCH_PARTIAL"
            reasons = list(validation.coverage_gaps)
        else:
            status = "RESEARCH_READY"
            reasons = []
        ranked = rank_research_candidates(validation, source_map=self.network_catalog.sources, top_k=top_k)
        full_market_role_gap_codes = sorted(
            str(row.get("security_code"))
            for row in ranked
            if row.get("per_security_role_gaps")
        )
        full_market_contract = (
            validation.contract
            if validation.contract is not None
            and validation.contract.scope == "FULL_MARKET"
            else None
        )
        ranked_security_codes = {
            str(row.get("security_code"))
            for row in ranked
            if str(row.get("security_code", ""))
        }
        full_market_claim_allowed = bool(
            validation.status == "PASS"
            and full_market_contract is not None
            and validation.exact_universe_reconciled
            and ranked
            and len(ranked) == full_market_contract.expected_universe_count
            and len(ranked_security_codes) == full_market_contract.expected_universe_count
            and not full_market_role_gap_codes
        )
        if validation.exact_universe_reconciled and full_market_role_gap_codes:
            status = "RESEARCH_PARTIAL"
            reasons.append(
                "FULL_MARKET_PER_SECURITY_ROLE_COVERAGE_INCOMPLETE:"
                + ",".join(full_market_role_gap_codes)
            )
        packet_hash: str | None = None
        if validation.status in {"PASS", "PARTIAL"}:
            try:
                packet_hash = evidence_packet_hash(network_run_root)
            except (OSError, TypeError, ValueError) as exc:
                status = "SOURCE_NETWORK_BLOCKED"
                reasons.append(f"EVIDENCE_PACKET_CHANGED_AFTER_VALIDATION:{exc}")
                ranked = []
                full_market_claim_allowed = False
            else:
                if packet_hash != validation.evidence_packet_hash:
                    status = "SOURCE_NETWORK_BLOCKED"
                    reasons.append("EVIDENCE_PACKET_CHANGED_AFTER_VALIDATION")
                    ranked = []
                    packet_hash = None
                    full_market_claim_allowed = False
        network_run = validation.to_dict()
        network_claim_boundaries = network_run.get("claim_boundaries")
        if isinstance(network_claim_boundaries, dict):
            network_claim_boundaries["full_market_claim_allowed"] = (
                full_market_claim_allowed
            )
        return {
            "status": status,
            "mode": "research_network",
            "product": {**asdict(product), "required_capabilities": sorted(product.required_capabilities)},
            "policy": policy.profile_id,
            "network_run": network_run,
            "evidence_packet_hash": packet_hash,
            "runtime_trust_registry_id": validation.runtime_trust_registry_id,
            "runtime_trust_registry_hash": validation.runtime_trust_registry_hash,
            "runtime_trust_key_id": validation.runtime_trust_key_id,
            "full_market_claim_allowed": full_market_claim_allowed,
            "ranked_candidates": ranked,
            "reasons": list(dict.fromkeys([*reasons, *validation.warnings])),
            "claim_boundaries": {
                "historical_archive_required_to_start_research": False,
                "validated_model_required_to_start_research": False,
                "per_run_evidence_required": True,
                "probability_allowed": False,
                "recommendation_allowed": False,
                "full_market_best_requires_exact_reconciliation": True,
                "full_market_claim_allowed": full_market_claim_allowed,
                "detection_is_not_execution": True,
            },
        }


__all__ = ["ResearchPipeline"]
