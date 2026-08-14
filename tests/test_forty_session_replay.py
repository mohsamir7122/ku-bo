from __future__ import annotations

import copy
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from jsonschema import Draft202012Validator, ValidationError
except ModuleNotFoundError:  # The dependency is installed by the repository's test extra.
    Draft202012Validator = None
    ValidationError = Exception

from kubo.forty_session_replay import (
    PRODUCT_ID,
    ReplayValidationError,
    _metrics,
    evaluate_forty_session_replay,
    validate_forty_session_replay_packet,
    validate_forty_session_replay_result,
)
from kubo.hashing import canonical_json_bytes, hash_json


ROOT = Path(__file__).resolve().parents[1]
KUWAIT = timezone(timedelta(hours=3))
HASHES = {
    "authority": "a" * 64,
    "calendar": "b" * 64,
    "code": "c" * 64,
    "calendar_raw": "d" * 64,
    "universe_evidence": "e" * 64,
    "feature_snapshot": "f" * 64,
    "feature": "1" * 64,
    "outcome": "2" * 64,
    "market_benchmark": "3" * 64,
    "corporate_action": "4" * 64,
    "sector_benchmark": "5" * 64,
    "sector_identity": "6" * 64,
    "execution": "7" * 64,
}


def _trading_sessions(start: date, count: int) -> list[date]:
    sessions: list[date] = []
    current = start
    while len(sessions) < count:
        if current.weekday() in {6, 0, 1, 2, 3}:  # Sunday through Thursday
            sessions.append(current)
        current += timedelta(days=1)
    return sessions


def _stamp(day: date, hour: int, minute: int = 0) -> str:
    return datetime.combine(day, time(hour, minute), KUWAIT).isoformat()


