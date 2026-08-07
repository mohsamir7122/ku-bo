from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from kubo.cli_v3 import main
from kubo.provenance import runtime_package_hash, source_tree_hash


ROOT = Path(__file__).resolve().parents[1]


def write_cli_outcome_pack(
    ledger_dir: Path,
    *,
    outcome_id: str,
    decision_id: str,
    security_code: str,
    observed_at: str,
) -> Path:
    content = b'{"security_code":"101","official_close_fils":100}\n'
    packet = ledger_dir / "outcome_evidence" / outcome_id
    raw_path = packet / "raw" / "official-close.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(content)
    manifest = {
        "schema_version": "1.0",
        "outcome_id": outcome_id,
        "decision_id": decision_id,
        "security_code": security_code,
        "artifacts": [
            {
                "path": "raw/official-close.json",
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
                "source_id": "official-market-close",
                "source_url": "https://www.example.com/market/official-close.json",
                "content_type": "application/json",
                "observed_at": observed_at,
            }
        ],
    }
    (packet / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )
    return packet


class ResearchLedgerCliTests(unittest.TestCase):
    def test_recorded_code_hash_binds_the_executed_package_not_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            project_root = workspace / "configuration-only-project"
            shutil.copytree(ROOT / "config", project_root / "config")
            request = workspace / "request.json"
            request.write_text(
                json.dumps(
                    {
                        "request_id": "wheel-code-provenance",
                        "product_id": "next_session_rank",
                    }
                ),
                encoding="utf-8",
            )
            ledger_dir = workspace / "ledger"
            code = main(
                [
                    "--project-root",
                    str(project_root),
                    "run-request",
                    "--request",
                    str(request),
                    "--network-run",
                    str(ROOT / "examples" / "synthetic_source_network_run"),
                    "--output",
                    str(workspace / "report.json"),
                    "--research-ledger-dir",
                    str(ledger_dir),
                    "--ledger-id",
                    "wheel-ledger",
                ]
            )
            self.assertEqual(code, 0)
            event = json.loads(
                (ledger_dir / "research_decisions.jsonl").read_text(encoding="utf-8")
            )
            configuration_hash = source_tree_hash(
                project_root,
                ("config", "research"),
            )
            self.assertEqual(event["code_hash"], runtime_package_hash())
            self.assertEqual(event["configuration_hash"], configuration_hash)
            self.assertNotEqual(event["code_hash"], event["configuration_hash"])

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

            with mock.patch.dict(
                "os.environ", {"KUBO_LEDGER_HMAC_KEY": ""}, clear=False
            ), self.assertRaisesRegex(ValueError, "requires KUBO_LEDGER_HMAC_KEY"):
                main(
                    [
                        "seal-research-ledger",
                        "--ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                        "--seal",
                        str(workspace / "unsigned-with-key-id.seal.json"),
                        "--key-id",
                        "runtime-key-v1",
                    ]
                )

            runtime_key = bytes(range(32))
            environment = {"KUBO_LEDGER_HMAC_KEY": "hex:" + runtime_key.hex()}
            with mock.patch.dict("os.environ", environment, clear=False):
                downgrade_code = main(
                    [
                        "verify-research-ledger",
                        "--ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                        "--seal",
                        str(seal),
                        "--expected-key-id",
                        "runtime-key-v1",
                    ]
                )
                self.assertEqual(downgrade_code, 1)

                hmac_seal_code = main(
                    [
                        "seal-research-ledger",
                        "--ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                        "--seal",
                        str(seal),
                        "--key-id",
                        "runtime-key-v1",
                    ]
                )
                self.assertEqual(hmac_seal_code, 0)
                missing_expected_code = main(
                    [
                        "verify-research-ledger",
                        "--ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                        "--seal",
                        str(seal),
                    ]
                )
                self.assertEqual(missing_expected_code, 1)
                correct_code = main(
                    [
                        "verify-research-ledger",
                        "--ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                        "--seal",
                        str(seal),
                        "--expected-key-id",
                        "runtime-key-v1",
                    ]
                )
                self.assertEqual(correct_code, 0)

    def test_append_outcome_cli_validates_payload_and_evidence_pack_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            request_path = workspace / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "request_id": "recorded-request",
                        "product_id": "next_session_rank",
                        "output_format": "json",
                    }
                ),
                encoding="utf-8",
            )
            ledger_dir = workspace / "ledger"
            self.assertEqual(
                main(
                    [
                        "--project-root",
                        str(ROOT),
                        "run-request",
                        "--request",
                        str(request_path),
                        "--network-run",
                        str(ROOT / "examples" / "synthetic_source_network_run"),
                        "--output",
                        str(workspace / "report.json"),
                        "--research-ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                    ]
                ),
                0,
            )
            decision = json.loads(
                (ledger_dir / "research_decisions.jsonl").read_text(encoding="utf-8")
            )
            decision_id = decision["decision_id"]
            decision_at = decision["decision_at"]
            observed_at = decision["recorded_at"]
            security_code = decision["report"]["candidates"][0]["security_code"]
            pack = write_cli_outcome_pack(
                ledger_dir,
                outcome_id="outcome-1",
                decision_id=decision_id,
                security_code=security_code,
                observed_at=observed_at,
            )
            payload = {
                "schema_version": "1.0",
                "security_code": security_code,
                "metric_id": "next_session_decimal_return",
                "value": 0.02,
                "unit": "DECIMAL_RETURN",
                "measurement_start_at": decision_at,
                "measurement_end_at": observed_at,
                "method_id": "official_close_to_close_v1",
                "notes": "Measured from official closing-price evidence.",
            }
            payload_path = workspace / "outcome.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            append_code = main(
                [
                    "append-research-outcome",
                    "--ledger-dir",
                    str(ledger_dir),
                    "--ledger-id",
                    "test-ledger",
                    "--outcome-id",
                    "outcome-1",
                    "--decision-id",
                    decision_id,
                    "--observed-at",
                    observed_at,
                    "--payload",
                    str(payload_path),
                    "--evidence-pack",
                    str(pack),
                ]
            )
            self.assertEqual(append_code, 0)
            outcome = json.loads(
                (ledger_dir / "research_outcomes.jsonl").read_text(encoding="utf-8")
            )
            self.assertEqual(outcome["evidence_packet_path"], "outcome_evidence/outcome-1")
            self.assertEqual(
                outcome["evidence_hashes"],
                [hashlib.sha256((pack / "raw" / "official-close.json").read_bytes()).hexdigest()],
            )
            self.assertEqual(
                main(
                    [
                        "verify-research-ledger",
                        "--ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                    ]
                ),
                0,
            )

            duplicate_payload = workspace / "duplicate.json"
            duplicate_payload.write_text(
                '{"schema_version":"1.0","schema_version":"1.0"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate object key"):
                main(
                    [
                        "append-research-outcome",
                        "--ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                        "--outcome-id",
                        "outcome-duplicate",
                        "--decision-id",
                        decision_id,
                        "--observed-at",
                        observed_at,
                        "--payload",
                        str(duplicate_payload),
                        "--evidence-pack",
                        str(pack),
                    ]
                )

            nan_payload = workspace / "nan.json"
            nan_payload.write_text('{"value":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-JSON numeric constant"):
                main(
                    [
                        "append-research-outcome",
                        "--ledger-dir",
                        str(ledger_dir),
                        "--ledger-id",
                        "test-ledger",
                        "--outcome-id",
                        "outcome-nan",
                        "--decision-id",
                        decision_id,
                        "--observed-at",
                        observed_at,
                        "--payload",
                        str(nan_payload),
                        "--evidence-pack",
                        str(pack),
                    ]
                )


if __name__ == "__main__":
    unittest.main()
