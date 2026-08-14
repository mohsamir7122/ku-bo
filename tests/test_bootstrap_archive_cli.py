from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date, datetime, timezone
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from kubo.atomic_output import AtomicOutputError, OUTPUT_ROOT_ALREADY_EXISTS
from kubo.bootstrap_archive.workspace import prepare_bootstrap_archive
from kubo.cli_v3 import main, parser


ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 8, 14)
EXTERNAL_TEMP_ROOT = (
    Path("/dev/shm") if Path("/dev/shm").is_dir() else Path(tempfile.gettempdir())
)


def _run(argv: list[str]) -> tuple[int, dict[str, object]]:
    output = StringIO()
    with redirect_stdout(output):
        code = main(argv)
    payload = json.loads(output.getvalue())
    if not isinstance(payload, dict):
        raise AssertionError("CLI did not emit one JSON object")
    return code, payload


class BootstrapArchiveCliTests(unittest.TestCase):
    def test_parser_exposes_only_validate_config_prepare_and_verify_archive_commands(self) -> None:
        root_parser = parser()
        subparsers = next(action for action in root_parser._actions if action.dest == "command")
        self.assertIn("validate-bootstrap-archive-config", subparsers.choices)
        self.assertIn("prepare-bootstrap-archive", subparsers.choices)
        self.assertIn("validate-bootstrap-archive", subparsers.choices)
        self.assertNotIn("collect-bootstrap-archive", subparsers.choices)
        self.assertNotIn("run-company-intelligence", subparsers.choices)
        self.assertNotIn("run-source-waves", subparsers.choices)
        self.assertNotIn("reconcile-bootstrap-with-boursa", subparsers.choices)

    def test_validate_bootstrap_config_reports_declared_only_noncollection(self) -> None:
        code, payload = _run(
            [
                "--project-root",
                str(ROOT),
                "validate-bootstrap-archive-config",
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "PASS_CONTRACT")
        self.assertEqual(
            payload["bootstrap_archive"]["source_runtime_binding_status"],
            "ALL_UNBOUND",
        )
        self.assertEqual(payload["source_crosswalk"]["readiness_status"], "DEFINED_ONLY")
        self.assertIs(payload["source_crosswalk"]["collection_allowed"], False)
        self.assertIs(payload["source_crosswalk"]["live_operational"], False)

    def test_prepare_then_validate_archive_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = Path(directory) / "archive"
            prepare_code, prepared = _run(
                [
                    "--project-root",
                    str(ROOT),
                    "prepare-bootstrap-archive",
                    "--as-of",
                    AS_OF.isoformat(),
                    "--output-root",
                    str(archive),
                ]
            )
            self.assertEqual(prepare_code, 0)
            self.assertEqual(prepared["status"], "PASS_SCAFFOLD_PREPARATION")
            self.assertEqual(
                prepared["pre_commit_validation"]["status"],
                "PASS_EMPTY_ARCHIVE_SCAFFOLD",
            )

            validate_code, verified = _run(
                [
                    "--project-root",
                    str(Path(directory) / "not-a-checkout"),
                    "validate-bootstrap-archive",
                    "--archive-root",
                    str(archive),
                ]
            )
            self.assertEqual(validate_code, 0)
            self.assertEqual(verified["status"], "PASS_EMPTY_ARCHIVE_SCAFFOLD")
            self.assertEqual(verified["evidence_artifact_count"], 0)
            self.assertEqual(verified["company_count"], 0)
            self.assertEqual(verified["event_count"], 0)
            self.assertIs(verified["collection_allowed"], False)

    def test_prepare_cli_is_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = Path(directory) / "archive"
            first_code, _ = _run(
                [
                    "--project-root",
                    str(ROOT),
                    "prepare-bootstrap-archive",
                    "--as-of",
                    AS_OF.isoformat(),
                    "--output-root",
                    str(archive),
                ]
            )
            self.assertEqual(first_code, 0)
            descriptor = (archive / "bootstrap_archive.json").read_bytes()

            with self.assertRaises(AtomicOutputError) as captured:
                main(
                    [
                        "--project-root",
                        str(ROOT),
                        "prepare-bootstrap-archive",
                        "--as-of",
                        AS_OF.isoformat(),
                        "--output-root",
                        str(archive),
                    ]
                )
            self.assertEqual(captured.exception.code, OUTPUT_ROOT_ALREADY_EXISTS)
            self.assertEqual((archive / "bootstrap_archive.json").read_bytes(), descriptor)

    def test_prepare_requires_a_real_project_root_before_output_creation(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            root = Path(directory)
            output = root / "archive"
            with self.assertRaisesRegex(SystemExit, "project root is invalid"):
                main(
                    [
                        "--project-root",
                        str(root / "missing-checkout"),
                        "prepare-bootstrap-archive",
                        "--as-of",
                        AS_OF.isoformat(),
                        "--output-root",
                        str(output),
                    ]
                )
            self.assertFalse(output.exists())

    def test_validate_cli_rejects_tampered_archive(self) -> None:
        with tempfile.TemporaryDirectory(dir=EXTERNAL_TEMP_ROOT) as directory:
            archive = Path(directory) / "archive"
            prepare_bootstrap_archive(
                project_root=ROOT,
                output_root=archive,
                as_of=AS_OF,
                prepared_at=datetime(2026, 8, 14, 18, 30, tzinfo=timezone.utc),
            )
            (archive / "raw" / "editorial" / "unadmitted.bin").write_bytes(b"raw")

            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                main(
                    [
                        "validate-bootstrap-archive",
                        "--archive-root",
                        str(archive),
                    ]
                )


if __name__ == "__main__":
    unittest.main()