def valid_packet(*, top_k: int = 1) -> dict[str, object]:
    sessions = _trading_sessions(date(2026, 6, 18), 41)
    policy = {
        "primary_label": "GROSS_ADJUSTED_RETURN_GT_0",
        "secondary_labels": [
            "MARKET_NET_EXCESS_GT_0",
            "SECTOR_NET_EXCESS_GT_0",
        ],
        "horizon_sessions": 1,
        "decision_count": 40,
        "top_k": top_k,
        "minimum_effective_decisions": 40,
        "non_fill_policy": "STOP_BACKTEST",
        "benchmark_rule": "POINT_IN_TIME_MARKET_AND_SECTOR",
        "ranking_rule": "SCORE_DESC_SECURITY_CODE_ASC",
    }
    codes = ["101", "108", "413"]
    decisions: list[dict[str, object]] = []
    for index, decision_day in enumerate(sessions[:-1]):
        outcome_day = sessions[index + 1]
        decision_at = _stamp(decision_day, 13, 15)
        expected_codes = list(codes)
        rows: list[dict[str, object]] = []
        for rank, code in enumerate(codes, start=1):
            decision_close = 100.0 + rank
            if code == "101":
                multiplier = 1.01 if index % 2 == 0 else 0.99
            elif code == "108":
                multiplier = 1.02
            else:
                multiplier = 0.98
            rows.append(
                {
                    "security_code": code,
                    "identity_valid_from": "2020-01-01",
                    "identity_valid_to": None,
                    "identity_first_available_at": "2026-01-01T00:00:00+03:00",
                    "feature_available_at": decision_at,
                    "score_computed_at": decision_at,
                    "feature_evidence_sha256": HASHES["feature"],
                    "sector_code": "BANKS",
                    "sector_valid_from": "2020-01-01",
                    "sector_valid_to": None,
                    "sector_first_available_at": "2026-01-01T00:00:00+03:00",
                    "sector_identity_evidence_sha256": HASHES["sector_identity"],
                    "outcome_observed_at": _stamp(outcome_day, 13, 30),
                    "outcome_evidence_sha256": HASHES["outcome"],
                    "market_benchmark_evidence_sha256": HASHES["market_benchmark"],
                    "sector_benchmark_evidence_sha256": HASHES["sector_benchmark"],
                    "corporate_action_evidence_sha256": None,
                    "execution_evidence_sha256": (
                        HASHES["execution"] if rank <= top_k else None
                    ),
                    "execution_status": "FILLED" if rank <= top_k else "NOT_SELECTED",
                    "outcome_status": "OBSERVED_TRADING_OUTCOME",
                    "entry_at": _stamp(outcome_day, 9, 0) if rank <= top_k else None,
                    "exit_at": _stamp(outcome_day, 13, 15) if rank <= top_k else None,
                    "entry_price_fils": decision_close if rank <= top_k else None,
                    "exit_price_fils": (
                        decision_close * multiplier if rank <= top_k else None
                    ),
                    "fees_return": 0.001 if rank <= top_k else None,
                    "spread_return": 0.0 if rank <= top_k else None,
                    "slippage_return": 0.0 if rank <= top_k else None,
                    "decision_close_fils": decision_close,
                    "outcome_close_fils": decision_close * multiplier,
                    "price_adjustment_factor": 1.0,
                    "cash_distribution_return": 0.0,
                    "market_benchmark_decision_value": 1000.0,
                    "market_benchmark_outcome_value": 1005.0,
                    "sector_benchmark_decision_value": 1000.0,
                    "sector_benchmark_outcome_value": 1002.0,
                    "score": float(4 - rank),
                    "rank": rank,
                    "selected": rank <= top_k,
                    "abstained": False,
                }
            )
        decisions.append(
            {
                "decision_id": f"decision-{index + 1:02d}",
                "decision_session": decision_day.isoformat(),
                "outcome_session": outcome_day.isoformat(),
                "decision_at": decision_at,
                "universe_first_available_at": "2026-01-01T00:00:00+03:00",
                "universe_evidence_sha256": HASHES["universe_evidence"],
                "universe_sha256": hash_json(
                    {
                        "decision_session": decision_day.isoformat(),
                        "security_codes": expected_codes,
                    }
                ),
                "feature_snapshot_sha256": HASHES["feature_snapshot"],
                "feature_snapshot_created_at": decision_at,
                "policy_sha256": hash_json(policy),
                "code_sha256": HASHES["code"],
                "expected_security_codes": expected_codes,
                "rows": rows,
            }
        )
    official_sessions = [
        {
            "trade_date": day.isoformat(),
            "session_open_at": _stamp(day, 9, 0),
            "session_close_at": _stamp(day, 13, 15),
            "calendar_first_available_at": "2026-01-01T00:00:00+03:00",
            "raw_sha256": HASHES["calendar_raw"],
            "is_trading_day": True,
        }
        for day in sessions
    ]
    return {
        "schema_version": "1.0",
        "packet_id": "forty-session-fixture",
        "product_id": PRODUCT_ID,
        "timezone": "Asia/Kuwait",
        "created_at": _stamp(sessions[-1], 14, 0),
        "evidence_classification": "PROVEN_REAL_EVIDENCE",
        "rights_status": "RESEARCH_USE_AUTHORIZED",
        "data_foundation_status": "DATA_FOUNDATION_READY_FOR_BASELINE_BACKTEST",
        "final_authority_receipt_sha256": HASHES["authority"],
        "trading_calendar_sha256": hash_json(official_sessions),
        "code_sha256": HASHES["code"],
        "policy_sha256": hash_json(policy),
        "policy": policy,
        "official_sessions": official_sessions,
        "decisions": decisions,
    }


class FortySessionReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema = json.loads(
            (ROOT / "schemas" / "forty-session-replay.schema.json").read_text(
                encoding="utf-8"
            )
        )
        cls.schema = schema
        result_schema = json.loads(
            (
                ROOT
                / "schemas"
                / "forty-session-replay-result.schema.json"
            ).read_text(encoding="utf-8")
        )
        cls.result_schema = result_schema
        cls.schema_validator = None
        cls.result_schema_validator = None
        if Draft202012Validator is not None:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator.check_schema(result_schema)
            cls.schema_validator = Draft202012Validator(
                schema,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            )
            cls.result_schema_validator = Draft202012Validator(
                result_schema,
                format_checker=Draft202012Validator.FORMAT_CHECKER,
            )

    def evaluate(self, packet: dict[str, object]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            runtime.mkdir()
            path = runtime / "packet.json"
            path.write_bytes(canonical_json_bytes(packet))
            return evaluate_forty_session_replay(path, runtime_root=runtime)

    def assert_valid_result(self, result: dict[str, object]) -> None:
        self.assertIs(validate_forty_session_replay_result(result), result)
        if self.result_schema_validator is not None:
            self.result_schema_validator.validate(result)

    def test_valid_packet_matches_schema_but_final_authority_stays_required(self) -> None:
        packet = valid_packet()
        self.assertEqual(PRODUCT_ID, "KUWAIT_120D_NEXT_SESSION_RESEARCH")
        self.assertEqual(
            packet["policy"]["primary_label"],
            "GROSS_ADJUSTED_RETURN_GT_0",
        )
        if self.schema_validator is not None:
            self.schema_validator.validate(packet)
        replay = validate_forty_session_replay_packet(packet)
        metrics, diagnostics = _metrics(replay)
        self.assertIsNotNone(metrics)
        self.assertEqual(diagnostics["decision_sessions"], 40)
        self.assertEqual(diagnostics["denominator_rows"], 120)
        assert metrics is not None
        self.assertEqual(metrics["primary_absolute_up_hits"], 20)
        self.assertEqual(metrics["primary_selected_denominator"], 40)
        self.assertEqual(metrics["primary_selected_directional_agreement"], 0.5)
        self.assertEqual(metrics["primary_top1_directional_agreement"], 0.5)
        self.assertEqual(len(metrics["primary_top1_wilson_95"]), 2)
        self.assertEqual(metrics["market_net_excess_hits"], 20)
        self.assertEqual(metrics["market_net_excess_rate"], 0.5)
        self.assertEqual(metrics["sector_net_excess_hits"], 20)
        self.assertEqual(metrics["sector_net_excess_rate"], 0.5)
        self.assertEqual(metrics["probability"], None)
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST", result)
        self.assertEqual(
            result["errors"],
            ["FINAL_DATA_FOUNDATION_AUTHORITY_RECEIPT_REQUIRED"],
        )
        self.assertIsNone(result["metrics"])
        self.assertIsNone(result["agreement_rate"])
        self.assertEqual(result["agreement_rate_status"], "NOT_APPLICABLE")
        self.assertIsNone(result["authority_receipt_sha256"])
        self.assertFalse(result["authority_verified"])
        self.assertFalse(result["accuracy_claim_allowed"])
        self.assertFalse(
            result["claim_boundaries"][
                "independent_final_authority_receipt_verified"
            ]
        )
        self.assertTrue(result["claim_boundaries"]["metrics_withheld_on_stop"])
        self.assert_valid_result(result)

    def test_stop_result_contract_rejects_metrics_authority_and_accuracy_claims(self) -> None:
        result = self.evaluate(valid_packet())
        self.assert_valid_result(result)
        mutations = (
            ("input_sha256", "A" * 64),
            ("metrics", {}),
            ("agreement_rate", 1.0),
            ("agreement_rate_status", "MEASURED"),
            ("authority_receipt_sha256", "8" * 64),
            ("authority_verified", True),
            ("accuracy_claim_allowed", True),
        )
        for field, replacement in mutations:
            with self.subTest(field=field):
                invalid = copy.deepcopy(result)
                invalid[field] = replacement
                with self.assertRaises(ReplayValidationError):
                    validate_forty_session_replay_result(invalid)
                if self.result_schema_validator is not None:
                    with self.assertRaises(ValidationError):
                        self.result_schema_validator.validate(invalid)

        for field, replacement in (
            ("independent_final_authority_receipt_verified", True),
            ("metrics_withheld_on_stop", False),
        ):
            with self.subTest(claim_boundary=field):
                invalid = copy.deepcopy(result)
                invalid["claim_boundaries"][field] = replacement
                with self.assertRaises(ReplayValidationError):
                    validate_forty_session_replay_result(invalid)
                if self.result_schema_validator is not None:
                    with self.assertRaises(ValidationError):
                        self.result_schema_validator.validate(invalid)

    def test_evaluate_validates_the_result_before_returning_it(self) -> None:
        with patch(
            "kubo.forty_session_replay.validate_forty_session_replay_result",
            wraps=validate_forty_session_replay_result,
        ) as validator:
            result = self.evaluate(valid_packet())
        self.assertEqual(validator.call_count, 1)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assert_valid_result(result)

    def test_stop_inference_is_not_an_advertised_runtime_status(self) -> None:
        result = self.evaluate(valid_packet())
        result["status"] = "STOP_INFERENCE"
        result["errors"] = ["INSUFFICIENT_PROCESS_VALID_SCOREABLE_SESSIONS"]
        with self.assertRaises(ReplayValidationError):
            validate_forty_session_replay_result(result)
        if self.result_schema_validator is not None:
            with self.assertRaises(ValidationError):
                self.result_schema_validator.validate(result)

    def test_caller_authored_future_pass_shape_cannot_unlock_public_validator(self) -> None:
        packet = valid_packet()
        metrics, diagnostics = _metrics(validate_forty_session_replay_packet(packet))
        assert metrics is not None
        result = self.evaluate(packet)
        result.update(
            {
                "status": "PASS_BACKTEST",
                "errors": [],
                "metrics": metrics,
                "diagnostics": {
                    **diagnostics,
                    "process_valid_scoreable_sessions": 40,
                },
                "agreement_rate": metrics[
                    "primary_selected_directional_agreement"
                ],
                "agreement_rate_status": "MEASURED",
                "authority_receipt_sha256": "8" * 64,
                "authority_verified": True,
                "accuracy_claim_allowed": True,
            }
        )
        result["claim_boundaries"].update(
            {
                "independent_final_authority_receipt_verified": True,
                "metrics_withheld_on_stop": False,
            }
        )
        if self.result_schema_validator is not None:
            self.result_schema_validator.validate(result)
        with self.assertRaisesRegex(
            ReplayValidationError,
            "PASS_REQUIRES_INDEPENDENT_AUTHORITY_RESOLVER",
        ):
            validate_forty_session_replay_result(result)

    def test_invalid_packet_identifier_cannot_break_the_stop_result_schema(self) -> None:
        packet = valid_packet()
        packet["packet_id"] = "x" * 129
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIsNone(result["packet_id"])
        self.assert_valid_result(result)

    def test_in_memory_validator_accepts_complete_packet(self) -> None:
        normalized = validate_forty_session_replay_packet(valid_packet())
        self.assertEqual(normalized.packet_id, "forty-session-fixture")
        self.assertEqual(len(normalized.decisions), 40)

    def test_schema_rejects_unknown_fields(self) -> None:
        packet = valid_packet()
        packet["unexpected"] = True
        if self.schema_validator is not None:
            with self.assertRaises(ValidationError):
                self.schema_validator.validate(packet)
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIsNone(result["metrics"])
        self.assertIn("UNKNOWN_OR_MISSING_FIELDS", result["errors"][0])

    def test_requires_exactly_forty_decisions(self) -> None:
        packet = valid_packet()
        packet["decisions"].pop()
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIsNone(result["metrics"])
        self.assertIn("EXACTLY_40_REQUIRED", result["errors"][0])

    def test_requires_exactly_forty_one_official_sessions(self) -> None:
        packet = valid_packet()
        packet["official_sessions"].pop()
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("EXACTLY_41_REQUIRED", result["errors"][0])

    def test_decision_and_outcome_must_be_consecutive_official_sessions(self) -> None:
        packet = valid_packet()
        packet["decisions"][3]["outcome_session"] = packet["official_sessions"][5][
            "trade_date"
        ]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("CONSECUTIVE_OFFICIAL_SESSION", result["errors"][0])

    def test_duplicate_or_unsorted_official_session_is_rejected(self) -> None:
        packet = valid_packet()
        packet["official_sessions"][2]["trade_date"] = packet["official_sessions"][1][
            "trade_date"
        ]
        packet["official_sessions"][2]["session_close_at"] = packet[
            "official_sessions"
        ][1]["session_close_at"]
        packet["official_sessions"][2]["session_open_at"] = packet[
            "official_sessions"
        ][1]["session_open_at"]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("STRICTLY_INCREASING", result["errors"][0])

    def test_non_trading_calendar_row_is_rejected(self) -> None:
        packet = valid_packet()
        packet["official_sessions"][0]["is_trading_day"] = False
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("OFFICIAL_TRADING_SESSION_REQUIRED", result["errors"][0])

    def test_calendar_must_be_known_at_decision(self) -> None:
        packet = valid_packet()
        first_outcome = packet["decisions"][0]["outcome_session"]
        packet["official_sessions"][1]["calendar_first_available_at"] = (
            f"{first_outcome}T13:20:00+03:00"
        )
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertTrue(
            "CALENDAR_AVAILABLE_AFTER_SESSION" in result["errors"][0]
            or "OUTCOME_SESSION_CALENDAR_NOT_KNOWN" in result["errors"][0]
        )

    def test_calendar_hash_binds_all_forty_one_session_rows(self) -> None:
        packet = valid_packet()
        packet["trading_calendar_sha256"] = "0" * 64
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("CALENDAR_BYTES_MISMATCH", result["errors"][0])

    def test_decision_cannot_precede_official_close(self) -> None:
        packet = valid_packet()
        day = packet["decisions"][0]["decision_session"]
        packet["decisions"][0]["decision_at"] = f"{day}T13:14:00+03:00"
        packet["decisions"][0]["rows"][0]["feature_available_at"] = packet[
            "decisions"
        ][0]["decision_at"]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("DECISION_PRECEDES_OFFICIAL_CLOSE", result["errors"][0])

    def test_decision_and_features_must_be_frozen_before_outcome_open(self) -> None:
        packet = valid_packet()
        outcome_day = packet["decisions"][0]["outcome_session"]
        intraday = f"{outcome_day}T12:00:00+03:00"
        packet["decisions"][0]["decision_at"] = intraday
        packet["decisions"][0]["rows"][0]["feature_available_at"] = intraday
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("DECISION_NOT_BEFORE_OUTCOME_OPEN", result["errors"][0])

    def test_feature_lookahead_is_rejected(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["rows"][0]["feature_available_at"] = packet[
            "decisions"
        ][0]["rows"][0]["outcome_observed_at"]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIsNone(result["metrics"])
        self.assertIn("LOOK_AHEAD_FEATURE", result["errors"][0])

    def test_feature_snapshot_lookahead_is_rejected(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["feature_snapshot_created_at"] = packet["decisions"][
            0
        ]["rows"][0]["outcome_observed_at"]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIsNone(result["metrics"])
        self.assertIn("LOOK_AHEAD_FEATURE_SNAPSHOT", result["errors"][0])

    def test_feature_must_not_postdate_its_snapshot(self) -> None:
        packet = valid_packet()
        day = packet["decisions"][0]["decision_session"]
        packet["decisions"][0]["feature_snapshot_created_at"] = (
            f"{day}T13:14:00+03:00"
        )
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIsNone(result["metrics"])
        self.assertIn("FEATURE_POSTDATES_SNAPSHOT", result["errors"][0])

    def test_score_must_be_computed_between_snapshot_and_decision(self) -> None:
        for score_time in (
            "2026-06-18T13:14:00+03:00",
            "2026-06-18T13:16:00+03:00",
        ):
            with self.subTest(score_time=score_time):
                packet = valid_packet()
                packet["decisions"][0]["rows"][0]["score_computed_at"] = score_time
                result = self.evaluate(packet)
                self.assertEqual(result["status"], "STOP_BACKTEST")
                self.assertIsNone(result["metrics"])
                self.assertIn(
                    "SCORE_COMPUTED_OUTSIDE_POINT_IN_TIME_WINDOW",
                    result["errors"][0],
                )

    def test_universe_lookahead_is_rejected(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["universe_first_available_at"] = packet["decisions"][
            0
        ]["rows"][0]["outcome_observed_at"]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("LOOK_AHEAD_UNIVERSE", result["errors"][0])

    def test_identity_must_be_effective_and_available_at_decision(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["rows"][0]["identity_valid_from"] = "2027-01-01"
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("IDENTITY_NOT_EFFECTIVE_AT_DECISION", result["errors"][0])

        packet = valid_packet()
        packet["decisions"][0]["rows"][0]["identity_first_available_at"] = packet[
            "decisions"
        ][0]["rows"][0]["outcome_observed_at"]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("LOOK_AHEAD_IDENTITY", result["errors"][0])

    def test_outcome_must_be_observed_after_official_close_and_before_packet(self) -> None:
        packet = valid_packet()
        outcome_day = packet["decisions"][0]["outcome_session"]
        packet["decisions"][0]["rows"][0]["outcome_observed_at"] = (
            f"{outcome_day}T13:00:00+03:00"
        )
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("OUTCOME_OBSERVED_BEFORE_OFFICIAL_CLOSE", result["errors"][0])

        packet = valid_packet()
        packet["decisions"][-1]["rows"][0]["outcome_observed_at"] = (
            "2026-08-13T15:00:00+03:00"
        )
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("OUTCOME_OBSERVED_AFTER_PACKET_CREATION", result["errors"][0])

    def test_full_denominator_must_match_expected_codes_and_order(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["rows"].pop()
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("FULL_DENOMINATOR_MISMATCH", result["errors"][0])

        packet = valid_packet()
        first, second = packet["decisions"][0]["rows"][:2]
        packet["decisions"][0]["rows"][:2] = [second, first]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("DENOMINATOR_ORDER_OR_IDENTITY_MISMATCH", result["errors"][0])

    def test_expected_codes_must_be_unique_and_canonically_sorted(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["expected_security_codes"] = ["108", "101", "413"]
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("SECURITY_CODES_NOT_CANONICALLY_SORTED", result["errors"][0])

    def test_universe_hash_binds_session_and_full_code_list(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["universe_sha256"] = "0" * 64
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("UNIVERSE_HASH_MISMATCH", result["errors"][0])

    def test_policy_hash_and_decision_bindings_are_recomputed(self) -> None:
        packet = valid_packet()
        packet["policy"]["top_k"] = 2
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("POLICY_BYTES_MISMATCH", result["errors"][0])

        packet = valid_packet()
        packet["decisions"][0]["code_sha256"] = "9" * 64
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("CODE_HASH_MISMATCH", result["errors"][0])

    def test_absolute_up_is_primary_and_excess_is_secondary(self) -> None:
        packet = valid_packet()
        for decision in packet["decisions"]:
            selected = decision["rows"][0]
            selected["decision_close_fils"] = 100.0
            selected["outcome_close_fils"] = 101.0
            selected["market_benchmark_decision_value"] = 1000.0
            selected["market_benchmark_outcome_value"] = 1020.0
            selected["sector_benchmark_decision_value"] = 1000.0
            selected["sector_benchmark_outcome_value"] = 1030.0
        metrics, _diagnostics = _metrics(validate_forty_session_replay_packet(packet))
        assert metrics is not None
        self.assertEqual(metrics["primary_absolute_up_hits"], 40)
        self.assertEqual(metrics["market_net_excess_hits"], 0)
        self.assertEqual(metrics["sector_net_excess_hits"], 0)

    def test_costs_affect_actionable_and_excess_but_not_gross_direction(self) -> None:
        packet = valid_packet()
        for decision in packet["decisions"]:
            selected = decision["rows"][0]
            selected["decision_close_fils"] = 100.0
            selected["outcome_close_fils"] = 100.5
            selected["entry_price_fils"] = 100.0
            selected["exit_price_fils"] = 100.5
            selected["fees_return"] = 0.01
            selected["market_benchmark_decision_value"] = 1000.0
            selected["market_benchmark_outcome_value"] = 1000.0
            selected["sector_benchmark_decision_value"] = 1000.0
            selected["sector_benchmark_outcome_value"] = 1000.0
        metrics, _diagnostics = _metrics(validate_forty_session_replay_packet(packet))
        assert metrics is not None
        self.assertEqual(metrics["primary_absolute_up_hits"], 40)
        self.assertEqual(metrics["actionable_net_up_hits"], 0)
        self.assertEqual(metrics["market_net_excess_hits"], 0)
        self.assertEqual(metrics["sector_net_excess_hits"], 0)

    def test_nonfill_and_point_in_time_sector_fail_closed(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["rows"][0]["execution_status"] = "NON_FILL"
        result = self.evaluate(packet)
        self.assertIn("NON_FILL_OR_UNRESOLVED_EXECUTION_FORBIDDEN", result["errors"][0])

        packet = valid_packet()
        packet["decisions"][0]["rows"][0]["sector_first_available_at"] = packet[
            "decisions"
        ][0]["rows"][0]["outcome_observed_at"]
        result = self.evaluate(packet)
        self.assertIn("LOOK_AHEAD_SECTOR_IDENTITY", result["errors"][0])

    def test_nontrading_denominator_rows_stop_for_open_outcome_policy(self) -> None:
        cases = (
            (0, "SUSPENDED", "SUSPENDED"),
            (1, "NO_TRADE", "NOT_SELECTED"),
        )
        for row_index, outcome_status, execution_status in cases:
            with self.subTest(outcome_status=outcome_status):
                packet = valid_packet()
                row = packet["decisions"][0]["rows"][row_index]
                row["outcome_status"] = outcome_status
                row["outcome_close_fils"] = None
                row["execution_status"] = execution_status
                for field in (
                    "entry_at",
                    "exit_at",
                    "entry_price_fils",
                    "exit_price_fils",
                    "fees_return",
                    "spread_return",
                    "slippage_return",
                ):
                    row[field] = None
                if self.schema_validator is not None:
                    self.schema_validator.validate(packet)
                result = self.evaluate(packet)
                self.assertEqual(result["status"], "STOP_BACKTEST")
                self.assertIsNone(result["metrics"])
                self.assertIn(
                    f"OUTCOME_SESSION_POLICY_NOT_FROZEN:KU-BO-008-D01:{outcome_status}",
                    result["errors"][0],
                )

    def test_nontrading_rows_cannot_smuggle_a_synthetic_close(self) -> None:
        packet = valid_packet()
        row = packet["decisions"][0]["rows"][0]
        row["outcome_status"] = "SUSPENDED"
        row["execution_status"] = "SUSPENDED"
        for field in (
            "entry_at",
            "exit_at",
            "entry_price_fils",
            "exit_price_fils",
            "fees_return",
            "spread_return",
            "slippage_return",
        ):
            row[field] = None
        if self.schema_validator is not None:
            with self.assertRaises(ValidationError):
                self.schema_validator.validate(packet)
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn(
            "NONTRADING_OUTCOME_MUST_NOT_CONTAIN_SYNTHETIC_CLOSE",
            result["errors"][0],
        )

    def test_top_k_metrics_use_all_selected_rows_without_changing_top1(self) -> None:
        metrics, _diagnostics = _metrics(
            validate_forty_session_replay_packet(valid_packet(top_k=2))
        )
        assert metrics is not None
        self.assertEqual(metrics["primary_selected_denominator"], 80)
        self.assertEqual(metrics["primary_absolute_up_hits"], 60)
        self.assertEqual(metrics["primary_selected_directional_agreement"], 0.75)
        self.assertEqual(metrics["primary_top1_denominator"], 40)
        self.assertEqual(metrics["primary_top1_directional_agreement"], 0.5)

    def test_corporate_action_adjustment_requires_evidence(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["rows"][0]["price_adjustment_factor"] = 2.0
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("CORPORATE_ACTION_EVIDENCE_REQUIRED", result["errors"][0])

        packet = valid_packet()
        packet["decisions"][0]["rows"][0]["price_adjustment_factor"] = 2.0
        packet["decisions"][0]["rows"][0][
            "corporate_action_evidence_sha256"
        ] = HASHES["corporate_action"]
        validate_forty_session_replay_packet(packet)
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST", result)
        self.assertIn("FINAL_DATA_FOUNDATION_AUTHORITY_RECEIPT_REQUIRED", result["errors"])

    def test_numeric_strings_and_boolean_numbers_are_rejected(self) -> None:
        for value in ("101.0", True):
            with self.subTest(value=value):
                packet = valid_packet()
                packet["decisions"][0]["rows"][0]["decision_close_fils"] = value
                result = self.evaluate(packet)
                self.assertEqual(result["status"], "STOP_BACKTEST")
                self.assertIn("JSON_NUMBER_REQUIRED", result["errors"][0])

    def test_selected_rows_must_equal_contiguous_top_k(self) -> None:
        packet = valid_packet(top_k=2)
        packet["decisions"][0]["rows"][1]["selected"] = False
        packet["decisions"][0]["rows"][1]["execution_status"] = "NOT_SELECTED"
        packet["decisions"][0]["rows"][1]["execution_evidence_sha256"] = None
        for field in (
            "entry_at",
            "exit_at",
            "entry_price_fils",
            "exit_price_fils",
            "fees_return",
            "spread_return",
            "slippage_return",
        ):
            packet["decisions"][0]["rows"][1][field] = None
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("SELECTED_ROWS_MUST_EQUAL_TOP_K", result["errors"][0])

        packet = valid_packet()
        packet["decisions"][0]["rows"][1]["rank"] = 3
        packet["decisions"][0]["rows"][2]["rank"] = 4
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("RANKS_MUST_BE_UNIQUE_AND_CONTIGUOUS", result["errors"][0])

    def test_rank_is_recomputed_from_descending_score_and_security_code_ties(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["rows"][0]["score"] = 1.0
        packet["decisions"][0]["rows"][1]["score"] = 3.0
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn(
            "RANK_MUST_DERIVE_FROM_SCORE_DESC_SECURITY_CODE_ASC",
            result["errors"][0],
        )

        packet = valid_packet()
        for row in packet["decisions"][0]["rows"]:
            row["score"] = 1.0
        validate_forty_session_replay_packet(packet)
        packet["decisions"][0]["rows"][0]["rank"] = 2
        packet["decisions"][0]["rows"][1]["rank"] = 1
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn(
            "RANK_MUST_DERIVE_FROM_SCORE_DESC_SECURITY_CODE_ASC",
            result["errors"][0],
        )

    def test_valid_abstention_is_diagnosed_but_authority_gate_stays_first(self) -> None:
        packet = valid_packet()
        for row in packet["decisions"][0]["rows"]:
            row["score"] = None
            row["rank"] = None
            row["selected"] = False
            row["abstained"] = True
            row["execution_status"] = "NOT_SELECTED"
            row["execution_evidence_sha256"] = None
            for field in (
                "entry_at",
                "exit_at",
                "entry_price_fils",
                "exit_price_fils",
                "fees_return",
                "spread_return",
                "slippage_return",
            ):
                row[field] = None
        metrics, diagnostics = _metrics(validate_forty_session_replay_packet(packet))
        self.assertIsNone(metrics)
        self.assertEqual(diagnostics["effective_decisions"], 39)
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST", result)
        self.assertIsNone(result["metrics"])
        self.assertEqual(result["diagnostics"]["effective_decisions"], 39)
        self.assertIn("FINAL_DATA_FOUNDATION_AUTHORITY_RECEIPT_REQUIRED", result["errors"])

    def test_synthetic_fixture_and_unapproved_rights_cannot_produce_metrics(self) -> None:
        for field, value in (
            ("evidence_classification", "SYNTHETIC_ONLY"),
            ("rights_status", "FIXTURE_ONLY"),
            ("data_foundation_status", "PARTIAL"),
        ):
            with self.subTest(field=field):
                packet = valid_packet()
                packet[field] = value
                result = self.evaluate(packet)
                self.assertEqual(result["status"], "STOP_BACKTEST")
                self.assertIsNone(result["metrics"])

    def test_wrong_timezone_offset_is_rejected(self) -> None:
        packet = valid_packet()
        packet["decisions"][0]["decision_at"] = "2026-06-18T10:15:00+00:00"
        result = self.evaluate(packet)
        self.assertEqual(result["status"], "STOP_BACKTEST")
        self.assertIn("ASIA_KUWAIT_OFFSET_REQUIRED", result["errors"][0])

    def test_packet_path_must_remain_inside_real_runtime_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            outside = root / "packet.json"
            outside.write_bytes(canonical_json_bytes(valid_packet()))
            result = evaluate_forty_session_replay(outside, runtime_root=runtime)
            self.assertEqual(result["status"], "STOP_BACKTEST")
            self.assertIsNone(result["metrics"])
            self.assertIn("OUTSIDE_RUNTIME_ROOT", result["errors"][0])

    def test_symlink_packet_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            target = runtime / "target.json"
            target.write_bytes(canonical_json_bytes(valid_packet()))
            link = runtime / "packet.json"
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")
            result = evaluate_forty_session_replay(link, runtime_root=runtime)
            self.assertEqual(result["status"], "STOP_BACKTEST")
            self.assertIsNone(result["metrics"])
            self.assertIn("UNSAFE_OR_INVALID_JSON", result["errors"][0])

    def test_duplicate_json_keys_and_non_finite_values_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            runtime.mkdir()
            path = runtime / "packet.json"
            path.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
            result = evaluate_forty_session_replay(path, runtime_root=runtime)
            self.assertEqual(result["status"], "STOP_BACKTEST")
            self.assertIsNone(result["metrics"])
            self.assertIn("duplicate key", result["errors"][0])

            path.write_text('{"score":NaN}', encoding="utf-8")
            result = evaluate_forty_session_replay(path, runtime_root=runtime)
            self.assertEqual(result["status"], "STOP_BACKTEST")
            self.assertIsNone(result["metrics"])
            self.assertIn("non-finite JSON", result["errors"][0])

    def test_input_bytes_are_bound_in_stopped_result(self) -> None:
        packet = valid_packet()
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "runtime"
            runtime.mkdir()
            path = runtime / "packet.json"
            content = canonical_json_bytes(packet)
            path.write_bytes(content)
            result = evaluate_forty_session_replay(path, runtime_root=runtime)
            self.assertEqual(result["status"], "STOP_BACKTEST", result)
            self.assertEqual(len(result["input_sha256"]), 64)
            self.assertEqual(result["packet_id"], packet["packet_id"])


if __name__ == "__main__":
    unittest.main()
