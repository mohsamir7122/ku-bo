from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.codex_control_check import REQUIRED_FILES, validate


ROOT = Path(__file__).resolve().parents[1]


class CodexControlCheckTests(unittest.TestCase):
    def test_repository_control_layer_passes(self) -> None:
        report = validate(ROOT)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["task_id"], "KU-BO-2026-08-26-INTEGRATION")
        self.assertEqual(
            report["expected_branch"],
            "codex/kuwait-engine-integration-v1",
        )
        self.assertFalse(
            report["claim_boundaries"]["control_check_authorizes_merge"]
        )
        self.assertFalse(
            report["claim_boundaries"]["control_check_proves_backtest_readiness"]
        )

    def _copy_control_surface(self, destination: Path) -> None:
        for relative in REQUIRED_FILES:
            source = ROOT / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def test_merge_permission_cannot_be_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control_surface(root)
            task = root / "docs/codex/CURRENT_TASK.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "MERGE_ALLOWED: NO",
                    "MERGE_ALLOWED: YES",
                    1,
                ),
                encoding="utf-8",
            )
            report = validate(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn(
                "CURRENT_TASK_UNSAFE_PERMISSION:MERGE_ALLOWED",
                report["errors"],
            )

    def test_private_drive_url_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control_surface(root)
            start = root / "CODEX_START_HERE.md"
            start.write_text(
                start.read_text(encoding="utf-8")
                + "\nhttps://drive.google.com/drive/folders/private-id\n",
                encoding="utf-8",
            )
            report = validate(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn(
                "PRIVATE_GOOGLE_URL_COMMITTED:CODEX_START_HERE.md",
                report["errors"],
            )

    def test_raw_conversation_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control_surface(root)
            path = root / "docs/codex/raw_conversations/chat.txt"
            path.parent.mkdir(parents=True)
            path.write_text("private transcript", encoding="utf-8")
            report = validate(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any(
                    error.startswith("RAW_CONVERSATION_PATH_FORBIDDEN:")
                    for error in report["errors"]
                )
            )


if __name__ == "__main__":
    unittest.main()
