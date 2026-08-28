from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts.codex_control_check import (
    CONTROL_STATE_FILE,
    REQUIRED_FILES,
    validate,
)


ROOT = Path(__file__).resolve().parents[1]


class CodexControlCheckTests(unittest.TestCase):
    @staticmethod
    def _control_state(root: Path = ROOT) -> dict:
        return json.loads((root / CONTROL_STATE_FILE).read_text(encoding="utf-8"))

    def test_repository_control_layer_passes(self) -> None:
        state = self._control_state()
        report = validate(ROOT)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["task_id"], state["task_id"])
        self.assertEqual(report["expected_branch"], state["work_branch"])
        self.assertEqual(report["control_base_sha"], state["control_base_sha"])
        self.assertEqual(
            report["git_state"]["observed_work_branch"],
            state["work_branch"],
        )
        self.assertEqual(
            report["git_state"]["control_base_ref_sha"],
            state["control_base_sha"],
        )
        self.assertTrue(report["git_state"]["base_is_ancestor_of_head"])
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

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _prepare_live_git_fixture(self, root: Path) -> tuple[str, str]:
        root.mkdir(parents=True, exist_ok=True)
        self._git(root, "init", "-b", "main")
        self._git(root, "config", "user.email", "control-test@example.invalid")
        self._git(root, "config", "user.name", "Control Test")
        seed = root / "seed.txt"
        seed.write_text("base\n", encoding="utf-8")
        self._git(root, "add", "seed.txt")
        self._git(root, "commit", "-m", "base")
        base_sha = self._git(root, "rev-parse", "HEAD")
        work_branch = "test/control-branch"
        self._git(root, "checkout", "-b", work_branch)
        self._copy_control_surface(root)

        state_path = root / CONTROL_STATE_FILE
        state = self._control_state(root)
        original_base = state["control_base_sha"]
        original_branch = state["work_branch"]
        state["control_base_sha"] = base_sha
        state["work_branch"] = work_branch
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for relative in (
            "CODEX_START_HERE.md",
            "STATUS.md",
            "NEXT_ACTIONS.md",
            "docs/codex/CURRENT_STATUS.md",
            "docs/codex/CURRENT_TASK.md",
        ):
            path = root / relative
            path.write_text(
                path.read_text(encoding="utf-8")
                .replace(original_base, base_sha)
                .replace(original_branch, work_branch),
                encoding="utf-8",
            )
        progress_path = root / "PROGRESS.json"
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        progress["active_control"]["control_base_sha"] = base_sha
        progress["active_control"]["work_branch"] = work_branch
        progress["base_sha"] = base_sha
        progress["work_branch"] = work_branch
        progress_path.write_text(
            json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "add control surface")
        return base_sha, work_branch

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
            report = validate(root, check_git=False)
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
            report = validate(root, check_git=False)
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
            report = validate(root, check_git=False)
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(
                any(
                    error.startswith("RAW_CONVERSATION_PATH_FORBIDDEN:")
                    for error in report["errors"]
                )
            )

    def test_task_identity_must_match_canonical_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control_surface(root)
            task = root / "docs/codex/CURRENT_TASK.md"
            state = self._control_state(root)
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    f"TASK_ID: {state['task_id']}",
                    "TASK_ID: STALE-TASK",
                    1,
                ),
                encoding="utf-8",
            )
            report = validate(root, check_git=False)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn(
                "CONTROL_STATE_TASK_MISMATCH:TASK_ID",
                report["errors"],
            )

    def test_progress_mirror_must_match_canonical_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._copy_control_surface(root)
            progress_path = root / "PROGRESS.json"
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            progress["active_control"]["work_branch"] = "stale/branch"
            progress_path.write_text(
                json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            report = validate(root, check_git=False)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn(
                "PROGRESS_ACTIVE_CONTROL_MISMATCH:work_branch",
                report["errors"],
            )

    def test_live_git_wrong_branch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, expected_branch = self._prepare_live_git_fixture(root)
            self._git(root, "checkout", "-b", "test/wrong-branch")
            report = validate(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn(
                f"GIT_WORK_BRANCH_MISMATCH:test/wrong-branch:{expected_branch}",
                report["errors"],
            )

    def test_detached_push_checkout_uses_github_branch_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, expected_branch = self._prepare_live_git_fixture(root)
            head_sha = self._git(root, "rev-parse", "HEAD")
            self._git(root, "checkout", "--detach", head_sha)
            with mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_REF": f"refs/heads/{expected_branch}",
                    "GITHUB_SHA": head_sha,
                },
                clear=False,
            ):
                report = validate(root)
            self.assertEqual(report["status"], "PASS", report["errors"])
            self.assertEqual(
                report["git_state"]["observed_work_branch"],
                expected_branch,
            )

    def test_exact_pull_request_head_checkout_uses_event_sha(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_sha, expected_branch = self._prepare_live_git_fixture(root)
            head_sha = self._git(root, "rev-parse", "HEAD")
            event_path = root / "event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "pull_request": {
                            "base": {"ref": "main", "sha": base_sha},
                            "head": {"ref": expected_branch, "sha": head_sha},
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self._git(root, "checkout", "--detach", head_sha)
            with mock.patch.dict(
                "os.environ",
                {
                    "GITHUB_EVENT_PATH": str(event_path),
                    "GITHUB_HEAD_REF": expected_branch,
                    "GITHUB_REF": "refs/pull/1/merge",
                    # GitHub exposes the synthetic merge SHA here, while CI
                    # deliberately checks out the immutable PR-head SHA.
                    "GITHUB_SHA": "f" * 40,
                },
                clear=False,
            ):
                report = validate(root)
            self.assertEqual(report["status"], "PASS", report["errors"])
            self.assertEqual(report["git_state"]["actual_head_sha"], head_sha)

    def test_live_git_moved_base_ref_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_sha, _ = self._prepare_live_git_fixture(root)
            self._git(root, "branch", "-f", "main", "HEAD")
            moved_sha = self._git(root, "rev-parse", "main")
            report = validate(root)
            self.assertEqual(report["status"], "FAIL")
            self.assertIn(
                f"GIT_BASE_REF_MOVED:main:{moved_sha}:{base_sha}",
                report["errors"],
            )

    def test_live_git_invalid_ancestry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_sha, original_branch = self._prepare_live_git_fixture(root)
            divergent_branch = "test/divergent-branch"
            self._git(root, "checkout", "--orphan", divergent_branch)
            state_path = root / CONTROL_STATE_FILE
            state = self._control_state(root)
            state["work_branch"] = divergent_branch
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            for relative in (
                "CODEX_START_HERE.md",
                "STATUS.md",
                "NEXT_ACTIONS.md",
                "docs/codex/CURRENT_STATUS.md",
                "docs/codex/CURRENT_TASK.md",
            ):
                path = root / relative
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        original_branch,
                        divergent_branch,
                    ),
                    encoding="utf-8",
                )
            progress_path = root / "PROGRESS.json"
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            progress["active_control"]["work_branch"] = divergent_branch
            progress["work_branch"] = divergent_branch
            progress_path.write_text(
                json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "divergent control")
            report = validate(root)
            head_sha = self._git(root, "rev-parse", "HEAD")
            self.assertEqual(report["status"], "FAIL")
            self.assertIn(
                f"GIT_BASE_NOT_ANCESTOR_OF_HEAD:{base_sha}:{head_sha}",
                report["errors"],
            )


if __name__ == "__main__":
    unittest.main()
