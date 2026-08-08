from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import unittest

from kubo.cli_v3 import BLOCKING_STATUSES, main as cli_main


ROOT = Path(__file__).resolve().parents[1]


class CliReadinessGateTests(unittest.TestCase):
    def test_degraded_and_incomplete_market_states_are_blocking(self) -> None:
        self.assertTrue(
            {
                "CAPTURE_DEGRADED",
                "DEGRADED",
                "PARTIAL_UNIVERSE_MAPPING_REQUIRED",
                "FULL_MARKET_IDENTITY_EVIDENCE_REQUIRED",
            }
            <= BLOCKING_STATUSES
        )

    def test_validate_config_includes_symbol_mapping_contract(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = cli_main(
                ["--project-root", str(ROOT), "validate-config"]
            )
        self.assertEqual(exit_code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["symbol_mapping"]["status"], "PASS")
        self.assertEqual(report["symbol_mapping"]["security_count"], 5)


if __name__ == "__main__":
    unittest.main()
