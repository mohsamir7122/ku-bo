from __future__ import annotations

import contextlib
import io
import inspect
import json
from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

from kubo.catalog import Catalog
from kubo.cli_v3 import main as cli_main
from kubo.evaluation import evaluate_forecasts
from kubo.hashing import canonical_json_bytes, sha256_bytes
from kubo.ledger import ForecastLedger, validate_forecast_payload
from kubo.outcome_sessions import OutcomeSessionAuthority

from tests.helpers import HASHES, gate_report, one_decision_evaluation_fixture, product_with_minimum, valid_model
from tests.outcome_session_helpers import build_test_outcome_authority


ROOT = Path(__file__).resolve().parents[1]


def forecast_payload(*, due_at: str, decision_at: str = "2026-08-06T14:00:00+03:00") -> dict:
    return {
        "decision_id": "d1",
        "security_code": "101",
        "product_id": "next_session_rank",
        "target_rule": "NET_EXCESS_GT_0",
        "decision_at": decision_at,
        "outcome_due_at": due_at,
        "horizon_sessions": 1,
        "model_version": "m1",
        "entry_rule": "first feasible",
        "eligible": True,
        "selected": True,
        "abstained": False,
        "score": 0.5,
        "probability": None,
        "rank": 1,
        "thesis_episode_id": "episode-1",
    }


def append_forecast(
    ledger: ForecastLedger,
    payload: dict,
    *,
    policy_hash: str,
    calendar_hash: str,
    status_hash: str,
) -> None:
    ledger.append(
        event_type="CREATE",
        claim_id="c1",
        issued_at="2026-08-06T14:00:00+03:00",
        effective_at="2026-08-06T14:00:00+03:00",
        recorded_at="2026-08-06T14:01:00+03:00",
        test_mode=True,
        source_hash=HASHES["f"],
        actor_or_model_id="m1",
        policy_hash=policy_hash,
        code_hash=HASHES["b"],
        feature_snapshot_hash=HASHES["c"],
        universe_hash=HASHES["d"],
        trading_calendar_hash=calendar_hash,
        security_status_hash=status_hash,
        payload=payload,
    )


