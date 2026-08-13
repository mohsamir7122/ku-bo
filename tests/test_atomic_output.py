from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from kubo.atomic_output import (
    ARTIFACT_VALIDATION_PRE_WRITE,
    AtomicOutputError,
    ENTRY_PRE_WRITE,
    OUTPUT_ROOT_ALREADY_EXISTS,
    OUTPUT_ROOT_CHANGED_DURING_COMMIT,
    PARTIAL_OUTPUT_FORBIDDEN,
    PRE_COMMIT_RECHECK,
    run_atomic_output,
)
import kubo.atomic_output as atomic_output


class AtomicOutputTests(unittest.TestCase):
    def _staging_entries(self, parent: Path, target_name: str) -> list[Path]:
        prefix = f".{target_name}.staging-"
        return sorted(path for path in parent.iterdir() if path.name.startswith(prefix))

    def test_success_publishes_complete_tree_and_returns_worker_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "packet"

            def worker(staging: Path) -> dict[str, int]:
                self.assertTrue(staging.name.startswith(".packet.staging-"))
                (staging / "reports").mkdir()
                (staging / "reports" / "result.json").write_text(
                    '{"status":"PASS"}\n',
                    encoding="utf-8",
                )
                return {"files": 1}

            result = run_atomic_output(target, worker)

            self.assertEqual(result, {"files": 1})
            self.assertEqual(
                (target / "reports" / "result.json").read_text(encoding="utf-8"),
                '{"status":"PASS"}\n',
            )
            self.assertEqual(self._staging_entries(parent, target.name), [])

    def test_before_commit_runs_after_worker_and_can_inspect_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "output"
            observations: list[str] = []

            def worker(staging: Path) -> str:
                (staging / "ready.txt").write_text("ready", encoding="utf-8")
                observations.append("worker")
                return "published"

            def before_commit(staging: Path) -> None:
                self.assertEqual(
                    (staging / "ready.txt").read_text(encoding="utf-8"),
                    "ready",
                )
                observations.append("before_commit")

            result = run_atomic_output(
                target,
                worker,
                before_commit=before_commit,
            )

            self.assertEqual(result, "published")
            self.assertEqual(observations, ["worker", "before_commit"])
            self.assertTrue((target / "ready.txt").is_file())

    def test_preexisting_directory_is_rejected_without_calling_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            target.mkdir()
            marker = target / "owner.txt"
            marker.write_text("preserve", encoding="utf-8")
            called = False

            def worker(staging: Path) -> None:
                nonlocal called
                called = True

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(target, worker)

            self.assertEqual(captured.exception.code, OUTPUT_ROOT_ALREADY_EXISTS)
            self.assertFalse(called)
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_preexisting_empty_directory_is_also_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            target.mkdir()

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(target, lambda staging: None)

            self.assertEqual(captured.exception.code, OUTPUT_ROOT_ALREADY_EXISTS)
            self.assertTrue(target.is_dir())
            self.assertEqual(list(target.iterdir()), [])

    def test_preexisting_file_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"
            target.write_bytes(b"owner-bytes")

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(target, lambda staging: None)

            self.assertEqual(captured.exception.code, OUTPUT_ROOT_ALREADY_EXISTS)
            self.assertEqual(target.read_bytes(), b"owner-bytes")

    def test_preexisting_symlink_is_never_followed_or_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            owner = parent / "owner"
            owner.mkdir()
            target = parent / "output"
            try:
                target.symlink_to(owner, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("directory symlinks are unavailable")

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(target, lambda staging: None)

            self.assertEqual(captured.exception.code, OUTPUT_ROOT_ALREADY_EXISTS)
            self.assertTrue(target.is_symlink())
            self.assertTrue(owner.is_dir())

    def test_missing_parent_is_rejected_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "missing"
            target = parent / "output"

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(target, lambda staging: None)

            self.assertEqual(captured.exception.code, PARTIAL_OUTPUT_FORBIDDEN)
            self.assertFalse(parent.exists())

    def test_symlink_parent_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_parent = root / "real"
            real_parent.mkdir()
            linked_parent = root / "linked"
            try:
                linked_parent.symlink_to(real_parent, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("directory symlinks are unavailable")

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(linked_parent / "output", lambda staging: None)

            self.assertEqual(captured.exception.code, PARTIAL_OUTPUT_FORBIDDEN)
            self.assertEqual(list(real_parent.iterdir()), [])

    def test_worker_exception_discards_staging_and_exposes_structured_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "output"

            def worker(staging: Path) -> None:
                (staging / "partial.txt").write_text("partial", encoding="utf-8")
                raise RuntimeError("validation failed")

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(target, worker)

            self.assertEqual(captured.exception.code, PARTIAL_OUTPUT_FORBIDDEN)
            self.assertIsInstance(captured.exception.__cause__, RuntimeError)
            self.assertFalse(target.exists())
            self.assertEqual(self._staging_entries(parent, target.name), [])

    def test_worker_failure_retains_serialized_entry_channel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output"

            def worker(staging: Path) -> None:
                (staging / "partial.txt").write_text("partial", encoding="utf-8")
                raise RuntimeError("serialized validation failed")

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(
                    target,
                    worker,
                    failure_phase=ARTIFACT_VALIDATION_PRE_WRITE,
                )

            self.assertEqual(captured.exception.failure_code, PARTIAL_OUTPUT_FORBIDDEN)
            self.assertEqual(
                captured.exception.failure_phase,
                ARTIFACT_VALIDATION_PRE_WRITE,
            )
            self.assertFalse(target.exists())

    def test_before_commit_exception_also_discards_staging(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "output"

            def before_commit(staging: Path) -> None:
                self.assertTrue((staging / "complete.txt").is_file())
                raise RuntimeError("pre-commit validation failed")

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(
                    target,
                    lambda staging: (staging / "complete.txt").write_text(
                        "complete",
                        encoding="utf-8",
                    ),
                    before_commit=before_commit,
                )

            self.assertEqual(captured.exception.code, PARTIAL_OUTPUT_FORBIDDEN)
            self.assertIsInstance(captured.exception.__cause__, RuntimeError)
            self.assertFalse(target.exists())
            self.assertEqual(self._staging_entries(parent, target.name), [])

    def test_stable_pre_commit_rejection_is_preserved_after_cleanup(self) -> None:
        class StableAdmissionRejection(RuntimeError):
            failure_code = "STAGE_TREE_CHANGED_DURING_VERIFICATION"
            failure_phase = "PRE_COMMIT_RECHECK"

        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "output"
            rejection = StableAdmissionRejection("stage tree changed")

            def before_commit(staging: Path) -> None:
                self.assertTrue((staging / "complete.txt").is_file())
                raise rejection

            with self.assertRaises(StableAdmissionRejection) as captured:
                run_atomic_output(
                    target,
                    lambda staging: (staging / "complete.txt").write_text(
                        "complete",
                        encoding="utf-8",
                    ),
                    before_commit=before_commit,
                )

            self.assertIs(captured.exception, rejection)
            self.assertFalse(target.exists())
            self.assertEqual(self._staging_entries(parent, target.name), [])

    def test_target_created_by_before_commit_race_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "output"

            def worker(staging: Path) -> None:
                (staging / "ours.txt").write_text("ours", encoding="utf-8")

            def before_commit(staging: Path) -> None:
                del staging
                target.mkdir()
                (target / "owner.txt").write_text("racer", encoding="utf-8")

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(target, worker, before_commit=before_commit)

            self.assertEqual(
                captured.exception.code,
                OUTPUT_ROOT_CHANGED_DURING_COMMIT,
            )
            self.assertEqual(captured.exception.failure_phase, PRE_COMMIT_RECHECK)
            self.assertEqual(
                (target / "owner.txt").read_text(encoding="utf-8"),
                "racer",
            )
            self.assertEqual(self._staging_entries(parent, target.name), [])

    def test_no_overwrite_primitive_closes_race_after_final_absence_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "output"
            original = atomic_output._rename_noreplace

            def race(parent_guard, staging_guard, target_name):
                target.mkdir()
                (target / "owner.txt").write_text("late-racer", encoding="utf-8")
                return original(parent_guard, staging_guard, target_name)

            with patch("kubo.atomic_output._rename_noreplace", side_effect=race):
                with self.assertRaises(AtomicOutputError) as captured:
                    run_atomic_output(
                        target,
                        lambda staging: (staging / "ours.txt").write_text(
                            "ours",
                            encoding="utf-8",
                        ),
                    )

            self.assertEqual(
                captured.exception.code,
                OUTPUT_ROOT_CHANGED_DURING_COMMIT,
            )
            self.assertEqual(
                (target / "owner.txt").read_text(encoding="utf-8"),
                "late-racer",
            )
            self.assertEqual(self._staging_entries(parent, target.name), [])

    @unittest.skipIf(os.name == "nt", "directory replacement semantics differ on Windows")
    def test_parent_replacement_is_detected_and_original_staging_is_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "parent"
            displaced = root / "displaced-parent"
            parent.mkdir()
            target = parent / "output"

            def worker(staging: Path) -> None:
                (staging / "partial.txt").write_text("partial", encoding="utf-8")

            def before_commit(staging: Path) -> None:
                del staging
                parent.rename(displaced)
                parent.mkdir()

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(target, worker, before_commit=before_commit)

            self.assertEqual(
                captured.exception.code,
                OUTPUT_ROOT_CHANGED_DURING_COMMIT,
            )
            self.assertFalse(target.exists())
            self.assertEqual(self._staging_entries(displaced, target.name), [])

    def test_removed_staging_is_rejected_as_partial_output_violation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "output"

            def before_commit(staging: Path) -> None:
                shutil.rmtree(staging)

            with self.assertRaises(AtomicOutputError) as captured:
                run_atomic_output(
                    target,
                    lambda staging: (staging / "partial.txt").write_text(
                        "partial",
                        encoding="utf-8",
                    ),
                    before_commit=before_commit,
                )

            self.assertEqual(captured.exception.code, PARTIAL_OUTPUT_FORBIDDEN)
            self.assertFalse(target.exists())
            self.assertEqual(self._staging_entries(parent, target.name), [])

    def test_error_has_stable_machine_readable_shape(self) -> None:
        error = AtomicOutputError(OUTPUT_ROOT_ALREADY_EXISTS, "target exists")
        self.assertEqual(error.failure_code, OUTPUT_ROOT_ALREADY_EXISTS)
        self.assertEqual(error.failure_phase, ENTRY_PRE_WRITE)
        self.assertEqual(
            error.to_dict(),
            {
                "error": "ATOMIC_OUTPUT_ERROR",
                "code": OUTPUT_ROOT_ALREADY_EXISTS,
                "phase": ENTRY_PRE_WRITE,
                "message": "target exists",
            },
        )
        with self.assertRaises(ValueError):
            AtomicOutputError("UNKNOWN", "invalid")


if __name__ == "__main__":
    unittest.main()
