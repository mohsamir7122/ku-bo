from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from kubo.catalog import Catalog
from kubo.evaluation import evaluate_forecasts
from kubo.stopgates import Gate, build_stop_gate_report

from helpers import HASHES, gate_report, one_decision_evaluation_fixture, product_with_minimum, valid_model


ROOT = Path(__file__).resolve().parents[1]


class StopGateEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = Catalog(ROOT / "config")
        self.product = product_with_minimum(self.catalog.products["next_session_rank"], 1)

    def test_missing_gate_forces_stop_backtest(self):
        report = build_stop_gate_report([], manifest_hashes=frozenset(HASHES.values()), independent_dates=100, minimum_independent_dates=40, event_count=1)
        self.assertEqual(report["verdict"], "STOP_BACKTEST")
        self.assertTrue(any("MISSING_REQUIRED_GATES" in item for item in report["errors"]))

    def test_unresolved_gate_evidence_forces_stop_backtest(self):
        gates = [Gate(gate_id, "PASS", "CRITICAL", "f" * 64, "", "") for gate_id in {
            "ARTIFACT_RESOLUTION", "FORECAST_LEDGER", "LEDGER_SEAL", "LEAKAGE_CONTROL", "THESIS_EPISODES",
            "FULL_DENOMINATOR", "UNIVERSE_BENCHMARK", "POINT_IN_TIME_IDENTITY", "PRICE_CA_QA", "PROCESS_VALID_CLAIMS",
        }]
        report = build_stop_gate_report(gates, manifest_hashes=frozenset({HASHES["a"]}), independent_dates=100, minimum_independent_dates=40, event_count=1)
        self.assertEqual(report["verdict"], "STOP_BACKTEST")

    def test_small_sample_is_stop_inference_not_failure(self):
        report = gate_report(minimum_dates=40, independent_dates=1)
        self.assertEqual(report["verdict"], "STOP_INFERENCE")

    def test_valid_one_decision_fixture_scores_when_minimum_is_one(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), self.product)
            report = evaluate_forecasts(
                [fixture["prediction"]], [fixture["outcome"]], product=self.product,
                model_card=valid_model(self.product, probability_allowed=False), ledger_events=fixture["ledger"].events(),
                gate_report=gate_report(1, 1), universe_by_decision={"d1": frozenset({"101"})},
                resolved_artifact_hashes=frozenset(HASHES.values()), top_k=1,
            )
            self.assertEqual(report["status"], "PASS", report)
            self.assertEqual(report["metrics"]["coverage"], 1.0)
            self.assertIsNotNone(report["metrics"]["mean_selected_executed_net_excess"])

    def test_real_product_minimum_returns_stop_inference(self):
        product = self.catalog.products["next_session_rank"]
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), product)
            report = evaluate_forecasts(
                [fixture["prediction"]], [fixture["outcome"]], product=product,
                model_card=valid_model(product, probability_allowed=False), ledger_events=fixture["ledger"].events(),
                gate_report=gate_report(40, 1), universe_by_decision={"d1": frozenset({"101"})},
                resolved_artifact_hashes=frozenset(HASHES.values()), top_k=1,
            )
            self.assertEqual(report["status"], "STOP_INFERENCE")

    def test_string_boolean_prediction_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), self.product)
            fixture["prediction"]["selected"] = "False"
            report = evaluate_forecasts(
                [fixture["prediction"]], [fixture["outcome"]], product=self.product,
                model_card=valid_model(self.product, probability_allowed=False), ledger_events=fixture["ledger"].events(),
                gate_report=gate_report(1, 1), universe_by_decision={"d1": frozenset({"101"})},
                resolved_artifact_hashes=frozenset(HASHES.values()), top_k=1,
            )
            self.assertEqual(report["status"], "STOP_BACKTEST")
            self.assertTrue(any("JSON boolean" in item or "ledger payload mismatch" in item for item in report["errors"]))

    def test_missing_denominator_row_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), self.product)
            report = evaluate_forecasts(
                [fixture["prediction"]], [fixture["outcome"]], product=self.product,
                model_card=valid_model(self.product, probability_allowed=False), ledger_events=fixture["ledger"].events(),
                gate_report=gate_report(1, 1), universe_by_decision={"d1": frozenset({"101", "102"})},
                resolved_artifact_hashes=frozenset(HASHES.values()), top_k=1,
            )
            self.assertEqual(report["status"], "STOP_BACKTEST")
            self.assertTrue(any("DENOMINATOR_MISMATCH" in item for item in report["errors"]))

    def test_changed_prediction_does_not_match_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), self.product)
            fixture["prediction"]["score"] = 0.99
            report = evaluate_forecasts(
                [fixture["prediction"]], [fixture["outcome"]], product=self.product,
                model_card=valid_model(self.product, probability_allowed=False), ledger_events=fixture["ledger"].events(),
                gate_report=gate_report(1, 1), universe_by_decision={"d1": frozenset({"101"})},
                resolved_artifact_hashes=frozenset(HASHES.values()), top_k=1,
            )
            self.assertEqual(report["status"], "STOP_BACKTEST")
            self.assertTrue(any("ledger payload mismatch" in item for item in report["errors"]))

    def test_outcome_due_time_cannot_move(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), self.product)
            fixture["outcome"]["outcome_at"] = "2026-08-10T13:15:00+03:00"
            report = evaluate_forecasts(
                [fixture["prediction"]], [fixture["outcome"]], product=self.product,
                model_card=valid_model(self.product, probability_allowed=False), ledger_events=fixture["ledger"].events(),
                gate_report=gate_report(1, 1), universe_by_decision={"d1": frozenset({"101"})},
                resolved_artifact_hashes=frozenset(HASHES.values()), top_k=1,
            )
            self.assertEqual(report["status"], "STOP_BACKTEST")

    def test_probability_is_scored_only_when_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), self.product, probability=0.7)
            report = evaluate_forecasts(
                [fixture["prediction"]], [fixture["outcome"]], product=self.product,
                model_card=valid_model(self.product, probability_allowed=True), ledger_events=fixture["ledger"].events(),
                gate_report=gate_report(1, 1), universe_by_decision={"d1": frozenset({"101"})},
                resolved_artifact_hashes=frozenset(HASHES.values()), top_k=1,
            )
            self.assertEqual(report["status"], "PASS", report)
            self.assertEqual(report["metrics"]["probability_rows"], 1)
            self.assertIsNotNone(report["metrics"]["brier_score"])


if __name__ == "__main__":
    unittest.main()