class OutcomeSessionContractTests(unittest.TestCase):
    def test_public_forecast_validator_has_no_authority_bypass_flag(self):
        self.assertNotIn(
            "require_outcome_session_authority",
            inspect.signature(validate_forecast_payload).parameters,
        )
        errors = validate_forecast_payload(
            forecast_payload(due_at="2026-08-07T13:15:00+03:00"),
            policy_hash=HASHES["a"],
            trading_calendar_hash=HASHES["e"],
            security_status_hash=HASHES["f"],
        )
        self.assertIn("OUTCOME_SESSION_AUTHORITY_REQUIRED", errors)
        with self.assertRaises(TypeError):
            validate_forecast_payload(
                forecast_payload(due_at="2026-08-07T13:15:00+03:00"),
                require_outcome_session_authority=False,
            )

    def test_generic_ledger_rejects_self_declared_civil_due_time_without_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ForecastLedger(Path(directory) / "ledger.jsonl", "L1")
            with self.assertRaisesRegex(ValueError, "OUTCOME_SESSION_AUTHORITY_REQUIRED"):
                append_forecast(
                    ledger,
                    forecast_payload(due_at="2026-08-07T13:15:00+03:00"),
                    policy_hash=HASHES["a"],
                    calendar_hash=HASHES["e"],
                    status_hash=HASHES["f"],
                )
            self.assertFalse((Path(directory) / "ledger.jsonl").exists())

    def test_repository_unfrozen_policy_blocks_forecast_recording_explicitly(self):
        authority = OutcomeSessionAuthority.from_structural_files(project_root=ROOT)
        self.assertIn("OUTCOME_SESSION_POLICY_NOT_FROZEN", authority.errors)
        with tempfile.TemporaryDirectory() as directory:
            ledger = ForecastLedger(
                Path(directory) / "ledger.jsonl",
                "L1",
                outcome_session_authority=authority,
            )
            with self.assertRaisesRegex(ValueError, "OUTCOME_SESSION_POLICY_NOT_FROZEN"):
                append_forecast(
                    ledger,
                    forecast_payload(due_at="2026-08-09T13:15:00+03:00"),
                    policy_hash=authority.policy_sha256 or HASHES["a"],
                    calendar_hash=HASHES["e"],
                    status_hash=HASHES["f"],
                )

    def test_committed_global_option_one_is_not_an_approved_d01_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            authority = build_test_outcome_authority(Path(directory) / "authority")
            self.assertIn(
                "OUTCOME_SESSION_USER_DECISION_NOT_APPROVED:KU-BO-008-D01",
                authority.errors,
            )
            errors = authority.validate_due_at(
                security_code="101",
                decision_at="2026-08-06T14:00:00+03:00",
                outcome_due_at="2026-08-09T13:15:00+03:00",
                horizon_sessions=1,
                policy_hash=authority.policy_sha256,
                trading_calendar_hash=authority.trading_calendar_sha256,
                security_status_hash=authority.security_status_sha256,
            )
            self.assertIn(
                "OUTCOME_SESSION_USER_DECISION_NOT_APPROVED:KU-BO-008-D01",
                errors,
            )
            self.assertFalse(any("expected=" in error for error in errors), errors)

    def test_weekend_civil_shortcut_is_not_the_next_official_session(self):
        with tempfile.TemporaryDirectory() as directory:
            authority = build_test_outcome_authority(Path(directory) / "authority")
            ledger = ForecastLedger(
                Path(directory) / "ledger.jsonl",
                "L1",
                outcome_session_authority=authority,
            )
            with self.assertRaises(ValueError) as caught:
                append_forecast(
                    ledger,
                    forecast_payload(due_at="2026-08-07T13:15:00+03:00"),
                    policy_hash=authority.policy_sha256 or "",
                    calendar_hash=authority.trading_calendar_sha256 or "",
                    status_hash=authority.security_status_sha256 or "",
                )
            message = str(caught.exception)
            self.assertIn("OUTCOME_SESSION_ARTIFACT_BOUND_OFFICIAL_AUTHORITY_REQUIRED", message)
            self.assertNotIn("expected=", message)
            diagnostic = authority._structural_option_one_due_at(
                security_code="101",
                decision_at=datetime.fromisoformat("2026-08-06T14:00:00+03:00"),
                horizon_sessions=1,
            )
            self.assertEqual(diagnostic.isoformat(), "2026-08-09T13:15:00+03:00")

    def test_holiday_civil_shortcut_advances_to_next_official_session(self):
        with tempfile.TemporaryDirectory() as directory:
            authority = build_test_outcome_authority(
                Path(directory) / "authority",
                trading_dates=frozenset({date(2026, 8, 6), date(2026, 8, 11)}),
            )
            errors = authority.validate_due_at(
                security_code="101",
                decision_at="2026-08-06T14:00:00+03:00",
                outcome_due_at="2026-08-10T13:15:00+03:00",
                horizon_sessions=1,
                policy_hash=authority.policy_sha256,
                trading_calendar_hash=authority.trading_calendar_sha256,
                security_status_hash=authority.security_status_sha256,
            )
            self.assertIn("OUTCOME_SESSION_ARTIFACT_BOUND_OFFICIAL_AUTHORITY_REQUIRED", errors)
            self.assertFalse(any("expected=" in error for error in errors), errors)
            diagnostic = authority._structural_option_one_due_at(
                security_code="101",
                decision_at=datetime.fromisoformat("2026-08-06T14:00:00+03:00"),
                horizon_sessions=1,
            )
            self.assertEqual(diagnostic.isoformat(), "2026-08-11T13:15:00+03:00")

    def test_suspended_session_does_not_satisfy_the_horizon(self):
        status_rows = (
            {
                "security_code": "101", "board": "cash", "status": "TRADING",
                "effective_from": "2026-08-01", "effective_to": "2026-08-08",
                "reason_code": "OPEN", "notice_id": "n1", "raw_sha256": "8" * 64,
            },
            {
                "security_code": "101", "board": "cash", "status": "SUSPENDED",
                "effective_from": "2026-08-09", "effective_to": "2026-08-09",
                "reason_code": "SUSPENDED", "notice_id": "n2", "raw_sha256": "8" * 64,
            },
            {
                "security_code": "101", "board": "cash", "status": "TRADING",
                "effective_from": "2026-08-10", "effective_to": "",
                "reason_code": "RESUMED", "notice_id": "n3", "raw_sha256": "8" * 64,
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            authority = build_test_outcome_authority(
                Path(directory) / "authority", status_rows=status_rows
            )
            errors = authority.validate_due_at(
                security_code="101",
                decision_at="2026-08-06T14:00:00+03:00",
                outcome_due_at="2026-08-09T13:15:00+03:00",
                horizon_sessions=1,
                policy_hash=authority.policy_sha256,
                trading_calendar_hash=authority.trading_calendar_sha256,
                security_status_hash=authority.security_status_sha256,
            )
            self.assertFalse(any("expected=" in error for error in errors), errors)
            diagnostic = authority._structural_option_one_due_at(
                security_code="101",
                decision_at=datetime.fromisoformat("2026-08-06T14:00:00+03:00"),
                horizon_sessions=1,
            )
            self.assertEqual(diagnostic.isoformat(), "2026-08-10T13:15:00+03:00")

    def test_decision_before_official_close_is_not_an_eod_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            authority = build_test_outcome_authority(Path(directory) / "authority")
            with self.assertRaisesRegex(
                ValueError, "DECISION_AT_PRECEDES_OFFICIAL_SESSION_CLOSE"
            ):
                authority._structural_option_one_due_at(
                    security_code="101",
                    decision_at=datetime.fromisoformat("2026-08-06T12:00:00+03:00"),
                    horizon_sessions=1,
                )

    def test_evaluation_rejects_outcome_when_session_authority_is_absent(self):
        catalog = Catalog(ROOT / "config")
        product = product_with_minimum(catalog.products["next_session_rank"], 1)
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), product)
            report = evaluate_forecasts(
                [fixture["prediction"]],
                [fixture["outcome"]],
                product=product,
                model_card=valid_model(product, probability_allowed=False),
                ledger_events=fixture["ledger"].events(),
                gate_report=gate_report(1, 1),
                universe_by_decision={"d1": frozenset({"101"})},
                resolved_artifact_hashes=frozenset(HASHES.values()),
                top_k=1,
            )
            self.assertEqual(report["status"], "STOP_BACKTEST")
            self.assertTrue(
                any("OUTCOME_SESSION_AUTHORITY_REQUIRED" in error for error in report["errors"]),
                report,
            )

    def test_cli_verify_ledger_uses_repository_policy_and_blocks_unfrozen_forecast(self):
        catalog = Catalog(ROOT / "config")
        product = product_with_minimum(catalog.products["next_session_rank"], 1)
        with tempfile.TemporaryDirectory() as directory:
            fixture = one_decision_evaluation_fixture(Path(directory), product)
            event = fixture["ledger"].events()[0]
            event["forecast_evidence_mode"] = "REAL_EVIDENCE"
            unsigned = dict(event)
            unsigned.pop("event_hash")
            event["event_hash"] = sha256_bytes(canonical_json_bytes(unsigned))
            fixture["ledger"].path.write_text(
                json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = cli_main(
                    [
                        "--project-root", str(ROOT),
                        "verify-ledger",
                        "--ledger", str(fixture["ledger"].path),
                        "--ledger-id", "ledger-eval",
                    ]
                )
            self.assertEqual(code, 1)
            self.assertIn("OUTCOME_SESSION_POLICY_NOT_FROZEN", stream.getvalue())

    def test_policy_symlink_is_never_authoritative(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "authority"
            build_test_outcome_authority(root)
            policy = root / "config" / "pilot" / "outcome_session_policy.json"
            target = root / "policy-copy.json"
            target.write_bytes(policy.read_bytes())
            policy.unlink()
            try:
                policy.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            authority = OutcomeSessionAuthority.from_structural_files(project_root=root)
            self.assertTrue(
                any("must not contain symlinks" in error for error in authority.errors),
                authority.errors,
            )

    def test_duck_typed_subclass_and_manual_authorities_cannot_validate_or_seal(self):
        class DuckAuthority:
            def validate_due_at(self, **kwargs):
                return ()

        class OverrideAuthority(OutcomeSessionAuthority):
            def validate_due_at(self, **kwargs):
                return ()

        subclass = OverrideAuthority(
            status="PASS",
            errors=(),
            policy_sha256=HASHES["a"],
            trading_calendar_sha256=HASHES["e"],
            security_status_sha256=HASHES["f"],
            calendar={},
            statuses=(),
        )
        manual = OutcomeSessionAuthority(
            status="PASS",
            errors=(),
            policy_sha256=HASHES["a"],
            trading_calendar_sha256=HASHES["e"],
            security_status_sha256=HASHES["f"],
            calendar={},
            statuses=(),
        )
        for label, authority, expected in (
            ("duck", DuckAuthority(), "OUTCOME_SESSION_AUTHORITY_EXACT_TYPE_REQUIRED"),
            ("subclass", subclass, "OUTCOME_SESSION_AUTHORITY_EXACT_TYPE_REQUIRED"),
            (
                "manual",
                manual,
                "OUTCOME_SESSION_ARTIFACT_BOUND_OFFICIAL_AUTHORITY_REQUIRED",
            ),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "ledger.jsonl"
                ledger = ForecastLedger(
                    path,
                    "L1",
                    outcome_session_authority=authority,  # type: ignore[arg-type]
                )
                with self.assertRaisesRegex(ValueError, expected):
                    append_forecast(
                        ledger,
                        forecast_payload(due_at="2026-08-07T13:15:00+03:00"),
                        policy_hash=HASHES["a"],
                        calendar_hash=HASHES["e"],
                        status_hash=HASHES["f"],
                    )

                fixture = one_decision_evaluation_fixture(Path(directory), Catalog(ROOT / "config").products["next_session_rank"])
                event = fixture["ledger"].events()[0]
                event["forecast_evidence_mode"] = "REAL_EVIDENCE"
                unsigned = dict(event)
                unsigned.pop("event_hash")
                event["event_hash"] = sha256_bytes(canonical_json_bytes(unsigned))
                path.write_bytes(canonical_json_bytes(event))
                report = ledger.verify()
                self.assertEqual(report["status"], "BLOCKED", report)
                self.assertTrue(any(expected in error for error in report["errors"]), report)
                with self.assertRaisesRegex(ValueError, "cannot seal invalid ledger"):
                    ledger.seal(Path(directory) / "seal.json")


if __name__ == "__main__":
    unittest.main()
