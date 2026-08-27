from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from kubo.cli_v3 import main
from kubo.data_foundation_cli import _report_is_blocking
from kubo.exit_status import is_blocking_status


ROOT = Path(__file__).resolve().parents[1]


class ExitStatusTests(unittest.TestCase):
    def test_blocked_and_equivalent_statuses_are_nonzero_classes(self) -> None:
        for status in (
            "DRY_RUN_BLOCKED",
            "BLOCKED_PENDING_SOURCE",
            "RESEARCH_ASSET_PENDING_ADMISSION",
            "ACCESS_REVIEW_REQUIRED",
            "RETRYABLE_RATE_LIMIT",
            "ROBOTS_UNREACHABLE",
            "CAPABILITY_EXHAUSTED_ABSTAIN",
            "NO_TRADE",
        ):
            with self.subTest(status=status):
                self.assertTrue(is_blocking_status(status))

    def test_success_statuses_are_not_misclassified(self) -> None:
        for status in (
            "PASS",
            "PASS_FAIL_CLOSED_RECOVERY_POLICY",
            "CAPABILITY_EVIDENCE_AVAILABLE",
            "CAPABILITY_VERIFIED_ZERO_RESULT",
            "DRY_RUN_COMPLETE_NO_RECOMMENDATION",
        ):
            with self.subTest(status=status):
                self.assertFalse(is_blocking_status(status))

    def test_data_foundation_nested_statuses_fail_closed(self) -> None:
        self.assertTrue(
            _report_is_blocking(
                {
                    "status": "PASS",
                    "validation_status": "DRY_RUN_BLOCKED",
                    "contract_status": "PASS",
                }
            )
        )

    def test_cli_returns_nonzero_for_blocked_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()):
            code = main(
                [
                    "--project-root",
                    str(ROOT),
                    "run-live-dry-run",
                    "--private-runtime-root",
                    temporary,
                    "--output-root",
                    "runs",
                    "--run-id",
                    "blocked-cli-run",
                    "--decision-session-date",
                    "2026-08-24",
                    "--recorded-at",
                    "2026-08-24T08:00:00+03:00",
                ]
            )
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
