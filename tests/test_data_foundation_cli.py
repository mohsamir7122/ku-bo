from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from kubo.data_foundation_cli import (
    _boundary_admission_request,
    _parse_boundary_inputs,
    _report_is_blocking,
    main,
    parser,
)
from kubo.tri_security_admission import build_boundary_operation_binding


ROOT = Path(__file__).resolve().parents[1]


class DataFoundationCliTests(unittest.TestCase):
    ADMISSION_ARGUMENTS = [
        "--admission-path",
        "semantic-admission.json",
        "--receipt-path",
        "run-receipt.json",
        "--stage-binding-path",
        "stage-binding.json",
        "--workspace-root",
        "tri-workspace",
        "--input-root",
        "status-workspace",
        "--expected-batch-plan-sha256",
        "a" * 64,
        "--expected-scoped-config-manifest-sha256",
        "b" * 64,
        "--expected-stage-manifest-sha256",
        "c" * 64,
        "--decision-at",
        "2026-08-13T10:00:00+03:00",
        "--expected-run-id",
        "tri-run-001",
        "--expected-batch-id",
        "tri-batch-001",
    ]

    @patch("kubo.data_foundation_cli.import_status_history")
    @patch("kubo.data_foundation_cli._boundary_admission_request")
    def test_import_status_history_command_uses_declared_contract(
        self,
        request_builder,
        importer,
    ) -> None:
        admission_request = object()
        request_builder.return_value = admission_request
        importer.return_value = {
            "status": "HISTORICAL_STATUS_INTERVALS_READY",
        }
        output = StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "import-status-history",
                    "--status-corporate-root",
                    "status-root",
                    "--workspace",
                    "status-workspace",
                    "--output-root",
                    "status-output",
                    *self.ADMISSION_ARGUMENTS,
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(output.getvalue())["status"],
            "HISTORICAL_STATUS_INTERVALS_READY",
        )
        importer.assert_called_once_with(
            status_corporate_root=Path("status-root"),
            workspace=Path("status-workspace"),
            output_root=Path("status-output"),
            admission_request=admission_request,
        )
        self.assertEqual(
            request_builder.call_args.kwargs["boundary_inputs"],
            {
                "status_corporate_root": Path("status-root"),
                "workspace": Path("status-workspace"),
            },
        )

    def test_all_eight_production_boundaries_defer_missing_authority_paths_to_admission(
        self,
    ) -> None:
        root_parser = parser()
        subparsers = next(
            action
            for action in root_parser._actions
            if action.dest == "command"
        )
        commands = (
            "import-user-price-exports",
            "import-official-foundation",
            "import-status-corporate",
            "import-ca-enrichment",
            "import-status-history",
            "import-benchmark-history",
            "import-official-eod",
            "build-data-foundation-packet",
        )
        expected = {
            "--admission-path",
            "--workspace-root",
            "--input-root",
            "--expected-batch-plan-sha256",
            "--expected-scoped-config-manifest-sha256",
            "--expected-stage-manifest-sha256",
            "--decision-at",
            "--expected-run-id",
            "--expected-batch-id",
        }
        for command in commands:
            actions = subparsers.choices[command]._actions
            required = {
                option
                for action in actions
                if action.required
                for option in action.option_strings
            }
            self.assertTrue(expected <= required, command)
            self.assertNotIn("--receipt-path", required, command)
            self.assertNotIn("--stage-binding-path", required, command)

    def test_all_eight_commands_forward_exact_inputs_and_admission_request(
        self,
    ) -> None:
        cases = (
            (
                "import-user-price-exports",
                [
                    "--input-dir",
                    "price-input",
                    "--output-root",
                    "price-output",
                    "--observed-at",
                    "2026-08-13T09:00:00+03:00",
                ],
                "import_investing_user_exports",
                {
                    "config_dir": ROOT / "config",
                    "input_dir": Path("price-input"),
                },
            ),
            (
                "import-official-foundation",
                ["--workspace", "official-workspace", "--output-root", "official-output"],
                "import_official_foundation",
                {
                    "config_dir": ROOT / "config",
                    "workspace": Path("official-workspace"),
                },
            ),
            (
                "import-status-corporate",
                [
                    "--workspace",
                    "status-workspace",
                    "--official-foundation-root",
                    "official-root",
                    "--output-root",
                    "status-output",
                ],
                "import_status_corporate",
                {
                    "official_foundation_root": Path("official-root"),
                    "workspace": Path("status-workspace"),
                },
            ),
            (
                "import-ca-enrichment",
                [
                    "--status-corporate-root",
                    "status-root",
                    "--workspace",
                    "ca-workspace",
                    "--output-root",
                    "ca-output",
                ],
                "import_ca_enrichment",
                {
                    "status_corporate_root": Path("status-root"),
                    "workspace": Path("ca-workspace"),
                },
            ),
            (
                "import-status-history",
                [
                    "--status-corporate-root",
                    "status-root",
                    "--workspace",
                    "history-workspace",
                    "--output-root",
                    "history-output",
                ],
                "import_status_history",
                {
                    "status_corporate_root": Path("status-root"),
                    "workspace": Path("history-workspace"),
                },
            ),
            (
                "import-benchmark-history",
                [
                    "--official-foundation-root",
                    "official-root",
                    "--workspace",
                    "benchmark-workspace",
                    "--output-root",
                    "benchmark-output",
                    "--imported-at",
                    "2026-08-13T09:00:00+03:00",
                ],
                "import_benchmark_history",
                {
                    "config_dir": ROOT / "config",
                    "official_foundation_root": Path("official-root"),
                    "workspace": Path("benchmark-workspace"),
                },
            ),
            (
                "import-official-eod",
                [
                    "--workspace",
                    "eod-workspace",
                    "--official-foundation-root",
                    "official-root",
                    "--status-history-root",
                    "history-root",
                    "--output-root",
                    "eod-output",
                    "--run-id",
                    "eod-run-001",
                    "--imported-at",
                    "2026-08-13T09:00:00+03:00",
                ],
                "import_official_daily_eod",
                {
                    "workspace_root": Path("eod-workspace"),
                    "official_foundation_root": Path("official-root"),
                    "status_history_root": Path("history-root"),
                },
            ),
            (
                "build-data-foundation-packet",
                [
                    "--official-foundation-root",
                    "official-root",
                    "--status-history-root",
                    "history-root",
                    "--ca-enrichment-root",
                    "ca-root",
                    "--research-price-history-root",
                    "price-root",
                    "--benchmark-root",
                    "benchmark-root",
                    "--official-eod-root",
                    "eod-root",
                    "--output-root",
                    "packet-output",
                ],
                "build_data_foundation_packet",
                {
                    "official_foundation_root": Path("official-root"),
                    "status_history_root": Path("history-root"),
                    "ca_enrichment_root": Path("ca-root"),
                    "research_price_history_root": Path("price-root"),
                    "benchmark_root": Path("benchmark-root"),
                    "official_eod_root": Path("eod-root"),
                    "project_root": ROOT,
                    "outcome_session_policy_path": (
                        ROOT / "config" / "pilot" / "outcome_session_policy.json"
                    ),
                },
            ),
        )
        for command, command_arguments, importer_name, expected_inputs in cases:
            with self.subTest(command=command):
                request = object()
                output = StringIO()
                with (
                    patch(
                        "kubo.data_foundation_cli._boundary_admission_request",
                        return_value=request,
                    ) as request_builder,
                    patch(
                        f"kubo.data_foundation_cli.{importer_name}",
                        return_value={"status": "PASS"},
                    ) as importer,
                    redirect_stdout(output),
                ):
                    code = main(
                        [
                            "--project-root",
                            str(ROOT),
                            command,
                            *command_arguments,
                            *self.ADMISSION_ARGUMENTS,
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertEqual(
                    request_builder.call_args.kwargs["boundary_inputs"],
                    expected_inputs,
                )
                self.assertIs(
                    importer.call_args.kwargs["admission_request"],
                    request,
                )

    def test_admission_request_constructor_uses_three_runtime_authorities(self) -> None:
        args = parser().parse_args(
            [
                "--project-root",
                str(ROOT),
                "import-status-history",
                "--status-corporate-root",
                "status-root",
                "--workspace",
                "status-workspace",
                "--output-root",
                "status-output",
                *self.ADMISSION_ARGUMENTS,
                "--predecessor-admission",
                "status-corporate-admission.json",
            ]
        )
        environment = {
            "KUBO_TRI_RUN_HMAC_KEY": "hex:" + (b"r" * 32).hex(),
            "KUBO_TRI_RUN_HMAC_KEY_ID": "run-key-v1",
            "KUBO_TRI_STAGE_HMAC_KEY": "hex:" + (b"s" * 32).hex(),
            "KUBO_TRI_STAGE_HMAC_KEY_ID": "stage-key-v1",
            "KUBO_TRI_SEMANTIC_HMAC_KEY": "hex:" + (b"m" * 32).hex(),
            "KUBO_TRI_SEMANTIC_HMAC_KEY_ID": "semantic-key-v2",
        }
        boundary_inputs = {
            "status_corporate_root": Path("status-root"),
            "workspace": Path("status-workspace"),
        }
        with patch.dict("os.environ", environment, clear=False):
            request = _boundary_admission_request(
                args,
                boundary_inputs=boundary_inputs,
                operation_binding=build_boundary_operation_binding(
                    "import_status_history",
                    decision_at="2026-08-13T10:00:00+03:00",
                ),
            )

        self.assertEqual(request.run_key, b"r" * 32)
        self.assertEqual(request.v1_stage_key, b"s" * 32)
        self.assertEqual(request.semantic_key, b"m" * 32)
        self.assertEqual(request.semantic_key_id, "semantic-key-v2")
        self.assertEqual(dict(request.boundary_inputs), boundary_inputs)
        self.assertEqual(
            request.predecessor_admission_paths,
            (Path("status-corporate-admission.json"),),
        )

    def test_missing_authority_cli_options_build_none_request_fields(self) -> None:
        args = parser().parse_args(
            [
                "--project-root",
                str(ROOT),
                "import-status-history",
                "--status-corporate-root",
                "status-root",
                "--workspace",
                "status-workspace",
                "--output-root",
                "status-output",
                "--admission-path",
                "semantic-admission.json",
                "--workspace-root",
                "tri-workspace",
                "--input-root",
                "status-workspace",
                "--expected-batch-plan-sha256",
                "a" * 64,
                "--expected-scoped-config-manifest-sha256",
                "b" * 64,
                "--expected-stage-manifest-sha256",
                "c" * 64,
                "--decision-at",
                "2026-08-13T10:00:00+03:00",
                "--expected-run-id",
                "tri-run-001",
                "--expected-batch-id",
                "tri-batch-001",
            ]
        )
        environment = {
            "KUBO_TRI_RUN_HMAC_KEY": "hex:" + (b"r" * 32).hex(),
            "KUBO_TRI_RUN_HMAC_KEY_ID": "run-key-v1",
            "KUBO_TRI_STAGE_HMAC_KEY": "hex:" + (b"s" * 32).hex(),
            "KUBO_TRI_STAGE_HMAC_KEY_ID": "stage-key-v1",
            "KUBO_TRI_SEMANTIC_HMAC_KEY": "hex:" + (b"m" * 32).hex(),
            "KUBO_TRI_SEMANTIC_HMAC_KEY_ID": "semantic-key-v2",
        }
        boundary_inputs = {
            "status_corporate_root": Path("status-root"),
            "workspace": Path("status-workspace"),
        }

        self.assertIsNone(args.receipt_path)
        self.assertIsNone(args.stage_binding_path)
        with patch.dict("os.environ", environment, clear=False):
            request = _boundary_admission_request(
                args,
                boundary_inputs=boundary_inputs,
                operation_binding=build_boundary_operation_binding(
                    "import_status_history",
                    decision_at="2026-08-13T10:00:00+03:00",
                ),
            )

        self.assertIsNone(request.receipt_path)
        self.assertIsNone(request.stage_binding_path)

    def test_issue_semantic_admission_command_verifies_v1_and_uses_third_key(
        self,
    ) -> None:
        environment = {
            "KUBO_TRI_RUN_HMAC_KEY": "hex:" + (b"r" * 32).hex(),
            "KUBO_TRI_RUN_HMAC_KEY_ID": "run-key-v1",
            "KUBO_TRI_STAGE_HMAC_KEY": "hex:" + (b"s" * 32).hex(),
            "KUBO_TRI_STAGE_HMAC_KEY_ID": "stage-key-v1",
            "KUBO_TRI_SEMANTIC_HMAC_KEY": "hex:" + (b"m" * 32).hex(),
            "KUBO_TRI_SEMANTIC_HMAC_KEY_ID": "semantic-key-v2",
        }
        verified_receipt = object()
        verified_stage = Mock()
        verified_stage.report.return_value = {
            "binding_sha256": "d" * 64,
            "stage_id": "OFFICIAL_FOUNDATION",
        }
        issuance = {
            "status": "PASS",
            "boundary_id": "import_official_foundation",
        }
        output = StringIO()
        with (
            patch.dict("os.environ", environment, clear=False),
            patch(
                "kubo.data_foundation_cli.verify_tri_security_run_receipt",
                return_value=verified_receipt,
            ) as verify_receipt,
            patch(
                "kubo.data_foundation_cli.verify_tri_security_stage_binding",
                return_value=verified_stage,
            ) as verify_stage,
            patch(
                "kubo.data_foundation_cli.issue_semantic_boundary_admission",
                return_value=issuance,
            ) as issue,
            redirect_stdout(output),
        ):
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "issue-tri-security-semantic-admission",
                    "--boundary-id",
                    "import_official_foundation",
                    "--receipt-path",
                    "run-receipt.json",
                    "--stage-binding-path",
                    "stage-binding.json",
                    "--workspace-root",
                    "tri-workspace",
                    "--input-root",
                    "official-workspace",
                    "--output-path",
                    "semantic-admission.json",
                    "--expected-batch-plan-sha256",
                    "a" * 64,
                    "--expected-scoped-config-manifest-sha256",
                    "b" * 64,
                    "--expected-stage-manifest-sha256",
                    "c" * 64,
                    "--expected-run-id",
                    "tri-run-001",
                    "--expected-batch-id",
                    "tri-batch-001",
                    "--admission-id",
                    "official-foundation-admission",
                    "--issued-at",
                    "2026-08-13T10:00:00+03:00",
                    "--operation-decision-at",
                    "2026-08-13T10:00:00+03:00",
                    "--boundary-input",
                    "config_dir=config",
                    "--boundary-input",
                    "workspace=official-workspace",
                ]
            )

        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()), issuance)
        self.assertEqual(
            verify_stage.call_args.kwargs["expected_stage_id"],
            "OFFICIAL_FOUNDATION",
        )
        self.assertIs(issue.call_args.kwargs["verified_receipt"], verified_receipt)
        self.assertEqual(issue.call_args.kwargs["key"], b"m" * 32)
        self.assertEqual(issue.call_args.kwargs["key_id"], "semantic-key-v2")
        self.assertEqual(
            issue.call_args.kwargs["boundary_inputs"],
            {
                "config_dir": Path("config"),
                "workspace": Path("official-workspace"),
            },
        )
        self.assertEqual(
            issue.call_args.kwargs["operation_binding"]["arguments"],
            {},
        )
        verify_receipt.assert_called_once()

    def test_boundary_input_parser_rejects_duplicate_roles(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _parse_boundary_inputs(["workspace=one", "workspace=two"])

    def test_independent_validation_blocker_controls_exit_status(self) -> None:
        self.assertTrue(
            _report_is_blocking(
                {
                    "status": "OFFICIAL_COMPLETE_EOD_READY",
                    "validation_status": "BLOCKED",
                }
            )
        )
        self.assertFalse(
            _report_is_blocking(
                {
                    "status": "OFFICIAL_COMPLETE_EOD_READY",
                    "validation_status": "PASS",
                }
            )
        )

    def test_validate_benchmark_registry_command(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "validate-benchmark-registry",
                ]
            )
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "PASS")
        self.assertGreater(report["benchmark_count"], 1)
        self.assertEqual(
            report["benchmark_count"], report["required_benchmark_count"]
        )
        self.assertEqual(len(report["registry_sha256"]), 64)

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
