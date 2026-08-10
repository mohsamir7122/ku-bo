from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from kubo.data_foundation_cli import main


ROOT = Path(__file__).resolve().parents[1]


class DataFoundationCliTests(unittest.TestCase):
    def test_validate_pilot_config_command(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "validate-pilot-config",
                ]
            )
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["identity_seed"]["security_count"], 5)
        self.assertFalse(report["identity_seed"]["official_identity_ready"])

    def test_validate_ca_formulas_command(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "validate-ca-formulas",
                ]
            )
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(
            report["claim_boundaries"]["mechanical_factor_is_official_factor"]
        )
        self.assertFalse(
            report["claim_boundaries"][
                "reference_price_factor_is_return_engine_multiplier"
            ]
        )

    def test_prepare_price_collection_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            workspace = Path(directory) / "workspace"
            with redirect_stdout(output):
                code = main(
                    [
                        "--project-root",
                        str(ROOT),
                        "prepare-price-collection",
                        "--output-root",
                        str(workspace),
                        "--downloaded-by",
                        "unit-test",
                    ]
                )
            self.assertEqual(code, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "PASS")
            self.assertTrue(
                (workspace / "manifests" / "price_collection_manifest.csv").is_file()
            )

    def test_prepare_official_foundation_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            workspace = Path(directory) / "official"
            with redirect_stdout(output):
                code = main(
                    [
                        "--project-root",
                        str(ROOT),
                        "prepare-official-foundation",
                        "--output-root",
                        str(workspace),
                        "--run-id",
                        "official-pilot-001",
                        "--calendar-year",
                        "2026",
                        "--prepared-by",
                        "unit-test",
                    ]
                )
            self.assertEqual(code, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["artifact_count"], 5)
            self.assertTrue(
                (workspace / "manifests" / "official_foundation_manifest.json").is_file()
            )
            self.assertFalse(
                report["claim_boundaries"]["workspace_contains_official_evidence"]
            )

    def test_prepare_status_corporate_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            workspace = Path(directory) / "status-ca"
            with redirect_stdout(output):
                code = main(
                    [
                        "--project-root",
                        str(ROOT),
                        "prepare-status-corporate",
                        "--output-root",
                        str(workspace),
                        "--run-id",
                        "status-ca-001",
                        "--action-window-from",
                        "2021-01-01",
                        "--action-window-to",
                        "2026-08-09",
                        "--prepared-by",
                        "unit-test",
                    ]
                )
            self.assertEqual(code, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["artifact_count"], 3)
            self.assertTrue(
                (workspace / "manifests" / "status_corporate_manifest.json").is_file()
            )
            self.assertFalse(
                report["claim_boundaries"]["current_status_is_status_history"]
            )
            self.assertFalse(
                report["claim_boundaries"][
                    "corporate_action_schedule_contains_adjustment_factor"
                ]
            )


if __name__ == "__main__":
    unittest.main()
