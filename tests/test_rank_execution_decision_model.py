from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.catalog import Catalog
from kubo.decisions import build_decision
from kubo.execution import assess_execution
from kubo.hashing import sha256_file
from kubo.modelcard import ModelCardResult, validate_model_card
from kubo.ranker import heuristic_rank


ROOT = Path(__file__).resolve().parents[1]
HASH_A = "a" * 64


def write_prospectively_validated_card(directory: Path, product) -> tuple[Path, dict, dict[str, Path]]:
    artifacts_root = directory / "artifacts"
    artifacts_root.mkdir()
    artifact_paths: dict[str, Path] = {}
    artifacts: dict[str, dict[str, str]] = {}
    for name in ("trial_registry", "model", "code", "policy", "prospective_ledger"):
        artifact_path = artifacts_root / f"{name}.bin"
        artifact_path.write_bytes(f"verified-{name}".encode("utf-8"))
        artifact_paths[name] = artifact_path
        artifacts[name] = {
            "path": artifact_path.relative_to(directory).as_posix(),
            "sha256": sha256_file(artifact_path),
        }

    receipt = {
        "schema_version": "1.0",
        "receipt_id": "receipt-1",
        "product_id": product.product_id,
        "model_version": "m1",
        "validation_status": "PROSPECTIVE_VALIDATED",
        "validated_at": "2026-08-05T12:00:00+03:00",
        "independent_dates": product.minimum_independent_dates,
        "gates": {
            "artifact_resolution": True,
            "prospective_ledger": True,
            "temporal_validation": True,
            "full_denominator": True,
            "baseline_comparison": True,
            "costs_and_nonfill": True,
            "calibration": True,
        },
        "artifacts": artifacts,
    }
    receipt_path = directory / "validation-receipt.json"
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    payload = {
        "model_version": "m1",
        "product_id": product.product_id,
        "target_rule": product.target_rule,
        "horizon_sessions": product.horizon_sessions,
        "decision_cutoff_rule": "post-close",
        "eligible_universe_rule": "frozen",
        "feature_names_and_available_at_rules": ["x"],
        "training_window": "2021-2024",
        "calibration_window": "2025",
        "locked_test_windows": ["2026"],
        "purge_sessions": product.horizon_sessions,
        "embargo_sessions": 0,
        "trial_registry_hash": artifacts["trial_registry"]["sha256"],
        "baseline_models": ["naive"],
        "calibration_method": "isotonic",
        "cost_and_fill_policy": "frozen",
        "minimum_coverage": 0.9,
        "minimum_expected_net_edge": 0.01,
        "abstention_policy": "frozen",
        "out_of_sample_metrics_by_window_and_regime": {"2026": {"brier": 0.2}},
        "model_hash": artifacts["model"]["sha256"],
        "code_hash": artifacts["code"]["sha256"],
        "policy_hash": artifacts["policy"]["sha256"],
        "prospective_ledger_hash": artifacts["prospective_ledger"]["sha256"],
        "validation_receipt_path": receipt_path.relative_to(directory).as_posix(),
        "validation_receipt_hash": sha256_file(receipt_path),
        "approved_at": "2026-08-06T12:00:00+03:00",
        "retirement_triggers": ["drift"],
        "validation_status": "PROSPECTIVE_VALIDATED",
        "frozen_base_rate": 0.3,
    }
    card_path = directory / "model.json"
    card_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return card_path, payload, artifact_paths


class RankExecutionDecisionModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = Catalog(ROOT / "config")
        self.product = self.catalog.products["next_session_rank"]

    def test_missing_features_abstain_instead_of_becoming_zero(self):
        rows = heuristic_rank([
            {"security_code": "101", "relative_return_5d": 0.1},
            {"security_code": "102"},
        ], product_id="next_session_rank", top_k=1)
        row_101 = next(row for row in rows if row["security_code"] == "101")
        row_102 = next(row for row in rows if row["security_code"] == "102")
        self.assertTrue(row_101["abstained"])
        self.assertIsNone(row_101["score"])
        self.assertTrue(row_102["abstained"])
        self.assertIsNone(row_102["probability"])

    def test_complete_heuristic_is_still_not_probability(self):
        row = {"security_code": "101", "relative_return_5d": .1, "relative_return_20d": .1, "relative_value_20d": .1, "relative_volume_20d": .1, "official_event_net_30d": .1, "liquidity_percentile": .8}
        ranked = heuristic_rank([row], product_id="next_session_rank", top_k=1)
        self.assertTrue(ranked[0]["selected"])
        self.assertIsNone(ranked[0]["probability"])
        self.assertEqual(ranked[0]["score_kind"], "UNVALIDATED_HEURISTIC_BASELINE")

    def test_public_delayed_snapshot_is_never_executable(self):
        result = assess_execution({
            "feed_access": "PUBLIC_DELAYED", "entitlement_id": "none", "raw_sha256": HASH_A,
            "observed_at": "2026-08-06T10:00:00+03:00", "provider_as_of": "2026-08-06T09:45:00+03:00",
            "delay_minutes": 15, "market_phase": "CONTINUOUS", "trading_status": "TRADED",
            "bid_fils": 99, "ask_fils": 101, "reference_price_fils": 100,
        }, decision_at="2026-08-06T10:00:00+03:00", manifest_hashes=frozenset({HASH_A}))
        self.assertEqual(result.status, "DETECTED_NOT_EXECUTABLE")
        self.assertIn("EXECUTION_FEED_NOT_AUTHORIZED", result.reason_codes)

    def test_authorized_label_without_entitlement_is_rejected(self):
        result = assess_execution({
            "feed_access": "LICENSED_VENDOR", "entitlement_id": "", "raw_sha256": HASH_A,
            "observed_at": "2026-08-06T10:00:00+03:00", "provider_as_of": "2026-08-06T10:00:00+03:00",
            "delay_minutes": 0, "market_phase": "CONTINUOUS", "trading_status": "TRADED",
            "bid_fils": 99, "ask_fils": 101, "reference_price_fils": 100,
        }, decision_at="2026-08-06T10:00:00+03:00", manifest_hashes=frozenset({HASH_A}))
        self.assertIn("MISSING_FEED_ENTITLEMENT_ID", result.reason_codes)

    def test_upper_limit_queue_is_not_execution(self):
        result = assess_execution({
            "feed_access": "BROKER_AUTHENTICATED", "entitlement_id": "broker-1", "raw_sha256": HASH_A,
            "observed_at": "2026-08-06T10:00:00+03:00", "provider_as_of": "2026-08-06T10:00:00+03:00",
            "delay_minutes": 0, "market_phase": "CONTINUOUS", "trading_status": "TRADED",
            "bid_fils": 110, "ask_fils": 110, "reference_price_fils": 100,
        }, decision_at="2026-08-06T10:00:00+03:00", manifest_hashes=frozenset({HASH_A}))
        self.assertIn("UPPER_LIMIT_QUEUE_OR_CENSORING", result.reason_codes)

    def test_model_card_cannot_claim_validation_with_short_purge(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload, _ = write_prospectively_validated_card(Path(directory), self.product)
            payload["purge_sessions"] = 0
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            report = validate_model_card(path, self.product)
            self.assertEqual(report.status, "BLOCKED")
            self.assertIn("PURGE_SHORTER_THAN_HORIZON", report.errors)

    def test_prospective_model_card_requires_resolved_receipt_and_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload, _ = write_prospectively_validated_card(Path(directory), self.product)
            self.assertEqual(validate_model_card(path, self.product).status, "PASS")

            payload.pop("validation_receipt_path")
            payload.pop("validation_receipt_hash")
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            report = validate_model_card(path, self.product)
            self.assertEqual(report.status, "BLOCKED")
            self.assertFalse(report.probability_allowed)
            self.assertTrue(any("INVALID_PROSPECTIVE_VALIDATION_RECEIPT" in error for error in report.errors))

    def test_prospective_model_card_rejects_mutated_bound_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _, artifact_paths = write_prospectively_validated_card(Path(directory), self.product)
            artifact_paths["model"].write_bytes(b"mutated-model")
            report = validate_model_card(path, self.product)
            self.assertEqual(report.status, "BLOCKED")
            self.assertFalse(report.probability_allowed)
            self.assertTrue(any("artifact bytes mismatch: model" in error for error in report.errors))

    def test_model_card_rejects_future_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload, _ = write_prospectively_validated_card(Path(directory), self.product)
            payload["approved_at"] = "2099-01-01T00:00:00+03:00"
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            report = validate_model_card(path, self.product)
            self.assertEqual(report.status, "BLOCKED")
            self.assertFalse(report.probability_allowed)
            self.assertIn("APPROVED_AT_IN_FUTURE", report.errors)

    def test_unvalidated_model_cannot_create_high_buy_opportunity(self):
        model = ModelCardResult("PASS", "PILOT_LOCKED", "m1", False, (), {"model_version": "m1", "policy_hash": "a"*64})
        decision = build_decision(
            security_code="101", product=self.product, model_card=model, score=.8, probability=None,
            expected_net_edge=.05, estimated_cost=.005, safety_margin=.005,
            gates={key: True for key in ("pack", "identity", "timing", "universe", "corporate_actions", "feature_snapshot", "policy_hash")},
            profile_features={}, execution=None,
        )
        self.assertEqual(decision.status, "WATCH")
        self.assertNotIn("HIGH_BUY_OPPORTUNITY", decision.profile_classes)

    def test_valid_research_without_execution_is_not_high_buy(self):
        model = ModelCardResult("PASS", "PROSPECTIVE_VALIDATED", "m1", True, (), {"model_version": "m1", "policy_hash": "a"*64})
        decision = build_decision(
            security_code="101", product=self.product, model_card=model, score=.8, probability=.7,
            expected_net_edge=.05, estimated_cost=.005, safety_margin=.005,
            gates={key: True for key in ("pack", "identity", "timing", "universe", "corporate_actions", "feature_snapshot", "policy_hash")},
            profile_features={}, execution=None,
        )
        self.assertEqual(decision.status, "QUALIFIED_RESEARCH_NOT_YET_EXECUTABLE")


if __name__ == "__main__":
    unittest.main()
