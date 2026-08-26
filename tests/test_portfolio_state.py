from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from kubo.portfolio_state import PortfolioStateError, validate_portfolio_state


DECISION_AT = "2026-08-25T09:30:00+03:00"


def _evidence(path: str, content: bytes) -> dict[str, object]:
    return {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "captured_at": "2026-08-25T09:20:00+03:00",
        "source_id": "user-authorized-broker-export",
    }


def _snapshot(evidence: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "portfolio_id": "portfolio-001",
        "as_of": "2026-08-25T09:20:00+03:00",
        "timezone": "Asia/Kuwait",
        "currency": "KWD",
        "source_type": "USER_AUTHORIZED_EXPORT",
        "completeness": "COMPLETE",
        "evidence": [evidence],
        "cash": {"available": 100.0, "settled": 100.0, "reserved": 0.0},
        "positions": [
            {
                "security_code": "101",
                "quantity": 10,
                "available_quantity": 10,
                "average_cost": 2.0,
                "market_value": 20.0,
            }
        ],
        "reconciliation": {
            "broker_total_equity": 120.0,
            "computed_total_equity": 120.0,
            "difference": 0.0,
            "status": "MATCHED",
        },
    }


def _orders(evidence: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "portfolio_id": "portfolio-001",
        "as_of": "2026-08-25T09:20:00+03:00",
        "timezone": "Asia/Kuwait",
        "currency": "KWD",
        "source_type": "USER_AUTHORIZED_EXPORT",
        "completeness": "COMPLETE",
        "evidence": [evidence],
        "orders": [
            {
                "order_id": "order-001",
                "security_code": "101",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 5,
                "filled_quantity": 0,
                "limit_price": 2.1,
                "status": "OPEN",
                "submitted_at": "2026-08-25T09:10:00+03:00",
                "updated_at": "2026-08-25T09:20:00+03:00",
            }
        ],
    }


class PortfolioStateTests(unittest.TestCase):
    def _packet(self, root: Path) -> tuple[Path, Path, Path, dict[str, object], dict[str, object]]:
        evidence_root = root / "evidence"
        evidence_root.mkdir()
        content = b"private broker export fixture\n"
        (evidence_root / "broker.csv").write_bytes(content)
        evidence = _evidence("broker.csv", content)
        snapshot = _snapshot(evidence)
        orders = _orders(evidence)
        snapshot_path = root / "snapshot.json"
        orders_path = root / "orders.json"
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
        orders_path.write_text(json.dumps(orders), encoding="utf-8")
        return snapshot_path, orders_path, evidence_root, snapshot, orders

    def test_valid_packet_is_structural_and_non_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path, orders_path, evidence_root, _, _ = self._packet(Path(directory))

            report = validate_portfolio_state(
                snapshot_path,
                orders_path,
                evidence_root=evidence_root,
                decision_at=DECISION_AT,
            )

            self.assertEqual(report["status"], "PASS_STRUCTURAL_NON_ACTIONABLE")
            self.assertEqual(report["active_order_count"], 1)
            self.assertFalse(report["actionable"])
            self.assertFalse(report["claim_boundaries"]["order_submitted"])
            report_schema = json.loads(
                (Path(__file__).resolve().parents[1] / "schemas" / "portfolio-validation-report.schema.json").read_text()
            )
            Draft202012Validator(report_schema).validate(report)

    def test_evidence_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path, orders_path, evidence_root, snapshot, _ = self._packet(Path(directory))
            snapshot["evidence"][0]["sha256"] = "0" * 64
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

            with self.assertRaisesRegex(PortfolioStateError, "hash mismatch"):
                validate_portfolio_state(
                    snapshot_path,
                    orders_path,
                    evidence_root=evidence_root,
                    decision_at=DECISION_AT,
                )

    def test_stale_snapshot_is_rejected_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path, orders_path, evidence_root, snapshot, _ = self._packet(Path(directory))
            snapshot["as_of"] = "2026-08-25T08:00:00+03:00"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

            with self.assertRaisesRegex(PortfolioStateError, "stale"):
                validate_portfolio_state(
                    snapshot_path,
                    orders_path,
                    evidence_root=evidence_root,
                    decision_at=DECISION_AT,
                    max_age_minutes=30,
                )

    def test_duplicate_order_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path, orders_path, evidence_root, _, orders = self._packet(Path(directory))
            orders["orders"].append(dict(orders["orders"][0]))
            orders_path.write_text(json.dumps(orders), encoding="utf-8")

            with self.assertRaisesRegex(PortfolioStateError, "duplicate order_id"):
                validate_portfolio_state(
                    snapshot_path,
                    orders_path,
                    evidence_root=evidence_root,
                    decision_at=DECISION_AT,
                )

    def test_partial_unreconciled_packet_remains_non_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path, orders_path, evidence_root, snapshot, orders = self._packet(Path(directory))
            snapshot["completeness"] = "PARTIAL"
            snapshot["reconciliation"]["broker_total_equity"] = 121.0
            snapshot["reconciliation"]["difference"] = 1.0
            snapshot["reconciliation"]["status"] = "UNRESOLVED"
            orders["completeness"] = "PARTIAL"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            orders_path.write_text(json.dumps(orders), encoding="utf-8")

            report = validate_portfolio_state(
                snapshot_path,
                orders_path,
                evidence_root=evidence_root,
                decision_at=DECISION_AT,
            )

            self.assertEqual(report["status"], "PARTIAL_STRUCTURAL_NON_ACTIONABLE")
            self.assertIn("ACTIVE_ORDERS_WITH_UNRESOLVED_RECONCILIATION", report["warnings"])
            self.assertFalse(report["actionable"])

    def test_order_updated_after_decision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path, orders_path, evidence_root, _, orders = self._packet(Path(directory))
            orders["orders"][0]["updated_at"] = "2026-08-25T09:31:00+03:00"
            orders_path.write_text(json.dumps(orders), encoding="utf-8")

            with self.assertRaisesRegex(PortfolioStateError, "point-in-time ordering"):
                validate_portfolio_state(
                    snapshot_path,
                    orders_path,
                    evidence_root=evidence_root,
                    decision_at=DECISION_AT,
                )

    def test_numeric_strings_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path, orders_path, evidence_root, snapshot, _ = self._packet(Path(directory))
            snapshot["cash"]["settled"] = "100.0"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

            with self.assertRaisesRegex(PortfolioStateError, "JSON number"):
                validate_portfolio_state(
                    snapshot_path,
                    orders_path,
                    evidence_root=evidence_root,
                    decision_at=DECISION_AT,
                )

    def test_evidence_that_predates_snapshot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path, orders_path, evidence_root, snapshot, _ = self._packet(Path(directory))
            snapshot["evidence"][0]["captured_at"] = "2026-08-25T09:19:59+03:00"
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

            with self.assertRaisesRegex(PortfolioStateError, "predates"):
                validate_portfolio_state(
                    snapshot_path,
                    orders_path,
                    evidence_root=evidence_root,
                    decision_at=DECISION_AT,
                )


if __name__ == "__main__":
    unittest.main()
