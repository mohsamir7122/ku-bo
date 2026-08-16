from __future__ import annotations

import copy
import json
import unittest

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None

from kubo.event_factor_panel import (
    EventFactorPanelError,
    _event_metrics,
    evaluate_event_factor_panel,
    validate_event_factor_panel_packet,
    validate_event_factor_panel_result,
)
from event_factor_panel_fixture import ROOT, valid_packet


class EventFactorPanelContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet_validator = None
        cls.result_validator = None
        if Draft202012Validator is not None:
            packet_schema = json.loads(
                (ROOT / "schemas" / "event-factor-panel.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            result_schema = json.loads(
                (
                    ROOT
                    / "schemas"
                    / "event-factor-panel-result.schema.json"
                ).read_text(encoding="utf-8")
            )
            Draft202012Validator.check_schema(packet_schema)
            Draft202012Validator.check_schema(result_schema)
            cls.packet_validator = Draft202012Validator(
                packet_schema,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            )
            cls.result_validator = Draft202012Validator(
                result_schema,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            )

    def test_json_schemas_accept_valid_packet_and_stop_result(self) -> None:
        if self.packet_validator is None or self.result_validator is None:
            self.skipTest("jsonschema is not installed")
        packet = valid_packet()
        self.packet_validator.validate(packet)
        self.result_validator.validate(evaluate_event_factor_panel(packet))

    def test_structurally_valid_packet_computes_internal_metrics(self) -> None:
        packet = valid_packet()
        validated = validate_event_factor_panel_packet(packet)
        metrics = _event_metrics(validated)
        self.assertEqual(metrics["pre_session_count"], 20)
        self.assertEqual(metrics["post_session_count"], 20)
        self.assertEqual(metrics["observed_factor_count"], 1)
        self.assertEqual(metrics["unknown_factor_count"], 1)
        self.assertEqual(metrics["blocked_factor_count"], 1)
        expected = (114.5 / 105.0 - 1.0) * 100.0
        self.assertAlmostEqual(metrics["post_stock_return_pct"], expected)
        self.assertGreater(metrics["post_to_pre_volume_ratio"], 1.0)
        self.assertIsNone(metrics["probability"])

    def test_public_evaluation_stops_and_withholds_metrics(self) -> None:
        result = evaluate_event_factor_panel(valid_packet())
        self.assertEqual(result["status"], "STOP_EVENT_STUDY")
        self.assertIn(
            "INDEPENDENT_FINAL_EVENT_STUDY_AUTHORITY_RECEIPT_REQUIRED",
            result["errors"],
        )
        self.assertIsNone(result["metrics"])
        self.assertIsNone(result["agreement_rate"])
        self.assertFalse(result["accuracy_claim_allowed"])
        self.assertEqual(result["diagnostics"]["pre_sessions"], 20)
        self.assertIs(validate_event_factor_panel_result(result), result)


    def test_future_factor_is_rejected(self) -> None:
        packet = valid_packet()
        packet["factor_snapshot"]["factors"][0]["available_at"] = packet["created_at"]
        with self.assertRaisesRegex(
            EventFactorPanelError, "became available after event"
        ):
            validate_event_factor_panel_packet(packet)

    def test_unadjusted_price_basis_is_rejected(self) -> None:
        packet = valid_packet()
        packet["policy"]["price_basis"] = "RAW_CLOSE"
        with self.assertRaisesRegex(EventFactorPanelError, "TOTAL_RETURN_INDEX"):
            validate_event_factor_panel_packet(packet)

    def test_missing_benchmark_evidence_is_rejected(self) -> None:
        packet = valid_packet()
        packet["post_sessions"][0]["market_benchmark_evidence_sha256"] = None
        with self.assertRaisesRegex(EventFactorPanelError, "lowercase SHA-256"):
            validate_event_factor_panel_packet(packet)


    def test_session_evidence_must_match_top_level_receipts(self) -> None:
        packet = valid_packet()
        packet["pre_sessions"][0]["price_evidence_sha256"] = "9" * 64
        with self.assertRaisesRegex(
            EventFactorPanelError,
            "does not match evidence_receipts.price_history_sha256",
        ):
            validate_event_factor_panel_packet(packet)

    def test_wrong_window_count_is_rejected(self) -> None:
        packet = valid_packet()
        packet["post_sessions"].pop()
        with self.assertRaisesRegex(EventFactorPanelError, "exactly 20"):
            validate_event_factor_panel_packet(packet)

    def test_mutated_stop_result_cannot_claim_accuracy(self) -> None:
        result = evaluate_event_factor_panel(valid_packet())
        invalid = copy.deepcopy(result)
        invalid["accuracy_claim_allowed"] = True
        with self.assertRaises(EventFactorPanelError):
            validate_event_factor_panel_result(invalid)
        invalid = copy.deepcopy(result)
        invalid["metrics"] = {}
        with self.assertRaises(EventFactorPanelError):
            validate_event_factor_panel_result(invalid)

