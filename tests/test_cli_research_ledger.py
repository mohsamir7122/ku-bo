from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kubo.cli_v3 import main


ROOT = Path(__file__).resolve().parents[1]


class ResearchLedgerCliTests(unittest.TestCase):
    def test_run_request_can_record_verify_and_seal_research_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            request = workspace / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "request_id": "recorded-request",
                        "product_id": "next_session_rank",
                        "output_format": "json",
                    }
                ),
                encoding="utf-8",
            )
            output = workspace / "report.json"
            ledger_dir = workspace / "ledger"
            run_code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "run-request",
                    "--request",
                    str(request),
                    "--network-run",
                    str(ROOT / "examples" / "synthetic_source_network_run"),
                    "--output",
                    str(output),
                    "--research-ledger-dir",
                    str(ledger_dir),
                    "--ledger-id",
                    "test-ledger",
                ]
            )
            self.assertEqual(run_code, 0)
            self.assertTrue((ledger_dir / "research_decisions.jsonl").is_file())
            verify_code = main(
                [
                    "verify-research-ledger",
                    "--ledger-dir",
                    str(ledger_dir),
                    "--ledger-id",
                    "test-ledger",
                ]
            )
            self.assertEqual(verify_code, 0)
            seal = workspace / "ledger.seal.json"
            seal_code = main(
                [
                    "seal-research-ledger",
                    "--ledger-dir",
                    str(ledger_dir),
                    "--ledger-id",
                    "test-ledger",
                    "--seal",
                    str(seal),
                ]
            )
            self.assertEqual(seal_code, 0)
            self.assertTrue(seal.is_file())


if __name__ == "__main__":
    unittest.main()
