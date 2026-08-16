from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.event_factor_panel import (
    EventFactorPanelError,
    audit_retrospective_csv,
    audit_retrospective_decisions,
)
from event_factor_panel_fixture import ROOT


class EventFactorPanelAuditTests(unittest.TestCase):
    def test_factor_registry_is_unique_and_fail_closed(self) -> None:
        registry = json.loads(
            (
                ROOT
                / "config"
                / "pilot"
                / "humansoft_factor_registry.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(registry["security_code"], "HUMANSOFT")
        shard_root = (
            ROOT / "config" / "pilot" / "humansoft_factor_registry"
        )
        factors = []
        for shard_name in registry["shards"]:
            shard = json.loads(
                (shard_root / shard_name).read_text(encoding="utf-8")
            )
            self.assertEqual(shard["registry_id"], registry["registry_id"])
            factors.extend(shard["factors"])
        self.assertEqual(len(factors), registry["factor_count"])
        factor_ids = [row["factor_id"] for row in factors]
        self.assertEqual(len(factor_ids), len(set(factor_ids)))
        self.assertGreaterEqual(len(factors), 25)
        self.assertEqual(
            registry["global_rules"]["missing_values"],
            "NEVER_COERCE_TO_ZERO",
        )
        self.assertEqual(
            registry["global_rules"]["promotion"],
            "FAIL_CLOSED",
        )
        self.assertEqual(
            registry["legacy_repository_disposition"]["Research"],
            "NO_SCORE_OR_BACKTEST_SALVAGE; definitions may inform rewrites only",
        )
        event_reaction = next(
            row for row in factors if row["factor_id"] == "PRICE_REACTION"
        )
        self.assertEqual(event_reaction["pre_event_role"], "FORBIDDEN")
        evidence_gate = next(
            row for row in factors if row["factor_id"] == "EVIDENCE_COVERAGE"
        )
        self.assertEqual(
            evidence_gate["missing_data_action"],
            "STOP_AND_WITHHOLD_METRICS",
        )

    def test_retrospective_audit_reports_neutral_baseline(self) -> None:
        rows: list[dict[str, object]] = []
        index = 0

        def add(action: str, return_pct: float, score: float) -> None:
            nonlocal index
            index += 1
            rows.append(
                {
                    "decision_id": f"synthetic-{index}",
                    "decision_at": f"2026-01-{index:02d}T13:20:00+03:00",
                    "model_horizon_sessions": 5,
                    "audited_horizon_sessions": 20,
                    "score": score,
                    "action": action,
                    "relative_return_pct": return_pct,
                }
            )

        add("AVOID", -5.0, -2.0)
        add("NEUTRAL", -5.0, -1.0)
        add("NEUTRAL", -5.0, -1.0)
        for _ in range(4):
            add("AVOID", 0.0, -1.0)
        for _ in range(13):
            add("NEUTRAL", 0.0, 0.0)
        add("LONG", 5.0, 2.0)
        add("NEUTRAL", 5.0, 1.0)
        add("NEUTRAL", 5.0, 1.0)

        audit = audit_retrospective_decisions(
            rows,
            decision_cadence_sessions=5,
        )
        self.assertEqual(audit["sample_size"], 23)
        self.assertEqual(audit["raw_concordance_hits"], 15)
        self.assertAlmostEqual(audit["raw_concordance_rate"], 15 / 23)
        self.assertEqual(audit["always_neutral_hits"], 17)
        self.assertAlmostEqual(audit["always_neutral_rate"], 17 / 23)
        self.assertLess(
            audit["raw_concordance_rate"],
            audit["always_neutral_rate"],
        )
        self.assertAlmostEqual(audit["balanced_accuracy"], 0.4771241830065359)
        self.assertAlmostEqual(audit["macro_f1"], 0.5049019607843137)
        self.assertEqual(audit["overlap_status"], "OVERLAPPING_OUTCOME_WINDOWS")
        self.assertTrue(audit["cross_horizon"])
        self.assertFalse(audit["accuracy_claim_allowed"])
        self.assertFalse(audit["p_value_reported"])


    def test_csv_audit_emits_aggregate_only_output(self) -> None:
        header = (
            "prediction_id,protocol_version,decision_at,horizon_sessions,"
            "score,action,excess_return_20_pct\n"
        )
        body = (
            "one,HUMANSOFT-RETRO-V1,2026-01-01T13:20:00+03:00,5,"
            "2,LONG,5\n"
            "two,HUMANSOFT-RETRO-V1,2026-01-08T13:20:00+03:00,5,"
            "0,NEUTRAL,0\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "predictions_sealed.csv"
            output = Path(directory) / "audit.json"
            source.write_text(header + body, encoding="utf-8")
            result = audit_retrospective_csv(
                source,
                output_path=output,
                decision_cadence_sessions=5,
            )
            emitted = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result, emitted)
        self.assertEqual(result["sample_size"], 2)
        self.assertFalse(result["row_level_data_emitted"])
        self.assertEqual(result["source_filename"], "predictions_sealed.csv")
        self.assertEqual(
            result["source_protocol_versions"],
            ["HUMANSOFT-RETRO-V1"],
        )
        self.assertNotIn("rows", result)
        self.assertFalse(result["accuracy_claim_allowed"])


    def test_csv_fractional_model_horizon_is_rejected(self) -> None:
        header = (
            "prediction_id,protocol_version,decision_at,horizon_sessions,"
            "score,action,excess_return_20_pct\n"
        )
        body = (
            "one,HUMANSOFT-RETRO-V1,2026-01-01T13:20:00+03:00,"
            "5.5,0,NEUTRAL,0\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "predictions_sealed.csv"
            source.write_text(header + body, encoding="utf-8")
            with self.assertRaisesRegex(
                EventFactorPanelError,
                "must be a positive integer",
            ):
                audit_retrospective_csv(source)

    def test_retrospective_duplicate_decision_is_rejected(self) -> None:
        row = {
            "decision_id": "duplicate",
            "decision_at": "2026-01-01T13:20:00+03:00",
            "model_horizon_sessions": 5,
            "audited_horizon_sessions": 20,
            "score": 0.0,
            "action": "NEUTRAL",
            "relative_return_pct": 0.0,
        }
        with self.assertRaisesRegex(EventFactorPanelError, "duplicate decision_id"):
            audit_retrospective_decisions([row, dict(row)])


if __name__ == "__main__":
    unittest.main()
